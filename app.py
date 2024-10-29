import os
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from database import db
from monitoring import setup_logging, start_monitoring, log_request_metrics
from error_handling.exceptions import TranscriptionError, ValidationError, APIError
from error_handling.handlers import handle_errors, error_context, retry_on_error, log_errors
from transcription.deepgram_client import DeepgramTranscriptionClient, DeepgramAPIError
import asyncio
from flask_cors import CORS
import traceback

# Set up enhanced logging
logger, perf_logger = setup_logging()

app = Flask(__name__, static_url_path='/static', static_folder='static')
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configuration
app.secret_key = os.urandom(24)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
    "pool_size": 10,
    "max_overflow": 20,
}

# File upload settings
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB
app.config['ALLOWED_EXTENSIONS'] = {'wav', 'mp3', 'flac', 'mp4'}

# Processing timeouts
app.config['PROCESSING_TIMEOUT'] = 300  # 5 minutes

# MIME types for static files
app.config['MIME_TYPES'] = {
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.html': 'text/html; charset=utf-8',
    '.ico': 'image/x-icon',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.eot': 'application/vnd.ms-fontobject'
}

# Security headers
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self' https:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "img-src 'self' data: https:; "
        "font-src 'self' https:; "
        "connect-src 'self' https:; "
        "media-src 'self' https:; "
        "object-src 'none';"
    )
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'microphone=self'
    
    # Add caching headers for static files
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000'
    else:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        
    return response

# Initialize extensions
db.init_app(app)

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
logger.info(f"Upload folder created at {app.config['UPLOAD_FOLDER']}")

# Error handlers
@app.errorhandler(ValidationError)
def handle_validation_error(error):
    return jsonify(error.to_dict()), 400

@app.errorhandler(APIError)
def handle_api_error(error):
    return jsonify(error.to_dict()), error.status_code

@app.errorhandler(DeepgramAPIError)
def handle_deepgram_error(error):
    return jsonify(error.to_dict()), 500

@app.errorhandler(TranscriptionError)
def handle_transcription_error(error):
    return jsonify(error.to_dict()), 500

@app.errorhandler(413)
def request_entity_too_large(error):
    error = ValidationError(
        f"File too large. Maximum size is {app.config['MAX_CONTENT_LENGTH']/1024/1024:.0f}MB",
        field='file_size'
    )
    return jsonify(error.to_dict()), 413

@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        error = APIError("Resource not found", status_code=404)
        return jsonify(error.to_dict()), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    with error_context("Database rollback"):
        db.session.rollback()
    if request.path.startswith('/api/'):
        error = APIError("Internal server error", status_code=500)
        return jsonify(error.to_dict()), 500
    return render_template('500.html'), 500

@app.errorhandler(Exception)
def unhandled_exception(error):
    logger.error(f"Unhandled exception: {str(error)}\nTraceback:\n{traceback.format_exc()}")
    if request.path.startswith('/api/'):
        error = APIError("An unexpected error occurred", status_code=500)
        return jsonify(error.to_dict()), 500
    return render_template('500.html'), 500

# Serve static files with proper MIME types and caching
@app.route('/static/<path:filename>')
@log_request_metrics()
@handle_errors()
def serve_static(filename):
    try:
        mimetype = None
        for ext, mime in app.config['MIME_TYPES'].items():
            if filename.endswith(ext):
                mimetype = mime
                break
                
        if not mimetype:
            logger.warning(f"Unknown MIME type for file: {filename}")
            mimetype = 'application/octet-stream'
            
        response = send_from_directory(app.static_folder, filename, mimetype=mimetype)
        response.headers['Cache-Control'] = 'public, max-age=31536000'
        response.headers['Vary'] = 'Accept-Encoding'
        
        return response
    except Exception as e:
        logger.error(f"Error serving static file {filename}: {str(e)}")
        raise APIError("Error serving static file", status_code=500)

# Import routes and blueprints after app initialization
from routes import *
from api import api_bp, swagger_ui_blueprint, SWAGGER_URL

# Register blueprints
app.register_blueprint(api_bp)
app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)

async def validate_deepgram():
    """Validate Deepgram API key on startup"""
    try:
        client = DeepgramTranscriptionClient()
        await client.validate_api_key()
        logger.info("Deepgram API key validation successful")
    except DeepgramAPIError as e:
        logger.error(f"Deepgram API key validation failed: {str(e)}")
        raise

# Initialize database and validate Deepgram
with app.app_context():
    try:
        with error_context("Database initialization"):
            db.create_all()
            logger.info("Database tables created successfully")
            
        # Validate Deepgram API key
        asyncio.run(validate_deepgram())
        
    except Exception as e:
        logger.error(f"Initialization error: {str(e)}")
        raise

# Start monitoring
scheduler = start_monitoring(app)

# Cleanup on shutdown
import atexit
atexit.register(lambda: scheduler.shutdown())

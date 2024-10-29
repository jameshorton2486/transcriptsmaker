from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import logging
from monitoring import setup_logging, start_monitoring, log_request_metrics
from error_handling.exceptions import TranscriptionError, ValidationError, APIError
from error_handling.handlers import handle_errors, error_context, retry_on_error, log_errors
from database import db

# Set up enhanced logging
logger, perf_logger = setup_logging()

# Initialize the app with proper static file configuration
app = Flask(__name__, 
    static_url_path='/static',
    static_folder='static'
)

# Configuration
app.config.update(
    SECRET_KEY=os.urandom(24),
    SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL"),
    SQLALCHEMY_ENGINE_OPTIONS={
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
    },
    UPLOAD_FOLDER='/tmp/uploads',
    MAX_CONTENT_LENGTH=2 * 1024 * 1024 * 1024,  # 2GB
    ALLOWED_EXTENSIONS={'wav', 'mp3', 'flac', 'mp4'},
    PROCESSING_TIMEOUT=300,  # 5 minutes
    SEND_FILE_MAX_AGE_DEFAULT=0,  # Disable caching for development
    PREFERRED_URL_SCHEME='https',  # Force HTTPS
    MIME_TYPES={
        '.js': 'application/javascript',
        '.css': 'text/css',
        '.html': 'text/html',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml'
    }
)

# Initialize extensions
CORS(app)
db.init_app(app)

# Create upload folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
logger.info(f"Upload folder created at {app.config['UPLOAD_FOLDER']}")

# Security headers
@app.after_request
def add_security_headers(response):
    response.headers.update({
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': (
            "default-src 'self' https:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: https:; "
            "font-src 'self' https:; "
            "connect-src 'self' https:; "
            "media-src 'self' https:; "
            "object-src 'none';"
        ),
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'microphone=self'
    })
    
    # Configure caching based on environment
    if app.debug:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    elif request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000'
    else:
        response.headers['Cache-Control'] = 'no-cache, must-revalidate'
    
    return response

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Resource not found', 'code': 404}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error', 'code': 500}), 500
    return render_template('500.html'), 500

# Import routes
from routes import *

from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
from flask_cors import CORS
import os
import logging
from monitoring import setup_logging, start_monitoring, log_request_metrics
from error_handling.exceptions import TranscriptionError, ValidationError, APIError
from error_handling.handlers import handle_errors, error_context, retry_on_error, log_errors
from database import db
from werkzeug.middleware.proxy_fix import ProxyFix

# Set up enhanced logging
logger, perf_logger = setup_logging()

# Initialize the app with proper static file configuration
app = Flask(__name__, 
    static_url_path='/static',
    static_folder='static',
    template_folder='templates'
)

# Handle proxy headers from Replit
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

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
    SEND_FILE_MAX_AGE_DEFAULT=31536000,  # Enable caching for static files
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=1800,
    PREFERRED_URL_SCHEME='https',
    SERVER_NAME=f"{os.environ.get('REPL_SLUG', 'legal-transcription')}.repl.co",
    APPLICATION_ROOT='/',
    MIME_TYPES={
        '.js': 'application/javascript',
        '.css': 'text/css',
        '.html': 'text/html',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.ico': 'image/x-icon'
    }
)

# Initialize extensions
CORS(app)
db.init_app(app)

# Create upload folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
logger.info(f"Upload folder created at {app.config['UPLOAD_FOLDER']}")

# Security headers and MIME type handling
@app.after_request
def add_header(response):
    response.headers.update({
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'X-XSS-Protection': '1; mode=block',
        'Content-Security-Policy': (
            "default-src 'self' https:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: https:; "
            "font-src 'self' https:; "
            "connect-src 'self' https: wss:; "
            "media-src 'self' https:; "
            "object-src 'none';"
        ),
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'microphone=self'
    })
    
    # Handle static files
    if request.path.startswith('/static/'):
        ext = os.path.splitext(request.path)[-1]
        if ext in app.config['MIME_TYPES']:
            response.mimetype = app.config['MIME_TYPES'][ext]
            response.cache_control.max_age = 31536000
            response.cache_control.public = True
            response.headers['Vary'] = 'Accept-Encoding'
            if ext in ['.css', '.js']:
                response.headers['Content-Encoding'] = 'gzip'
    
    return response

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Resource not found', 'code': 404}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    error_context = {
        'url': request.url,
        'method': request.method,
        'error': str(error),
        'stack_trace': getattr(error, '__traceback__', None)
    }
    logger.error(f"Internal server error: {error_context}")
    
    if request.path.startswith('/api/'):
        return jsonify({
            'error': 'Internal server error',
            'code': 500,
            'message': str(error) if app.debug else 'An unexpected error occurred'
        }), 500
    return render_template('500.html', error=error if app.debug else None), 500

# Import routes
from routes import *

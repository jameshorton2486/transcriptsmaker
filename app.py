from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
from flask_cors import CORS
import os
import logging
import shutil
import traceback  # Added missing import
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler  # Added TimedRotatingFileHandler
from monitoring import setup_logging, start_monitoring, log_request_metrics
from error_handling.exceptions import TranscriptionError, ValidationError, APIError
from error_handling.handlers import handle_errors, error_context, retry_on_error, log_errors
from database import db
from werkzeug.middleware.proxy_fix import ProxyFix

# Clean up old log files
def cleanup_logs():
    log_files = ['app.log', 'error.log', 'performance.log']
    for log_file in log_files:
        try:
            if os.path.exists(log_file):
                os.remove(log_file)
                print(f"Removed old log file: {log_file}")
        except Exception as e:
            print(f"Error cleaning up log file {log_file}: {str(e)}")

# Clean up logs before starting
cleanup_logs()

# Set up enhanced logging with more detailed formatting and time-based rotation
log_formatter = logging.Formatter(
    '%(asctime)s - [%(levelname)s] - %(name)s - %(module)s:%(lineno)d - %(message)s - %(pathname)s'
)

# Configure app logger with time-based rotation
app_handler = TimedRotatingFileHandler(
    'app.log',
    when='midnight',
    interval=1,
    backupCount=7,
    encoding='utf-8'
)
app_handler.setFormatter(log_formatter)
app_handler.setLevel(logging.DEBUG)

# Configure error logger with both size and time-based rotation
error_handler = TimedRotatingFileHandler(
    'error.log',
    when='midnight',
    interval=1,
    backupCount=30,
    encoding='utf-8'
)
error_handler.setFormatter(log_formatter)
error_handler.setLevel(logging.ERROR)

# Set up root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)
root_logger.addHandler(app_handler)
root_logger.addHandler(error_handler)

# Get application logger
logger = logging.getLogger(__name__)

# Initialize the app with proper static file configuration
app = Flask(__name__, 
    static_url_path='/static',
    static_folder='static',
    template_folder='templates'
)

# Handle proxy headers from Replit
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configuration with enhanced error handling
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
    APPLICATION_ROOT='/',
)

# Initialize extensions
CORS(app)

# Verify database configuration before initialization
if not app.config['SQLALCHEMY_DATABASE_URI']:
    logger.error("Database URL not configured. Please check environment variables.")
    raise ValueError("Database URL not configured")

try:
    db.init_app(app)
    logger.info("Database initialization successful")
except Exception as e:
    logger.error(f"Database initialization failed: {str(e)}\n{traceback.format_exc()}")
    raise

# Create upload folder with proper permissions
uploads_dir = app.config['UPLOAD_FOLDER']
if os.path.exists(uploads_dir):
    shutil.rmtree(uploads_dir)
os.makedirs(uploads_dir, exist_ok=True)
os.chmod(uploads_dir, 0o755)
logger.info(f"Upload folder created at {uploads_dir} with permissions 755")

# Enhanced security headers
@app.after_request
def add_header(response):
    request_info = {
        'endpoint': request.endpoint,
        'method': request.method,
        'path': request.path,
        'remote_addr': request.remote_addr,
        'user_agent': request.headers.get('User-Agent')
    }
    logger.debug(f"Processing request: {request_info}")
    
    # Add security headers with enhanced CSP
    response.headers.update({
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'X-XSS-Protection': '1; mode=block',
        'Content-Security-Policy': (
            "default-src 'self' https:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https: cdn.jsdelivr.net cdn.replit.com; "
            "style-src 'self' 'unsafe-inline' https: cdn.jsdelivr.net cdn.replit.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https: cdn.jsdelivr.net cdn.replit.com; "
            "connect-src 'self' https: wss:; "
            "media-src 'self' https:; "
            "object-src 'none';"
        ),
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'microphone=self'
    })
    
    # Only set cache headers for static files
    if request.path.startswith('/static/'):
        response.cache_control.max_age = 31536000
        response.cache_control.public = True
        response.headers['Vary'] = 'Accept-Encoding'
    
    logger.debug(f"Response headers set: {dict(response.headers)}")
    return response

# Serve static files directly with enhanced error handling
@app.route('/static/<path:filename>')
@log_errors()
def serve_static(filename):
    logger.debug(f"Serving static file: {filename}")
    try:
        return send_from_directory(app.static_folder, filename)
    except Exception as e:
        logger.error(f"Error serving static file {filename}: {str(e)}")
        raise

# Enhanced error handlers
@app.errorhandler(404)
def not_found_error(error):
    error_context = {
        'url': request.url,
        'method': request.method,
        'remote_addr': request.remote_addr,
        'user_agent': request.headers.get('User-Agent'),
        'error': str(error),
        'traceback': traceback.format_exc()
    }
    logger.error(f"404 Error: {error_context}")
    
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Resource not found', 'code': 404}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    error_context = {
        'url': request.url,
        'method': request.method,
        'remote_addr': request.remote_addr,
        'user_agent': request.headers.get('User-Agent'),
        'error': str(error),
        'traceback': traceback.format_exc()
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

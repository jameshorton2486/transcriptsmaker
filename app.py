import os
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from database import db

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_url_path='/static', static_folder='static')

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
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.html': 'text/html',
    '.ico': 'image/x-icon'
}

# Initialize extensions
db.init_app(app)

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
logger.info(f"Upload folder created at {app.config['UPLOAD_FOLDER']}")

# Serve static files with proper MIME types
@app.route('/static/<path:filename>')
def serve_static(filename):
    mimetype = None
    for ext, mime in app.config['MIME_TYPES'].items():
        if filename.endswith(ext):
            mimetype = mime
            break
    return send_from_directory(app.static_folder, filename, mimetype=mimetype)

# Import routes and blueprints after app initialization
from routes import *
from api import api_bp, swagger_ui_blueprint, SWAGGER_URL

# Register blueprints
app.register_blueprint(api_bp)
app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)

with app.app_context():
    try:
        db.create_all()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}")
        raise

# Error handlers
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        'error': 'File too large',
        'max_size': f"{app.config['MAX_CONTENT_LENGTH']/1024/1024:.0f}MB"
    }), 413, {'Content-Type': 'application/json'}

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404, {'Content-Type': 'text/html'}

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500, {'Content-Type': 'text/html'}

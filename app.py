import os
import logging
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.utils import secure_filename

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

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)

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

# Initialize extensions
db.init_app(app)

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
logger.info(f"Upload folder created at {app.config['UPLOAD_FOLDER']}")

# Import routes after app initialization
from routes import *

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
    return jsonify({'error': 'Resource not found'}), 404, {'Content-Type': 'application/json'}

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500, {'Content-Type': 'application/json'}

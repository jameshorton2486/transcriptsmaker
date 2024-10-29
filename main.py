import os
import sys
import logging
import signal
from logging.handlers import RotatingFileHandler
from app import app
from audio_processor.processor import AudioProcessor
import atexit

# Version info
VERSION = "1.0.0"

# Configure logging with rotation
def setup_logging():
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s'
    )
    
    # Main application log with rotation
    app_handler = RotatingFileHandler(
        'app.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    app_handler.setFormatter(log_formatter)
    app_handler.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add handlers
    root_logger.addHandler(app_handler)
    root_logger.addHandler(console_handler)
    
    return root_logger

# Signal handlers for graceful shutdown
def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
    sys.exit(0)

def cleanup():
    logger.info("Performing cleanup before shutdown...")
    # Add any cleanup tasks here

if __name__ == "__main__":
    # Setup logging
    logger = setup_logging()
    
    # Print startup banner
    logger.info("=" * 60)
    logger.info(f"Legal Transcription System v{VERSION}")
    logger.info("=" * 60)
    
    # Log configuration details (excluding sensitive data)
    config_info = {
        'ENVIRONMENT': os.environ.get('FLASK_ENV', 'production'),
        'DEBUG_MODE': os.environ.get('FLASK_DEBUG', 'False').lower() == 'true',
        'UPLOAD_FOLDER': app.config['UPLOAD_FOLDER'],
        'MAX_CONTENT_LENGTH': f"{app.config['MAX_CONTENT_LENGTH'] / (1024*1024*1024):.1f}GB",
        'ALLOWED_EXTENSIONS': list(app.config['ALLOWED_EXTENSIONS']),
        'PROCESSING_TIMEOUT': f"{app.config['PROCESSING_TIMEOUT']}s"
    }
    logger.info("Configuration:")
    for key, value in config_info.items():
        logger.info(f"  {key}: {value}")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Register cleanup handler
    atexit.register(cleanup)
    
    # Determine debug mode from environment with secure default
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    if debug_mode:
        logger.warning("Running in DEBUG mode. This is not recommended for production!")
        logger.warning("Please set FLASK_DEBUG=False in production environments.")
    
    # Development server warning
    logger.warning("This is a development server. Do not use it in a production deployment.")
    logger.warning("Use a production WSGI server instead.")
    
    try:
        # Start the application
        logger.info("Starting Legal Transcription System...")
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=debug_mode,
            use_reloader=debug_mode
        )
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        sys.exit(1)

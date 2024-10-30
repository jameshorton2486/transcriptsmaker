import os
import sys
import logging
from app import app, logger
import atexit
import signal
import shutil
import traceback

# Version info
VERSION = "1.0.0"

def cleanup(signum=None, frame=None):
    """Cleanup function to handle graceful shutdown"""
    logger.info("Performing cleanup before shutdown...")
    try:
        # Clean up any temporary files or symlinks
        tmp_dir = '/tmp/uploads'
        if os.path.exists(tmp_dir):
            for filename in os.listdir(tmp_dir):
                file_path = os.path.join(tmp_dir, filename)
                try:
                    if os.path.islink(file_path):
                        os.unlink(file_path)
                        logger.debug(f"Removed symlink: {file_path}")
                    elif os.path.isfile(file_path):
                        os.remove(file_path)
                        logger.debug(f"Removed file: {file_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up {file_path}: {str(e)}\n{traceback.format_exc()}")
            
            # Clean directory itself
            try:
                shutil.rmtree(tmp_dir)
                logger.info("Removed upload directory")
            except Exception as e:
                logger.error(f"Error removing upload directory: {str(e)}\n{traceback.format_exc()}")
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}\n{traceback.format_exc()}")
    finally:
        # Ensure we exit
        if signum is not None:
            sys.exit(0)

if __name__ == "__main__":
    try:
        # Print startup banner
        logger.info("=" * 60)
        logger.info(f"Legal Transcription System v{VERSION}")
        logger.info("=" * 60)

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, cleanup)
        signal.signal(signal.SIGINT, cleanup)
        atexit.register(cleanup)

        # Get port from environment with Replit compatibility
        port = int(os.environ.get('PORT', '5000'))
        
        # Create uploads directory with proper permissions
        uploads_dir = '/tmp/uploads'
        if os.path.exists(uploads_dir):
            shutil.rmtree(uploads_dir)  # Clean existing directory
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Set proper permissions for uploads directory
        try:
            os.chmod(uploads_dir, 0o755)
            logger.info(f"Set permissions 755 for uploads directory: {uploads_dir}")
        except Exception as e:
            logger.warning(f"Could not set permissions for uploads directory: {str(e)}")
        
        # Create static symlinks if needed
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        if not os.path.exists(static_dir):
            os.makedirs(static_dir, exist_ok=True)
            logger.info(f"Created static directory: {static_dir}")
        
        # Log configuration
        config_info = {
            'ENVIRONMENT': os.environ.get('FLASK_ENV', 'production'),
            'DEBUG_MODE': os.environ.get('FLASK_DEBUG', 'False').lower() == 'true',
            'SERVER_PORT': port,
            'UPLOADS_DIR': uploads_dir,
            'STATIC_DIR': static_dir
        }
        for key, value in config_info.items():
            logger.info(f"  {key}: {value}")

        # Start the application
        logger.info("Starting Legal Transcription System...")
        app.run(
            host="0.0.0.0",
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True
        )
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}\n{traceback.format_exc()}")
        sys.exit(1)

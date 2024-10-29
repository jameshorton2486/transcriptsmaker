import os
import sys
import logging
from app import app, logger
import atexit
import signal

# Version info
VERSION = "1.0.0"

def cleanup(signum=None, frame=None):
    """Cleanup function to handle graceful shutdown"""
    logger.info("Performing cleanup before shutdown...")
    try:
        # Add cleanup tasks here
        pass
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
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

        # Log configuration
        config_info = {
            'ENVIRONMENT': os.environ.get('FLASK_ENV', 'production'),
            'DEBUG_MODE': os.environ.get('FLASK_DEBUG', 'False').lower() == 'true',
            'SERVER_PORT': 5000  # Using port 5000 for Replit compatibility
        }
        for key, value in config_info.items():
            logger.info(f"  {key}: {value}")

        # Start the application
        logger.info("Starting Legal Transcription System...")
        app.run(
            host="0.0.0.0",  # Listen on all interfaces
            port=5000,  # Using port 5000 for Replit compatibility
            debug=False,  # Keep debug mode disabled for production
            use_reloader=False  # Prevent duplicate processes
        )
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        sys.exit(1)

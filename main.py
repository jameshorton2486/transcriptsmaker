from app import app
from audio_processor.processor import AudioProcessor
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting Legal Transcription System")
    app.run(host="0.0.0.0", port=5000)

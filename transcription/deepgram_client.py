import os
import logging
import asyncio
import mimetypes
from typing import Optional, Dict, Any, List
from datetime import datetime
from deepgram import DeepgramClient, PrerecordedOptions
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import time

logger = logging.getLogger(__name__)

class DeepgramError(Exception):
    """Custom exception class for Deepgram-related errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'message': str(self),
            'status_code': self.status_code,
            'timestamp': self.timestamp.isoformat(),
            'response_data': self.response_data
        }

class DeepgramValidationError(DeepgramError):
    """Raised when file validation fails"""
    pass

class DeepgramTranscriptionClient:
    # Maximum file size (100MB)
    MAX_FILE_SIZE = 100 * 1024 * 1024
    
    # Supported MIME types and their extensions
    SUPPORTED_FORMATS = {
        'audio/wav': ['.wav'],
        'audio/x-wav': ['.wav'],
        'audio/mpeg': ['.mp3'],
        'audio/mp3': ['.mp3'],
        'audio/flac': ['.flac'],
        'audio/x-flac': ['.flac'],
        'video/mp4': ['.mp4'],
        'audio/mp4': ['.mp4']
    }
    
    def __init__(self):
        """Initialize the Deepgram client with API key from environment"""
        self.api_key = os.environ.get('DEEPGRAM_API_KEY')
        if not self.api_key:
            raise DeepgramError("Deepgram API key not found in environment variables")
            
        self.client = DeepgramClient(self.api_key)
        logger.info("Deepgram client initialized")

    def _validate_file(self, file_path: str) -> None:
        """
        Validate file existence, size, and format
        
        Args:
            file_path: Path to the audio file
            
        Raises:
            DeepgramValidationError: If validation fails
        """
        start_time = time.time()
        try:
            if not os.path.exists(file_path):
                raise DeepgramValidationError(f"File not found: {file_path}")

            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > self.MAX_FILE_SIZE:
                raise DeepgramValidationError(
                    f"File size ({file_size} bytes) exceeds maximum allowed size ({self.MAX_FILE_SIZE} bytes)"
                )

            # Check MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                raise DeepgramValidationError("Could not determine file type")

            file_ext = os.path.splitext(file_path)[1].lower()
            if mime_type not in self.SUPPORTED_FORMATS or \
               file_ext not in self.SUPPORTED_FORMATS[mime_type]:
                raise DeepgramValidationError(f"Unsupported file format: {mime_type}")

            logger.debug(f"File validation successful: {file_path} ({mime_type}, {file_size} bytes)")
        finally:
            duration = time.time() - start_time
            logger.info(f"File validation completed in {duration:.2f}s")

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        before_sleep=lambda retry_state: logger.warning(
            f"Retry attempt {retry_state.attempt_number} after {retry_state.outcome.exception()}"
        )
    )
    async def transcribe_file(self, file_path: str) -> Dict[str, Any]:
        """
        Transcribe an audio file using Deepgram's API with retry logic
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Dict containing transcription results
            
        Raises:
            DeepgramError: If transcription fails
        """
        start_time = time.time()
        metrics = {
            'file_path': file_path,
            'start_time': datetime.utcnow().isoformat()
        }

        try:
            # Validate file before processing
            self._validate_file(file_path)

            # Configure transcription options
            options = PrerecordedOptions(
                smart_format=True,
                punctuate=True,
                diarize=True,
                utterances=True,
                model="nova-2",
                language="en-US"
            )

            logger.info(f"Starting transcription for file: {file_path}")
            
            # Determine file mimetype
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = 'audio/wav'  # Default to wav if unable to determine

            with open(file_path, 'rb') as audio:
                response = await self.client.listen.prerecorded.v("1").transcribe_file(audio, options)

            # Process response
            if not response or not isinstance(response, dict) or 'results' not in response:
                raise DeepgramError("Invalid response format from Deepgram")

            try:
                results = response['results']
                if not results.get('channels'):
                    raise DeepgramError("No channels found in transcription results")

                channel = results['channels'][0]
                if not channel.get('alternatives'):
                    raise DeepgramError("No alternatives found in transcription results")

                transcript = channel['alternatives'][0]
            except (KeyError, IndexError) as e:
                raise DeepgramError(f"Invalid response structure: {str(e)}")

            # Log success metrics
            duration = time.time() - start_time
            metrics.update({
                'duration': duration,
                'success': True,
                'transcript_length': len(transcript.get('transcript', '')),
                'confidence': transcript.get('confidence', 0)
            })
            logger.info(f"Transcription metrics: {metrics}")

            return {
                'text': transcript.get('transcript', ''),
                'confidence': transcript.get('confidence', 0),
                'words': transcript.get('words', []),
                'speakers': self._extract_speakers(channel)
            }

        except Exception as e:
            # Log error metrics
            duration = time.time() - start_time
            metrics.update({
                'duration': duration,
                'success': False,
                'error': str(e),
                'error_type': e.__class__.__name__
            })
            logger.error(f"Transcription failed: {metrics}")

            if isinstance(e, DeepgramError):
                raise
            raise DeepgramError(f"Transcription error: {str(e)}")

        finally:
            # Cleanup
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"Cleaned up temporary file: {file_path}")
            except Exception as e:
                logger.error(f"Error cleaning up file {file_path}: {str(e)}")

    def _extract_speakers(self, channel_data: Dict) -> List[Dict[str, Any]]:
        """Extract speaker information from channel data"""
        speakers = []
        alternatives = channel_data.get('alternatives', [])
        if not alternatives:
            return speakers

        words = alternatives[0].get('words', [])
        current_speaker = None
        start_time = None
        current_text = []

        for word in words:
            speaker = word.get('speaker')
            if speaker != current_speaker:
                if current_speaker is not None:
                    speakers.append({
                        'speaker_id': str(current_speaker),
                        'start_time': start_time,
                        'end_time': word.get('start', 0),
                        'text': ' '.join(current_text)
                    })
                current_speaker = speaker
                start_time = word.get('start', 0)
                current_text = []
            current_text.append(word.get('word', ''))

        # Add the last speaker segment
        if current_speaker is not None and current_text:
            speakers.append({
                'speaker_id': str(current_speaker),
                'start_time': start_time,
                'end_time': words[-1].get('end', 0) if words else 0,
                'text': ' '.join(current_text)
            })

        return speakers

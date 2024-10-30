import os
import logging
import aiohttp
import json
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class DeepgramError(Exception):
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

class DeepgramTranscriptionClient:
    BASE_URL = "https://api.deepgram.com/v1"
    
    def __init__(self):
        self.api_key = os.environ.get('DEEPGRAM_API_KEY')
        if not self.api_key:
            raise DeepgramError("Deepgram API key not found in environment variables")
            
        self.headers = {
            'Authorization': f'Token {self.api_key}',
            'Content-Type': 'application/json'
        }
        logger.info("Deepgram client initialized")

    def _validate_response(self, status_code: int, response_data: Dict) -> None:
        """Validate API response and raise appropriate errors"""
        if status_code == 404:
            logger.error(f"Deepgram API endpoint not found: {response_data}")
            raise DeepgramError("API endpoint not found", status_code, response_data)
        elif status_code == 401:
            logger.error("Invalid Deepgram API key")
            raise DeepgramError("Invalid API key", status_code, response_data)
        elif status_code == 429:
            logger.error("Rate limit exceeded")
            raise DeepgramError("Rate limit exceeded", status_code, response_data)
        elif status_code >= 400:
            logger.error(f"Deepgram API error: {response_data}")
            raise DeepgramError(f"API error: {response_data.get('error', 'Unknown error')}", 
                              status_code, response_data)

    async def transcribe_file(self, file_path: str) -> Dict[str, Any]:
        """Transcribe an audio file using Deepgram's API"""
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            raise DeepgramError(f"File not found: {file_path}")

        endpoint = f"{self.BASE_URL}/listen"
        
        try:
            logger.info(f"Starting transcription for file: {file_path}")
            async with aiohttp.ClientSession() as session:
                # Log request details (excluding sensitive info)
                logger.debug(f"Sending request to: {endpoint}")
                logger.debug(f"Request headers: {json.dumps({k: v for k, v in self.headers.items() if k != 'Authorization'})}")

                form_data = aiohttp.FormData()
                form_data.add_field('file', 
                                  open(file_path, 'rb'),
                                  filename=os.path.basename(file_path))

                async with session.post(endpoint, 
                                     data=form_data,
                                     headers={'Authorization': self.headers['Authorization']}) as response:
                    
                    # Log response status
                    logger.debug(f"Response status: {response.status}")
                    response_data = await response.json()

                    # Validate response
                    self._validate_response(response.status, response_data)

                    if response.status == 200:
                        # Process successful response
                        results = response_data.get('results', {})
                        channels = results.get('channels', [])
                        
                        if not channels:
                            logger.warning("No transcription results found in response")
                            return {'error': 'No transcription results found'}

                        # Extract transcription from first channel
                        alternatives = channels[0].get('alternatives', [])
                        if not alternatives:
                            logger.warning("No alternatives found in transcription")
                            return {'error': 'No transcription alternatives found'}

                        transcript = alternatives[0]
                        
                        logger.info(f"Transcription completed successfully for {file_path}")
                        return {
                            'text': transcript.get('transcript', ''),
                            'confidence': transcript.get('confidence', 0.0),
                            'words': transcript.get('words', [])
                        }

                    logger.error(f"Unexpected response: {response_data}")
                    raise DeepgramError("Unexpected API response", 
                                      response.status, response_data)

        except aiohttp.ClientError as e:
            logger.error(f"Network error during transcription: {str(e)}")
            raise DeepgramError(f"Network error: {str(e)}")
        except Exception as e:
            logger.error(f"Error during transcription: {str(e)}")
            raise DeepgramError(f"Transcription error: {str(e)}")

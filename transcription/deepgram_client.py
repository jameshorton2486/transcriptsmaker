from deepgram import Deepgram
import os
import asyncio
import json
from models import Transcription, Speaker, NoiseProfile
from app import db
import logging
from error_handling.exceptions import TranscriptionError, APIError

logger = logging.getLogger(__name__)

class DeepgramAPIError(TranscriptionError):
    """Custom exception for Deepgram API related errors"""
    def __init__(self, message: str, error_code: str = None):
        super().__init__(message, error_code or 'DEEPGRAM_API_ERROR')

class DeepgramTranscriptionClient:
    def __init__(self):
        self.api_key = os.environ.get("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise DeepgramAPIError("Deepgram API key not found in environment", "MISSING_API_KEY")
        
        try:
            self.dg_client = Deepgram(self.api_key)
        except Exception as e:
            raise DeepgramAPIError(f"Failed to initialize Deepgram client: {str(e)}", "INIT_ERROR")
    
    async def validate_api_key(self):
        """Validate the Deepgram API key by making a test request"""
        try:
            # Create a minimal audio sample for testing
            test_audio = b'\x00' * 44100  # 1 second of silence
            source = {'buffer': test_audio, 'mimetype': 'audio/wav'}
            await self.dg_client.transcription.prerecorded(source, {'smart_format': True})
            logger.info("Deepgram API key validation successful")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if 'unauthorized' in error_msg or 'invalid api key' in error_msg:
                raise DeepgramAPIError("Invalid Deepgram API key", "INVALID_API_KEY")
            elif 'network' in error_msg or 'connection' in error_msg:
                raise DeepgramAPIError("Network error while validating API key", "NETWORK_ERROR")
            else:
                raise DeepgramAPIError(f"Error validating API key: {str(e)}", "VALIDATION_ERROR")
            
    async def transcribe_file(self, audio_file_path):
        """Transcribe audio file with speaker diarization and noise classification"""
        try:
            with open(audio_file_path, 'rb') as audio:
                source = {'buffer': audio, 'mimetype': 'audio/wav'}
                options = {
                    'smart_format': True,
                    'diarize': True,
                    'utterances': True,
                    'punctuate': True,
                    'noise_reduction': True,
                    'detect_topics': True,
                    'language': 'en-US'
                }
                
                try:
                    response = await self.dg_client.transcription.prerecorded(source, options)
                    return self._process_response(response)
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'unauthorized' in error_msg:
                        raise DeepgramAPIError("Invalid API key or unauthorized access", "AUTH_ERROR")
                    elif 'format' in error_msg:
                        raise DeepgramAPIError("Invalid audio format or corrupted file", "FORMAT_ERROR")
                    elif 'network' in error_msg or 'connection' in error_msg:
                        raise DeepgramAPIError("Network error during transcription", "NETWORK_ERROR")
                    else:
                        raise DeepgramAPIError(f"Transcription error: {str(e)}", "PROCESSING_ERROR")
                        
        except FileNotFoundError:
            raise DeepgramAPIError(f"Audio file not found: {audio_file_path}", "FILE_NOT_FOUND")
        except Exception as e:
            if not isinstance(e, DeepgramAPIError):
                raise DeepgramAPIError(f"Error processing audio file: {str(e)}", "PROCESSING_ERROR")
            raise
            
    def _process_response(self, response):
        """Process Deepgram response and extract relevant information"""
        try:
            results = response['results']
            transcript_data = {
                'text': results['channels'][0]['alternatives'][0]['transcript'],
                'confidence': results['channels'][0]['alternatives'][0]['confidence'],
                'words': results['channels'][0]['alternatives'][0]['words'],
                'speakers': []
            }
            
            # Process speaker diarization
            current_speaker = None
            current_text = []
            
            for word in transcript_data['words']:
                if 'speaker' in word:
                    if current_speaker != word['speaker']:
                        if current_speaker is not None:
                            transcript_data['speakers'].append({
                                'speaker_id': f"speaker_{current_speaker}",
                                'text': ' '.join(current_text),
                                'start_time': start_time,
                                'end_time': word['end']
                            })
                        current_speaker = word['speaker']
                        current_text = [word['word']]
                        start_time = word['start']
                    else:
                        current_text.append(word['word'])
                        
            # Add the last speaker segment
            if current_speaker is not None and current_text:
                transcript_data['speakers'].append({
                    'speaker_id': f"speaker_{current_speaker}",
                    'text': ' '.join(current_text),
                    'start_time': start_time,
                    'end_time': transcript_data['words'][-1]['end']
                })
                
            return transcript_data
            
        except KeyError as e:
            raise DeepgramAPIError(f"Invalid response format: {str(e)}", "RESPONSE_ERROR")
        except Exception as e:
            raise DeepgramAPIError(f"Error processing response: {str(e)}", "PROCESSING_ERROR")
        
    async def start_streaming(self, websocket):
        """Handle real-time streaming transcription"""
        try:
            options = {
                'punctuate': True,
                'diarize': True,
                'smart_format': True,
                'language': 'en-US'
            }
            
            try:
                stream = await self.dg_client.transcription.live(options)
                return stream
            except Exception as e:
                error_msg = str(e).lower()
                if 'unauthorized' in error_msg:
                    raise DeepgramAPIError("Invalid API key for streaming", "STREAM_AUTH_ERROR")
                elif 'network' in error_msg or 'connection' in error_msg:
                    raise DeepgramAPIError("Network error starting stream", "STREAM_NETWORK_ERROR")
                else:
                    raise DeepgramAPIError(f"Error starting live transcription: {str(e)}", "STREAM_ERROR")
                    
        except Exception as e:
            if not isinstance(e, DeepgramAPIError):
                raise DeepgramAPIError(f"Error initializing stream: {str(e)}", "STREAM_INIT_ERROR")
            raise

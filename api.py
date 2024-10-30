from flask import Blueprint, request, jsonify, make_response
from flask_restful import Api, Resource
from models import db, Transcription, Speaker, CustomVocabulary, NoiseProfile
from transcription.deepgram_client import DeepgramTranscriptionClient
from audio_processor.processor import AudioProcessor
from audio_processor.exceptions import AudioProcessingError
from werkzeug.utils import secure_filename
import os
import asyncio
import logging
import mimetypes
from functools import wraps
import time
from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from flask_swagger_ui import get_swaggerui_blueprint

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Blueprint
api_bp = Blueprint('api', __name__)
api = Api(api_bp)

# Setup Swagger documentation
SWAGGER_URL = '/api/docs'
API_URL = '/api/swagger.json'

swagger_ui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Legal Transcription API"
    }
)

def validate_audio_file(file):
    """Validate audio file format and content type"""
    if not file:
        raise ValueError("No file provided")
        
    filename = secure_filename(file.filename)
    extension = os.path.splitext(filename)[1].lower()
    
    # Validate file extension
    if extension not in {'.wav', '.mp3', '.flac', '.mp4'}:
        raise ValueError(f"Unsupported file format: {extension}")
    
    # Validate content type
    content_type = file.content_type
    valid_types = {
        '.wav': {'audio/wav', 'audio/x-wav', 'audio/wave'},
        '.mp3': {'audio/mpeg', 'audio/mp3'},
        '.flac': {'audio/flac', 'audio/x-flac'},
        '.mp4': {'audio/mp4', 'video/mp4'}
    }
    
    if content_type not in valid_types.get(extension, set()):
        raise ValueError(f"Invalid content type for {extension}: {content_type}")
    
    return filename

class TranscriptionAPI(Resource):
    @require_api_key
    def post(self):
        """Submit audio file for transcription"""
        try:
            if 'audio' not in request.files:
                return {'error': 'No audio file provided'}, 400

            file = request.files['audio']
            if not file.filename:
                return {'error': 'No selected file'}, 400

            try:
                filename = validate_audio_file(file)
            except ValueError as e:
                return {'error': str(e)}, 400

            file_path = os.path.join('/tmp/uploads', filename)
            file.save(file_path)

            transcription = Transcription(
                filename=filename,
                status='processing'
            )
            db.session.add(transcription)
            db.session.commit()

            # Process in background
            asyncio.create_task(self._process_transcription(transcription.id, file_path))

            return {
                'id': transcription.id,
                'status': 'processing',
                'message': 'Transcription job created successfully'
            }, 202

        except Exception as e:
            logger.error(f"Error creating transcription: {str(e)}")
            return {'error': str(e)}, 500

    async def _process_transcription(self, transcription_id, file_path):
        try:
            transcription_client = DeepgramTranscriptionClient()
            processor = AudioProcessor(file_path)
            
            # Process audio with enhanced error handling
            try:
                enhanced_audio, sample_rate, noise_type = await processor.process_audio()
                enhanced_path = os.path.join('/tmp/uploads', f'enhanced_{os.path.basename(file_path)}')
                await asyncio.to_thread(processor.save_enhanced_audio, enhanced_audio, sample_rate, enhanced_path)
            except AudioProcessingError as e:
                logger.error(f"Audio processing error: {str(e)}")
                raise

            # Transcribe with proper error handling
            try:
                result = await transcription_client.transcribe_file(enhanced_path)
                if not result or 'error' in result:
                    raise ValueError(f"Transcription failed: {result.get('error', 'Unknown error')}")
            except Exception as e:
                logger.error(f"Transcription error: {str(e)}")
                raise

            # Update transcription record
            transcription = Transcription.query.get(transcription_id)
            transcription.text = result.get('text', '')
            transcription.confidence_score = result.get('confidence', 0.0)
            transcription.status = 'completed'

            # Process speakers with validation
            speakers_data = result.get('speakers', [])
            for speaker_data in speakers_data:
                if not all(k in speaker_data for k in ['speaker_id', 'start_time', 'end_time', 'text']):
                    logger.warning(f"Invalid speaker data: {speaker_data}")
                    continue
                
                speaker = Speaker(
                    transcription_id=transcription_id,
                    speaker_id=speaker_data['speaker_id'],
                    start_time=speaker_data['start_time'],
                    end_time=speaker_data['end_time'],
                    text=speaker_data['text']
                )
                db.session.add(speaker)

            # Add noise profile
            noise_profile = NoiseProfile(
                transcription_id=transcription_id,
                type=noise_type,
                confidence=0.85,
                start_time=0.0,
                end_time=float(len(enhanced_audio)) / sample_rate
            )
            db.session.add(noise_profile)
            
            db.session.commit()
            logger.info(f"Successfully processed transcription {transcription_id}")

        except Exception as e:
            logger.error(f"Error processing transcription {transcription_id}: {str(e)}")
            transcription = Transcription.query.get(transcription_id)
            transcription.status = 'failed'
            transcription.text = str(e)
            db.session.commit()
        finally:
            # Cleanup
            for path in [file_path, enhanced_path]:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception as e:
                    logger.error(f"Error cleaning up file {path}: {str(e)}")

# Rest of the API classes remain the same...

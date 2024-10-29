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

# API documentation
spec = APISpec(
    title="Legal Transcription API",
    version="1.0.0",
    openapi_version="3.0.2",
    plugins=[MarshmallowPlugin()],
)

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return {'error': 'No API key provided'}, 401
        # TODO: Implement API key validation against database
        return f(*args, **kwargs)
    return decorated

class TranscriptionAPI(Resource):
    @require_api_key
    def post(self):
        """Submit audio file for transcription"""
        if 'audio' not in request.files:
            return {'error': 'No audio file provided'}, 400

        file = request.files['audio']
        if not file.filename:
            return {'error': 'No selected file'}, 400

        try:
            filename = secure_filename(file.filename)
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
            
            enhanced_audio, sample_rate, noise_type = await processor.process_audio()
            enhanced_path = os.path.join('/tmp/uploads', f'enhanced_{os.path.basename(file_path)}')
            await asyncio.to_thread(processor.save_enhanced_audio, enhanced_audio, sample_rate, enhanced_path)
            
            result = await transcription_client.transcribe_file(enhanced_path)
            
            transcription = Transcription.query.get(transcription_id)
            transcription.text = result['text']
            transcription.confidence_score = result['confidence']
            transcription.status = 'completed'
            
            for speaker_data in result['speakers']:
                speaker = Speaker(
                    transcription_id=transcription_id,
                    speaker_id=speaker_data['speaker_id'],
                    start_time=speaker_data['start_time'],
                    end_time=speaker_data['end_time'],
                    text=speaker_data['text']
                )
                db.session.add(speaker)
            
            noise_profile = NoiseProfile(
                transcription_id=transcription_id,
                type=noise_type,
                confidence=0.85,
                start_time=0.0,
                end_time=float(len(enhanced_audio)) / sample_rate
            )
            db.session.add(noise_profile)
            
            db.session.commit()
            
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

class TranscriptionStatusAPI(Resource):
    @require_api_key
    def get(self, transcription_id):
        """Get transcription status"""
        transcription = Transcription.query.get_or_404(transcription_id)
        return {
            'id': transcription.id,
            'status': transcription.status,
            'created_at': transcription.created_at.isoformat()
        }

class TranscriptionResultAPI(Resource):
    @require_api_key
    def get(self, transcription_id):
        """Get transcription result"""
        transcription = Transcription.query.get_or_404(transcription_id)
        
        if transcription.status != 'completed':
            return {
                'id': transcription.id,
                'status': transcription.status,
                'message': 'Transcription not completed yet'
            }, 404
            
        speakers = [{
            'id': speaker.speaker_id,
            'text': speaker.text,
            'start_time': speaker.start_time,
            'end_time': speaker.end_time
        } for speaker in transcription.speakers]
        
        noise_profiles = NoiseProfile.query.filter_by(transcription_id=transcription_id).all()
        noise_data = [{
            'type': profile.type,
            'confidence': profile.confidence,
            'start_time': profile.start_time,
            'end_time': profile.end_time
        } for profile in noise_profiles]
        
        return {
            'id': transcription.id,
            'text': transcription.text,
            'confidence': transcription.confidence_score,
            'speakers': speakers,
            'noise_profiles': noise_data,
            'created_at': transcription.created_at.isoformat()
        }

class VocabularyAPI(Resource):
    @require_api_key
    def post(self):
        """Add custom vocabulary terms"""
        data = request.get_json()
        if not data or 'terms' not in data:
            return {'error': 'No terms provided'}, 400
            
        try:
            added_terms = []
            for term_data in data['terms']:
                term = CustomVocabulary(
                    term=term_data['term'],
                    pronunciation=term_data.get('pronunciation')
                )
                db.session.add(term)
                added_terms.append(term_data['term'])
                
            db.session.commit()
            return {
                'message': 'Terms added successfully',
                'terms': added_terms
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': str(e)}, 500

    @require_api_key
    def get(self):
        """Get all custom vocabulary terms"""
        terms = CustomVocabulary.query.all()
        return {
            'terms': [{
                'term': term.term,
                'pronunciation': term.pronunciation,
                'created_at': term.created_at.isoformat()
            } for term in terms]
        }

# Register resources
api.add_resource(TranscriptionAPI, '/api/transcribe')
api.add_resource(TranscriptionStatusAPI, '/api/transcribe/<int:transcription_id>/status')
api.add_resource(TranscriptionResultAPI, '/api/transcribe/<int:transcription_id>')
api.add_resource(VocabularyAPI, '/api/vocabulary')

@api_bp.route('/api/swagger.json')
def create_swagger_spec():
    return jsonify({
        "openapi": "3.0.2",
        "info": {
            "title": "Legal Transcription API",
            "version": "1.0.0"
        },
        "paths": {
            "/api/transcribe": {
                "post": {
                    "summary": "Submit audio file for transcription",
                    "security": [{"ApiKeyAuth": []}],
                    "requestBody": {
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "audio": {
                                            "type": "string",
                                            "format": "binary"
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "202": {
                            "description": "Transcription job created"
                        }
                    }
                }
            },
            "/api/transcribe/{transcription_id}/status": {
                "get": {
                    "summary": "Get transcription status",
                    "security": [{"ApiKeyAuth": []}],
                    "parameters": [
                        {
                            "name": "transcription_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Transcription status"
                        }
                    }
                }
            }
        },
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key"
                }
            }
        }
    })

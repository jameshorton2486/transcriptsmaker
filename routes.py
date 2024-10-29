import os
import logging
from flask import render_template, request, jsonify, make_response
from app import app, db
from models import Transcription, Speaker, NoiseProfile
from werkzeug.utils import secure_filename
from transcription.deepgram_client import DeepgramTranscriptionClient
from audio_processor.processor import AudioProcessor
import asyncio
from functools import wraps
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Deepgram client
transcription_client = DeepgramTranscriptionClient()

# Constants
MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac', 'mp4'}
PROCESSING_TIMEOUT = 300  # 5 minutes

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def with_error_handling(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        start_time = time.time()
        temp_files = []
        
        try:
            return await asyncio.wait_for(
                f(*args, **kwargs),
                timeout=PROCESSING_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error(f"Operation timed out after {PROCESSING_TIMEOUT} seconds")
            return make_response(
                jsonify({'error': 'Operation timed out'}),
                408,
                {'Content-Type': 'application/json'}
            )
        except Exception as e:
            logger.error(f"Error in {f.__name__}: {str(e)}")
            status_code = 500
            if isinstance(e, ValueError):
                status_code = 400
            elif isinstance(e, FileNotFoundError):
                status_code = 404
            
            return make_response(
                jsonify({'error': str(e)}),
                status_code,
                {'Content-Type': 'application/json'}
            )
        finally:
            # Clean up any temporary files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.info(f"Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    logger.error(f"Error cleaning up file {temp_file}: {str(e)}")
            
            # Log processing time
            logger.info(f"Operation completed in {time.time() - start_time:.2f} seconds")
    return decorated_function

@app.route('/')
def index():
    return render_template('transcribe.html')

@app.route('/api/transcribe', methods=['POST'])
@with_error_handling
async def transcribe():
    # Validate request
    if 'audio' not in request.files:
        raise ValueError('No audio file provided')
    
    audio_file = request.files['audio']
    if audio_file.filename == '':
        raise ValueError('No selected file')
    
    if not allowed_file(audio_file.filename):
        raise ValueError('Invalid file format')
    
    # Check file size
    if request.content_length > MAX_CONTENT_LENGTH:
        raise ValueError(f'File too large. Maximum size is {MAX_CONTENT_LENGTH/1024/1024:.0f}MB')
    
    filename = secure_filename(audio_file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    enhanced_path = os.path.join(app.config['UPLOAD_FOLDER'], f'enhanced_{filename}')
    
    logger.info(f"Processing file: {filename}")
    
    try:
        # Create transcription record
        transcription = Transcription(filename=filename, status='processing')
        db.session.add(transcription)
        db.session.commit()
        
        # Save file
        audio_file.save(file_path)
        logger.info(f"File saved: {file_path}")
        
        # Process and enhance audio
        processor = AudioProcessor(file_path)
        enhanced_audio, sample_rate, noise_type = await asyncio.to_thread(
            processor.process_audio
        )
        logger.info("Audio enhancement completed")
        
        # Save enhanced audio
        await asyncio.to_thread(
            processor.save_enhanced_audio,
            enhanced_audio,
            sample_rate,
            enhanced_path
        )
        
        # Process the enhanced audio file
        result = await transcription_client.transcribe_file(enhanced_path)
        logger.info("Transcription completed")
        
        # Update transcription record
        transcription.text = result['text']
        transcription.confidence_score = result['confidence']
        transcription.status = 'completed'
        
        # Add speaker information
        for speaker_data in result['speakers']:
            speaker = Speaker(
                transcription_id=transcription.id,
                speaker_id=speaker_data['speaker_id'],
                start_time=speaker_data['start_time'],
                end_time=speaker_data['end_time'],
                text=speaker_data['text']
            )
            db.session.add(speaker)
            
        # Add noise profile
        noise_profile = NoiseProfile(
            transcription_id=transcription.id,
            type=noise_type,
            confidence=0.85,
            start_time=0.0,
            end_time=float(len(enhanced_audio)) / sample_rate
        )
        db.session.add(noise_profile)
        
        db.session.commit()
        logger.info(f"Database records updated for transcription ID: {transcription.id}")
        
        response_data = {
            'id': transcription.id,
            'text': result['text'],
            'confidence': result['confidence'],
            'speakers': result['speakers'],
            'noise_profile': {
                'type': noise_type,
                'confidence': 0.85
            }
        }
        
        return make_response(
            jsonify(response_data),
            200,
            {'Content-Type': 'application/json'}
        )
        
    except Exception as e:
        logger.error(f"Error processing file {filename}: {str(e)}")
        db.session.rollback()
        raise
    finally:
        # Clean up temporary files
        for path in [file_path, enhanced_path]:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.info(f"Cleaned up file: {path}")
            except Exception as e:
                logger.error(f"Error cleaning up file {path}: {str(e)}")

@app.route('/api/transcriptions/<int:transcription_id>')
@with_error_handling
async def get_transcription(transcription_id):
    transcription = Transcription.query.get_or_404(transcription_id)
    
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
    
    response_data = {
        'id': transcription.id,
        'text': transcription.text,
        'confidence': transcription.confidence_score,
        'status': transcription.status,
        'speakers': speakers,
        'noise_profiles': noise_data
    }
    
    return make_response(
        jsonify(response_data),
        200,
        {'Content-Type': 'application/json'}
    )

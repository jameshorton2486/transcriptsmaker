import os
from flask import render_template, request, jsonify
from app import app, db
from models import Transcription, Speaker, NoiseProfile
from werkzeug.utils import secure_filename
from transcription.deepgram_client import DeepgramTranscriptionClient
from audio_processor.processor import AudioProcessor
import asyncio

# Initialize Deepgram client
transcription_client = DeepgramTranscriptionClient()

@app.route('/')
def index():
    return render_template('transcribe.html')

@app.route('/api/transcribe', methods=['POST'])
async def transcribe():
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
        
    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    filename = secure_filename(audio_file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    audio_file.save(file_path)
    
    try:
        # Create transcription record
        transcription = Transcription(filename=filename, status='processing')
        db.session.add(transcription)
        db.session.commit()
        
        # Process and enhance audio
        processor = AudioProcessor(file_path)
        enhanced_audio, sample_rate, noise_type = processor.process_audio()
        
        # Save enhanced audio
        enhanced_path = os.path.join(app.config['UPLOAD_FOLDER'], f'enhanced_{filename}')
        processor.save_enhanced_audio(enhanced_audio, sample_rate, enhanced_path)
        
        # Process the enhanced audio file
        result = await transcription_client.transcribe_file(enhanced_path)
        
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
            confidence=0.85,  # Default confidence for now
            start_time=0.0,
            end_time=float(len(enhanced_audio)) / sample_rate
        )
        db.session.add(noise_profile)
            
        db.session.commit()
        
        # Clean up files
        os.remove(file_path)
        os.remove(enhanced_path)
        
        return jsonify({
            'id': transcription.id,
            'text': result['text'],
            'confidence': result['confidence'],
            'speakers': result['speakers'],
            'noise_profile': {
                'type': noise_type,
                'confidence': 0.85
            }
        })
        
    except Exception as e:
        db.session.rollback()
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(enhanced_path):
            os.remove(enhanced_path)
        return jsonify({'error': str(e)}), 500

@app.route('/api/transcriptions/<int:transcription_id>')
def get_transcription(transcription_id):
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
    
    return jsonify({
        'id': transcription.id,
        'text': transcription.text,
        'confidence': transcription.confidence_score,
        'status': transcription.status,
        'speakers': speakers,
        'noise_profiles': noise_data
    })

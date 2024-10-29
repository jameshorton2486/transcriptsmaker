from deepgram import Deepgram
import os
import asyncio
import json
from models import Transcription, Speaker, NoiseProfile
from app import db

class DeepgramTranscriptionClient:
    def __init__(self):
        self.dg_client = Deepgram(os.environ.get("DEEPGRAM_API_KEY"))
        
    async def transcribe_file(self, audio_file_path):
        """Transcribe audio file with speaker diarization and noise classification"""
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
            
            response = await self.dg_client.transcription.prerecorded(source, options)
            return self._process_response(response)
            
    def _process_response(self, response):
        """Process Deepgram response and extract relevant information"""
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
        
    async def start_streaming(self, websocket):
        """Handle real-time streaming transcription"""
        options = {
            'punctuate': True,
            'diarize': True,
            'smart_format': True,
            'language': 'en-US'
        }
        
        try:
            return await self.dg_client.transcription.live(options)
        except Exception as e:
            print(f"Error starting live transcription: {e}")
            return None

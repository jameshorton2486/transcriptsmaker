import azure.cognitiveservices.speech as speechsdk
import os
from models import Transcription, Speaker
from app import db

class AzureTranscriptionClient:
    def __init__(self):
        self.speech_config = speechsdk.SpeechConfig(
            subscription=os.environ.get("AZURE_SPEECH_KEY"),
            region=os.environ.get("AZURE_SPEECH_REGION")
        )
        self.speech_config.enable_dictation()
        self.speech_config.speech_recognition_language = "en-US"
        
    def transcribe_file(self, audio_file_path):
        """Transcribe audio file with speaker diarization"""
        audio_config = speechsdk.AudioConfig(filename=audio_file_path)
        
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config,
            audio_config=audio_config
        )
        
        done = False
        transcript = []

        def handle_result(evt):
            if evt.result.text:
                transcript.append({
                    'text': evt.result.text,
                    'offset': evt.result.offset,
                    'duration': evt.result.duration
                })

        def stop_cb(evt):
            nonlocal done
            done = True
            
        speech_recognizer.recognized.connect(handle_result)
        speech_recognizer.session_stopped.connect(stop_cb)
        speech_recognizer.canceled.connect(stop_cb)
        
        speech_recognizer.start_continuous_recognition()
        while not done:
            continue
            
        return transcript

from database import db
from datetime import datetime

class Transcription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='pending')
    text = db.Column(db.Text)
    confidence_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    speakers = db.relationship('Speaker', backref='transcription', lazy=True)

class Speaker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transcription_id = db.Column(db.Integer, db.ForeignKey('transcription.id'))
    speaker_id = db.Column(db.String(50))
    start_time = db.Column(db.Float)
    end_time = db.Column(db.Float)
    text = db.Column(db.Text)

class CustomVocabulary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(255), unique=True, nullable=False)
    pronunciation = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class NoiseProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transcription_id = db.Column(db.Integer, db.ForeignKey('transcription.id'))
    type = db.Column(db.String(50))
    confidence = db.Column(db.Float)
    start_time = db.Column(db.Float)
    end_time = db.Column(db.Float)

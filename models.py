from database import db
from datetime import datetime
from enum import Enum
from sqlalchemy import Index, CheckConstraint, event
from sqlalchemy.orm import validates

class TranscriptionStatus(str, Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

class Transcription(db.Model):
    __tablename__ = 'transcription'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False, index=True)
    status = db.Column(
        db.Enum(TranscriptionStatus),
        default=TranscriptionStatus.PENDING,
        nullable=False,
        index=True
    )
    text = db.Column(db.Text)
    confidence_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships with lazy loading
    speakers = db.relationship('Speaker', backref='transcription', lazy='dynamic', cascade='all, delete-orphan')
    noise_profiles = db.relationship('NoiseProfile', backref='transcription', lazy='dynamic', cascade='all, delete-orphan')
    
    # Composite index
    __table_args__ = (
        Index('idx_filename_status', 'filename', 'status'),
    )
    
    @validates('confidence_score')
    def validate_confidence(self, key, value):
        if value is not None and (value < 0 or value > 1):
            raise ValueError("Confidence score must be between 0 and 1")
        return value

class Speaker(db.Model):
    __tablename__ = 'speaker'
    
    id = db.Column(db.Integer, primary_key=True)
    transcription_id = db.Column(db.Integer, db.ForeignKey('transcription.id', ondelete='CASCADE'), index=True)
    speaker_id = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.Float, nullable=False)
    end_time = db.Column(db.Float, nullable=False)
    text = db.Column(db.Text, nullable=False)
    
    # Time constraint
    __table_args__ = (
        CheckConstraint('end_time > start_time', name='check_time_order'),
        CheckConstraint('start_time >= 0', name='check_start_time_positive'),
    )
    
    @validates('speaker_id')
    def validate_speaker_id(self, key, value):
        if not value:
            raise ValueError("Speaker ID cannot be empty")
        return value

class CustomVocabulary(db.Model):
    __tablename__ = 'custom_vocabulary'
    
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(255), unique=True, nullable=False, index=True)
    pronunciation = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @validates('term')
    def validate_term(self, key, value):
        if not value or len(value.strip()) == 0:
            raise ValueError("Term cannot be empty")
        return value.strip()

class NoiseProfile(db.Model):
    __tablename__ = 'noise_profile'
    
    id = db.Column(db.Integer, primary_key=True)
    transcription_id = db.Column(db.Integer, db.ForeignKey('transcription.id', ondelete='CASCADE'), index=True)
    type = db.Column(db.String(50), nullable=False)
    confidence = db.Column(db.Float, nullable=False)
    start_time = db.Column(db.Float, nullable=False)
    end_time = db.Column(db.Float, nullable=False)
    
    # Time and confidence constraints
    __table_args__ = (
        CheckConstraint('end_time > start_time', name='check_noise_time_order'),
        CheckConstraint('start_time >= 0', name='check_noise_start_time_positive'),
        CheckConstraint('confidence >= 0 AND confidence <= 1', name='check_confidence_range'),
    )
    
    @validates('type')
    def validate_type(self, key, value):
        if not value:
            raise ValueError("Noise type cannot be empty")
        return value

# Event listeners for automatic updated_at
@event.listens_for(Transcription, 'before_update')
@event.listens_for(CustomVocabulary, 'before_update')
def update_updated_at(mapper, connection, target):
    target.updated_at = datetime.utcnow()

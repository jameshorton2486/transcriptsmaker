"""Centralized exception handling system for the Legal Transcription System."""

import logging
import traceback
from functools import wraps
from typing import Optional, Type, Union
from datetime import datetime

logger = logging.getLogger(__name__)

class TranscriptionError(Exception):
    """Base exception class for all transcription-related errors."""
    def __init__(self, message: str, error_code: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.error_code = error_code or 'UNKNOWN_ERROR'
        self.timestamp = datetime.utcnow()
        self.original_error = original_error

    def to_dict(self):
        """Convert exception to dictionary for logging and API responses."""
        return {
            'error_code': self.error_code,
            'message': str(self),
            'timestamp': self.timestamp.isoformat(),
            'type': self.__class__.__name__,
            'original_error': str(self.original_error) if self.original_error else None
        }

class ValidationError(TranscriptionError):
    """Raised when input validation fails."""
    def __init__(self, message: str, field: str = None):
        super().__init__(message, error_code='VALIDATION_ERROR')
        self.field = field

class ProcessingError(TranscriptionError):
    """Raised when audio processing fails."""
    def __init__(self, message: str, stage: str = None):
        super().__init__(message, error_code='PROCESSING_ERROR')
        self.stage = stage

class APIError(TranscriptionError):
    """Raised when API operations fail."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message, error_code=f'API_ERROR_{status_code}')
        self.status_code = status_code

class DatabaseError(TranscriptionError):
    """Raised when database operations fail."""
    def __init__(self, message: str, operation: str = None):
        super().__init__(message, error_code='DATABASE_ERROR')
        self.operation = operation

class ResourceError(TranscriptionError):
    """Raised when resource limits are exceeded or resources are unavailable."""
    def __init__(self, message: str, resource_type: str = None):
        super().__init__(message, error_code='RESOURCE_ERROR')
        self.resource_type = resource_type

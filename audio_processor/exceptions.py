"""Custom exceptions for audio processing operations."""

class AudioProcessingError(Exception):
    """Base class for audio processing exceptions."""
    def __init__(self, message, error_code=None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

class AudioFormatError(AudioProcessingError):
    """Raised when audio format is invalid or unsupported."""
    def __init__(self, message):
        super().__init__(message, error_code='FORMAT_ERROR')

class AudioQualityError(AudioProcessingError):
    """Raised when audio quality doesn't meet requirements."""
    def __init__(self, message):
        super().__init__(message, error_code='QUALITY_ERROR')

class AudioProcessingTimeout(AudioProcessingError):
    """Raised when audio processing operation times out."""
    def __init__(self, message):
        super().__init__(message, error_code='TIMEOUT_ERROR')

class AudioEnhancementError(AudioProcessingError):
    """Raised when audio enhancement operation fails."""
    def __init__(self, message):
        super().__init__(message, error_code='ENHANCEMENT_ERROR')

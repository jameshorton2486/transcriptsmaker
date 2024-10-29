class StreamHandler {
    constructor() {
        this.ws = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;
        this.reconnectDelay = 1000;
        this.pingInterval = null;
        this.errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
        
        this.initializeButtons();
    }

    initializeButtons() {
        const startBtn = document.getElementById('startStreaming');
        const stopBtn = document.getElementById('stopStreaming');
        
        if (!startBtn || !stopBtn) {
            this.showError('Streaming controls not found', 'INIT_ERROR');
            return;
        }
        
        startBtn.addEventListener('click', () => this.startStreaming());
        stopBtn.addEventListener('click', () => this.stopStreaming());
    }

    showError(message, errorCode = 'UNKNOWN_ERROR', details = null) {
        console.error(`${errorCode}:`, message, details || '');
        
        // Update modal content
        const modalTitle = document.getElementById('errorModalLabel');
        const modalBody = document.getElementById('errorModalBody');
        
        modalTitle.textContent = this.getErrorTypeTitle(errorCode);
        let errorMessage = this.getEnhancedErrorMessage(message, errorCode);
        
        modalBody.innerHTML = `
            <div class="d-flex align-items-center mb-3">
                <i class="bi bi-exclamation-triangle-fill text-danger me-2"></i>
                <strong class="text-danger">${errorCode}</strong>
            </div>
            <p class="mb-0">${errorMessage}</p>
            ${details ? `<small class="text-muted mt-2 d-block">${details}</small>` : ''}
        `;

        // Show the modal
        this.errorModal.show();

        // Update transcription output with error indicator
        const output = document.getElementById('transcriptionOutput');
        if (output) {
            output.innerHTML = `
                <div class="alert alert-danger alert-dismissible fade show mb-0" role="alert">
                    <strong>${errorCode}:</strong> An error occurred. See error details in the modal.
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                </div>
            `;
        }

        if (this.isRecording) {
            this.stopStreaming();
        }
    }

    getErrorTypeTitle(errorCode) {
        switch (errorCode) {
            case 'MEDIA_ERROR':
                return 'Microphone Access Error';
            case 'WEBSOCKET_ERROR':
                return 'Connection Error';
            case 'RECORDER_ERROR':
                return 'Recording Error';
            case 'CONNECTION_ERROR':
                return 'Connection Lost';
            default:
                return 'Error';
        }
    }

    getEnhancedErrorMessage(message, errorCode) {
        switch (errorCode) {
            case 'MEDIA_ERROR':
                if (message.includes('NotAllowedError')) {
                    return 'Microphone access denied. Please allow microphone access in your browser settings and try again.';
                } else if (message.includes('NotFoundError')) {
                    return 'No microphone found. Please connect a microphone and try again.';
                } else if (message.includes('NotReadableError')) {
                    return 'Could not access microphone. Please make sure it\'s not being used by another application.';
                }
                break;
            case 'WEBSOCKET_ERROR':
                return 'Connection error. Please check your internet connection and try again.';
            case 'RECORDER_ERROR':
                return 'Error recording audio. Please check your microphone settings and try again.';
            case 'CONNECTION_ERROR':
                return 'Lost connection to streaming server. Please check your internet connection and try again.';
        }
        return message;
    }

    // ... Rest of the StreamHandler class implementation remains the same ...
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing StreamHandler...');
    window.streamHandler = new StreamHandler();
});

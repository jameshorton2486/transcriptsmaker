class StreamHandler {
    constructor() {
        console.debug('Initializing StreamHandler...');
        this.initialized = false;
        this.ws = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;
        this.reconnectDelay = 1000;
        this.pingInterval = null;

        try {
            this.initializeModal();
            this.initializeButtons();
            this.initialized = true;
            console.debug('StreamHandler initialized successfully');
        } catch (error) {
            console.error('Error initializing StreamHandler:', error);
            this.handleInitializationError(error);
            throw error;
        }
    }

    initializeButtons() {
        console.debug('Initializing streaming buttons...');
        this.startButton = document.getElementById('startStreaming');
        this.stopButton = document.getElementById('stopStreaming');

        if (!this.startButton || !this.stopButton) {
            throw new Error('Streaming buttons not found');
        }

        this.startButton.addEventListener('click', () => this.startStreaming());
        this.stopButton.addEventListener('click', () => this.stopStreaming());
    }

    async startStreaming() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.setupMediaRecorder(stream);
            this.startButton.disabled = true;
            this.stopButton.disabled = false;
        } catch (error) {
            this.showError('Failed to access microphone', 'MEDIA_ERROR', error.message);
        }
    }

    setupMediaRecorder(stream) {
        this.mediaRecorder = new MediaRecorder(stream);
        this.mediaRecorder.addEventListener('dataavailable', (event) => {
            this.audioChunks.push(event.data);
        });

        this.mediaRecorder.addEventListener('stop', () => {
            const audioBlob = new Blob(this.audioChunks, { type: 'audio/wav' });
            this.uploadAudio(audioBlob);
            this.audioChunks = [];
        });

        this.mediaRecorder.start(1000);
        this.isRecording = true;
    }

    stopStreaming() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
            this.startButton.disabled = false;
            this.stopButton.disabled = true;
        }
    }

    async uploadAudio(blob) {
        try {
            const formData = new FormData();
            formData.append('audio', blob, 'recording.wav');

            const response = await fetch('/api/transcribe', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || 'Failed to upload recording');
            }

            document.getElementById('transcriptionOutput').innerHTML = 
                `<div class="alert alert-success">Recording uploaded successfully. Transcription ID: ${result.id}</div>`;
        } catch (error) {
            this.showError(error.message, 'UPLOAD_ERROR');
        }
    }

    initializeModal() {
        console.debug('Initializing error modal...');
        const modalElement = document.getElementById('errorModal');
        if (!modalElement) {
            throw new Error('Error modal element not found');
        }
        
        this.errorModal = new bootstrap.Modal(modalElement, {
            backdrop: 'static',
            keyboard: true
        });

        modalElement.addEventListener('show.bs.modal', () => {
            console.debug('Error modal is being shown');
            document.body.classList.add('modal-open');
        });

        modalElement.addEventListener('hidden.bs.modal', () => {
            console.debug('Error modal was hidden');
            this.cleanupModal();
        });

        document.querySelectorAll('[data-bs-dismiss="modal"]').forEach(button => {
            button.addEventListener('click', () => {
                this.hideModal();
            });
        });
    }

    handleInitializationError(error) {
        console.error('Initialization error:', error);
        const errorContainer = document.createElement('div');
        errorContainer.className = 'alert alert-danger m-3';
        errorContainer.innerHTML = `
            <h4 class="alert-heading">Initialization Error</h4>
            <p>${this.sanitizeErrorMessage(error.message)}</p>
            <hr>
            <p class="mb-0">Please refresh the page or contact support if the problem persists.</p>
        `;
        document.body.insertBefore(errorContainer, document.body.firstChild);
    }

    hideModal() {
        if (this.errorModal) {
            console.debug('Hiding error modal');
            this.errorModal.hide();
            setTimeout(() => {
                document.body.classList.remove('modal-open');
                const backdrop = document.querySelector('.modal-backdrop');
                if (backdrop) backdrop.remove();
            }, 300);
        }
    }

    cleanupModal() {
        console.debug('Cleaning up error modal');
        const modalBody = document.getElementById('errorModalBody');
        if (modalBody) {
            modalBody.innerHTML = '';
        }
        document.body.classList.remove('modal-open');
        const backdrop = document.querySelector('.modal-backdrop');
        if (backdrop) {
            backdrop.remove();
        }
    }

    showError(message, errorType = 'UNKNOWN_ERROR', details = null) {
        console.error(`${errorType}:`, message, details || '');
        
        try {
            if (!this.errorModal) {
                console.error('Error modal not initialized');
                alert(this.sanitizeErrorMessage(`${errorType}: ${message}`));
                return;
            }
            
            const modalTitle = document.getElementById('errorModalLabel');
            const modalBody = document.getElementById('errorModalBody');
            
            if (!modalTitle || !modalBody) {
                console.error('Modal elements not found');
                alert(this.sanitizeErrorMessage(`${errorType}: ${message}`));
                return;
            }
            
            modalTitle.textContent = this.getErrorTypeTitle(errorType);
            modalBody.innerHTML = this.createSafeErrorContent(errorType, message, details);
            
            this.errorModal.show();
        } catch (error) {
            console.error('Error showing error modal:', error);
            alert(this.sanitizeErrorMessage(`${errorType}: ${message}`));
        }
    }

    createSafeErrorContent(errorType, message, details) {
        return `
            <div class="d-flex align-items-center mb-3">
                <i class="bi bi-exclamation-triangle-fill text-light fs-4 me-2"></i>
                <strong class="text-light">${this.sanitizeErrorMessage(errorType)}</strong>
            </div>
            <p class="mb-0 text-light fw-medium">${this.sanitizeErrorMessage(message)}</p>
            ${details ? `<pre class="mt-3 p-2 bg-dark text-light rounded"><code>${this.sanitizeErrorMessage(details)}</code></pre>` : ''}
        `;
    }

    sanitizeErrorMessage(unsafe) {
        if (typeof unsafe !== 'string') {
            unsafe = String(unsafe);
        }
        return unsafe
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;')
            .replace(/`/g, '&#x60;')
            .replace(/\(/g, '&#40;')
            .replace(/\)/g, '&#41;');
    }

    getErrorTypeTitle(errorType) {
        const errorTitles = {
            'MEDIA_ERROR': 'Microphone Access Error',
            'WEBSOCKET_ERROR': 'Connection Error',
            'RECORDER_ERROR': 'Recording Error',
            'CONNECTION_ERROR': 'Connection Lost',
            'STREAMING_ERROR': 'Streaming Error',
            'UPLOAD_ERROR': 'Upload Error',
            'INIT_ERROR': 'Initialization Error'
        };
        return errorTitles[errorType] || 'Error';
    }
}

// Enhanced initialization
document.addEventListener('DOMContentLoaded', () => {
    console.debug('DOM loaded, initializing StreamHandler...');
    try {
        if (!window.streamHandler) {
            window.streamHandler = new StreamHandler();
            console.debug('StreamHandler initialized successfully');
        }
    } catch (error) {
        console.error('Failed to initialize StreamHandler:', error);
    }
});

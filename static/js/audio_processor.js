class AudioProcessor {
    constructor() {
        console.debug('Initializing AudioProcessor...');
        this.initialized = false;
        try {
            // Initialize audio context with fallback
            console.debug('Setting up AudioContext...');
            if (!window.AudioContext && !window.webkitAudioContext) {
                throw new Error('AudioContext not supported in this browser');
            }
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.allowedFormats = ['wav', 'mp3', 'flac', 'mp4'];
            
            // Initialize error modal
            console.debug('Initializing error modal...');
            const errorModalElement = document.getElementById('errorModal');
            if (!errorModalElement) {
                throw new Error('Error modal element not found. Please check HTML structure.');
            }
            
            this.errorModal = new bootstrap.Modal(errorModalElement, {
                backdrop: 'static',
                keyboard: false
            });

            // Initialize form after modal setup
            this.initializeUploadForm();
            this.initialized = true;
            console.debug('AudioProcessor initialization completed successfully');
        } catch (error) {
            console.error('Error initializing AudioProcessor:', error);
            this.handleInitializationError(error);
            throw error;
        }
    }

    handleInitializationError(error) {
        const errorMessage = error.message || 'Failed to initialize audio processor';
        const errorDetails = {
            component: 'AudioProcessor',
            timestamp: new Date().toISOString(),
            error: error.toString(),
            stack: error.stack
        };
        console.error('Initialization error details:', errorDetails);
        this.showError(errorMessage, 'INIT_ERROR', JSON.stringify(errorDetails, null, 2));
    }

    initializeUploadForm() {
        console.debug('Initializing upload form...');
        const form = document.getElementById('uploadForm');
        if (!form) {
            throw new Error('Upload form element not found. Please check HTML structure.');
        }

        const fileInput = document.getElementById('audioFile');
        if (!fileInput) {
            throw new Error('File input element not found. Please check HTML structure.');
        }

        // Enhance file input validation
        fileInput.addEventListener('change', (e) => {
            console.debug('File input changed, validating file...');
            const file = e.target.files[0];
            
            if (!file) {
                return;
            }

            if (!this.validateFileFormat(file)) {
                this.showError(
                    `Invalid file format: ${file.type}. Please upload a WAV, MP3, FLAC, or MP4 file.`,
                    'FORMAT_ERROR'
                );
                e.target.value = '';
                return;
            }

            if (file.size > 2 * 1024 * 1024 * 1024) { // 2GB
                this.showError(
                    `File size (${(file.size / (1024 * 1024 * 1024)).toFixed(2)}GB) exceeds maximum limit of 2GB`,
                    'SIZE_ERROR'
                );
                e.target.value = '';
                return;
            }
        });

        form.addEventListener('submit', this.handleFormSubmit.bind(this));
        console.debug('Upload form initialized successfully');
    }

    async handleFormSubmit(e) {
        e.preventDefault();
        if (!this.initialized) {
            this.showError('AudioProcessor not properly initialized', 'INIT_ERROR');
            return;
        }

        console.debug('Form submission started...');
        const fileInput = document.getElementById('audioFile');
        const file = fileInput.files[0];
        
        if (!file) {
            this.showError(
                'No audio file selected. Please choose an audio file to continue.',
                'VALIDATION_ERROR'
            );
            return;
        }

        const submitButton = e.target.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';

        try {
            const formData = new FormData();
            formData.append('audio', file);

            const response = await fetch('/api/transcribe', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            console.debug('Transcription completed successfully');
            this.updateTranscriptionOutput(result);
        } catch (error) {
            console.error('Error processing file:', error);
            this.handleProcessingError(error);
        } finally {
            submitButton.disabled = false;
            submitButton.innerHTML = 'Start Transcription';
        }
    }

    handleProcessingError(error) {
        let errorMessage = 'An unexpected error occurred while processing the file';
        let errorType = 'PROCESSING_ERROR';

        if (error.message.includes('413')) {
            errorMessage = 'File size exceeds server limit';
            errorType = 'SIZE_ERROR';
        } else if (error.message.toLowerCase().includes('format')) {
            errorMessage = 'Incorrect file format. Please upload a WAV, MP3, FLAC, or MP4 file.';
            errorType = 'FORMAT_ERROR';
        } else if (error.message.toLowerCase().includes('network') || !navigator.onLine) {
            errorMessage = 'Network error occurred. Please check your internet connection.';
            errorType = 'NETWORK_ERROR';
        }

        this.showError(errorMessage, errorType, error.message);
    }

    validateFileFormat(file) {
        const extension = file.name.split('.').pop().toLowerCase();
        return this.allowedFormats.includes(extension);
    }

    showError(message, errorType = 'UNKNOWN_ERROR', details = null) {
        console.error(`${errorType}:`, message, details || '');
        
        try {
            if (!this.errorModal) {
                console.error('Error modal not initialized');
                alert(`${errorType}: ${message}`);
                return;
            }
            
            const modalTitle = document.getElementById('errorModalLabel');
            const modalBody = document.getElementById('errorModalBody');
            
            if (!modalTitle || !modalBody) {
                console.error('Modal elements not found');
                alert(`${errorType}: ${message}`);
                return;
            }
            
            modalTitle.textContent = this.getErrorTypeTitle(errorType);
            modalBody.innerHTML = `
                <div class="d-flex align-items-center mb-3">
                    <i class="bi bi-exclamation-triangle-fill text-light fs-4 me-2"></i>
                    <strong class="text-light">${errorType}</strong>
                </div>
                <p class="mb-0 text-light fw-medium">${message}</p>
                ${details ? `<pre class="mt-3 p-2 bg-dark text-light rounded"><code>${details}</code></pre>` : ''}
            `;
            
            this.errorModal.show();

            this.updateTranscriptionWithError(errorType, message);
        } catch (error) {
            console.error('Error showing error modal:', error);
            alert(`${errorType}: ${message}`);
        }
    }

    updateTranscriptionWithError(errorType, message) {
        const output = document.getElementById('transcriptionOutput');
        if (output) {
            output.innerHTML = `
                <div class="alert alert-danger alert-dismissible fade show mb-0" role="alert">
                    <div class="d-flex align-items-center">
                        <i class="bi bi-exclamation-triangle-fill me-2"></i>
                        <div>
                            <strong>${errorType}:</strong> ${message}
                            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                        </div>
                    </div>
                </div>
            `;
        }
    }

    getErrorTypeTitle(errorType) {
        const errorTitles = {
            'VALIDATION_ERROR': 'Validation Error',
            'FORMAT_ERROR': 'File Format Error',
            'SIZE_ERROR': 'File Size Error',
            'NETWORK_ERROR': 'Network Error',
            'PROCESSING_ERROR': 'Processing Error',
            'INIT_ERROR': 'Initialization Error',
            'UNKNOWN_ERROR': 'Error'
        };
        return errorTitles[errorType] || 'Error';
    }

    updateTranscriptionOutput(data) {
        console.debug('Updating transcription output...');
        const output = document.getElementById('transcriptionOutput');
        if (!output) {
            console.error('Transcription output element not found');
            return;
        }

        try {
            output.querySelectorAll('.alert').forEach(alert => alert.remove());

            if (data.error) {
                this.showError(data.error, data.error_code || 'API_ERROR');
                return;
            }
            
            let html = '<div class="transcription-content">';
            if (data.speakers && data.speakers.length > 0) {
                data.speakers.forEach(speaker => {
                    html += `
                        <div class="mb-3 p-2 border-start border-primary border-3">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <strong class="text-primary">Speaker ${speaker.id}</strong>
                                <span class="text-muted small">${this.formatTime(speaker.start_time)}</span>
                            </div>
                            <p class="mb-1">${this.escapeHtml(speaker.text)}</p>
                        </div>`;
                });
            } else {
                html += `<p>${this.escapeHtml(data.text || 'No transcription available')}</p>`;
            }
            
            if (data.confidence) {
                html += `
                    <div class="mt-3 text-muted">
                        <small>Confidence Score: ${(data.confidence * 100).toFixed(1)}%</small>
                    </div>`;
            }
            
            html += '</div>';
            output.innerHTML = html;
            console.debug('Transcription output updated successfully');
        } catch (error) {
            console.error('Error updating transcription output:', error);
            this.showError('Failed to update transcription output', 'UPDATE_ERROR', error.message);
        }
    }

    escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') return '';
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    formatTime(seconds) {
        const date = new Date(seconds * 1000);
        const minutes = date.getUTCMinutes();
        const secs = date.getUTCSeconds();
        const ms = date.getUTCMilliseconds();
        return `${minutes}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
    }
}

// Enhanced initialization with proper error handling
document.addEventListener('DOMContentLoaded', () => {
    console.debug('DOM loaded, initializing AudioProcessor...');
    try {
        if (!window.audioProcessor) {
            window.audioProcessor = new AudioProcessor();
            console.debug('AudioProcessor initialized successfully');
        }
    } catch (error) {
        console.error('Failed to initialize AudioProcessor:', error);
        // Show error in UI even if modal isn't available
        const errorContainer = document.createElement('div');
        errorContainer.className = 'alert alert-danger m-3';
        errorContainer.innerHTML = `
            <h4 class="alert-heading">Initialization Error</h4>
            <p>${error.message}</p>
            <hr>
            <p class="mb-0">Please refresh the page or contact support if the problem persists.</p>
        `;
        document.body.insertBefore(errorContainer, document.body.firstChild);
    }
});

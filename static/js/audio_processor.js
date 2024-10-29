class AudioProcessor {
    constructor() {
        console.debug('Initializing AudioProcessor...');
        try {
            // Initialize audio context
            console.debug('Setting up AudioContext...');
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.allowedFormats = ['wav', 'mp3', 'flac', 'mp4'];
            
            // Initialize error modal
            console.debug('Initializing error modal...');
            const errorModalElement = document.getElementById('errorModal');
            if (!errorModalElement) {
                throw new Error('Error modal element not found');
            }
            
            this.errorModal = new bootstrap.Modal(errorModalElement, {
                backdrop: 'static',
                keyboard: false
            });
            console.debug('Error modal initialized successfully');
            
            this.initializeUploadForm();
            console.debug('AudioProcessor initialization completed');
        } catch (error) {
            console.error('Error initializing AudioProcessor:', error);
            this.showError('Failed to initialize audio processor', 'INIT_ERROR', error.message);
            throw error;
        }
    }

    initializeUploadForm() {
        console.debug('Initializing upload form...');
        const form = document.getElementById('uploadForm');
        if (!form) {
            throw new Error('Upload form not found');
        }

        const fileInput = document.getElementById('audioFile');
        if (!fileInput) {
            throw new Error('File input element not found');
        }

        fileInput.addEventListener('change', (e) => {
            console.debug('File input changed, validating file...');
            const file = e.target.files[0];
            if (file && !this.validateFileFormat(file)) {
                this.showError(
                    'Incorrect file format. Please upload a WAV, MP3, FLAC, or MP4 file.',
                    'FORMAT_ERROR'
                );
                e.target.value = '';
            }
        });

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            console.debug('Form submission started...');
            
            const fileInput = document.getElementById('audioFile');
            const file = fileInput.files[0];
            
            if (!file) {
                this.showError(
                    'No audio file was uploaded. Please select an audio file to continue.',
                    'VALIDATION_ERROR'
                );
                return;
            }

            if (!this.validateFileFormat(file)) {
                this.showError(
                    'Incorrect file format. Please upload a WAV, MP3, FLAC, or MP4 file.',
                    'FORMAT_ERROR'
                );
                return;
            }

            if (file.size > 2 * 1024 * 1024 * 1024) { // 2GB
                this.showError('File size exceeds maximum limit of 2GB', 'SIZE_ERROR');
                return;
            }

            const formData = new FormData();
            formData.append('audio', file);

            try {
                console.debug('Submitting form data...');
                const submitButton = form.querySelector('button[type="submit"]');
                submitButton.disabled = true;
                submitButton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Processing...';

                const response = await fetch('/api/transcribe', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();
                if (!response.ok) {
                    throw new Error(result.message || 'Error processing file');
                }
                
                console.debug('Transcription completed successfully');
                this.updateTranscriptionOutput(result);
            } catch (error) {
                console.error('Error processing file:', error);
                let errorMessage = 'An unexpected error occurred while processing the file';
                let errorType = 'PROCESSING_ERROR';

                if (error.message.includes('413')) {
                    errorMessage = 'File size exceeds server limit';
                    errorType = 'SIZE_ERROR';
                } else if (error.message.includes('format')) {
                    errorMessage = 'Incorrect file format. Please upload a WAV, MP3, FLAC, or MP4 file.';
                    errorType = 'FORMAT_ERROR';
                } else if (error.message.includes('network')) {
                    errorMessage = 'Network error occurred. Please check your internet connection.';
                    errorType = 'NETWORK_ERROR';
                }

                this.showError(errorMessage, errorType, error.message);
            } finally {
                const submitButton = form.querySelector('button[type="submit"]');
                submitButton.disabled = false;
                submitButton.textContent = 'Start Transcription';
            }
        });
        
        console.debug('Upload form initialized successfully');
    }

    validateFileFormat(file) {
        const extension = file.name.split('.').pop().toLowerCase();
        return this.allowedFormats.includes(extension);
    }

    showError(message, errorType = 'UNKNOWN_ERROR', details = null) {
        console.error(`${errorType}:`, message, details || '');
        
        try {
            // Get modal elements
            const modalElement = document.getElementById('errorModal');
            if (!modalElement) {
                console.error('Error modal element not found');
                return;
            }
            
            // Initialize modal if needed
            if (!this.errorModal) {
                this.errorModal = new bootstrap.Modal(modalElement);
            }
            
            // Update modal content
            const modalTitle = document.getElementById('errorModalLabel');
            const modalBody = document.getElementById('errorModalBody');
            
            if (!modalTitle || !modalBody) {
                console.error('Modal elements not found');
                return;
            }
            
            modalTitle.textContent = this.getErrorTypeTitle(errorType);
            modalBody.innerHTML = `
                <div class="d-flex align-items-center mb-3">
                    <i class="bi bi-exclamation-triangle-fill text-light fs-4 me-2"></i>
                    <strong class="text-light">${errorType}</strong>
                </div>
                <p class="mb-0 text-light fw-medium">${message}</p>
                ${details ? `<small class="text-muted mt-2 d-block">${details}</small>` : ''}
            `;
            
            // Show modal
            this.errorModal.show();

            // Update transcription output with error indicator
            const output = document.getElementById('transcriptionOutput');
            if (output) {
                output.innerHTML = `
                    <div class="alert alert-danger alert-dismissible fade show mb-0" role="alert">
                        <div class="d-flex align-items-center">
                            <i class="bi bi-exclamation-triangle-fill me-2"></i>
                            <strong>${errorType}:</strong> An error occurred. See error details in the modal.
                        </div>
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error showing error modal:', error);
        }
    }

    getErrorTypeTitle(errorType) {
        switch (errorType) {
            case 'VALIDATION_ERROR':
                return 'Validation Error';
            case 'FORMAT_ERROR':
                return 'File Format Error';
            case 'SIZE_ERROR':
                return 'File Size Error';
            case 'NETWORK_ERROR':
                return 'Network Error';
            case 'PROCESSING_ERROR':
                return 'Processing Error';
            case 'INIT_ERROR':
                return 'Initialization Error';
            default:
                return 'Error';
        }
    }

    updateTranscriptionOutput(data) {
        console.debug('Updating transcription output...');
        const output = document.getElementById('transcriptionOutput');
        if (!output) {
            console.error('Transcription output element not found');
            return;
        }

        try {
            // Clear any existing error messages
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
                            <p class="mb-1">${speaker.text}</p>
                        </div>`;
                });
            } else {
                html += `<p>${data.text || 'No transcription available'}</p>`;
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

    formatTime(seconds) {
        const date = new Date(seconds * 1000);
        const minutes = date.getUTCMinutes();
        const secs = date.getUTCSeconds();
        const ms = date.getUTCMilliseconds();
        return `${minutes}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.debug('DOM loaded, initializing AudioProcessor...');
    try {
        window.audioProcessor = new AudioProcessor();
        console.debug('AudioProcessor initialized successfully');
    } catch (error) {
        console.error('Failed to initialize AudioProcessor:', error);
    }
});

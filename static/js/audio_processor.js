class AudioProcessor {
    constructor() {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.allowedFormats = ['wav', 'mp3', 'flac', 'mp4'];
        
        // Initialize error modal
        console.log('Initializing error modal...');
        const errorModalElement = document.getElementById('errorModal');
        if (!errorModalElement) {
            console.error('Error modal element not found');
            return;
        }
        this.errorModal = new bootstrap.Modal(errorModalElement, {
            backdrop: 'static',
            keyboard: false
        });
        console.log('Error modal initialized');
        
        this.initializeUploadForm();
    }

    initializeUploadForm() {
        const form = document.getElementById('uploadForm');
        if (!form) {
            this.showError('Upload form not found', 'INIT_ERROR');
            return;
        }

        const fileInput = document.getElementById('audioFile');
        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file && !this.validateFileFormat(file)) {
                this.showError(
                    'Incorrect file format. Please upload a WAV, MP3, FLAC, or MP4 file.',
                    'FORMAT_ERROR'
                );
                e.target.value = ''; // Clear the file input
            }
        });

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById('audioFile');
            const file = fileInput.files[0];
            
            if (!file) {
                this.showError('No audio file was uploaded. Please select an audio file to continue.', 'VALIDATION_ERROR');
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
                
                this.updateTranscriptionOutput(result);
            } catch (error) {
                console.error('Error:', error);
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

                this.showError(errorMessage, errorType);
            } finally {
                const submitButton = form.querySelector('button[type="submit"]');
                submitButton.disabled = false;
                submitButton.textContent = 'Start Transcription';
            }
        });
    }

    validateFileFormat(file) {
        const extension = file.name.split('.').pop().toLowerCase();
        return this.allowedFormats.includes(extension);
    }

    showError(message, errorType = 'UNKNOWN_ERROR') {
        console.log('Showing error modal:', { type: errorType, message: message });
        
        try {
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
            `;

            // Force show the modal
            if (this.errorModal) {
                this.errorModal.show();
                console.log('Error modal shown successfully');
            } else {
                console.error('Error modal not properly initialized');
            }

            // Also update the transcription output area with an error indicator
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
            console.error('Error showing modal:', error);
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
            default:
                return 'Error';
        }
    }

    // ... rest of the class implementation remains the same ...
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing AudioProcessor...');
    window.audioProcessor = new AudioProcessor();
});

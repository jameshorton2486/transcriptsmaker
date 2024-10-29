class AudioProcessor {
    constructor() {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.initializeUploadForm();
    }

    initializeUploadForm() {
        const form = document.getElementById('uploadForm');
        if (!form) {
            this.showError('Upload form not found', 'INIT_ERROR');
            return;
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById('audioFile');
            const file = fileInput.files[0];
            
            if (!file) {
                this.showError('Please select a file', 'VALIDATION_ERROR');
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
                this.showError(error.message || 'Error processing file', 'PROCESSING_ERROR');
            } finally {
                const submitButton = form.querySelector('button[type="submit"]');
                submitButton.disabled = false;
                submitButton.textContent = 'Start Transcription';
            }
        });
    }

    showError(message, errorType = 'UNKNOWN_ERROR') {
        const output = document.getElementById('transcriptionOutput');
        if (!output) return;

        const errorHtml = `
            <div class="alert alert-danger alert-dismissible fade show" role="alert">
                <strong>${errorType}:</strong> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        `;
        output.innerHTML = errorHtml;
    }

    updateTranscriptionOutput(data) {
        const output = document.getElementById('transcriptionOutput');
        if (!output) {
            console.error('Transcription output element not found');
            return;
        }

        // Clear any existing error messages
        output.querySelectorAll('.alert').forEach(alert => alert.remove());

        let html = '';
        
        if (data.error) {
            this.showError(data.error, data.error_code || 'API_ERROR');
            return;
        }
        
        if (data.speakers && data.speakers.length > 0) {
            html = '<div class="transcription-content">';
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
            html += '</div>';
        } else {
            html = `
                <div class="transcription-content">
                    <p>${data.text || 'No transcription available'}</p>
                </div>`;
        }
        
        // Add confidence score if available
        if (data.confidence) {
            html += `
                <div class="mt-3 text-muted">
                    <small>Confidence Score: ${(data.confidence * 100).toFixed(1)}%</small>
                </div>`;
        }
        
        output.innerHTML = html;
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
    console.log('Initializing AudioProcessor...');
    window.audioProcessor = new AudioProcessor();
});

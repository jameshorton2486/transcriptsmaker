class AudioProcessor {
    constructor() {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.initializeUploadForm();
    }

    initializeUploadForm() {
        const form = document.getElementById('uploadForm');
        if (!form) {
            console.error('Upload form not found');
            return;
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById('audioFile');
            const file = fileInput.files[0];
            
            if (!file) {
                alert('Please select a file');
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
                if (result.error) {
                    throw new Error(result.error);
                }
                
                this.updateTranscriptionOutput(result);
            } catch (error) {
                console.error('Error:', error);
                alert('Error processing file: ' + error.message);
            } finally {
                const submitButton = form.querySelector('button[type="submit"]');
                submitButton.disabled = false;
                submitButton.textContent = 'Start Transcription';
            }
        });
    }

    updateTranscriptionOutput(data) {
        const output = document.getElementById('transcriptionOutput');
        if (!output) {
            console.error('Transcription output element not found');
            return;
        }

        let html = '';
        
        if (data.speakers && data.speakers.length > 0) {
            data.speakers.forEach(speaker => {
                html += `
                    <div class="mb-2">
                        <strong class="text-primary">Speaker ${speaker.id}</strong>
                        <span class="text-muted">(${this.formatTime(speaker.start_time)})</span>
                        <p class="mb-1">${speaker.text}</p>
                    </div>`;
            });
        } else {
            html = `<p>${data.text || 'No transcription available'}</p>`;
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

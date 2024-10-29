class AudioProcessor {
    constructor() {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.initializeUploadForm();
    }

    initializeUploadForm() {
        const form = document.getElementById('uploadForm');
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
                const response = await fetch('/api/transcribe', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();
                this.updateTranscriptionOutput(result);
            } catch (error) {
                console.error('Error:', error);
                alert('Error processing file');
            }
        });
    }

    updateTranscriptionOutput(data) {
        const output = document.getElementById('transcriptionOutput');
        let html = '';
        
        data.speakers.forEach(speaker => {
            html += `<p><strong>Speaker ${speaker.id}</strong> (${this.formatTime(speaker.start_time)}): ${speaker.text}</p>`;
        });
        
        output.innerHTML = html;
    }

    formatTime(seconds) {
        return new Date(seconds * 1000).toISOString().substr(11, 8);
    }
}

// Initialize audio processor
document.addEventListener('DOMContentLoaded', () => {
    window.audioProcessor = new AudioProcessor();
});

class StreamHandler {
    constructor() {
        this.ws = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        
        this.initializeButtons();
    }

    initializeButtons() {
        const startBtn = document.getElementById('startStreaming');
        const stopBtn = document.getElementById('stopStreaming');
        
        startBtn.addEventListener('click', () => this.startStreaming());
        stopBtn.addEventListener('click', () => this.stopStreaming());
    }

    async startStreaming() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.mediaRecorder = new MediaRecorder(stream);
            
            this.ws = new WebSocket('ws://' + window.location.host + '/stream');
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.ws.send(event.data);
                }
            };
            
            this.mediaRecorder.start(100);
            this.isRecording = true;
            
            document.getElementById('startStreaming').disabled = true;
            document.getElementById('stopStreaming').disabled = false;
        } catch (error) {
            console.error('Error:', error);
            alert('Error accessing microphone');
        }
    }

    stopStreaming() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.ws.close();
            this.isRecording = false;
            
            document.getElementById('startStreaming').disabled = false;
            document.getElementById('stopStreaming').disabled = true;
        }
    }
}

// Initialize streaming handler
document.addEventListener('DOMContentLoaded', () => {
    window.streamHandler = new StreamHandler();
});

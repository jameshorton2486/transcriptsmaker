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
        
        this.initializeButtons();
    }

    initializeButtons() {
        const startBtn = document.getElementById('startStreaming');
        const stopBtn = document.getElementById('stopStreaming');
        
        startBtn.addEventListener('click', () => this.startStreaming());
        stopBtn.addEventListener('click', () => this.stopStreaming());
    }

    setupWebSocket() {
        this.ws = new WebSocket('ws://' + window.location.host + '/stream');
        
        this.ws.onopen = () => {
            console.log('WebSocket connection established');
            this.setupPing();
        };
        
        this.ws.onclose = (event) => {
            console.log('WebSocket connection closed:', event.code, event.reason);
            this.clearPing();
            
            if (this.isRecording && this.reconnectAttempts < this.maxReconnectAttempts) {
                console.log(`Attempting to reconnect (${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})`);
                setTimeout(() => {
                    this.reconnectAttempts++;
                    this.setupWebSocket();
                }, this.reconnectDelay * this.reconnectAttempts);
            } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
                this.handleError('WebSocket connection failed after multiple attempts');
                this.stopStreaming();
            }
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.handleError('WebSocket connection error');
        };
        
        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.error) {
                    this.handleError(data.error);
                } else {
                    this.updateTranscriptionOutput(data);
                }
            } catch (error) {
                console.error('Error processing message:', error);
            }
        };
    }

    setupPing() {
        this.pingInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000); // Send ping every 30 seconds
    }

    clearPing() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    async startStreaming() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true
                }
            });
            
            this.setupWebSocket();
            
            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus',
                bitsPerSecond: 64000
            });
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0 && this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(event.data);
                }
            };
            
            this.mediaRecorder.onerror = (error) => {
                console.error('MediaRecorder error:', error);
                this.handleError('Error recording audio');
                this.stopStreaming();
            };
            
            this.mediaRecorder.start(1000); // Send data every second
            this.isRecording = true;
            this.reconnectAttempts = 0;
            
            document.getElementById('startStreaming').disabled = true;
            document.getElementById('stopStreaming').disabled = false;
        } catch (error) {
            console.error('Error:', error);
            this.handleError('Error accessing microphone: ' + error.message);
        }
    }

    stopStreaming() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
        }
        
        if (this.ws) {
            this.ws.close();
        }
        
        this.clearPing();
        this.isRecording = false;
        this.mediaRecorder = null;
        this.ws = null;
        
        document.getElementById('startStreaming').disabled = false;
        document.getElementById('stopStreaming').disabled = true;
    }

    handleError(message) {
        console.error('Error:', message);
        const output = document.getElementById('transcriptionOutput');
        if (output) {
            output.innerHTML = `<div class="alert alert-danger">${message}</div>`;
        }
        this.stopStreaming();
    }

    updateTranscriptionOutput(data) {
        const output = document.getElementById('transcriptionOutput');
        if (!output) return;

        let html = '';
        if (data.speakers && data.speakers.length > 0) {
            data.speakers.forEach(speaker => {
                html += `
                    <div class="mb-2">
                        <strong class="text-primary">Speaker ${speaker.speaker_id}</strong>
                        <span class="text-muted">(${this.formatTime(speaker.start_time)})</span>
                        <p class="mb-1">${speaker.text}</p>
                    </div>`;
            });
        } else if (data.text) {
            html = `<p>${data.text}</p>`;
        }
        
        if (data.noise_profile) {
            html += `
                <div class="mt-2 text-muted">
                    <small>Background Noise: ${data.noise_profile.type} 
                    (Confidence: ${Math.round(data.noise_profile.confidence * 100)}%)</small>
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
    console.log('Initializing StreamHandler...');
    window.streamHandler = new StreamHandler();
});

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
        this.errorDisplayTimeout = null;
        
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

    setupWebSocket() {
        this.ws = new WebSocket('ws://' + window.location.host + '/stream');
        
        this.ws.onopen = () => {
            console.log('WebSocket connection established');
            this.showStatus('Connected', 'success');
            this.setupPing();
        };
        
        this.ws.onclose = (event) => {
            console.log('WebSocket connection closed:', event.code, event.reason);
            this.clearPing();
            
            if (this.isRecording && this.reconnectAttempts < this.maxReconnectAttempts) {
                this.showStatus(`Reconnecting (${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})...`, 'warning');
                setTimeout(() => {
                    this.reconnectAttempts++;
                    this.setupWebSocket();
                }, this.reconnectDelay * this.reconnectAttempts);
            } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
                this.handleError('Connection lost after multiple attempts', 'CONNECTION_ERROR');
                this.stopStreaming();
            }
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.handleError('Connection error occurred', 'WEBSOCKET_ERROR');
        };
        
        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.error) {
                    this.handleError(data.error, data.error_code || 'STREAMING_ERROR');
                } else {
                    this.updateTranscriptionOutput(data);
                }
            } catch (error) {
                console.error('Error processing message:', error);
                this.handleError('Error processing transcription', 'PARSE_ERROR');
            }
        };
    }

    showStatus(message, type = 'info') {
        const output = document.getElementById('transcriptionOutput');
        if (!output) return;

        const statusHtml = `
            <div class="alert alert-${type} alert-dismissible fade show mb-3" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        `;

        // Insert status at the top of the output
        const content = output.querySelector('.transcription-content');
        if (content) {
            content.insertAdjacentHTML('beforebegin', statusHtml);
        } else {
            output.insertAdjacentHTML('afterbegin', statusHtml);
        }
    }

    handleError(message, errorCode = 'UNKNOWN_ERROR') {
        console.error(`${errorCode}:`, message);
        
        // Clear any existing error timeout
        if (this.errorDisplayTimeout) {
            clearTimeout(this.errorDisplayTimeout);
        }

        const output = document.getElementById('transcriptionOutput');
        if (output) {
            const errorHtml = `
                <div class="alert alert-danger alert-dismissible fade show" role="alert">
                    <strong>${errorCode}:</strong> ${message}
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                </div>
            `;
            
            // Remove existing error messages
            output.querySelectorAll('.alert-danger').forEach(alert => alert.remove());
            
            // Add new error message
            output.insertAdjacentHTML('afterbegin', errorHtml);
            
            // Auto-dismiss error after 5 seconds
            this.errorDisplayTimeout = setTimeout(() => {
                const alert = output.querySelector('.alert-danger');
                if (alert) {
                    alert.classList.remove('show');
                    setTimeout(() => alert.remove(), 150);
                }
            }, 5000);
        }
        
        if (this.isRecording) {
            this.stopStreaming();
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
                this.handleError('Error recording audio', 'RECORDER_ERROR');
            };
            
            this.mediaRecorder.start(1000);
            this.isRecording = true;
            this.reconnectAttempts = 0;
            
            document.getElementById('startStreaming').disabled = true;
            document.getElementById('stopStreaming').disabled = false;
            
            this.showStatus('Recording started', 'info');
        } catch (error) {
            console.error('Error:', error);
            this.handleError(
                error.name === 'NotAllowedError' 
                    ? 'Microphone access denied. Please allow microphone access and try again.' 
                    : `Error accessing microphone: ${error.message}`,
                'MEDIA_ERROR'
            );
        }
    }

    stopStreaming() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
            this.showStatus('Recording stopped', 'info');
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

    updateTranscriptionOutput(data) {
        const output = document.getElementById('transcriptionOutput');
        if (!output) return;

        let html = '<div class="transcription-content">';
        if (data.speakers && data.speakers.length > 0) {
            data.speakers.forEach(speaker => {
                html += `
                    <div class="mb-3 p-2 border-start border-primary border-3">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <strong class="text-primary">Speaker ${speaker.speaker_id}</strong>
                            <span class="text-muted small">${this.formatTime(speaker.start_time)}</span>
                        </div>
                        <p class="mb-1">${speaker.text}</p>
                    </div>`;
            });
        } else if (data.text) {
            html += `<p>${data.text}</p>`;
        }
        
        if (data.noise_profile) {
            html += `
                <div class="mt-2 text-muted">
                    <small>Background Noise: ${data.noise_profile.type} 
                    (Confidence: ${Math.round(data.noise_profile.confidence * 100)}%)</small>
                </div>`;
        }
        
        html += '</div>';
        output.innerHTML = html;
    }

    formatTime(seconds) {
        const date = new Date(seconds * 1000);
        const minutes = date.getUTCMinutes();
        const secs = date.getUTCSeconds();
        const ms = date.getUTCMilliseconds();
        return `${minutes}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
    }

    setupPing() {
        this.pingInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000);
    }

    clearPing() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('Initializing StreamHandler...');
    window.streamHandler = new StreamHandler();
});

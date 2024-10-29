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
            this.errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
            this.initializeButtons();
            this.initialized = true;
            console.debug('StreamHandler initialized successfully');
        } catch (error) {
            console.error('Error initializing StreamHandler:', error);
            this.handleInitializationError(error);
            throw error;
        }
    }

    handleInitializationError(error) {
        const errorDetails = {
            component: 'StreamHandler',
            timestamp: new Date().toISOString(),
            error: error.toString(),
            stack: error.stack
        };
        console.error('Initialization error details:', errorDetails);
        this.showError(
            error.message || 'Failed to initialize streaming handler',
            'INIT_ERROR',
            JSON.stringify(errorDetails, null, 2)
        );
    }

    initializeButtons() {
        console.debug('Initializing streaming buttons...');
        const startBtn = document.getElementById('startStreaming');
        const stopBtn = document.getElementById('stopStreaming');
        
        if (!startBtn || !stopBtn) {
            throw new Error('Streaming control buttons not found. Please check HTML structure.');
        }
        
        startBtn.addEventListener('click', () => this.startStreaming());
        stopBtn.addEventListener('click', () => this.stopStreaming());
        
        // Reset button states
        startBtn.disabled = false;
        stopBtn.disabled = true;
    }

    async startStreaming() {
        if (!this.initialized) {
            this.showError('StreamHandler not properly initialized', 'INIT_ERROR');
            return;
        }

        try {
            console.debug('Starting streaming...');
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.setupMediaRecorder(stream);
            this.setupWebSocket();
            
            const startBtn = document.getElementById('startStreaming');
            const stopBtn = document.getElementById('stopStreaming');
            if (startBtn) startBtn.disabled = true;
            if (stopBtn) stopBtn.disabled = false;
            
            this.isRecording = true;
        } catch (error) {
            console.error('Error starting streaming:', error);
            this.handleStreamingError(error);
        }
    }

    stopStreaming() {
        console.debug('Stopping streaming...');
        try {
            if (this.mediaRecorder) {
                this.mediaRecorder.stop();
            }
            if (this.ws) {
                this.ws.close();
            }
            if (this.pingInterval) {
                clearInterval(this.pingInterval);
            }

            this.isRecording = false;
            this.audioChunks = [];
            this.reconnectAttempts = 0;

            const startBtn = document.getElementById('startStreaming');
            const stopBtn = document.getElementById('stopStreaming');
            if (startBtn) startBtn.disabled = false;
            if (stopBtn) stopBtn.disabled = true;

            console.debug('Streaming stopped successfully');
        } catch (error) {
            console.error('Error stopping streaming:', error);
            this.showError(
                'Error stopping streaming session',
                'STREAMING_ERROR',
                error.message
            );
        }
    }

    setupMediaRecorder(stream) {
        console.debug('Setting up MediaRecorder...');
        try {
            this.mediaRecorder = new MediaRecorder(stream);
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                        this.ws.send(event.data);
                    }
                }
            };

            this.mediaRecorder.onstop = () => {
                console.debug('MediaRecorder stopped');
                stream.getTracks().forEach(track => track.stop());
            };

            this.mediaRecorder.onerror = (error) => {
                console.error('MediaRecorder error:', error);
                this.showError(
                    'Error recording audio',
                    'RECORDER_ERROR',
                    error.error.message
                );
                this.stopStreaming();
            };

            this.mediaRecorder.start(1000); // Send data every second
        } catch (error) {
            console.error('Error setting up MediaRecorder:', error);
            throw new Error(`Failed to setup MediaRecorder: ${error.message}`);
        }
    }

    setupWebSocket() {
        console.debug('Setting up WebSocket connection...');
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/transcribe`;

        try {
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.debug('WebSocket connection established');
                this.setupPingInterval();
            };

            this.ws.onclose = (event) => {
                console.debug('WebSocket connection closed:', event);
                this.handleWebSocketClose(event);
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.handleWebSocketError(error);
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleTranscriptionUpdate(data);
                } catch (error) {
                    console.error('Error processing WebSocket message:', error);
                }
            };
        } catch (error) {
            console.error('Error setting up WebSocket:', error);
            throw new Error(`Failed to setup WebSocket: ${error.message}`);
        }
    }

    setupPingInterval() {
        this.pingInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000); // Send ping every 30 seconds
    }

    handleWebSocketClose(event) {
        clearInterval(this.pingInterval);
        
        if (this.isRecording && this.reconnectAttempts < this.maxReconnectAttempts) {
            console.debug(`Attempting to reconnect (${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})...`);
            setTimeout(() => {
                this.reconnectAttempts++;
                this.setupWebSocket();
            }, this.reconnectDelay * this.reconnectAttempts);
        } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            this.showError(
                'Connection lost. Maximum reconnection attempts reached.',
                'CONNECTION_ERROR'
            );
            this.stopStreaming();
        }
    }

    handleWebSocketError(error) {
        this.showError(
            'Error with transcription connection',
            'WEBSOCKET_ERROR',
            error.message
        );
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            this.stopStreaming();
        }
    }

    handleTranscriptionUpdate(data) {
        const output = document.getElementById('transcriptionOutput');
        if (!output) return;

        if (data.error) {
            this.showError(data.error, 'TRANSCRIPTION_ERROR');
            return;
        }

        // Update transcription display
        const transcriptionDiv = document.createElement('div');
        transcriptionDiv.className = 'mb-3 p-2 border-start border-primary border-3';
        transcriptionDiv.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-2">
                <strong class="text-primary">${data.speaker || 'Speaker'}</strong>
                <span class="text-muted small">${new Date().toLocaleTimeString()}</span>
            </div>
            <p class="mb-1">${this.escapeHtml(data.text)}</p>
        `;
        output.appendChild(transcriptionDiv);
        output.scrollTop = output.scrollHeight;
    }

    handleStreamingError(error) {
        let errorMessage = 'An error occurred while starting the streaming session';
        let errorType = 'STREAMING_ERROR';

        if (error.name === 'NotAllowedError') {
            errorMessage = 'Microphone access denied. Please allow microphone access and try again.';
            errorType = 'MEDIA_ERROR';
        } else if (error.name === 'NotFoundError') {
            errorMessage = 'No microphone found. Please connect a microphone and try again.';
            errorType = 'MEDIA_ERROR';
        } else if (error.name === 'NotReadableError') {
            errorMessage = 'Could not access microphone. Please make sure it\'s not being used by another application.';
            errorType = 'MEDIA_ERROR';
        }

        this.showError(errorMessage, errorType, error.message);
    }

    showError(message, errorType = 'UNKNOWN_ERROR', details = null) {
        console.error(`${errorType}:`, message, details || '');
        
        try {
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
        } catch (error) {
            console.error('Error showing error modal:', error);
            alert(`${errorType}: ${message}`);
        }

        if (this.isRecording) {
            this.stopStreaming();
        }
    }

    getErrorTypeTitle(errorType) {
        const errorTitles = {
            'MEDIA_ERROR': 'Microphone Access Error',
            'WEBSOCKET_ERROR': 'Connection Error',
            'RECORDER_ERROR': 'Recording Error',
            'CONNECTION_ERROR': 'Connection Lost',
            'STREAMING_ERROR': 'Streaming Error',
            'TRANSCRIPTION_ERROR': 'Transcription Error',
            'INIT_ERROR': 'Initialization Error'
        };
        return errorTitles[errorType] || 'Error';
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
}

// Enhanced initialization with proper error handling
document.addEventListener('DOMContentLoaded', () => {
    console.debug('DOM loaded, initializing StreamHandler...');
    try {
        if (!window.streamHandler) {
            window.streamHandler = new StreamHandler();
            console.debug('StreamHandler initialized successfully');
        }
    } catch (error) {
        console.error('Failed to initialize StreamHandler:', error);
        // Show error in UI even if modal isn't available
        const errorContainer = document.createElement('div');
        errorContainer.className = 'alert alert-danger m-3';
        errorContainer.innerHTML = `
            <h4 class="alert-heading">Streaming Initialization Error</h4>
            <p>${error.message}</p>
            <hr>
            <p class="mb-0">Please refresh the page or contact support if the problem persists.</p>
        `;
        document.body.insertBefore(errorContainer, document.body.firstChild);
    }
});

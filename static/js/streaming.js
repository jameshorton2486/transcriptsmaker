class StreamHandler {
    constructor() {
        console.debug('Initializing StreamHandler...');
        this.initialized = false;
        this.ws = null;
        this.mediaRecorder = null;
        this.audioContext = null;
        this.isRecording = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;
        this.reconnectDelay = 1000;
        this.pingInterval = null;
        this.processingMetrics = {
            bytesProcessed: 0,
            chunksProcessed: 0,
            errors: 0,
            startTime: null
        };

        try {
            this.initializeModal();
            this.initializeUI();
            this.initialized = true;
            console.debug('StreamHandler initialized successfully');
        } catch (error) {
            console.error('Error initializing StreamHandler:', error);
            this.handleInitializationError(error);
            throw error;
        }
    }

    initializeUI() {
        console.debug('Initializing streaming interface...');
        this.startButton = document.getElementById('startStreaming');
        this.stopButton = document.getElementById('stopStreaming');
        this.statusIndicator = this.createStatusIndicator();
        
        if (!this.startButton || !this.stopButton) {
            throw new Error('Streaming buttons not found');
        }

        this.startButton.addEventListener('click', () => this.startStreaming());
        this.stopButton.addEventListener('click', () => this.stopStreaming());
        
        this.transcriptContainer = document.getElementById('transcriptionOutput');
        if (!this.transcriptContainer) {
            throw new Error('Transcription output container not found');
        }
    }

    createStatusIndicator() {
        const container = document.querySelector('[data-component="streaming"] .card-header');
        if (!container) return null;

        const indicator = document.createElement('div');
        indicator.className = 'streaming-status ms-2 badge bg-secondary';
        indicator.textContent = 'Not Connected';
        container.style.display = 'flex';
        container.style.alignItems = 'center';
        container.style.justifyContent = 'space-between';
        container.appendChild(indicator);
        return indicator;
    }

    updateStatus(status, additionalInfo = '') {
        if (!this.statusIndicator) return;

        const statusMap = {
            'connected': { text: 'Connected', class: 'bg-success' },
            'connecting': { text: 'Connecting...', class: 'bg-warning' },
            'reconnecting': { text: 'Reconnecting...', class: 'bg-warning' },
            'error': { text: 'Error', class: 'bg-danger' },
            'closed': { text: 'Disconnected', class: 'bg-secondary' }
        };

        const statusInfo = statusMap[status] || { text: status, class: 'bg-secondary' };
        this.statusIndicator.className = `streaming-status ms-2 badge ${statusInfo.class}`;
        this.statusIndicator.textContent = additionalInfo ? `${statusInfo.text} - ${additionalInfo}` : statusInfo.text;
    }

    async startStreaming() {
        try {
            this.processingMetrics.startTime = Date.now();
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
            
            await this.setupWebSocket();
            this.setupAudioProcessing(stream);
            
            this.startButton.disabled = true;
            this.stopButton.disabled = false;
            this.updateStatus('connected');
            
        } catch (error) {
            console.error('Error starting stream:', error);
            this.showError('Failed to start streaming', 'MEDIA_ERROR', error.message);
        }
    }

    async setupWebSocket() {
        try {
            this.updateStatus('connecting');
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/stream`;
            
            this.ws = new WebSocket(wsUrl);
            this.setupWebSocketHandlers();
            
            await new Promise((resolve, reject) => {
                const timeout = setTimeout(() => reject(new Error('Connection timeout')), 5000);
                this.ws.onopen = () => {
                    clearTimeout(timeout);
                    resolve();
                };
            });
            
            this.startPingInterval();
            console.debug('WebSocket connection established');
            
        } catch (error) {
            throw new Error(`Failed to setup WebSocket: ${error.message}`);
        }
    }

    setupWebSocketHandlers() {
        this.ws.onmessage = async (event) => {
            try {
                const data = JSON.parse(event.data);
                switch (data.type) {
                    case 'transcript':
                        await this.handleTranscript(data);
                        break;
                    case 'status':
                        this.updateStatus(data.status);
                        break;
                    case 'error':
                        this.handleError(data);
                        break;
                }
            } catch (error) {
                console.error('Error processing WebSocket message:', error);
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.handleWebSocketError();
        };

        this.ws.onclose = () => {
            console.debug('WebSocket connection closed');
            this.updateStatus('closed');
            this.handleConnectionClose();
        };
    }

    setupAudioProcessing(stream) {
        this.audioContext = new AudioContext({
            sampleRate: 16000,
            latencyHint: 'interactive'
        });

        const source = this.audioContext.createMediaStreamSource(stream);
        const processor = this.audioContext.createScriptProcessor(2048, 1, 1);

        source.connect(processor);
        processor.connect(this.audioContext.destination);

        processor.onaudioprocess = (e) => {
            if (this.ws?.readyState === WebSocket.OPEN) {
                const inputData = e.inputBuffer.getChannelData(0);
                const audioData = new Float32Array(inputData);
                this.ws.send(audioData.buffer);
                
                this.processingMetrics.bytesProcessed += audioData.byteLength;
                this.processingMetrics.chunksProcessed++;
                
                if (this.processingMetrics.chunksProcessed % 100 === 0) {
                    this.logProcessingMetrics();
                }
            }
        };

        this.mediaRecorder = {
            stream,
            audioContext: this.audioContext,
            source,
            processor,
            stop: () => {
                processor.disconnect();
                source.disconnect();
                this.audioContext.close();
                stream.getTracks().forEach(track => track.stop());
            }
        };

        this.isRecording = true;
    }

    async handleTranscript(data) {
        if (!this.transcriptContainer) return;

        const transcriptDiv = document.createElement('div');
        transcriptDiv.className = 'mb-2 fade-in';
        
        const confidenceClass = data.confidence > 0.8 ? 'text-success' : 
                              data.confidence > 0.6 ? 'text-warning' : 'text-danger';

        transcriptDiv.innerHTML = `
            <div class="d-flex justify-content-between align-items-start">
                <p class="mb-1 flex-grow-1">${this.sanitizeErrorMessage(data.transcript)}</p>
                <span class="badge ${confidenceClass} ms-2">
                    ${(data.confidence * 100).toFixed(1)}%
                </span>
            </div>
            ${data.words.length > 0 ? `
                <div class="text-muted small">
                    <span class="me-2">Words: ${data.words.length}</span>
                    <span>Duration: ${(data.words[data.words.length - 1].end - data.words[0].start).toFixed(2)}s</span>
                </div>
            ` : ''}
        `;

        if (!data.is_final) {
            transcriptDiv.classList.add('interim');
        }

        this.transcriptContainer.appendChild(transcriptDiv);
        this.transcriptContainer.scrollTop = this.transcriptContainer.scrollHeight;
    }

    handleError(data) {
        console.error('Received error from server:', data);
        this.showError(data.error, 'STREAMING_ERROR');
        this.processingMetrics.errors++;
    }

    async handleWebSocketError() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
            
            this.updateStatus('reconnecting', `Attempt ${this.reconnectAttempts}`);
            console.debug(`Reconnecting in ${delay}ms...`);
            
            await new Promise(resolve => setTimeout(resolve, delay));
            await this.setupWebSocket();
        } else {
            this.updateStatus('error');
            this.showError('Connection lost', 'CONNECTION_ERROR', 'Unable to reconnect to the server');
            await this.stopStreaming();
        }
    }

    handleConnectionClose() {
        this.cleanupWebSocket();
        if (this.isRecording) {
            this.stopStreaming();
        }
    }

    async stopStreaming() {
        if (this.isRecording) {
            this.cleanupWebSocket();
            if (this.mediaRecorder) {
                this.mediaRecorder.stop();
                this.mediaRecorder = null;
            }
            this.isRecording = false;
            this.startButton.disabled = false;
            this.stopButton.disabled = true;
            this.updateStatus('closed');
            this.logProcessingMetrics(true);
        }
    }

    startPingInterval() {
        this.pingInterval = setInterval(() => {
            if (this.ws?.readyState === WebSocket.OPEN) {
                this.ws.send(new ArrayBuffer(0));
            }
        }, 30000);
    }

    cleanupWebSocket() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.reconnectAttempts = 0;
    }

    logProcessingMetrics(final = false) {
        const duration = (Date.now() - this.processingMetrics.startTime) / 1000;
        const metrics = {
            bytesProcessed: this.processingMetrics.bytesProcessed,
            chunksProcessed: this.processingMetrics.chunksProcessed,
            errors: this.processingMetrics.errors,
            duration: duration.toFixed(2),
            averageChunksPerSecond: (this.processingMetrics.chunksProcessed / duration).toFixed(2),
            averageBytesPerSecond: (this.processingMetrics.bytesProcessed / duration).toFixed(2)
        };
        
        console.debug(`Processing metrics${final ? ' (Final)' : ''}: `, metrics);
        return metrics;
    }

    initializeModal() {
        console.debug('Initializing error modal...');
        const modalElement = document.getElementById('errorModal');
        if (!modalElement) {
            throw new Error('Error modal element not found');
        }
        
        this.errorModal = new bootstrap.Modal(modalElement, {
            backdrop: 'static',
            keyboard: true
        });

        modalElement.addEventListener('show.bs.modal', () => {
            console.debug('Error modal is being shown');
            document.body.classList.add('modal-open');
        });

        modalElement.addEventListener('hidden.bs.modal', () => {
            console.debug('Error modal was hidden');
            this.cleanupModal();
        });

        document.querySelectorAll('[data-bs-dismiss="modal"]').forEach(button => {
            button.addEventListener('click', () => {
                this.hideModal();
            });
        });
    }

    handleInitializationError(error) {
        console.error('Initialization error:', error);
        const errorContainer = document.createElement('div');
        errorContainer.className = 'alert alert-danger m-3';
        errorContainer.innerHTML = `
            <h4 class="alert-heading">Initialization Error</h4>
            <p>${this.sanitizeErrorMessage(error.message)}</p>
            <hr>
            <p class="mb-0">Please refresh the page or contact support if the problem persists.</p>
        `;
        document.body.insertBefore(errorContainer, document.body.firstChild);
    }

    hideModal() {
        if (this.errorModal) {
            console.debug('Hiding error modal');
            this.errorModal.hide();
            setTimeout(() => {
                document.body.classList.remove('modal-open');
                const backdrop = document.querySelector('.modal-backdrop');
                if (backdrop) backdrop.remove();
            }, 300);
        }
    }

    cleanupModal() {
        console.debug('Cleaning up error modal');
        const modalBody = document.getElementById('errorModalBody');
        if (modalBody) {
            modalBody.innerHTML = '';
        }
        document.body.classList.remove('modal-open');
        const backdrop = document.querySelector('.modal-backdrop');
        if (backdrop) {
            backdrop.remove();
        }
    }

    showError(message, errorType = 'UNKNOWN_ERROR', details = null) {
        console.error(`${errorType}:`, message, details || '');
        
        try {
            if (!this.errorModal) {
                console.error('Error modal not initialized');
                alert(this.sanitizeErrorMessage(`${errorType}: ${message}`));
                return;
            }
            
            const modalTitle = document.getElementById('errorModalLabel');
            const modalBody = document.getElementById('errorModalBody');
            
            if (!modalTitle || !modalBody) {
                console.error('Modal elements not found');
                alert(this.sanitizeErrorMessage(`${errorType}: ${message}`));
                return;
            }
            
            modalTitle.textContent = this.getErrorTypeTitle(errorType);
            modalBody.innerHTML = this.createSafeErrorContent(errorType, message, details);
            
            this.errorModal.show();
        } catch (error) {
            console.error('Error showing error modal:', error);
            alert(this.sanitizeErrorMessage(`${errorType}: ${message}`));
        }
    }

    createSafeErrorContent(errorType, message, details) {
        return `
            <div class="d-flex align-items-center mb-3">
                <i class="bi bi-exclamation-triangle-fill text-light fs-4 me-2"></i>
                <strong class="text-light">${this.sanitizeErrorMessage(errorType)}</strong>
            </div>
            <p class="mb-0 text-light fw-medium">${this.sanitizeErrorMessage(message)}</p>
            ${details ? `<pre class="mt-3 p-2 bg-dark text-light rounded"><code>${this.sanitizeErrorMessage(details)}</code></pre>` : ''}
        `;
    }

    sanitizeErrorMessage(unsafe) {
        if (typeof unsafe !== 'string') {
            unsafe = String(unsafe);
        }
        return unsafe
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;')
            .replace(/`/g, '&#x60;')
            .replace(/\(/g, '&#40;')
            .replace(/\)/g, '&#41;');
    }

    getErrorTypeTitle(errorType) {
        const errorTitles = {
            'MEDIA_ERROR': 'Microphone Access Error',
            'WEBSOCKET_ERROR': 'Connection Error',
            'RECORDER_ERROR': 'Recording Error',
            'CONNECTION_ERROR': 'Connection Lost',
            'STREAMING_ERROR': 'Streaming Error',
            'UPLOAD_ERROR': 'Upload Error',
            'INIT_ERROR': 'Initialization Error'
        };
        return errorTitles[errorType] || 'Error';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.debug('DOM loaded, initializing StreamHandler...');
    let retryCount = 0;
    const maxRetries = 3;
    
    function initializeWithRetry() {
        try {
            if (!window.streamHandler) {
                window.streamHandler = new StreamHandler();
                console.debug('StreamHandler initialized successfully');
            }
        } catch (error) {
            console.error(`Failed to initialize StreamHandler (attempt ${retryCount + 1}):`, error);
            
            if (retryCount < maxRetries) {
                retryCount++;
                console.debug(`Retrying initialization in ${retryCount * 1000}ms...`);
                setTimeout(initializeWithRetry, retryCount * 1000);
            } else {
                console.error('Max retry attempts reached. StreamHandler initialization failed.');
                showFallbackError();
            }
        }
    }
    
    initializeWithRetry();
});
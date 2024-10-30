class AudioProcessor {
    constructor() {
        console.debug('Initializing AudioProcessor...');
        this.initialized = false;
        try {
            if (!window.AudioContext && !window.webkitAudioContext) {
                throw new Error('AudioContext not supported in this browser');
            }
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.allowedFormats = ['wav', 'mp3', 'flac', 'mp4'];
            
            this.initializeModal();
            this.initializeUploadForm();
            this.initialized = true;
            console.debug('AudioProcessor initialization completed successfully');
        } catch (error) {
            console.error('Error initializing AudioProcessor:', error);
            this.handleInitializationError(error);
            throw error;
        }
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

        // Enhanced close button handling
        document.querySelectorAll('[data-bs-dismiss="modal"]').forEach(button => {
            button.addEventListener('click', () => {
                this.hideModal();
            });
        });

        // Handle escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.errorModal._isShown) {
                this.hideModal();
            }
        });
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
            'VALIDATION_ERROR': 'Validation Error',
            'FORMAT_ERROR': 'File Format Error',
            'SIZE_ERROR': 'File Size Error',
            'PROCESSING_ERROR': 'Processing Error',
            'INIT_ERROR': 'Initialization Error',
            'UNKNOWN_ERROR': 'Error'
        };
        return errorTitles[errorType] || 'Error';
    }
}

// Enhanced initialization
document.addEventListener('DOMContentLoaded', () => {
    console.debug('DOM loaded, initializing AudioProcessor...');
    try {
        if (!window.audioProcessor) {
            window.audioProcessor = new AudioProcessor();
            console.debug('AudioProcessor initialized successfully');
        }
    } catch (error) {
        console.error('Failed to initialize AudioProcessor:', error);
        const safeErrorMessage = error.message
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
            
        const errorContainer = document.createElement('div');
        errorContainer.className = 'alert alert-danger m-3';
        errorContainer.innerHTML = `
            <h4 class="alert-heading">Initialization Error</h4>
            <p>${safeErrorMessage}</p>
            <hr>
            <p class="mb-0">Please refresh the page or contact support if the problem persists.</p>
        `;
        document.body.insertBefore(errorContainer, document.body.firstChild);
    }
});

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
        const errorModalElement = document.getElementById('errorModal');
        if (!errorModalElement) {
            throw new Error('Error modal element not found');
        }
        
        this.errorModal = new bootstrap.Modal(errorModalElement, {
            backdrop: 'static',
            keyboard: false
        });

        // Enhanced modal event listeners
        errorModalElement.addEventListener('show.bs.modal', () => {
            console.debug('Error modal is being shown');
        });

        errorModalElement.addEventListener('hidden.bs.modal', () => {
            console.debug('Error modal was hidden');
            this.cleanupModal();
        });

        // Improved close button handling
        const closeButtons = errorModalElement.querySelectorAll('[data-bs-dismiss="modal"]');
        closeButtons.forEach(button => {
            button.addEventListener('click', () => {
                this.hideModal();
            });
        });
    }

    cleanupModal() {
        console.debug('Cleaning up error modal content');
        const modalBody = document.getElementById('errorModalBody');
        if (modalBody) {
            modalBody.innerHTML = '';
        }
        // Reset modal state
        document.body.classList.remove('modal-open');
        const backdrop = document.querySelector('.modal-backdrop');
        if (backdrop) {
            backdrop.remove();
        }
    }

    hideModal() {
        if (this.errorModal) {
            console.debug('Hiding error modal');
            this.errorModal.hide();
            // Ensure proper cleanup after hide animation
            setTimeout(() => this.cleanupModal(), 300);
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

    // Rest of the class implementation remains the same...
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

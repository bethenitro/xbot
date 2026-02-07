/**
 * Interval Selector Component
 * Handles the advanced interval input with days, hours, minutes, seconds
 */

class IntervalSelector {
    constructor() {
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.updateDisplay();
        this.updateReplyDisplay();
    }
    
    setupEventListeners() {
        // Listen for changes on all interval inputs (posting)
        const inputs = ['intervalDays', 'intervalHours', 'intervalMinutes', 'intervalSeconds'];
        
        inputs.forEach(inputId => {
            const input = document.getElementById(inputId);
            if (input) {
                input.addEventListener('input', () => this.updateDisplay());
                input.addEventListener('change', () => this.updateDisplay());
            }
        });
        
        // Listen for changes on reply interval inputs
        const replyInputs = ['replyIntervalDays', 'replyIntervalHours', 'replyIntervalMinutes', 'replyIntervalSeconds'];
        
        replyInputs.forEach(inputId => {
            const input = document.getElementById(inputId);
            if (input) {
                input.addEventListener('input', () => this.updateReplyDisplay());
                input.addEventListener('change', () => this.updateReplyDisplay());
            }
        });
    }
    
    updateDisplay() {
        const days = parseInt(document.getElementById('intervalDays')?.value || 0);
        const hours = parseInt(document.getElementById('intervalHours')?.value || 0);
        const minutes = parseInt(document.getElementById('intervalMinutes')?.value || 0);
        const seconds = parseInt(document.getElementById('intervalSeconds')?.value || 0);
        
        // Calculate total seconds
        const totalSeconds = (days * 24 * 60 * 60) + (hours * 60 * 60) + (minutes * 60) + seconds;
        
        // Update hidden input
        const hiddenInput = document.getElementById('postingInterval');
        if (hiddenInput) {
            hiddenInput.value = totalSeconds;
        }
        
        // Update display
        this.updateDisplayText(days, hours, minutes, seconds, totalSeconds);
    }
    
    updateDisplayText(days, hours, minutes, seconds, totalSeconds) {
        const displayElement = document.getElementById('totalIntervalDisplay');
        const secondsElement = document.getElementById('totalSeconds');
        
        if (!displayElement || !secondsElement) return;
        
        // Build human-readable text
        const parts = [];
        
        if (days > 0) {
            parts.push(`${days} day${days !== 1 ? 's' : ''}`);
        }
        if (hours > 0) {
            parts.push(`${hours} hour${hours !== 1 ? 's' : ''}`);
        }
        if (minutes > 0) {
            parts.push(`${minutes} minute${minutes !== 1 ? 's' : ''}`);
        }
        if (seconds > 0) {
            parts.push(`${seconds} second${seconds !== 1 ? 's' : ''}`);
        }
        
        let displayText = 'No interval';
        if (parts.length > 0) {
            if (parts.length === 1) {
                displayText = parts[0];
            } else if (parts.length === 2) {
                displayText = parts.join(' and ');
            } else {
                displayText = parts.slice(0, -1).join(', ') + ', and ' + parts[parts.length - 1];
            }
        }
        
        displayElement.textContent = displayText;
        secondsElement.textContent = totalSeconds.toLocaleString();
        
        // Add warning for very short intervals
        const warningElement = document.getElementById('intervalWarning');
        if (totalSeconds < 60 && totalSeconds > 0) {
            if (!warningElement) {
                const warning = document.createElement('div');
                warning.id = 'intervalWarning';
                warning.className = 'alert alert-warning';
                warning.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Very short intervals may trigger rate limits';
                displayElement.parentNode.appendChild(warning);
            }
        } else if (warningElement) {
            warningElement.remove();
        }
    }
    
    // Set interval from total seconds (for loading saved values)
    setFromSeconds(totalSeconds) {
        const days = Math.floor(totalSeconds / (24 * 60 * 60));
        const remainingAfterDays = totalSeconds % (24 * 60 * 60);
        
        const hours = Math.floor(remainingAfterDays / (60 * 60));
        const remainingAfterHours = remainingAfterDays % (60 * 60);
        
        const minutes = Math.floor(remainingAfterHours / 60);
        const seconds = remainingAfterHours % 60;
        
        // Update inputs
        document.getElementById('intervalDays').value = days;
        document.getElementById('intervalHours').value = hours;
        document.getElementById('intervalMinutes').value = minutes;
        document.getElementById('intervalSeconds').value = seconds;
        
        this.updateDisplay();
    }
    
    // Get total seconds
    getTotalSeconds() {
        return parseInt(document.getElementById('postingInterval')?.value || 0);
    }
    
    // Validate interval
    isValid() {
        const total = this.getTotalSeconds();
        return total > 0; // No minimum limit as requested
    }
    
    // Get validation message
    getValidationMessage() {
        const total = this.getTotalSeconds();
        if (total <= 0) {
            return 'Interval must be greater than 0';
        }
        if (total < 10) {
            return 'Warning: Very short intervals may cause issues';
        }
        return '';
    }
    
    // Update reply interval display
    updateReplyDisplay() {
        const days = parseInt(document.getElementById('replyIntervalDays')?.value || 0);
        const hours = parseInt(document.getElementById('replyIntervalHours')?.value || 0);
        const minutes = parseInt(document.getElementById('replyIntervalMinutes')?.value || 0);
        const seconds = parseInt(document.getElementById('replyIntervalSeconds')?.value || 0);
        
        // Calculate total seconds
        const totalSeconds = (days * 24 * 60 * 60) + (hours * 60 * 60) + (minutes * 60) + seconds;
        
        // Update hidden input
        const replyIntervalInput = document.getElementById('replyInterval');
        if (replyIntervalInput) {
            replyIntervalInput.value = totalSeconds;
        }
        
        const displayElement = document.getElementById('totalReplyIntervalDisplay');
        const secondsElement = document.getElementById('totalReplySeconds');
        
        if (!displayElement || !secondsElement) return;
        
        // Build human-readable text
        const parts = [];
        
        if (days > 0) {
            parts.push(`${days} day${days !== 1 ? 's' : ''}`);
        }
        if (hours > 0) {
            parts.push(`${hours} hour${hours !== 1 ? 's' : ''}`);
        }
        if (minutes > 0) {
            parts.push(`${minutes} minute${minutes !== 1 ? 's' : ''}`);
        }
        if (seconds > 0) {
            parts.push(`${seconds} second${seconds !== 1 ? 's' : ''}`);
        }
        
        let displayText = 'No interval';
        if (parts.length > 0) {
            if (parts.length === 1) {
                displayText = parts[0];
            } else if (parts.length === 2) {
                displayText = parts.join(' and ');
            } else {
                displayText = parts.slice(0, -1).join(', ') + ', and ' + parts[parts.length - 1];
            }
        }
        
        displayElement.textContent = displayText;
        secondsElement.textContent = totalSeconds.toLocaleString();
        
        // Add warning for very short intervals
        const warningElement = document.getElementById('replyIntervalWarning');
        if (totalSeconds < 60 && totalSeconds > 0) {
            if (!warningElement) {
                const warning = document.createElement('div');
                warning.id = 'replyIntervalWarning';
                warning.className = 'alert alert-warning';
                warning.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Very short intervals may trigger rate limits';
                displayElement.parentNode.appendChild(warning);
            }
        } else if (warningElement) {
            warningElement.remove();
        }
    }
    
    // Set reply interval from total seconds (for loading saved values)
    setReplyFromSeconds(totalSeconds) {
        const days = Math.floor(totalSeconds / (24 * 60 * 60));
        const remainingAfterDays = totalSeconds % (24 * 60 * 60);
        
        const hours = Math.floor(remainingAfterDays / (60 * 60));
        const remainingAfterHours = remainingAfterDays % (60 * 60);
        
        const minutes = Math.floor(remainingAfterHours / 60);
        const seconds = remainingAfterHours % 60;
        
        // Update inputs
        document.getElementById('replyIntervalDays').value = days;
        document.getElementById('replyIntervalHours').value = hours;
        document.getElementById('replyIntervalMinutes').value = minutes;
        document.getElementById('replyIntervalSeconds').value = seconds;
        
        this.updateReplyDisplay();
    }
    
    // Get total reply seconds
    getReplyTotalSeconds() {
        return parseInt(document.getElementById('replyInterval')?.value || 0);
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('intervalDays')) {
        window.intervalSelector = new IntervalSelector();
    }
});

// Export for use in other scripts
window.IntervalSelector = IntervalSelector;
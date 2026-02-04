/**
 * Dashboard Component for Xbot Web Interface
 * Handles posting activity, account status, and pipeline management
 */

class DashboardManager {
    constructor(app) {
        this.app = app;
        this.refreshInterval = null;
        this.currentConcurrentBrowsers = 1; // Default value
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.startAutoRefresh();
        this.loadDashboardData();
        this.loadConcurrentBrowsersConfig();
    }
    
    setupEventListeners() {
        // Refresh button
        const refreshBtn = document.getElementById('refreshActivity');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.loadDashboardData());
        }
        
        // Concurrent browsers configuration
        const concurrentBrowsersInput = document.getElementById('maxConcurrentBrowsers');
        if (concurrentBrowsersInput) {
            concurrentBrowsersInput.addEventListener('change', (e) => {
                this.updateConcurrentBrowsers(parseInt(e.target.value));
            });
        }
        
        // Auto-refresh when dashboard becomes active
        document.addEventListener('sectionChanged', (e) => {
            if (e.detail.section === 'dashboard') {
                this.loadDashboardData();
            }
        });
    }
    
    async loadConcurrentBrowsersConfig() {
        try {
            const response = await fetch('/api/config/concurrent-browsers');
            if (response.ok) {
                const data = await response.json();
                this.currentConcurrentBrowsers = data.max_concurrent_browsers;
                this.updateConcurrentBrowsersDisplay();
            }
        } catch (error) {
            console.error('Failed to load concurrent browsers config:', error);
        }
    }
    
    async updateConcurrentBrowsers(value) {
        try {
            // Validate input
            const numValue = Math.max(1, Math.min(5, value));
            
            const response = await fetch('/api/config/concurrent-browsers', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ max_concurrent_browsers: numValue })
            });
            
            if (response.ok) {
                const data = await response.json();
                this.currentConcurrentBrowsers = data.max_concurrent_browsers;
                this.updateConcurrentBrowsersDisplay();
                this.app.showToast(`Concurrent browsers updated to ${numValue}`, 'success');
            } else {
                const error = await response.json();
                this.app.showToast(`Failed to update: ${error.error}`, 'error');
            }
        } catch (error) {
            console.error('Failed to update concurrent browsers:', error);
            this.app.showToast('Failed to update concurrent browsers setting', 'error');
        }
    }
    
    updateConcurrentBrowsersDisplay() {
        // Update input field
        const input = document.getElementById('maxConcurrentBrowsers');
        if (input) {
            input.value = this.currentConcurrentBrowsers;
        }
        
        // Update info display
        const currentValueSpan = document.querySelector('.concurrent-browsers-info .current-setting .value');
        if (currentValueSpan) {
            currentValueSpan.textContent = `${this.currentConcurrentBrowsers} browser${this.currentConcurrentBrowsers > 1 ? 's' : ''}`;
        }
        
        // Update performance indicator
        this.updatePerformanceIndicator();
        
        // Update recommendations
        this.updateRecommendations();
    }
    
    updatePerformanceIndicator() {
        const indicator = document.querySelector('.performance-indicator');
        if (!indicator) return;
        
        // Remove existing classes
        indicator.classList.remove('conservative', 'balanced', 'aggressive');
        
        // Add appropriate class based on value
        if (this.currentConcurrentBrowsers === 1) {
            indicator.classList.add('conservative');
            indicator.innerHTML = '<i class="fas fa-leaf"></i> Conservative';
        } else if (this.currentConcurrentBrowsers <= 3) {
            indicator.classList.add('balanced');
            indicator.innerHTML = '<i class="fas fa-balance-scale"></i> Balanced';
        } else {
            indicator.classList.add('aggressive');
            indicator.innerHTML = '<i class="fas fa-rocket"></i> Aggressive';
        }
    }
    
    updateRecommendations() {
        const recommendationsDiv = document.querySelector('.concurrent-browsers-info .recommendations');
        if (!recommendationsDiv) return;
        
        let recommendations = '';
        
        if (this.currentConcurrentBrowsers === 1) {
            recommendations = `
                <strong>Conservative Mode (1 browser):</strong>
                <ul>
                    <li>✅ Lowest system resource usage</li>
                    <li>✅ Most stable and reliable</li>
                    <li>✅ Best for older hardware</li>
                    <li>⏱️ Slower posting speed</li>
                </ul>
            `;
        } else if (this.currentConcurrentBrowsers <= 3) {
            recommendations = `
                <strong>Balanced Mode (${this.currentConcurrentBrowsers} browsers):</strong>
                <ul>
                    <li>✅ Good balance of speed and stability</li>
                    <li>✅ Moderate resource usage</li>
                    <li>✅ Recommended for most users</li>
                    <li>⚡ ${this.currentConcurrentBrowsers}x faster than single browser</li>
                </ul>
            `;
        } else {
            recommendations = `
                <strong>Aggressive Mode (${this.currentConcurrentBrowsers} browsers):</strong>
                <ul>
                    <li>⚡ Maximum posting speed</li>
                    <li>⚠️ <span class="highlight">High system resource usage</span></li>
                    <li>⚠️ <span class="highlight">Requires powerful hardware</span></li>
                    <li>⚠️ <span class="highlight">Monitor system performance</span></li>
                </ul>
            `;
        }
        
        recommendationsDiv.innerHTML = recommendations;
    }
    
    startAutoRefresh() {
        // Refresh dashboard data every 30 seconds
        this.refreshInterval = setInterval(() => {
            if (this.app.currentSection === 'dashboard') {
                this.loadDashboardData();
            }
        }, 30000);
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
    
    async loadDashboardData() {
        try {
            console.log('Loading dashboard data...');
            
            // Load all dashboard data in parallel
            const [accountActivity] = await Promise.all([
                this.fetchAccountActivity()
            ]);
            
            console.log('Dashboard data loaded:', {
                accountActivity
            });
            
            this.updateAccountActivity(accountActivity);
            
        } catch (error) {
            console.error('Failed to load dashboard data:', error);
            this.app.showToast('Failed to load dashboard data', 'error');
        }
    }
    
    async fetchAccountActivity() {
        const response = await fetch('/api/dashboard/account-activity');
        if (!response.ok) throw new Error('Failed to fetch account activity');
        const data = await response.json();
        // Handle both success/error format and direct data format
        if (data.success === false) throw new Error(data.error);
        return data;
    }
    
    updateAccountActivity(data) {
        const container = document.getElementById('accountActivity');
        if (!container) return;
        
        if (!data.accounts || data.accounts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-chart-line"></i>
                    <p>No account activity yet</p>
                    <small>Add accounts and start the bot to see activity</small>
                </div>
            `;
            return;
        }
        
        container.innerHTML = data.accounts.map(account => `
            <div class="account-item">
                <div class="account-info">
                    <div class="account-avatar">
                        ${account.username.charAt(0).toUpperCase()}
                    </div>
                    <div class="account-details">
                        <h4>@${account.username}</h4>
                        <div class="account-stats">
                            <span>Posts: ${account.total_posts}</span>
                        </div>
                    </div>
                </div>
                <div class="account-status">
                    <div class="last-post-time">
                        ${account.last_post_time ? this.formatTimeAgo(account.last_post_time) : 'Never'}
                    </div>
                </div>
            </div>
        `).join('');
    }
    
    // Utility functions
    formatTimeAgo(timestamp) {
        if (!timestamp) return 'Never';
        
        const now = new Date();
        const time = new Date(timestamp);
        const diffMs = now - time;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);
        
        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;
        
        return time.toLocaleDateString();
    }
    
    formatScheduledTime(timestamp) {
        if (!timestamp) return 'Unknown';
        
        const time = new Date(timestamp);
        return time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    
    formatTimeRemaining(timestamp) {
        if (!timestamp) return 'Unknown';
        
        const now = new Date();
        const time = new Date(timestamp);
        const diffMs = time - now;
        
        if (diffMs <= 0) return 'Now';
        
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);
        
        if (diffMins < 60) return `in ${diffMins}m`;
        if (diffHours < 24) return `in ${diffHours}h`;
        return `in ${diffDays}d`;
    }
    
    truncateText(text, maxLength) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }
    
    getCommunityName(url) {
        if (!url) return 'Unknown';
        
        // Extract community ID from URL and create a short name
        const match = url.match(/communities\/(\d+)/);
        if (match) {
            return `Community ${match[1].slice(-4)}`;
        }
        
        return 'Community';
    }
    
    destroy() {
        this.stopAutoRefresh();
    }
}

// Export for use in main app
window.DashboardManager = DashboardManager;
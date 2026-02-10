/**
 * Enhanced Twitter Bot (Xbot) - Web Interface JavaScript
 * Modern web-based GUI for bot management
 */

class XbotWebInterface {
    constructor() {
        this.currentSection = 'dashboard';
        this.botStatus = 'stopped';
        this.refreshInterval = null;
        
        // Track uploaded images for different forms
        this.quickPostFiles = [];
        this.modalPostFiles = [];
        
        // Verify essential DOM elements exist
        this.verifyDOMElements();
        
        this.init();
    }
    
    verifyDOMElements() {
        const requiredElements = [
            'startBot', 'stopBot', 'refreshData', 'clearLog',
            'addAccount', 'addProxy', 'addPost', 'saveConfig'
        ];
        
        const missingElements = [];
        requiredElements.forEach(id => {
            if (!document.getElementById(id)) {
                missingElements.push(id);
            }
        });
        
        if (missingElements.length > 0) {
            console.warn('Missing DOM elements:', missingElements);
        }
        
        // Check navigation elements
        const navLinks = document.querySelectorAll('.nav-link');
        const contentSections = document.querySelectorAll('.content-section');
        
        console.log(`Found ${navLinks.length} navigation links`);
        console.log(`Found ${contentSections.length} content sections`);
        
        if (navLinks.length === 0) {
            console.error('No navigation links found!');
        }
    }
    
    init() {
        this.setupEventListeners();
        this.setupNavigation();
        this.setupWebSocket();
        this.loadInitialData();
        
        // Initialize dashboard manager with a slight delay to ensure DOM is ready
        setTimeout(() => {
            if (window.DashboardManager) {
                this.dashboardManager = new window.DashboardManager(this);
                console.log('Dashboard manager initialized');
            } else {
                console.warn('DashboardManager not available');
            }
        }, 100);
    }
    
    setupWebSocket() {
        // Initialize Socket.IO connection
        this.socket = io();
        
        this.socket.on('connect', () => {
            console.log('Connected to WebSocket');
            this.addLogEntry('Connected to server');
        });
        
        this.socket.on('disconnect', () => {
            console.log('Disconnected from WebSocket');
            this.addLogEntry('Disconnected from server');
        });
        
        this.socket.on('status_update', (data) => {
            console.log('Status update received:', data);
            this.updateBotStatus(data.status);
            this.updateStats(data.stats);
            
            // Refresh dashboard data when status changes
            if (this.dashboardManager && this.currentSection === 'dashboard') {
                this.dashboardManager.loadDashboardData();
            }
        });
        
        // Listen for dashboard refresh events
        this.socket.on('dashboard_refresh', () => {
            console.log('Dashboard refresh requested');
            if (this.dashboardManager && this.currentSection === 'dashboard') {
                this.dashboardManager.loadDashboardData();
            }
        });
        
        this.socket.on('log_entry', (data) => {
            this.addLogEntry(data.message, data.level);
        });
        
        this.socket.on('file_updated', (data) => {
            this.showToast(`${data.filename} updated`, 'info');
        });
        
        this.socket.on('error', (data) => {
            this.showToast('WebSocket error: ' + data.message, 'error');
        });
        
        // Request status updates every 10 seconds instead of HTTP polling
        setInterval(() => {
            if (this.socket.connected) {
                this.socket.emit('request_status');
            }
        }, 10000);
    }
    
    setupEventListeners() {
        try {
            // Navigation
            document.querySelectorAll('.nav-link').forEach(link => {
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    const section = link.dataset.section;
                    console.log('Navigation clicked:', section); // Debug log
                    this.showSection(section);
                });
            });
            
            // Bot controls
            document.getElementById('startBot')?.addEventListener('click', () => this.startBot());
            document.getElementById('stopBot')?.addEventListener('click', () => this.stopBot());
            
            // Scheduler controls (same as bot controls)
            document.getElementById('startScheduler')?.addEventListener('click', () => this.startBot());
            document.getElementById('stopScheduler')?.addEventListener('click', () => this.stopBot());
            
            // Dashboard
            document.getElementById('refreshData')?.addEventListener('click', () => this.refreshData());
            document.getElementById('clearLog')?.addEventListener('click', () => this.clearLog());
            
            // Accounts
            document.getElementById('addAccount')?.addEventListener('click', () => this.showAddAccountModal());
            
            // Proxies
            document.getElementById('addProxy')?.addEventListener('click', () => this.showAddProxyModal());
            document.getElementById('importProxies')?.addEventListener('click', () => this.showImportProxiesModal());
            document.getElementById('testAllProxies')?.addEventListener('click', () => this.testAllProxies());
            
            // Posts
            document.getElementById('addPost')?.addEventListener('click', () => this.showAddPostModal());
            document.getElementById('addCommunity')?.addEventListener('click', () => this.showAddCommunityModal());
            document.getElementById('bulkImportCommunities')?.addEventListener('click', () => this.showBulkImportCommunitiesModal());
            document.getElementById('addToQueue')?.addEventListener('click', () => this.addToQueue());
            document.getElementById('postNow')?.addEventListener('click', () => this.postNow());
            
            // Image upload handler
            document.getElementById('imageUpload')?.addEventListener('change', (e) => this.handleImageUpload(e));
            
            // Initialize image preview
            this.updateImagePreview();
            
            // Settings
            document.getElementById('saveConfig')?.addEventListener('click', () => this.saveConfig());
            document.getElementById('saveSchedulerSettings')?.addEventListener('click', () => this.saveConfig());
            document.getElementById('resetConfig')?.addEventListener('click', () => this.resetConfig());
            
            // Concurrent browsers input handler
            document.getElementById('maxConcurrentBrowsers')?.addEventListener('input', (e) => {
                const value = Math.max(1, Math.min(5, parseInt(e.target.value) || 1));
                e.target.value = value; // Ensure value stays within bounds
                this.updateConcurrentBrowsersDisplay(value);
            });
            
            // Modal
            document.querySelector('.modal-close')?.addEventListener('click', () => this.hideModal());
            
            // Handle modal overlay clicks properly
            document.querySelector('.modal-overlay')?.addEventListener('click', (e) => {
                this.handleModalOverlayClick(e);
            });
            
            console.log('Event listeners setup completed'); // Debug log
        } catch (error) {
            console.error('Error setting up event listeners:', error);
        }
    }
    
    setupNavigation() {
        // Show dashboard by default
        this.showSection('dashboard');
    }
    
    showSection(sectionName) {
        console.log('Showing section:', sectionName); // Debug log
        
        // Hide all sections
        document.querySelectorAll('.content-section').forEach(section => {
            section.classList.remove('active');
        });
        
        // Remove active class from all nav links
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        
        // Show selected section
        const targetSection = document.getElementById(sectionName);
        if (targetSection) {
            targetSection.classList.add('active');
        } else {
            console.error('Section not found:', sectionName);
        }
        
        // Add active class to selected nav link
        const targetNavLink = document.querySelector(`[data-section="${sectionName}"]`);
        if (targetNavLink) {
            targetNavLink.classList.add('active');
        } else {
            console.error('Nav link not found for section:', sectionName);
        }
        
        this.currentSection = sectionName;
        
        // Dispatch section change event for other components
        document.dispatchEvent(new CustomEvent('sectionChanged', {
            detail: { section: sectionName }
        }));
        
        // Load section-specific data
        this.loadSectionData(sectionName);
    }
    
    loadSectionData(section) {
        switch (section) {
            case 'dashboard':
                this.loadDashboardData();
                break;
            case 'accounts':
                this.loadAccounts();
                break;
            case 'proxies':
                this.loadProxies();
                break;
            case 'posts':
                this.loadCaptions();
                this.loadImageGroups();
                this.loadCommunities();
                this.loadContentPairs();
                break;
            case 'settings':
                this.loadConfig();
                break;
        }
    }
    
    async loadInitialData() {
        await this.refreshStatus();
        await this.loadDashboardData();
        await this.loadAccounts();
        await this.loadCommunities();
        await this.loadCaptions();
        await this.loadImageGroups();
    }
    
    async editFile(filename) {
        try {
            // Get file content
            const response = await fetch(`/api/files/${filename}`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showFileEditModal(filename, data.content);
            } else {
                this.showToast('Failed to load file: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to load file: ' + error.message, 'error');
            console.error('Failed to load file:', error);
        }
    }
    
    showFileEditModal(filename, content) {
        const fileType = filename.split('.').pop();
        const isJson = fileType === 'json';
        
        this.showModal(`Edit ${filename}`, `
            <div class="form-group">
                <label for="fileContent">File Content</label>
                <textarea id="fileContent" class="form-control" rows="20" 
                          style="font-family: 'Courier New', monospace; font-size: 14px;">${content}</textarea>
            </div>
            ${isJson ? '<p class="help-text">⚠️ Make sure to maintain valid JSON format</p>' : ''}
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.saveFile('${filename}')">Save File</button>
        `);
    }
    
    async saveFile(filename) {
        const content = document.getElementById('fileContent').value;
        
        // Validate JSON if it's a JSON file
        if (filename.endsWith('.json')) {
            try {
                JSON.parse(content);
            } catch (e) {
                this.showToast('Invalid JSON format: ' + e.message, 'error');
                return;
            }
        }
        
        try {
            const response = await fetch(`/api/files/${filename}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast(data.message, 'success');
                this.hideModal();
                this.addLogEntry(`File ${filename} saved`);
            } else {
                this.showToast('Failed to save file: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to save file: ' + error.message, 'error');
            console.error('Failed to save file:', error);
        }
    }
    
    async refreshStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            if (data.success) {
                this.updateBotStatus(data.status);
                this.updateStats(data.stats);
            }
        } catch (error) {
            console.error('Failed to refresh status:', error);
        }
    }
    
    updateBotStatus(status) {
        this.botStatus = status;
        const statusText = document.getElementById('statusText');
        const statusDot = document.querySelector('.status-dot');
        const startBtn = document.getElementById('startBot');
        const stopBtn = document.getElementById('stopBot');
        
        if (status === 'running') {
            statusText.textContent = 'Status: Running';
            statusDot.className = 'status-dot running';
            startBtn.disabled = true;
            stopBtn.disabled = false;
        } else {
            statusText.textContent = 'Status: Stopped';
            statusDot.className = 'status-dot stopped';
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
    }
    
    updateStats(stats) {
        const updateElement = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        };

        updateElement('accountCount', stats.accounts || 0);
        updateElement('proxyCount', stats.proxies || 0);
        updateElement('queueCount', stats.queue || 0);
        updateElement('successRate', stats.success_rate || '0%');
    }
    
    async loadDashboardData() {
        await this.refreshStatus();
        
        // Delegate to dashboard manager if it exists
        if (this.dashboardManager && this.dashboardManager.loadDashboardData) {
            await this.dashboardManager.loadDashboardData();
        }
    }
    
    async loadAccounts() {
        try {
            const response = await fetch('/api/accounts');
            const data = await response.json();
            
            if (data.success) {
                this.renderAccounts(data.accounts);
                this.updateAccountSelect(data.accounts);
            } else {
                this.showToast('Failed to load accounts: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to load accounts', 'error');
            console.error('Failed to load accounts:', error);
        }
    }
    
    renderAccounts(accounts) {
        const container = document.getElementById('accountsList');
        
        if (accounts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-users"></i>
                    <p>No accounts added yet</p>
                    <small>Click "Add Account" to get started</small>
                </div>
            `;
            return;
        }
        
        container.innerHTML = accounts.map(account => {
            const proxyText = account.use_proxy 
                ? (account.proxy !== 'None' ? account.proxy : 'No proxy selected')
                : 'Proxy disabled';
            const proxyClass = account.use_proxy && account.proxy !== 'None' ? 'proxy-enabled' : 'proxy-disabled';
            const isActive = account.is_active !== false; // Default to true if not set
            
            return `
                <div class="list-item">
                    <div class="item-info">
                        <div class="item-title">@${account.username} ${!isActive ? '<span style="color: #999;">(Inactive)</span>' : ''}</div>
                        <div class="item-subtitle">
                            <span class="${proxyClass}">🔗 ${proxyText}</span>
                        </div>
                    </div>
                    <div class="item-actions">
                        <span class="status-badge ${account.status}">${account.status}</span>
                        <button class="btn btn-outline btn-sm" onclick="app.toggleAccount('${account.username}')" title="${isActive ? 'Deactivate' : 'Activate'} account">
                            <i class="fas fa-toggle-${isActive ? 'on' : 'off'}"></i>
                        </button>
                        <button class="btn btn-outline btn-sm" onclick="app.openAccountBrowser('${account.username}')" title="Open Browser">
                            <i class="fas fa-external-link-alt"></i>
                        </button>
                        <button class="btn btn-outline btn-sm" onclick="app.editAccountProxy('${account.username}')" title="Edit proxy">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="app.removeAccount('${account.username}')">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    updateAccountSelect(accounts) {
        const select = document.getElementById('accountSelect');
        
        if (accounts.length === 0) {
            select.innerHTML = '<option value="">No accounts available</option>';
            return;
        }
        
        select.innerHTML = '<option value="">Select account...</option>' +
            accounts.map(account => 
                `<option value="${account.username}">@${account.username}</option>`
            ).join('');
    }
    
    async loadProxies() {
        try {
            const response = await fetch('/api/proxies');
            const data = await response.json();
            
            if (data.success) {
                this.renderProxies(data.proxies);
            } else {
                this.showToast('Failed to load proxies: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to load proxies', 'error');
            console.error('Failed to load proxies:', error);
        }
    }
    
    renderProxies(proxies) {
        const container = document.getElementById('proxiesList');
        
        if (proxies.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-shield-alt"></i>
                    <p>No proxies added yet</p>
                    <small>Click "Add Proxy" to get started</small>
                </div>
            `;
            return;
        }
        
        container.innerHTML = proxies.map(proxy => `
            <div class="list-item">
                <div class="item-info">
                    <div class="item-title">${proxy.display_url || proxy.host + ':' + proxy.port}</div>
                    <div class="item-subtitle">Type: ${proxy.type.toUpperCase()} | User: ${proxy.username || 'None'}</div>
                </div>
                <div class="item-actions">
                    <span class="status-badge ${proxy.status}">${proxy.status}</span>
                    <button class="btn btn-outline btn-sm" onclick="app.testProxy('${proxy.id}')">
                        <i class="fas fa-bolt"></i>
                    </button>
                    <button class="btn btn-danger btn-sm" onclick="app.removeProxy('${proxy.id}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    }
    
    async startBot() {
        try {
            const response = await fetch('/api/bot/start', { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Bot started successfully', 'success');
                this.addLogEntry('Bot started');
            } else {
                this.showToast('Failed to start bot: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to start bot', 'error');
            console.error('Failed to start bot:', error);
        }
    }
    
    async stopBot() {
        try {
            const response = await fetch('/api/bot/stop', { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Bot stopped successfully', 'success');
                this.addLogEntry('Bot stopped');
            } else {
                this.showToast('Failed to stop bot: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to stop bot', 'error');
            console.error('Failed to stop bot:', error);
        }
    }
    
    showAddAccountModal() {
        // First load available proxies
        this.loadProxiesForAccountModal().then(proxies => {
            const proxyOptions = proxies.length > 0 
                ? '<option value="">No proxy</option>' + 
                  proxies.map(proxy => 
                      `<option value="${proxy.id}">${proxy.display_url || proxy.host + ':' + proxy.port} (${proxy.status})</option>`
                  ).join('')
                : '<option value="">No proxies available</option>';

            this.showModal('Add Account', `
                <form id="addAccountForm">
                    <div class="form-group">
                        <label for="accountUsername">Username</label>
                        <input type="text" id="accountUsername" class="form-control" 
                               placeholder="Enter Twitter username (without @)" required>
                    </div>
                    <div class="form-group">
                        <label for="accountProxy">Proxy (Optional)</label>
                        <select id="accountProxy" class="form-control">
                            ${proxyOptions}
                        </select>
                        <small class="help-text">Select a proxy to use for this account's login and posting</small>
                    </div>
                    <div class="form-group">
                        <label class="checkbox-label">
                            <input type="checkbox" id="useProxyForAccount" checked> 
                            Use proxy for this account
                        </label>
                        <small class="help-text">When enabled, this account will always use the selected proxy</small>
                    </div>
                </form>
            `, `
                <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
                <button class="btn btn-primary" onclick="app.addAccount()">Add Account</button>
            `, false); // Prevent accidental closing
        });
    }
    
    async loadProxiesForAccountModal() {
        try {
            const response = await fetch('/api/proxies');
            const data = await response.json();
            
            if (data.success) {
                // Filter to only show working or unknown proxies
                return data.proxies.filter(proxy => proxy.status !== 'failed');
            } else {
                console.error('Failed to load proxies for account modal:', data.error);
                return [];
            }
        } catch (error) {
            console.error('Failed to load proxies for account modal:', error);
            return [];
        }
    }
    
    async addAccount() {
        const username = document.getElementById('accountUsername').value.trim();
        const selectedProxy = document.getElementById('accountProxy').value;
        const useProxy = document.getElementById('useProxyForAccount').checked;
        
        if (!username) {
            this.showToast('Please enter a username', 'warning');
            return;
        }
        
        try {
            const requestData = {
                username: username,
                use_proxy: useProxy
            };
            
            // Add proxy if selected and use_proxy is enabled
            if (useProxy && selectedProxy) {
                requestData.preferred_proxy = selectedProxy;
            }
            
            const response = await fetch('/api/accounts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                if (data.pending_login) {
                    // Show login completion modal instead of hiding
                    this.showLoginCompletionModal(data.username, data.message);
                } else {
                    this.showToast('Account added successfully', 'success');
                    this.hideModal();
                    this.loadAccounts();
                    const proxyText = selectedProxy && useProxy ? ` with proxy` : '';
                    this.addLogEntry(`Account @${username} added${proxyText}`);
                    
                    // Refresh dashboard data
                    if (this.dashboardManager) {
                        this.dashboardManager.loadDashboardData();
                    }
                }
            } else {
                this.showToast('Failed to add account: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to add account: ' + error.message, 'error');
            console.error('Failed to add account:', error);
        }
    }
    
    showLoginCompletionModal(username, message) {
        this.showModal('Complete Login', `
            <div class="login-completion-info">
                <p><strong>Browser opened for account: @${username}</strong></p>
                <p>${message}</p>
                <div class="login-instructions">
                    <h4>Instructions:</h4>
                    <ol>
                        <li>The browser has opened with Google.com</li>
                        <li><strong>You have complete control</strong> - browse wherever you want</li>
                        <li>Navigate to any platform and login to your account manually</li>
                        <li>Take your time - no rush, no automation</li>
                        <li>Once you're successfully logged in, click "Login Complete" below</li>
                    </ol>
                    <div class="manual-control-info">
                        <h5>✋ Complete Manual Control:</h5>
                        <ul>
                            <li>No automatic mouse movements</li>
                            <li>No automatic navigation</li>
                            <li>No automatic typing or clicking</li>
                            <li>You control everything - the bot just saves cookies when you're done</li>
                        </ul>
                    </div>
                </div>
                <div class="login-status" id="loginStatus">
                    <span class="status-indicator waiting">⏳ Waiting for login...</span>
                </div>
            </div>
        `, `
            <button class="btn btn-outline" onclick="app.cancelLogin('${username}')">Cancel</button>
            <button class="btn btn-primary" onclick="app.completeLogin('${username}')">Login Complete</button>
        `, false); // Don't allow closing by clicking outside
    }
    
    async completeLogin(username) {
        try {
            const statusElement = document.getElementById('loginStatus');
            if (statusElement) {
                statusElement.innerHTML = '<span class="status-indicator processing">⏳ Completing login...</span>';
            }
            
            const response = await fetch(`/api/accounts/${username}/complete-login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Account login completed successfully!', 'success');
                this.hideModal();
                this.loadAccounts();
                this.addLogEntry(`Account @${username} login completed`);
            } else {
                if (statusElement) {
                    statusElement.innerHTML = '<span class="status-indicator error">❌ Login failed</span>';
                }
                this.showToast('Failed to complete login: ' + data.error, 'error');
            }
        } catch (error) {
            const statusElement = document.getElementById('loginStatus');
            if (statusElement) {
                statusElement.innerHTML = '<span class="status-indicator error">❌ Error occurred</span>';
            }
            this.showToast('Failed to complete login: ' + error.message, 'error');
            console.error('Failed to complete login:', error);
        }
    }
    
    async cancelLogin(username) {
        try {
            const response = await fetch(`/api/accounts/${username}/cancel-login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Login cancelled', 'info');
                this.hideModal();
                this.addLogEntry(`Login cancelled for account @${username}`);
            } else {
                this.showToast('Failed to cancel login: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to cancel login: ' + error.message, 'error');
            console.error('Failed to cancel login:', error);
        }
    }

    async openAccountBrowser(username) {
        if (!confirm(`Open browser for @${username}?`)) {
            return;
        }
        
        try {
            const response = await fetch('/api/accounts/open', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast(data.message, 'success');
            } else {
                this.showToast('Failed to open browser: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to open browser', 'error');
            console.error('Failed to open browser:', error);
        }
    }
    
    async editAccountProxy(username) {
        // Load available proxies first
        const proxies = await this.loadProxiesForAccountModal();
        
        // Get current account data
        try {
            const response = await fetch('/api/accounts');
            const data = await response.json();
            
            if (!data.success) {
                this.showToast('Failed to load account data', 'error');
                return;
            }
            
            const account = data.accounts.find(acc => acc.username === username);
            if (!account) {
                this.showToast('Account not found', 'error');
                return;
            }
            
            const proxyOptions = '<option value="">No proxy</option>' + 
                proxies.map(proxy => {
                    const selected = proxy.id === account.proxy ? 'selected' : '';
                    return `<option value="${proxy.id}" ${selected}>${proxy.display_url || proxy.host + ':' + proxy.port} (${proxy.status})</option>`;
                }).join('');

            this.showModal(`Edit Proxy for @${username}`, `
                <form id="editAccountProxyForm">
                    <div class="form-group">
                        <label for="editAccountProxy">Proxy</label>
                        <select id="editAccountProxy" class="form-control">
                            ${proxyOptions}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="checkbox-label">
                            <input type="checkbox" id="editUseProxyForAccount" ${account.use_proxy ? 'checked' : ''}> 
                            Use proxy for this account
                        </label>
                    </div>
                </form>
            `, `
                <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
                <button class="btn btn-primary" onclick="app.saveAccountProxy('${username}')">Save Changes</button>
            `);
            
        } catch (error) {
            this.showToast('Failed to load account data: ' + error.message, 'error');
            console.error('Failed to load account data:', error);
        }
    }
    
    async saveAccountProxy(username) {
        const selectedProxy = document.getElementById('editAccountProxy').value;
        const useProxy = document.getElementById('editUseProxyForAccount').checked;
        
        try {
            const response = await fetch(`/api/accounts/${username}/proxy`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    preferred_proxy: selectedProxy || null,
                    use_proxy: useProxy
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Account proxy settings updated', 'success');
                this.hideModal();
                this.loadAccounts();
                this.addLogEntry(`Updated proxy settings for @${username}`);
            } else {
                this.showToast('Failed to update proxy settings: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to update proxy settings: ' + error.message, 'error');
            console.error('Failed to update proxy settings:', error);
        }
    }
    
    // Posts Management
    async loadPosts() {
        try {
            const response = await fetch('/api/posts');
            const data = await response.json();
            
            if (data.success) {
                this.renderPosts(data.posts);
            } else {
                this.showToast('Failed to load posts: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to load posts', 'error');
            console.error('Failed to load posts:', error);
        }
    }
    
    renderPosts(posts) {
        const container = document.getElementById('postsList');
        
        if (posts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-edit"></i>
                    <p>No posts added yet</p>
                    <small>Click "Add Post" to create your first post</small>
                </div>
            `;
            return;
        }
        
        container.innerHTML = posts.map(post => {
            const imageCount = post.images ? post.images.length : 0;
            const imageText = imageCount > 0 ? ` | ${imageCount} image(s)` : '';
            
            return `
                <div class="list-item">
                    <div class="item-info">
                        <div class="item-title">${post.content.substring(0, 100)}${post.content.length > 100 ? '...' : ''}</div>
                        <div class="item-subtitle">Used: ${post.used_count} times | Created: ${new Date(post.created_at).toLocaleDateString()}${imageText}</div>
                        ${imageCount > 0 ? `
                            <div class="post-images">
                                ${post.images.slice(0, 3).map(img => `
                                    <img src="/api/images/${img.split('/').pop()}" alt="Post image" style="width: 40px; height: 40px; object-fit: cover; margin: 2px; border-radius: 4px;">
                                `).join('')}
                                ${imageCount > 3 ? `<span class="more-images">+${imageCount - 3} more</span>` : ''}
                            </div>
                        ` : ''}
                    </div>
                    <div class="item-actions">
                        <span class="status-badge ${post.active ? 'active' : 'inactive'}">${post.active ? 'Active' : 'Inactive'}</span>
                        <button class="btn btn-outline btn-sm" onclick="app.togglePost(${post.id})" title="Toggle active">
                            <i class="fas fa-toggle-${post.active ? 'on' : 'off'}"></i>
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="app.removePost(${post.id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    showAddPostModal() {
        this.modalPostFiles = []; // Reset modal files
        this.showModal('Add Post', `
            <form id="addPostForm">
                <div class="form-group">
                    <label for="postContentModal">Post Content</label>
                    <textarea id="postContentModal" class="form-control" rows="6" 
                              placeholder="Enter your post content here..." required></textarea>
                    <small class="help-text">Write engaging content for your Twitter posts</small>
                </div>
                <div class="form-group">
                    <label for="postImageModal">Image (Optional)</label>
                    <input type="file" id="postImageModal" class="form-control" 
                           accept="image/*" multiple>
                    <small class="help-text">Select up to 4 images to attach to your post</small>
                </div>
                <div id="imagePreviewModal" class="image-preview" style="display: none;">
                    <h4>Image Preview:</h4>
                    <div id="imagePreviewContainerModal" class="image-preview-container"></div>
                </div>
            </form>
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.addPostFromModal()">Add Post</button>
        `);
        
        // Add image preview functionality
        document.getElementById('postImageModal').addEventListener('change', (e) => {
            const files = Array.from(e.target.files);
            if (this.modalPostFiles.length + files.length > 4) {
                this.showToast('Maximum 4 images allowed per post', 'warning');
                const remainingSlots = 4 - this.modalPostFiles.length;
                if (remainingSlots > 0) {
                    this.modalPostFiles.push(...files.slice(0, remainingSlots));
                }
            } else {
                this.modalPostFiles.push(...files);
            }
            e.target.value = ''; // Clear value to allow re-selecting
            this.previewImages();
        });
    }
    
    removeModalImage(index) {
        this.modalPostFiles.splice(index, 1);
        this.previewImages();
    }
    
    previewImages() {
        const previewContainer = document.getElementById('imagePreviewContainerModal');
        const previewSection = document.getElementById('imagePreviewModal');
        
        if (!previewSection || !previewContainer) return;
        
        if (this.modalPostFiles.length === 0) {
            previewSection.style.display = 'none';
            return;
        }
        
        previewContainer.innerHTML = '';
        previewSection.style.display = 'block';
        
        this.modalPostFiles.forEach((file, index) => {
            if (file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const imgDiv = document.createElement('div');
                    imgDiv.className = 'image-preview-item';
                    imgDiv.innerHTML = `
                        <img src="${e.target.result}" alt="Preview ${index + 1}" style="max-width: 100px; max-height: 100px; margin: 5px;">
                        <button type="button" class="image-preview-remove" onclick="app.removeModalImage(${index})" title="Remove image">
                            ×
                        </button>
                    `;
                    previewContainer.appendChild(imgDiv);
                };
                reader.readAsDataURL(file);
            }
        });
    }
    
    async addPostFromModal() {
        const content = document.getElementById('postContentModal').value.trim();
        
        if (!content) {
            this.showToast('Please enter post content', 'warning');
            return;
        }
        
        try {
            // Prepare form data for file upload
            const formData = new FormData();
            formData.append('content', content);
            
            // Add images if selected
            this.modalPostFiles.forEach((file) => {
                formData.append('images', file);
            });
            
            const response = await fetch('/api/posts', {
                method: 'POST',
                body: formData  // Don't set Content-Type header, let browser set it with boundary
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                const imageText = this.modalPostFiles.length > 0 ? ` with ${this.modalPostFiles.length} image(s)` : '';
                this.showToast(`Post added successfully${imageText}`, 'success');
                this.hideModal();
                this.modalPostFiles = []; // Clear
                this.loadPosts();
            } else {
                this.showToast('Failed to add post: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to add post: ' + error.message, 'error');
            console.error('Failed to add post:', error);
        }
    }
    
    async removePost(postId) {
        if (!confirm('Are you sure you want to remove this post?')) {
            return;
        }
        
        try {
            const response = await fetch(`/api/posts/${postId}`, { method: 'DELETE' });
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Post removed successfully', 'success');
                this.loadPosts();
            } else {
                this.showToast('Failed to remove post: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to remove post: ' + error.message, 'error');
            console.error('Failed to remove post:', error);
        }
    }
    
    async togglePost(postId) {
        try {
            const response = await fetch(`/api/posts/${postId}/toggle`, { method: 'PUT' });
            const data = await response.json();
            
            if (data.success) {
                this.loadPosts();
            } else {
                this.showToast('Failed to toggle post: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to toggle post: ' + error.message, 'error');
            console.error('Failed to toggle post:', error);
        }
    }
    
    // Communities Management
    async loadCommunities() {
        try {
            const response = await fetch('/api/communities');
            const data = await response.json();
            
            if (data.success) {
                this.renderCommunities(data.communities);
                this.updateCommunitySelect(data.communities);
            } else {
                this.showToast('Failed to load communities: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to load communities', 'error');
            console.error('Failed to load communities:', error);
        }
    }
    
    renderCommunities(communities) {
        const container = document.getElementById('communitiesList');
        
        if (communities.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-home"></i>
                    <p>No communities added yet</p>
                    <small>Click "Add Community" to get started</small>
                </div>
            `;
            return;
        }
        
        container.innerHTML = communities.map(community => `
            <div class="list-item">
                <div class="item-info">
                    <div class="item-title">${community.name}</div>
                    <div class="item-subtitle">${community.url}</div>
                </div>
                <div class="item-actions">
                    <span class="status-badge ${community.active ? 'active' : 'inactive'}">${community.active ? 'Active' : 'Inactive'}</span>
                    <button class="btn btn-outline btn-sm" onclick="app.toggleCommunity(${community.id})" title="Toggle active">
                        <i class="fas fa-toggle-${community.active ? 'on' : 'off'}"></i>
                    </button>
                    <button class="btn btn-danger btn-sm" onclick="app.removeCommunity(${community.id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    }
    
    updateCommunitySelect(communities) {
        const select = document.getElementById('communitySelect');
        
        if (communities.length === 0) {
            select.innerHTML = '<option value="">No communities available</option>';
            return;
        }
        
        const activeCommunities = communities.filter(c => c.active);
        select.innerHTML = '<option value="">Select community...</option>' +
            activeCommunities.map(community => 
                `<option value="${community.url}">${community.name}</option>`
            ).join('');
    }

    // --- Caption Management ---
    async loadCaptions() {
        try {
            const response = await fetch('/api/captions');
            const data = await response.json();
            if (data.success) {
                this.renderCaptions(data.captions);
            }
        } catch (error) {
            console.error('Failed to load captions:', error);
        }
    }

    renderCaptions(captions) {
        const container = document.getElementById('captionsList');
        if (!container) return;
        if (captions.length === 0) {
            container.innerHTML = `<div class="empty-state"><i class="fas fa-font"></i><p>No captions</p></div>`;
            return;
        }
        
        // Add delete all button at the top
        let html = `
            <div style="display: flex; justify-content: flex-end; margin-bottom: 10px;">
                <button class="btn btn-danger btn-sm" onclick="app.deleteAllCaptions()" title="Delete all captions">
                    <i class="fas fa-trash-alt"></i> Delete All
                </button>
            </div>
        `;
        
        html += captions.map(c => `
            <div class="list-item" style="display:flex; justify-content:space-between; align-items:center;">
                <div class="item-info">${c.content.substring(0, 50)}${c.content.length > 50 ? '...' : ''}</div>
                <button class="btn btn-danger btn-sm" onclick="app.deleteCaption(${c.id})"><i class="fas fa-trash"></i></button>
            </div>
        `).join('');
        
        container.innerHTML = html;
    }

    async deleteCaption(id) {
        if(!confirm('Delete caption?')) return;
        await fetch(`/api/captions/${id}`, { method: 'DELETE' });
        this.loadCaptions();
    }

    showAddCaptionModal() {
        this.showModal('Add Captions', `
            <div class="form-group">
                <label>Caption Content (One per line)</label>
                <textarea id="newCaptionContent" class="form-control" rows="8" placeholder="Enter one caption per line"></textarea>
                <small class="help-text">Each line will be saved as a separate caption.</small>
            </div>
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.addCaptionFromModal()">Add Captions</button>
        `);
    }

    async addCaptionFromModal() {
        const text = document.getElementById('newCaptionContent').value.trim();
        if(!text) return;
        
        const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
        
        for (const content of lines) {
            await fetch('/api/captions', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({content})
            });
        }
        
        this.hideModal();
        this.loadCaptions();
    }

    // --- Image Library Management ---
    async loadImageGroups() {
        try {
            const response = await fetch('/api/image-groups');
            const data = await response.json();
            if (data.success) {
                this.renderImageGroups(data.groups);
            }
        } catch (error) {
            console.error('Failed to load image groups:', error);
        }
    }

    renderImageGroups(groups) {
        const container = document.getElementById('imageGroupsList');
        if (!container) return;
        if (!groups || groups.length === 0) {
            container.innerHTML = `<div class="empty-state"><i class="fas fa-images"></i><p>No image groups</p></div>`;
            return;
        }
        
        // Add delete all button at the top
        let html = `
            <div style="display: flex; justify-content: flex-end; margin-bottom: 10px;">
                <button class="btn btn-danger btn-sm" onclick="app.deleteAllImageGroups()" title="Delete all image groups">
                    <i class="fas fa-trash-alt"></i> Delete All
                </button>
            </div>
        `;
        
        html += groups.map(g => {
            const imgCount = g.images ? g.images.length : 0;
            const imagesHtml = g.images ? g.images.slice(0, 5).map(imgPath => {
                const filename = imgPath.split(/[\\/]/).pop();
                return `<img src="/api/images/${filename}" style="width:30px;height:30px;object-fit:cover;border-radius:4px;margin-right:2px;display:inline-block;">`;
            }).join('') : '';
            
            return `
            <div class="list-item" style="display:flex; justify-content:space-between; align-items:center;">
                <div style="display:flex;align-items:center;gap:10px;">
                    <div style="display:flex; flex-wrap:wrap; max-width: 180px;">${imagesHtml}${imgCount > 5 ? `<span style="font-size:0.8em;color:#666;">+${imgCount-5}</span>` : ''}</div>
                    <span style="font-size: 0.9em; color: #666;">${imgCount} images</span>
                </div>
                <button class="btn btn-danger btn-sm" onclick="app.deleteImageGroup(${g.id})"><i class="fas fa-trash"></i></button>
            </div>
        `}).join('');
        
        container.innerHTML = html;
    }

    async deleteImageGroup(id) {
        if(!confirm('Delete image group?')) return;
        await fetch(`/api/image-groups/${id}`, { method: 'DELETE' });
        this.loadImageGroups();
    }

    showAddImageGroupModal() {
        this.showModal('Add Images', `
            <div class="form-group">
                <label>Select Images</label>
                <input type="file" id="newGroupImages" class="form-control" accept="image/*" multiple>
            </div>
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.addImageGroupFromModal()">Add</button>
        `);
    }

    async addImageGroupFromModal() {
        const fileInput = document.getElementById('newGroupImages');
        if(fileInput.files.length === 0) return;
        
        const formData = new FormData();
        for(let i=0; i<fileInput.files.length; i++) {
            formData.append('images', fileInput.files[i]);
        }

        await fetch('/api/image-groups', {
            method: 'POST',
            body: formData
        });
        this.hideModal();
        this.loadImageGroups();
    }
    
    showAddCommunityModal() {
        this.showModal('Add Community', `
            <form id="addCommunityForm">
                <div class="form-group">
                    <label for="communityName">Community Name</label>
                    <input type="text" id="communityName" class="form-control" 
                           placeholder="Enter a friendly name for this community" required>
                </div>
                <div class="form-group">
                    <label for="communityUrl">Community URL</label>
                    <input type="url" id="communityUrl" class="form-control" 
                           placeholder="https://twitter.com/i/communities/..." required>
                    <small class="help-text">Enter the full Twitter community URL</small>
                </div>
            </form>
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.addCommunityFromModal()">Add Community</button>
        `);
    }
    
    showBulkImportCommunitiesModal() {
        this.showModal('Bulk Import Communities', `
            <form id="bulkImportCommunitiesForm">
                <div class="form-group">
                    <label for="communitiesListBulk">Community URLs</label>
                    <textarea id="communitiesListBulk" class="form-control" rows="12" 
                              placeholder="Paste community URLs here, one per line:&#10;&#10;https://twitter.com/i/communities/1234567890&#10;https://x.com/i/communities/0987654321&#10;https://twitter.com/i/communities/1122334455"></textarea>
                    <small class="help-text">Enter one Twitter/X community URL per line. Empty lines and duplicates will be ignored.</small>
                </div>
                <div class="form-group">
                    <label class="checkbox-label">
                        <input type="checkbox" id="autoNameCommunities" checked> 
                        Auto-generate community names
                    </label>
                    <small class="help-text">Automatically create names like "Community 1", "Community 2", etc.</small>
                </div>
            </form>
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.bulkImportCommunities()">Import Communities</button>
        `);
    }
    
    async bulkImportCommunities() {
        const communitiesText = document.getElementById('communitiesListBulk').value.trim();
        const autoName = document.getElementById('autoNameCommunities').checked;
        
        if (!communitiesText) {
            this.showToast('Please enter community URLs', 'warning');
            return;
        }
        
        const lines = communitiesText.split('\n').map(line => line.trim()).filter(line => line);
        const validUrls = [];
        const invalidLines = [];
        
        // Validate URLs
        lines.forEach((line, index) => {
            if (line.includes('twitter.com/i/communities/') || line.includes('x.com/i/communities/')) {
                if (!validUrls.includes(line)) { // Avoid duplicates
                    validUrls.push(line);
                }
            } else {
                invalidLines.push(`Line ${index + 1}: ${line}`);
            }
        });
        
        if (validUrls.length === 0) {
            this.showToast('No valid community URLs found', 'error');
            return;
        }
        
        if (invalidLines.length > 0) {
            const proceed = confirm(`Found ${invalidLines.length} invalid URLs that will be skipped:\n\n${invalidLines.slice(0, 5).join('\n')}${invalidLines.length > 5 ? '\n...' : ''}\n\nProceed with ${validUrls.length} valid URLs?`);
            if (!proceed) return;
        }
        
        let imported = 0;
        let failed = 0;
        
        // Import each valid URL
        for (let i = 0; i < validUrls.length; i++) {
            const url = validUrls[i];
            const name = autoName ? `Community ${i + 1}` : `Community ${Date.now()}_${i}`;
            
            try {
                const response = await fetch('/api/communities', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, url })
                });
                
                const data = await response.json();
                if (data.success) {
                    imported++;
                } else {
                    failed++;
                    console.error(`Failed to import ${url}:`, data.error);
                }
            } catch (error) {
                failed++;
                console.error(`Error importing ${url}:`, error);
            }
        }
        
        this.showToast(`Import complete: ${imported} imported, ${failed} failed`, imported > 0 ? 'success' : 'warning');
        this.hideModal();
        this.loadCommunities();
        this.addLogEntry(`Bulk imported ${imported} communities`);
    }
    
    async addCommunityFromModal() {
        const name = document.getElementById('communityName').value.trim();
        const url = document.getElementById('communityUrl').value.trim();
        
        if (!name || !url) {
            this.showToast('Please enter both name and URL', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/communities', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, url })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Community added successfully', 'success');
                this.hideModal();
                this.loadCommunities();
            } else {
                this.showToast('Failed to add community: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to add community: ' + error.message, 'error');
            console.error('Failed to add community:', error);
        }
    }
    
    async removeCommunity(communityId) {
        if (!confirm('Are you sure you want to remove this community?')) {
            return;
        }
        
        try {
            const response = await fetch(`/api/communities/${communityId}`, { method: 'DELETE' });
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Community removed successfully', 'success');
                this.loadCommunities();
            } else {
                this.showToast('Failed to remove community: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to remove community: ' + error.message, 'error');
            console.error('Failed to remove community:', error);
        }
    }
    
    async toggleCommunity(communityId) {
        try {
            const response = await fetch(`/api/communities/${communityId}/toggle`, { method: 'PUT' });
            const data = await response.json();
            
            if (data.success) {
                this.loadCommunities();
            } else {
                this.showToast('Failed to toggle community: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to toggle community: ' + error.message, 'error');
            console.error('Failed to toggle community:', error);
        }
    }
    
    async removeAccount(username) {
        if (!confirm(`Are you sure you want to remove account @${username}?`)) {
            return;
        }
        
        try {
            const response = await fetch(`/api/accounts/${username}`, { method: 'DELETE' });
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Account removed successfully', 'success');
                this.loadAccounts();
                this.addLogEntry(`Account @${username} removed`);
            } else {
                this.showToast('Failed to remove account: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to remove account', 'error');
            console.error('Failed to remove account:', error);
        }
    }
    
    async toggleAccount(username) {
        try {
            const response = await fetch(`/api/accounts/${username}/toggle`, { method: 'PUT' });
            const data = await response.json();
            
            if (data.success) {
                this.showToast(data.message, 'success');
                this.loadAccounts();
                this.addLogEntry(`Account @${username} ${data.is_active ? 'activated' : 'deactivated'}`);
            } else {
                this.showToast('Failed to toggle account: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to toggle account', 'error');
            console.error('Failed to toggle account:', error);
        }
    }
    
    async deleteAllCaptions() {
        if (!confirm('Delete ALL captions? This cannot be undone!')) return;
        try {
            const response = await fetch('/api/captions/delete-all', { method: 'DELETE' });
            const data = await response.json();
            if (data.success) {
                this.showToast('All captions deleted', 'success');
                this.loadCaptions();
            }
        } catch (error) {
            this.showToast('Failed to delete all captions', 'error');
        }
    }
    
    async deleteAllImageGroups() {
        if (!confirm('Delete ALL image groups? This cannot be undone!')) return;
        try {
            const response = await fetch('/api/image-groups/delete-all', { method: 'DELETE' });
            const data = await response.json();
            if (data.success) {
                this.showToast('All image groups deleted', 'success');
                this.loadImageGroups();
            }
        } catch (error) {
            this.showToast('Failed to delete all image groups', 'error');
        }
    }
    
    // Content Pairing Management
    async loadContentPairs() {
        try {
            const response = await fetch('/api/content-pairs');
            const data = await response.json();
            if (data.success) {
                this.renderContentPairs(data.pairs);
            }
        } catch (error) {
            console.error('Failed to load content pairs:', error);
        }
    }
    
    renderContentPairs(pairs) {
        const container = document.getElementById('contentPairsList');
        if (!container) return;
        
        if (!pairs || pairs.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-link"></i>
                    <p>No content pairs created yet</p>
                    <small>Click "Create Pair" to link caption(s), photo, and account together</small>
                </div>
            `;
            return;
        }
        
        container.innerHTML = pairs.map(pair => {
            // Handle both old format (caption_id) and new format (caption_ids)
            let captionDisplay = 'Not set';
            if (pair.caption_ids && Array.isArray(pair.caption_ids)) {
                captionDisplay = `${pair.caption_ids.length} caption(s)`;
            } else if (pair.caption_id) {
                captionDisplay = `Caption ID: ${pair.caption_id}`;
            }
            
            return `
            <div class="list-item" style="display:flex; justify-content:space-between; align-items:center; padding: 15px;">
                <div class="item-info" style="flex: 1;">
                    <div style="display: flex; gap: 20px; align-items: center;">
                        <div style="flex: 1;">
                            <strong>Account:</strong> @${pair.account_username || 'Not set'}
                        </div>
                        <div style="flex: 1;">
                            <strong>Captions:</strong> ${captionDisplay}
                        </div>
                        <div style="flex: 1;">
                            <strong>Image Group ID:</strong> ${pair.image_group_id || 'Not set'}
                        </div>
                    </div>
                </div>
                <div class="item-actions">
                    <button class="btn btn-outline btn-sm" onclick="app.editContentPair(${pair.id})" title="Edit pair">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-danger btn-sm" onclick="app.deleteContentPair(${pair.id})" title="Delete pair">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `}).join('');
    }
    
    async showAddContentPairModal() {
        // Load all necessary data first
        const [captionsRes, imageGroupsRes, accountsRes] = await Promise.all([
            fetch('/api/captions'),
            fetch('/api/image-groups'),
            fetch('/api/accounts')
        ]);
        
        const captions = (await captionsRes.json()).captions || [];
        const imageGroups = (await imageGroupsRes.json()).groups || [];
        const accounts = (await accountsRes.json()).accounts || [];
        
        const captionOptions = captions.length > 0 
            ? captions.map(c => 
                `<option value="${c.id}">${c.content.substring(0, 50)}${c.content.length > 50 ? '...' : ''}</option>`
              ).join('')
            : '<option value="" disabled>No captions available</option>';
        
        const imageGroupOptions = imageGroups.length > 0
            ? '<option value="">Select image group...</option>' + imageGroups.map(g => 
                `<option value="${g.id}">Group ${g.id} (${g.images ? g.images.length : 0} images)</option>`
              ).join('')
            : '<option value="">No image groups available</option>';
        
        const accountOptions = accounts.length > 0
            ? '<option value="">Select account...</option>' + accounts.map(a => 
                `<option value="${a.username}">@${a.username}</option>`
              ).join('')
            : '<option value="">No accounts available</option>';
        
        this.showModal('Create Content Pair', `
            <form id="addContentPairForm">
                <div class="form-group">
                    <label for="pairAccount">Account</label>
                    <select id="pairAccount" class="form-control">
                        ${accountOptions}
                    </select>
                    <small class="help-text">Select the account that will use this content</small>
                </div>
                <div class="form-group">
                    <label for="pairCaptions">Captions (Multiple Selection)</label>
                    <select id="pairCaptions" class="form-control" multiple size="6" style="height: auto;">
                        ${captionOptions}
                    </select>
                    <small class="help-text">Hold Ctrl (Cmd on Mac) to select multiple captions. The bot will rotate through them.</small>
                </div>
                <div class="form-group">
                    <label for="pairImageGroup">Image Group</label>
                    <select id="pairImageGroup" class="form-control">
                        ${imageGroupOptions}
                    </select>
                    <small class="help-text">Select the image group for this pair</small>
                </div>
            </form>
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.addContentPairFromModal()">Create Pair</button>
        `);
    }
    
    async addContentPairFromModal() {
        const account = document.getElementById('pairAccount').value;
        const captionSelect = document.getElementById('pairCaptions');
        const selectedCaptions = Array.from(captionSelect.selectedOptions).map(opt => parseInt(opt.value));
        const imageGroup = document.getElementById('pairImageGroup').value;
        
        if (!account) {
            this.showToast('Please select an account', 'warning');
            return;
        }
        
        if (selectedCaptions.length === 0) {
            this.showToast('Please select at least one caption', 'warning');
            return;
        }
        
        if (!imageGroup) {
            this.showToast('Please select an image group', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/content-pairs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    account_username: account,
                    caption_ids: selectedCaptions,
                    image_group_id: parseInt(imageGroup)
                })
            });
            
            const data = await response.json();
            if (data.success) {
                this.showToast(`Content pair created with ${selectedCaptions.length} caption(s)`, 'success');
                this.hideModal();
                this.loadContentPairs();
            } else {
                this.showToast('Failed to create pair: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to create pair', 'error');
            console.error('Failed to create pair:', error);
        }
    }
    
    async deleteContentPair(pairId) {
        if (!confirm('Delete this content pair?')) return;
        
        try {
            const response = await fetch(`/api/content-pairs/${pairId}`, { method: 'DELETE' });
            const data = await response.json();
            if (data.success) {
                this.showToast('Content pair deleted', 'success');
                this.loadContentPairs();
            }
        } catch (error) {
            this.showToast('Failed to delete pair', 'error');
        }
    }
    
    async editContentPair(pairId) {
        // Load current pair data and all options
        const [pairRes, captionsRes, imageGroupsRes, accountsRes] = await Promise.all([
            fetch('/api/content-pairs'),
            fetch('/api/captions'),
            fetch('/api/image-groups'),
            fetch('/api/accounts')
        ]);
        
        const pairs = (await pairRes.json()).pairs || [];
        const pair = pairs.find(p => p.id === pairId);
        
        if (!pair) {
            this.showToast('Pair not found', 'error');
            return;
        }
        
        const captions = (await captionsRes.json()).captions || [];
        const imageGroups = (await imageGroupsRes.json()).groups || [];
        const accounts = (await accountsRes.json()).accounts || [];
        
        // Handle both old format (caption_id) and new format (caption_ids)
        let selectedCaptionIds = [];
        if (pair.caption_ids && Array.isArray(pair.caption_ids)) {
            selectedCaptionIds = pair.caption_ids;
        } else if (pair.caption_id) {
            selectedCaptionIds = [pair.caption_id];
        }
        
        const captionOptions = captions.map(c => {
            const isSelected = selectedCaptionIds.includes(c.id);
            return `<option value="${c.id}" ${isSelected ? 'selected' : ''}>${c.content.substring(0, 50)}${c.content.length > 50 ? '...' : ''}</option>`;
        }).join('');
        
        const imageGroupOptions = imageGroups.map(g => 
            `<option value="${g.id}" ${g.id === pair.image_group_id ? 'selected' : ''}>Group ${g.id} (${g.images ? g.images.length : 0} images)</option>`
        ).join('');
        
        const accountOptions = accounts.map(a => 
            `<option value="${a.username}" ${a.username === pair.account_username ? 'selected' : ''}>@${a.username}</option>`
        ).join('');
        
        this.showModal('Edit Content Pair', `
            <form id="editContentPairForm">
                <div class="form-group">
                    <label for="editPairAccount">Account</label>
                    <select id="editPairAccount" class="form-control">
                        ${accountOptions}
                    </select>
                </div>
                <div class="form-group">
                    <label for="editPairCaptions">Captions (Multiple Selection)</label>
                    <select id="editPairCaptions" class="form-control" multiple size="6" style="height: auto;">
                        ${captionOptions}
                    </select>
                    <small class="help-text">Hold Ctrl (Cmd on Mac) to select multiple captions. Currently selected: ${selectedCaptionIds.length}</small>
                </div>
                <div class="form-group">
                    <label for="editPairImageGroup">Image Group</label>
                    <select id="editPairImageGroup" class="form-control">
                        ${imageGroupOptions}
                    </select>
                </div>
            </form>
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.updateContentPairFromModal(${pairId})">Update Pair</button>
        `);
    }
    
    async updateContentPairFromModal(pairId) {
        const account = document.getElementById('editPairAccount').value;
        const captionSelect = document.getElementById('editPairCaptions');
        const selectedCaptions = Array.from(captionSelect.selectedOptions).map(opt => parseInt(opt.value));
        const imageGroup = document.getElementById('editPairImageGroup').value;
        
        if (selectedCaptions.length === 0) {
            this.showToast('Please select at least one caption', 'warning');
            return;
        }
        
        try {
            const response = await fetch(`/api/content-pairs/${pairId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    account_username: account,
                    caption_ids: selectedCaptions,
                    image_group_id: parseInt(imageGroup)
                })
            });
            
            const data = await response.json();
            if (data.success) {
                this.showToast(`Content pair updated with ${selectedCaptions.length} caption(s)`, 'success');
                this.hideModal();
                this.loadContentPairs();
            } else {
                this.showToast('Failed to update pair: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to update pair', 'error');
        }
    }
    
    showAddProxyModal() {
        this.showModal('Add Proxy', `
            <form id="addProxyForm">
                <div class="form-row">
                    <div class="form-group">
                        <label for="proxyHost">Host</label>
                        <input type="text" id="proxyHost" class="form-control" 
                               placeholder="127.0.0.1" required>
                    </div>
                    <div class="form-group">
                        <label for="proxyPort">Port</label>
                        <input type="number" id="proxyPort" class="form-control" 
                               placeholder="8080" required>
                    </div>
                </div>
                <div class="form-group">
                    <label for="proxyType">Type</label>
                    <select id="proxyType" class="form-control">
                        <option value="HTTP">HTTP</option>
                        <option value="HTTPS">HTTPS</option>
                        <option value="SOCKS4">SOCKS4</option>
                        <option value="SOCKS5">SOCKS5</option>
                    </select>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label for="proxyUsername">Username (optional)</label>
                        <input type="text" id="proxyUsername" class="form-control" 
                               placeholder="Username">
                    </div>
                    <div class="form-group">
                        <label for="proxyPassword">Password (optional)</label>
                        <input type="password" id="proxyPassword" class="form-control" 
                               placeholder="Password">
                    </div>
                </div>
            </form>
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.addProxy()">Add Proxy</button>
        `);
    }
    
    async addProxy() {
        const host = document.getElementById('proxyHost').value.trim();
        const port = document.getElementById('proxyPort').value.trim();
        const type = document.getElementById('proxyType').value;
        const username = document.getElementById('proxyUsername').value.trim();
        const password = document.getElementById('proxyPassword').value.trim();
        
        if (!host || !port) {
            this.showToast('Please enter host and port', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/proxies', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host, port: parseInt(port), type, username, password })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Proxy added successfully', 'success');
                this.hideModal();
                this.loadProxies();
                this.addLogEntry(`Proxy ${host}:${port} added`);
            } else {
                this.showToast('Failed to add proxy: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to add proxy: ' + error.message, 'error');
            console.error('Failed to add proxy:', error);
        }
    }
    
    async removeProxy(proxyId) {
        if (!confirm('Are you sure you want to remove this proxy?')) {
            return;
        }
        
        try {
            const response = await fetch(`/api/proxies/${proxyId}`, { method: 'DELETE' });
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Proxy removed successfully', 'success');
                this.loadProxies();
                this.addLogEntry(`Proxy removed`);
            } else {
                this.showToast('Failed to remove proxy: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to remove proxy', 'error');
            console.error('Failed to remove proxy:', error);
        }
    }
    
    async testProxy(proxyId) {
        this.showToast('Testing proxy...', 'info');
        
        try {
            const response = await fetch(`/api/proxies/${proxyId}/test`, { method: 'POST' });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                const status = data.status === 'working' ? 'success' : 'error';
                this.showToast(`Proxy test: ${data.status}`, status);
                this.loadProxies(); // Refresh to show updated status
            } else {
                this.showToast('Failed to test proxy: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to test proxy: ' + error.message, 'error');
            console.error('Failed to test proxy:', error);
        }
    }
    
    async testAllProxies() {
        this.showToast('Testing all proxies...', 'info');
        
        try {
            const response = await fetch('/api/proxies/test-all', { method: 'POST' });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast(data.message, 'success');
                this.loadProxies(); // Refresh to show updated statuses
                this.addLogEntry('All proxies tested');
            } else {
                this.showToast('Failed to test proxies: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to test proxies: ' + error.message, 'error');
            console.error('Failed to test proxies:', error);
        }
    }
    
    showImportProxiesModal() {
        this.showModal('Import Proxies', `
            <div class="form-group">
                <label for="proxyList">Proxy List</label>
                <textarea id="proxyList" class="form-control" rows="10" 
                          placeholder="Enter proxies in format: host:port:username:password (one per line)&#10;Example:&#10;127.0.0.1:8080&#10;192.168.1.1:3128:user:pass"></textarea>
            </div>
            <div class="form-group">
                <label for="importProxyType">Default Type</label>
                <select id="importProxyType" class="form-control">
                    <option value="HTTP">HTTP</option>
                    <option value="HTTPS">HTTPS</option>
                    <option value="SOCKS4">SOCKS4</option>
                    <option value="SOCKS5">SOCKS5</option>
                </select>
            </div>
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.importProxies()">Import Proxies</button>
        `);
    }
    
    async importProxies() {
        const proxyList = document.getElementById('proxyList').value.trim();
        const defaultType = document.getElementById('importProxyType').value;
        
        if (!proxyList) {
            this.showToast('Please enter proxy list', 'warning');
            return;
        }
        
        const lines = proxyList.split('\n').filter(line => line.trim());
        let imported = 0;
        let failed = 0;
        
        for (const line of lines) {
            const parts = line.trim().split(':');
            if (parts.length < 2) {
                failed++;
                continue;
            }
            
            const [host, port, username, password] = parts;
            
            try {
                const response = await fetch('/api/proxies', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        host,
                        port: parseInt(port),
                        type: defaultType,
                        username: username || '',
                        password: password || ''
                    })
                });
                
                const data = await response.json();
                if (data.success) {
                    imported++;
                } else {
                    failed++;
                }
            } catch (error) {
                failed++;
            }
        }
        
        this.showToast(`Import complete: ${imported} imported, ${failed} failed`, 'info');
        this.hideModal();
        this.loadProxies();
        this.addLogEntry(`Imported ${imported} proxies`);
    }
    
    async addToQueue() {
        const communitySelect = document.getElementById('communitySelect');
        const communityUrl = communitySelect.value.trim();
        const account = document.getElementById('accountSelect').value;
        const content = document.getElementById('postContent').value.trim();
        
        if (!account || !content) {
            this.showToast('Please select an account and enter post content', 'warning');
            return;
        }
        
        // TODO: Implement queue functionality
        this.showToast('Post added to queue (feature coming soon)', 'info');
        this.addLogEntry(`Post queued for @${account}`);
    }
    
    async postNow() {
        const communitySelect = document.getElementById('communitySelect');
        const communityUrl = communitySelect.value.trim();
        const account = document.getElementById('accountSelect').value;
        const content = document.getElementById('postContent').value.trim();
        const imageInput = document.getElementById('imageUpload');
        
        if (!account || !content) {
            this.showToast('Please select an account and enter post content', 'warning');
            return;
        }
        
        // Confirm before posting
        const confirmMessage = `Post "${content.substring(0, 50)}${content.length > 50 ? '...' : ''}" immediately using @${account}?`;
        if (!confirm(confirmMessage)) {
            return;
        }
        
        try {
            // Show loading state
            const postButton = document.getElementById('postNow');
            const originalText = postButton.innerHTML;
            postButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Posting...';
            postButton.disabled = true;
            
            // Prepare form data
            const formData = new FormData();
            formData.append('content', content);
            formData.append('account', account);
            
            if (communityUrl) {
                formData.append('community_url', communityUrl);
            }
            
            // Add images if selected
            if (this.quickPostFiles.length > 0) {
                this.quickPostFiles.forEach(file => {
                    formData.append('images', file);
                });
            }
            
            // Make the API call
            const response = await fetch('/api/post-now', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast(data.message, 'success');
                this.addLogEntry(`✓ ${data.message}`);
                
                // Clear the form
                document.getElementById('postContent').value = '';
                document.getElementById('communitySelect').value = '';
                document.getElementById('imageUpload').value = '';
                this.quickPostFiles = [];
                
                // Update preview
                this.updateImagePreview();
                
            } else {
                this.showToast('Failed to post: ' + data.error, 'error');
                this.addLogEntry(`✗ Post failed: ${data.error}`);
            }
            
        } catch (error) {
            console.error('Error posting now:', error);
            this.showToast('Network error while posting', 'error');
            this.addLogEntry(`✗ Network error: ${error.message}`);
        } finally {
            // Restore button state
            const postButton = document.getElementById('postNow');
            postButton.innerHTML = originalText;
            postButton.disabled = false;
        }
    }
    
    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const data = await response.json();
            
            if (data.success) {
                this.renderConfig(data.config);
                
                // Also load concurrent browsers config from the dedicated endpoint
                try {
                    const concurrentResponse = await fetch('/api/config/concurrent-browsers');
                    if (concurrentResponse.ok) {
                        const concurrentData = await concurrentResponse.json();
                        const concurrentBrowsers = concurrentData.max_concurrent_browsers || 1;
                        document.getElementById('maxConcurrentBrowsers').value = concurrentBrowsers;
                        this.updateConcurrentBrowsersDisplay(concurrentBrowsers);
                    }
                } catch (concurrentError) {
                    console.warn('Failed to load concurrent browsers config:', concurrentError);
                    // Use default value
                    this.updateConcurrentBrowsersDisplay(1);
                }
            } else {
                this.showToast('Failed to load config: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to load config', 'error');
            console.error('Failed to load config:', error);
        }
    }
    
    renderConfig(config) {
        // Update form fields with config values - stealth mode enabled by default
        document.getElementById('headlessDefault').checked = config.browser_settings?.headless || false;
        document.getElementById('autoSave').checked = config.session_settings?.auto_save !== false; // Default true
        document.getElementById('stealthMode').checked = config.stealth_settings?.enabled !== false; // Default true
        document.getElementById('useProxiesDefault').checked = config.proxy_settings?.use_by_default !== false; // Default true
        
        // Scheduler settings
        document.getElementById('randomnessPercent').value = config.posting_intervals?.randomness_percent || 25;
        document.getElementById('refreshCookies').checked = config.stealth_settings?.auto_refresh_cookies !== false; // Default true
        document.getElementById('maxRetries').value = config.error_handling?.max_retries || 3;
        
        // Concurrent browsers setting
        document.getElementById('maxConcurrentBrowsers').value = config.browser_settings?.max_concurrent_browsers || 1;
        this.updateConcurrentBrowsersDisplay(config.browser_settings?.max_concurrent_browsers || 1);
    }
    
    async saveConfig() {
        const config = {
            browser_settings: {
                headless: document.getElementById('headlessDefault').checked,
                max_concurrent_browsers: parseInt(document.getElementById('maxConcurrentBrowsers').value) || 1
            },
            session_settings: {
                auto_save: document.getElementById('autoSave').checked
            },
            stealth_settings: {
                enabled: document.getElementById('stealthMode').checked,
                auto_refresh_cookies: document.getElementById('refreshCookies').checked,
                fingerprint_consistency: true // Always enabled for security
            },
            posting_intervals: {
                // Use value from the main scheduler input on dashboard
                default: parseInt(document.getElementById('postingInterval').value) || 3600,
                randomness_percent: parseInt(document.getElementById('randomnessPercent').value) || 25
            },
            error_handling: {
                max_retries: parseInt(document.getElementById('maxRetries').value) || 3
            },
            proxy_settings: {
                use_by_default: document.getElementById('useProxiesDefault').checked
            }
        };
        
        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showToast('Configuration saved successfully', 'success');
                this.addLogEntry('Configuration updated');
                
                // Update concurrent browsers display after successful save
                const concurrentBrowsers = parseInt(document.getElementById('maxConcurrentBrowsers').value) || 1;
                this.updateConcurrentBrowsersDisplay(concurrentBrowsers);
            } else {
                this.showToast('Failed to save config: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to save config', 'error');
            console.error('Failed to save config:', error);
        }
    }
    
    resetConfig() {
        if (!confirm('Are you sure you want to reset configuration to defaults?')) {
            return;
        }
        
        // Set secure defaults
        document.getElementById('headlessDefault').checked = false;
        document.getElementById('autoSave').checked = true; // Default enabled
        document.getElementById('stealthMode').checked = true; // Default enabled
        document.getElementById('useProxiesDefault').checked = true; // Default enabled
        document.getElementById('randomnessPercent').value = 25;
        document.getElementById('refreshCookies').checked = true; // Default enabled
        document.getElementById('maxRetries').value = 3;
        document.getElementById('maxConcurrentBrowsers').value = 1; // Default to 1 browser
        
        // Update concurrent browsers display
        this.updateConcurrentBrowsersDisplay(1);
        
        this.showToast('Configuration reset to secure defaults', 'info');
    }
    
    clearLog() {
        const logContainer = document.getElementById('logContainer');
        if (!logContainer) {
            console.log('Log cleared (no log container found)');
            this.showToast('Log cleared', 'info');
            return;
        }
        
        logContainer.innerHTML = `
            <div class="log-entry">
                <span class="log-time">${new Date().toLocaleTimeString()}</span>
                <span class="log-message">Log cleared</span>
            </div>
        `;
        this.showToast('Log cleared', 'info');
    }
    
    async refreshData() {
        this.showToast('Refreshing data...', 'info');
        await this.loadInitialData();
        
        // Also refresh dashboard data if dashboard manager exists
        if (this.dashboardManager && this.dashboardManager.loadDashboardData) {
            await this.dashboardManager.loadDashboardData();
        }
        
        this.showToast('Data refreshed successfully', 'success');
    }
    
    addLogEntry(message, level = 'info') {
        const logContainer = document.getElementById('logContainer');
        
        // If no log container exists, just log to console
        if (!logContainer) {
            console.log(`[${level.toUpperCase()}] ${message}`);
            return;
        }
        
        const entry = document.createElement('div');
        entry.className = `log-entry log-${level}`;
        entry.innerHTML = `
            <span class="log-time">${new Date().toLocaleTimeString()}</span>
            <span class="log-message">${message}</span>
        `;
        logContainer.insertBefore(entry, logContainer.firstChild);
        
        // Keep only last 50 entries
        while (logContainer.children.length > 50) {
            logContainer.removeChild(logContainer.lastChild);
        }
    }
    
    showModal(title, body, footer = '', allowOutsideClose = true) {
        document.getElementById('modalTitle').textContent = title;
        document.getElementById('modalBody').innerHTML = body;
        document.getElementById('modalFooter').innerHTML = footer;
        
        const modal = document.getElementById('modal');
        modal.classList.add('show');
        
        // Set data attribute to control outside click behavior
        modal.setAttribute('data-allow-outside-close', allowOutsideClose.toString());
    }
    
    hideModal() {
        document.getElementById('modal').classList.remove('show');
    }
    
    handleModalOverlayClick(event) {
        const modal = document.getElementById('modal');
        const allowOutsideClose = modal.getAttribute('data-allow-outside-close') !== 'false';
        
        if (allowOutsideClose && event.target.classList.contains('modal-overlay')) {
            this.hideModal();
        }
    }
    
    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span>${message}</span>
            <button class="toast-close">&times;</button>
        `;
        
        container.appendChild(toast);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 5000);
        
        // Manual close
        toast.querySelector('.toast-close').addEventListener('click', () => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        });
    }
    
    // Image handling methods
    handleImageUpload(event) {
        const files = Array.from(event.target.files);
        if (this.quickPostFiles.length + files.length > 4) {
            this.showToast('Maximum 4 images allowed per post', 'warning');
            const remainingSlots = 4 - this.quickPostFiles.length;
            if (remainingSlots > 0) {
                this.quickPostFiles.push(...files.slice(0, remainingSlots));
            }
        } else {
            this.quickPostFiles.push(...files);
        }
        
        // Clear value to allow re-selecting same file
        event.target.value = '';
        this.updateImagePreview();
    }
    
    updateImagePreview() {
        const preview = document.getElementById('imagePreview');
        if (!preview) return;
        
        // Clear preview
        preview.innerHTML = '';
        
        if (this.quickPostFiles.length === 0) {
            preview.classList.remove('has-images');
            preview.innerHTML = `
                <div class="image-preview-placeholder">
                    <i class="fas fa-images"></i>
                    <span>No images selected</span>
                </div>
            `;
            return;
        }
        
        preview.classList.add('has-images');
        
        // Show preview for each file
        this.quickPostFiles.forEach((file, index) => {
            if (file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const previewItem = document.createElement('div');
                    previewItem.className = 'image-preview-item';
                    previewItem.innerHTML = `
                        <img src="${e.target.result}" alt="Preview ${index + 1}">
                        <button type="button" class="image-preview-remove" onclick="app.removeImage(${index})" title="Remove image">
                            ×
                        </button>
                    `;
                    preview.appendChild(previewItem);
                };
                reader.readAsDataURL(file);
            }
        });
    }
    
    removeImage(index) {
        this.quickPostFiles.splice(index, 1);
        this.updateImagePreview();
    }
    
    // Concurrent browsers display update method
    updateConcurrentBrowsersDisplay(value) {
        // Update current setting display
        const currentElement = document.getElementById('currentConcurrentBrowsers');
        if (currentElement) {
            currentElement.textContent = `${value}`;
        }
        
        // Update recommendation based on value
        const recommendationElement = document.getElementById('concurrentBrowsersRecommendation');
        if (recommendationElement) {
            let recommendation = '';
            
            if (value === 1) {
                recommendation = 'Conservative mode - lowest resource usage, most stable';
            } else if (value <= 3) {
                recommendation = `Balanced mode - ${value}x faster posting, moderate resource usage`;
            } else {
                recommendation = `Aggressive mode - ${value}x faster posting, high resource usage`;
            }
            
            recommendationElement.textContent = recommendation;
        }
        
        // Update dashboard manager if it exists
        if (this.dashboardManager && this.dashboardManager.updateConcurrentBrowsersDisplay) {
            this.dashboardManager.currentConcurrentBrowsers = value;
            this.dashboardManager.updateConcurrentBrowsersDisplay();
        }
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    try {
        console.log('Initializing Xbot Web Interface...');
        window.app = new XbotWebInterface();
        console.log('Xbot Web Interface initialized successfully');
    } catch (error) {
        console.error('Failed to initialize Xbot Web Interface:', error);
        // Show error message to user
        document.body.innerHTML = `
            <div style="padding: 20px; background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; border-radius: 5px; margin: 20px;">
                <h3>Application Error</h3>
                <p>Failed to initialize the web interface. Please refresh the page.</p>
                <p><strong>Error:</strong> ${error.message}</p>
                <button onclick="location.reload()" style="padding: 10px 20px; background: #dc3545; color: white; border: none; border-radius: 3px; cursor: pointer;">
                    Refresh Page
                </button>
            </div>
        `;
    }
});

// Add global error handler
window.addEventListener('error', (event) => {
    console.error('Global JavaScript error:', event.error);
});

// Add unhandled promise rejection handler
window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
});
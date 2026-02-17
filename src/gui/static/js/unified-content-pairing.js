/**
 * Unified Content Pairing Management
 * Handles captions + accounts + communities + image groups pairing
 */

// Wait for DOM and app to be ready
document.addEventListener('DOMContentLoaded', () => {
    // Add methods to XbotWebInterface prototype after app is created
    if (typeof XbotWebInterface !== 'undefined') {
        Object.assign(XbotWebInterface.prototype, {
    // Unified Content Pairing Management
    async loadUnifiedContentPairing() {
        try {
            const response = await fetch('/api/content-pairing');
            const data = await response.json();
            if (data.success) {
                this.renderUnifiedContentPairing(data.pairing);
            }
        } catch (error) {
            console.error('Failed to load unified content pairing:', error);
        }
    },
    
    renderUnifiedContentPairing(pairings) {
        const container = document.getElementById('unifiedContentPairingList');
        if (!container) return;
        
        if (!pairings || pairings.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-link"></i>
                    <p>No content pairings created yet</p>
                    <small>Click "Create Pairing" to link captions, accounts, communities, and images together</small>
                </div>
            `;
            return;
        }
        
        container.innerHTML = pairings.map(pairing => {
            const captionCount = pairing.caption_ids && pairing.caption_ids.length > 0 
                ? `${pairing.caption_ids.length} caption(s)` 
                : 'No captions';
            const accountCount = pairing.accounts && pairing.accounts.length > 0 
                ? `${pairing.accounts.length} account(s)` 
                : 'No accounts';
            const communityCount = pairing.communities && pairing.communities.length > 0 
                ? `${pairing.communities.length} community(ies)` 
                : 'All communities';
            const imageGroupCount = pairing.image_groups && pairing.image_groups.length > 0 
                ? `${pairing.image_groups.length} image group(s)` 
                : 'Text-only';
            
            return `
            <div class="list-item" style="display:flex; justify-content:space-between; align-items:center; padding: 15px; margin-bottom: 10px; border: 1px solid #ddd; border-radius: 4px;">
                <div class="item-info" style="flex: 1;">
                    <div style="margin-bottom: 8px;">
                        <strong style="font-size: 16px;">${pairing.name || 'Unnamed Pairing'}</strong>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; font-size: 14px;">
                        <div>
                            <i class="fas fa-font"></i> <strong>Captions:</strong> ${captionCount}
                        </div>
                        <div>
                            <i class="fas fa-users"></i> <strong>Accounts:</strong> ${accountCount}
                        </div>
                        <div>
                            <i class="fas fa-home"></i> <strong>Communities:</strong> ${communityCount}
                        </div>
                        <div>
                            <i class="fas fa-images"></i> <strong>Images:</strong> ${imageGroupCount}
                        </div>
                    </div>
                </div>
                <div class="item-actions">
                    <button class="btn btn-outline btn-sm" onclick="app.editUnifiedContentPairing(${pairing.id})" title="Edit pairing">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-danger btn-sm" onclick="app.deleteUnifiedContentPairing(${pairing.id})" title="Delete pairing">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `}).join('');
    },
    
    async showAddUnifiedContentPairingModal() {
        // Load all necessary data
        const [captionsRes, imageGroupsRes, accountsRes, communitiesRes] = await Promise.all([
            fetch('/api/captions'),
            fetch('/api/image-groups'),
            fetch('/api/accounts'),
            fetch('/api/communities')
        ]);
        
        const captions = (await captionsRes.json()).captions || [];
        const imageGroups = (await imageGroupsRes.json()).groups || [];
        const accounts = (await accountsRes.json()).accounts || [];
        const communitiesData = (await communitiesRes.json()).communities || [];
        
        // Extract all community URLs from the flat array
        const allCommunities = communitiesData.map(c => c.url).filter(url => url);
        
        const captionOptions = captions.length > 0 
            ? captions.map(c => 
                `<option value="${c.id}">${c.content.substring(0, 60)}${c.content.length > 60 ? '...' : ''}</option>`
              ).join('')
            : '<option value="" disabled>No captions available</option>';
        
        const imageGroupOptions = imageGroups.length > 0
            ? imageGroups.map(g => 
                `<option value="${g.name}">${g.name} (${g.images ? g.images.length : 0} images)</option>`
              ).join('')
            : '<option value="" disabled>No image groups available</option>';
        
        const accountOptions = accounts.length > 0
            ? accounts.map(a => 
                `<option value="${a.username}">@${a.username}</option>`
              ).join('')
            : '<option value="" disabled>No accounts available</option>';
        
        const communityOptions = allCommunities.length > 0
            ? allCommunities.map((url, idx) => {
                const shortName = url.split('/').pop();
                return `<option value="${url}">${shortName}</option>`;
              }).join('')
            : '<option value="" disabled>No communities available</option>';
        
        this.showModal('Create Content Pairing', `
            <form id="addUnifiedPairingForm">
                <div class="form-group">
                    <label for="pairingName">Pairing Name</label>
                    <input type="text" id="pairingName" class="form-control" placeholder="e.g., Tech Posts for Account1">
                    <small class="help-text">Give this pairing a descriptive name</small>
                </div>
                
                <div class="form-group">
                    <label for="pairingCaptions">Captions (Multiple Selection)</label>
                    <select id="pairingCaptions" class="form-control" multiple size="6" style="height: auto;">
                        ${captionOptions}
                    </select>
                    <small class="help-text">Hold Ctrl (Cmd on Mac) to select multiple captions</small>
                </div>
                
                <div class="form-group">
                    <label for="pairingAccounts">Accounts (Multiple Selection)</label>
                    <select id="pairingAccounts" class="form-control" multiple size="4" style="height: auto;">
                        ${accountOptions}
                    </select>
                    <small class="help-text">Select accounts that will use this content</small>
                </div>
                
                <div class="form-group">
                    <label for="pairingCommunities">Communities (Multiple Selection - Leave empty for all)</label>
                    <select id="pairingCommunities" class="form-control" multiple size="6" style="height: auto;">
                        ${communityOptions}
                    </select>
                    <small class="help-text">Select specific communities, or leave empty to post to all communities</small>
                </div>
                
                <div class="form-group">
                    <label for="pairingImageGroups">Image Groups (Multiple Selection - Leave empty for text-only)</label>
                    <select id="pairingImageGroups" class="form-control" multiple size="4" style="height: auto;">
                        ${imageGroupOptions}
                    </select>
                    <small class="help-text">Select image groups, or leave empty for text-only posts</small>
                </div>
            </form>
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.saveUnifiedContentPairing()">Create Pairing</button>
        `);
    },
    
    async saveUnifiedContentPairing() {
        const name = document.getElementById('pairingName').value.trim();
        const captionSelect = document.getElementById('pairingCaptions');
        const accountSelect = document.getElementById('pairingAccounts');
        const communitySelect = document.getElementById('pairingCommunities');
        const imageGroupSelect = document.getElementById('pairingImageGroups');
        
        const selectedCaptions = Array.from(captionSelect.selectedOptions).map(opt => parseInt(opt.value));
        const selectedAccounts = Array.from(accountSelect.selectedOptions).map(opt => opt.value);
        const selectedCommunities = Array.from(communitySelect.selectedOptions).map(opt => opt.value);
        const selectedImageGroups = Array.from(imageGroupSelect.selectedOptions).map(opt => opt.value);
        
        if (!name) {
            this.showToast('Please enter a pairing name', 'warning');
            return;
        }
        
        if (selectedCaptions.length === 0) {
            this.showToast('Please select at least one caption', 'warning');
            return;
        }
        
        if (selectedAccounts.length === 0) {
            this.showToast('Please select at least one account', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/content-pairing', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    caption_ids: selectedCaptions,
                    accounts: selectedAccounts,
                    communities: selectedCommunities,
                    image_groups: selectedImageGroups
                })
            });
            
            const data = await response.json();
            if (data.success) {
                this.showToast(`Content pairing "${name}" created successfully`, 'success');
                this.hideModal();
                this.loadUnifiedContentPairing();
            } else {
                this.showToast('Failed to create pairing: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to create pairing', 'error');
            console.error('Failed to create pairing:', error);
        }
    },
    
    async editUnifiedContentPairing(pairingId) {
        // Load current pairing and all options
        const [pairingRes, captionsRes, imageGroupsRes, accountsRes, communitiesRes] = await Promise.all([
            fetch('/api/content-pairing'),
            fetch('/api/captions'),
            fetch('/api/image-groups'),
            fetch('/api/accounts'),
            fetch('/api/communities')
        ]);
        
        const pairings = (await pairingRes.json()).pairing || [];
        const pairing = pairings.find(p => p.id === pairingId);
        
        if (!pairing) {
            this.showToast('Pairing not found', 'error');
            return;
        }
        
        const captions = (await captionsRes.json()).captions || [];
        const imageGroups = (await imageGroupsRes.json()).groups || [];
        const accounts = (await accountsRes.json()).accounts || [];
        const communitiesData = (await communitiesRes.json()).communities || [];
        
        // Extract all community URLs from the flat array
        const allCommunities = communitiesData.map(c => c.url).filter(url => url);
        
        const selectedCaptionIds = pairing.caption_ids || [];
        const selectedAccounts = pairing.accounts || [];
        const selectedCommunities = pairing.communities || [];
        const selectedImageGroups = pairing.image_groups || [];
        
        const captionOptions = captions.map(c => {
            const isSelected = selectedCaptionIds.includes(c.id);
            return `<option value="${c.id}" ${isSelected ? 'selected' : ''}>${c.content.substring(0, 60)}${c.content.length > 60 ? '...' : ''}</option>`;
        }).join('');
        
        const imageGroupOptions = imageGroups.map(g => {
            const isSelected = selectedImageGroups.includes(g.name);
            return `<option value="${g.name}" ${isSelected ? 'selected' : ''}>${g.name} (${g.images ? g.images.length : 0} images)</option>`;
        }).join('');
        
        const accountOptions = accounts.map(a => {
            const isSelected = selectedAccounts.includes(a.username);
            return `<option value="${a.username}" ${isSelected ? 'selected' : ''}>@${a.username}</option>`;
        }).join('');
        
        const communityOptions = allCommunities.map((url, idx) => {
            const shortName = url.split('/').pop();
            const isSelected = selectedCommunities.includes(url);
            return `<option value="${url}" ${isSelected ? 'selected' : ''}>${shortName}</option>`;
        }).join('');
        
        this.showModal('Edit Content Pairing', `
            <form id="editUnifiedPairingForm">
                <div class="form-group">
                    <label for="editPairingName">Pairing Name</label>
                    <input type="text" id="editPairingName" class="form-control" value="${pairing.name || ''}">
                </div>
                
                <div class="form-group">
                    <label for="editPairingCaptions">Captions (Multiple Selection)</label>
                    <select id="editPairingCaptions" class="form-control" multiple size="6" style="height: auto;">
                        ${captionOptions}
                    </select>
                    <small class="help-text">Currently selected: ${selectedCaptionIds.length}</small>
                </div>
                
                <div class="form-group">
                    <label for="editPairingAccounts">Accounts (Multiple Selection)</label>
                    <select id="editPairingAccounts" class="form-control" multiple size="4" style="height: auto;">
                        ${accountOptions}
                    </select>
                    <small class="help-text">Currently selected: ${selectedAccounts.length}</small>
                </div>
                
                <div class="form-group">
                    <label for="editPairingCommunities">Communities (Multiple Selection - Leave empty for all)</label>
                    <select id="editPairingCommunities" class="form-control" multiple size="6" style="height: auto;">
                        ${communityOptions}
                    </select>
                    <small class="help-text">Currently selected: ${selectedCommunities.length || 'All communities'}</small>
                </div>
                
                <div class="form-group">
                    <label for="editPairingImageGroups">Image Groups (Multiple Selection - Leave empty for text-only)</label>
                    <select id="editPairingImageGroups" class="form-control" multiple size="4" style="height: auto;">
                        ${imageGroupOptions}
                    </select>
                    <small class="help-text">Currently selected: ${selectedImageGroups.length || 'Text-only'}</small>
                </div>
            </form>
        `, `
            <button class="btn btn-outline" onclick="app.hideModal()">Cancel</button>
            <button class="btn btn-primary" onclick="app.updateUnifiedContentPairing(${pairingId})">Update Pairing</button>
        `);
    },
    
    async updateUnifiedContentPairing(pairingId) {
        const name = document.getElementById('editPairingName').value.trim();
        const captionSelect = document.getElementById('editPairingCaptions');
        const accountSelect = document.getElementById('editPairingAccounts');
        const communitySelect = document.getElementById('editPairingCommunities');
        const imageGroupSelect = document.getElementById('editPairingImageGroups');
        
        const selectedCaptions = Array.from(captionSelect.selectedOptions).map(opt => parseInt(opt.value));
        const selectedAccounts = Array.from(accountSelect.selectedOptions).map(opt => opt.value);
        const selectedCommunities = Array.from(communitySelect.selectedOptions).map(opt => opt.value);
        const selectedImageGroups = Array.from(imageGroupSelect.selectedOptions).map(opt => opt.value);
        
        if (!name) {
            this.showToast('Please enter a pairing name', 'warning');
            return;
        }
        
        if (selectedCaptions.length === 0) {
            this.showToast('Please select at least one caption', 'warning');
            return;
        }
        
        if (selectedAccounts.length === 0) {
            this.showToast('Please select at least one account', 'warning');
            return;
        }
        
        try {
            const response = await fetch(`/api/content-pairing/${pairingId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    caption_ids: selectedCaptions,
                    accounts: selectedAccounts,
                    communities: selectedCommunities,
                    image_groups: selectedImageGroups
                })
            });
            
            const data = await response.json();
            if (data.success) {
                this.showToast(`Content pairing "${name}" updated successfully`, 'success');
                this.hideModal();
                this.loadUnifiedContentPairing();
            } else {
                this.showToast('Failed to update pairing: ' + data.error, 'error');
            }
        } catch (error) {
            this.showToast('Failed to update pairing', 'error');
            console.error('Failed to update pairing:', error);
        }
    },
    
    async deleteUnifiedContentPairing(pairingId) {
        if (!confirm('Delete this content pairing?')) return;
        
        try {
            const response = await fetch(`/api/content-pairing/${pairingId}`, { method: 'DELETE' });
            const data = await response.json();
            if (data.success) {
                this.showToast('Content pairing deleted', 'success');
                this.loadUnifiedContentPairing();
            }
        } catch (error) {
            this.showToast('Failed to delete pairing', 'error');
        }
    }
        });
    } else {
        console.error('XbotWebInterface not found - unified content pairing methods not loaded');
    }
});

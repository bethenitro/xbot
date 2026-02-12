"""
Web-based GUI server for Enhanced Twitter Bot using Flask.
"""

import os
import json
import asyncio
import threading
import logging
import random
import time
import base64
import mimetypes
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
import os

from src.proxy.proxy_manager import ProxyManager
from src.account.account_manager import AccountManager


class BrowserEventLoop:
    """
    Manages a persistent event loop in a background thread for browser operations.
    
    ZenDriver/nodriver requires the event loop to remain active for the browser
    to stay open. This class provides a dedicated background thread with its own
    event loop that persists for the lifetime of browser sessions.
    """
    
    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self._running = False
        self.logger = logging.getLogger(__name__)
    
    def start(self):
        """Start the background event loop thread."""
        if self._running:
            return
        
        self._running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
        # Wait for the loop to be ready
        while self.loop is None:
            import time
            time.sleep(0.01)
        
        self.logger.info("Browser event loop started in background thread")
    
    def _run_loop(self):
        """Run the event loop in the background thread."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
    
    def run_coroutine(self, coro):
        """
        Run a coroutine in the background event loop.
        
        This method is thread-safe and can be called from any thread.
        The coroutine will run in the background event loop thread.
        """
        if not self._running or self.loop is None:
            self.start()
        
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()  # Block until complete
    
    def run_coroutine_async(self, coro):
        """
        Schedule a coroutine in the background event loop without waiting.
        
        Returns a Future that can be used to check completion status.
        """
        if not self._running or self.loop is None:
            self.start()
        
        return asyncio.run_coroutine_threadsafe(coro, self.loop)
    
    def stop(self):
        """Stop the background event loop."""
        if self.loop and self._running:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._running = False
            if self.thread:
                self.thread.join(timeout=5)
            self.logger.info("Browser event loop stopped")


# Global browser event loop instance
browser_event_loop = BrowserEventLoop()


class WebGUIServer:
    """Web-based GUI server using Flask."""
    
    def __init__(self, config: Dict):
        """Initialize web GUI server."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Ensure data directory exists
        Path("data").mkdir(exist_ok=True)
        Path("sessions").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)
        Path("data/images").mkdir(exist_ok=True)  # For uploaded images
        
        # Initialize managers
        self.proxy_manager = ProxyManager(config)
        self.account_manager = AccountManager(config)
        
        # Initialize post manager (will be set by main application)
        self.post_manager = None
        
        # Bot state
        self.is_running = False
        self.current_operation = None
        
        # Pending account logins
        self.pending_accounts = {}
        
        # Callbacks for bot operations
        self.start_callback: Optional = None
        self.stop_callback: Optional = None
        self.pause_callback: Optional = None
        
        # Create Flask app
        self.app = Flask(__name__, 
                        template_folder=str(Path(__file__).parent / "templates"),
                        static_folder=str(Path(__file__).parent / "static"))
        CORS(self.app)
        
        # Initialize SocketIO
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        
        # Setup routes and socket events
        self.setup_routes()
        self.setup_socket_events()
    
    def setup_routes(self):
        """Setup Flask routes."""
        
        @self.app.route('/')
        def index():
            """Main dashboard page."""
            return render_template('index.html')
        
        @self.app.route('/api/images/<filename>')
        def serve_image(filename):
            """Serve images from data/images directory."""
            try:
                # Use absolute path for images directory
                images_dir = os.path.abspath("data/images")
                if not os.path.exists(images_dir):
                    os.makedirs(images_dir, exist_ok=True)
                
                # Check if file exists before trying to serve it
                file_path = os.path.join(images_dir, filename)
                self.logger.info(f"Attempting to serve image: {filename}, full path: {file_path}")
                
                if not os.path.exists(file_path):
                    self.logger.error(f"Image file not found: {file_path}")
                    return jsonify({'error': 'Image not found'}), 404
                
                self.logger.info(f"Image file found, serving: {file_path}")
                # Use absolute path for send_from_directory
                return send_from_directory(images_dir, filename)
            except Exception as e:
                self.logger.error(f"Error serving image {filename}: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                return jsonify({'error': 'Internal server error'}), 500
        
        @self.app.route('/api/status')
        def get_status():
            """Get bot status and statistics."""
            try:
                account_stats = self.account_manager.get_account_stats()
                proxy_stats = self.proxy_manager.get_proxy_stats()
                
                return jsonify({
                    'success': True,
                    'status': 'running' if self.is_running else 'stopped',
                    'stats': {
                        'accounts': account_stats.get('total', 0),
                        'proxies': proxy_stats.get('total', 0),
                        'queue': 0,  # TODO: Implement queue stats
                        'success_rate': '0%'  # TODO: Implement success rate
                    }
                })
            except Exception as e:
                self.logger.error(f"Error getting status: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/browser/status')
        def get_browser_status():
            """Get browser status - ZenDriver only."""
            try:
                from src.browser.browser_factory import browser_factory
                available_browsers = browser_factory.get_available_browsers()
                
                return jsonify({
                    'success': True,
                    'selected': True,
                    'selected_browser': 'zendriver',
                    'available_browsers': available_browsers,
                    'locked': True
                })
            except Exception as e:
                self.logger.error(f"Error getting browser status: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/browser/available')
        def get_available_browsers():
            """Get available browsers - ZenDriver only."""
            try:
                from src.browser.browser_factory import browser_factory
                available_browsers = browser_factory.get_available_browsers()
                
                return jsonify({
                    'success': True,
                    'browsers': available_browsers
                })
            except Exception as e:
                self.logger.error(f"Error getting available browsers: {e}")
                return jsonify({'success': False, 'error': str(e)})

        
        @self.app.route('/api/accounts', methods=['GET'])
        def get_accounts():
            """Get all accounts."""
            try:
                accounts = self.account_manager.get_all_accounts_dict()
                account_list = []
                
                for username, account_data in accounts.items():
                    account_list.append({
                        'username': username,
                        'status': account_data.status,  # Use the actual status from the account
                        'proxy': account_data.preferred_proxy or 'None',
                        'use_proxy': account_data.use_proxy
                    })
                
                return jsonify({
                    'success': True,
                    'accounts': account_list
                })
            except Exception as e:
                self.logger.error(f"Error getting accounts: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/accounts', methods=['POST'])
        def add_account():
            """Add new account."""
            try:
                data = request.get_json()
                username = data.get('username')
                use_proxy = data.get('use_proxy', True)
                preferred_proxy = data.get('preferred_proxy')
                
                if not username:
                    return jsonify({'success': False, 'error': 'Username is required'})
                
                # Validate proxy if provided
                if preferred_proxy and preferred_proxy not in self.proxy_manager.proxies:
                    return jsonify({'success': False, 'error': 'Selected proxy not found'})
                
                # Store pending account for login completion
                self.pending_accounts[username] = {
                    'username': username,
                    'preferred_proxy': preferred_proxy,
                    'use_proxy': use_proxy,
                    'status': 'waiting_for_login'
                }
                
                # Start browser session for manual login using persistent event loop
                # This keeps the event loop alive so ZenDriver's browser stays open
                success = browser_event_loop.run_coroutine(
                    self.account_manager.start_login_session(
                        username=username,
                        preferred_proxy=preferred_proxy,
                        use_proxy=use_proxy
                    )
                )
                
                if success:
                    proxy_info = f" with proxy {preferred_proxy}" if preferred_proxy and use_proxy else ""
                    message = f'Browser opened for account {username}{proxy_info}. Please login manually and click "Login Complete" when done.'
                    
                    # Broadcast update to all connected clients
                    self.broadcast_log_entry(message)
                    
                    return jsonify({
                        'success': True, 
                        'message': message,
                        'pending_login': True,
                        'username': username
                    })
                else:
                    return jsonify({'success': False, 'error': 'Failed to open browser for login'})
                    
            except Exception as e:
                self.logger.error(f"Error adding account: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/accounts/open', methods=['POST'])
        def open_account_browser():
            """Open browser for existing account - allows multiple instances."""
            try:
                data = request.get_json()
                username = data.get('username')
                
                if not username:
                    return jsonify({'success': False, 'error': 'Username is required'})
                
                if username not in self.account_manager.accounts:
                    return jsonify({'success': False, 'error': 'Account not found'})
                
                # Start browser session using persistent event loop
                # Removed the check for existing sessions to allow multiple browser instances
                success = browser_event_loop.run_coroutine(
                    self.account_manager.open_account_browser(username, allow_multiple=True)
                )
                
                if success:
                    message = f'Browser opened for account @{username}'
                    self.broadcast_log_entry(message)
                    return jsonify({'success': True, 'message': message})
                else:
                    return jsonify({'success': False, 'error': 'Failed to open browser'})
                    
            except Exception as e:
                self.logger.error(f"Error opening browser: {e}")
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/accounts/<username>/complete-login', methods=['POST'])
        def complete_login(username):
            """Complete manual login for account."""
            try:
                if username not in self.pending_accounts:
                    return jsonify({'success': False, 'error': 'No pending login for this account'})
                
                # Complete the login process using persistent event loop
                success = browser_event_loop.run_coroutine(
                    self.account_manager.complete_login_session(username)
                )
                
                if success:
                    # Remove from pending accounts
                    del self.pending_accounts[username]
                    
                    message = f'Account {username} login completed successfully'
                    self.broadcast_log_entry(message)
                    
                    # Broadcast status update to refresh dashboard
                    self.broadcast_status_update()
                    
                    return jsonify({'success': True, 'message': message})
                else:
                    return jsonify({'success': False, 'error': 'Failed to complete login'})
                    
            except Exception as e:
                self.logger.error(f"Error completing login: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/accounts/<username>/cancel-login', methods=['POST'])
        def cancel_login(username):
            """Cancel manual login for account."""
            try:
                if username not in self.pending_accounts:
                    return jsonify({'success': False, 'error': 'No pending login for this account'})
                
                # Cancel the login process using persistent event loop
                success = browser_event_loop.run_coroutine(
                    self.account_manager.cancel_login_session(username)
                )
                
                # Remove from pending accounts
                del self.pending_accounts[username]
                
                message = f'Login cancelled for account {username}'
                self.broadcast_log_entry(message)
                
                return jsonify({'success': True, 'message': message})
                    
            except Exception as e:
                self.logger.error(f"Error cancelling login: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/accounts/<username>', methods=['DELETE'])
        def remove_account(username):
            """Remove account."""
            try:
                success = self.account_manager.remove_account(username)
                if success:
                    # Broadcast update to all connected clients
                    self.broadcast_log_entry(f"Account @{username} removed")
                    
                    # Broadcast status update to refresh dashboard
                    self.broadcast_status_update()
                    
                    return jsonify({'success': True, 'message': f'Account {username} removed'})
                else:
                    return jsonify({'success': False, 'error': 'Failed to remove account'})
            except Exception as e:
                self.logger.error(f"Error removing account: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/accounts/<username>/toggle', methods=['PUT'])
        def toggle_account(username):
            """Toggle account active status."""
            try:
                success = self.account_manager.toggle_account_status(username)
                if success:
                    account = self.account_manager.get_account(username)
                    status = "activated" if account.is_active else "deactivated"
                    self.broadcast_log_entry(f"Account @{username} {status}")
                    return jsonify({'success': True, 'message': f'Account {status}', 'is_active': account.is_active})
                else:
                    return jsonify({'success': False, 'error': 'Failed to toggle account status'})
            except Exception as e:
                self.logger.error(f"Error toggling account: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/accounts/<username>/proxy', methods=['PUT'])
        def update_account_proxy(username):
            """Update account proxy settings."""
            try:
                data = request.get_json()
                preferred_proxy = data.get('preferred_proxy')
                use_proxy = data.get('use_proxy', True)
                
                # Validate proxy if provided
                if preferred_proxy and preferred_proxy not in self.proxy_manager.proxies:
                    return jsonify({'success': False, 'error': 'Selected proxy not found'})
                
                # Update account
                success = self.account_manager.update_account_proxy(
                    username=username,
                    preferred_proxy=preferred_proxy,
                    use_proxy=use_proxy
                )
                
                if success:
                    proxy_info = f" to {preferred_proxy}" if preferred_proxy and use_proxy else " (disabled)"
                    message = f'Updated proxy settings for @{username}{proxy_info}'
                    
                    # Broadcast update to all connected clients
                    self.broadcast_log_entry(message)
                    
                    return jsonify({'success': True, 'message': message})
                else:
                    return jsonify({'success': False, 'error': 'Failed to update account proxy settings'})
                    
            except Exception as e:
                self.logger.error(f"Error updating account proxy: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/proxies', methods=['GET'])
        def get_proxies():
            """Get all proxies."""
            try:
                proxies = self.proxy_manager.get_all_proxies()
                proxy_list = []
                
                for proxy_id, proxy_data in proxies.items():
                    proxy_list.append({
                        'id': proxy_id,
                        'host': proxy_data.host,
                        'port': proxy_data.port,
                        'type': proxy_data.protocol,
                        'status': proxy_data.status,
                        'username': proxy_data.username or '',
                        'display_url': proxy_data.display_url
                    })
                
                return jsonify({
                    'success': True,
                    'proxies': proxy_list
                })
            except Exception as e:
                self.logger.error(f"Error getting proxies: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/proxies', methods=['POST'])
        def add_proxy():
            """Add new proxy."""
            try:
                data = request.get_json()
                host = data.get('host')
                port = data.get('port')
                proxy_type = data.get('type', 'HTTP')
                username = data.get('username')
                password = data.get('password')
                
                if not host or not port:
                    return jsonify({'success': False, 'error': 'Host and port are required'})
                
                proxy_id = self.proxy_manager.add_proxy(
                    host=host,
                    port=int(port),
                    protocol=proxy_type.lower(),
                    username=username if username else None,
                    password=password if password else None
                )
                
                # Broadcast update to all connected clients
                self.broadcast_log_entry(f"Proxy {host}:{port} added successfully")
                
                return jsonify({'success': True, 'message': 'Proxy added successfully', 'id': proxy_id})
                
            except Exception as e:
                self.logger.error(f"Error adding proxy: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/proxies/<proxy_id>', methods=['DELETE'])
        def remove_proxy(proxy_id):
            """Remove proxy."""
            try:
                success = self.proxy_manager.remove_proxy(proxy_id)
                if success:
                    # Broadcast update to all connected clients
                    self.broadcast_log_entry(f"Proxy removed successfully")
                    return jsonify({'success': True, 'message': 'Proxy removed'})
                else:
                    return jsonify({'success': False, 'error': 'Failed to remove proxy'})
            except Exception as e:
                self.logger.error(f"Error removing proxy: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/proxies/<proxy_id>/test', methods=['POST'])
        def test_proxy(proxy_id):
            """Test a single proxy."""
            try:
                # Check if proxy exists
                if proxy_id not in self.proxy_manager.proxies:
                    return jsonify({'success': False, 'error': 'Proxy not found'})
                
                # Test the proxy
                result = self.proxy_manager.test_proxy_sync(proxy_id)
                status = "working" if result else "failed"
                
                return jsonify({'success': True, 'status': status})
                
            except Exception as e:
                self.logger.error(f"Error testing proxy {proxy_id}: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/proxies/test-all', methods=['POST'])
        def test_all_proxies():
            """Test all proxies."""
            try:
                if not self.proxy_manager.proxies:
                    return jsonify({
                        'success': True, 
                        'message': 'No proxies to test',
                        'results': {}
                    })
                
                # Test all proxies
                results = self.proxy_manager.test_all_proxies_sync()
                working = sum(1 for r in results.values() if r == "working")
                total = len(results)
                
                return jsonify({
                    'success': True, 
                    'message': f'Tested {total} proxies, {working} working',
                    'results': results
                })
                
            except Exception as e:
                self.logger.error(f"Error testing proxies: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/bot/start', methods=['POST'])
        def start_bot():
            """Start the bot."""
            try:
                if self.start_callback:
                    threading.Thread(target=self.start_callback, daemon=True).start()
                    self.is_running = True
                    return jsonify({'success': True, 'message': 'Bot started'})
                else:
                    return jsonify({'success': False, 'error': 'Start callback not set'})
            except Exception as e:
                self.logger.error(f"Error starting bot: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/bot/stop', methods=['POST'])
        def stop_bot():
            """Stop the bot."""
            try:
                if self.stop_callback:
                    threading.Thread(target=self.stop_callback, daemon=True).start()
                    self.is_running = False
                    return jsonify({'success': True, 'message': 'Bot stopped'})
                else:
                    return jsonify({'success': False, 'error': 'Stop callback not set'})
            except Exception as e:
                self.logger.error(f"Error stopping bot: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/config', methods=['GET'])
        def get_config():
            """Get configuration."""
            try:
                return jsonify({'success': True, 'config': self.config})
            except Exception as e:
                self.logger.error(f"Error getting config: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/config', methods=['POST'])
        def save_config():
            """Save configuration."""
            try:
                data = request.get_json()
                self.config.update(data)
                
                # Save to file
                with open('config.json', 'w') as f:
                    json.dump(self.config, f, indent=4)
                
                # Update scheduler if it exists
                if self.post_manager and hasattr(self.post_manager, 'posting_scheduler'):
                    scheduler = self.post_manager.posting_scheduler
                    
                    # Update randomness
                    if 'posting_intervals' in data:
                        rp = data['posting_intervals'].get('randomness_percent')
                        if rp is not None:
                            scheduler.randomness_percent = int(rp)
                            scheduler.config['randomness_percent'] = int(rp)
                            self.logger.info(f"Updated scheduler randomness to {rp}%")
                            
                        # Update all community groups with new default interval
                        new_default = data['posting_intervals'].get('default')
                        if new_default is not None:
                            interval = int(new_default)
                            # Directly update group interval property
                            for group in scheduler.community_groups:
                                group.posting_interval = interval
                            # Save updated groups to file
                            scheduler.file_manager.save_communities(scheduler.community_groups)
                            # Reload to ensure consistency
                            scheduler.reload_community_groups()
                            self.logger.info(f"Updated {len(scheduler.community_groups)} community groups to new interval: {interval}s")

                return jsonify({'success': True, 'message': 'Configuration saved'})
            except Exception as e:
                self.logger.error(f"Error saving config: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/config/concurrent-browsers', methods=['GET'])
        def get_concurrent_browsers_config():
            """Get concurrent browsers configuration."""
            try:
                # Get current setting from config
                current_value = self.config.get('browser_settings', {}).get('max_concurrent_browsers', 1)
                
                return jsonify({
                    'success': True,
                    'max_concurrent_browsers': current_value,
                    'min_value': 1,
                    'max_value': 5,
                    'description': 'Maximum number of browsers that can run simultaneously (1-5). Higher values increase speed but use more system resources.'
                })
            except Exception as e:
                self.logger.error(f"Error getting concurrent browsers config: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/config/concurrent-browsers', methods=['POST'])
        def set_concurrent_browsers_config():
            """Set concurrent browsers configuration."""
            try:
                data = request.get_json()
                max_concurrent = data.get('max_concurrent_browsers', 1)
                
                # Validate the value
                if not isinstance(max_concurrent, int) or not 1 <= max_concurrent <= 5:
                    return jsonify({
                        'success': False, 
                        'error': 'max_concurrent_browsers must be an integer between 1 and 5'
                    })
                
                # Update config
                if 'browser_settings' not in self.config:
                    self.config['browser_settings'] = {}
                
                self.config['browser_settings']['max_concurrent_browsers'] = max_concurrent
                
                # Save to file
                with open('config.json', 'w') as f:
                    json.dump(self.config, f, indent=4)
                
                # Broadcast update to all connected clients
                self.broadcast_log_entry(f"Concurrent browsers setting updated to {max_concurrent}")
                
                return jsonify({
                    'success': True, 
                    'message': f'Concurrent browsers set to {max_concurrent}',
                    'max_concurrent_browsers': max_concurrent
                })
            except Exception as e:
                self.logger.error(f"Error setting concurrent browsers config: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/files/<filename>', methods=['GET'])
        def get_file_content(filename):
            """Get file content for editing."""
            try:
                file_map = {
                    'config.json': 'config.json',
                    'communities.txt': 'data/communities.txt',
                    'posts.txt': 'data/posts.txt'
                }
                
                if filename not in file_map:
                    return jsonify({'success': False, 'error': 'File not found'})
                
                file_path = Path(file_map[filename])
                
                if file_path.exists():
                    content = file_path.read_text(encoding='utf-8')
                else:
                    # Create default content for new files
                    if filename == 'communities.txt':
                        content = "# Twitter Community URLs (one per line)\n# Example: https://twitter.com/i/communities/1234567890\n"
                    elif filename == 'posts.txt':
                        content = "# Post content (one per line)\n# Example: This is my first post!\n"
                    else:
                        content = ""
                
                return jsonify({'success': True, 'content': content})
                
            except Exception as e:
                self.logger.error(f"Error reading file {filename}: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/files/<filename>', methods=['POST'])
        def save_file_content(filename):
            """Save file content."""
            try:
                file_map = {
                    'config.json': 'config.json',
                    'communities.txt': 'data/communities.txt',
                    'posts.txt': 'data/posts.txt'
                }
                
                if filename not in file_map:
                    return jsonify({'success': False, 'error': 'File not found'})
                
                data = request.get_json()
                content = data.get('content', '')
                
                file_path = Path(file_map[filename])
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding='utf-8')
                
                # Emit update to all connected clients
                self.socketio.emit('file_updated', {'filename': filename})
                
                return jsonify({'success': True, 'message': f'{filename} saved successfully'})
                
            except Exception as e:
                self.logger.error(f"Error saving file {filename}: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        # Communities Management API
        @self.app.route('/api/communities', methods=['GET'])
        def get_communities():
            """Get all communities."""
            try:
                communities = self.load_communities_data()
                return jsonify({'success': True, 'communities': communities})
            except Exception as e:
                self.logger.error(f"Error getting communities: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/communities', methods=['POST'])
        def add_community():
            """Add new community."""
            try:
                data = request.get_json()
                name = data.get('name', '').strip()
                url = data.get('url', '').strip()
                
                if not name or not url:
                    return jsonify({'success': False, 'error': 'Name and URL are required'})
                
                if not url.startswith('https://twitter.com/i/communities/') and not url.startswith('https://x.com/i/communities/'):
                    return jsonify({'success': False, 'error': 'Invalid Twitter community URL'})
                
                communities = self.load_communities_data()
                
                # Check if community already exists
                for community in communities:
                    if community['url'] == url:
                        return jsonify({'success': False, 'error': 'Community already exists'})
                
                # Add new community
                new_community = {
                    'id': len(communities) + 1,
                    'name': name,
                    'url': url,
                    'active': True,
                    'created_at': datetime.now().isoformat()
                }
                
                communities.append(new_community)
                self.save_communities_data(communities)
                
                # Broadcast update
                self.broadcast_log_entry(f"Community '{name}' added")
                
                # Broadcast status update to refresh dashboard
                self.broadcast_status_update()
                
                return jsonify({'success': True, 'message': 'Community added successfully'})
                
            except Exception as e:
                self.logger.error(f"Error adding community: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/communities/<int:community_id>', methods=['DELETE'])
        def remove_community(community_id):
            """Remove community."""
            try:
                communities = self.load_communities_data()
                communities = [c for c in communities if c['id'] != community_id]
                self.save_communities_data(communities)
                
                # Broadcast update
                self.broadcast_log_entry(f"Community removed")
                
                # Broadcast status update to refresh dashboard
                self.broadcast_status_update()
                
                return jsonify({'success': True, 'message': 'Community removed successfully'})
                
            except Exception as e:
                self.logger.error(f"Error removing community: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/communities/<int:community_id>/toggle', methods=['PUT'])
        def toggle_community(community_id):
            """Toggle community active status."""
            try:
                communities = self.load_communities_data()
                
                for community in communities:
                    if community['id'] == community_id:
                        community['active'] = not community['active']
                        break
                
                self.save_communities_data(communities)
                
                return jsonify({'success': True, 'message': 'Community status updated'})
                
            except Exception as e:
                self.logger.error(f"Error toggling community: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        # Posts Management API
        @self.app.route('/api/posts', methods=['GET'])
        def get_posts():
            """Get all posts."""
            try:
                posts = self.load_posts_data()
                return jsonify({'success': True, 'posts': posts})
            except Exception as e:
                self.logger.error(f"Error getting posts: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/captions', methods=['GET'])
        def get_captions():
            """Get all captions."""
            try:
                data_dir = Path(os.getcwd()) / "data"
                captions_file = data_dir / "captions.json"
                
                if captions_file.exists():
                    try:
                        content = captions_file.read_text(encoding='utf-8')
                        captions = json.loads(content) if content.strip() else []
                    except json.JSONDecodeError:
                        self.logger.warning("Corrupt captions.json, resetting")
                        captions = []
                else:
                    captions = []
                return jsonify({'success': True, 'captions': captions})
            except Exception as e:
                self.logger.error(f"Error getting captions: {e}")
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/captions', methods=['POST'])
        def add_caption():
            """Add new caption."""
            try:
                data = request.get_json()
                content = data.get('content', '').strip()
                image_groups = data.get('image_groups', [])
                
                if not content:
                    return jsonify({'success': False, 'error': 'Content required'})
                
                data_dir = Path(os.getcwd()) / "data"
                data_dir.mkdir(parents=True, exist_ok=True)
                captions_file = data_dir / "captions.json"
                
                if captions_file.exists():
                    try:
                        file_content = captions_file.read_text(encoding='utf-8')
                        captions = json.loads(file_content) if file_content.strip() else []
                    except json.JSONDecodeError:
                        captions = []
                else:
                    captions = []
                
                new_caption = {
                    'id': int(time.time() * 1000),
                    'content': content,
                    'created_at': datetime.now().isoformat(),
                    'image_groups': image_groups
                }
                captions.append(new_caption)
                captions_file.write_text(json.dumps(captions, indent=2), encoding='utf-8')
                return jsonify({'success': True, 'message': 'Caption added'})
            except Exception as e:
                self.logger.error(f"Error adding caption: {e}")
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/captions/<int:caption_id>', methods=['DELETE'])
        def delete_caption(caption_id):
            """Delete caption."""
            try:
                captions_file = Path("data/captions.json")
                if not captions_file.exists():
                    return jsonify({'success': False, 'error': 'No captions file'})
                
                captions = json.loads(captions_file.read_text(encoding='utf-8'))
                captions = [c for c in captions if c['id'] != caption_id]
                captions_file.write_text(json.dumps(captions, indent=2), encoding='utf-8')
                return jsonify({'success': True, 'message': 'Caption deleted'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/captions/<int:caption_id>', methods=['PUT'])
        def update_caption(caption_id):
            """Update caption."""
            try:
                data = request.get_json()
                captions_file = Path("data/captions.json")
                if not captions_file.exists():
                    return jsonify({'success': False, 'error': 'No captions file'})
                
                captions = json.loads(captions_file.read_text(encoding='utf-8'))
                for caption in captions:
                    if caption['id'] == caption_id:
                        if 'content' in data:
                            caption['content'] = data['content']
                        if 'image_groups' in data:
                            caption['image_groups'] = data['image_groups']
                        break
                
                captions_file.write_text(json.dumps(captions, indent=2), encoding='utf-8')
                return jsonify({'success': True, 'message': 'Caption updated'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/captions/delete-all', methods=['DELETE'])
        def delete_all_captions():
            """Delete all captions."""
            try:
                captions_file = Path("data/captions.json")
                captions_file.write_text(json.dumps([], indent=2), encoding='utf-8')
                self.broadcast_log_entry("All captions deleted")
                return jsonify({'success': True, 'message': 'All captions deleted'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        # Content Pairing API
        @self.app.route('/api/content-pairs', methods=['GET'])
        def get_content_pairs():
            """Get all content pairs (caption + photo + account)."""
            try:
                pairs_file = Path("data/content_pairs.json")
                if pairs_file.exists():
                    pairs = json.loads(pairs_file.read_text(encoding='utf-8'))
                else:
                    pairs = []
                return jsonify({'success': True, 'pairs': pairs})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/content-pairs', methods=['POST'])
        def add_content_pair():
            """Add a new content pair."""
            try:
                data = request.get_json()
                caption_ids = data.get('caption_ids', [])  # Now accepts array
                image_group_id = data.get('image_group_id')
                account_username = data.get('account_username')
                
                # Support both single caption_id (backward compatibility) and multiple caption_ids
                if 'caption_id' in data and not caption_ids:
                    caption_ids = [data.get('caption_id')]
                
                pairs_file = Path("data/content_pairs.json")
                if pairs_file.exists():
                    pairs = json.loads(pairs_file.read_text(encoding='utf-8'))
                else:
                    pairs = []
                
                new_pair = {
                    'id': int(time.time() * 1000),
                    'caption_ids': caption_ids,  # Array of caption IDs
                    'image_group_id': image_group_id,
                    'account_username': account_username,
                    'created_at': datetime.now().isoformat()
                }
                
                pairs.append(new_pair)
                pairs_file.write_text(json.dumps(pairs, indent=2), encoding='utf-8')
                
                caption_count = len(caption_ids) if caption_ids else 0
                self.broadcast_log_entry(f"Content pair created for @{account_username} with {caption_count} caption(s)")
                return jsonify({'success': True, 'message': 'Content pair created', 'pair': new_pair})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/content-pairs/<int:pair_id>', methods=['DELETE'])
        def delete_content_pair(pair_id):
            """Delete a content pair."""
            try:
                pairs_file = Path("data/content_pairs.json")
                if not pairs_file.exists():
                    return jsonify({'success': False, 'error': 'No pairs file'})
                
                pairs = json.loads(pairs_file.read_text(encoding='utf-8'))
                pairs = [p for p in pairs if p['id'] != pair_id]
                pairs_file.write_text(json.dumps(pairs, indent=2), encoding='utf-8')
                
                self.broadcast_log_entry("Content pair deleted")
                return jsonify({'success': True, 'message': 'Content pair deleted'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/content-pairs/<int:pair_id>', methods=['PUT'])
        def update_content_pair(pair_id):
            """Update a content pair."""
            try:
                data = request.get_json()
                
                pairs_file = Path("data/content_pairs.json")
                if not pairs_file.exists():
                    return jsonify({'success': False, 'error': 'No pairs file'})
                
                pairs = json.loads(pairs_file.read_text(encoding='utf-8'))
                
                for pair in pairs:
                    if pair['id'] == pair_id:
                        # Support both single caption_id and multiple caption_ids
                        if 'caption_ids' in data:
                            pair['caption_ids'] = data['caption_ids']
                        elif 'caption_id' in data:
                            # Backward compatibility: convert single to array
                            pair['caption_ids'] = [data['caption_id']]
                        
                        if 'image_group_id' in data:
                            pair['image_group_id'] = data['image_group_id']
                        if 'account_username' in data:
                            pair['account_username'] = data['account_username']
                        pair['updated_at'] = datetime.now().isoformat()
                        break
                
                pairs_file.write_text(json.dumps(pairs, indent=2), encoding='utf-8')
                
                self.broadcast_log_entry("Content pair updated")
                return jsonify({'success': True, 'message': 'Content pair updated'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        # Account-Community Pairing API (Unified Content Pairing)
        @self.app.route('/api/content-pairing', methods=['GET'])
        def get_content_pairing():
            """Get unified content pairing configuration."""
            try:
                pairing_file = Path("data/content_pairing.json")
                if pairing_file.exists():
                    pairing = json.loads(pairing_file.read_text(encoding='utf-8'))
                else:
                    pairing = []
                return jsonify({'success': True, 'pairing': pairing})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/content-pairing', methods=['POST'])
        def add_content_pairing():
            """Add unified content pairing (captions + accounts + communities + image groups)."""
            try:
                data = request.get_json()
                name = data.get('name', '')
                caption_ids = data.get('caption_ids', [])
                accounts = data.get('accounts', [])
                communities = data.get('communities', [])
                image_groups = data.get('image_groups', [])
                
                if not name:
                    return jsonify({'success': False, 'error': 'Name is required'})
                
                pairing_file = Path("data/content_pairing.json")
                if pairing_file.exists():
                    pairing = json.loads(pairing_file.read_text(encoding='utf-8'))
                else:
                    pairing = []
                
                new_pairing = {
                    'id': int(time.time() * 1000),
                    'name': name,
                    'caption_ids': caption_ids,
                    'accounts': accounts,
                    'communities': communities,
                    'image_groups': image_groups,
                    'created_at': datetime.now().isoformat()
                }
                
                pairing.append(new_pairing)
                pairing_file.write_text(json.dumps(pairing, indent=2), encoding='utf-8')
                
                self.broadcast_log_entry(f"Content pairing '{name}' created")
                return jsonify({'success': True, 'message': 'Content pairing saved', 'pairing': new_pairing})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/content-pairing/<int:pairing_id>', methods=['PUT'])
        def update_content_pairing(pairing_id):
            """Update unified content pairing."""
            try:
                data = request.get_json()
                
                pairing_file = Path("data/content_pairing.json")
                if not pairing_file.exists():
                    return jsonify({'success': False, 'error': 'No pairing file'})
                
                pairing = json.loads(pairing_file.read_text(encoding='utf-8'))
                
                for item in pairing:
                    if item.get('id') == pairing_id:
                        if 'name' in data:
                            item['name'] = data['name']
                        if 'caption_ids' in data:
                            item['caption_ids'] = data['caption_ids']
                        if 'accounts' in data:
                            item['accounts'] = data['accounts']
                        if 'communities' in data:
                            item['communities'] = data['communities']
                        if 'image_groups' in data:
                            item['image_groups'] = data['image_groups']
                        item['updated_at'] = datetime.now().isoformat()
                        break
                
                pairing_file.write_text(json.dumps(pairing, indent=2), encoding='utf-8')
                
                self.broadcast_log_entry(f"Content pairing updated")
                return jsonify({'success': True, 'message': 'Content pairing updated'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/content-pairing/<int:pairing_id>', methods=['DELETE'])
        def delete_content_pairing(pairing_id):
            """Delete unified content pairing."""
            try:
                pairing_file = Path("data/content_pairing.json")
                if not pairing_file.exists():
                    return jsonify({'success': False, 'error': 'No pairing file'})
                
                pairing = json.loads(pairing_file.read_text(encoding='utf-8'))
                pairing = [p for p in pairing if p.get('id') != pairing_id]
                pairing_file.write_text(json.dumps(pairing, indent=2), encoding='utf-8')
                
                self.broadcast_log_entry(f"Content pairing deleted")
                return jsonify({'success': True, 'message': 'Content pairing deleted'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/image-groups', methods=['GET'])
        def get_image_groups():
            """Get all image groups."""
            try:
                # Use absolute path
                data_dir = Path(os.getcwd()) / "data"
                img_file = data_dir / "image_groups.json"
                
                if img_file.exists():
                    try:
                        content = img_file.read_text(encoding='utf-8')
                        groups = json.loads(content) if content.strip() else []
                    except json.JSONDecodeError:
                        self.logger.warning("Corrupt image_groups.json, resetting")
                        groups = []
                else:
                    groups = []
                return jsonify({'success': True, 'groups': groups})
            except Exception as e:
                self.logger.error(f"Error getting image groups: {e}")
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/image-groups', methods=['POST'])
        def add_image_group():
            """Add new image group."""
            try:
                # Ensure data directory exists
                data_dir = Path(os.getcwd()) / "data"
                images_dir = data_dir / "images"
                images_dir.mkdir(parents=True, exist_ok=True)
                
                image_paths = []
                
                # Image Deduplication Logic
                import hashlib
                hashes_file = data_dir / "image_hashes.json"
                image_hashes = {}
                
                # Load existing hashes
                if hashes_file.exists():
                    try:
                        image_hashes = json.loads(hashes_file.read_text(encoding='utf-8'))
                    except: 
                        pass
                else:
                    # Index existing images if hash file doesn't exist
                    self.logger.info("Indexing existing images for deduplication...")
                    for existing_file in images_dir.glob('*'):
                        if existing_file.is_file() and existing_file.name != 'image_hashes.json':
                            try:
                                with open(existing_file, 'rb') as f:
                                    h = hashlib.sha256(f.read()).hexdigest()
                                    image_hashes[h] = existing_file.name
                            except: 
                                pass
                
                if 'images' in request.files:
                    files = request.files.getlist('images')
                    self.logger.info(f"Received {len(files)} images for upload")
                    
                    for file in files:
                        if file and file.filename:
                            # Calculate hash
                            content = file.read()
                            file.seek(0)
                            file_hash = hashlib.sha256(content).hexdigest()
                            
                            # Check for duplicate
                            existing_filename = image_hashes.get(file_hash)
                            if existing_filename and (images_dir / existing_filename).exists():
                                self.logger.info(f"Reusing existing image: {existing_filename}")
                                image_paths.append(str(Path("data/images") / existing_filename))
                            else:
                                filename = secure_filename(file.filename)
                                timestamp = int(datetime.now().timestamp())
                                unique_filename = f"{timestamp}_{filename}"
                                image_path = images_dir / unique_filename
                                
                                self.logger.info(f"Saving image to {image_path}")
                                file.save(str(image_path))
                                
                                # Update hash index
                                image_hashes[file_hash] = unique_filename
                                # Store relative path for portability
                                image_paths.append(str(Path("data/images") / unique_filename))
                
                # Save updated hashes
                try:
                    hashes_file.write_text(json.dumps(image_hashes, indent=2), encoding='utf-8')
                except Exception as e:
                    self.logger.error(f"Failed to save image hashes: {e}")
                
                if not image_paths:
                     self.logger.warning("No images processed in upload request")
                     return jsonify({'success': False, 'error': 'No images uploaded'})

                img_file = data_dir / "image_groups.json"
                if img_file.exists():
                    try:
                        content = img_file.read_text(encoding='utf-8')
                        groups = json.loads(content) if content.strip() else []
                    except json.JSONDecodeError:
                        groups = []
                else:
                    groups = []
                
                if groups:
                    # Use the first group as the main library for all images
                    # This ensures all uploaded images are considered one large group
                    group = groups[0]
                    existing_images = set(group['images'])
                    added_count = 0
                    
                    for p in image_paths:
                        if p not in existing_images:
                            group['images'].append(p)
                            existing_images.add(p)
                            added_count += 1
                    
                    self.logger.info(f"Added {added_count} images to main library group (Total: {len(group['images'])})")
                else:
                    # Create the first/main group
                    new_group = {
                        'id': int(time.time() * 1000),
                        'images': image_paths,
                        'name': 'Main Library',
                        'created_at': datetime.now().isoformat()
                    }
                    groups.append(new_group)
                    self.logger.info(f"Created main library group with {len(image_paths)} images")
                
                self.logger.info(f"Saving image group library with {len(groups)} items")
                img_file.write_text(json.dumps(groups, indent=2), encoding='utf-8')
                
                return jsonify({'success': True, 'message': 'Images added to library'})
            except Exception as e:
                self.logger.error(f"Error adding image group: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                return jsonify({'success': False, 'error': str(e)})
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/image-groups/<int:group_id>', methods=['DELETE'])
        def delete_image_group(group_id):
            """Delete image group."""
            try:
                img_file = Path("data/image_groups.json")
                if not img_file.exists():
                    return jsonify({'success': False, 'error': 'No image groups file'})
                
                groups = json.loads(img_file.read_text(encoding='utf-8'))
                groups = [g for g in groups if g['id'] != group_id]
                img_file.write_text(json.dumps(groups, indent=2), encoding='utf-8')
                return jsonify({'success': True, 'message': 'Image group deleted'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/image-groups/<int:group_id>/images/<path:image_path>', methods=['DELETE'])
        def delete_single_image(group_id, image_path):
            """Delete a single image from a group."""
            try:
                img_file = Path("data/image_groups.json")
                if not img_file.exists():
                    return jsonify({'success': False, 'error': 'No image groups file'})
                
                groups = json.loads(img_file.read_text(encoding='utf-8'))
                for group in groups:
                    if group['id'] == group_id:
                        # Remove the image from the group
                        group['images'] = [img for img in group['images'] if img != image_path]
                        break
                
                img_file.write_text(json.dumps(groups, indent=2), encoding='utf-8')
                return jsonify({'success': True, 'message': 'Image deleted from group'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/image-groups/delete-all', methods=['DELETE'])
        def delete_all_image_groups():
            """Delete all image groups."""
            try:
                img_file = Path("data/image_groups.json")
                img_file.write_text(json.dumps([], indent=2), encoding='utf-8')
                self.broadcast_log_entry("All image groups deleted")
                return jsonify({'success': True, 'message': 'All image groups deleted'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/posts', methods=['POST'])
        def add_post():
            """Add new post with optional images."""
            try:
                # Handle both JSON and form data
                if request.content_type and 'multipart/form-data' in request.content_type:
                    # Form data with files
                    content = request.form.get('content', '').strip()
                    
                    if not content:
                        return jsonify({'success': False, 'error': 'Post content is required'})
                    
                    posts = self.load_posts_data()
                    
                    # Handle image uploads with deduplication
                    image_paths = []
                    images_dir = Path("data/images")
                    images_dir.mkdir(parents=True, exist_ok=True)
                    
                    import hashlib
                    hashes_file = Path("data/image_hashes.json")
                    image_hashes = {}
                    
                    # Load or Initialize Index
                    if hashes_file.exists():
                        try:
                            image_hashes = json.loads(hashes_file.read_text(encoding='utf-8'))
                        except: pass
                    else:
                        for existing in images_dir.glob('*'):
                            if existing.is_file() and existing.name != 'image_hashes.json':
                                try:
                                    with open(existing, 'rb') as f:
                                        h = hashlib.sha256(f.read()).hexdigest()
                                        image_hashes[h] = existing.name
                                except: pass

                    files_to_process = []
                    if 'images' in request.files:
                        files_to_process.extend(request.files.getlist('images'))
                    
                    for key in request.files:
                        if key.startswith('image_'):
                            files_to_process.append(request.files[key])
                            
                    for file in files_to_process:
                        if file and file.filename:
                            # Hash check
                            content = file.read()
                            file.seek(0)
                            fhash = hashlib.sha256(content).hexdigest()
                            
                            existing_name = image_hashes.get(fhash)
                            if existing_name and (images_dir / existing_name).exists():
                                self.logger.info(f"Reusing existing image: {existing_name}")
                                image_path = images_dir / existing_name
                            else:
                                filename = secure_filename(file.filename)
                                timestamp = int(datetime.now().timestamp())
                                unique_filename = f"{timestamp}_{filename}"
                                image_path = images_dir / unique_filename
                                self.logger.info(f"Saving new image: {image_path}")
                                file.save(str(image_path))
                                image_hashes[fhash] = unique_filename
                            
                            # Store path string
                            image_paths.append(str(image_path))
                            
                    # Save hashes
                    try:
                        hashes_file.write_text(json.dumps(image_hashes, indent=2), encoding='utf-8')
                    except: pass
                    
                    # Add new post with images
                    new_post = {
                        'id': len(posts) + 1,
                        'content': content,
                        'images': image_paths,
                        'active': True,
                        'created_at': datetime.now().isoformat(),
                        'used_count': 0
                    }
                else:
                    # JSON data (backward compatibility)
                    data = request.get_json()
                    content = data.get('content', '').strip()
                    
                    if not content:
                        return jsonify({'success': False, 'error': 'Post content is required'})
                    
                    posts = self.load_posts_data()
                    
                    # Add new post without images
                    new_post = {
                        'id': len(posts) + 1,
                        'content': content,
                        'images': [],
                        'active': True,
                        'created_at': datetime.now().isoformat(),
                        'used_count': 0
                    }
                
                posts.append(new_post)
                self.save_posts_data(posts)
                
                # Broadcast update
                image_text = f" with {len(new_post['images'])} image(s)" if new_post['images'] else ""
                self.broadcast_log_entry(f"Post added: {content[:50]}...{image_text}")
                
                return jsonify({'success': True, 'message': 'Post added successfully'})
                
            except Exception as e:
                self.logger.error(f"Error adding post: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/posts/<int:post_id>', methods=['DELETE'])
        def remove_post(post_id):
            """Remove post."""
            try:
                posts = self.load_posts_data()
                posts = [p for p in posts if p['id'] != post_id]
                self.save_posts_data(posts)
                
                # Broadcast update
                self.broadcast_log_entry(f"Post removed")
                
                return jsonify({'success': True, 'message': 'Post removed successfully'})
                
            except Exception as e:
                self.logger.error(f"Error removing post: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/posts/<int:post_id>/toggle', methods=['PUT'])
        def toggle_post(post_id):
            """Toggle post active status."""
            try:
                posts = self.load_posts_data()
                
                for post in posts:
                    if post['id'] == post_id:
                        post['active'] = not post['active']
                        break
                
                self.save_posts_data(posts)
                
                return jsonify({'success': True, 'message': 'Post status updated'})
                
            except Exception as e:
                self.logger.error(f"Error toggling post: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/post-now', methods=['POST'])
        def post_now():
            """Post immediately using ZenDriver."""
            try:
                # Get form data
                content = request.form.get('content', '').strip()
                community_url = request.form.get('community_url', '').strip()
                account_username = request.form.get('account', '').strip()
                
                self.logger.info(f"Post now request: account={account_username}, content_length={len(content)}, community_url={community_url}")
                
                # Validate required fields
                if not content:
                    return jsonify({'success': False, 'error': 'Post content is required'})
                
                if not account_username:
                    return jsonify({'success': False, 'error': 'Account selection is required'})
                
                # Get account data
                account = self.account_manager.get_account(account_username)
                if not account:
                    return jsonify({'success': False, 'error': f'Account {account_username} not found'})
                
                # Handle image uploads
                image_paths = []
                if 'images' in request.files:
                    files = request.files.getlist('images')
                    for file in files:
                        if file and file.filename:
                            filename = secure_filename(file.filename)
                            if filename:
                                # Save to data/images directory
                                image_path = Path("data/images") / filename
                                file.save(str(image_path))
                                image_paths.append(str(image_path))
                
                # Log the posting attempt
                image_info = f" with {len(image_paths)} images" if image_paths else ""
                community_info = f" to {community_url}" if community_url else ""
                self.broadcast_log_entry(f"Posting started background: @{account_username}{community_info}{image_info}")
                
                # Perform the post using ZenDriver in background event loop without blocking
                browser_event_loop.run_coroutine_async(
                    self._create_post_with_zendriver(account, content, image_paths, community_url)
                )
                
                message = f'Post process initiated for @{account_username}. Check logs for progress.'
                return jsonify({'success': True, 'message': message})
                
            except Exception as e:
                self.logger.error(f"Error in post now: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
                error_msg = f'Post now failed: {str(e)}'
                self.broadcast_log_entry(error_msg)
                return jsonify({'success': False, 'error': error_msg})
        
        # Dashboard API endpoints
        @self.app.route('/api/dashboard/account-activity', methods=['GET'])
        def get_account_activity():
            """Get account posting activity for dashboard."""
            try:
                # Reload accounts to get latest stats
                self.account_manager.load_accounts()
                
                accounts_data = []
                accounts = self.account_manager.get_all_accounts()
                
                for account in accounts:
                    # Get posting history for this account
                    # Prioritize real stats from account object
                    history = self.get_account_posting_history(account.username)
                    
                    accounts_data.append({
                        'username': account.username,
                        'total_posts': account.posts_count,
                        'posts_today': history.get('posts_today', 0),
                        'success_rate': history.get('success_rate', 0),
                        'communities_count': len(history.get('communities', [])),
                        'last_post_time': account.last_used.isoformat() if account.last_used else None,
                        'status': account.status
                    })
                
                return jsonify({'accounts': accounts_data})
                
            except Exception as e:
                self.logger.error(f"Error getting account activity: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/dashboard/recent-posts', methods=['GET'])
        def get_recent_posts():
            """Get recent posts for dashboard."""
            try:
                recent_posts = self.get_recent_posting_history(limit=10)
                
                return jsonify({
                    'posts': recent_posts,
                    'total': len(recent_posts)
                })
                
            except Exception as e:
                self.logger.error(f"Error getting recent posts: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/dashboard/next-posts', methods=['GET'])
        def get_next_posts():
            """Get next posts in pipeline for dashboard."""
            try:
                if not self.post_manager:
                    return jsonify({'posts': [], 'total': 0})
                
                # Get next scheduled posts
                next_posts = self.get_upcoming_posts(limit=5)
                
                return jsonify({
                    'posts': next_posts,
                    'total': len(next_posts)
                })
                
            except Exception as e:
                self.logger.error(f"Error getting next posts: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/dashboard/community-status', methods=['GET'])
        def get_community_status():
            """Get community status for dashboard."""
            try:
                communities_data = []
                
                # Load communities directly from file
                communities = self.load_communities_data()
                
                # Get current community from post manager if available
                current_community = None
                if self.post_manager:
                    try:
                        status = self.post_manager.get_community_status()
                        current_community = status.get('current_community')
                    except:
                        pass  # Ignore errors if post_manager methods don't exist
                
                for community in communities:
                    if community.get('active', True):
                        # Get posting history for this community
                        history = self.get_community_posting_history(community['url'])
                        
                        communities_data.append({
                            'name': community['name'],
                            'url': community['url'],
                            'is_current': community['url'] == current_community,
                            'total_posts': history.get('total_posts', 0),
                            'last_post_time': history.get('last_post_time'),
                            'next_post_time': history.get('next_post_time')
                        })
                
                return jsonify({
                    'communities': communities_data,
                    'total': len(communities_data)
                })
                
            except Exception as e:
                self.logger.error(f"Error getting community status: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/dashboard/multi-account-status', methods=['GET'])
        def get_multi_account_status():
            """Get multi-account posting status for dashboard."""
            try:
                # Get basic counts from data files
                accounts = self.account_manager.get_all_accounts()
                communities = self.load_communities_data()
                active_communities = [c for c in communities if c.get('active', True)]
                
                total_accounts = len(accounts)
                total_communities = len(active_communities)
                total_combinations = total_accounts * total_communities
                
                # If no accounts or communities, return disabled state
                if total_accounts == 0 or total_communities == 0:
                    return jsonify({
                        'enabled': False,
                        'total_accounts': total_accounts,
                        'total_communities': total_communities,
                        'total_combinations': 0,
                        'accounts': [],
                        'communities': [],
                        'current_account': None,
                        'current_community': None,
                        'strategy': 'Add accounts and communities to enable'
                    })
                
                # Get current status from post manager if available
                current_account = None
                current_community = None
                if self.post_manager:
                    try:
                        account_status = self.post_manager.get_account_status()
                        community_status = self.post_manager.get_community_status()
                        current_account = account_status.get('current_account')
                        current_community = community_status.get('current_community_short')
                    except:
                        pass  # Ignore errors if post_manager methods don't exist
                
                # Get detailed account info
                accounts_info = []
                for i, account in enumerate(accounts):
                    accounts_info.append({
                        'username': account.username,
                        'index': i,
                        'is_current': account.username == current_account,
                        'communities_to_post': total_communities,
                        'status': account.status
                    })
                
                # Get detailed community info
                communities_info = []
                for i, community in enumerate(active_communities):
                    community_short = community['name']
                    communities_info.append({
                        'name': community_short,
                        'url': community['url'],
                        'index': i,
                        'is_current': community['url'] == current_community,
                        'accounts_to_post': total_accounts
                    })
                
                return jsonify({
                    'enabled': True,
                    'total_accounts': total_accounts,
                    'total_communities': total_communities,
                    'total_combinations': total_combinations,
                    'current_account': current_account or (accounts[0].username if accounts else None),
                    'current_community': current_community or (active_communities[0]['name'] if active_communities else None),
                    'accounts': accounts_info,
                    'communities': communities_info,
                    'strategy': 'Every account posts to every community'
                })
                
            except Exception as e:
                self.logger.error(f"Error getting multi-account status: {e}")
                return jsonify({'success': False, 'error': str(e)})
    
    
    async def _create_post_with_zendriver(self, account, content: str, image_paths: list, community_url: str = None) -> bool:
        """
        Perform posting using ZenDriver.
        
        Args:
            account: Account data object
            content: Post content text
            image_paths: List of image file paths
            community_url: Optional community URL to post to
            
        Returns:
            True if successful, False otherwise
        """
        browser = None
        try:
            # Import browser factory
            from src.browser.browser_factory import browser_factory
            
            # Get proxy configuration if needed
            proxy_config = None
            if account.use_proxy and account.preferred_proxy:
                from src.proxy.proxy_manager import ProxyManager
                proxy_manager = ProxyManager(self.config)
                
                if account.preferred_proxy in proxy_manager.proxies:
                    proxy_data = proxy_manager.proxies[account.preferred_proxy]
                    proxy_config = proxy_data.url
                    self.logger.info(f"Using proxy {proxy_config} for post")
            
            # Initialize browser using factory
            browser = browser_factory.create_driver(self.config)
            
            # Launch browser with account-specific profile
            success = await browser.launch_browser(
                proxy_config=proxy_config,
                headless=False,
                fingerprint_data=account.fingerprint_data,
                account_username=account.username
            )
            
            if not success:
                self.logger.error("Failed to launch browser for posting")
                return False
            
            # Load existing cookies if available
            existing_cookies = await self.account_manager.load_account_cookies(account)
            if existing_cookies:
                await browser.set_cookies(existing_cookies)
                self.logger.info(f"Loaded {len(existing_cookies)} cookies for {account.username}")
            
            # Use selectors from config
            selectors = self.config['automation']['selectors']
            
            # Step 1: Human-like navigation path (Stealth Flow)
            # Flow: x.com -> random internal pages -> target community
            self.logger.info("Stealth navigation: starting at https://x.com/home")
            await browser.navigate_to_url("https://x.com/home")
            await asyncio.sleep(random.uniform(3.0, 5.5))
            
            intermediate_urls = [
                "https://x.com/notifications",
                "https://x.com/explore",
                "https://x.com/i/connect_people",
                "https://x.com/i/bookmarks",
                "https://x.com/explore/tabs/trending",
                "https://x.com/explore/tabs/news",
                "https://x.com/explore/tabs/sports"
            ]
            
            # Determine loose random number of pages to visit (1 to 3)
            num_pages = random.randint(1, 3)
            self.logger.info(f"Stealth navigation: visiting {num_pages} intermediate pages")

            # Shuffle list to ensure random selection order
            random.shuffle(intermediate_urls)
            
            for i in range(num_pages):
                page_url = intermediate_urls[i % len(intermediate_urls)] # Use modulo to avoid index out of bounds
                self.logger.info(f"Stealth navigation ({i+1}/{num_pages}): visiting {page_url}")
                await browser.navigate_to_url(page_url)
                
                # Add some interaction: minimal scroll
                await browser.scroll_page(random.randint(50, 200))
                await asyncio.sleep(random.uniform(3.0, 5.0))

            # Finally go to target community or home
            target = community_url if community_url else "https://x.com/home"
            self.logger.info(f"Navigating to final target: {target}")
            success = await browser.navigate_to_url(target)
            if not success:
                self.logger.error("Failed to navigate to target URL")
                return False

            # Human-like pause to "read" the page after landing
            await asyncio.sleep(random.uniform(3.5, 6.0))

            # Check if we need to join the community
            current_url = await browser.get_current_url()
            if '/communities/' in current_url:
                self.logger.info("On community page, checking membership status...")
                
                # Simulate reading the community page - humans take time to orient
                await asyncio.sleep(random.uniform(2.0, 4.5))
                
                # Check if already joined
                joined_button = await browser.find_element(selectors['joined_button'], timeout=3)
                if joined_button:
                    self.logger.info("Already a member of this community")
                    # Brief pause even when already joined - natural recognition time
                    await asyncio.sleep(random.uniform(1.0, 2.5))
                else:
                    # Need to join the community
                    self.logger.info("Not a member, attempting to join community...")
                    
                    # Human pause while "deciding" to join
                    await asyncio.sleep(random.uniform(1.5, 3.5))
                    
                    join_button = await browser.find_element(selectors['join_button'], timeout=5)
                    if join_button:
                        # Natural hesitation before clicking important button
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                        
                        success = await browser.click_element(join_button)
                        if not success:
                            self.logger.error("Failed to click join button")
                            return False
                        
                        self.logger.info("Clicked join button, waiting for dialog...")
                        
                        # Wait for the join dialog - humans read the terms/conditions
                        await asyncio.sleep(random.uniform(3.5, 6.0))
                        agree_button = await browser.find_element(selectors['agree_join_button'], timeout=10)
                        if agree_button:
                            # Simulate reading the agreement before clicking
                            await asyncio.sleep(random.uniform(2.5, 5.0))
                            
                            success = await browser.click_element(agree_button)
                            if not success:
                                self.logger.error("Failed to click agree and join button")
                                return False
                            
                            self.logger.info("Successfully joined community")
                            
                            # Wait for join process to complete - observe the confirmation
                            await asyncio.sleep(random.uniform(4.0, 6.5))
                        else:
                            self.logger.error("Agree and join button not found")
                            return False
                    else:
                        self.logger.error("Join button not found - may already be a member or page not loaded")
            
            # Step 2: Find and click compose button
            self.logger.info("Looking for compose button...")
            compose_button = await browser.find_element(selectors['compose_button'], timeout=10)
            if not compose_button:
                self.logger.error("Compose button not found")
                return False
            
            # Human-like delay before clicking compose
            await asyncio.sleep(random.uniform(1.5, 2.5))
            
            success = await browser.click_element(compose_button)
            if not success:
                self.logger.error("Failed to click compose button")
                return False
            
            self.logger.info("Clicked compose button")
            
            # Wait for compose dialog to appear with human-like delay
            await asyncio.sleep(random.uniform(2.0, 3.0))
            
            # Step 3: Find the text area
            textbox = await browser.find_element(selectors['compose_textbox'], timeout=10)
            if not textbox:
                self.logger.error("Compose textbox not found")
                return False
            
            # Decide steps order randomly for human-like behavior
            # True = Image first, False = Text first
            images_first = random.choice([True, False])
            self.logger.info(f"Posting order: {'Images -> Text' if images_first else 'Text -> Images'}")
            
            async def upload_action():
                if image_paths:
                    self.logger.info(f"Uploading {len(image_paths)} images...")
                    success = await self._upload_images_zendriver(browser, image_paths, selectors)
                    if not success:
                        self.logger.warning("Image upload failed, continuing...")
                    await asyncio.sleep(random.uniform(2.0, 3.0))
            
            async def type_action():
                self.logger.info("Typing post content...")
                # Re-find textbox as it may have changed/detached
                tb = await browser.find_element(selectors['compose_textbox'], timeout=5) or textbox
                await browser.click_element(tb)
                await asyncio.sleep(random.uniform(0.5, 1.0))
                success = await browser.type_text_human_like(tb, content)
                if not success:
                    self.logger.error("Failed to type content")
                await asyncio.sleep(random.uniform(2.0, 3.5))

            if images_first:
                await upload_action()
                await type_action()
            else:
                await type_action()
                await upload_action()

            # Step 6: Find and click tweet button
            self.logger.info("Looking for tweet button...")
            tweet_button = await browser.find_element(selectors['tweet_button'], timeout=10)
            if not tweet_button:
                self.logger.error("Tweet button not found")
                return False
            
            # Final human-like delay before posting
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            success = await browser.click_element(tweet_button)
            if not success:
                self.logger.error("Failed to click tweet button")
                return False
            
            self.logger.info("Clicked tweet button")
            
            # Step 7: Wait on page and add human-like behavior
            await asyncio.sleep(random.uniform(5.0, 7.0))
            
            # Human-like behavior: scroll a bit after posting
            self.logger.info("Adding human-like behavior - scrolling...")
            await browser.scroll_page(random.randint(200, 500))
            
            # Final wait to ensure post is processed
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            self.logger.info("Post process completed (check removed as requested)")
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating post with ZenDriver: {e}")
            return False
        finally:
            if browser:
                try:
                    # Save cookies before closing
                    cookies = await browser.get_cookies()
                    if cookies:
                        await self.account_manager.save_account_cookies(account, cookies)
                        self.logger.info(f"Saved {len(cookies)} cookies before closing")
                    
                    self.logger.info("Closing ZenDriver browser...")
                    await browser.close_browser()
                    self.logger.info("ZenDriver browser closed successfully")
                except Exception as e:
                    self.logger.error(f"Error during browser cleanup: {e}")
    
    async def _upload_images_zendriver(self, browser, image_paths: list, selectors: dict, target_element=None) -> bool:
        """
        Upload images using CDP DOM.setFileInputFiles method.
        This is the most reliable method for file uploads in browser automation.
        """
        try:
            for i, image_path in enumerate(image_paths):
                try:
                    p = Path(image_path).absolute()
                    if not p.exists():
                        self.logger.warning(f"Image not found: {image_path}")
                        continue
                    
                    self.logger.info(f"Uploading image {i+1}/{len(image_paths)}: {p.name}")
                    
                    # Find the file input element
                    file_input = await browser.find_element(selectors['media_upload'], timeout=5)
                    
                    if not file_input:
                        self.logger.info("File input not found, trying to reveal it via media button click...")
                        # Click media button to potentially reveal the input
                        media_button = await browser.find_element(selectors['media_button'], timeout=5)
                        if media_button:
                            # Use CDP to click without triggering file dialog
                            # First get the element's backend node ID
                            try:
                                # Get the object ID from the element
                                if hasattr(file_input, 'backend_node_id'):
                                    backend_node_id = file_input.backend_node_id
                                elif hasattr(file_input, '_backend_node_id'):
                                    backend_node_id = file_input._backend_node_id
                                else:
                                    # Try to find file input via CDP directly
                                    pass
                            except:
                                pass
                        
                        await asyncio.sleep(1.0)
                        file_input = await browser.find_element(selectors['media_upload'], timeout=5)
                    
                    if file_input:
                        # Use CDP DOM.setFileInputFiles to set the file directly
                        # This bypasses the system file dialog completely
                        abs_path = str(p)
                        
                        try:
                            # Method 1: Use nodriver/zendriver's native file setting if available
                            if hasattr(file_input, 'send_file'):
                                await file_input.send_file(abs_path)
                                self.logger.info(f"Uploaded via send_file: {p.name}")
                            elif hasattr(file_input, 'set_input_files'):
                                await file_input.set_input_files([abs_path])
                                self.logger.info(f"Uploaded via set_input_files: {p.name}")
                            else:
                                # Method 2: Use CDP directly via browser.tab.send
                                # Get the backend node ID for the file input
                                node_info_js = """
                                (el) => {
                                    return el ? true : false;
                                }
                                """
                                
                                # Use send_keys as fallback - this works for file inputs in CDP-based browsers
                                await file_input.send_keys(abs_path)
                                self.logger.info(f"Uploaded via send_keys: {p.name}")
                        except Exception as upload_err:
                            self.logger.error(f"Upload method failed: {upload_err}")
                            # Final fallback: try send_keys directly
                            try:
                                await file_input.send_keys(abs_path)
                                self.logger.info(f"Uploaded via fallback send_keys: {p.name}")
                            except Exception as fallback_err:
                                self.logger.error(f"Fallback upload failed: {fallback_err}")
                                continue
                        
                        # Wait for image to be processed
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                    else:
                        self.logger.error("File input element not found")
                        return False
                    
                except Exception as e:
                    self.logger.error(f"Failed to upload image {image_path}: {e}")
            
            self.logger.info("Image upload process completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Error in image upload process: {e}")
            return False
    
    def setup_socket_events(self):
        """Setup WebSocket events."""
        
        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection."""
            self.logger.info("Client connected to WebSocket")
            emit('connected', {'message': 'Connected to Xbot WebSocket'})
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection."""
            self.logger.info("Client disconnected from WebSocket")
        
        @self.socketio.on('request_status')
        def handle_status_request():
            """Handle status request via WebSocket."""
            try:
                account_stats = self.account_manager.get_account_stats()
                proxy_stats = self.proxy_manager.get_proxy_stats()
                
                status_data = {
                    'status': 'running' if self.is_running else 'stopped',
                    'stats': {
                        'accounts': account_stats.get('total', 0),
                        'proxies': proxy_stats.get('total', 0),
                        'queue': 0,
                        'success_rate': '0%'
                    }
                }
                
                emit('status_update', status_data)
                
            except Exception as e:
                self.logger.error(f"Error handling status request: {e}")
                emit('error', {'message': str(e)})
    
    def broadcast_status_update(self):
        """Broadcast status update to all connected clients."""
        try:
            account_stats = self.account_manager.get_account_stats()
            proxy_stats = self.proxy_manager.get_proxy_stats()
            
            status_data = {
                'status': 'running' if self.is_running else 'stopped',
                'stats': {
                    'accounts': account_stats.get('total', 0),
                    'proxies': proxy_stats.get('total', 0),
                    'queue': 0,
                    'success_rate': '0%'
                }
            }
            
            self.socketio.emit('status_update', status_data)
            
        except Exception as e:
            self.logger.error(f"Error broadcasting status update: {e}")
    
    def broadcast_log_entry(self, message: str, level: str = 'info'):
        """Broadcast log entry to all connected clients."""
        try:
            log_data = {
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'message': message,
                'level': level
            }
            
            self.socketio.emit('log_entry', log_data)
            
        except Exception as e:
            self.logger.error(f"Error broadcasting log entry: {e}")
    
    def broadcast_dashboard_refresh(self):
        """Broadcast dashboard refresh event to all connected clients."""
        try:
            self.socketio.emit('dashboard_refresh')
            self.logger.debug("Dashboard refresh event broadcasted")
        except Exception as e:
            self.logger.error(f"Error broadcasting dashboard refresh: {e}")
    
    def load_communities_data(self) -> List[Dict]:
        """Load communities from JSON file."""
        try:
            communities_file = Path("data/communities.json")
            if communities_file.exists():
                with open(communities_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            self.logger.error(f"Error loading communities: {e}")
            return []
    
    def save_communities_data(self, communities: List[Dict]) -> None:
        """Save communities to JSON file."""
        try:
            communities_file = Path("data/communities.json")
            communities_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(communities_file, 'w', encoding='utf-8') as f:
                json.dump(communities, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.logger.error(f"Error saving communities: {e}")
    
    def load_posts_data(self) -> List[Dict]:
        """Load posts from JSON file."""
        try:
            posts_file = Path("data/posts.json")
            if posts_file.exists():
                with open(posts_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return []
        except Exception as e:
            self.logger.error(f"Error loading posts: {e}")
            return []
    
    def save_posts_data(self, posts: List[Dict]) -> None:
        """Save posts to JSON file."""
        try:
            posts_file = Path("data/posts.json")
            posts_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(posts_file, 'w', encoding='utf-8') as f:
                json.dump(posts, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.logger.error(f"Error saving posts: {e}")
    
    def get_account_posting_history(self, username: str) -> Dict:
        """Get posting history for a specific account."""
        try:
            # This would typically read from a posting history database/file
            # For now, return mock data - you can implement actual history tracking
            history_file = Path(f"data/history_{username}.json")
            
            if history_file.exists():
                with open(history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            # Return default empty history
            return {
                'total_posts': 0,
                'posts_today': 0,
                'success_rate': 0,
                'communities': [],
                'last_post_time': None
            }
            
        except Exception as e:
            self.logger.error(f"Error getting account history for {username}: {e}")
            return {
                'total_posts': 0,
                'posts_today': 0,
                'success_rate': 0,
                'communities': [],
                'last_post_time': None
            }
    
    def get_recent_posting_history(self, limit: int = 10) -> List[Dict]:
        """Get recent posting history across all accounts."""
        try:
            # This would typically read from a posting history database/file
            # For now, return mock data - you can implement actual history tracking
            history_file = Path("data/posting_history.json")
            
            if history_file.exists():
                with open(history_file, 'r', encoding='utf-8') as f:
                    try:
                        history = json.load(f)
                        
                        # Handle both List (real app) and Dict (old/mock) formats
                        if isinstance(history, list):
                            posts_list = history
                        else:
                            posts_list = history.get('posts', [])
                        
                        # Sort by timestamp/posted_at and return most recent
                        recent = sorted(posts_list, 
                                      key=lambda x: x.get('timestamp') or x.get('posted_at') or '', 
                                      reverse=True)
                        return recent[:limit]
                    except json.JSONDecodeError:
                        return []
            
            return []
            
        except Exception as e:
            self.logger.error(f"Error getting recent posting history: {e}")
            return []
    
    def get_upcoming_posts(self, limit: int = 5) -> List[Dict]:
        """Get upcoming scheduled posts."""
        try:
            if not self.post_manager:
                return []
            
            # Get next posts from the scheduler
            upcoming = []
            
            # Generate mock upcoming posts based on current configuration
            # In a real implementation, this would come from the scheduler
            communities = self.load_communities_data()
            active_communities = [c for c in communities if c.get('active', True)]
            
            if active_communities:
                from datetime import datetime, timedelta
                import random
                
                base_time = datetime.now()
                
                for i in range(min(limit, len(active_communities))):
                    community = active_communities[i % len(active_communities)]
                    scheduled_time = base_time + timedelta(minutes=30 + (i * 60))
                    
                    # Get a sample caption
                    captions_file = Path("data/captions.json")
                    content = "Sample post content"
                    if captions_file.exists():
                        captions = json.loads(captions_file.read_text())
                        if captions:
                            content = random.choice(captions)['content']
                    
                    upcoming.append({
                        'content': content,
                        'scheduled_for': scheduled_time.isoformat(),
                        'account': 'sample_account',
                        'community_url': community['url'],
                        'community_name': community['name']
                    })
            
            return upcoming
            
        except Exception as e:
            self.logger.error(f"Error getting upcoming posts: {e}")
            return []
    
    def get_community_posting_history(self, community_url: str) -> Dict:
        """Get posting history for a specific community."""
        try:
            # This would typically read from a posting history database/file
            # For now, return mock data - you can implement actual history tracking
            history_file = Path("data/posting_history.json")
            
            if history_file.exists():
                with open(history_file, 'r', encoding='utf-8') as f:
                    try:
                        history = json.load(f)
                        
                        # Handle both List (real app) and Dict (old/mock) formats
                        if isinstance(history, list):
                            posts_list = history
                        else:
                            posts_list = history.get('posts', [])
                        
                        # Filter posts for this community
                        community_posts = [
                            post for post in posts_list
                            if post.get('community') == community_url or post.get('community_url') == community_url
                        ]
                        
                        if community_posts:
                            # Get last post time
                            # Use 'timestamp' first, fall back to 'posted_at'
                            last_post = max(community_posts, key=lambda x: x.get('timestamp') or x.get('posted_at') or '')
                            
                            return {
                                'total_posts': len(community_posts),
                                'last_post_time': last_post.get('timestamp') or last_post.get('posted_at'),
                                'next_post_time': None  # Would be calculated based on schedule
                            }
                    except json.JSONDecodeError:
                        pass
            
            return {
                'total_posts': 0,
                'last_post_time': None,
                'next_post_time': None
            }
            
        except Exception as e:
            self.logger.error(f"Error getting community history for {community_url}: {e}")
            return {
                'total_posts': 0,
                'last_post_time': None,
                'next_post_time': None
            }
    
    def set_callbacks(self, start_callback=None, stop_callback=None, pause_callback=None):
        """Set callback functions for bot operations."""
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.pause_callback = pause_callback
    
    def set_post_manager(self, post_manager):
        """Set the post manager instance."""
        self.post_manager = post_manager
    
    def run(self, host='127.0.0.1', port=5000, debug=False):
        """Start the web server."""
        try:
            # Start the persistent browser event loop
            browser_event_loop.start()
            self.logger.info("Browser event loop initialized")
            
            self.logger.info(f"Starting web GUI server on http://{host}:{port}")
            print(f"Web GUI available at: http://{host}:{port}")
            self.socketio.run(self.app, host=host, port=port, debug=debug, use_reloader=False)
        except Exception as e:
            self.logger.error(f"Web server error: {e}")
            raise
        finally:
            # Stop the browser event loop when server shuts down
            browser_event_loop.stop()
    
    def close(self):
        """Close the web server."""
        # Stop the browser event loop
        browser_event_loop.stop()
        # Flask server will be closed when the process ends


def create_web_gui(config: Dict) -> WebGUIServer:
    """Factory function to create web GUI."""
    return WebGUIServer(config)
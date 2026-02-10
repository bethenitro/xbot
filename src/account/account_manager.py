"""
Account management system for the Enhanced Twitter Bot.
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Optional, List, Callable
from pathlib import Path
import json

from ..models.proxy import AccountData
from ..utils.file_manager import FileManager


class AccountManager:
    """Manages Twitter account operations and data."""
    
    def __init__(self, config: Dict):
        """Initialize account manager."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.file_manager = FileManager()
        
        # Account storage
        self.accounts: Dict[str, AccountData] = {}
        self.account_file = Path("data/accounts.json")
        
        # Active login sessions
        self.active_sessions: Dict[str, Any] = {}
        
        # Load existing accounts
        self.load_accounts()
        
        # Clean up any orphaned browser profiles
        self.cleanup_orphaned_browser_profiles()
    
    def load_accounts(self) -> None:
        """Load accounts from file."""
        try:
            if self.account_file.exists():
                # Read and parse JSON directly
                with open(self.account_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                for username, account_data in data.items():
                    self.accounts[username] = AccountData.from_dict(account_data)
                self.logger.info(f"Loaded {len(self.accounts)} accounts")
            else:
                self.logger.info("No existing account file found")
        except Exception as e:
            self.logger.error(f"Failed to load accounts: {e}")
    
    def save_accounts(self) -> None:
        """Save accounts to file."""
        try:
            # Ensure data directory exists
            self.account_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to serializable format
            data = {
                username: account.to_dict() 
                for username, account in self.accounts.items()
            }
            
            # Write JSON directly
            with open(self.account_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            self.logger.debug(f"Saved {len(self.accounts)} accounts")
        except Exception as e:
            self.logger.error(f"Failed to save accounts: {e}")
    
    async def add_account(self, username: str, preferred_proxy: str = None,
                         use_proxy: bool = True, login_callback: Callable = None) -> bool:
        """Add a new Twitter account."""
        try:
            if username in self.accounts:
                self.logger.warning(f"Account {username} already exists")
                return False
            
            # Create account data
            account = AccountData(
                username=username,
                preferred_proxy=preferred_proxy,
                use_proxy=use_proxy,
                cookies_file=f"sessions/{username}_cookies.json"
            )
            
            # Perform login process
            success = await self._perform_login(account, login_callback)
            
            if success:
                self.accounts[username] = account
                self.save_accounts()
                proxy_info = f" with proxy {preferred_proxy}" if preferred_proxy and use_proxy else ""
                self.logger.info(f"Successfully added account: {username}{proxy_info}")
                return True
            else:
                self.logger.error(f"Failed to add account: {username}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error adding account {username}: {e}")
            return False
    
    async def _perform_login(self, account: AccountData, login_callback: Callable = None) -> bool:
        """Perform login process for an account."""
        try:
            # Import browser factory
            from ..browser.browser_factory import browser_factory
            
            # Get proxy configuration if needed
            proxy_config = None
            if account.use_proxy and account.preferred_proxy:
                # Import proxy manager to get proxy data
                from ..proxy.proxy_manager import ProxyManager
                proxy_manager = ProxyManager(self.config)
                
                if account.preferred_proxy in proxy_manager.proxies:
                    proxy_data = proxy_manager.proxies[account.preferred_proxy]
                    proxy_config = proxy_data.url
                    self.logger.info(f"Using proxy {proxy_config} for account {account.username}")
                else:
                    self.logger.warning(f"Preferred proxy {account.preferred_proxy} not found for account {account.username}")
            
            # Initialize browser using factory
            browser = browser_factory.create_driver(self.config)
            
            try:
                # Start browser session with consistent fingerprint
                success = await browser.launch_browser(
                    proxy_config=proxy_config, 
                    headless=False,
                    fingerprint_data=account.fingerprint_data,
                    account_username=account.username
                )
                if not success:
                    return False
                
                # Save fingerprint data for new accounts
                if not account.fingerprint_data:
                    account.fingerprint_data = browser.get_current_fingerprint()
                    self.logger.info(f"Saved fingerprint data for account {account.username}")
                
                # Browser is ready for manual navigation (user will navigate manually)
                self.logger.info(f"Browser ready for manual navigation - account: {account.username}")
                
                # Wait for manual login if callback provided
                if login_callback:
                    await login_callback(f"Please navigate to your desired platform and login to account: {account.username}")
                
                # Wait for login completion (check for home page or dashboard)
                login_success = await self._wait_for_login_completion(browser)
                
                if login_success:
                    # Save cookies and update fingerprint
                    cookies_list = await browser.get_cookies()
                    await self.save_account_cookies(account, cookies_list)
                    account.update_login()
                    return True
                else:
                    self.logger.error(f"Login timeout or failed for {account.username}")
                    return False
                    
            finally:
                await browser.close_browser()
                
        except Exception as e:
            self.logger.error(f"Login process failed for {account.username}: {e}")
            return False
    
    async def _wait_for_login_completion(self, browser, timeout: int = 300) -> bool:
        """Wait for login to complete by checking URL changes."""
        try:
            start_time = asyncio.get_event_loop().time()
            
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                try:
                    current_url = browser.get_current_url()
                    
                    # Check if we're on the home page (login successful)
                    if "twitter.com/home" in current_url or "x.com/home" in current_url:
                        return True
                    
                    # Check if still on login page
                    if "login" in current_url:
                        await asyncio.sleep(2)
                        continue
                    
                    # Check for other success indicators
                    if any(indicator in current_url for indicator in ["/home", "/compose"]):
                        return True
                    
                    # If we can't get URL (browser closed/crashed), consider it incomplete
                    await asyncio.sleep(2)
                    
                except Exception as url_error:
                    self.logger.warning(f"Could not get current URL: {url_error}")
                    # If browser is not accessible, wait a bit and try again
                    await asyncio.sleep(2)
                    continue
            
            # Timeout reached - for manual login, this might be acceptable
            self.logger.warning("Login completion timeout reached")
            return False
            
        except Exception as e:
            self.logger.error(f"Error waiting for login completion: {e}")
            return False
    
    async def save_account_cookies(self, account: AccountData, cookies: List[Dict]) -> None:
        """Save account cookies."""
        try:
            # Ensure sessions directory exists
            sessions_dir = Path("sessions")
            sessions_dir.mkdir(exist_ok=True)
            
            # Save cookies as plain JSON (no encryption)
            cookie_data = {"encrypted": False, "data": cookies}
            
            # Save to file
            cookie_file = sessions_dir / f"{account.username}_cookies.json"
            with open(cookie_file, 'w', encoding='utf-8') as f:
                json.dump(cookie_data, f, indent=2, ensure_ascii=False)
            
            account.cookies_file = str(cookie_file)
            self.logger.info(f"Saved cookies for account: {account.username}")
            
        except Exception as e:
            self.logger.error(f"Failed to save cookies for {account.username}: {e}")
    
    async def load_account_cookies(self, account: AccountData) -> Optional[List[Dict]]:
        """Load account cookies."""
        try:
            if not account.cookies_file or not Path(account.cookies_file).exists():
                return None
            
            # Read and parse JSON directly
            with open(account.cookies_file, 'r', encoding='utf-8') as f:
                cookie_data = json.load(f)
            
            # Just return the data (no decryption needed)
            cookies = cookie_data["data"]
            
            return cookies
            
        except Exception as e:
            self.logger.error(f"Failed to load cookies for {account.username}: {e}")
            return None
    
    def remove_account(self, username: str) -> bool:
        """Remove an account and cleanup all associated data."""
        try:
            if username not in self.accounts:
                return False
            
            account = self.accounts[username]
            
            # Remove cookies file
            if account.cookies_file and Path(account.cookies_file).exists():
                Path(account.cookies_file).unlink()
                self.logger.info(f"Removed cookies file for account: {username}")
            
            # Remove ZenDriver browser profile directory
            import shutil
            zendriver_profile_dir = Path(f"sessions/zendriver_profiles/{username}")
            if zendriver_profile_dir.exists():
                shutil.rmtree(zendriver_profile_dir)
                self.logger.info(f"Removed ZenDriver profile directory for account: {username}")
            
            # Remove from memory and save
            del self.accounts[username]
            self.save_accounts()
            
            self.logger.info(f"Successfully removed account and all associated data: {username}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to remove account {username}: {e}")
            return False
    
    def get_account(self, username: str) -> Optional[AccountData]:
        """Get account by username."""
        return self.accounts.get(username)
    
    def get_all_accounts(self) -> List[AccountData]:
        """Get all accounts."""
        return list(self.accounts.values())
    
    def get_all_accounts_dict(self) -> Dict[str, AccountData]:
        """Get all accounts as dictionary."""
        return self.accounts.copy()
    
    def get_active_accounts(self) -> List[AccountData]:
        """Get all active accounts."""
        return [account for account in self.accounts.values() if account.is_active]
    
    def update_account_proxy(self, username: str, preferred_proxy: str = None, use_proxy: bool = True) -> bool:
        """Update account's proxy settings."""
        try:
            if username not in self.accounts:
                return False
            
            account = self.accounts[username]
            account.preferred_proxy = preferred_proxy
            account.use_proxy = use_proxy
            
            self.save_accounts()
            
            proxy_info = f" to {preferred_proxy}" if preferred_proxy and use_proxy else " (disabled)"
            self.logger.info(f"Updated proxy settings for account {username}{proxy_info}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update proxy for {username}: {e}")
            return False
    
    def toggle_account_status(self, username: str) -> bool:
        """Toggle account active/inactive status."""
        try:
            if username not in self.accounts:
                return False
            
            account = self.accounts[username]
            account.is_active = not account.is_active
            
            self.save_accounts()
            
            status = "activated" if account.is_active else "deactivated"
            self.logger.info(f"Account {username} {status}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to toggle status for {username}: {e}")
            return False
    
    def cleanup_orphaned_browser_profiles(self) -> int:
        """
        Clean up browser profile directories for accounts that no longer exist.
        
        Returns:
            Number of orphaned directories cleaned up
        """
        try:
            import shutil
            
            zendriver_profiles_dir = Path("sessions/zendriver_profiles")
            if not zendriver_profiles_dir.exists():
                return 0
            
            cleaned_count = 0
            current_usernames = set(self.accounts.keys())
            
            # Check each directory in zendriver_profiles
            for profile_dir in zendriver_profiles_dir.iterdir():
                if profile_dir.is_dir() and profile_dir.name not in ["default"]:
                    # If directory name doesn't match any current account, it's orphaned
                    if profile_dir.name not in current_usernames:
                        shutil.rmtree(profile_dir)
                        self.logger.info(f"Cleaned up orphaned browser profile: {profile_dir.name}")
                        cleaned_count += 1
            
            if cleaned_count > 0:
                self.logger.info(f"Cleaned up {cleaned_count} orphaned browser profile directories")
            
            return cleaned_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup orphaned browser profiles: {e}")
            return 0
    
    def get_account_stats(self) -> Dict[str, int]:
        """Get account statistics."""
        stats = {
            'total': len(self.accounts),
            'active': 0,
            'suspended': 0,
            'failed': 0,
            'unknown': 0
        }
        
        for account in self.accounts.values():
            if account.status == 'active':
                stats['active'] += 1
            elif account.status == 'suspended':
                stats['suspended'] += 1
            elif account.status == 'failed':
                stats['failed'] += 1
            else:
                stats['unknown'] += 1
        
        return stats
    
    async def refresh_account_cookies(self, account: AccountData) -> bool:
        """Refresh account cookies after successful posting."""
        try:
            # Import browser factory
            from ..browser.browser_factory import browser_factory
            
            # Get proxy configuration
            proxy_config = None
            if account.use_proxy and account.preferred_proxy:
                from ..proxy.proxy_manager import ProxyManager
                proxy_manager = ProxyManager(self.config)
                
                if account.preferred_proxy in proxy_manager.proxies:
                    proxy_data = proxy_manager.proxies[account.preferred_proxy]
                    proxy_config = proxy_data.url
            
            # Initialize browser with consistent fingerprint using factory
            browser = browser_factory.create_driver(self.config)
            
            try:
                # Launch with existing fingerprint and cookies
                success = await browser.launch_browser(
                    proxy_config=proxy_config,
                    headless=True,  # Silent refresh
                    fingerprint_data=account.fingerprint_data,
                    account_username=account.username
                )
                if not success:
                    return False
                
                # Load existing cookies
                existing_cookies = await self.load_account_cookies(account)
                if existing_cookies:
                    await browser.set_cookies(existing_cookies)
                
                # Don't navigate automatically - cookies will be refreshed when user navigates
                self.logger.info(f"Browser ready for cookie refresh - account: {account.username}")
                
                # Get updated cookies
                updated_cookies = await browser.get_cookies()
                if updated_cookies:
                    await self.save_account_cookies(account, updated_cookies)
                    self.logger.info(f"Refreshed cookies for account {account.username}")
                    return True
                
                return False
                
            finally:
                await browser.close_browser()
                
        except Exception as e:
            self.logger.error(f"Failed to refresh cookies for {account.username}: {e}")
            return False
    
    async def test_account_login(self, username: str) -> bool:
        """Test if account can login successfully."""
        try:
            account = self.get_account(username)
            if not account:
                return False
            
            # Load cookies and test
            cookies = await self.load_account_cookies(account)
            if not cookies:
                return False
            
            # Import browser factory
            from ..browser.browser_factory import browser_factory
            
            browser = browser_factory.create_driver(self.config)
            
            try:
                success = await browser.launch_browser(headless=True, account_username=account.username)
                if not success:
                    return False
                
                # Set cookies in the correct format
                if cookies:
                    await browser.set_cookies(cookies)
                
                # Don't navigate automatically - just check if cookies are valid
                self.logger.info(f"Testing account cookies without navigation - account: {account.username}")
                
                # For now, assume cookies are valid if they exist
                # Real validation would happen when user actually navigates
                success = True
                
                if success:
                    account.status = "active"
                else:
                    account.status = "failed"
                
                self.save_accounts()
                return success
                
            finally:
                await browser.close_browser()
                
        except Exception as e:
            self.logger.error(f"Failed to test account login for {username}: {e}")
            return False
    
    async def open_account_browser(self, username: str, allow_multiple: bool = False) -> bool:
        """Open a browser session for an existing account."""
        try:
            if username not in self.accounts:
                self.logger.error(f"Account {username} not found")
                return False
            
            # Check if already active (only if not allowing multiple)
            if not allow_multiple and username in self.active_sessions:
                self.logger.warning(f"Browser session already active for {username}")
                return True
            
            account = self.accounts[username]
            
            # Import browser factory
            from ..browser.browser_factory import browser_factory
            
            # Get proxy configuration if needed
            proxy_config = None
            if account.use_proxy and account.preferred_proxy:
                # Import proxy manager to get proxy data
                from ..proxy.proxy_manager import ProxyManager
                proxy_manager = ProxyManager(self.config)
                
                if account.preferred_proxy in proxy_manager.proxies:
                    proxy_data = proxy_manager.proxies[account.preferred_proxy]
                    proxy_config = proxy_data.url
                    self.logger.info(f"Using proxy {proxy_config} for account {account.username}")
            
            # Initialize browser using factory
            browser = browser_factory.create_driver(self.config)
            
            # Start browser session
            # Force headless=False for manual interaction
            success = await browser.launch_browser(
                proxy_config=proxy_config, 
                headless=False,
                fingerprint_data=account.fingerprint_data,
                account_username=account.username
            )
            
            if not success:
                return False
            
            # Load cookies
            cookies = await self.load_account_cookies(account)
            if cookies:
                await browser.set_cookies(cookies)
                self.logger.info(f"Loaded {len(cookies)} cookies for {username}")
                # Refresh to apply cookies
                await browser.navigate_to_url("https://x.com/home")
            else:
                self.logger.warning(f"No cookies found for {username}, user may need to login")
                await browser.navigate_to_url("https://x.com/i/flow/login")
            
            # Store the active session (with unique key if allowing multiple)
            if allow_multiple:
                # Use timestamp to create unique session key
                import time
                session_key = f"{username}_{int(time.time() * 1000)}"
            else:
                session_key = username
            
            self.active_sessions[session_key] = {
                'account': account,
                'browser': browser,
                'type': 'manual_browser'  # Distinguish from login session
            }
            
            # Start background task to monitor browser close and save cookies
            asyncio.create_task(self._monitor_browser_and_save_cookies(session_key, username))
            
            self.logger.info(f"Browser opened for account: {username}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error opening browser for {username}: {e}")
            return False

    async def start_login_session(self, username: str, preferred_proxy: str = None,
                                use_proxy: bool = True) -> bool:
        """Start a browser session for manual login."""
        try:
            if username in self.accounts:
                self.logger.warning(f"Account {username} already exists")
                return False
            
            # Create temporary account data
            account = AccountData(
                username=username,
                preferred_proxy=preferred_proxy,
                use_proxy=use_proxy,
                cookies_file=f"sessions/{username}_cookies.json"
            )
            
            # Import browser factory
            from ..browser.browser_factory import browser_factory
            
            # Get proxy configuration if needed
            proxy_config = None
            if account.use_proxy and account.preferred_proxy:
                # Import proxy manager to get proxy data
                from ..proxy.proxy_manager import ProxyManager
                proxy_manager = ProxyManager(self.config)
                
                if account.preferred_proxy in proxy_manager.proxies:
                    proxy_data = proxy_manager.proxies[account.preferred_proxy]
                    proxy_config = proxy_data.url
                    self.logger.info(f"Using proxy {proxy_config} for account {account.username}")
                else:
                    self.logger.warning(f"Preferred proxy {account.preferred_proxy} not found for account {account.username}")
            
            # Initialize browser using factory
            browser = browser_factory.create_driver(self.config)
            
            # Start browser session with consistent fingerprint
            success = await browser.launch_browser(
                proxy_config=proxy_config, 
                headless=False,
                fingerprint_data=account.fingerprint_data,
                account_username=account.username
            )
            if not success:
                return False
            
            # Save fingerprint data for new accounts
            if not account.fingerprint_data:
                account.fingerprint_data = browser.get_current_fingerprint()
                self.logger.info(f"Saved fingerprint data for account {account.username}")
            
            # Browser is ready for manual navigation (user will navigate manually)
            self.logger.info(f"Browser ready for manual navigation - account: {account.username}")
            
            # Store the active session
            self.active_sessions[username] = {
                'account': account,
                'browser': browser
            }
            
            return True
                
        except Exception as e:
            self.logger.error(f"Error starting login session for {username}: {e}")
            return False
    
    async def complete_login_session(self, username: str) -> bool:
        """Complete the manual login session and save the account."""
        try:
            if username not in self.active_sessions:
                self.logger.error(f"No active session for {username}")
                return False
            
            session = self.active_sessions[username]
            account = session['account']
            browser = session['browser']
            
            # Accept login as complete regardless of current page when user confirms
            # This allows flexibility for different login states and closed browsers
            try:
                # Try to get cookies if browser is still active
                cookies_list = await browser.get_cookies()
                if cookies_list and len(cookies_list) > 0:
                    await self.save_account_cookies(account, cookies_list)
                    self.logger.info(f"Saved {len(cookies_list)} cookies for account: {username}")
                else:
                    self.logger.info(f"No cookies available, but marking login as complete for account: {username}")
            except Exception as cookie_error:
                self.logger.warning(f"Could not retrieve cookies for {username}: {cookie_error}")
                self.logger.info(f"Marking login as complete anyway for account: {username}")
            
            # Update account login status
            account.update_login()
            
            # Add to accounts and save
            self.accounts[username] = account
            self.save_accounts()
            
            # Try to close browser if still active
            try:
                await browser.close_browser()
            except Exception as close_error:
                self.logger.warning(f"Could not close browser for {username}: {close_error}")
            
            # Clean up session
            del self.active_sessions[username]
            
            proxy_info = f" with proxy {account.preferred_proxy}" if account.preferred_proxy and account.use_proxy else ""
            self.logger.info(f"Successfully completed login for account: {username}{proxy_info}")
            return True
                
        except Exception as e:
            self.logger.error(f"Error completing login session for {username}: {e}")
            return False
    
    async def cancel_login_session(self, username: str) -> bool:
        """Cancel the manual login session."""
        try:
            if username not in self.active_sessions:
                return True  # Already cancelled or doesn't exist
            
            session = self.active_sessions[username]
            browser = session['browser']
            
            # Close browser
            await browser.close_browser()
            del self.active_sessions[username]
            
            self.logger.info(f"Cancelled login session for account: {username}")
            return True
                
        except Exception as e:
            self.logger.error(f"Error cancelling login session for {username}: {e}")
            return False
    async def _monitor_browser_and_save_cookies(self, session_key: str, username: str = None) -> None:
        """Monitor browser session and save cookies when it closes or periodically."""
        try:
            # If username not provided, extract from session_key
            if username is None:
                username = session_key.split('_')[0] if '_' in session_key else session_key
            
            if session_key not in self.active_sessions:
                return
                
            session = self.active_sessions[session_key]
            browser = session['browser']
            account = session['account']
            
            self.logger.info(f"Started cookie monitor for {username} (session: {session_key})")
            
            while session_key in self.active_sessions:
                try:
                    # Check if browser is still alive
                    if not await browser.is_browser_alive():
                        self.logger.info(f"Browser closed for {username}, saving final cookies...")
                        break
                        
                    # Periodically save cookies (every 30 seconds) while open
                    # to prevent loss if browser crashes
                    cookies = await browser.get_cookies()
                    if cookies:
                        await self.save_account_cookies(account, cookies)
                        self.logger.debug(f"Periodically saved cookies for {username}")
                except Exception as e:
                    self.logger.debug(f"Cookie monitor heart-beat check failed: {e}")
                    break
                    
                await asyncio.sleep(30)
            
            # Final save if possible when loop finishes
            try:
                # Try to get cookies one last time if possible
                if await browser.is_browser_alive():
                    cookies = await browser.get_cookies()
                    if cookies:
                        await self.save_account_cookies(account, cookies)
            except:
                pass
                
            # Cleanup session from active sessions if we detected it closed
            if session_key in self.active_sessions:
                del self.active_sessions[session_key]
                self.logger.info(f"Cleaned up session and saved final cookies for {username}")
                
        except Exception as e:
            self.logger.error(f"Error in cookie monitor for {username}: {e}")

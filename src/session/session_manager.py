"""
Session Manager component for cookie-based authentication management.
Handles browser sessions, authentication, and cookie management similar to redpost-bot.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..models.session import Session
from ..utils.file_utils import safe_file_read, safe_file_write, ensure_directory


class SessionManager:
    """Manages browser sessions and cookie-based authentication."""
    
    def __init__(self, sessions_dir: str = "sessions"):
        """
        Initialize session manager.
        
        Args:
            sessions_dir: Directory to store session data
        """
        self.sessions_dir = Path(sessions_dir)
        ensure_directory(str(self.sessions_dir))
        
        self.current_session: Optional[Session] = None
        self.logger = logging.getLogger(__name__)
    
    def create_session(self, browser_instance: Any = None) -> Session:
        """
        Create a new browser session.
        
        Args:
            browser_instance: Browser automation instance
            
        Returns:
            New Session object
        """
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        
        session = Session(
            session_id=session_id,
            browser_instance=browser_instance,
            created_at=datetime.now(),
            last_activity=datetime.now()
        )
        
        self.current_session = session
        self.logger.info(f"Created new session: {session_id}")
        
        return session
    
    async def save_cookies(self, session: Session, cookies: Dict[str, str] = None) -> bool:
        """
        Save authentication cookies after manual login.
        
        Args:
            session: Session to save cookies for
            cookies: Cookies to save (gets from browser if None)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if cookies is None and session.browser_instance:
                # Get cookies from browser
                cookies = await session.browser_instance.get_cookies()
            
            if not cookies:
                self.logger.warning("No cookies to save")
                return False
            
            # Filter for authentication-related cookies
            auth_cookies = self._filter_auth_cookies(cookies)
            
            if not auth_cookies:
                self.logger.warning("No authentication cookies found")
                return False
            
            # Save cookies as plain JSON (no encryption)
            session.cookies = {'data': auth_cookies}
            session.authenticated = True
            session.update_activity()
            
            # Save session to file
            success = self._save_session_to_file(session)
            
            if success:
                self.logger.info(f"Saved encrypted cookies for session: {session.session_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to save cookies: {e}")
            return False
    
    async def restore_cookies(self, session: Session) -> bool:
        """
        Restore saved cookies to maintain authentication.
        
        Args:
            session: Session to restore cookies for
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not session.cookies.get('data'):
                self.logger.warning("No cookies found in session")
                return False
            
            if not session.browser_instance:
                self.logger.error("No browser instance available for cookie restoration")
                return False
            
            # Get cookies (no decryption needed)
            auth_cookies = session.cookies['data']
            
            # Set cookies in browser
            success = await session.browser_instance.set_cookies(auth_cookies)
            
            if success:
                session.authenticated = True
                session.update_activity()
                self.logger.info(f"Restored cookies for session: {session.session_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to restore cookies: {e}")
            return False
    
    async def validate_session(self, session: Session) -> bool:
        """
        Check if current session is still authenticated.
        
        Args:
            session: Session to validate
            
        Returns:
            True if session is valid and authenticated, False otherwise
        """
        try:
            if not session or not session.browser_instance:
                return False
            
            # Check if session has expired
            if session.is_expired():
                self.logger.info(f"Session expired: {session.session_id}")
                return False
            
            # Check if we have authentication cookies
            if not session.has_valid_cookies():
                self.logger.warning(f"Session missing valid cookies: {session.session_id}")
                return False
            
            # Try to navigate to a Twitter page that requires authentication
            browser = session.browser_instance
            current_url = browser.get_current_url()
            
            # Navigate to Twitter home to check authentication
            if not current_url.startswith('https://twitter.com') and not current_url.startswith('https://x.com'):
                await browser.navigate_to_url('https://twitter.com/home')
            
            # Check if we're redirected to login page
            final_url = browser.get_current_url()
            
            if 'login' in final_url or 'signin' in final_url:
                self.logger.warning(f"Session not authenticated, redirected to login: {session.session_id}")
                session.authenticated = False
                return False
            
            # Update activity and confirm authentication
            session.update_activity()
            session.authenticated = True
            
            self.logger.debug(f"Session validation successful: {session.session_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Session validation failed: {e}")
            return False
    
    async def handle_authentication_challenge(self, session: Session) -> bool:
        """
        Handle login challenges and prompt for manual login.
        
        Args:
            session: Session that needs authentication
            
        Returns:
            True if authentication was successful, False otherwise
        """
        try:
            if not session.browser_instance:
                self.logger.error("No browser instance for authentication")
                return False
            
            browser = session.browser_instance
            
            # Navigate to Twitter login page
            self.logger.info("Navigating to Twitter login page for manual authentication...")
            await browser.navigate_to_url('https://twitter.com/login')
            
            # Wait for manual login (this would be handled by GUI in full implementation)
            self.logger.info("Please complete manual login in the browser window...")
            self.logger.info("The system will wait for authentication to complete...")
            
            # Poll for successful authentication (check for redirect away from login)
            max_wait_time = 300  # 5 minutes
            check_interval = 5   # Check every 5 seconds
            
            for _ in range(max_wait_time // check_interval):
                current_url = browser.get_current_url()
                
                # Check if we're no longer on login page
                if 'login' not in current_url and 'signin' not in current_url:
                    # Verify we're on a valid Twitter page
                    if current_url.startswith('https://twitter.com') or current_url.startswith('https://x.com'):
                        self.logger.info("Manual login detected, saving authentication cookies...")
                        
                        # Save cookies after successful login
                        success = await self.save_cookies(session)
                        
                        if success:
                            self.logger.info("Authentication successful and cookies saved")
                            return True
                
                # Wait before next check
                import asyncio
                await asyncio.sleep(check_interval)
            
            self.logger.warning("Authentication timeout - manual login not completed")
            return False
            
        except Exception as e:
            self.logger.error(f"Authentication challenge handling failed: {e}")
            return False
    
    async def clear_session_data(self, session: Session) -> None:
        """
        Clear authentication data when switching accounts.
        
        Args:
            session: Session to clear
        """
        try:
            session.clear_authentication()
            
            # Clear cookies from browser if available
            if session.browser_instance:
                browser = session.browser_instance
                await browser.execute_script("document.cookie.split(';').forEach(function(c) { document.cookie = c.replace(/^ +/, '').replace(/=.*/, '=;expires=' + new Date().toUTCString() + ';path=/'); });")
            
            # Remove session file
            session_file = self.sessions_dir / f"{session.session_id}.json"
            if session_file.exists():
                session_file.unlink()
            
            self.logger.info(f"Cleared session data: {session.session_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to clear session data: {e}")
    
    def load_session_from_file(self, session_id: str, browser_instance: Any = None) -> Optional[Session]:
        """
        Load session from file.
        
        Args:
            session_id: ID of session to load
            browser_instance: Browser instance to associate with session
            
        Returns:
            Session object if found, None otherwise
        """
        try:
            session_file = self.sessions_dir / f"{session_id}.json"
            
            if not session_file.exists():
                return None
            
            content = safe_file_read(str(session_file))
            if not content:
                return None
            
            session_data = json.loads(content)
            session = Session.from_dict(session_data, browser_instance)
            
            self.logger.info(f"Loaded session from file: {session_id}")
            return session
            
        except Exception as e:
            self.logger.error(f"Failed to load session from file: {e}")
            return None
    
    def get_available_sessions(self) -> List[str]:
        """
        Get list of available session IDs.
        
        Returns:
            List of session IDs
        """
        try:
            session_files = list(self.sessions_dir.glob("session_*.json"))
            session_ids = [f.stem for f in session_files]
            
            return session_ids
            
        except Exception as e:
            self.logger.error(f"Failed to get available sessions: {e}")
            return []
    
    def cleanup_expired_sessions(self, max_age_hours: int = 24) -> int:
        """
        Clean up expired session files.
        
        Args:
            max_age_hours: Maximum age of sessions to keep
            
        Returns:
            Number of sessions cleaned up
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            cleaned_count = 0
            
            for session_file in self.sessions_dir.glob("session_*.json"):
                try:
                    content = safe_file_read(str(session_file))
                    if content:
                        session_data = json.loads(content)
                        created_at = datetime.fromisoformat(session_data['created_at'])
                        
                        if created_at < cutoff_time:
                            session_file.unlink()
                            cleaned_count += 1
                            self.logger.debug(f"Cleaned up expired session: {session_file.stem}")
                
                except Exception as e:
                    self.logger.warning(f"Error processing session file {session_file}: {e}")
            
            if cleaned_count > 0:
                self.logger.info(f"Cleaned up {cleaned_count} expired sessions")
            
            return cleaned_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0
    
    def _filter_auth_cookies(self, cookies: List[Dict]) -> List[Dict]:
        """
        Filter cookies to keep only authentication-related ones.
        
        Args:
            cookies: List of cookie dictionaries from ZenDriver
            
        Returns:
            Filtered list of authentication cookies
        """
        # Common Twitter authentication cookie names
        auth_cookie_names = [
            'auth_token',
            'ct0',
            'twid',
            'remember_checked_on',
            'kdt',
            'auth_multi',
            'guest_id',
            'personalization_id'
        ]
        
        filtered_cookies = []
        
        # Handle list of dictionaries (ZenDriver format)
        if isinstance(cookies, list):
            for cookie in cookies:
                cookie_name = cookie.get('name', '').lower()
                if any(auth_name in cookie_name for auth_name in auth_cookie_names):
                    filtered_cookies.append(cookie)
        # Handle dictionary (legacy format)
        elif isinstance(cookies, dict):
            for name, value in cookies.items():
                if any(auth_name in name.lower() for auth_name in auth_cookie_names):
                    filtered_cookies.append({
                        'name': name,
                        'value': value,
                        'domain': '.twitter.com',
                        'path': '/'
                    })
        
        return filtered_cookies
    
    def _save_session_to_file(self, session: Session) -> bool:
        """
        Save session data to file.
        
        Args:
            session: Session to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            session_file = self.sessions_dir / f"{session.session_id}.json"
            session_data = session.to_dict()
            
            content = json.dumps(session_data, indent=2, ensure_ascii=False)
            success = safe_file_write(str(session_file), content)
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to save session to file: {e}")
            return False
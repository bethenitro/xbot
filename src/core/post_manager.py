"""
Post Manager component - orchestrates the overall posting workflow.
Coordinates between all components and manages posting operations.
"""

import logging
import time
import threading
import asyncio
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from pathlib import Path

from ..config.manager import ConfigurationManager
from ..utils.file_manager import FileManager
from ..browser.browser_factory import browser_factory
from ..session.session_manager import SessionManager
from ..account.account_manager import AccountManager
from ..behavior.human_behavior_simulator import HumanBehaviorSimulator
from ..twitter.twitter_interface import TwitterInterface
from ..posting.queue_manager import QueueManager
from ..posting.posting_scheduler import PostingScheduler
from ..stealth.stealth_engine import StealthEngine
from ..error.error_handler import ErrorHandler
from ..models.post import Post


class PostManager:
    """Orchestrates the overall posting workflow and coordinates between components."""
    
    def __init__(self, config_manager: ConfigurationManager):
        """
        Initialize post manager.
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.config = config_manager.get_config()
        self.logger = logging.getLogger(__name__)
        
        # Component instances
        self.file_manager = FileManager()
        self.browser_driver = None
        self.session_manager = SessionManager()
        self.account_manager = AccountManager(self.config.to_dict())
        self.behavior_simulator = HumanBehaviorSimulator(self.config.behavior_settings.__dict__)
        self.twitter_interface: Optional[TwitterInterface] = None
        self.queue_manager = QueueManager(self.file_manager)
        
        # Initialize posting scheduler with randomness config
        scheduler_config = {
            'randomness_percent': getattr(self.config.posting_intervals, 'randomness_percent', 25),
            'auto_refresh_cookies': getattr(self.config.stealth_settings, 'auto_refresh_cookies', True)
        }
        self.posting_scheduler = PostingScheduler(self.file_manager, scheduler_config)
        self.stealth_engine = StealthEngine(self.config.stealth_settings.__dict__)
        self.error_handler = ErrorHandler(self.config.error_handling.__dict__)
        
        # Operation state - Posting
        self.is_running = False
        self.is_paused = False
        self.posting_thread: Optional[threading.Thread] = None
        self.posting_loop: Optional[asyncio.AbstractEventLoop] = None
        self.stop_event = threading.Event()
        
        # Operation state - Replies (separate from posting)
        self.is_reply_running = False
        self.is_reply_paused = False
        self.reply_thread: Optional[threading.Thread] = None
        self.reply_loop: Optional[asyncio.AbstractEventLoop] = None
        self.reply_stop_event = threading.Event()
        self.next_reply_time = None
        self.reply_interval_base = getattr(self.config, 'reply_settings', None).reply_interval if getattr(self.config, 'reply_settings', None) else 300
        self.reply_randomness = getattr(self.config, 'reply_settings', None).randomness_percent if getattr(self.config, 'reply_settings', None) else 25
        
        # Community cycling state
        self.cycle_communities = True
        self.current_community_index = 0
        self.community_list = []
        
        # Account cycling state (NEW - for multi-account posting)
        self.cycle_accounts = True
        self.current_account_index = 0
        self.active_accounts_list = []
        
        # Callbacks for GUI updates
        self.status_callback: Optional[Callable[[str], None]] = None
        self.error_callback: Optional[Callable[[str], None]] = None
        
        # Initialize error recovery callbacks
        self._setup_error_recovery()
    
    def start_posting(self) -> bool:
        """
        Initiate the posting process.
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            if self.is_running:
                self.logger.warning("Posting is already running")
                return False
            
            self.logger.info("Starting posting operations...")
            self._update_status("Starting...")
            
            # Start posting thread - loop management moved inside the thread
            self.is_running = True
            self.is_paused = False
            self.stop_event.clear()
            
            self.posting_thread = threading.Thread(target=self._posting_loop, daemon=True)
            self.posting_thread.start()
            
            # Note: Browser initialization now happens inside the posting thread
            # to ensure event loop consistency for ZenDriver.
            
            self._update_status("Running")
            self.logger.info("Posting operations thread started")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start posting: {e}")
            self._update_status("Error")
            self._show_error(f"Failed to start posting: {e}")
            return False
    
    def stop_posting(self) -> bool:
        """
        Stop all posting operations.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        try:
            if not self.is_running:
                self.logger.warning("Posting is not running")
                return False
            
            self.logger.info("Stopping posting operations...")
            self._update_status("Stopping...")
            
            # Signal stop and wait for thread
            self.stop_event.set()
            self.is_running = False
            
            if self.posting_thread and self.posting_thread.is_alive():
                self.posting_thread.join(timeout=15)
            
            self._update_status("Stopped")
            self.logger.info("Posting operations stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop posting: {e}")
            self._update_status("Error")
            return False
    
    def pause_posting(self) -> bool:
        """
        Pause posting operations.
        
        Returns:
            True if paused successfully, False otherwise
        """
        try:
            if not self.is_running:
                self.logger.warning("Cannot pause - posting is not running")
                return False
            
            self.is_paused = not self.is_paused
            status = "Paused" if self.is_paused else "Running"
            
            self._update_status(status)
            self.logger.info(f"Posting operations {status.lower()}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to pause posting: {e}")
            return False
    
    def start_replies(self) -> bool:
        """
        Start automated reply operations (separate from posting).
        
        Returns:
            True if started successfully, False otherwise
        """
        try:
            if self.is_reply_running:
                self.logger.warning("Replies are already running")
                return False
            
            self.logger.info("Starting automated reply operations...")
            
            # Start reply thread
            self.is_reply_running = True
            self.is_reply_paused = False
            self.reply_stop_event.clear()
            
            self.reply_thread = threading.Thread(target=self._reply_loop, daemon=True)
            self.reply_thread.start()
            
            self.logger.info("Reply operations thread started")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start replies: {e}")
            return False
    
    def stop_replies(self) -> bool:
        """
        Stop automated reply operations.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        try:
            if not self.is_reply_running:
                self.logger.warning("Replies are not running")
                return False
            
            self.logger.info("Stopping reply operations...")
            
            # Signal stop and wait for thread
            self.reply_stop_event.set()
            self.is_reply_running = False
            
            if self.reply_thread and self.reply_thread.is_alive():
                self.reply_thread.join(timeout=15)
            
            self.logger.info("Reply operations stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop replies: {e}")
            return False
    
    def pause_replies(self) -> bool:
        """
        Pause reply operations.
        
        Returns:
            True if paused successfully, False otherwise
        """
        try:
            if not self.is_reply_running:
                self.logger.warning("Cannot pause - replies are not running")
                return False
            
            self.is_reply_paused = not self.is_reply_paused
            status = "Paused" if self.is_reply_paused else "Running"
            
            self.logger.info(f"Reply operations {status.lower()}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to pause replies: {e}")
            return False
    
    def _reply_loop(self) -> None:
        """Automated reply loop running in separate thread."""
        # Create dedicated event loop for reply thread
        self.reply_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.reply_loop)
        
        try:
            self.logger.info("Reply loop started with dedicated event loop")
            
            # Schedule first reply to happen immediately
            try:
                from datetime import datetime
                self.next_reply_time = datetime.now()
                self.logger.info(f"First reply scheduled at {self.next_reply_time} (immediately)")
            except Exception:
                self.next_reply_time = None
            
            while self.is_reply_running and not self.reply_stop_event.is_set():
                try:
                    # Check if paused
                    if self.is_reply_paused:
                        time.sleep(5)
                        continue
                    
                    # Check if it's time to send a reply
                    if self.next_reply_time:
                        from datetime import datetime
                        now = datetime.now()
                        if now >= self.next_reply_time:
                            try:
                                # Load accounts if needed
                                if not self.active_accounts_list:
                                    self._load_accounts_list()
                                
                                # Select account to use for reply
                                account = self._get_current_account()
                                if account:
                                    # Pick random caption and images (force image for replies)
                                    content, images = self._select_random_caption_and_images(force_image=True)
                                    self.logger.info(f"Automated reply: @{account.username} -> '{content[:30]}...' (images={len(images)})")
                                    result = self.reply_loop.run_until_complete(
                                        self._reply_to_random_tweet(account, content, images)
                                    )
                                    if result:
                                        self.logger.info("✅ Automated reply sent successfully")
                                    else:
                                        self.logger.warning("❌ Automated reply failed")
                                    # Advance account for next reply
                                    self._advance_to_next_account()
                                else:
                                    self.logger.warning("No account available for automated reply")
                            except Exception as e:
                                self.logger.error(f"Error during automated reply: {e}")
                            finally:
                                # Schedule next reply
                                try:
                                    self._schedule_next_reply()
                                    self.logger.info(f"Next reply scheduled at {self.next_reply_time}")
                                except Exception:
                                    self.next_reply_time = None
                                time.sleep(2)
                        else:
                            # Wait until next reply time
                            time.sleep(5)
                    else:
                        # No reply scheduled, wait
                        time.sleep(10)
                    
                except Exception as e:
                    self.logger.error(f"Error in reply loop: {e}")
                    time.sleep(10)
            
            self.logger.info("Reply loop stopping...")
            
        except Exception as e:
            self.logger.error(f"Fatal error in reply loop: {e}")
        finally:
            self.reply_loop.close()
            self.reply_loop = None
            self.logger.info("Reply loop thread ended and loop closed")
    
    def process_next_post(self) -> bool:
        """
        Handle the next post in the queue with MULTI-ACCOUNT support.
        
        MULTI-ACCOUNT IMPLEMENTATION: Every account posts to every community
        
        Returns:
            True if post was processed successfully, False otherwise
        """
        try:
            # Check if we're rate limited
            if self.error_handler.check_rate_limits():
                self.logger.info("Rate limited, skipping post processing")
                return False
            
            # Load community list if not loaded
            if not self.community_list:
                self._load_community_list()
            
            if not self.community_list:
                self.logger.warning("No communities available for posting")
                return False
            
            # Load accounts list if not loaded
            if not self.active_accounts_list:
                self._load_accounts_list()
            
            if not self.active_accounts_list:
                self.logger.warning("No active accounts available for posting")
                return False
            
            # Get next due post
            next_group_info = self.posting_scheduler.get_next_due_post()
            if not next_group_info:
                self.logger.debug("No posts due for posting")
                return False
            
            group_name = next_group_info['name']
            
            # Get next post for this group
            next_post = self.queue_manager.get_next_post(group_name)
            if not next_post:
                self.logger.debug(f"No available posts for group: {group_name}")
                return False
            
            # MULTI-ACCOUNT STRATEGY: Every account posts to every community
            # Note: This synchronous version is mainly for manual testing
            # The main automated posting uses the async version
            success = self._execute_multi_account_posting_sync(next_post, group_name)
            
            if success:
                # Mark post as completed and update schedule
                self.queue_manager.mark_post_completed(next_post.id, group_name)
                self.posting_scheduler.schedule_next_post(group_name)
                self.error_handler.reset_failure_count()
                
                self.logger.info(f"✅ Successfully completed multi-account posting for post: {next_post.id}")
            else:
                # Handle posting failure
                self._handle_posting_failure(next_post, group_name)
            
            return success
            
        except Exception as e:
            context = {
                'component': 'post_manager',
                'operation': 'process_next_post'
            }
            self.error_handler.handle_error(e, context)
            return False
    
    def _execute_multi_account_posting_sync(self, post: Post, group_name: str) -> bool:
        """
        Synchronous wrapper for multi-account posting.
        
        Args:
            post: Post to process
            group_name: Community group name
            
        Returns:
            True if at least one posting succeeded, False if all failed
        """
        try:
            # Create event loop if none exists
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Run the async multi-account posting
            return loop.run_until_complete(self._execute_multi_account_posting(post, group_name))
            
        except Exception as e:
            self.logger.error(f"Error in synchronous multi-account posting: {e}")
            return False
    
    def handle_posting_error(self, error: Exception, context: Dict[str, Any] = None) -> None:
        """
        Handle posting failures with error recovery.
        
        Args:
            error: Exception that occurred
            context: Additional context information
        """
        try:
            context = context or {}
            context.update({
                'component': 'post_manager',
                'operation': 'posting'
            })
            
            # Use error handler for recovery
            recovery_success = self.error_handler.handle_error(error, context)
            
            if not recovery_success:
                self.logger.error("Error recovery failed, may need manual intervention")
                self._show_error(f"Posting error: {error}")
            
        except Exception as e:
            self.logger.error(f"Error in error handling: {e}")
    
    def get_status_info(self) -> Dict[str, Any]:
        """
        Get current status information.
        
        Returns:
            Dictionary with status information
        """
        try:
            queue_status = self.queue_manager.get_queue_status()
            schedule_status = self.posting_scheduler.get_schedule_status()
            stealth_status = self.stealth_engine.get_stealth_status()
            error_stats = self.error_handler.get_error_statistics()
            
            # No persistent browser since we create new instances per post (like quick post)
            browser_alive = False
            
            return {
                'is_running': self.is_running,
                'is_paused': self.is_paused,
                'status_text': self._get_current_status(),
                'queue': queue_status,
                'schedule': schedule_status,
                'stealth': stealth_status,
                'errors': error_stats,
                'browser_alive': browser_alive
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get status info: {e}")
            return {}
    
    def set_callbacks(self, status_callback: Callable[[str], None] = None,
                     error_callback: Callable[[str], None] = None) -> None:
        """
        Set callback functions for GUI updates.
        
        Args:
            status_callback: Function to call for status updates
            error_callback: Function to call for error notifications
        """
        self.status_callback = status_callback
        self.error_callback = error_callback
    
    def set_community_cycling(self, enabled: bool) -> None:
        """
        Enable or disable community cycling.
        
        Args:
            enabled: Whether to enable community cycling
        """
        self.cycle_communities = enabled
        self.logger.info(f"Community cycling {'enabled' if enabled else 'disabled'}")
    
    def set_account_cycling(self, enabled: bool) -> None:
        """
        Enable or disable account cycling.
        
        Args:
            enabled: Whether to enable account cycling
        """
        self.cycle_accounts = enabled
        self.logger.info(f"Account cycling {'enabled' if enabled else 'disabled'}")
    
    def reset_community_cycle(self) -> None:
        """Reset community cycling to start from the first community."""
        self.current_community_index = 0
        self.logger.info("Community cycle reset to start from community 1")
    
    def reset_account_cycle(self) -> None:
        """Reset account cycling to start from the first account."""
        self.current_account_index = 0
        self.logger.info("Account cycle reset to start from account 1")
    
    def get_community_status(self) -> Dict[str, Any]:
        """
        Get current community cycling status.
        
        Returns:
            Dictionary with community status information
        """
        current_community = self._get_current_community() if self.community_list else None
        
        # Calculate progress
        progress_percentage = 0
        if self.community_list and len(self.community_list) > 0:
            progress_percentage = ((self.current_community_index + 1) / len(self.community_list)) * 100
        
        return {
            'cycling_enabled': self.cycle_communities,
            'total_communities': len(self.community_list),
            'current_index': self.current_community_index,
            'current_community': current_community,
            'current_community_short': current_community.split('/')[-1] if current_community else None,
            'progress_percentage': round(progress_percentage, 1),
            'communities': self.community_list,
            'next_community': self._get_next_community_preview(),
            'cycle_position': f"{self.current_community_index + 1}/{len(self.community_list)}" if self.community_list else "0/0"
        }
    
    def get_account_status(self) -> Dict[str, Any]:
        """
        Get current account cycling status.
        
        Returns:
            Dictionary with account status information
        """
        current_account = self._get_current_account()
        
        # Calculate progress
        progress_percentage = 0
        if self.active_accounts_list and len(self.active_accounts_list) > 0:
            progress_percentage = ((self.current_account_index + 1) / len(self.active_accounts_list)) * 100
        
        return {
            'cycling_enabled': self.cycle_accounts,
            'total_accounts': len(self.active_accounts_list),
            'current_index': self.current_account_index,
            'current_account': current_account.username if current_account else None,
            'current_account_obj': current_account,
            'progress_percentage': round(progress_percentage, 1),
            'accounts': [acc.username for acc in self.active_accounts_list],
            'next_account': self._get_next_account_preview(),
            'cycle_position': f"{self.current_account_index + 1}/{len(self.active_accounts_list)}" if self.active_accounts_list else "0/0"
        }
    
    def _get_next_community_preview(self) -> Optional[str]:
        """Get preview of what the next community will be after advancement."""
        if not self.community_list:
            return None
        
        next_index = self.current_community_index + 1
        if next_index >= len(self.community_list):
            next_index = 0  # Will cycle back to first
        
        return self.community_list[next_index]
    
    def _get_current_account(self):
        """
        Get the current account for posting.
        
        Returns:
            Current account object or None if no accounts available
        """
        if not self.active_accounts_list:
            self.logger.warning("No active accounts available for posting")
            return None
        
        # Ensure index is within bounds (safety check)
        if self.current_account_index >= len(self.active_accounts_list):
            self.logger.info(f"Account index {self.current_account_index} out of bounds, resetting to 0")
            self.current_account_index = 0
        
        current_account = self.active_accounts_list[self.current_account_index]
        self.logger.debug(f"Current account ({self.current_account_index + 1}/{len(self.active_accounts_list)}): @{current_account.username}")
        
        return current_account
    
    def _advance_to_next_account(self) -> None:
        """Advance to the next account in the cycle with proper restart logic."""
        if not self.active_accounts_list:
            self.logger.warning("Cannot advance account - no accounts available")
            return
        
        previous_index = self.current_account_index
        self.current_account_index += 1
        
        # If we've reached the end, cycle back to the beginning
        if self.current_account_index >= len(self.active_accounts_list):
            self.current_account_index = 0
            self.logger.info(f"🔄 Completed full account cycle! Restarting from account 1 (was at account {previous_index + 1}/{len(self.active_accounts_list)})")
        
        current_account = self._get_current_account()
        if current_account:
            self.logger.info(f"👤 Advanced to account {self.current_account_index + 1}/{len(self.active_accounts_list)}: @{current_account.username}")
        
        # Log cycle progress
        progress_percentage = ((self.current_account_index + 1) / len(self.active_accounts_list)) * 100
        self.logger.debug(f"Account cycle progress: {progress_percentage:.1f}% ({self.current_account_index + 1}/{len(self.active_accounts_list)})")
    
    def _get_next_account_preview(self) -> Optional[str]:
        """Get preview of what the next account will be after advancement."""
        if not self.active_accounts_list:
            return None
        
        next_index = self.current_account_index + 1
        if next_index >= len(self.active_accounts_list):
            next_index = 0  # Will cycle back to first
        
        return self.active_accounts_list[next_index].username

    def _compute_next_reply_delay(self) -> int:
        """Compute next reply delay (seconds) with configured randomness."""
        try:
            import random
            base = int(self.reply_interval_base)
            variation = int(base * (float(self.reply_randomness) / 100.0))
            offset = random.randint(-variation, variation) if variation > 0 else 0
            delay = max(1, base + offset)
            return delay
        except Exception:
            return int(self.reply_interval_base)

    def _schedule_next_reply(self) -> None:
        """Set `self.next_reply_time` based on computed delay."""
        from datetime import datetime, timedelta
        seconds = self._compute_next_reply_delay()
        self.next_reply_time = datetime.now() + timedelta(seconds=seconds)

    def _select_random_caption_and_images(self, force_image: bool = False):
        """Select a random caption from `data/captions.json` and 0-1 images from `data/images`.

        Args:
            force_image: If True, always include an image (for replies). If False, 70% chance.

        Returns: (content:str, images: List[str])
        """
        try:
            import random
            captions_file = self.file_manager.captions_json_file
            content = ""
            if captions_file.exists():
                data = captions_file.read_text(encoding='utf-8')
                try:
                    arr = __import__('json').loads(data)
                    if isinstance(arr, list) and arr:
                        item = random.choice(arr)
                        content = item.get('content', '') if isinstance(item, dict) else str(item)
                except Exception:
                    content = data.strip().split('\n')[0] if data else ""

            # Pick 0 or 1 image randomly
            images_dir = self.file_manager.data_dir / 'images'
            images = []
            if images_dir.exists() and images_dir.is_dir():
                files = [str(p) for p in images_dir.iterdir() if p.is_file()]
                if files:
                    # If force_image is True, always add an image. Otherwise 70% chance.
                    if force_image or random.random() < 0.7:
                        images = [random.choice(files)]

            return content or "", images
        except Exception as e:
            self.logger.debug(f"Failed to select caption/images: {e}")
            return "", []
    
    async def _initialize_browser_session(self) -> bool:
        """Initialize browser and session components."""
        try:
            self.logger.info("Initializing browser session...")
            
            # Determine which account to use
            active_accounts = self.account_manager.get_active_accounts()
            current_account = None
            
            if active_accounts:
                # Use the first active account for now (can be expanded to cycling)
                current_account = active_accounts[0]
                self.logger.info(f"Using active account: {current_account.username}")
            else:
                self.logger.warning("No active accounts found. Using default browser profile.")

            # Initialize browser driver using factory
            browser_config = self.config.browser_settings.__dict__
            browser_config.update(self.config.stealth_settings.__dict__)
            
            # Prepare launch parameters
            account_username = current_account.username if current_account else None
            proxy_config = None
            fingerprint_data = None
            
            if current_account:
                fingerprint_data = current_account.fingerprint_data
                
                # Check for proxy
                if current_account.use_proxy and current_account.preferred_proxy:
                    # Initialize proxy manager temporarily to get details (should be injected really)
                    from ..proxy.proxy_manager import ProxyManager
                    proxy_manager = ProxyManager(self.config.to_dict())
                    if current_account.preferred_proxy in proxy_manager.proxies:
                        proxy_data = proxy_manager.proxies[current_account.preferred_proxy]
                        proxy_config = proxy_data.url
            
            self.browser_driver = browser_factory.create_driver(browser_config)
            
            # Launch browser with account context
            success = await self.browser_driver.launch_browser(
                proxy_config=proxy_config,
                fingerprint_data=fingerprint_data,
                account_username=account_username
            )
            
            if not success:
                self.logger.error("Failed to launch browser")
                return False
            
            # Restore cookies if account exists
            if current_account:
                cookies = await self.account_manager.load_account_cookies(current_account)
                if cookies:
                    success = await self.browser_driver.set_cookies(cookies)
                    if success:
                        self.logger.info(f"Restored session cookies for {current_account.username}")
                    else:
                        self.logger.warning(f"Failed to restore cookies for {current_account.username}")
            
            # Initialize Twitter interface
            self.twitter_interface = TwitterInterface(self.browser_driver, self.behavior_simulator)
            
            # Create session (tracking object)
            session = self.session_manager.create_session(self.browser_driver)
            
            # Initialize stealth session
            success = await self.stealth_engine.initialize_stealth_session(
                self.browser_driver, 
                self.behavior_simulator
            )
            
            if not success:
                self.logger.warning("Stealth session initialization failed")
            
            # Check authentication
            if not await self.session_manager.validate_session(session):
                self.logger.info("Session not authenticated, attempting authentication...")
                # If we have an account but cookies failed, we might need manual login again
                # For now, we utilize the generic handler
                success = await self.session_manager.handle_authentication_challenge(session)
                
                if success and current_account:
                    # If manual auth succeeded, update the account cookies
                    new_cookies = await self.browser_driver.get_cookies()
                    await self.account_manager.save_account_cookies(current_account, new_cookies)
                    current_account.update_login()
                    self.account_manager.save_accounts()
                
                if not success:
                    self.logger.error("Authentication failed")
                    return False
            
            self.logger.info("Browser session initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize browser session: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    async def _cleanup_browser_session(self) -> None:
        """Cleanup browser and session resources."""
        try:
            if self.browser_driver:
                await self.browser_driver.close_browser()
                self.browser_driver = None
            
            self.twitter_interface = None
            
            self.logger.info("Browser session cleaned up")
            
        except Exception as e:
            self.logger.error(f"Error during browser cleanup: {e}")
    
    def _posting_loop(self) -> None:
        """Main posting loop running in separate thread with a dedicated event loop."""
        # Create a dedicated event loop for this thread
        self.posting_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.posting_loop)
        
        try:
            self.logger.info("Posting loop started with dedicated event loop")
            
            # No need to initialize persistent browser session since we create new instances per post
            # This matches the quick post behavior exactly
            
            while self.is_running and not self.stop_event.is_set():
                try:
                    # Check if paused
                    if self.is_paused:
                        time.sleep(5)
                        continue
                    
                    # Process next post (creates new browser instance like quick post)
                    post_processed = self.posting_loop.run_until_complete(self._process_next_post_async())
                    
                    if post_processed:
                        # Add stealth delay after posting
                        self.posting_loop.run_until_complete(self.stealth_engine.apply_stealth_delay(self.behavior_simulator, 5.0))
                    else:
                        # No posts to process, wait before checking again
                        time.sleep(10)
                    
                    # No need to check browser health since we create new instances per post
                    
                except Exception as e:
                    self.handle_posting_error(e)
                    time.sleep(10)  # Wait before retrying
            
            self.logger.info("Posting loop stopping...")
            
        except Exception as e:
            self.logger.error(f"Fatal error in posting loop: {e}")
            self._update_status("Error")
        finally:
            # No persistent browser to clean up
            self.posting_loop.close()
            self.posting_loop = None
            self.logger.info("Posting loop thread ended and loop closed")
    
    async def _process_next_post_async(self) -> bool:
        """
        MULTI-ACCOUNT IMPLEMENTATION: Every account posts to every community
        
        This method implements the requirement where:
        - Account 1 → Community 1, Community 2, Community 3
        - Account 2 → Community 1, Community 2, Community 3  
        - Account 3 → Community 1, Community 2, Community 3
        
        Returns:
            True if post was processed successfully, False otherwise
        """
        try:
            # Check if we're rate limited
            if self.error_handler.check_rate_limits():
                self.logger.info("Rate limited, skipping post processing")
                return False
            
            # Load community list if not loaded
            if not self.community_list:
                self._load_community_list()
            
            if not self.community_list:
                self.logger.warning("No communities available for posting")
                return False
            
            # Load accounts list if not loaded
            if not self.active_accounts_list:
                self._load_accounts_list()
            
            if not self.active_accounts_list:
                self.logger.warning("No active accounts available for posting")
                return False
            
            # Get next due post
            next_group_info = self.posting_scheduler.get_next_due_post()
            if not next_group_info:
                self.logger.debug("No posts due for posting")
                return False
            
            group_name = next_group_info['name']
            
            # Get next post for this group
            next_post = self.queue_manager.get_next_post(group_name)
            if not next_post:
                self.logger.debug(f"No available posts for group: {group_name}")
                return False
            
            # MULTI-ACCOUNT STRATEGY: Every account posts to every community
            success = await self._execute_multi_account_posting(next_post, group_name)
            
            if success:
                # Mark post as completed and update schedule
                self.queue_manager.mark_post_completed(next_post.id, group_name)
                self.posting_scheduler.schedule_next_post(group_name)
                self.error_handler.reset_failure_count()
                
                self.logger.info(f"✅ Successfully completed multi-account posting for post: {next_post.id}")
            else:
                # Handle posting failure
                self._handle_posting_failure(next_post, group_name)
            
            return success
            
        except Exception as e:
            context = {
                'component': 'post_manager',
                'operation': 'process_next_post'
            }
            self.error_handler.handle_error(e, context)
            return False
    
    async def _execute_multi_account_posting(self, post: Post, group_name: str) -> bool:
        """
        CONFIGURABLE CONCURRENT BROWSERS: Execute multi-account posting with configurable concurrency.
        
        OPTIMIZATION: Configurable concurrent posting with proper resource management.
        - Configurable number of concurrent browsers (1-5)
        - Proper cleanup between batches
        - Memory management
        - System resource monitoring
        
        Args:
            post: Post to process
            group_name: Community group name
            
        Returns:
            True if at least one posting succeeded, False if all failed
        """
        try:
            # Get max concurrent browsers from config
            max_concurrent = getattr(self.config.browser_settings, 'max_concurrent_browsers', 1)
            max_concurrent = max(1, min(5, max_concurrent))  # Ensure it's between 1-5
            
            total_posts = len(self.active_accounts_list) * len(self.community_list)
            successful_posts = 0
            failed_posts = 0
            
            self.logger.info(f"⚡ CONCURRENCY: Using {max_concurrent} concurrent browser{'s' if max_concurrent > 1 else ''}")

            # DISTRIBUTED MODE: 1 post per account per batch, distributed across communities
            self.logger.info(f"🔄 Account Distribution Mode: distributing accounts across communities to avoid pattern detection")
            
            if not self.community_list:
                self.logger.warning("No communities available")
                return False

            num_communities = len(self.community_list)
            # Use current global index as the base offset for rotation
            base_community_index = self.current_community_index
            
            total_posts = len(self.active_accounts_list)
            self.logger.info(f"🚀 Starting DISTRIBUTED multi-account posting: {len(self.active_accounts_list)} accounts -> {total_posts} total posts (1 each)")
            
            # Create all posting tasks
            all_tasks = []
            post_number = 1
            
            # Determine stable assignment per account first to Ensure Recycling
            # We use the STABLE list to determine the "next community" for each account
            # This guarantees that Account A cycles C0->C1->C2 regardless of execution order
            account_community_map = {}
            for idx, account in enumerate(self.active_accounts_list):
                 # Offset by global index AND account index to distribute them
                 # Account 0 gets (Base + 0) % N
                 # Account 1 gets (Base + 1) % N
                 assigned_community_index = (base_community_index + idx) % num_communities
                 community_url = self.community_list[assigned_community_index]
                 account_community_map[account.username] = community_url

            # Create all posting tasks (Randomized Execution Order)
            all_tasks = []
            post_number = 1
            
            import random 
            # Shuffle accounts locally to randomize order of execution (who posts first)
            # But the TARGET community is fixed by the stable map above
            batch_accounts = list(self.active_accounts_list)
            random.shuffle(batch_accounts)
            
            for account in batch_accounts:
                 community_url = account_community_map[account.username]
                 community_short = community_url.split('/')[-1]
                 
                 self.logger.info(f"📋 Plan: @{account.username} -> {community_short}")
                 
                 task_info = {
                    'account': account,
                    'community_url': community_url,
                    'community_short': community_short,
                    'post_number': post_number,
                    'total_posts': total_posts, # Correct total is 1 per account now
                    'content': post.content,
                    'image_paths': post.images
                }
                 all_tasks.append(task_info)
                 
                 post_number += 1
            
            # Update the base index for the NEXT batch so the rotation moves
            # We increment by 1 so the "window" of communities slides
            if self.cycle_communities:
                self.current_community_index = (self.current_community_index + 1) % num_communities
                self.logger.info(f"🔄 updated community cycle index to {self.current_community_index}")
            
            # Process tasks in batches based on max_concurrent
            if max_concurrent == 1:
                # Sequential processing (original behavior)
                self.logger.info("📱 Sequential processing mode (1 browser at a time)")
                for task in all_tasks:
                    try:
                        self.logger.info(f"📍 Post {task['post_number']}/{task['total_posts']}: @{task['account'].username} → {task['community_short']}")
                        self._update_status(f"Posting {task['post_number']}/{task['total_posts']}: @{task['account'].username}")
                        
                        success = await self._create_post_like_quick_post_optimized(
                            account=task['account'],
                            content=task['content'],
                            image_paths=task['image_paths'],
                            community_url=task['community_url'],
                            post_number=task['post_number'],
                            total_posts=task['total_posts']
                        )
                        
                        if success:
                            successful_posts += 1
                            self.logger.info(f"✅ Success {task['post_number']}/{task['total_posts']}: @{task['account'].username} → {task['community_short']}")
                            
                            # Update account stats
                            task['account'].update_post()
                            self.account_manager.save_accounts()
                            
                            # Add to global history for dashboard
                            history_entry = {
                                'post_id': f"auto_{int(time.time())}_{task['post_number']}",
                                'account': task['account'].username,
                                'community': task['community_url'],
                                'community_name': task['community_short'],
                                'content_preview': task['content'][:50] + "..." if len(task['content']) > 50 else task['content'],
                                'status': 'success',
                                'timestamp': datetime.now().isoformat()
                            }
                            self.file_manager.write_posting_history(history_entry)
                        else:
                            failed_posts += 1
                            self.logger.warning(f"❌ Failed {task['post_number']}/{task['total_posts']}: @{task['account'].username} → {task['community_short']}")
                        
                        # Progressive stealth delays
                        if task['post_number'] < task['total_posts']:
                            base_delay = 15.0
                            if task['post_number'] % 5 == 0:
                                base_delay += 10.0
                                self.logger.info(f"🧊 System cooldown: Extra delay after {task['post_number']} posts")
                            
                            delay_seconds = await self.stealth_engine.apply_stealth_delay(self.behavior_simulator, base_delay)
                            self.logger.info(f"⏱️  Stealth delay: {delay_seconds:.1f}s before next post")
                        
                    except Exception as e:
                        failed_posts += 1
                        self.logger.error(f"❌ Error in post {task['post_number']}/{task['total_posts']}: @{task['account'].username} → {task['community_short']}: {e}")
                        continue
            else:
                # Concurrent processing (new feature)
                self.logger.info(f"🔄 Concurrent processing mode ({max_concurrent} browsers at a time)")
                
                # Process in batches
                for batch_start in range(0, len(all_tasks), max_concurrent):
                    batch_end = min(batch_start + max_concurrent, len(all_tasks))
                    batch_tasks = all_tasks[batch_start:batch_end]
                    
                    self.logger.info(f"🔄 Processing batch {batch_start//max_concurrent + 1}: posts {batch_start + 1}-{batch_end}")
                    
                    # Create concurrent tasks for this batch
                    concurrent_tasks = []
                    for task in batch_tasks:
                        self.logger.info(f"📍 Queuing post {task['post_number']}/{task['total_posts']}: @{task['account'].username} → {task['community_short']}")
                        
                        coroutine = self._create_post_like_quick_post_optimized(
                            account=task['account'],
                            content=task['content'],
                            image_paths=task['image_paths'],
                            community_url=task['community_url'],
                            post_number=task['post_number'],
                            total_posts=task['total_posts']
                        )
                        concurrent_tasks.append((coroutine, task))
                    
                    # Execute batch concurrently
                    self._update_status(f"Concurrent posting: batch {batch_start//max_concurrent + 1}")
                    batch_results = await asyncio.gather(*[task[0] for task in concurrent_tasks], return_exceptions=True)
                    
                    # Process results
                    for i, result in enumerate(batch_results):
                        task = concurrent_tasks[i][1]
                        if isinstance(result, Exception):
                            failed_posts += 1
                            self.logger.error(f"❌ Exception in post {task['post_number']}: @{task['account'].username} → {task['community_short']}: {result}")
                        elif result:
                            successful_posts += 1
                            self.logger.info(f"✅ Success {task['post_number']}/{task['total_posts']}: @{task['account'].username} → {task['community_short']}")
                        else:
                            failed_posts += 1
                            self.logger.warning(f"❌ Failed {task['post_number']}/{task['total_posts']}: @{task['account'].username} → {task['community_short']}")
                    
                    # Batch-level cooldown (longer for concurrent processing)
                    if batch_end < len(all_tasks):
                        batch_cooldown = 30.0 + (max_concurrent * 5.0)  # Scale cooldown with concurrency
                        self.logger.info(f"🧊 Batch cooldown: {batch_cooldown}s before next batch")
                        await asyncio.sleep(batch_cooldown)
                        
                        # Force garbage collection after each batch
                        import gc
                        gc.collect()
                        self.logger.debug(f"🧹 Garbage collection performed after batch {batch_start//max_concurrent + 1}")
            
            # Log final results
            success_rate = (successful_posts / total_posts) * 100 if total_posts > 0 else 0
            self.logger.info(f"📊 CONFIGURABLE multi-account posting completed: {successful_posts}/{total_posts} successful ({success_rate:.1f}%)")
            self.logger.info(f"⚡ Used {max_concurrent} concurrent browser{'s' if max_concurrent > 1 else ''}")
            
            if successful_posts > 0:
                self.logger.info(f"✅ At least {successful_posts} posts succeeded - marking as successful")
                return True
            else:
                self.logger.error(f"❌ All {total_posts} posts failed - marking as failed")
                return False
            
        except Exception as e:
            self.logger.error(f"Fatal error in configurable multi-account posting: {e}")
            return False
    
    async def _process_single_post(self, post: Post, community_url: str) -> bool:
        """
        Process a single post using the EXACT same method as quick post.
        This creates a new browser instance for each post, just like quick post does.
        
        MULTI-ACCOUNT IMPLEMENTATION: Every account posts to every community
        
        Args:
            post: Post to process
            community_url: Community URL to post to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"Processing post: {post.id} to community: {community_url}")
            self._update_status(f"Posting: {post.id[:8]}...")
            
            # Get current account for posting (FIXED - proper multi-account cycling)
            current_account = self._get_current_account()
            if not current_account:
                self.logger.error("No current account available for posting")
                return False
            
            self.logger.info(f"Using account: @{current_account.username} for community: {community_url}")
            
            # Use the EXACT same method as quick post - create new browser instance
            success = await self._create_post_like_quick_post(
                account=current_account,
                content=post.content,
                image_paths=post.images,
                community_url=community_url
            )
            
            # Log the action for stealth assessment
            self.stealth_engine.log_action('post_creation', success, {
                'post_id': post.id,
                'community_url': community_url,
                'account': current_account.username
            })
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to process post {post.id}: {e}")
            return False
    
    async def _create_post_like_quick_post_optimized(self, account, content: str, image_paths: list, community_url: str = None, post_number: int = 1, total_posts: int = 1) -> bool:
        """
        OPTIMIZED version of _create_post_like_quick_post with enhanced resource management.
        
        OPTIMIZATIONS:
        - Better memory management
        - Explicit garbage collection
        - Enhanced error handling
        - Resource monitoring
        - Progressive delays for system stability
        
        Args:
            account: Account data object
            content: Post content text
            image_paths: List of image file paths
            community_url: Optional community URL to post to
            post_number: Current post number (for progress tracking)
            total_posts: Total posts in this cycle (for progress tracking)
            
        Returns:
            True if successful, False otherwise
        """
        browser = None
        try:
            import random
            import gc  # OPTIMIZATION: Explicit garbage collection
            from ..browser.browser_factory import browser_factory
            
            # OPTIMIZATION: Log resource usage periodically
            if post_number % 5 == 0:
                self.logger.info(f"🔧 System check at post {post_number}/{total_posts}")
            
            # Get proxy configuration if needed (same as quick post)
            proxy_config = None
            if account.use_proxy and account.preferred_proxy:
                from ..proxy.proxy_manager import ProxyManager
                proxy_manager = ProxyManager(self.config.to_dict())
                
                if account.preferred_proxy in proxy_manager.proxies:
                    proxy_data = proxy_manager.proxies[account.preferred_proxy]
                    proxy_config = proxy_data.url
                    self.logger.info(f"Using proxy {proxy_config} for post {post_number}")
            
            # OPTIMIZATION: Initialize browser with enhanced error handling
            try:
                browser = browser_factory.create_driver(self.config.to_dict())
            except Exception as browser_init_error:
                self.logger.error(f"Browser initialization failed for post {post_number}: {browser_init_error}")
                return False
            
            # OPTIMIZATION: Launch browser with timeout and retry logic
            launch_success = False
            max_launch_retries = 2
            
            for retry in range(max_launch_retries):
                try:
                    launch_success = await browser.launch_browser(
                        proxy_config=proxy_config,
                        headless=False,
                        fingerprint_data=account.fingerprint_data,
                        account_username=account.username
                    )
                    
                    if launch_success:
                        break
                    else:
                        self.logger.warning(f"Browser launch attempt {retry + 1}/{max_launch_retries} failed for post {post_number}")
                        if retry < max_launch_retries - 1:
                            await asyncio.sleep(5)  # Wait before retry
                        
                except Exception as launch_error:
                    self.logger.error(f"Browser launch error (attempt {retry + 1}): {launch_error}")
                    if retry < max_launch_retries - 1:
                        await asyncio.sleep(5)  # Wait before retry
            
            if not launch_success:
                self.logger.error(f"Failed to launch browser for post {post_number} after {max_launch_retries} attempts")
                return False
            
            # Load existing cookies if available (same as quick post)
            existing_cookies = await self.account_manager.load_account_cookies(account)
            if existing_cookies:
                await browser.set_cookies(existing_cookies)
                self.logger.info(f"Loaded {len(existing_cookies)} cookies for {account.username} (post {post_number})")
            
            # Use selectors from config (same as quick post)
            config_dict = self.config.to_dict()
            selectors = config_dict['automation']['selectors']
            
            # Step 1: Human-like navigation path (Stealth Flow) - EXACT same as quick post
            self.logger.info(f"Stealth navigation for post {post_number}: starting at https://x.com/home")
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
            
            # OPTIMIZATION: Reduce intermediate pages for multi-account to save time
            # But still maintain stealth behavior
            num_pages = random.randint(1, 2)  # Reduced from 1-3 to 1-2
            self.logger.info(f"Stealth navigation for post {post_number}: visiting {num_pages} intermediate pages")

            # Shuffle list to ensure random selection order - EXACT same as quick post
            random.shuffle(intermediate_urls)
            
            for i in range(num_pages):
                page_url = intermediate_urls[i % len(intermediate_urls)]
                self.logger.info(f"Stealth navigation ({i+1}/{num_pages}) for post {post_number}: visiting {page_url}")
                await browser.navigate_to_url(page_url)
                
                # OPTIMIZATION: Slightly reduced scroll and wait times for multi-account
                await browser.scroll_page(random.randint(50, 150))  # Reduced scroll range
                await asyncio.sleep(random.uniform(2.0, 4.0))  # Reduced wait time

            # Finally go to target community or home - EXACT same as quick post
            target = community_url if community_url else "https://x.com/home"
            self.logger.info(f"Navigating to final target for post {post_number}: {target}")
            success = await browser.navigate_to_url(target)
            if not success:
                self.logger.error(f"Failed to navigate to target URL for post {post_number}")
                return False

            # Human-like pause to "read" the page after landing - EXACT same as quick post
            await asyncio.sleep(random.uniform(3.5, 6.0))

            # Check if we need to join the community - EXACT same as quick post
            current_url = await browser.get_current_url()
            if '/communities/' in current_url:
                self.logger.info(f"On community page for post {post_number}, checking membership status...")
                
                # Simulate reading the community page - EXACT same as quick post
                await asyncio.sleep(random.uniform(2.0, 4.5))
                
                # Check if already joined - EXACT same as quick post
                joined_button = await browser.find_element(selectors['joined_button'], timeout=3)
                if joined_button:
                    self.logger.info(f"Already a member of this community for post {post_number}")
                    # Brief pause even when already joined - EXACT same as quick post
                    await asyncio.sleep(random.uniform(1.0, 2.5))
                else:
                    # Need to join the community - EXACT same as quick post
                    self.logger.info(f"Not a member for post {post_number}, attempting to join community...")
                    
                    # Human pause while "deciding" to join - EXACT same as quick post
                    await asyncio.sleep(random.uniform(1.5, 3.5))
                    
                    join_button = await browser.find_element(selectors['join_button'], timeout=5)
                    if join_button:
                        # Natural hesitation before clicking - EXACT same as quick post
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                        
                        success = await browser.click_element(join_button)
                        if not success:
                            self.logger.error(f"Failed to click join button for post {post_number}")
                            return False
                        
                        self.logger.info(f"Clicked join button for post {post_number}, waiting for dialog...")
                        
                        # Wait for the join dialog - EXACT same as quick post
                        await asyncio.sleep(random.uniform(3.5, 6.0))
                        agree_button = await browser.find_element(selectors['agree_join_button'], timeout=10)
                        if agree_button:
                            # Simulate reading the agreement - EXACT same as quick post
                            await asyncio.sleep(random.uniform(2.5, 5.0))
                            
                            success = await browser.click_element(agree_button)
                            if not success:
                                self.logger.error(f"Failed to click agree and join button for post {post_number}")
                                return False
                            
                            self.logger.info(f"Successfully joined community for post {post_number}")
                            
                            # Wait for join process to complete - EXACT same as quick post
                            await asyncio.sleep(random.uniform(4.0, 6.5))
                        else:
                            self.logger.error(f"Agree and join button not found for post {post_number}")
                            return False
                    else:
                        self.logger.error(f"Join button not found for post {post_number} - may already be a member or page not loaded")
            
            # Step 2: Find and click compose button - EXACT same as quick post
            self.logger.info(f"Looking for compose button for post {post_number}...")
            compose_button = await browser.find_element(selectors['compose_button'], timeout=10)
            if not compose_button:
                self.logger.error(f"Compose button not found for post {post_number}")
                return False
            
            # Human-like delay before clicking compose - EXACT same as quick post
            await asyncio.sleep(random.uniform(1.5, 2.5))
            
            success = await browser.click_element(compose_button)
            if not success:
                self.logger.error(f"Failed to click compose button for post {post_number}")
                return False
            
            self.logger.info(f"Clicked compose button for post {post_number}")
            
            # Wait for compose dialog to appear - EXACT same as quick post
            await asyncio.sleep(random.uniform(2.0, 3.0))
            
            # Step 3: Find the text area - EXACT same as quick post
            textbox = await browser.find_element(selectors['compose_textbox'], timeout=10)
            if not textbox:
                self.logger.error(f"Compose textbox not found for post {post_number}")
                return False
            
            # Decide steps order randomly - EXACT same as quick post
            images_first = random.choice([True, False])
            self.logger.info(f"Posting order for post {post_number}: {'Images -> Text' if images_first else 'Text -> Images'}")
            
            async def upload_action():
                if image_paths:
                    self.logger.info(f"Uploading {len(image_paths)} images for post {post_number}...")
                    success = await self._upload_images_like_quick_post(browser, image_paths, selectors)
                    if not success:
                        self.logger.warning(f"Image upload failed for post {post_number}, continuing...")
                    await asyncio.sleep(random.uniform(2.0, 3.0))
            
            async def type_action():
                self.logger.info(f"Typing post content for post {post_number}...")
                # Re-find textbox as it may have changed - EXACT same as quick post
                tb = await browser.find_element(selectors['compose_textbox'], timeout=5) or textbox
                await browser.click_element(tb)
                await asyncio.sleep(random.uniform(0.5, 1.0))
                success = await browser.type_text_human_like(tb, content)
                if not success:
                    self.logger.error(f"Failed to type content for post {post_number}")
                await asyncio.sleep(random.uniform(2.0, 3.5))

            # Execute in random order - EXACT same as quick post
            if images_first:
                await upload_action()
                await type_action()
            else:
                await type_action()
                await upload_action()

            # Step 6: Find and click tweet button - EXACT same as quick post
            self.logger.info(f"Looking for tweet button for post {post_number}...")
            tweet_button = await browser.find_element(selectors['tweet_button'], timeout=10)
            if not tweet_button:
                self.logger.error(f"Tweet button not found for post {post_number}")
                return False
            
            # Final human-like delay before posting - EXACT same as quick post
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            success = await browser.click_element(tweet_button)
            if not success:
                self.logger.error(f"Failed to click tweet button for post {post_number}")
                return False
            
            self.logger.info(f"Clicked tweet button for post {post_number}")
            
            # Step 7: Wait on page and add human-like behavior - EXACT same as quick post
            await asyncio.sleep(random.uniform(5.0, 7.0))
            
            # Human-like behavior: scroll a bit after posting - EXACT same as quick post
            self.logger.info(f"Adding human-like behavior for post {post_number} - scrolling...")
            await browser.scroll_page(random.randint(200, 500))
            
            # Final wait to ensure post is processed - EXACT same as quick post
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            self.logger.info(f"Post process completed for post {post_number}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating optimized post {post_number}: {e}")
            return False
        finally:
            # OPTIMIZATION: Enhanced cleanup with explicit resource management
            if browser:
                try:
                    # Save cookies before closing - EXACT same as quick post
                    cookies = await browser.get_cookies()
                    if cookies:
                        await self.account_manager.save_account_cookies(account, cookies)
                        self.logger.info(f"Saved {len(cookies)} cookies for post {post_number} before closing")
                    
                    self.logger.info(f"Closing browser for post {post_number}...")
                    await browser.close_browser()
                    self.logger.info(f"Browser closed successfully for post {post_number}")
                    
                    # OPTIMIZATION: Explicit cleanup
                    browser = None
                    
                except Exception as e:
                    self.logger.error(f"Error during browser cleanup for post {post_number}: {e}")
            
            # OPTIMIZATION: Force garbage collection after every few posts
            if post_number % 3 == 0:
                import gc
                gc.collect()
                self.logger.debug(f"🧹 Garbage collection performed after post {post_number}")
        """
        EXACT replica of the quick post method from web_server._create_post_with_zendriver()
        This ensures 100% identical behavior between quick post and scheduled posting.
        """
        browser = None
        try:
            import random
            from ..browser.browser_factory import browser_factory
            
            # Get proxy configuration if needed (same as quick post)
            proxy_config = None
            if account.use_proxy and account.preferred_proxy:
                from ..proxy.proxy_manager import ProxyManager
                proxy_manager = ProxyManager(self.config.to_dict())
                
                if account.preferred_proxy in proxy_manager.proxies:
                    proxy_data = proxy_manager.proxies[account.preferred_proxy]
                    proxy_config = proxy_data.url
                    self.logger.info(f"Using proxy {proxy_config} for post")
            
            # Initialize browser using factory (same as quick post)
            browser = browser_factory.create_driver(self.config.to_dict())
            
            # Launch browser with account-specific profile (same as quick post)
            success = await browser.launch_browser(
                proxy_config=proxy_config,
                headless=False,
                fingerprint_data=account.fingerprint_data,
                account_username=account.username
            )
            
            if not success:
                self.logger.error("Failed to launch browser for posting")
                return False
            
            # Load existing cookies if available (same as quick post)
            existing_cookies = await self.account_manager.load_account_cookies(account)
            if existing_cookies:
                await browser.set_cookies(existing_cookies)
                self.logger.info(f"Loaded {len(existing_cookies)} cookies for {account.username}")
            
            # Use selectors from config (same as quick post)
            config_dict = self.config.to_dict()
            selectors = config_dict['automation']['selectors']
            
            # Step 1: Human-like navigation path (Stealth Flow) - EXACT same as quick post
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
            
            # Determine loose random number of pages to visit (1 to 3) - EXACT same as quick post
            num_pages = random.randint(1, 3)
            self.logger.info(f"Stealth navigation: visiting {num_pages} intermediate pages")

            # Shuffle list to ensure random selection order - EXACT same as quick post
            random.shuffle(intermediate_urls)
            
            for i in range(num_pages):
                page_url = intermediate_urls[i % len(intermediate_urls)]
                self.logger.info(f"Stealth navigation ({i+1}/{num_pages}): visiting {page_url}")
                await browser.navigate_to_url(page_url)
                
                # Add some interaction: minimal scroll - EXACT same as quick post
                await browser.scroll_page(random.randint(50, 200))
                await asyncio.sleep(random.uniform(3.0, 5.0))

            # Finally go to target community or home - EXACT same as quick post
            target = community_url if community_url else "https://x.com/home"
            self.logger.info(f"Navigating to final target: {target}")
            success = await browser.navigate_to_url(target)
            if not success:
                self.logger.error("Failed to navigate to target URL")
                return False

            # Human-like pause to "read" the page after landing - EXACT same as quick post
            await asyncio.sleep(random.uniform(3.5, 6.0))

            # Check if we need to join the community - EXACT same as quick post
            current_url = await browser.get_current_url()
            if '/communities/' in current_url:
                self.logger.info("On community page, checking membership status...")
                
                # Simulate reading the community page - EXACT same as quick post
                await asyncio.sleep(random.uniform(2.0, 4.5))
                
                # Check if already joined - EXACT same as quick post
                joined_button = await browser.find_element(selectors['joined_button'], timeout=3)
                if joined_button:
                    self.logger.info("Already a member of this community")
                    # Brief pause even when already joined - EXACT same as quick post
                    await asyncio.sleep(random.uniform(1.0, 2.5))
                else:
                    # Need to join the community - EXACT same as quick post
                    self.logger.info("Not a member, attempting to join community...")
                    
                    # Human pause while "deciding" to join - EXACT same as quick post
                    await asyncio.sleep(random.uniform(1.5, 3.5))
                    
                    join_button = await browser.find_element(selectors['join_button'], timeout=5)
                    if join_button:
                        # Natural hesitation before clicking - EXACT same as quick post
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                        
                        success = await browser.click_element(join_button)
                        if not success:
                            self.logger.error("Failed to click join button")
                            return False
                        
                        self.logger.info("Clicked join button, waiting for dialog...")
                        
                        # Wait for the join dialog - EXACT same as quick post
                        await asyncio.sleep(random.uniform(3.5, 6.0))
                        agree_button = await browser.find_element(selectors['agree_join_button'], timeout=10)
                        if agree_button:
                            # Simulate reading the agreement - EXACT same as quick post
                            await asyncio.sleep(random.uniform(2.5, 5.0))
                            
                            success = await browser.click_element(agree_button)
                            if not success:
                                self.logger.error("Failed to click agree and join button")
                                return False
                            
                            self.logger.info("Successfully joined community")
                            
                            # Wait for join process to complete - EXACT same as quick post
                            await asyncio.sleep(random.uniform(4.0, 6.5))
                        else:
                            self.logger.error("Agree and join button not found")
                            return False
                    else:
                        self.logger.error("Join button not found - may already be a member or page not loaded")
            
            # Step 2: Find and click compose button - EXACT same as quick post
            self.logger.info("Looking for compose button...")
            compose_button = await browser.find_element(selectors['compose_button'], timeout=10)
            if not compose_button:
                self.logger.error("Compose button not found")
                return False
            
            # Human-like delay before clicking compose - EXACT same as quick post
            await asyncio.sleep(random.uniform(1.5, 2.5))
            
            success = await browser.click_element(compose_button)
            if not success:
                self.logger.error("Failed to click compose button")
                return False
            
            self.logger.info("Clicked compose button")
            
            # Wait for compose dialog to appear - EXACT same as quick post
            await asyncio.sleep(random.uniform(2.0, 3.0))
            
            # Step 3: Find the text area - EXACT same as quick post
            textbox = await browser.find_element(selectors['compose_textbox'], timeout=10)
            if not textbox:
                self.logger.error("Compose textbox not found")
                return False
            
            # Decide steps order randomly - EXACT same as quick post
            images_first = random.choice([True, False])
            self.logger.info(f"Posting order: {'Images -> Text' if images_first else 'Text -> Images'}")
            
            async def upload_action():
                if image_paths:
                    self.logger.info(f"Uploading {len(image_paths)} images...")
                    success = await self._upload_images_like_quick_post(browser, image_paths, selectors)
                    if not success:
                        self.logger.warning("Image upload failed, continuing...")
                    await asyncio.sleep(random.uniform(2.0, 3.0))
            
            async def type_action():
                self.logger.info("Typing post content...")
                # Re-find textbox as it may have changed - EXACT same as quick post
                tb = await browser.find_element(selectors['compose_textbox'], timeout=5) or textbox
                await browser.click_element(tb)
                await asyncio.sleep(random.uniform(0.5, 1.0))
                success = await browser.type_text_human_like(tb, content)
                if not success:
                    self.logger.error("Failed to type content")
                await asyncio.sleep(random.uniform(2.0, 3.5))

            # Execute in random order - EXACT same as quick post
            if images_first:
                await upload_action()
                await type_action()
            else:
                await type_action()
                await upload_action()

            # Step 6: Find and click tweet button - EXACT same as quick post
            self.logger.info("Looking for tweet button...")
            tweet_button = await browser.find_element(selectors['tweet_button'], timeout=10)
            if not tweet_button:
                self.logger.error("Tweet button not found")
                return False
            
            # Final human-like delay before posting - EXACT same as quick post
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            success = await browser.click_element(tweet_button)
            if not success:
                self.logger.error("Failed to click tweet button")
                return False
            
            self.logger.info("Clicked tweet button")
            
            # Step 7: Wait on page and add human-like behavior - EXACT same as quick post
            await asyncio.sleep(random.uniform(5.0, 7.0))
            
            # Human-like behavior: scroll a bit after posting - EXACT same as quick post
            self.logger.info("Adding human-like behavior - scrolling...")
            await browser.scroll_page(random.randint(200, 500))
            
            # Final wait to ensure post is processed - EXACT same as quick post
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            self.logger.info("Post process completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating post like quick post: {e}")
            return False
        finally:
            if browser:
                try:
                    # Save cookies before closing - EXACT same as quick post
                    cookies = await browser.get_cookies()
                    if cookies:
                        await self.account_manager.save_account_cookies(account, cookies)
                        self.logger.info(f"Saved {len(cookies)} cookies before closing")
                    
                    self.logger.info("Closing browser...")
                    await browser.close_browser()
                    self.logger.info("Browser closed successfully")
                except Exception as e:
                    self.logger.error(f"Error during browser cleanup: {e}")
    
    async def _upload_images_like_quick_post(self, browser, image_paths: list, selectors: dict) -> bool:
        """
        EXACT replica of the image upload method from quick post.
        """
        try:
            import random
            
            for i, image_path in enumerate(image_paths):
                try:
                    p = Path(image_path).absolute()
                    if not p.exists():
                        self.logger.warning(f"Image not found: {image_path}")
                        continue
                    
                    self.logger.info(f"Uploading image {i+1}/{len(image_paths)}: {p.name}")
                    
                    # Find the file input element - EXACT same as quick post
                    file_input = await browser.find_element(selectors['media_upload'], timeout=5)
                    
                    if not file_input:
                        self.logger.info("File input not found, trying to reveal it via media button click...")
                        # Click media button to potentially reveal the input - EXACT same as quick post
                        media_button = await browser.find_element(selectors['media_button'], timeout=5)
                        if media_button:
                            # Scroll media button into view first to ensure it's accessible
                            self.logger.info("Scrolling media button into view...")
                            await browser.scroll_element_into_view(media_button)
                            await asyncio.sleep(0.5)
                        
                        await asyncio.sleep(1.0)
                        file_input = await browser.find_element(selectors['media_upload'], timeout=5)
                    
                    if file_input:
                        # Use CDP DOM.setFileInputFiles - EXACT same as quick post
                        abs_path = str(p)
                        
                        try:
                            # Method 1: Use nodriver/zendriver's native file setting - EXACT same as quick post
                            if hasattr(file_input, 'send_file'):
                                await file_input.send_file(abs_path)
                                self.logger.info(f"Uploaded via send_file: {p.name}")
                            elif hasattr(file_input, 'set_input_files'):
                                await file_input.set_input_files([abs_path])
                                self.logger.info(f"Uploaded via set_input_files: {p.name}")
                            else:
                                # Use send_keys as fallback - EXACT same as quick post
                                await file_input.send_keys(abs_path)
                                self.logger.info(f"Uploaded via send_keys: {p.name}")
                        except Exception as upload_err:
                            self.logger.error(f"Upload method failed: {upload_err}")
                            # Final fallback - EXACT same as quick post
                            try:
                                await file_input.send_keys(abs_path)
                                self.logger.info(f"Uploaded via fallback send_keys: {p.name}")
                            except Exception as fallback_err:
                                self.logger.error(f"Fallback upload failed: {fallback_err}")
                                continue
                        
                        # Wait for image to be processed - EXACT same as quick post
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

    async def _reply_to_random_tweet(self, account, content: str, image_paths: list = None, reply_number: int = 1, total_replies: int = 1) -> bool:
        """
        Reply to a randomly selected tweet that contains an image.

        Steps:
        - Navigate to https://x.com/home
        - Scroll randomly up/down a few times
        - Select a tweet that has an image and open it by clicking
        - Ensure the inline reply button is visible and click it
        - Optionally upload images and type a reply (random order)
        - Click the reply/send button and wait for confirmation toast
        """
        browser = None
        try:
            import random
            from ..browser.browser_factory import browser_factory

            # Prepare proxy if needed
            proxy_config = None
            if account.use_proxy and account.preferred_proxy:
                from ..proxy.proxy_manager import ProxyManager
                proxy_manager = ProxyManager(self.config.to_dict())
                if account.preferred_proxy in proxy_manager.proxies:
                    proxy_data = proxy_manager.proxies[account.preferred_proxy]
                    proxy_config = proxy_data.url

            # Initialize browser
            browser = browser_factory.create_driver(self.config.to_dict())
            success = await browser.launch_browser(
                proxy_config=proxy_config,
                headless=False,
                fingerprint_data=account.fingerprint_data,
                account_username=account.username
            )

            if not success:
                self.logger.error("Failed to launch browser for reply")
                return False

            # Load cookies
            existing_cookies = await self.account_manager.load_account_cookies(account)
            if existing_cookies:
                await browser.set_cookies(existing_cookies)
                self.logger.info(f"Loaded {len(existing_cookies)} cookies for reply account {account.username}")

            config_dict = self.config.to_dict()
            selectors = config_dict['automation']['selectors']
            reply_cfg = getattr(self.config, 'reply_settings', None) or {}

            # Go to home and perform human-like scrolling
            self.logger.info("Reply flow: navigating to https://x.com/home")
            await browser.navigate_to_url("https://x.com/home")
            await asyncio.sleep(random.uniform(2.5, 4.5))

            min_scroll = getattr(self.config, 'reply_settings', None).min_scroll_actions if getattr(self.config, 'reply_settings', None) else 2
            max_scroll = getattr(self.config, 'reply_settings', None).max_scroll_actions if getattr(self.config, 'reply_settings', None) else 5
            scroll_actions = random.randint(min_scroll, max_scroll)

            for i in range(scroll_actions):
                # Only scroll down initially (positive values only)
                pixels = random.randint(100, 800)
                await browser.scroll_page(pixels)
                await asyncio.sleep(random.uniform(1.0, 2.5))

            # Randomize behavior: sometimes visit another page before selecting tweet
            visit_other_page = random.random() < 0.4  # 40% chance to visit another page
            
            if visit_other_page:
                intermediate_pages = [
                    "https://x.com/explore",
                    "https://x.com/notifications",
                    "https://x.com/i/bookmarks",
                    "https://x.com/explore/tabs/trending",
                    "https://x.com/explore/tabs/news"
                ]
                other_page = random.choice(intermediate_pages)
                self.logger.info(f"Reply flow: visiting {other_page} before selecting tweet")
                await browser.navigate_to_url(other_page)
                await asyncio.sleep(random.uniform(2.0, 4.0))
                
                # Scroll a bit on the other page (only down initially)
                for _ in range(random.randint(1, 2)):
                    pixels = random.randint(100, 400)
                    await browser.scroll_page(pixels)
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                
                # Go back to home
                self.logger.info("Reply flow: returning to https://x.com/home")
                await browser.navigate_to_url("https://x.com/home")
                await asyncio.sleep(random.uniform(2.0, 3.5))
                
                # Do minimal scroll on home (1-2 times, only down)
                minimal_scrolls = random.randint(1, 2)
                for _ in range(minimal_scrolls):
                    pixels = random.randint(100, 400)
                    await browser.scroll_page(pixels)
                    await asyncio.sleep(random.uniform(1.0, 2.0))

            # Find tweets and pick one with an image
            tweets = await browser.find_elements(selectors.get('tweet_container', "article[data-testid='tweet']"))
            random.shuffle(tweets)

            target_tweet = None
            for t in tweets:
                try:
                    # Try to find a photo element inside the tweet
                    # Use the photo selector without the article prefix for inside-query
                    photo_selector = selectors.get('tweet_photo', "[data-testid='tweetPhoto']")
                    # Many element objects expose query_selector
                    photo = None
                    if hasattr(t, 'query_selector'):
                        try:
                            photo = await t.query_selector(photo_selector)
                        except Exception:
                            photo = None

                    if photo:
                        target_tweet = t
                        break
                except Exception:
                    continue

            if not target_tweet:
                self.logger.warning("No tweet with image found to reply to")
                return False

            # Open the tweet by clicking it
            self.logger.info("Opening selected tweet to reply")
            clicked = await browser.click_element(target_tweet)
            if not clicked:
                self.logger.error("Failed to click selected tweet")
                return False

            # Wait for tweet page to load
            await asyncio.sleep(random.uniform(1.5, 3.0))

            # Occasionally do a small scroll to bring reply UI into view
            if random.random() < 0.6:
                await browser.scroll_page(random.randint(0, 200))

            # Find inline reply button
            reply_btn = await browser.find_element(selectors.get('tweet_inline_button', "button[data-testid='tweetButtonInline']"), timeout=6)
            if not reply_btn:
                # Try a little scroll and retry
                await browser.scroll_page(150)
                await asyncio.sleep(0.8)
                reply_btn = await browser.find_element(selectors.get('tweet_inline_button', "button[data-testid='tweetButtonInline']"), timeout=4)

            if not reply_btn:
                self.logger.error("Reply button not found on tweet page")
                return False

            # Click reply to open reply composer
            success = await browser.click_element(reply_btn)
            if not success:
                self.logger.error("Failed to click reply button")
                return False

            await asyncio.sleep(random.uniform(0.8, 1.8))

            # Decide order: upload images first or type text first
            images_first = random.choice([True, False])

            async def upload_action():
                if image_paths:
                    self.logger.info("Uploading reply image(s)")
                    await asyncio.sleep(random.uniform(0.6, 1.4))
                    await self._upload_images_like_quick_post(browser, image_paths, selectors)

            async def type_action():
                tb_selector = selectors.get('reply_textbox', selectors.get('compose_textbox'))
                tb = await browser.find_element(tb_selector, timeout=5)
                if not tb:
                    self.logger.error("Reply textbox not found")
                    return False
                await asyncio.sleep(random.uniform(0.2, 0.6))
                await browser.type_text_human_like(tb, content)
                await asyncio.sleep(random.uniform(0.6, 1.6))
                return True

            if images_first:
                await upload_action()
                await type_action()
            else:
                await type_action()
                await upload_action()

            # Click the inline reply/send button
            send_btn = await browser.find_element(selectors.get('tweet_inline_button', "button[data-testid='tweetButtonInline']"), timeout=8)
            if not send_btn:
                self.logger.error("Send/reply button not found")
                return False

            await asyncio.sleep(random.uniform(0.8, 1.6))
            clicked = await browser.click_element(send_btn)
            if not clicked:
                self.logger.error("Failed to click send/reply button")
                return False

            # Wait for confirmation toast
            toast_selector = "div[data-testid='toast']"
            toast_found = False
            for _ in range(30):
                toast = await browser.find_element(toast_selector, timeout=1)
                if toast:
                    # Toast appeared - consider it success
                    # Reading text from zendriver Element can be tricky, so just check presence
                    try:
                        # Try to get text via element property if available
                        if hasattr(toast, 'text'):
                            text = await toast.text if hasattr(toast.text, '__await__') else toast.text
                            if text and 'Your post was sent' in str(text):
                                toast_found = True
                                break
                        else:
                            # If we can't get text, just accept toast presence as success
                            toast_found = True
                            break
                    except Exception:
                        # If any error, accept toast presence as success
                        toast_found = True
                        break
                await asyncio.sleep(0.5)

            if not toast_found:
                self.logger.warning("Reply may not have been confirmed (toast not found)")
                return False

            # Human-like post-reply behavior
            await asyncio.sleep(random.uniform(1.2, 2.8))
            self.logger.info("Reply posted successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error during reply process: {e}")
            return False
        finally:
            if browser:
                try:
                    cookies = await browser.get_cookies()
                    if cookies:
                        await self.account_manager.save_account_cookies(account, cookies)
                    await browser.close_browser()
                except Exception as e:
                    self.logger.error(f"Error cleaning up reply browser: {e}")
    
    async def _refresh_session_cookies(self, current_account=None) -> None:
        """Refresh session cookies to keep login fresh."""
        # Note: This method is no longer needed since we create new browser instances per post
        # Cookie management is handled in the _create_post_like_quick_post method
        pass
    
    def _handle_posting_failure(self, post: Post, group_name: str) -> None:
        """Handle posting failure for a specific post."""
        try:
            # Check if we should skip this post
            if self.error_handler.skip_failed_posts:
                self.queue_manager.mark_post_skipped(post.id, "Maximum retries exceeded")
                self.logger.warning(f"Skipped failed post: {post.id}")
            else:
                self.queue_manager.mark_post_failed(post.id, "Posting failed")
                self.logger.error(f"Marked post as failed: {post.id}")
            
        except Exception as e:
            self.logger.error(f"Error handling posting failure: {e}")
    
    async def _restart_browser_session(self) -> bool:
        """Restart browser session after crash."""
        try:
            self.logger.info("Restarting browser session...")
            
            # Cleanup old session
            await self._cleanup_browser_session()
            
            # Wait before restart
            await asyncio.sleep(5)
            
            # Initialize new session
            success = await self._initialize_browser_session()
            
            if success:
                self.logger.info("Browser session restarted successfully")
            else:
                self.logger.error("Failed to restart browser session")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error restarting browser session: {e}")
            return False
    
    def _setup_error_recovery(self) -> None:
        """Set up error recovery callbacks."""
        from ..error.error_handler import ErrorType
        
        # Register recovery callbacks
        self.error_handler.register_recovery_callback(
            ErrorType.BROWSER_CRASH, 
            lambda ctx: self._restart_browser_session()
        )
        
        self.error_handler.register_recovery_callback(
            ErrorType.AUTHENTICATION_ERROR,
            lambda ctx: self._handle_authentication_error()
        )
    
    def _handle_authentication_error(self) -> bool:
        """Handle authentication errors."""
        try:
            self.logger.warning("Authentication error detected, attempting re-authentication...")
            
            if self.session_manager.current_session:
                success = self.session_manager.handle_authentication_challenge(
                    self.session_manager.current_session
                )
                return success
            
            return False
            
        except Exception as e:
            self.logger.error(f"Authentication error handling failed: {e}")
            return False
    
    def _update_status(self, status: str) -> None:
        """Update status and notify GUI."""
        try:
            if self.status_callback:
                self.status_callback(status)
        except Exception as e:
            self.logger.error(f"Error updating status: {e}")
    
    def _show_error(self, message: str) -> None:
        """Show error message to user."""
        try:
            if self.error_callback:
                self.error_callback(message)
        except Exception as e:
            self.logger.error(f"Error showing error message: {e}")
    
    def _get_current_status(self) -> str:
        """Get current status text."""
        if not self.is_running:
            return "Stopped"
        elif self.is_paused:
            return "Paused"
        elif self.error_handler.check_rate_limits():
            return "Rate Limited"
        else:
            return "Running"
    
    def _load_community_list(self) -> None:
        """Load community list from communities.json file."""
        try:
            communities_file = self.file_manager.communities_json_file
            if not communities_file.exists():
                self.logger.warning(f"Communities file not found: {communities_file}")
                return
            
            # Use the proper method to read communities
            community_groups = self.file_manager.read_communities_file()
            
            # Extract all community URLs from all groups
            communities = []
            for group in community_groups:
                communities.extend(group.communities)
            
            # Update community list and reset index if needed
            old_count = len(self.community_list) if self.community_list else 0
            self.community_list = communities
            
            # Reset index if we had communities before but list changed significantly
            if old_count > 0 and len(communities) != old_count:
                self.logger.info(f"Community list changed from {old_count} to {len(communities)} communities, resetting cycle")
                self.current_community_index = 0
            
            # Ensure index is within bounds
            if self.current_community_index >= len(self.community_list):
                self.logger.info(f"Current index {self.current_community_index} out of bounds, resetting to 0")
                self.current_community_index = 0
            
            self.logger.info(f"✅ Loaded {len(communities)} communities for cycling")
            
            # Log all communities for debugging
            for i, community in enumerate(communities):
                status = "👉 CURRENT" if i == self.current_community_index else "   "
                self.logger.debug(f"  {status} Community {i + 1}: {community}")
            
        except Exception as e:
            self.logger.error(f"Failed to load community list: {e}")
    
    def _load_accounts_list(self) -> None:
        """Load active accounts list for cycling."""
        try:
            # Get active accounts from account manager
            active_accounts = self.account_manager.get_active_accounts()
            
            # Update accounts list and reset index if needed
            old_count = len(self.active_accounts_list) if self.active_accounts_list else 0
            self.active_accounts_list = active_accounts
            
            # Reset index if we had accounts before but list changed significantly
            if old_count > 0 and len(active_accounts) != old_count:
                self.logger.info(f"Account list changed from {old_count} to {len(active_accounts)} accounts, resetting cycle")
                self.current_account_index = 0
            
            # Ensure index is within bounds
            if self.current_account_index >= len(self.active_accounts_list):
                self.logger.info(f"Current account index {self.current_account_index} out of bounds, resetting to 0")
                self.current_account_index = 0
            
            self.logger.info(f"✅ Loaded {len(active_accounts)} active accounts for cycling")
            
            # Log all accounts for debugging
            for i, account in enumerate(active_accounts):
                status = "👉 CURRENT" if i == self.current_account_index else "   "
                self.logger.debug(f"  {status} Account {i + 1}: @{account.username}")
            
        except Exception as e:
            self.logger.error(f"Failed to load accounts list: {e}")
    
    def reload_communities(self) -> bool:
        """
        Reload communities from file and update cycling state.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            old_current = self._get_current_community()
            self._load_community_list()
            new_current = self._get_current_community()
            
            if old_current != new_current:
                self.logger.info(f"Current community changed from {old_current} to {new_current}")
            
            return len(self.community_list) > 0
            
        except Exception as e:
            self.logger.error(f"Failed to reload communities: {e}")
            return False
    
    def reload_accounts(self) -> bool:
        """
        Reload accounts from account manager and update cycling state.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            old_current = self._get_current_account()
            self._load_accounts_list()
            new_current = self._get_current_account()
            
            if old_current != new_current:
                old_name = old_current.username if old_current else None
                new_name = new_current.username if new_current else None
                self.logger.info(f"Current account changed from @{old_name} to @{new_name}")
            
            return len(self.active_accounts_list) > 0
            
        except Exception as e:
            self.logger.error(f"Failed to reload accounts: {e}")
            return False
    
    def _get_current_community(self) -> Optional[str]:
        """
        Get the current community for posting.
        
        Returns:
            Current community URL or None if no communities available
        """
        if not self.community_list:
            self.logger.warning("No communities available for posting")
            return None
        
        # Ensure index is within bounds (safety check)
        if self.current_community_index >= len(self.community_list):
            self.logger.info(f"Community index {self.current_community_index} out of bounds, resetting to 0")
            self.current_community_index = 0
        
        current_community = self.community_list[self.current_community_index]
        self.logger.debug(f"Current community ({self.current_community_index + 1}/{len(self.community_list)}): {current_community}")
        
        return current_community
    
    def _advance_to_next_community(self) -> None:
        """Advance to the next community in the cycle with proper restart logic."""
        if not self.community_list:
            self.logger.warning("Cannot advance community - no communities available")
            return
        
        previous_index = self.current_community_index
        self.current_community_index += 1
        
        # If we've reached the end, cycle back to the beginning
        if self.current_community_index >= len(self.community_list):
            self.current_community_index = 0
            self.logger.info(f"🔄 Completed full community cycle! Restarting from community 1 (was at community {previous_index + 1}/{len(self.community_list)})")
        
        current_community = self._get_current_community()
        if current_community:
            self.logger.info(f"📍 Advanced to community {self.current_community_index + 1}/{len(self.community_list)}: {current_community}")
        
        # Log cycle progress
        progress_percentage = ((self.current_community_index + 1) / len(self.community_list)) * 100
        self.logger.debug(f"Community cycle progress: {progress_percentage:.1f}% ({self.current_community_index + 1}/{len(self.community_list)})")
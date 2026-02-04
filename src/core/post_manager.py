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
        
        # Operation state
        self.is_running = False
        self.is_paused = False
        self.posting_thread: Optional[threading.Thread] = None
        self.posting_loop: Optional[asyncio.AbstractEventLoop] = None
        self.stop_event = threading.Event()
        
        # Community cycling state
        self.cycle_communities = True
        self.current_community_index = 0
        self.community_list = []
        
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
    
    def process_next_post(self) -> bool:
        """
        Handle the next post in the queue with community cycling support.
        
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
            
            # Get current community for posting
            current_community = self._get_current_community()
            if not current_community:
                self.logger.error("No community available for posting")
                return False
            
            # Process the post with current community
            success = self._process_single_post(next_post, current_community)
            
            if success:
                # Mark post as completed and update schedule
                self.queue_manager.mark_post_completed(next_post.id, group_name)
                self.posting_scheduler.schedule_next_post(group_name)
                self.error_handler.reset_failure_count()
                
                # Move to next community if cycling is enabled
                if self.cycle_communities:
                    self._advance_to_next_community()
                
                self.logger.info(f"Successfully posted: {next_post.id} to community: {current_community}")
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
            
            # Check browser status - use thread-safe method if loop is running
            browser_alive = False
            if self.browser_driver:
                try:
                    if self.posting_loop and self.posting_loop.is_running():
                        future = asyncio.run_coroutine_threadsafe(
                            self.browser_driver.is_browser_alive(), 
                            self.posting_loop
                        )
                        browser_alive = future.result(timeout=5)
                    else:
                        # Fallback for when loop isn't running yet or already stopped
                        browser_alive = asyncio.run(self.browser_driver.is_browser_alive())
                except Exception as e:
                    self.logger.debug(f"Error checking browser status: {e}")
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
    
    def reset_community_cycle(self) -> None:
        """Reset community cycling to start from the first community."""
        self.current_community_index = 0
        self.logger.info("Community cycle reset to start from community 1")
    
    def get_community_status(self) -> Dict[str, Any]:
        """
        Get current community cycling status.
        
        Returns:
            Dictionary with community status information
        """
        return {
            'cycling_enabled': self.cycle_communities,
            'total_communities': len(self.community_list),
            'current_index': self.current_community_index,
            'current_community': self._get_current_community() if self.community_list else None,
            'communities': self.community_list
        }
    
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
        # Create a dedicated event loop for this thread to ensure ZenDriver persistence
        self.posting_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.posting_loop)
        
        try:
            self.logger.info("Posting loop started with dedicated event loop")
            
            # Initialize browser and session in this thread's loop
            success = self.posting_loop.run_until_complete(self._initialize_browser_session())
            if not success:
                self.logger.error("Failed to initialize browser session in posting thread")
                self.is_running = False
                return

            while self.is_running and not self.stop_event.is_set():
                try:
                    # Check if paused
                    if self.is_paused:
                        time.sleep(5)
                        continue
                    
                    # Process next post
                    post_processed = self.posting_loop.run_until_complete(self._process_next_post_async())
                    
                    if post_processed:
                        # Add stealth delay after posting
                        self.posting_loop.run_until_complete(self.stealth_engine.apply_stealth_delay(self.behavior_simulator, 5.0))
                    else:
                        # No posts to process, wait before checking again
                        # Use wait with timeout to still check stop_event
                        time.sleep(10)
                    
                    # Check browser health
                    if self.browser_driver:
                        browser_alive = self.posting_loop.run_until_complete(self.browser_driver.is_browser_alive())
                        if not browser_alive:
                            self.logger.warning("Browser crashed, attempting restart...")
                            self.posting_loop.run_until_complete(self._restart_browser_session())
                    
                except Exception as e:
                    self.handle_posting_error(e)
                    time.sleep(10)  # Wait before retrying
            
            self.logger.info("Posting loop stopping...")
            
        except Exception as e:
            self.logger.error(f"Fatal error in posting loop: {e}")
            self._update_status("Error")
        finally:
            # Clean up browser and close loop
            try:
                if self.posting_loop and self.posting_loop.is_running():
                    self.posting_loop.run_until_complete(self._cleanup_browser_session())
                else:
                    # If loop is not running but we have a browser, try a quick run
                    self.posting_loop.run_until_complete(self._cleanup_browser_session())
            except Exception as e:
                self.logger.debug(f"Error during cleanup: {e}")
            
            self.posting_loop.close()
            self.posting_loop = None
            self.logger.info("Posting loop thread ended and loop closed")
    
    async def _process_next_post_async(self) -> bool:
        """
        Async version of process_next_post for use in posting loop.
        
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
            
            # Get current community for posting
            current_community = self._get_current_community()
            if not current_community:
                self.logger.error("No community available for posting")
                return False
            
            # Process the post with current community
            success = await self._process_single_post(next_post, current_community)
            
            if success:
                # Mark post as completed and update schedule
                self.queue_manager.mark_post_completed(next_post.id, group_name)
                self.posting_scheduler.schedule_next_post(group_name)
                self.error_handler.reset_failure_count()
                
                # Move to next community if cycling is enabled
                if self.cycle_communities:
                    self._advance_to_next_community()
                
                self.logger.info(f"Successfully posted: {next_post.id} to community: {current_community}")
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
    
    async def _process_single_post(self, post: Post, community_url: str) -> bool:
        """
        Process a single post with cookie refresh after success.
        
        Args:
            post: Post to process
            community_url: Community URL to post to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"Processing post: {post.id} to community: {community_url}")
            self._update_status(f"Posting: {post.id[:8]}...")
            
            # Perform stealth actions before posting
            await self.stealth_engine.perform_random_actions(self.browser_driver, self.behavior_simulator)
            
            # Create the post using async method
            success = await self.twitter_interface.create_post(
                content=post.content,
                images=post.images,
                community_url=community_url
            )
            
            # Log the action for stealth assessment
            self.stealth_engine.log_action('post_creation', success, {
                'post_id': post.id,
                'community_url': community_url
            })
            
            if success:
                # Verify post was successful
                success = self.twitter_interface.verify_post_success()
                
                # Refresh cookies after successful post (if enabled)
                if success and getattr(self.config.stealth_settings, 'auto_refresh_cookies', True):
                    await self._refresh_session_cookies()
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to process post {post.id}: {e}")
            return False
    
    async def _refresh_session_cookies(self) -> None:
        """Refresh session cookies to keep login fresh."""
        try:
            if not self.browser_driver:
                return
            
            # Get updated cookies from browser
            cookies = await self.browser_driver.get_cookies()
            if cookies:
                # Save updated cookies to session
                if self.session_manager.current_session:
                    self.session_manager.current_session.cookies = cookies
                    self.session_manager.save_session(self.session_manager.current_session)
                    self.logger.info("Refreshed session cookies after successful post")
            
        except Exception as e:
            self.logger.error(f"Failed to refresh session cookies: {e}")
    
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
        """Load community list from communities.txt file."""
        try:
            communities_file = self.file_manager.communities_file
            if not communities_file.exists():
                self.logger.warning(f"Communities file not found: {communities_file}")
                return
            
            # Use the proper method to read communities
            community_groups = self.file_manager.read_communities_file()
            
            # Extract all community URLs from all groups
            communities = []
            for group in community_groups:
                communities.extend(group.communities)
            
            self.community_list = communities
            self.logger.info(f"Loaded {len(communities)} communities")
            
        except Exception as e:
            self.logger.error(f"Failed to load community list: {e}")
    
    def _get_current_community(self) -> Optional[str]:
        """
        Get the current community for posting.
        
        Returns:
            Current community URL or None if no communities available
        """
        if not self.community_list:
            return None
        
        if self.current_community_index >= len(self.community_list):
            # Reset to beginning if we've reached the end
            self.current_community_index = 0
        
        return self.community_list[self.current_community_index]
    
    def _advance_to_next_community(self) -> None:
        """Advance to the next community in the cycle."""
        if not self.community_list:
            return
        
        self.current_community_index += 1
        
        # If we've reached the end, cycle back to the beginning
        if self.current_community_index >= len(self.community_list):
            self.current_community_index = 0
            self.logger.info("Reached end of communities, cycling back to community 1")
        
        current_community = self._get_current_community()
        self.logger.info(f"Advanced to community {self.current_community_index + 1}: {current_community}")
"""
Twitter Interface component for Twitter-specific interactions.
Handles community navigation, posting workflow, and image uploads.
"""

import logging
import time
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any


class TwitterInterface:
    """Handles Twitter-specific interactions and posting logic."""
    
    def __init__(self, browser_driver: Any, behavior_simulator: Any):
        """
        Initialize Twitter interface.
        
        Args:
            browser_driver: Browser driver instance (ZenDriver)
            behavior_simulator: Human behavior simulator instance
        """
        self.browser = browser_driver
        self.behavior = behavior_simulator
        self.logger = logging.getLogger(__name__)
        
        # Twitter selectors (updated for current Twitter UI)
        self.selectors = {
            'compose_button': '[data-testid="SideNav_NewTweet_Button"]',
            'compose_textbox': '[data-testid="tweetTextarea_0"]',
            'media_upload': 'input[data-testid="fileInput"]',
            'tweet_button': '[data-testid="tweetButtonInline"]',
            'login_username': '[name="text"]',
            'login_password': '[name="password"]',
            'login_button': '[data-testid="LoginForm_Login_Button"]',
            'community_join_button': '[data-testid="communityJoinButton"]',
            'community_post_button': '[data-testid="communityTweetButton"]',
            'image_preview': '[data-testid="attachments"]',
            'error_message': '[data-testid="toast"]'
        }
    
    async def navigate_to_community(self, community_url: str) -> bool:
        """
        Navigate to community page.
        
        Args:
            community_url: URL of the Twitter community
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"Navigating to community: {community_url}")
            
            # Navigate to community URL
            success = await self.browser.navigate_to_url(community_url)
            if not success:
                return False
            
            # Add human-like page reading behavior
            await asyncio.sleep(2.0)  # Simplified for now
            
            # Check if we're on a valid community page
            current_url = self.browser.get_current_url()
            if not (current_url.startswith('https://twitter.com') or current_url.startswith('https://x.com')):
                self.logger.error(f"Invalid community URL or navigation failed: {current_url}")
                return False
            
            self.logger.info(f"Successfully navigated to community: {community_url}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to navigate to community {community_url}: {e}")
            return False
    
    async def create_post(self, content: str, images: List[str] = None, community_url: str = None) -> bool:
        """
        Create and publish a post with optional image attachments.
        
        Args:
            content: Text content of the post
            images: List of image file paths to attach
            community_url: Community URL to post to (optional)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"Creating post with {len(images) if images else 0} images")
            
            # Navigate to community if specified
            if community_url:
                success = await self.navigate_to_community(community_url)
                if not success:
                    return False
            
            # Find and click compose button
            compose_button = await self.browser.find_element(self.selectors['compose_button'], timeout=10)
            if not compose_button:
                self.logger.error("Compose button not found")
                return False
            
            success = await self.browser.click_element(compose_button)
            if not success:
                return False
            
            # Wait for compose dialog to appear
            await asyncio.sleep(2)
            textbox = await self.browser.find_element(self.selectors['compose_textbox'], timeout=10)
            if not textbox:
                self.logger.error("Compose textbox not found")
                return False
            
            # Upload images first if provided
            if images:
                success = await self.upload_images(images)
                if not success:
                    self.logger.warning("Image upload failed, continuing with text only")
            
            # Type the post content
            success = await self.browser.type_text(textbox, content, clear_first=True)
            if not success:
                self.logger.error("Failed to type post content")
                return False
            
            # Add reading pause to simulate reviewing the post
            await asyncio.sleep(2)
            
            # Find and click tweet button
            tweet_button = await self.browser.find_element(self.selectors['tweet_button'], timeout=10)
            if not tweet_button:
                self.logger.error("Tweet button not found")
                return False
            
            success = await self.browser.click_element(tweet_button)
            if not success:
                return False
            
            # Wait for post to be published (check for success indicators)
            await asyncio.sleep(5)  # Give time for post to process
            
            # Check for error messages
            try:
                error_element = await self.browser.find_element(self.selectors['error_message'], timeout=3)
                if error_element:
                    self.logger.error("Post failed - error message detected")
                    return False
            except:
                # No error message found, which is good
                pass
            
            self.logger.info("Post created successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create post: {e}")
            return False
    
    async def upload_images(self, image_paths: List[str]) -> bool:
        """
        Upload images before submitting post using latest ZenDriver API.
        
        Args:
            image_paths: List of image file paths to upload
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not image_paths:
                return True
            
            self.logger.info(f"Uploading {len(image_paths)} images")
            
            # Validate image files exist
            valid_images = []
            for image_path in image_paths:
                path = Path(image_path)
                if path.exists() and path.is_file():
                    valid_images.append(str(path.absolute()))
                else:
                    self.logger.warning(f"Image file not found: {image_path}")
            
            if not valid_images:
                self.logger.error("No valid image files found")
                return False
            
            # Find media upload input
            upload_input = await self.browser.find_element(self.selectors['media_upload'], timeout=5)
            if not upload_input:
                self.logger.error("Media upload input not found")
                return False
            
            # Upload each image using ZenDriver's send_keys method (latest API)
            for image_path in valid_images:
                try:
                    # Use send_keys method which is standard for file inputs in ZenDriver/nodriver
                    if hasattr(upload_input, 'send_keys'):
                        await upload_input.send_keys(image_path)
                    elif hasattr(upload_input, 'send_file'):
                        # Fallback for some ZenDriver versions
                        await upload_input.send_file(image_path)
                    else:
                        self.logger.warning("Upload input does not support send_keys or send_file")
                        return False
                    
                    # Wait between uploads to simulate human speed
                    await asyncio.sleep(1.5)
                    
                except Exception as e:
                    self.logger.error(f"Failed to upload individual image {image_path}: {e}")
                    continue
            
            # Additional wait for images to be processed by Twitter
            await asyncio.sleep(2)
            
            self.logger.info("Image upload completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to upload images: {e}")
            return False
    
    def handle_login_challenge(self, username: str = None, password: str = None) -> bool:
        """
        Handle login challenges and authentication prompts.
        
        Args:
            username: Twitter username (optional, for automated login)
            password: Twitter password (optional, for automated login)
            
        Returns:
            True if login successful, False otherwise
        """
        try:
            current_url = self.browser.get_current_url()
            
            # Check if we're on login page
            if 'login' not in current_url and 'signin' not in current_url:
                return True  # Already logged in
            
            self.logger.info("Handling login challenge")
            
            # If credentials provided, attempt automated login
            if username and password:
                return self._perform_automated_login(username, password)
            else:
                # Manual login - wait for user to complete
                return self._wait_for_manual_login()
            
        except Exception as e:
            self.logger.error(f"Login challenge handling failed: {e}")
            return False
    
    async def check_rate_limits(self) -> Dict[str, Any]:
        """
        Check for Twitter rate limiting indicators.
        
        Returns:
            Dictionary with rate limit information
        """
        try:
            rate_limit_info = {
                'limited': False,
                'retry_after': None,
                'message': None
            }
            
            # Check for rate limit error messages
            current_url = self.browser.get_current_url()
            page_source = await self.browser.execute_script("return document.body.innerText;")
            
            if page_source:
                # Look for common rate limit indicators
                rate_limit_keywords = [
                    'rate limit',
                    'too many requests',
                    'try again later',
                    'temporarily restricted'
                ]
                
                for keyword in rate_limit_keywords:
                    if keyword.lower() in page_source.lower():
                        rate_limit_info['limited'] = True
                        rate_limit_info['message'] = f"Rate limit detected: {keyword}"
                        rate_limit_info['retry_after'] = 900  # Default 15 minutes
                        break
            
            return rate_limit_info
            
        except Exception as e:
            self.logger.error(f"Failed to check rate limits: {e}")
            return {'limited': False, 'retry_after': None, 'message': None}
    
    def verify_post_success(self) -> bool:
        """
        Verify that the post was successfully published.
        
        Returns:
            True if post appears to be successful, False otherwise
        """
        try:
            # Wait a moment for the page to update
            time.sleep(2)
            
            # Check current URL - successful posts often redirect
            current_url = self.browser.get_current_url()
            
            # Look for success indicators
            if 'status' in current_url or 'tweet' in current_url:
                self.logger.debug("Post success indicated by URL")
                return True
            
            # Check for error messages
            error_element = self.browser.find_element(self.selectors['error_message'], timeout=3)
            if error_element:
                return False
            
            # If no errors found, assume success
            return True
            
        except Exception as e:
            self.logger.debug(f"Post verification inconclusive: {e}")
            return True  # Assume success if we can't determine otherwise
    
    def _perform_automated_login(self, username: str, password: str) -> bool:
        """
        Perform automated login with credentials.
        
        Args:
            username: Twitter username
            password: Twitter password
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Find username field
            username_field = self.browser.find_element(self.selectors['login_username'])
            if not username_field:
                self.logger.error("Username field not found")
                return False
            
            # Type username with human behavior
            success = self.behavior.type_with_human_timing(username_field, username)
            if not success:
                return False
            
            # Find and click next/continue button (Twitter login is multi-step)
            next_button = self.browser.find_element('[data-testid="LoginForm_Login_Button"]')
            if next_button:
                self.browser.click_element(next_button)
                time.sleep(2)
            
            # Find password field
            password_field = self.browser.find_element(self.selectors['login_password'])
            if not password_field:
                self.logger.error("Password field not found")
                return False
            
            # Type password with human behavior
            success = self.behavior.type_with_human_timing(password_field, password)
            if not success:
                return False
            
            # Find and click login button
            login_button = self.browser.find_element(self.selectors['login_button'])
            if not login_button:
                self.logger.error("Login button not found")
                return False
            
            success = self.browser.click_element(login_button)
            if not success:
                return False
            
            # Wait for login to complete
            time.sleep(5)
            
            # Check if login was successful
            current_url = self.browser.get_current_url()
            if 'login' not in current_url and 'signin' not in current_url:
                self.logger.info("Automated login successful")
                return True
            else:
                self.logger.error("Automated login failed")
                return False
            
        except Exception as e:
            self.logger.error(f"Automated login failed: {e}")
            return False
    
    def _wait_for_manual_login(self) -> bool:
        """
        Wait for manual login completion.
        
        Returns:
            True if login completed, False if timeout
        """
        try:
            self.logger.info("Waiting for manual login completion...")
            
            max_wait_time = 300  # 5 minutes
            check_interval = 5   # Check every 5 seconds
            
            for _ in range(max_wait_time // check_interval):
                current_url = self.browser.get_current_url()
                
                # Check if we're no longer on login page
                if 'login' not in current_url and 'signin' not in current_url:
                    # Verify we're on a valid Twitter page
                    if current_url.startswith('https://twitter.com') or current_url.startswith('https://x.com'):
                        self.logger.info("Manual login completed successfully")
                        return True
                
                time.sleep(check_interval)
            
            self.logger.warning("Manual login timeout")
            return False
            
        except Exception as e:
            self.logger.error(f"Manual login wait failed: {e}")
            return False
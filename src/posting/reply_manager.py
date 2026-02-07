"""
Reply Manager component for automated reply posting.
Handles finding posts with images and replying to them with captions and images.
"""

import logging
import random
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import json
import uuid

from ..models.post import Post, PostStatus
from ..utils.file_manager import FileManager


class ReplyManager:
    """Manages automated reply posting to tweets with images."""
    
    def __init__(self, file_manager: FileManager, config: Dict[str, Any] = None):
        """
        Initialize reply manager.
        
        Args:
            file_manager: File manager instance for data persistence
            config: Configuration dictionary with reply settings
        """
        self.file_manager = file_manager
        self.logger = logging.getLogger(__name__)
        self.config = config or {}
        
        # Reply configuration
        self.reply_interval = self.config.get('reply_interval', 300)  # Default 5 minutes
        self.randomness_percent = self.config.get('randomness_percent', 25)  # Default 25% randomness
        self.last_reply_time: Optional[datetime] = None
        
        # Selectors for reply automation
        self.selectors = {
            'tweet_container': 'article[data-testid="tweet"]',
            'tweet_text': 'article[data-testid="tweet"] [data-testid="tweetText"]',
            'user_name': 'article[data-testid="tweet"] [data-testid="User-Name"]',
            'tweet_photo': 'article[data-testid="tweet"] [data-testid="tweetPhoto"]',
            'reply_button_inline': 'button[data-testid="tweetButtonInline"]',
            'file_input': 'input[type="file"]',
            'add_photo_button': 'button[aria-label="Add photos or video"]',
            'reply_textarea': 'div[data-testid="tweetTextarea_0"]',
            'toast_notification': 'div[data-testid="toast"]'
        }
        
        self.logger.info("Reply Manager initialized")
    
    def calculate_randomized_interval(self, base_interval: int) -> int:
        """
        Calculate randomized reply interval to avoid detection patterns.
        
        Args:
            base_interval: Base interval in seconds
            
        Returns:
            Randomized interval in seconds
        """
        try:
            # Calculate variation range
            variation = int(base_interval * (self.randomness_percent / 100))
            
            # Generate random offset within ±variation
            offset = random.randint(-variation, variation)
            
            # Apply offset
            randomized_interval = base_interval + offset
            
            # Ensure interval is positive
            randomized_interval = max(1, randomized_interval)
            
            self.logger.debug(f"Randomized reply interval: {base_interval}s → {randomized_interval}s (±{self.randomness_percent}%)")
            
            return randomized_interval
            
        except Exception as e:
            self.logger.error(f"Failed to calculate randomized interval: {e}")
            return base_interval
    
    def is_ready_for_next_reply(self) -> bool:
        """
        Check if enough time has passed for the next reply.
        
        Returns:
            True if ready for next reply, False otherwise
        """
        if not self.last_reply_time:
            return True
        
        randomized_interval = self.calculate_randomized_interval(self.reply_interval)
        next_reply_time = self.last_reply_time + timedelta(seconds=randomized_interval)
        
        return datetime.now() >= next_reply_time
    
    def mark_reply_posted(self) -> None:
        """Mark that a reply was just posted."""
        self.last_reply_time = datetime.now()
        self.logger.info(f"Reply posted at {self.last_reply_time}")
    
    def get_time_until_next_reply(self) -> Optional[int]:
        """
        Get seconds until next reply is allowed.
        
        Returns:
            Seconds until next reply, 0 if ready now, None if never posted
        """
        if not self.last_reply_time:
            return 0
        
        randomized_interval = self.calculate_randomized_interval(self.reply_interval)
        next_reply_time = self.last_reply_time + timedelta(seconds=randomized_interval)
        
        time_diff = (next_reply_time - datetime.now()).total_seconds()
        return max(0, int(time_diff))
    
    def generate_reply_content(self) -> Optional[Dict[str, Any]]:
        """
        Generate reply content from captions and images library.
        
        Returns:
            Dictionary with 'content' and 'images' keys, or None if generation fails
        """
        try:
            # Load captions
            captions_file = Path("data/captions.json")
            if not captions_file.exists():
                self.logger.warning("Captions file not found")
                return None
            
            captions_data = json.loads(captions_file.read_text(encoding='utf-8'))
            if not captions_data:
                self.logger.warning("No captions available")
                return None
            
            # Pick random caption
            caption_obj = random.choice(captions_data)
            content = caption_obj['content']
            
            # Load image groups - OPTIONAL (images are not required)
            images = []  # Default to empty list (text-only reply)
            img_file = Path("data/image_groups.json")
            if img_file.exists():
                try:
                    groups = json.loads(img_file.read_text(encoding='utf-8'))
                    if groups:
                        # Pick random image group and select only ONE image from it
                        group = random.choice(groups)
                        all_images = group['images']
                        
                        # Select only one random image from the group
                        selected_image = random.choice(all_images)
                        images = [selected_image]  # Single image in list
                        self.logger.debug(f"Selected image for reply: {selected_image}")
                except Exception as img_error:
                    self.logger.warning(f"Could not load images, creating text-only reply: {img_error}")
                    images = []
            else:
                self.logger.info("No image_groups.json found, creating text-only reply")
            
            reply_data = {
                'content': content,
                'images': images
            }
            
            if images:
                self.logger.info(f"Generated reply content with 1 image")
            else:
                self.logger.info(f"Generated text-only reply content")
            
            return reply_data
            
        except Exception as e:
            self.logger.error(f"Error generating reply content: {e}")
            return None
    
    async def find_tweet_with_image(self, browser) -> Optional[Dict[str, Any]]:
        """
        Find a tweet with an image on the current page.
        
        Args:
            browser: Browser driver instance
            
        Returns:
            Dictionary with tweet element and info, or None if not found
        """
        try:
            self.logger.info("Searching for tweets with images...")
            
            # Find all tweet containers
            tweet_containers = await browser.find_elements(self.selectors['tweet_container'])
            
            if not tweet_containers:
                self.logger.warning("No tweet containers found")
                return None
            
            self.logger.info(f"Found {len(tweet_containers)} tweet containers")
            
            # Filter tweets that have images
            tweets_with_images = []
            
            for i, tweet in enumerate(tweet_containers):
                try:
                    # Check if this tweet has an image
                    # We need to check within this specific tweet container
                    has_image = await browser.element_has_child(tweet, '[data-testid="tweetPhoto"]')
                    
                    if has_image:
                        # Get tweet text for logging
                        tweet_text_elem = await browser.find_element_in_parent(tweet, '[data-testid="tweetText"]')
                        tweet_text = ""
                        if tweet_text_elem:
                            tweet_text = await browser.get_element_text(tweet_text_elem)
                        
                        # Get username
                        username_elem = await browser.find_element_in_parent(tweet, '[data-testid="User-Name"]')
                        username = ""
                        if username_elem:
                            username = await browser.get_element_text(username_elem)
                        
                        tweets_with_images.append({
                            'element': tweet,
                            'text': tweet_text[:100] if tweet_text else "No text",
                            'username': username,
                            'index': i
                        })
                        
                        self.logger.debug(f"Tweet {i} has image - User: {username}")
                
                except Exception as e:
                    self.logger.debug(f"Error checking tweet {i}: {e}")
                    continue
            
            if not tweets_with_images:
                self.logger.warning("No tweets with images found on current page")
                return None
            
            # Select a random tweet with image
            selected_tweet = random.choice(tweets_with_images)
            self.logger.info(f"Selected tweet with image (index {selected_tweet['index']}): {selected_tweet['username']}")
            
            return selected_tweet
            
        except Exception as e:
            self.logger.error(f"Error finding tweet with image: {e}")
            return None
    
    async def scroll_page_human_like(self, browser) -> bool:
        """
        Scroll the page in a human-like manner.
        
        Args:
            browser: Browser driver instance
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Random number of scroll actions
            num_scrolls = random.randint(2, 5)
            self.logger.info(f"Performing {num_scrolls} human-like scroll actions")
            
            for i in range(num_scrolls):
                # Random scroll direction and amount
                scroll_down = random.choice([True, True, True, False])  # 75% down, 25% up
                
                if scroll_down:
                    scroll_amount = random.randint(200, 600)
                    await browser.scroll_page(scroll_amount)
                    self.logger.debug(f"Scrolled down {scroll_amount}px")
                else:
                    scroll_amount = random.randint(-300, -100)
                    await browser.scroll_page(scroll_amount)
                    self.logger.debug(f"Scrolled up {abs(scroll_amount)}px")
                
                # Random pause between scrolls
                await asyncio.sleep(random.uniform(1.0, 3.0))
            
            # Final pause to "read" content
            await asyncio.sleep(random.uniform(2.0, 4.0))
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error during human-like scrolling: {e}")
            return False
    
    def get_reply_status(self) -> Dict[str, Any]:
        """
        Get current reply status information.
        
        Returns:
            Dictionary with reply status
        """
        time_until_next = self.get_time_until_next_reply()
        
        return {
            'reply_interval': self.reply_interval,
            'randomness_percent': self.randomness_percent,
            'last_reply_time': self.last_reply_time.isoformat() if self.last_reply_time else None,
            'ready_for_reply': self.is_ready_for_next_reply(),
            'time_until_next_reply': time_until_next,
            'next_reply_time': (self.last_reply_time + timedelta(seconds=self.calculate_randomized_interval(self.reply_interval))).isoformat() if self.last_reply_time else None
        }
    
    def update_reply_interval(self, interval: int) -> bool:
        """
        Update the reply interval.
        
        Args:
            interval: New interval in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if interval < 60:  # Minimum 1 minute
                self.logger.error(f"Reply interval too short: {interval}s (minimum 60s)")
                return False
            
            old_interval = self.reply_interval
            self.reply_interval = interval
            
            self.logger.info(f"Updated reply interval: {old_interval}s -> {interval}s")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update reply interval: {e}")
            return False

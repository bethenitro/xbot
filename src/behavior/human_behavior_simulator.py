"""
Human Behavior Simulator component for realistic interaction patterns.
Implements realistic human interaction patterns for typing and scrolling.
"""

import random
import asyncio
import logging
from typing import List, Any, Dict


class HumanBehaviorSimulator:
    """Implements realistic human interaction patterns for typing and scrolling."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize human behavior simulator.
        
        Args:
            config: Behavior configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Typing configuration
        self.typing_delay_min = config.get('typing_delay_min', 50)  # ms
        self.typing_delay_max = config.get('typing_delay_max', 200)  # ms
        
        # Scrolling configuration
        self.scroll_pause_min = config.get('scroll_pause_min', 1000)  # ms
        self.scroll_pause_max = config.get('scroll_pause_max', 3000)  # ms
        
        # Reading pause configuration
        self.reading_pause_min = config.get('reading_pause_min', 5)  # seconds
        self.reading_pause_max = config.get('reading_pause_max', 15)  # seconds
        
        # Timing fluctuation (±20% variation)
        self.timing_fluctuation = config.get('timing_fluctuation', 0.2)
        
        # Random Twitter pages for stealth visits
        self.random_pages = [
            'https://twitter.com/explore',
            'https://twitter.com/notifications',
            'https://twitter.com/messages',
            'https://twitter.com/bookmarks',
            'https://twitter.com/i/trends',
            'https://twitter.com/settings',
            'https://twitter.com/home'
        ]
    
    async def type_with_human_timing(self, element: Any, text: str, clear_first: bool = True) -> bool:
        """
        Type text with realistic human keystroke delays.
        
        Args:
            element: ZenDriver element to type into
            text: Text to type
            clear_first: Whether to clear existing text first
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not element or not text:
                return False
            
            # Clear existing text if requested
            if clear_first:
                if hasattr(element, 'clear_input_by_deleting'):
                    await element.clear_input_by_deleting()
                else:
                    await element.click()
                    await element.send_keys('\x01')  # Ctrl+A
                    await element.send_keys('\x08')  # Backspace
                await self._add_typing_delay()
            
            # Click to focus
            await element.click()
            await self._add_typing_delay()
            
            # Type each character with human-like delays
            for i, char in enumerate(text):
                await element.send_keys(char)
                
                # Add realistic delay between keystrokes
                if i < len(text) - 1:  # Don't delay after last character
                    await self._add_keystroke_delay()
                
                # Occasionally add longer pauses (thinking/hesitation)
                if random.random() < 0.05:  # 5% chance
                    await self._add_thinking_pause()
            
            # Add final delay after typing
            await self._add_typing_delay()
            
            self.logger.debug(f"Typed text with human timing: {len(text)} characters")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to type with human timing: {e}")
            return False
    
    async def perform_random_scroll(self, browser: Any, scroll_count: int = None) -> bool:
        """
        Execute random scrolling behavior to simulate reading.
        
        Args:
            browser: Browser instance
            scroll_count: Number of scroll actions (random if None)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not browser:
                return False
            
            # Determine number of scroll actions
            if scroll_count is None:
                scroll_count = random.randint(2, 5)
            
            for _ in range(scroll_count):
                # Random scroll direction and amount
                if random.random() < 0.8:  # 80% chance to scroll down
                    scroll_pixels = random.randint(200, 600)
                    await browser.execute_script(f"window.scrollBy(0, {scroll_pixels});")
                else:  # 20% chance to scroll up
                    scroll_pixels = random.randint(100, 300)
                    await browser.execute_script(f"window.scrollBy(0, -{scroll_pixels});")
                
                # Add pause between scrolls
                await self._add_scroll_pause()
                
                # Occasionally add reading pause
                if random.random() < 0.3:  # 30% chance
                    await self._add_reading_pause()
            
            self.logger.debug(f"Performed {scroll_count} random scroll actions")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to perform random scroll: {e}")
            return False
    
    async def add_reading_pause(self) -> None:
        """Add realistic reading pause to simulate human behavior."""
        pause_duration = self._get_reading_pause_duration()
        self.logger.debug(f"Adding reading pause: {pause_duration:.1f}s")
        await asyncio.sleep(pause_duration)
    
    def generate_random_page_visits(self, count: int = None) -> List[str]:
        """
        Generate list of random Twitter pages to visit for stealth.
        
        Args:
            count: Number of pages to generate (random if None)
            
        Returns:
            List of Twitter page URLs
        """
        if count is None:
            count = random.randint(2, 3)
        
        # Select random pages without replacement
        selected_pages = random.sample(self.random_pages, min(count, len(self.random_pages)))
        
        self.logger.debug(f"Generated {len(selected_pages)} random page visits")
        return selected_pages
    
    async def simulate_page_reading(self, browser: Any, min_time: float = 3.0, max_time: float = 8.0) -> bool:
        """
        Simulate reading a page with scrolling and pauses.
        
        Args:
            browser: Browser instance
            min_time: Minimum time to spend on page (seconds)
            max_time: Maximum time to spend on page (seconds)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not browser:
                return False
            
            total_time = random.uniform(min_time, max_time)
            end_time = asyncio.get_event_loop().time() + total_time
            
            while asyncio.get_event_loop().time() < end_time:
                # Perform random action
                action = random.choice(['scroll', 'pause', 'small_scroll'])
                
                if action == 'scroll':
                    await self.perform_random_scroll(browser, scroll_count=1)
                elif action == 'pause':
                    await self._add_reading_pause()
                elif action == 'small_scroll':
                    # Small scroll to simulate fine reading
                    pixels = random.randint(50, 150)
                    try:
                        # Use browser's execute_script which is async
                        await browser.execute_script(f"window.scrollBy(0, {pixels});")
                    except:
                        # Fallback to direct tab.evaluate if browser is ZenDriverDriver
                        if hasattr(browser, 'tab') and browser.tab:
                            await browser.tab.evaluate(f"window.scrollBy(0, {pixels});")
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                
                # Check if we've spent enough time
                if asyncio.get_event_loop().time() >= end_time:
                    break
            
            self.logger.debug(f"Simulated page reading for {total_time:.1f}s")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to simulate page reading: {e}")
            return False
    
    async def add_random_mouse_movement(self, browser: Any) -> bool:
        """
        Add random mouse movement (ZenDriver handles this natively).
        
        Args:
            browser: Browser instance
            
        Returns:
            True (ZenDriver handles mouse movement automatically)
        """
        # ZenDriver has built-in human-like cursor movement
        # We just add a small delay to allow it to work
        await self._add_mouse_delay()
        return True
    
    async def simulate_typing_mistakes(self, element: Any, text: str, mistake_probability: float = 0.02) -> bool:
        """
        Simulate typing with occasional mistakes and corrections.
        
        Args:
            element: ZenDriver element to type into
            text: Text to type
            mistake_probability: Probability of making a mistake per character
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not element or not text:
                return False
            
            await element.click()
            await self._add_typing_delay()
            
            for i, char in enumerate(text):
                # Occasionally make a typing mistake
                if random.random() < mistake_probability:
                    # Type wrong character
                    wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                    await element.send_keys(wrong_char)
                    await self._add_keystroke_delay()
                    
                    # Pause (realize mistake)
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                    
                    # Backspace to correct
                    await element.send_keys('\x08') # Backspace
                    await self._add_keystroke_delay()
                
                # Type correct character
                await element.send_keys(char)
                
                if i < len(text) - 1:
                    await self._add_keystroke_delay()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to simulate typing with mistakes: {e}")
            return False
    
    async def _add_keystroke_delay(self) -> None:
        """Add delay between keystrokes (50-200ms with fluctuation)."""
        base_delay = random.uniform(self.typing_delay_min, self.typing_delay_max) / 1000.0
        fluctuated_delay = self._apply_timing_fluctuation(base_delay)
        await asyncio.sleep(fluctuated_delay)
    
    async def _add_typing_delay(self) -> None:
        """Add delay for typing actions (200-500ms)."""
        delay = random.uniform(0.2, 0.5)
        fluctuated_delay = self._apply_timing_fluctuation(delay)
        await asyncio.sleep(fluctuated_delay)
    
    async def _add_scroll_pause(self) -> None:
        """Add pause between scroll actions."""
        base_delay = random.uniform(self.scroll_pause_min, self.scroll_pause_max) / 1000.0
        fluctuated_delay = self._apply_timing_fluctuation(base_delay)
        await asyncio.sleep(fluctuated_delay)
    
    async def _add_reading_pause(self) -> None:
        """Add reading pause (5-15 seconds with fluctuation)."""
        pause_duration = self._get_reading_pause_duration()
        await asyncio.sleep(pause_duration)
    
    async def _add_thinking_pause(self) -> None:
        """Add thinking/hesitation pause during typing."""
        delay = random.uniform(0.3, 1.2)
        fluctuated_delay = self._apply_timing_fluctuation(delay)
        await asyncio.sleep(fluctuated_delay)
    
    async def _add_mouse_delay(self) -> None:
        """Add small delay for mouse movements."""
        delay = random.uniform(0.1, 0.3)
        await asyncio.sleep(delay)
    
    def _get_reading_pause_duration(self) -> float:
        """Get reading pause duration with fluctuation."""
        base_duration = random.uniform(self.reading_pause_min, self.reading_pause_max)
        return self._apply_timing_fluctuation(base_duration)
    
    def _apply_timing_fluctuation(self, base_time: float) -> float:
        """
        Apply timing fluctuation (±20% variation) to base time.
        
        Args:
            base_time: Base time in seconds
            
        Returns:
            Time with fluctuation applied
        """
        fluctuation = random.uniform(-self.timing_fluctuation, self.timing_fluctuation)
        fluctuated_time = base_time * (1 + fluctuation)
        
        # Ensure minimum time
        return max(fluctuated_time, 0.01)
    
    def get_random_delay_range(self, min_seconds: float, max_seconds: float) -> float:
        """
        Get random delay with timing fluctuation applied.
        
        Args:
            min_seconds: Minimum delay
            max_seconds: Maximum delay
            
        Returns:
            Random delay with fluctuation
        """
        base_delay = random.uniform(min_seconds, max_seconds)
        return self._apply_timing_fluctuation(base_delay)
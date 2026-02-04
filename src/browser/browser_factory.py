"""
Browser Factory for managing ZenDriver.
Handles initialization of ZenDriver driver only.
"""

import logging
from typing import Dict, Any

from .zendriver_driver import ZenDriverDriver


class BrowserFactory:
    """Factory class for creating ZenDriver browser instances."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._is_initialized = False
    
    def create_driver(self, config: Dict[str, Any]) -> ZenDriverDriver:
        """
        Create a ZenDriver browser instance.
        
        Args:
            config: Browser configuration dictionary
            
        Returns:
            ZenDriver browser instance
            
        Raises:
            ImportError: If ZenDriver dependencies are not installed
        """
        try:
            if not self._is_initialized:
                self.logger.info("Creating ZenDriver instance")
                self._is_initialized = True
            
            return ZenDriverDriver(config)
                
        except ImportError as e:
            raise ImportError(
                f"ZenDriver is not installed. Please install it with: pip install zendriver"
            ) from e
    
    def get_available_browsers(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about ZenDriver availability.
        
        Returns:
            Dictionary with browser info and availability
        """
        browsers = {}
        
        # Check ZenDriver availability
        try:
            import zendriver
            browsers["zendriver"] = {
                "name": "ZenDriver",
                "description": "Chrome DevTools Protocol-based automation (no WebDriver)",
                "available": True,
                "type": "chrome",
                "features": [
                    "Maximum stealth (no WebDriver)",
                    "Chrome DevTools Protocol",
                    "Blazing fast performance",
                    "Undetectable by anti-bot systems"
                ]
            }
        except ImportError:
            browsers["zendriver"] = {
                "name": "ZenDriver",
                "description": "Chrome DevTools Protocol-based automation (no WebDriver)",
                "available": False,
                "type": "chrome",
                "install_command": "pip install zendriver",
                "features": [
                    "Maximum stealth (no WebDriver)",
                    "Chrome DevTools Protocol",
                    "Blazing fast performance",
                    "Undetectable by anti-bot systems"
                ]
            }
        
        return browsers


# Global browser factory instance
browser_factory = BrowserFactory()
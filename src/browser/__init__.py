"""
Browser automation module for the Enhanced Twitter Bot system.
Provides ZenDriver browser automation with stealth capabilities.
"""

from .zendriver_driver import ZenDriverDriver
from .browser_factory import BrowserFactory, browser_factory

__all__ = [
    'ZenDriverDriver',
    'BrowserFactory',
    'browser_factory'
]
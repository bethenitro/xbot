"""
Configuration schema and validation for the Enhanced Twitter Bot system.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import json


@dataclass
class PostingIntervals:
    """Configuration for posting intervals."""
    default: int = 3600  # 1 hour default
    min: int = 1         # 1 second minimum (no practical limit)
    max: int = 86400     # 24 hours maximum
    randomness_percent: int = 25  # Randomness percentage for intervals


@dataclass
class BehaviorSettings:
    """Configuration for human behavior simulation."""
    typing_delay_min: int = 50      # Minimum keystroke delay in ms
    typing_delay_max: int = 200     # Maximum keystroke delay in ms
    scroll_pause_min: int = 1000    # Minimum scroll pause in ms
    scroll_pause_max: int = 3000    # Maximum scroll pause in ms
    reading_pause_min: int = 5      # Minimum reading pause in seconds
    reading_pause_max: int = 15     # Maximum reading pause in seconds
    timing_fluctuation: float = 0.2  # ±20% timing variation


@dataclass
class StealthSettings:
    """Configuration for stealth and anti-detection features."""
    enabled: bool = True                 # Enable stealth mode by default
    random_visits: bool = True           # Visit random pages before posting
    random_visits_count_min: int = 2     # Minimum random page visits
    random_visits_count_max: int = 3     # Maximum random page visits
    fingerprint_consistency: bool = True # Keep consistent fingerprints per account
    humanize_cursor: bool = True         # Use ZenDriver human-like cursor movement
    max_cursor_time: float = 1.5         # Maximum time for cursor movements
    show_cursor: bool = False            # Show cursor highlighter (debug mode)
    auto_refresh_cookies: bool = True    # Auto-refresh cookies after posts


@dataclass
class BrowserSettings:
    """Configuration for browser automation."""
    browser_type: str = "zendriver"      # Browser engine type (zendriver only)
    headless: bool = False               # Run browser in headless mode
    window_width: int = 1920            # Browser window width
    window_height: int = 1080           # Browser window height
    user_data_dir: Optional[str] = None # Custom user data directory
    timeout: int = 30                   # Default timeout for operations in seconds
    max_concurrent_browsers: int = 1     # Maximum number of concurrent browsers (1-5)


@dataclass
class SessionSettings:
    """Configuration for session management."""
    session_timeout: int = 3600         # Session timeout in seconds (1 hour)
    auto_save: bool = True              # Auto-save sessions by default
    auto_save_cookies: bool = True      # Automatically save cookies after login
    max_session_age: int = 86400        # Maximum session age in seconds (24 hours)


@dataclass
class AutomationSettings:
    """Configuration for automation selectors."""
    selectors: Dict[str, str] = None

    def __post_init__(self):
        if self.selectors is None:
            self.selectors = {
                "compose_button": "[data-testid='SideNav_NewTweet_Button']",
                "compose_textbox": "[data-testid='tweetTextarea_0']",
                "tweet_button": "[data-testid='tweetButton']",
                "media_upload": "input[data-testid='fileInput']",
                "media_button": "[data-testid='fileInput']",
                # Tweet / Reply selectors
                "tweet_container": "article[data-testid='tweet']",
                "tweet_text": "article[data-testid='tweet'] [data-testid='tweetText']",
                "tweet_user": "article[data-testid='tweet'] [data-testid='User-Name']",
                "tweet_photo": "[data-testid='tweetPhoto']",
                "tweet_inline_button": "button[data-testid='tweetButtonInline']",
                "reply_textbox": "div[data-testid='tweetTextarea_0']",
                "file_input": "input[type='file']",
                "add_media_button": "button[aria-label='Add photos or video']",
                "join_button": "//button[normalize-space(.)='Join']",
                "joined_button": "//button[.//span[text()='Joined']]",
                "agree_join_button": "//button[.//span[normalize-space(text())='Agree and join']]"
            }


@dataclass
class ReplySettings:
    """Configuration for automated reply posting."""
    enabled: bool = False               # Enable reply posting feature
    reply_interval: int = 300           # Default reply interval in seconds (5 minutes)
    randomness_percent: int = 25        # Randomness percentage for reply intervals
    min_scroll_actions: int = 2         # Minimum scroll actions before selecting tweet
    max_scroll_actions: int = 5         # Maximum scroll actions before selecting tweet


@dataclass
class ErrorHandling:
    """Configuration for error handling and recovery."""
    max_retries: int = 3                # Maximum retry attempts
    retry_delay_base: int = 1           # Base delay for exponential backoff in seconds
    rate_limit_pause: int = 900         # Pause duration for rate limits in seconds (15 min)
    skip_failed_posts: bool = True      # Skip posts that fail repeatedly
    log_level: str = "INFO"             # Logging level (DEBUG, INFO, WARNING, ERROR)


@dataclass
class ConfigSchema:
    """Complete configuration schema for the Enhanced Twitter Bot."""
    posting_intervals: PostingIntervals
    behavior_settings: BehaviorSettings
    stealth_settings: StealthSettings
    browser_settings: BrowserSettings
    session_settings: SessionSettings
    reply_settings: ReplySettings
    error_handling: ErrorHandling
    automation: AutomationSettings = None

    def __post_init__(self):
        if self.automation is None:
            self.automation = AutomationSettings()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'posting_intervals': {
                'default': self.posting_intervals.default,
                'min': self.posting_intervals.min,
                'max': self.posting_intervals.max,
                'randomness_percent': self.posting_intervals.randomness_percent
            },
            'behavior_settings': {
                'typing_delay_min': self.behavior_settings.typing_delay_min,
                'typing_delay_max': self.behavior_settings.typing_delay_max,
                'scroll_pause_min': self.behavior_settings.scroll_pause_min,
                'scroll_pause_max': self.behavior_settings.scroll_pause_max,
                'reading_pause_min': self.behavior_settings.reading_pause_min,
                'reading_pause_max': self.behavior_settings.reading_pause_max,
                'timing_fluctuation': self.behavior_settings.timing_fluctuation
            },
            'stealth_settings': {
                'enabled': self.stealth_settings.enabled,
                'random_visits': self.stealth_settings.random_visits,
                'random_visits_count_min': self.stealth_settings.random_visits_count_min,
                'random_visits_count_max': self.stealth_settings.random_visits_count_max,
                'fingerprint_consistency': self.stealth_settings.fingerprint_consistency,
                'humanize_cursor': self.stealth_settings.humanize_cursor,
                'max_cursor_time': self.stealth_settings.max_cursor_time,
                'show_cursor': self.stealth_settings.show_cursor,
                'auto_refresh_cookies': self.stealth_settings.auto_refresh_cookies
            },
            'browser_settings': {
                'browser_type': self.browser_settings.browser_type,
                'headless': self.browser_settings.headless,
                'window_width': self.browser_settings.window_width,
                'window_height': self.browser_settings.window_height,
                'user_data_dir': self.browser_settings.user_data_dir,
                'timeout': self.browser_settings.timeout,
                'max_concurrent_browsers': self.browser_settings.max_concurrent_browsers
            },
            'session_settings': {
                'session_timeout': self.session_settings.session_timeout,
                'auto_save': self.session_settings.auto_save,
                'auto_save_cookies': self.session_settings.auto_save_cookies,
                'max_session_age': self.session_settings.max_session_age
            },
            'reply_settings': {
                'enabled': self.reply_settings.enabled,
                'reply_interval': self.reply_settings.reply_interval,
                'randomness_percent': self.reply_settings.randomness_percent,
                'min_scroll_actions': self.reply_settings.min_scroll_actions,
                'max_scroll_actions': self.reply_settings.max_scroll_actions
            },
            'error_handling': {
                'max_retries': self.error_handling.max_retries,
                'retry_delay_base': self.error_handling.retry_delay_base,
                'rate_limit_pause': self.error_handling.rate_limit_pause,
                'skip_failed_posts': self.error_handling.skip_failed_posts,
                'log_level': self.error_handling.log_level
            },
            'automation': {
                'selectors': self.automation.selectors
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConfigSchema':
        """Create configuration from dictionary."""
        return cls(
            posting_intervals=PostingIntervals(**data.get('posting_intervals', {})),
            behavior_settings=BehaviorSettings(**data.get('behavior_settings', {})),
            stealth_settings=StealthSettings(**data.get('stealth_settings', {})),
            browser_settings=BrowserSettings(**data.get('browser_settings', {})),
            session_settings=SessionSettings(**data.get('session_settings', {})),
            reply_settings=ReplySettings(**data.get('reply_settings', {})),
            error_handling=ErrorHandling(**data.get('error_handling', {})),
            automation=AutomationSettings(**data.get('automation', {}))
        )
    
    def validate(self) -> bool:
        """Validate configuration parameters."""
        # Validate posting intervals
        if self.posting_intervals.default < self.posting_intervals.min:
            raise ValueError("Default posting interval cannot be less than minimum")
        if self.posting_intervals.default > self.posting_intervals.max:
            raise ValueError("Default posting interval cannot be greater than maximum")
        
        # Validate behavior settings
        if self.behavior_settings.typing_delay_min >= self.behavior_settings.typing_delay_max:
            raise ValueError("Minimum typing delay must be less than maximum")
        if self.behavior_settings.scroll_pause_min >= self.behavior_settings.scroll_pause_max:
            raise ValueError("Minimum scroll pause must be less than maximum")
        if self.behavior_settings.reading_pause_min >= self.behavior_settings.reading_pause_max:
            raise ValueError("Minimum reading pause must be less than maximum")
        if not 0 <= self.behavior_settings.timing_fluctuation <= 1:
            raise ValueError("Timing fluctuation must be between 0 and 1")
        
        # Validate stealth settings
        if self.stealth_settings.random_visits_count_min >= self.stealth_settings.random_visits_count_max:
            raise ValueError("Minimum random visits must be less than maximum")
        if self.stealth_settings.max_cursor_time <= 0:
            raise ValueError("Maximum cursor time must be positive")
        
        # Validate browser settings
        if self.browser_settings.browser_type != 'zendriver':
            raise ValueError("Browser type must be 'zendriver'")
        if self.browser_settings.window_width <= 0 or self.browser_settings.window_height <= 0:
            raise ValueError("Browser window dimensions must be positive")
        if self.browser_settings.timeout <= 0:
            raise ValueError("Browser timeout must be positive")
        if not 1 <= self.browser_settings.max_concurrent_browsers <= 5:
            raise ValueError("Maximum concurrent browsers must be between 1 and 5")
        
        # Validate session settings
        if self.session_settings.session_timeout <= 0:
            raise ValueError("Session timeout must be positive")
        if self.session_settings.max_session_age <= 0:
            raise ValueError("Maximum session age must be positive")
        
        # Validate error handling
        if self.error_handling.max_retries < 0:
            raise ValueError("Maximum retries cannot be negative")
        if self.error_handling.retry_delay_base <= 0:
            raise ValueError("Retry delay base must be positive")
        if self.error_handling.rate_limit_pause <= 0:
            raise ValueError("Rate limit pause must be positive")
        if self.error_handling.log_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
            raise ValueError("Invalid log level")
        
        return True


# Default configuration instance
DEFAULT_CONFIG = ConfigSchema(
    posting_intervals=PostingIntervals(),
    behavior_settings=BehaviorSettings(),
    stealth_settings=StealthSettings(),
    browser_settings=BrowserSettings(),
    session_settings=SessionSettings(),
    reply_settings=ReplySettings(),
    error_handling=ErrorHandling()
)
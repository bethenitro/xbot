"""
Session data model for the Enhanced Twitter Bot system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class Session:
    """
    Represents a browser session with authentication and fingerprint data.
    
    Attributes:
        session_id: Unique identifier for the session
        browser_instance: Reference to the browser automation instance
        cookies: Encrypted authentication cookies
        fingerprint: Browser fingerprint data for stealth operations
        created_at: When the session was created
        last_activity: Timestamp of the last session activity
        authenticated: Whether the session is currently authenticated
    """
    session_id: str
    browser_instance: Any
    cookies: Dict[str, str] = field(default_factory=dict)
    fingerprint: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    authenticated: bool = False
    
    def __post_init__(self):
        """Validate session data after initialization."""
        if not self.session_id.strip():
            raise ValueError("Session ID cannot be empty")
    
    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity = datetime.now()
    
    def is_expired(self, timeout_seconds: int = 3600) -> bool:
        """
        Check if the session has expired based on inactivity.
        
        Args:
            timeout_seconds: Session timeout in seconds (default: 1 hour)
            
        Returns:
            True if session has expired, False otherwise
        """
        time_since_activity = (datetime.now() - self.last_activity).total_seconds()
        return time_since_activity > timeout_seconds
    
    def has_valid_cookies(self) -> bool:
        """Check if the session has authentication cookies."""
        # After manual login, if we have any cookies, consider it valid
        # This is less strict than checking for specific cookie names
        return len(self.cookies) > 0
    
    def clear_authentication(self) -> None:
        """Clear authentication data from the session."""
        self.authenticated = False
        self.cookies.clear()
    
    def set_authenticated(self, cookies: Dict[str, str]) -> None:
        """
        Mark session as authenticated and store cookies.
        
        Args:
            cookies: Authentication cookies to store
        """
        self.authenticated = True
        self.cookies.update(cookies)
        self.update_activity()
    
    def get_session_age(self) -> float:
        """Get the age of the session in seconds."""
        return (datetime.now() - self.created_at).total_seconds()
    
    def to_dict(self) -> dict:
        """Convert session to dictionary for serialization (excluding browser_instance)."""
        return {
            'session_id': self.session_id,
            'cookies': self.cookies,
            'fingerprint': self.fingerprint,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'authenticated': self.authenticated
        }
    
    @classmethod
    def from_dict(cls, data: dict, browser_instance: Any = None) -> 'Session':
        """
        Create session from dictionary.
        
        Args:
            data: Dictionary containing session data
            browser_instance: Browser instance to associate with session
            
        Returns:
            Session instance
        """
        return cls(
            session_id=data['session_id'],
            browser_instance=browser_instance,
            cookies=data.get('cookies', {}),
            fingerprint=data.get('fingerprint', {}),
            created_at=datetime.fromisoformat(data['created_at']),
            last_activity=datetime.fromisoformat(data['last_activity']),
            authenticated=data.get('authenticated', False)
        )
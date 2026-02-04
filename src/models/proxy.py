"""
Proxy data models for the Enhanced Twitter Bot system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
import json


@dataclass
class ProxyData:
    """Data model for proxy configuration and status."""
    
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "http"  # http, https, socks4, socks5
    rotation_url: Optional[str] = None
    location: Optional[str] = None
    
    # Status tracking
    status: str = "unknown"  # unknown, active, failed, testing
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[datetime] = None
    last_tested: Optional[datetime] = None
    
    # Performance metrics
    avg_response_time: float = 0.0
    last_response_time: float = 0.0
    
    def __post_init__(self):
        """Initialize computed properties."""
        if isinstance(self.last_used, str):
            self.last_used = datetime.fromisoformat(self.last_used)
        if isinstance(self.last_tested, str):
            self.last_tested = datetime.fromisoformat(self.last_tested)
    
    @property
    def url(self) -> str:
        """Get the proxy URL."""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.protocol}://{self.host}:{self.port}"
    
    @property
    def display_url(self) -> str:
        """Get a display-friendly URL (without credentials)."""
        return f"{self.protocol}://{self.host}:{self.port}"
    
    @property
    def is_working(self) -> bool:
        """Check if proxy is currently working."""
        return self.status == "active"
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return (self.success_count / total) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'password': self.password,
            'protocol': self.protocol,
            'rotation_url': self.rotation_url,
            'location': self.location,
            'status': self.status,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'last_tested': self.last_tested.isoformat() if self.last_tested else None,
            'avg_response_time': self.avg_response_time,
            'last_response_time': self.last_response_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProxyData':
        """Create instance from dictionary."""
        return cls(**data)
    
    def update_success(self, response_time: float = 0.0):
        """Update proxy after successful use."""
        self.success_count += 1
        self.status = "active"
        self.last_used = datetime.now()
        self.last_tested = datetime.now()
        
        # Update response time metrics
        if response_time > 0:
            self.last_response_time = response_time
            if self.avg_response_time == 0:
                self.avg_response_time = response_time
            else:
                # Exponential moving average
                self.avg_response_time = (self.avg_response_time * 0.7) + (response_time * 0.3)
    
    def update_failure(self):
        """Update proxy after failure."""
        self.failure_count += 1
        self.last_tested = datetime.now()
        
        # Mark as failed if too many failures
        if self.failure_count >= 3:
            self.status = "failed"
    
    def reset_stats(self):
        """Reset proxy statistics."""
        self.success_count = 0
        self.failure_count = 0
        self.status = "unknown"
        self.last_used = None
        self.last_tested = None
        self.avg_response_time = 0.0
        self.last_response_time = 0.0


@dataclass
class AccountData:
    """Data model for Twitter account configuration."""
    
    username: str
    preferred_proxy: Optional[str] = None
    cookies_file: Optional[str] = None
    session_data: Optional[Dict[str, Any]] = None
    
    # Fingerprint consistency - NEVER change these once set
    fingerprint_data: Optional[Dict[str, Any]] = None
    user_agent: Optional[str] = None
    screen_resolution: Optional[tuple] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    
    # Status tracking
    status: str = "unknown"  # unknown, active, suspended, failed
    last_login: Optional[datetime] = None
    last_used: Optional[datetime] = None
    posts_count: int = 0
    
    # Account settings
    use_proxy: bool = True
    headless_mode: bool = True
    
    def __post_init__(self):
        """Initialize computed properties."""
        if isinstance(self.last_login, str):
            self.last_login = datetime.fromisoformat(self.last_login)
        if isinstance(self.last_used, str):
            self.last_used = datetime.fromisoformat(self.last_used)
    
    @property
    def is_active(self) -> bool:
        """Check if account is active."""
        return self.status == "active"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'username': self.username,
            'preferred_proxy': self.preferred_proxy,
            'cookies_file': self.cookies_file,
            'session_data': self.session_data,
            'fingerprint_data': self.fingerprint_data,
            'user_agent': self.user_agent,
            'screen_resolution': self.screen_resolution,
            'timezone': self.timezone,
            'language': self.language,
            'status': self.status,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'posts_count': self.posts_count,
            'use_proxy': self.use_proxy,
            'headless_mode': self.headless_mode
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AccountData':
        """Create instance from dictionary."""
        return cls(**data)
    
    def update_login(self):
        """Update account after successful login."""
        self.status = "active"
        self.last_login = datetime.now()
    
    def update_post(self):
        """Update account after successful post."""
        self.posts_count += 1
        self.last_used = datetime.now()
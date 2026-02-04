"""
Community Group data model for the Enhanced Twitter Bot system.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class CommunityGroup:
    """
    Represents a group of Twitter communities that share posting schedules.
    
    Attributes:
        name: Unique name identifier for the community group
        communities: List of Twitter community URLs
        posting_interval: Interval between posts in seconds
        last_posted: Timestamp of the last post to this group
        active: Whether this group is currently active for posting
    """
    name: str
    communities: List[str]
    posting_interval: int
    last_posted: Optional[datetime] = None
    active: bool = True
    
    def __post_init__(self):
        """Validate community group data after initialization."""
        if not self.name.strip():
            raise ValueError("Community group name cannot be empty")
        if not self.communities:
            raise ValueError("Community group must have at least one community URL")
        if self.posting_interval < 1800:  # Minimum 30 minutes
            raise ValueError("Posting interval must be at least 1800 seconds (30 minutes)")
        
        # Validate community URLs
        for url in self.communities:
            if not url.strip():
                raise ValueError("Community URL cannot be empty")
            if not (url.startswith('https://twitter.com/') or url.startswith('https://x.com/')):
                raise ValueError(f"Invalid community URL format: {url}")
    
    def is_ready_for_next_post(self) -> bool:
        """Check if enough time has passed since the last post."""
        if not self.active:
            return False
        if self.last_posted is None:
            return True
        
        time_since_last = (datetime.now() - self.last_posted).total_seconds()
        return time_since_last >= self.posting_interval
    
    def mark_posted(self) -> None:
        """Update the last posted timestamp."""
        self.last_posted = datetime.now()
    
    def get_next_post_time(self) -> Optional[datetime]:
        """Get the timestamp when the next post can be made."""
        if not self.active or self.last_posted is None:
            return None
        
        from datetime import timedelta
        return self.last_posted + timedelta(seconds=self.posting_interval)
    
    def to_dict(self) -> dict:
        """Convert community group to dictionary for serialization."""
        return {
            'name': self.name,
            'communities': self.communities,
            'posting_interval': self.posting_interval,
            'last_posted': self.last_posted.isoformat() if self.last_posted else None,
            'active': self.active
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CommunityGroup':
        """Create community group from dictionary."""
        return cls(
            name=data['name'],
            communities=data['communities'],
            posting_interval=data['posting_interval'],
            last_posted=datetime.fromisoformat(data['last_posted']) if data.get('last_posted') else None,
            active=data.get('active', True)
        )
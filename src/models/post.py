"""
Post data model for the Enhanced Twitter Bot system.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional


class PostStatus(Enum):
    """Status of a post in the queue."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    POSTING = "posting"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Post:
    """
    Represents a post in the Twitter bot system.
    
    Attributes:
        id: Unique identifier for the post
        content: Text content of the post
        images: List of image file paths to attach
        community_groups: List of community group names this post belongs to
        status: Current status of the post
        created_at: When the post was created
        scheduled_for: When the post is scheduled to be published (optional)
        posted_at: When the post was actually published (optional)
    """
    id: str
    content: str
    images: List[str]
    community_groups: List[str]
    status: PostStatus
    created_at: datetime
    scheduled_for: Optional[datetime] = None
    posted_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Validate post data after initialization."""
        if not self.id:
            raise ValueError("Post ID cannot be empty")
        if not self.content.strip():
            raise ValueError("Post content cannot be empty")
        if not self.community_groups:
            raise ValueError("Post must belong to at least one community group")
    
    def is_ready_to_post(self) -> bool:
        """Check if the post is ready to be published."""
        return (
            self.status == PostStatus.PENDING and
            (self.scheduled_for is None or self.scheduled_for <= datetime.now())
        )
    
    def mark_completed(self) -> None:
        """Mark the post as completed and set posted timestamp."""
        self.status = PostStatus.COMPLETED
        self.posted_at = datetime.now()
    
    def mark_failed(self) -> None:
        """Mark the post as failed."""
        self.status = PostStatus.FAILED
    
    def to_dict(self) -> dict:
        """Convert post to dictionary for serialization."""
        return {
            'id': self.id,
            'content': self.content,
            'images': self.images,
            'community_groups': self.community_groups,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'scheduled_for': self.scheduled_for.isoformat() if self.scheduled_for else None,
            'posted_at': self.posted_at.isoformat() if self.posted_at else None
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Post':
        """Create post from dictionary."""
        return cls(
            id=data['id'],
            content=data['content'],
            images=data.get('images', []),
            community_groups=data['community_groups'],
            status=PostStatus(data['status']),
            created_at=datetime.fromisoformat(data['created_at']),
            scheduled_for=datetime.fromisoformat(data['scheduled_for']) if data.get('scheduled_for') else None,
            posted_at=datetime.fromisoformat(data['posted_at']) if data.get('posted_at') else None
        )
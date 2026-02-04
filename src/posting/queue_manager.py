"""
Queue Manager component for post queue and completion tracking.
Manages the post queue and tracks posting history.
"""

import logging
import random
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from collections import defaultdict

from ..models.post import Post, PostStatus
from ..utils.file_manager import FileManager


class QueueManager:
    """Manages the post queue and tracks posting history."""
    
    def __init__(self, file_manager: FileManager):
        """
        Initialize queue manager.
        
        Args:
            file_manager: File manager instance for data persistence
        """
        self.file_manager = file_manager
        self.posts: List[Post] = []
        self.logger = logging.getLogger(__name__)
        
        # Load posts from file
        self.reload_posts()
    
    def reload_posts(self) -> bool:
        """
        Reload posts from file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.posts = self.file_manager.read_posts_file()
            self.logger.info(f"Loaded {len(self.posts)} posts from file")
            return True
        except Exception as e:
            self.logger.error(f"Failed to reload posts: {e}")
            return False
    
    def get_next_post(self, community_group: str) -> Optional[Post]:
        """
        Get next post for a specific community group.
        Prioritizes random generation from Library (Captions + Images).
        Fallback to static posts.
        
        Args:
            community_group: Name of the community group
            
        Returns:
            Next available post for the group, None if no posts available
        """
        try:
            # 1. Try to generate a random post from Library
            dynamic_post = self._generate_dynamic_post(community_group)
            if dynamic_post:
                return dynamic_post

            # 2. Fallback to static posts
            # Find pending posts for this community group
            available_posts = [
                post for post in self.posts
                if (post.status == PostStatus.PENDING and
                    community_group in post.community_groups and
                    post.is_ready_to_post())
            ]
            
            if not available_posts:
                self.logger.debug(f"No available posts for community group: {community_group}")
                return None
            
            # Return the oldest post (FIFO)
            next_post = min(available_posts, key=lambda p: p.created_at)
            
            self.logger.info(f"Selected next post for {community_group}: {next_post.id}")
            return next_post
            
        except Exception as e:
            self.logger.error(f"Failed to get next post for {community_group}: {e}")
            return None

    def _generate_dynamic_post(self, community_group: str) -> Optional[Post]:
        """Generate a random post from Captions and Images library."""
        try:
            # Load captions
            captions_file = Path("data/captions.json")
            if not captions_file.exists():
                return None
            
            captions_data = json.loads(captions_file.read_text(encoding='utf-8'))
            if not captions_data:
                return None

            # Load image groups - strict requirement for images
            img_file = Path("data/image_groups.json")
            if not img_file.exists():
                return None
            
            groups = json.loads(img_file.read_text(encoding='utf-8'))
            if not groups:
                return None
                
            # Pick random caption
            caption_obj = random.choice(captions_data)
            content = caption_obj['content']
            
            # Pick random image group (100% pairing)
            group = random.choice(groups)
            images = group['images']
            
            # Create a Post object
            post_id = f"dynamic_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
            post = Post(
                id=post_id,
                content=content,
                images=images,
                community_groups=[community_group],
                status=PostStatus.PENDING,
                created_at=datetime.now()
            )
            self.logger.info(f"Generated dynamic post {post_id} with {len(images)} images")
            return post
            
        except Exception as e:
            self.logger.error(f"Error generating dynamic post: {e}")
            return None
    
    def mark_post_completed(self, post_id: str, community_group: str = None) -> bool:
        """
        Mark a post as successfully published.
        
        Args:
            post_id: ID of the post to mark as completed
            community_group: Community group it was posted to (for history)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if it's a dynamic post
            if post_id.startswith("dynamic_"):
                self.logger.info(f"Dynamic post {post_id} completed (not persisted)")
                return True

            # Find the post
            post = self._find_post_by_id(post_id)
            if not post:
                self.logger.error(f"Post not found: {post_id}")
                return False
            
            # Mark as completed
            post.mark_completed()
            
            # Log to posting history
            history_entry = {
                'post_id': post_id,
                'content_preview': post.content[:100] + '...' if len(post.content) > 100 else post.content,
                'community_group': community_group,
                'status': 'completed',
                'posted_at': post.posted_at.isoformat() if post.posted_at else None,
                'images_count': len(post.images)
            }
            
            self.file_manager.write_posting_history(history_entry)
            
            # Save updated posts to file
            success = self.file_manager.save_posts(self.posts)
            
            if success:
                self.logger.info(f"Marked post as completed: {post_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to mark post as completed: {e}")
            return False
    
    def mark_post_failed(self, post_id: str, error_message: str = None) -> bool:
        """
        Mark a post as failed.
        
        Args:
            post_id: ID of the post to mark as failed
            error_message: Optional error message
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Find the post
            post = self._find_post_by_id(post_id)
            if not post:
                self.logger.error(f"Post not found: {post_id}")
                return False
            
            # Mark as failed
            post.mark_failed()
            
            # Log to posting history
            history_entry = {
                'post_id': post_id,
                'content_preview': post.content[:100] + '...' if len(post.content) > 100 else post.content,
                'status': 'failed',
                'error_message': error_message,
                'failed_at': datetime.now().isoformat()
            }
            
            self.file_manager.write_posting_history(history_entry)
            
            # Save updated posts to file
            success = self.file_manager.save_posts(self.posts)
            
            if success:
                self.logger.warning(f"Marked post as failed: {post_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to mark post as failed: {e}")
            return False
    
    def mark_post_skipped(self, post_id: str, reason: str = None) -> bool:
        """
        Mark a post as skipped.
        
        Args:
            post_id: ID of the post to mark as skipped
            reason: Optional reason for skipping
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Find the post
            post = self._find_post_by_id(post_id)
            if not post:
                self.logger.error(f"Post not found: {post_id}")
                return False
            
            # Mark as skipped
            post.status = PostStatus.SKIPPED
            
            # Log to posting history
            history_entry = {
                'post_id': post_id,
                'content_preview': post.content[:100] + '...' if len(post.content) > 100 else post.content,
                'status': 'skipped',
                'reason': reason,
                'skipped_at': datetime.now().isoformat()
            }
            
            self.file_manager.write_posting_history(history_entry)
            
            # Save updated posts to file
            success = self.file_manager.save_posts(self.posts)
            
            if success:
                self.logger.info(f"Marked post as skipped: {post_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to mark post as skipped: {e}")
            return False
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get current queue statistics.
        
        Returns:
            Dictionary with queue status information
        """
        try:
            status = {
                'total_posts': len(self.posts),
                'pending_posts': 0,
                'completed_posts': 0,
                'failed_posts': 0,
                'skipped_posts': 0,
                'posts_by_group': defaultdict(int),
                'pending_by_group': defaultdict(int)
            }
            
            for post in self.posts:
                # Count by status
                if post.status == PostStatus.PENDING:
                    status['pending_posts'] += 1
                elif post.status == PostStatus.COMPLETED:
                    status['completed_posts'] += 1
                elif post.status == PostStatus.FAILED:
                    status['failed_posts'] += 1
                elif post.status == PostStatus.SKIPPED:
                    status['skipped_posts'] += 1
                
                # Count by community group
                for group in post.community_groups:
                    status['posts_by_group'][group] += 1
                    if post.status == PostStatus.PENDING:
                        status['pending_by_group'][group] += 1
            
            # Convert defaultdicts to regular dicts
            status['posts_by_group'] = dict(status['posts_by_group'])
            status['pending_by_group'] = dict(status['pending_by_group'])
            
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to get queue status: {e}")
            return {}
    
    def get_posts_for_group(self, community_group: str, status: PostStatus = None) -> List[Post]:
        """
        Get all posts for a specific community group.
        
        Args:
            community_group: Name of the community group
            status: Optional status filter
            
        Returns:
            List of posts for the group
        """
        try:
            filtered_posts = [
                post for post in self.posts
                if community_group in post.community_groups
            ]
            
            if status:
                filtered_posts = [
                    post for post in filtered_posts
                    if post.status == status
                ]
            
            return filtered_posts
            
        except Exception as e:
            self.logger.error(f"Failed to get posts for group {community_group}: {e}")
            return []
    
    def is_queue_empty(self, community_group: str = None) -> bool:
        """
        Check if the queue is empty.
        
        Args:
            community_group: Optional community group to check (checks all if None)
            
        Returns:
            True if queue is empty, False otherwise
        """
        try:
            if community_group:
                # Check specific group
                pending_posts = self.get_posts_for_group(community_group, PostStatus.PENDING)
                return len(pending_posts) == 0
            else:
                # Check all groups
                pending_posts = [post for post in self.posts if post.status == PostStatus.PENDING]
                return len(pending_posts) == 0
                
        except Exception as e:
            self.logger.error(f"Failed to check if queue is empty: {e}")
            return True
    
    def get_posting_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent posting history.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of posting history entries
        """
        try:
            return self.file_manager.get_posting_history(limit)
        except Exception as e:
            self.logger.error(f"Failed to get posting history: {e}")
            return []
    
    def add_post(self, post: Post) -> bool:
        """
        Add a new post to the queue.
        
        Args:
            post: Post to add
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate post
            if not post.id or not post.content.strip():
                self.logger.error("Invalid post: missing ID or content")
                return False
            
            # Check for duplicate ID
            if self._find_post_by_id(post.id):
                self.logger.error(f"Post with ID already exists: {post.id}")
                return False
            
            # Add to queue
            self.posts.append(post)
            
            # Save to file
            success = self.file_manager.save_posts(self.posts)
            
            if success:
                self.logger.info(f"Added new post to queue: {post.id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to add post: {e}")
            return False
    
    def remove_post(self, post_id: str) -> bool:
        """
        Remove a post from the queue.
        
        Args:
            post_id: ID of post to remove
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Find and remove post
            original_count = len(self.posts)
            self.posts = [post for post in self.posts if post.id != post_id]
            
            if len(self.posts) == original_count:
                self.logger.warning(f"Post not found for removal: {post_id}")
                return False
            
            # Save to file
            success = self.file_manager.save_posts(self.posts)
            
            if success:
                self.logger.info(f"Removed post from queue: {post_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to remove post: {e}")
            return False
    
    def _find_post_by_id(self, post_id: str) -> Optional[Post]:
        """
        Find post by ID.
        
        Args:
            post_id: ID of post to find
            
        Returns:
            Post object if found, None otherwise
        """
        for post in self.posts:
            if post.id == post_id:
                return post
        return None
    
    def get_next_posts_preview(self, community_group: str, count: int = 5) -> List[Dict[str, Any]]:
        """
        Get preview of next posts for a community group.
        
        Args:
            community_group: Name of the community group
            count: Number of posts to preview
            
        Returns:
            List of post preview dictionaries
        """
        try:
            # Get available posts for this group
            available_posts = [
                post for post in self.posts
                if (post.status == PostStatus.PENDING and
                    community_group in post.community_groups and
                    post.is_ready_to_post())
            ]
            
            # Sort by creation date (FIFO)
            available_posts.sort(key=lambda p: p.created_at)
            
            # Create previews
            previews = []
            for post in available_posts[:count]:
                preview = {
                    'id': post.id,
                    'content_preview': post.content[:100] + '...' if len(post.content) > 100 else post.content,
                    'images_count': len(post.images),
                    'created_at': post.created_at.isoformat(),
                    'community_groups': post.community_groups
                }
                previews.append(preview)
            
            return previews
            
        except Exception as e:
            self.logger.error(f"Failed to get posts preview: {e}")
            return []
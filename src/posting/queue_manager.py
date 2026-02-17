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
    
    def get_next_post(self, community_group: str, account_username: str = None) -> Optional[Post]:
        """
        Get next post for a specific community group and optionally an account.
        ONLY uses content pairing - no fallback to dynamic or static posts.
        
        Args:
            community_group: Name of the community group
            account_username: Optional account username for content pairing filtering
            
        Returns:
            Next available post for the group, None if no posts available
        """
        try:
            # ONLY try to get post from content pairing
            if account_username:
                paired_post = self._generate_post_from_pairing(community_group, account_username)
                if paired_post:
                    return paired_post
                else:
                    self.logger.warning(f"No content pairing found for @{account_username} in {community_group}")
                    return None
            
            # If no account specified, cannot use pairing
            self.logger.warning(f"No account specified - content pairing requires account context")
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get next post for {community_group}: {e}")
            return None
    
    def _generate_post_from_pairing(self, community_group: str, account_username: str) -> Optional[Post]:
        """Generate a post from content pairing configuration."""
        try:
            # Load content pairing
            pairing_file = Path("data/content_pairing.json")
            if not pairing_file.exists():
                self.logger.debug("No content_pairing.json found")
                return None
            
            pairings = json.loads(pairing_file.read_text(encoding='utf-8'))
            if not pairings:
                self.logger.debug("No content pairings configured")
                return None
            
            # Load communities to get all URLs for this group
            communities_file = Path("data/communities.json")
            all_community_urls = []
            if communities_file.exists():
                communities_data = json.loads(communities_file.read_text(encoding='utf-8'))
                all_community_urls = [c.get('url') for c in communities_data if c.get('url')]
            
            # Find pairings that match this account
            matching_pairings = []
            for pairing in pairings:
                accounts = pairing.get('accounts', [])
                communities = pairing.get('communities', [])
                
                # Check if this pairing applies to this account
                account_matches = account_username in accounts
                
                if not account_matches:
                    continue
                
                # Check if this pairing applies to any community
                # Empty communities list means "all communities"
                if len(communities) == 0:
                    # This pairing applies to all communities
                    matching_pairings.append(pairing)
                    self.logger.debug(f"Pairing '{pairing.get('name')}' matches (all communities)")
                else:
                    # This pairing has specific communities
                    # Since we're using community groups, we accept any pairing with communities
                    # The actual community URL will be determined by the posting flow
                    matching_pairings.append(pairing)
                    self.logger.debug(f"Pairing '{pairing.get('name')}' matches (specific communities)")
            
            if not matching_pairings:
                self.logger.debug(f"No matching content pairing for @{account_username}")
                return None
            
            # Pick a random matching pairing
            pairing = random.choice(matching_pairings)
            self.logger.info(f"Using content pairing: {pairing.get('name', 'Unnamed')} for @{account_username}")
            
            # Get caption IDs from pairing
            caption_ids = pairing.get('caption_ids', [])
            if not caption_ids:
                self.logger.warning(f"Content pairing has no captions")
                return None
            
            # Load captions
            captions_file = Path("data/captions.json")
            if not captions_file.exists():
                self.logger.warning("No captions.json found")
                return None
            
            all_captions = json.loads(captions_file.read_text(encoding='utf-8'))
            
            # Filter to only captions in this pairing
            paired_captions = [c for c in all_captions if c.get('id') in caption_ids]
            if not paired_captions:
                self.logger.warning(f"No captions found for pairing")
                return None
            
            # Pick random caption from pairing
            caption_obj = random.choice(paired_captions)
            content = caption_obj['content']
            
            # Get image groups from pairing (overrides caption's image_groups)
            pairing_image_groups = pairing.get('image_groups', [])
            images = []
            
            if pairing_image_groups:
                # Use pairing's image groups
                try:
                    img_file = Path("data/image_groups.json")
                    if img_file.exists():
                        all_groups = json.loads(img_file.read_text(encoding='utf-8'))
                        
                        # Filter to only the groups specified in pairing
                        filtered_groups = [
                            group for group in all_groups
                            if group.get('name') in pairing_image_groups
                        ]
                        
                        if filtered_groups:
                            group = random.choice(filtered_groups)
                            all_images = group['images']
                            selected_image = random.choice(all_images)
                            images = [selected_image]
                            self.logger.debug(f"Selected image from pairing: {selected_image}")
                except Exception as img_error:
                    self.logger.warning(f"Could not load images from pairing: {img_error}")
                    images = []
            
            # Create a Post object
            post_id = f"paired_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
            post = Post(
                id=post_id,
                content=content,
                images=images,
                community_groups=[community_group],
                status=PostStatus.PENDING,
                created_at=datetime.now()
            )
            
            if images:
                self.logger.info(f"✅ Generated paired post with 1 image for @{account_username}")
            else:
                self.logger.info(f"✅ Generated paired text-only post for @{account_username}")
            
            return post
            
        except Exception as e:
            self.logger.error(f"Error generating post from pairing: {e}")
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
            
            # Pick random caption
            caption_obj = random.choice(captions_data)
            content = caption_obj['content']
            
            # Check if caption specifies image groups
            images = []  # Default to empty list (text-only post)
            caption_image_groups = caption_obj.get('image_groups', [])
            
            if caption_image_groups:
                # Use caption-specific image groups
                try:
                    # Load all image groups
                    img_file = Path("data/image_groups.json")
                    if img_file.exists():
                        all_groups = json.loads(img_file.read_text(encoding='utf-8'))
                        
                        # Filter to only the groups specified in caption
                        filtered_groups = [
                            group for group in all_groups
                            if group.get('name') in caption_image_groups
                        ]
                        
                        if filtered_groups:
                            # Pick random group from filtered list
                            group = random.choice(filtered_groups)
                            all_images = group['images']
                            
                            # Select only one random image from the group
                            selected_image = random.choice(all_images)
                            images = [selected_image]
                            self.logger.debug(f"Selected image: {selected_image}")
                except Exception as img_error:
                    self.logger.warning(f"Could not load images, creating text-only post: {img_error}")
                    images = []
            
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
            
            if images:
                self.logger.info(f"Generated dynamic post {post_id} with 1 image")
            else:
                self.logger.info(f"Generated dynamic text-only post {post_id}")
            
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
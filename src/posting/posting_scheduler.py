"""
Posting Scheduler component for managing timing and scheduling.
Implements independent scheduling for community groups with interval management and randomized timing.
"""

import logging
import random
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from collections import defaultdict

from ..models.community_group import CommunityGroup
from ..models.post import Post
from ..utils.file_manager import FileManager


class PostingScheduler:
    """Manages timing and scheduling of posts across different community groups with randomized intervals."""
    
    def __init__(self, file_manager: FileManager, config: Dict[str, Any] = None):
        """
        Initialize posting scheduler.
        
        Args:
            file_manager: File manager instance for data persistence
            config: Configuration dictionary with randomness settings
        """
        self.file_manager = file_manager
        self.community_groups: List[CommunityGroup] = []
        self.logger = logging.getLogger(__name__)
        
        # Randomness configuration
        self.config = config or {}
        self.randomness_percent = self.config.get('randomness_percent', 25)  # Default 25% randomness
        self.auto_refresh_cookies = self.config.get('auto_refresh_cookies', True)
        
        # Load community groups from file
        self.reload_community_groups()
    
    def calculate_randomized_interval(self, base_interval: int) -> int:
        """
        Calculate randomized posting interval to avoid detection patterns.
        
        Args:
            base_interval: Base interval in seconds
            
        Returns:
            Randomized interval in seconds
        """
        try:
            # Calculate variation range
            variation = int(base_interval * (self.randomness_percent / 100))
            
            # Generate random offset within ±variation
            offset = random.randint(-variation, variation)
            
            # Apply offset (no minimum limit as requested)
            randomized_interval = base_interval + offset
            
            # Ensure interval is positive
            randomized_interval = max(1, randomized_interval)
            
            self.logger.debug(f"Randomized interval: {base_interval}s → {randomized_interval}s (±{self.randomness_percent}%)")
            
            return randomized_interval
            
        except Exception as e:
            self.logger.error(f"Failed to calculate randomized interval: {e}")
            return base_interval
    
    def reload_community_groups(self) -> bool:
        """
        Reload community groups from file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.community_groups = self.file_manager.read_communities_file()
            self.logger.info(f"Loaded {len(self.community_groups)} community groups from file")
            return True
        except Exception as e:
            self.logger.error(f"Failed to reload community groups: {e}")
            return False
    
    def schedule_next_post(self, community_group: str, interval_override: int = None) -> bool:
        """
        Schedule the next post for a community group with randomized timing.
        
        Args:
            community_group: Name of the community group
            interval_override: Optional interval override in seconds
            
        Returns:
            True if scheduled successfully, False otherwise
        """
        try:
            # Find the community group
            group = self._find_community_group(community_group)
            if not group:
                self.logger.error(f"Community group not found: {community_group}")
                return False
            
            # Use override interval if provided, otherwise use group's interval
            base_interval = interval_override or group.posting_interval
            
            # Apply randomization to avoid detection patterns
            randomized_interval = self.calculate_randomized_interval(base_interval)
            
            # Update last posted time and calculate next post time with randomized interval
            group.mark_posted()
            
            # Override the next post time with randomized calculation
            group.last_posted = datetime.now()
            next_post_time = group.last_posted + timedelta(seconds=randomized_interval)
            
            # Save updated community groups
            success = self.file_manager.save_communities(self.community_groups)
            
            if success:
                self.logger.info(f"Scheduled next post for {community_group} at {next_post_time} (randomized from {base_interval}s to {randomized_interval}s)")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to schedule next post for {community_group}: {e}")
            return False
    
    def get_next_due_post(self) -> Optional[Dict[str, Any]]:
        """
        Get the next post that should be published across all groups.
        
        Returns:
            Dictionary with community group info and next post time, None if no posts due
        """
        try:
            due_groups = []
            
            for group in self.community_groups:
                if not group.active:
                    continue
                
                if group.is_ready_for_next_post():
                    due_groups.append({
                        'group': group,
                        'name': group.name,
                        'last_posted': group.last_posted,
                        'posting_interval': group.posting_interval,
                        'communities': group.communities
                    })
            
            if not due_groups:
                return None
            
            # Return the group that has been waiting the longest
            # (or has never posted if last_posted is None)
            next_group = min(due_groups, key=lambda g: g['last_posted'] or datetime.min)
            
            self.logger.debug(f"Next due post for group: {next_group['name']}")
            return next_group
            
        except Exception as e:
            self.logger.error(f"Failed to get next due post: {e}")
            return None
    
    def update_schedule(self, community_group: str, interval: int) -> bool:
        """
        Update posting interval for a community group.
        
        Args:
            community_group: Name of the community group
            interval: New posting interval in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate interval
            # if interval < 1800:  # Minimum 30 minutes
            #    self.logger.error(f"Posting interval too short: {interval}s (minimum 1800s)")
            #    return False
            
            # Find and update the community group
            group = self._find_community_group(community_group)
            if not group:
                self.logger.error(f"Community group not found: {community_group}")
                return False
            
            old_interval = group.posting_interval
            group.posting_interval = interval
            
            # Save updated community groups
            success = self.file_manager.save_communities(self.community_groups)
            
            if success:
                self.logger.info(f"Updated posting interval for {community_group}: {old_interval}s -> {interval}s")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to update schedule for {community_group}: {e}")
            return False
    
    def get_schedule_status(self) -> Dict[str, Any]:
        """
        Get current scheduling status for all community groups.
        
        Returns:
            Dictionary with scheduling information
        """
        try:
            status = {
                'total_groups': len(self.community_groups),
                'active_groups': 0,
                'groups_ready': 0,
                'groups': []
            }
            
            for group in self.community_groups:
                group_info = {
                    'name': group.name,
                    'active': group.active,
                    'posting_interval': group.posting_interval,
                    'last_posted': group.last_posted.isoformat() if group.last_posted else None,
                    'next_post_time': group.get_next_post_time().isoformat() if group.get_next_post_time() else None,
                    'ready_for_post': group.is_ready_for_next_post(),
                    'communities_count': len(group.communities),
                    'time_until_next': None
                }
                
                if group.active:
                    status['active_groups'] += 1
                    
                    if group.is_ready_for_next_post():
                        status['groups_ready'] += 1
                    
                    # Calculate time until next post
                    next_time = group.get_next_post_time()
                    if next_time:
                        time_diff = (next_time - datetime.now()).total_seconds()
                        if time_diff > 0:
                            group_info['time_until_next'] = int(time_diff)
                        else:
                            group_info['time_until_next'] = 0
                
                status['groups'].append(group_info)
            
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to get schedule status: {e}")
            return {}
    
    def get_next_scheduled_times(self, hours_ahead: int = 24) -> List[Dict[str, Any]]:
        """
        Get upcoming scheduled post times for all groups.
        
        Args:
            hours_ahead: How many hours ahead to look
            
        Returns:
            List of scheduled times with group information
        """
        try:
            scheduled_times = []
            end_time = datetime.now() + timedelta(hours=hours_ahead)
            
            for group in self.community_groups:
                if not group.active:
                    continue
                
                # Calculate next few post times for this group
                current_time = datetime.now()
                next_post_time = group.get_next_post_time()
                
                if not next_post_time:
                    # If never posted, next post is now
                    next_post_time = current_time
                
                # Generate scheduled times within the time window
                while next_post_time <= end_time:
                    scheduled_times.append({
                        'group_name': group.name,
                        'scheduled_time': next_post_time.isoformat(),
                        'posting_interval': group.posting_interval,
                        'communities_count': len(group.communities)
                    })
                    
                    # Calculate next occurrence
                    next_post_time += timedelta(seconds=group.posting_interval)
            
            # Sort by scheduled time
            scheduled_times.sort(key=lambda x: x['scheduled_time'])
            
            return scheduled_times
            
        except Exception as e:
            self.logger.error(f"Failed to get scheduled times: {e}")
            return []
    
    def activate_group(self, community_group: str) -> bool:
        """
        Activate a community group for posting.
        
        Args:
            community_group: Name of the community group
            
        Returns:
            True if successful, False otherwise
        """
        try:
            group = self._find_community_group(community_group)
            if not group:
                self.logger.error(f"Community group not found: {community_group}")
                return False
            
            group.active = True
            
            # Save updated community groups
            success = self.file_manager.save_communities(self.community_groups)
            
            if success:
                self.logger.info(f"Activated community group: {community_group}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to activate group {community_group}: {e}")
            return False
    
    def deactivate_group(self, community_group: str) -> bool:
        """
        Deactivate a community group from posting.
        
        Args:
            community_group: Name of the community group
            
        Returns:
            True if successful, False otherwise
        """
        try:
            group = self._find_community_group(community_group)
            if not group:
                self.logger.error(f"Community group not found: {community_group}")
                return False
            
            group.active = False
            
            # Save updated community groups
            success = self.file_manager.save_communities(self.community_groups)
            
            if success:
                self.logger.info(f"Deactivated community group: {community_group}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to deactivate group {community_group}: {e}")
            return False
    
    def get_community_urls(self, community_group: str) -> List[str]:
        """
        Get community URLs for a specific group.
        
        Args:
            community_group: Name of the community group
            
        Returns:
            List of community URLs
        """
        try:
            group = self._find_community_group(community_group)
            if not group:
                return []
            
            return group.communities.copy()
            
        except Exception as e:
            self.logger.error(f"Failed to get community URLs for {community_group}: {e}")
            return []
    
    def add_community_group(self, group: CommunityGroup) -> bool:
        """
        Add a new community group.
        
        Args:
            group: CommunityGroup to add
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check for duplicate name
            if self._find_community_group(group.name):
                self.logger.error(f"Community group already exists: {group.name}")
                return False
            
            # Add to list
            self.community_groups.append(group)
            
            # Save to file
            success = self.file_manager.save_communities(self.community_groups)
            
            if success:
                self.logger.info(f"Added new community group: {group.name}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to add community group: {e}")
            return False
    
    def remove_community_group(self, community_group: str) -> bool:
        """
        Remove a community group.
        
        Args:
            community_group: Name of the community group to remove
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Find and remove group
            original_count = len(self.community_groups)
            self.community_groups = [
                group for group in self.community_groups 
                if group.name != community_group
            ]
            
            if len(self.community_groups) == original_count:
                self.logger.warning(f"Community group not found for removal: {community_group}")
                return False
            
            # Save to file
            success = self.file_manager.save_communities(self.community_groups)
            
            if success:
                self.logger.info(f"Removed community group: {community_group}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to remove community group: {e}")
            return False
    
    def _find_community_group(self, name: str) -> Optional[CommunityGroup]:
        """
        Find community group by name.
        
        Args:
            name: Name of the community group
            
        Returns:
            CommunityGroup object if found, None otherwise
        """
        for group in self.community_groups:
            if group.name == name:
                return group
        return None
    
    def get_time_until_next_post(self, community_group: str) -> Optional[int]:
        """
        Get seconds until next post for a community group.
        
        Args:
            community_group: Name of the community group
            
        Returns:
            Seconds until next post, None if group not found or ready now
        """
        try:
            group = self._find_community_group(community_group)
            if not group or not group.active:
                return None
            
            if group.is_ready_for_next_post():
                return 0
            
            next_time = group.get_next_post_time()
            if not next_time:
                return 0
            
            time_diff = (next_time - datetime.now()).total_seconds()
            return max(0, int(time_diff))
            
        except Exception as e:
            self.logger.error(f"Failed to get time until next post: {e}")
            return None
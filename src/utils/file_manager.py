"""
File Manager component for the Enhanced Twitter Bot system.
Handles reading posts.txt, communities.txt, config.json with validation and error handling.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

from ..models.post import Post, PostStatus
from ..models.community_group import CommunityGroup
from .file_utils import safe_file_read, safe_file_write, backup_file


class FileManager:
    """Manages file I/O operations and data persistence for the bot system."""
    
    def __init__(self, data_dir: str = "data"):
        """
        Initialize file manager.
        
        Args:
            data_dir: Directory containing data files
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.posts_file = self.data_dir / "posts.txt"
        self.communities_file = self.data_dir / "communities.txt"
        self.communities_json_file = self.data_dir / "communities.json"
        self.captions_json_file = self.data_dir / "captions.json"
        self.image_groups_json_file = self.data_dir / "image_groups.json"
        self.history_file = self.data_dir / "posting_history.json"
        self.config_file = Path("config.json")
        
        self.logger = logging.getLogger(__name__)
    
    def _get_configured_interval(self) -> int:
        """Get posting interval from config.json, fallback to 3600."""
        try:
            if self.config_file.exists():
                config = json.loads(self.config_file.read_text(encoding='utf-8'))
                return int(config.get('posting_intervals', {}).get('default', 3600))
        except:
            pass
        return 3600
    
    def read_posts_file(self) -> List[Post]:
        """
        Read posts from posts.txt file.
        
        Format: Each line is either:
        - Plain text post
        - JSON object with content, images, and community_groups
        
        Returns:
            List of Post objects
            
        Raises:
            ValueError: If file format is invalid
            FileNotFoundError: If posts file doesn't exist
        """
        try:
            if not self.posts_file.exists():
                self.logger.warning(f"Posts file not found: {self.posts_file}")
                return []
            
            content = safe_file_read(str(self.posts_file))
            if content is None:
                raise FileNotFoundError(f"Could not read posts file: {self.posts_file}")
            
            posts = []
            lines = content.strip().split('\n')
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):  # Skip empty lines and comments
                    continue
                
                try:
                    post = self._parse_post_line(line, line_num)
                    if post:
                        posts.append(post)
                except Exception as e:
                    self.logger.error(f"Error parsing post at line {line_num}: {e}")
                    # Continue processing other posts instead of failing completely
            
            self.logger.info(f"Loaded {len(posts)} posts from {self.posts_file}")
            return posts
            
        except Exception as e:
            self.logger.error(f"Failed to read posts file: {e}")
            raise
    
    def _parse_post_line(self, line: str, line_num: int) -> Optional[Post]:
        """
        Parse a single line from posts.txt.
        
        Args:
            line: Line content to parse
            line_num: Line number for error reporting
            
        Returns:
            Post object or None if line should be skipped
        """
        try:
            # Try to parse as JSON first
            if line.startswith('{'):
                data = json.loads(line)
                return Post(
                    id=data.get('id', f"post_{line_num}_{uuid.uuid4().hex[:8]}"),
                    content=data['content'],
                    images=data.get('images', []),
                    community_groups=data.get('community_groups', ['default']),
                    status=PostStatus(data.get('status', 'pending')),
                    created_at=datetime.fromisoformat(data['created_at']) if 'created_at' in data else datetime.now(),
                    scheduled_for=datetime.fromisoformat(data['scheduled_for']) if data.get('scheduled_for') else None,
                    posted_at=datetime.fromisoformat(data['posted_at']) if data.get('posted_at') else None
                )
            else:
                # Treat as plain text post
                return Post(
                    id=f"post_{line_num}_{uuid.uuid4().hex[:8]}",
                    content=line,
                    images=[],
                    community_groups=['default'],
                    status=PostStatus.PENDING,
                    created_at=datetime.now()
                )
                
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")
        except KeyError as e:
            raise ValueError(f"Missing required field: {e}")
        except Exception as e:
            raise ValueError(f"Parse error: {e}")
    
    def read_communities_file(self) -> List[CommunityGroup]:
        """
        Read community groups from communities.json file (GUI format) or fallback to communities.txt.
        
        Returns:
            List of CommunityGroup objects
            
        Raises:
            ValueError: If file format is invalid
            FileNotFoundError: If communities file doesn't exist
        """
        try:
            # First try to read from communities.json (GUI format)
            if self.communities_json_file.exists():
                return self._read_communities_from_json()
            
            # Fallback to communities.txt (legacy format)
            if self.communities_file.exists():
                return self._read_communities_from_txt()
            
            # No communities file found, return empty default group
            self.logger.warning("No communities file found, creating empty default group")
            return [CommunityGroup(
                name="default",
                communities=[],
                posting_interval=self._get_configured_interval()
            )]
            
        except Exception as e:
            self.logger.error(f"Failed to read communities file: {e}")
            raise
    
    def _read_communities_from_json(self) -> List[CommunityGroup]:
        """Read communities from communities.json file (GUI format)."""
        try:
            content = safe_file_read(str(self.communities_json_file))
            if content is None:
                raise FileNotFoundError(f"Could not read communities JSON file: {self.communities_json_file}")
            
            communities_data = json.loads(content)
            
            # Convert GUI format to CommunityGroup objects
            # GUI format: [{"id": 1, "name": "community1", "url": "...", "active": true, "created_at": "..."}]
            active_communities = [c for c in communities_data if c.get('active', True)]
            
            if not active_communities:
                self.logger.warning("No active communities found in communities.json")
                return [CommunityGroup(
                    name="default",
                    communities=[],
                    posting_interval=self._get_configured_interval()
                )]
            
            # Create a single community group with all active communities
            community_urls = [c['url'] for c in active_communities]
            
            community_group = CommunityGroup(
                name="default",
                communities=community_urls,
                posting_interval=self._get_configured_interval()
            )
            
            self.logger.info(f"Loaded {len(community_urls)} communities from communities.json")
            return [community_group]
            
        except Exception as e:
            self.logger.error(f"Failed to read communities from JSON: {e}")
            raise
    
    def _read_communities_from_txt(self) -> List[CommunityGroup]:
        """Read communities from communities.txt file (legacy format)."""
        try:
            content = safe_file_read(str(self.communities_file))
            if content is None:
                raise FileNotFoundError(f"Could not read communities file: {self.communities_file}")
            
            community_groups = []
            default_communities = []
            lines = content.strip().split('\n')
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):  # Skip empty lines and comments
                    continue
                
                try:
                    group = self._parse_community_line(line, line_num)
                    if group:
                        if group.name == "default":
                            default_communities.extend(group.communities)
                        else:
                            community_groups.append(group)
                except Exception as e:
                    self.logger.error(f"Error parsing community at line {line_num}: {e}")
                    # Continue processing other communities
            
            # Add default group if we have default communities
            if default_communities:
                community_groups.insert(0, CommunityGroup(
                    name="default",
                    communities=default_communities,
                    posting_interval=self._get_configured_interval()
                ))
            
            # Ensure we have at least one community group
            if not community_groups:
                community_groups.append(CommunityGroup(
                    name="default",
                    communities=[],
                    posting_interval=self._get_configured_interval()
                ))
            
            self.logger.info(f"Loaded {len(community_groups)} community groups from {self.communities_file}")
            return community_groups
            
        except Exception as e:
            self.logger.error(f"Failed to read communities from TXT: {e}")
            raise
    
    def _parse_community_line(self, line: str, line_num: int) -> Optional[CommunityGroup]:
        """
        Parse a single line from communities.txt.
        
        Args:
            line: Line content to parse
            line_num: Line number for error reporting
            
        Returns:
            CommunityGroup object or None if line should be skipped
        """
        try:
            # Try to parse as JSON first
            if line.startswith('{'):
                data = json.loads(line)
                return CommunityGroup(
                    name=data['name'],
                    communities=data['communities'],
                    posting_interval=data.get('posting_interval', self._get_configured_interval()),
                    last_posted=datetime.fromisoformat(data['last_posted']) if data.get('last_posted') else None,
                    active=data.get('active', True)
                )
            else:
                # Treat as plain community URL for default group
                if line.startswith('https://'):
                    return CommunityGroup(
                        name="default",
                        communities=[line],
                        posting_interval=self._get_configured_interval()
                    )
                else:
                    raise ValueError(f"Invalid community URL format: {line}")
                
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")
        except KeyError as e:
            raise ValueError(f"Missing required field: {e}")
        except Exception as e:
            raise ValueError(f"Parse error: {e}")
    
    def write_posting_history(self, entry: Dict[str, Any]) -> bool:
        """
        Write posting history entry to history file.
        
        Args:
            entry: History entry to write
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Load existing history
            history = []
            if self.history_file.exists():
                content = safe_file_read(str(self.history_file))
                if content:
                    history = json.loads(content)
            
            # Add new entry with timestamp
            entry['timestamp'] = datetime.now().isoformat()
            history.append(entry)
            
            # Keep only last 1000 entries to prevent file from growing too large
            if len(history) > 1000:
                history = history[-1000:]
            
            # Write back to file
            content = json.dumps(history, indent=2, ensure_ascii=False)
            success = safe_file_write(str(self.history_file), content)
            
            if success:
                self.logger.debug(f"Wrote posting history entry: {entry.get('post_id', 'unknown')}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to write posting history: {e}")
            return False
    
    def backup_data_files(self) -> Dict[str, Optional[str]]:
        """
        Create backup copies of all data files.
        
        Returns:
            Dictionary mapping file names to backup paths (None if backup failed)
        """
        backups = {}
        
        files_to_backup = [
            self.posts_file,
            self.communities_file,
            self.history_file
        ]
        
        for file_path in files_to_backup:
            if file_path.exists():
                backup_path = backup_file(str(file_path))
                backups[file_path.name] = backup_path
            else:
                backups[file_path.name] = None
        
        self.logger.info(f"Created backups for {len([b for b in backups.values() if b])} files")
        return backups
    
    def save_posts(self, posts: List[Post]) -> bool:
        """
        Save posts back to posts.txt file.
        
        Args:
            posts: List of posts to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            lines = []
            for post in posts:
                # Save as JSON for full data preservation
                lines.append(json.dumps(post.to_dict(), ensure_ascii=False))
            
            content = '\n'.join(lines)
            success = safe_file_write(str(self.posts_file), content)
            
            if success:
                self.logger.info(f"Saved {len(posts)} posts to {self.posts_file}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to save posts: {e}")
            return False
    
    def save_communities(self, community_groups: List[CommunityGroup]) -> bool:
        """
        Save community groups back to communities.txt file.
        
        Args:
            community_groups: List of community groups to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            lines = []
            for group in community_groups:
                # Save as JSON for full data preservation
                lines.append(json.dumps(group.to_dict(), ensure_ascii=False))
            
            content = '\n'.join(lines)
            success = safe_file_write(str(self.communities_file), content)
            
            if success:
                self.logger.info(f"Saved {len(community_groups)} community groups to {self.communities_file}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to save communities: {e}")
            return False
    
    def get_posting_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent posting history entries.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of history entries (most recent first)
        """
        try:
            if not self.history_file.exists():
                return []
            
            content = safe_file_read(str(self.history_file))
            if not content:
                return []
            
            history = json.loads(content)
            
            # Return most recent entries first
            return history[-limit:][::-1]
            
        except Exception as e:
            self.logger.error(f"Failed to read posting history: {e}")
            return []
    
    def validate_data_files(self) -> Dict[str, bool]:
        """
        Validate all data files for corruption or format issues.
        
        Returns:
            Dictionary mapping file names to validation status
        """
        validation_results = {}
        
        # Validate posts file
        try:
            self.read_posts_file()
            validation_results['posts.txt'] = True
        except Exception as e:
            self.logger.error(f"Posts file validation failed: {e}")
            validation_results['posts.txt'] = False
        
        # Validate communities file
        try:
            self.read_communities_file()
            validation_results['communities.txt'] = True
        except Exception as e:
            self.logger.error(f"Communities file validation failed: {e}")
            validation_results['communities.txt'] = False
        
        # Validate history file
        try:
            self.get_posting_history()
            validation_results['posting_history.json'] = True
        except Exception as e:
            self.logger.error(f"History file validation failed: {e}")
            validation_results['posting_history.json'] = False
        
        return validation_results
"""
File utility functions for the Enhanced Twitter Bot system.
"""

import os
import shutil
from pathlib import Path
from typing import Optional
import logging


def ensure_directory(path: str) -> Path:
    """
    Ensure directory exists, create if necessary.
    
    Args:
        path: Directory path to ensure
        
    Returns:
        Path object for the directory
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def backup_file(file_path: str, backup_suffix: str = ".backup") -> Optional[str]:
    """
    Create a backup copy of a file.
    
    Args:
        file_path: Path to file to backup
        backup_suffix: Suffix to add to backup file
        
    Returns:
        Path to backup file if successful, None otherwise
    """
    try:
        source_path = Path(file_path)
        if not source_path.exists():
            return None
        
        backup_path = source_path.with_suffix(source_path.suffix + backup_suffix)
        shutil.copy2(source_path, backup_path)
        
        logging.getLogger(__name__).info(f"Created backup: {backup_path}")
        return str(backup_path)
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to backup {file_path}: {e}")
        return None


def safe_file_write(file_path: str, content: str, encoding: str = 'utf-8') -> bool:
    """
    Safely write content to file with backup.
    
    Args:
        file_path: Path to file to write
        content: Content to write
        encoding: File encoding
        
    Returns:
        True if successful, False otherwise
    """
    try:
        path = Path(file_path)
        
        # Create backup if file exists
        if path.exists():
            backup_file(str(path))
        
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content
        with open(path, 'w', encoding=encoding) as f:
            f.write(content)
        
        return True
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to write {file_path}: {e}")
        return False


def safe_file_read(file_path: str, encoding: str = 'utf-8') -> Optional[str]:
    """
    Safely read content from file.
    
    Args:
        file_path: Path to file to read
        encoding: File encoding
        
    Returns:
        File content if successful, None otherwise
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return None
        
        with open(path, 'r', encoding=encoding) as f:
            return f.read()
            
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to read {file_path}: {e}")
        return None


def get_file_size(file_path: str) -> int:
    """
    Get file size in bytes.
    
    Args:
        file_path: Path to file
        
    Returns:
        File size in bytes, -1 if file doesn't exist
    """
    try:
        return Path(file_path).stat().st_size
    except (OSError, FileNotFoundError):
        return -1


def is_file_writable(file_path: str) -> bool:
    """
    Check if file is writable.
    
    Args:
        file_path: Path to file
        
    Returns:
        True if writable, False otherwise
    """
    try:
        path = Path(file_path)
        if path.exists():
            return os.access(path, os.W_OK)
        else:
            # Check if parent directory is writable
            return os.access(path.parent, os.W_OK)
    except Exception:
        return False
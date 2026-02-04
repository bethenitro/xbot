"""
Configuration manager for the Enhanced Twitter Bot system.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

from .schema import ConfigSchema, DEFAULT_CONFIG


class ConfigurationManager:
    """Manages configuration loading, validation, and saving."""
    
    def __init__(self, config_path: str = "config.json"):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to the configuration file
        """
        self.config_path = Path(config_path)
        self.config: Optional[ConfigSchema] = None
        self.logger = logging.getLogger(__name__)
    
    def load_config(self) -> ConfigSchema:
        """
        Load configuration from file or create default if not exists.
        
        Returns:
            ConfigSchema instance
            
        Raises:
            ValueError: If configuration is invalid
            FileNotFoundError: If config file cannot be read
        """
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                self.config = ConfigSchema.from_dict(config_data)
                self.logger.info(f"Configuration loaded from {self.config_path}")
            else:
                self.config = DEFAULT_CONFIG
                self.save_config(self.config)
                self.logger.info(f"Default configuration created at {self.config_path}")
            
            # Validate configuration
            self.config.validate()
            return self.config
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            raise
    
    def save_config(self, config: ConfigSchema) -> None:
        """
        Save configuration to file.
        
        Args:
            config: Configuration to save
            
        Raises:
            ValueError: If configuration is invalid
            IOError: If file cannot be written
        """
        try:
            # Validate before saving
            config.validate()
            
            # Create directory if it doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save configuration
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
            
            self.config = config
            self.logger.info(f"Configuration saved to {self.config_path}")
            
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            raise
    
    def get_config(self) -> ConfigSchema:
        """
        Get current configuration, loading if necessary.
        
        Returns:
            ConfigSchema instance
        """
        if self.config is None:
            return self.load_config()
        return self.config
    
    def update_config(self, updates: Dict[str, Any]) -> None:
        """
        Update configuration with new values.
        
        Args:
            updates: Dictionary of configuration updates
            
        Raises:
            ValueError: If updates are invalid
        """
        if self.config is None:
            self.load_config()
        
        # Convert current config to dict
        config_dict = self.config.to_dict()
        
        # Apply updates recursively
        self._deep_update(config_dict, updates)
        
        # Create new config from updated dict
        new_config = ConfigSchema.from_dict(config_dict)
        
        # Save the updated configuration
        self.save_config(new_config)
    
    def apply_runtime_config(self, updates: Dict[str, Any]) -> None:
        """
        Apply configuration changes without restart (runtime updates).
        
        Args:
            updates: Dictionary of configuration updates to apply at runtime
        """
        if self.config is None:
            self.load_config()
        
        # Convert current config to dict
        config_dict = self.config.to_dict()
        
        # Apply updates recursively
        self._deep_update(config_dict, updates)
        
        # Create new config from updated dict and validate
        new_config = ConfigSchema.from_dict(config_dict)
        new_config.validate()
        
        # Update in-memory configuration without saving to file
        self.config = new_config
        
        self.logger.info("Runtime configuration updated successfully")
    
    def get_config_profiles(self) -> List[str]:
        """
        Get available configuration profiles.
        
        Returns:
            List of available profile names
        """
        try:
            profiles_dir = self.config_path.parent / "profiles"
            if not profiles_dir.exists():
                return []
            
            profile_files = list(profiles_dir.glob("*.json"))
            profile_names = [f.stem for f in profile_files]
            
            return profile_names
            
        except Exception as e:
            self.logger.error(f"Failed to get config profiles: {e}")
            return []
    
    def load_config_profile(self, profile_name: str) -> bool:
        """
        Load configuration from a specific profile.
        
        Args:
            profile_name: Name of the profile to load
            
        Returns:
            True if successful, False otherwise
        """
        try:
            profiles_dir = self.config_path.parent / "profiles"
            profile_path = profiles_dir / f"{profile_name}.json"
            
            if not profile_path.exists():
                self.logger.error(f"Profile not found: {profile_name}")
                return False
            
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
            
            # Create config from profile data
            profile_config = ConfigSchema.from_dict(profile_data)
            profile_config.validate()
            
            # Apply profile configuration
            self.config = profile_config
            
            self.logger.info(f"Loaded configuration profile: {profile_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load config profile {profile_name}: {e}")
            return False
    
    def save_config_profile(self, profile_name: str, config: ConfigSchema = None) -> bool:
        """
        Save current configuration as a profile.
        
        Args:
            profile_name: Name for the profile
            config: Configuration to save (uses current if None)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if config is None:
                config = self.get_config()
            
            # Create profiles directory if it doesn't exist
            profiles_dir = self.config_path.parent / "profiles"
            profiles_dir.mkdir(parents=True, exist_ok=True)
            
            profile_path = profiles_dir / f"{profile_name}.json"
            
            # Save profile
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Saved configuration profile: {profile_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save config profile {profile_name}: {e}")
            return False
    
    def get_default_config(self) -> ConfigSchema:
        """
        Get default configuration.
        
        Returns:
            Default ConfigSchema instance
        """
        return DEFAULT_CONFIG
    
    def reset_to_defaults(self) -> None:
        """Reset configuration to default values."""
        self.save_config(DEFAULT_CONFIG)
        self.logger.info("Configuration reset to defaults")
    
    def validate_config(self, config: Optional[ConfigSchema] = None) -> bool:
        """
        Validate configuration.
        
        Args:
            config: Configuration to validate (uses current if None)
            
        Returns:
            True if valid
            
        Raises:
            ValueError: If configuration is invalid
        """
        if config is None:
            config = self.get_config()
        
        return config.validate()
    
    def _deep_update(self, base_dict: Dict[str, Any], updates: Dict[str, Any]) -> None:
        """
        Recursively update nested dictionary.
        
        Args:
            base_dict: Base dictionary to update
            updates: Updates to apply
        """
        for key, value in updates.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                self._deep_update(base_dict[key], value)
            else:
                base_dict[key] = value
    
    def get_config_summary(self) -> str:
        """
        Get a human-readable summary of current configuration.
        
        Returns:
            Configuration summary string
        """
        config = self.get_config()
        
        summary = [
            "Enhanced Twitter Bot Configuration Summary:",
            f"  Posting Interval: {config.posting_intervals.default}s ({config.posting_intervals.default // 60} minutes)",
            f"  Stealth Features: {'Enabled' if config.stealth_settings.random_visits else 'Disabled'}",
            f"  Human Behavior: {'Enabled' if config.stealth_settings.humanize_cursor else 'Disabled'}",
            f"  Browser Mode: {'Headless' if config.browser_settings.headless else 'Visible'}",
            f"  Max Retries: {config.error_handling.max_retries}",
            f"  Log Level: {config.error_handling.log_level}"
        ]
        
        return "\n".join(summary)
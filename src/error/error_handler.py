"""
Comprehensive error handling and recovery for the Enhanced Twitter Bot system.
Implements retry logic, rate limit handling, and recovery mechanisms.
"""

import logging
import time
import random
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass


class ErrorType(Enum):
    """Types of errors that can occur."""
    NETWORK_ERROR = "network_error"
    BROWSER_CRASH = "browser_crash"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION_ERROR = "authentication_error"
    POSTING_ERROR = "posting_error"
    FILE_ERROR = "file_error"
    CONFIGURATION_ERROR = "configuration_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ErrorContext:
    """Context information for an error."""
    error_type: ErrorType
    message: str
    timestamp: datetime
    component: str
    operation: str
    retry_count: int = 0
    details: Dict[str, Any] = None


class ErrorHandler:
    """Comprehensive error handling and recovery system."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize error handler.
        
        Args:
            config: Error handling configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay_base = config.get('retry_delay_base', 1)
        self.rate_limit_pause = config.get('rate_limit_pause', 900)  # 15 minutes
        self.skip_failed_posts = config.get('skip_failed_posts', True)
        
        # Error tracking
        self.error_history: List[ErrorContext] = []
        self.rate_limit_until: Optional[datetime] = None
        self.consecutive_failures = 0
        
        # Recovery callbacks
        self.recovery_callbacks: Dict[ErrorType, Callable] = {}
    
    def handle_error(self, error: Exception, context: Dict[str, Any]) -> bool:
        """
        Handle an error with appropriate recovery strategy.
        
        Args:
            error: Exception that occurred
            context: Context information about the error
            
        Returns:
            True if error was handled and operation can continue, False otherwise
        """
        try:
            # Classify the error
            error_type = self._classify_error(error, context)
            
            # Create error context
            error_context = ErrorContext(
                error_type=error_type,
                message=str(error),
                timestamp=datetime.now(),
                component=context.get('component', 'unknown'),
                operation=context.get('operation', 'unknown'),
                retry_count=context.get('retry_count', 0),
                details=context
            )
            
            # Log the error
            self._log_error(error_context)
            
            # Add to error history
            self.error_history.append(error_context)
            self._cleanup_error_history()
            
            # Apply recovery strategy
            return self._apply_recovery_strategy(error_context)
            
        except Exception as e:
            self.logger.error(f"Error in error handler: {e}")
            return False
    
    def retry_with_backoff(self, operation: Callable, max_retries: int = None, 
                          context: Dict[str, Any] = None) -> Any:
        """
        Retry operation with exponential backoff.
        
        Args:
            operation: Function to retry
            max_retries: Maximum retry attempts (uses config default if None)
            context: Context information for error handling
            
        Returns:
            Result of successful operation
            
        Raises:
            Exception: If all retries fail
        """
        max_retries = max_retries or self.max_retries
        context = context or {}
        
        for attempt in range(max_retries + 1):
            try:
                return operation()
                
            except Exception as e:
                if attempt == max_retries:
                    # Final attempt failed
                    context['retry_count'] = attempt
                    self.handle_error(e, context)
                    raise
                
                # Calculate backoff delay
                delay = self._calculate_backoff_delay(attempt)
                
                self.logger.warning(f"Operation failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
                self.logger.info(f"Retrying in {delay:.1f} seconds...")
                
                time.sleep(delay)
    
    def check_rate_limits(self) -> bool:
        """
        Check if we're currently rate limited.
        
        Returns:
            True if rate limited, False otherwise
        """
        if self.rate_limit_until and datetime.now() < self.rate_limit_until:
            return True
        
        # Clear rate limit if time has passed
        if self.rate_limit_until and datetime.now() >= self.rate_limit_until:
            self.rate_limit_until = None
            self.logger.info("Rate limit period has ended")
        
        return False
    
    def handle_rate_limit(self, retry_after: int = None) -> None:
        """
        Handle rate limiting by pausing operations.
        
        Args:
            retry_after: Seconds to wait (uses config default if None)
        """
        pause_duration = retry_after or self.rate_limit_pause
        self.rate_limit_until = datetime.now() + timedelta(seconds=pause_duration)
        
        self.logger.warning(f"Rate limit detected, pausing operations for {pause_duration} seconds")
        self.logger.info(f"Operations will resume at {self.rate_limit_until}")
    
    def register_recovery_callback(self, error_type: ErrorType, callback: Callable) -> None:
        """
        Register a recovery callback for specific error types.
        
        Args:
            error_type: Type of error to handle
            callback: Recovery function to call
        """
        self.recovery_callbacks[error_type] = callback
        self.logger.debug(f"Registered recovery callback for {error_type}")
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get error statistics and trends.
        
        Returns:
            Dictionary with error statistics
        """
        try:
            # Recent errors (last 24 hours)
            recent_cutoff = datetime.now() - timedelta(hours=24)
            recent_errors = [e for e in self.error_history if e.timestamp > recent_cutoff]
            
            # Count by error type
            error_counts = {}
            for error in recent_errors:
                error_type = error.error_type.value
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
            
            # Calculate error rate (errors per hour)
            hours_elapsed = 24
            if recent_errors:
                oldest_error = min(recent_errors, key=lambda e: e.timestamp)
                hours_elapsed = (datetime.now() - oldest_error.timestamp).total_seconds() / 3600
            
            error_rate = len(recent_errors) / max(1, hours_elapsed)
            
            statistics = {
                'total_errors_24h': len(recent_errors),
                'error_rate_per_hour': round(error_rate, 2),
                'consecutive_failures': self.consecutive_failures,
                'rate_limited': self.check_rate_limits(),
                'rate_limit_until': self.rate_limit_until.isoformat() if self.rate_limit_until else None,
                'error_counts_by_type': error_counts,
                'most_common_error': max(error_counts.items(), key=lambda x: x[1])[0] if error_counts else None
            }
            
            return statistics
            
        except Exception as e:
            self.logger.error(f"Failed to get error statistics: {e}")
            return {}
    
    def reset_failure_count(self) -> None:
        """Reset consecutive failure counter."""
        if self.consecutive_failures > 0:
            self.logger.info(f"Resetting consecutive failure count: {self.consecutive_failures}")
            self.consecutive_failures = 0
    
    def _classify_error(self, error: Exception, context: Dict[str, Any]) -> ErrorType:
        """
        Classify error type based on exception and context.
        
        Args:
            error: Exception that occurred
            context: Context information
            
        Returns:
            Classified error type
        """
        error_message = str(error).lower()
        
        # Network-related errors
        if any(keyword in error_message for keyword in ['connection', 'timeout', 'network', 'dns']):
            return ErrorType.NETWORK_ERROR
        
        # Rate limiting
        if any(keyword in error_message for keyword in ['rate limit', 'too many requests', '429']):
            return ErrorType.RATE_LIMIT
        
        # Authentication errors
        if any(keyword in error_message for keyword in ['auth', 'login', 'unauthorized', '401', '403']):
            return ErrorType.AUTHENTICATION_ERROR
        
        # Browser crashes
        if any(keyword in error_message for keyword in ['browser', 'webdriver', 'session', 'crash']):
            return ErrorType.BROWSER_CRASH
        
        # File errors
        if any(keyword in error_message for keyword in ['file', 'permission', 'disk', 'io']):
            return ErrorType.FILE_ERROR
        
        # Configuration errors
        if any(keyword in error_message for keyword in ['config', 'validation', 'schema']):
            return ErrorType.CONFIGURATION_ERROR
        
        # Posting-specific errors
        if context.get('operation') == 'posting':
            return ErrorType.POSTING_ERROR
        
        return ErrorType.UNKNOWN_ERROR
    
    def _apply_recovery_strategy(self, error_context: ErrorContext) -> bool:
        """
        Apply appropriate recovery strategy based on error type.
        
        Args:
            error_context: Error context information
            
        Returns:
            True if recovery was successful, False otherwise
        """
        try:
            error_type = error_context.error_type
            
            # Check for custom recovery callback
            if error_type in self.recovery_callbacks:
                try:
                    return self.recovery_callbacks[error_type](error_context)
                except Exception as e:
                    self.logger.error(f"Recovery callback failed for {error_type}: {e}")
            
            # Default recovery strategies
            if error_type == ErrorType.NETWORK_ERROR:
                return self._handle_network_error(error_context)
            
            elif error_type == ErrorType.RATE_LIMIT:
                return self._handle_rate_limit_error(error_context)
            
            elif error_type == ErrorType.BROWSER_CRASH:
                return self._handle_browser_crash(error_context)
            
            elif error_type == ErrorType.AUTHENTICATION_ERROR:
                return self._handle_authentication_error(error_context)
            
            elif error_type == ErrorType.POSTING_ERROR:
                return self._handle_posting_error(error_context)
            
            elif error_type == ErrorType.FILE_ERROR:
                return self._handle_file_error(error_context)
            
            else:
                return self._handle_generic_error(error_context)
                
        except Exception as e:
            self.logger.error(f"Recovery strategy failed: {e}")
            return False
    
    def _handle_network_error(self, error_context: ErrorContext) -> bool:
        """Handle network-related errors."""
        if error_context.retry_count < self.max_retries:
            delay = self._calculate_backoff_delay(error_context.retry_count)
            self.logger.info(f"Network error, retrying in {delay:.1f} seconds")
            time.sleep(delay)
            return True
        
        self.consecutive_failures += 1
        return False
    
    def _handle_rate_limit_error(self, error_context: ErrorContext) -> bool:
        """Handle rate limiting errors."""
        # Extract retry-after from error details if available
        retry_after = error_context.details.get('retry_after', self.rate_limit_pause)
        self.handle_rate_limit(retry_after)
        return False  # Don't retry immediately
    
    def _handle_browser_crash(self, error_context: ErrorContext) -> bool:
        """Handle browser crash errors."""
        self.logger.warning("Browser crash detected, restart required")
        # Browser restart would be handled by the calling component
        return False
    
    def _handle_authentication_error(self, error_context: ErrorContext) -> bool:
        """Handle authentication errors."""
        self.logger.warning("Authentication error, manual intervention required")
        return False  # Requires manual re-authentication
    
    def _handle_posting_error(self, error_context: ErrorContext) -> bool:
        """Handle posting-specific errors."""
        if self.skip_failed_posts and error_context.retry_count >= self.max_retries:
            self.logger.warning("Skipping failed post after maximum retries")
            return True  # Skip and continue
        
        return error_context.retry_count < self.max_retries
    
    def _handle_file_error(self, error_context: ErrorContext) -> bool:
        """Handle file I/O errors."""
        self.logger.error("File error occurred, check permissions and disk space")
        return False
    
    def _handle_generic_error(self, error_context: ErrorContext) -> bool:
        """Handle generic/unknown errors."""
        if error_context.retry_count < self.max_retries:
            delay = self._calculate_backoff_delay(error_context.retry_count)
            time.sleep(delay)
            return True
        
        self.consecutive_failures += 1
        return False
    
    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter.
        
        Args:
            attempt: Attempt number (0-based)
            
        Returns:
            Delay in seconds
        """
        # Exponential backoff: base * (2 ^ attempt)
        base_delay = self.retry_delay_base * (2 ** attempt)
        
        # Add jitter (±25% random variation)
        jitter = random.uniform(-0.25, 0.25) * base_delay
        
        return max(0.1, base_delay + jitter)
    
    def _log_error(self, error_context: ErrorContext) -> None:
        """
        Log error with appropriate level and context.
        
        Args:
            error_context: Error context to log
        """
        log_message = (
            f"Error in {error_context.component}.{error_context.operation}: "
            f"{error_context.message} (Type: {error_context.error_type.value}, "
            f"Retry: {error_context.retry_count})"
        )
        
        # Log with appropriate level based on error type
        if error_context.error_type in [ErrorType.RATE_LIMIT, ErrorType.NETWORK_ERROR]:
            self.logger.warning(log_message)
        elif error_context.error_type in [ErrorType.BROWSER_CRASH, ErrorType.AUTHENTICATION_ERROR]:
            self.logger.error(log_message)
        else:
            self.logger.error(log_message)
        
        # Log additional context if available
        if error_context.details:
            self.logger.debug(f"Error details: {error_context.details}")
    
    def _cleanup_error_history(self) -> None:
        """Clean up old error history entries."""
        # Keep only last 1000 errors
        if len(self.error_history) > 1000:
            self.error_history = self.error_history[-1000:]
        
        # Remove errors older than 7 days
        cutoff_time = datetime.now() - timedelta(days=7)
        self.error_history = [
            error for error in self.error_history 
            if error.timestamp > cutoff_time
        ]
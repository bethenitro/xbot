"""
Stealth Engine component for coordinating anti-bot detection evasion.
Coordinates random page visits, detection risk assessment, and fingerprint rotation.
"""

import logging
import random
import time
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from ..browser.zendriver_driver import ZenDriverDriver
from ..behavior.human_behavior_simulator import HumanBehaviorSimulator


class StealthEngine:
    """Coordinates all anti-bot detection evasion techniques."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize stealth engine.
        
        Args:
            config: Stealth configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Stealth configuration
        self.random_visits_enabled = config.get('random_visits', True)
        self.random_visits_min = config.get('random_visits_count_min', 2)
        self.random_visits_max = config.get('random_visits_count_max', 3)
        self.fingerprint_rotation = config.get('fingerprint_rotation', True)
        
        # Detection risk tracking
        self.risk_factors = {
            'rapid_actions': 0,
            'pattern_detection': 0,
            'session_age': 0,
            'failed_attempts': 0
        }
        
        # Activity tracking for risk assessment
        self.activity_log = []
        self.session_start_time = datetime.now()
        self.last_action_time = None
        
        # Random pages for stealth visits
        self.stealth_pages = [
            'https://twitter.com/explore',
            'https://twitter.com/explore/tabs/trending',
            'https://twitter.com/notifications',
            'https://twitter.com/i/bookmarks',
            'https://twitter.com/settings/account',
            'https://twitter.com/i/trends',
            'https://twitter.com/home',
            'https://twitter.com/messages'
        ]
    
    async def initialize_stealth_session(self, browser: ZenDriverDriver, behavior: HumanBehaviorSimulator) -> bool:
        """
        Set up a new stealth session with ZenDriver.
        
        Args:
            browser: ZenDriver browser driver
            behavior: Human behavior simulator
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info("Initializing stealth session...")
            
            # Reset risk factors for new session
            self.risk_factors = {
                'rapid_actions': 0,
                'pattern_detection': 0,
                'session_age': 0,
                'failed_attempts': 0
            }
            
            self.activity_log.clear()
            self.session_start_time = datetime.now()
            
            # Perform initial stealth setup
            if self.random_visits_enabled:
                success = await self.perform_random_actions(browser, behavior)
                if not success:
                    self.logger.warning("Random actions failed during stealth initialization")
            
            # Add initial session delay
            delay = behavior.get_random_delay_range(2.0, 5.0)
            await asyncio.sleep(delay)
            
            self.logger.info("Stealth session initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize stealth session: {e}")
            return False
    
    async def perform_random_actions(self, browser: ZenDriverDriver, behavior: HumanBehaviorSimulator) -> bool:
        """
        Execute random human-like actions (2-3 page visits before posting).
        
        Args:
            browser: Browser driver instance
            behavior: Human behavior simulator
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.random_visits_enabled:
                return True
            
            # Determine number of random visits
            visit_count = random.randint(self.random_visits_min, self.random_visits_max)
            
            self.logger.info(f"Performing {visit_count} random page visits for stealth")
            
            # Select random pages to visit
            selected_pages = random.sample(self.stealth_pages, min(visit_count, len(self.stealth_pages)))
            
            for page_url in selected_pages:
                try:
                    self.logger.debug(f"Visiting random page: {page_url}")
                    
                    # Navigate to random page
                    success = await browser.navigate_to_url(page_url)
                    if not success:
                        continue
                    
                    # Add human-like reading behavior
                    reading_time = random.uniform(3.0, 8.0)
                    await asyncio.sleep(reading_time)
                    
                    # Simulate some scrolling
                    try:
                        await browser.execute_script("window.scrollBy(0, Math.random() * 500);")
                        await asyncio.sleep(random.uniform(1.0, 2.0))
                    except:
                        pass  # Scrolling is optional
                    
                    # Log the action
                    self.log_action('random_visit', True, {'url': page_url})
                    
                except Exception as e:
                    self.logger.debug(f"Failed to visit random page {page_url}: {e}")
                    continue
            
            self.logger.info("Random page visits completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to perform random actions: {e}")
            return False
    
    def rotate_fingerprint(self, browser: ZenDriverDriver) -> bool:
        """
        Change browser fingerprint for new sessions.
        
        Args:
            browser: Browser driver instance
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.fingerprint_rotation:
                return True
            
            self.logger.info("Rotating browser fingerprint for stealth")
            
            # Generate new fingerprint (this would typically require browser restart)
            new_fingerprint = browser._generate_fingerprint()
            browser.current_fingerprint = new_fingerprint
            
            self.logger.debug(f"New fingerprint generated: {new_fingerprint}")
            
            # Log activity
            self._log_activity('fingerprint_rotation', {'fingerprint': new_fingerprint})
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to rotate fingerprint: {e}")
            return False
    
    def check_detection_risk(self) -> float:
        """
        Assess current detection risk level.
        
        Returns:
            Risk level between 0.0 (low) and 1.0 (high)
        """
        try:
            total_risk = 0.0
            
            # Check rapid actions risk
            rapid_risk = self._assess_rapid_actions_risk()
            total_risk += rapid_risk * 0.3
            
            # Check pattern detection risk
            pattern_risk = self._assess_pattern_risk()
            total_risk += pattern_risk * 0.25
            
            # Check session age risk
            session_risk = self._assess_session_age_risk()
            total_risk += session_risk * 0.2
            
            # Check failed attempts risk
            failure_risk = self._assess_failure_risk()
            total_risk += failure_risk * 0.25
            
            # Normalize to 0-1 range
            total_risk = min(1.0, max(0.0, total_risk))
            
            # Update risk factors
            self.risk_factors['rapid_actions'] = rapid_risk
            self.risk_factors['pattern_detection'] = pattern_risk
            self.risk_factors['session_age'] = session_risk
            self.risk_factors['failed_attempts'] = failure_risk
            
            if total_risk > 0.7:
                self.logger.warning(f"High detection risk detected: {total_risk:.2f}")
            elif total_risk > 0.4:
                self.logger.info(f"Moderate detection risk: {total_risk:.2f}")
            
            return total_risk
            
        except Exception as e:
            self.logger.error(f"Failed to check detection risk: {e}")
            return 0.5  # Return moderate risk on error
    
    async def apply_stealth_delay(self, behavior: HumanBehaviorSimulator, base_delay: float = 1.0) -> None:
        """
        Apply stealth delay based on current risk level.
        
        Args:
            behavior: Human behavior simulator
            base_delay: Base delay in seconds
        """
        try:
            risk_level = self.check_detection_risk()
            
            # Increase delay based on risk level
            risk_multiplier = 1.0 + (risk_level * 2.0)  # 1x to 3x multiplier
            adjusted_delay = base_delay * risk_multiplier
            
            # Add random fluctuation
            final_delay = behavior.get_random_delay_range(
                adjusted_delay * 0.8, 
                adjusted_delay * 1.2
            )
            
            self.logger.debug(f"Applying stealth delay: {final_delay:.2f}s (risk: {risk_level:.2f})")
            await asyncio.sleep(final_delay)
            return final_delay
            
        except Exception as e:
            self.logger.error(f"Failed to apply stealth delay: {e}")
            await asyncio.sleep(base_delay)  # Fallback to base delay
            return base_delay
    
    def log_action(self, action_type: str, success: bool, details: Dict[str, Any] = None) -> None:
        """
        Log an action for risk assessment.
        
        Args:
            action_type: Type of action performed
            success: Whether the action was successful
            details: Optional additional details
        """
        try:
            self._log_activity(action_type, {
                'success': success,
                'details': details or {}
            })
            
            # Update last action time
            self.last_action_time = datetime.now()
            
        except Exception as e:
            self.logger.error(f"Failed to log action: {e}")
    
    def get_stealth_status(self) -> Dict[str, Any]:
        """
        Get current stealth status and risk assessment.
        
        Returns:
            Dictionary with stealth status information
        """
        try:
            risk_level = self.check_detection_risk()
            
            status = {
                'risk_level': risk_level,
                'risk_category': self._get_risk_category(risk_level),
                'risk_factors': self.risk_factors.copy(),
                'session_age_minutes': (datetime.now() - self.session_start_time).total_seconds() / 60,
                'total_actions': len(self.activity_log),
                'random_visits_enabled': self.random_visits_enabled,
                'fingerprint_rotation_enabled': self.fingerprint_rotation,
                'last_action': self.last_action_time.isoformat() if self.last_action_time else None
            }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to get stealth status: {e}")
            return {}
    
    def _log_activity(self, action_type: str, data: Dict[str, Any]) -> None:
        """
        Log activity for risk assessment.
        
        Args:
            action_type: Type of activity
            data: Activity data
        """
        activity = {
            'timestamp': datetime.now(),
            'action_type': action_type,
            'data': data
        }
        
        self.activity_log.append(activity)
        
        # Keep only recent activities (last 100)
        if len(self.activity_log) > 100:
            self.activity_log = self.activity_log[-100:]
    
    def _assess_rapid_actions_risk(self) -> float:
        """Assess risk from rapid consecutive actions."""
        if len(self.activity_log) < 2:
            return 0.0
        
        # Check for actions within short time windows
        rapid_actions = 0
        recent_activities = [a for a in self.activity_log if (datetime.now() - a['timestamp']).total_seconds() < 300]  # Last 5 minutes
        
        for i in range(1, len(recent_activities)):
            time_diff = (recent_activities[i]['timestamp'] - recent_activities[i-1]['timestamp']).total_seconds()
            if time_diff < 2.0:  # Actions less than 2 seconds apart
                rapid_actions += 1
        
        # Normalize risk (more than 5 rapid actions = high risk)
        return min(1.0, rapid_actions / 5.0)
    
    def _assess_pattern_risk(self) -> float:
        """Assess risk from repetitive patterns."""
        if len(self.activity_log) < 5:
            return 0.0
        
        # Check for repetitive action types
        recent_actions = [a['action_type'] for a in self.activity_log[-10:]]
        
        # Count consecutive identical actions
        max_consecutive = 1
        current_consecutive = 1
        
        for i in range(1, len(recent_actions)):
            if recent_actions[i] == recent_actions[i-1]:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 1
        
        # Normalize risk (more than 3 consecutive identical actions = high risk)
        return min(1.0, (max_consecutive - 1) / 3.0)
    
    def _assess_session_age_risk(self) -> float:
        """Assess risk from session age."""
        session_age_minutes = (datetime.now() - self.session_start_time).total_seconds() / 60
        
        # Risk increases after 2 hours
        if session_age_minutes > 120:
            return min(1.0, (session_age_minutes - 120) / 120)  # Linear increase
        
        return 0.0
    
    def _assess_failure_risk(self) -> float:
        """Assess risk from failed attempts."""
        if not self.activity_log:
            return 0.0
        
        # Count recent failures
        recent_activities = [a for a in self.activity_log if (datetime.now() - a['timestamp']).total_seconds() < 600]  # Last 10 minutes
        failures = sum(1 for a in recent_activities if not a['data'].get('success', True))
        
        # Normalize risk (more than 3 failures = high risk)
        return min(1.0, failures / 3.0)
    
    def _get_risk_category(self, risk_level: float) -> str:
        """Get risk category string."""
        if risk_level < 0.3:
            return 'low'
        elif risk_level < 0.7:
            return 'moderate'
        else:
            return 'high'
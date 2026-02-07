"""
ZenDriver component for stealth browser automation.
Provides interface to ZenDriver browser with built-in humanization and stealth capabilities.
"""

import logging
import time
import random
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path

try:
    import zendriver as zd
except ImportError as e:
    logging.getLogger(__name__).error(f"Required dependencies not installed: {e}")
    raise ImportError("Please install zendriver: pip install zendriver")


class ZenDriverDriver:
    """Manages ZenDriver browser automation with built-in stealth capabilities."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize ZenDriver driver.
        
        Args:
            config: Browser configuration dictionary
        """
        self.config = config
        self.browser = None
        self.tab = None
        self.logger = logging.getLogger(__name__)
        self.current_fingerprint = None
        
        # Stealth configuration
        self.timeout = config.get('timeout', 30)
    
    async def launch_browser(self, proxy_config: Dict = None, headless: bool = None, 
                           fingerprint_data: Dict = None, account_username: str = None) -> bool:
        """
        Launch ZenDriver browser instance with consistent fingerprint.
        
        Args:
            proxy_config: Proxy configuration dictionary or URL string
            headless: Override headless mode
            fingerprint_data: Consistent fingerprint data for this account
            account_username: Username for account isolation (creates separate profile)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info("Launching ZenDriver browser with stealth configuration...")
            
            # Create account-specific user data directory for proper isolation
            import os
            if account_username:
                # Each account gets its own isolated profile directory
                user_data_dir = os.path.abspath(f"sessions/zendriver_profiles/{account_username}")
                self.logger.info(f"Using account-specific profile: {account_username}")
            else:
                # Fallback to default directory for non-account operations
                user_data_dir = os.path.abspath("sessions/zendriver_profiles/default")
                self.logger.info("Using default profile directory")
            
            os.makedirs(user_data_dir, exist_ok=True)
            
            # Prepare ZenDriver configuration with latest API
            config = zd.Config(
                headless=headless if headless is not None else self.config.get('headless', False),
                user_data_dir=user_data_dir,
                # Enhanced stealth settings for latest ZenDriver
                disable_webrtc=True,  # Prevent WebRTC IP leaks (v0.15.0+)
                disable_webgl=False,  # Keep WebGL for better fingerprint consistency
                # lang="en-US",  # Set consistent language - REMOVED due to zendriver bug
                user_agent=None  # Let ZenDriver handle user agent automatically
            )
            
            # Add proxy configuration if provided
            if proxy_config:
                proxy_args = self._get_proxy_args(proxy_config)
                if proxy_args:
                    for arg in proxy_args:
                        config.add_argument(arg)
                    self.logger.info(f"Using proxy configuration: {proxy_config}")
            
            # Use consistent fingerprint if provided, otherwise generate new one
            if fingerprint_data:
                self.logger.info("Using consistent fingerprint for account")
                self.current_fingerprint = fingerprint_data
            else:
                # Generate new fingerprint (only for new accounts)
                fingerprint = self._generate_fingerprint()
                self.current_fingerprint = fingerprint
                self.logger.info("Generated new fingerprint for account")
            
            # Launch browser with ZenDriver using latest API
            self.browser = await zd.start(config=config)
            
            # Navigate to Google.com and let user take full control
            self.logger.info("Opening Google.com - user has full control from here")
            self.tab = await self.browser.get("https://www.google.com")
            
            # Apply post-launch stealth enhancements
            await self._apply_stealth_enhancements()
            
            self.logger.info("ZenDriver browser launched successfully - ready for manual use")
            
            # Important: Don't let the function complete too quickly
            # ZenDriver might close if the async context ends immediately
            # Keep a small delay to ensure browser is fully established
            await asyncio.sleep(2)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to launch ZenDriver browser: {e}")
            # Clean up on failure
            await self._cleanup_on_error()
            return False
    
    async def _cleanup_on_error(self):
        """Clean up resources on error."""
        try:
            if self.browser:
                await self.browser.stop()
        except Exception as e:
            self.logger.debug(f"Error during cleanup: {e}")
        finally:
            self.browser = None
            self.tab = None
    
    def get_current_fingerprint(self) -> Dict[str, Any]:
        """Get the current fingerprint data for saving."""
        return getattr(self, 'current_fingerprint', {}).copy()
    
    def _generate_fingerprint(self) -> Dict[str, Any]:
        """
        Generate consistent Chrome-like fingerprint for new accounts.
        This fingerprint should NEVER change for the same account.
        """
        # Generate realistic Chrome fingerprint (minimal for ZenDriver)
        # ZenDriver handles most fingerprint aspects automatically via CDP
        fingerprint = {
            # ZenDriver uses CDP and handles language/locale automatically
            # No manual fingerprint configuration needed
        }
        
        return fingerprint
    
    def _get_proxy_args(self, proxy_config) -> List[str]:
        """
        Convert proxy configuration to Chrome browser arguments.
        For authenticated proxies, creates a Manifest V3 Chrome extension
        to handle proxy authentication silently without dialogs.
        
        Args:
            proxy_config: Proxy configuration dictionary or URL string
            
        Returns:
            List of Chrome arguments for proxy configuration
        """
        try:
            if isinstance(proxy_config, str):
                # Parse proxy URL string
                from urllib.parse import urlparse
                parsed = urlparse(proxy_config)
                
                # Ensure we have a valid scheme
                if not parsed.scheme:
                    proxy_config = f"http://{proxy_config}"
                    parsed = urlparse(proxy_config)
                
                # Build proxy server argument (without credentials in URL for security)
                proxy_server = f"{parsed.hostname}:{parsed.port}"
                args = [f"--proxy-server={proxy_server}"]
                self.logger.info(f"Configuring proxy: {parsed.hostname}:{parsed.port}")
                
                # Handle authentication via Manifest V3 Chrome extension
                if parsed.username and parsed.password:
                    extension_path = self._create_proxy_auth_extension(
                        parsed.username, 
                        parsed.password,
                        parsed.hostname,
                        parsed.port
                    )
                    if extension_path:
                        args.append(f"--load-extension={extension_path}")
                        self.logger.info("✓ Proxy auth extension loaded (Manifest V3 with asyncBlocking)")
                    else:
                        self.logger.warning("⚠ Failed to create proxy auth extension - authentication may fail")
                else:
                    self.logger.info("Proxy configured without authentication")
                
                return args
                
            elif isinstance(proxy_config, dict):
                # Handle dictionary format
                server = proxy_config.get("server", "")
                if server:
                    # Parse the server URL
                    from urllib.parse import urlparse
                    parsed = urlparse(server if "://" in server else f"http://{server}")
                    proxy_server = f"{parsed.hostname}:{parsed.port}"
                    args = [f"--proxy-server={proxy_server}"]
                    self.logger.info(f"Configuring proxy: {parsed.hostname}:{parsed.port}")
                    
                    # Handle authentication if provided
                    if proxy_config.get("username") and proxy_config.get("password"):
                        extension_path = self._create_proxy_auth_extension(
                            proxy_config["username"],
                            proxy_config["password"], 
                            parsed.hostname,
                            parsed.port
                        )
                        if extension_path:
                            args.append(f"--load-extension={extension_path}")
                            self.logger.info("✓ Proxy auth extension loaded (Manifest V3 with asyncBlocking)")
                        else:
                            self.logger.warning("⚠ Failed to create proxy auth extension")
                    else:
                        self.logger.info("Proxy configured without authentication")
                    
                    return args
            
            self.logger.warning("No valid proxy configuration provided")
            return []
            
        except Exception as e:
            self.logger.error(f"Failed to parse proxy configuration: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return []
    
    def _create_proxy_auth_extension(self, username: str, password: str, host: str, port: int) -> str:
        """
        Create a Chrome extension for proxy authentication using Manifest V3.
        
        This uses asyncBlocking for proper async authentication handling,
        which is the most reliable method for proxy authentication with ZenDriver/CDP.
        
        Args:
            username: Proxy username
            password: Proxy password
            host: Proxy host
            port: Proxy port
            
        Returns:
            Path to the extension directory, or None if creation failed
        """
        try:
            import os
            import json
            
            # Create extension directory
            extension_dir = os.path.abspath("sessions/proxy_auth_extension")
            os.makedirs(extension_dir, exist_ok=True)
            
            # Manifest V3 - future-proof and properly handles async proxy auth
            manifest = {
                "manifest_version": 3,
                "name": "Proxy Auth Handler",
                "version": "1.0.0",
                "description": "Handles authenticated proxy connections for ZenDriver",
                "permissions": [
                    "webRequest",
                    "webRequestAuthProvider"
                ],
                "host_permissions": [
                    "<all_urls>"
                ],
                "background": {
                    "service_worker": "background.js"
                }
            }
            
            with open(os.path.join(extension_dir, "manifest.json"), "w") as f:
                json.dump(manifest, f, indent=2)
            
            # Service worker with async authentication handling
            # The key difference: asyncBlocking allows proper async credential handling
            background_js = f"""
// Proxy authentication handler - Manifest V3
// Uses asyncBlocking for proper async credential delivery

chrome.webRequest.onAuthRequired.addListener(
    (details, asyncCallback) => {{
        // Check if this is a proxy authentication challenge
        if (details.isProxy && details.challenger) {{
            console.log('[Proxy Auth] Proxy authentication required for {{' + 
                        details.challenger.host + ':' + details.challenger.port + '}}');
            
            // Return credentials asynchronously
            asyncCallback({{
                authCredentials: {{
                    username: '{username}',
                    password: '{password}'
                }}
            }});
        }} else {{
            asyncCallback({{}});
        }}
    }},
    {{ urls: ['<all_urls>'] }},
    ['asyncBlocking']
);

console.log('[Proxy Auth Extension] Loaded successfully - monitoring for proxy authentication challenges');
"""
            
            with open(os.path.join(extension_dir, "background.js"), "w") as f:
                f.write(background_js)
            
            self.logger.info(f"✓ Created Manifest V3 proxy auth extension at {extension_dir}")
            return extension_dir
            
        except Exception as e:
            self.logger.error(f"Failed to create proxy auth extension: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return None
    
    async def _apply_stealth_enhancements(self):
        """Apply additional stealth enhancements using CDP."""
        try:
            if not self.tab:
                return
            
            # Add realistic behavior patterns
            stealth_script = """
            // Add realistic mouse movement patterns
            let lastMouseMove = Date.now();
            document.addEventListener('mousemove', () => {
                lastMouseMove = Date.now();
            });
            
            // Simulate realistic timing patterns
            const originalSetTimeout = window.setTimeout;
            window.setTimeout = function(callback, delay) {
                // Add slight randomness to timing (human-like)
                const randomDelay = delay + (Math.random() - 0.5) * Math.min(delay * 0.1, 50);
                return originalSetTimeout(callback, randomDelay);
            };
            
            // Log fingerprint for debugging (ZenDriver handles most automatically)
            console.log('ZenDriver Chrome Fingerprint:', {
                userAgent: navigator.userAgent.includes('Chrome'),
                vendor: navigator.vendor,
                webdriver: navigator.webdriver,
                screen: screen.width + 'x' + screen.height,
                devicePixelRatio: window.devicePixelRatio,
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory || 'undefined',
                cdpDetection: 'ZenDriver uses CDP - highly stealthy'
            });
            """
            
            # Execute stealth script
            await self.tab.evaluate(stealth_script)
            self.logger.info("Applied ZenDriver stealth enhancements")
            
        except Exception as e:
            self.logger.debug(f"Stealth enhancements failed: {e}")
            # Don't fail the entire launch for stealth enhancement issues
    
    async def navigate_to_url(self, url: str) -> bool:
        """
        Navigate to specified URL with human-like behavior.
        
        Args:
            url: URL to navigate to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.browser:
                raise RuntimeError("Browser not initialized")
            
            self.logger.debug(f"Navigating to: {url}")
            
            # Add random delay before navigation (human-like behavior)
            await self._add_human_delay(0.5, 2.0)
            
            # Navigate using ZenDriver's get method
            self.tab = await self.browser.get(url)
            
            # Add post-navigation delay
            await self._add_human_delay(1.0, 3.0)
            
            self.logger.debug(f"Successfully navigated to: {url}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to navigate to {url}: {e}")
            return False
    
    async def find_element(self, selector: str, timeout: int = None) -> Optional[Any]:
        """
        Find page element with wait and error handling using latest ZenDriver API.
        
        Args:
            selector: Element selector (CSS selector, XPath, or text)
            timeout: Custom timeout (uses default if None)
            
        Returns:
            Element if found, None otherwise
        """
        try:
            if not self.tab:
                raise RuntimeError("Browser not initialized")
            
            wait_timeout = timeout or self.timeout
            
            # ZenDriver doesn't support timeout parameter in query_selector
            # We need to implement our own timeout logic
            start_time = time.time()
            
            while time.time() - start_time < wait_timeout:
                try:
                    # Determine selector type and use appropriate method
                    if selector.startswith('//') or selector.startswith('(//'):
                        # XPath selector - use xpath method
                        element = await self.tab.xpath(selector)
                        if element and len(element) > 0:
                            return element[0]  # Return first match
                    elif any(c in selector for c in ('.', '#', '[', '>', ':', '+', '~', '*', '=')) or selector in ['div', 'span', 'button', 'a', 'input', 'img', 'textarea']:
                        # CSS selector - use query_selector method
                        element = await self.tab.query_selector(selector)
                        if element:
                            return element
                    else:
                        # Fallback: check if it looks like CSS or text
                        try:
                            element = await self.tab.query_selector(selector)
                            if element:
                                return element
                        except:
                            pass
                            
                        # Text search - use find method with best_match
                        element = await self.tab.find(selector, best_match=True)
                        if element:
                            return element
                        
                except Exception as e:
                    # Element not found yet, continue waiting
                    pass
                
                # Wait a bit before retrying
                await asyncio.sleep(0.5)
            
            # Timeout reached, element not found
            return None
            
        except Exception as e:
            self.logger.warning(f"Element not found: {selector} - {e}")
            return None
    
    async def type_text_human_like(self, element, text: str) -> bool:
        """
        Type text with human-like delays and behavior.
        
        Args:
            element: Element to type into
            text: Text to type
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not element:
                return False
            
            # Clear existing text first using ZenDriver's method
            try:
                result = element.clear_input_by_deleting()
                if hasattr(result, '__await__'):
                    await result
            except:
                # Fallback: try to clear by selecting all and typing
                result = element.send_keys("Ctrl+a")
                if hasattr(result, '__await__'):
                    await result
                await asyncio.sleep(0.1)
            
            await asyncio.sleep(random.uniform(0.3, 0.7))
            
            # Type character by character with human-like delays
            for i, char in enumerate(text):
                result = element.send_keys(char)
                if hasattr(result, '__await__'):
                    await result
                
                # Variable delays between characters (faster for common sequences)
                if char == ' ':
                    # Longer pause after spaces
                    delay = random.uniform(0.1, 0.3)
                elif char in '.,!?':
                    # Pause after punctuation
                    delay = random.uniform(0.2, 0.4)
                elif i > 0 and text[i-1:i+1] in ['th', 'er', 'in', 'on', 'an', 'ed']:
                    # Faster for common letter combinations
                    delay = random.uniform(0.05, 0.15)
                else:
                    # Normal typing speed
                    delay = random.uniform(0.08, 0.25)
                
                await asyncio.sleep(delay)
                
                # Occasional longer pauses (thinking)
                if random.random() < 0.05:  # 5% chance
                    await asyncio.sleep(random.uniform(0.5, 1.5))
            
            self.logger.info(f"Typed text with human-like behavior: {len(text)} characters")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to type text human-like: {e}")
            return False
    
    async def scroll_page(self, pixels: int = 300) -> bool:
        """
        Scroll the page with ultra-realistic human-like behavior.
        Implements physics-based easing, micro-corrections, overshooting,
        variable momentum, and natural reading pauses.
        
        Args:
            pixels: Number of pixels to scroll (positive = down, negative = up)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.tab:
                return False
            
            import math
            
            direction = 1 if pixels > 0 else -1
            total_distance = abs(pixels)
            
            # Easing functions for natural motion
            def ease_out_cubic(t):
                """Deceleration curve - fast start, slow end"""
                return 1 - pow(1 - t, 3)
            
            def ease_in_out_sine(t):
                """Smooth S-curve acceleration/deceleration"""
                return -(math.cos(math.pi * t) - 1) / 2
            
            def ease_out_expo(t):
                """Exponential deceleration - like finger lift"""
                return 1 if t == 1 else 1 - pow(2, -10 * t)
            
            # Choose random easing style for this scroll session
            easing_funcs = [ease_out_cubic, ease_in_out_sine, ease_out_expo]
            chosen_ease = random.choice(easing_funcs)
            
            # Determine scroll style (wheel, trackpad, or touch-like)
            scroll_style = random.choice(['wheel', 'trackpad', 'momentum'])
            
            scrolled = 0
            
            if scroll_style == 'wheel':
                # Mouse wheel: discrete chunks with variable timing
                while scrolled < total_distance:
                    # Wheel notches are typically 40-120 pixels
                    chunk = random.randint(35, 100)
                    if scrolled + chunk > total_distance:
                        chunk = total_distance - scrolled
                    
                    # Apply slight randomness to simulate imperfect wheel movement
                    jitter = random.randint(-5, 5)
                    actual_chunk = max(10, chunk + jitter)
                    
                    await self.tab.evaluate(f"window.scrollBy({{top: {actual_chunk * direction}, behavior: 'auto'}})")
                    scrolled += chunk
                    
                    # Variable delay between wheel notches
                    base_delay = random.uniform(0.08, 0.25)
                    # Sometimes user scrolls faster, sometimes slower
                    if random.random() < 0.15:
                        base_delay = random.uniform(0.3, 0.8)  # Pause to read
                    await asyncio.sleep(base_delay)
                    
            elif scroll_style == 'trackpad':
                # Trackpad: smooth continuous motion with momentum
                num_steps = random.randint(15, 30)
                
                for i in range(num_steps):
                    progress = (i + 1) / num_steps
                    eased_progress = chosen_ease(progress)
                    
                    target_scrolled = int(total_distance * eased_progress)
                    step_amount = target_scrolled - scrolled
                    
                    if step_amount > 0:
                        # Add micro-jitter for realism
                        jitter = random.uniform(-2, 2)
                        await self.tab.evaluate(f"window.scrollBy({{top: {(step_amount + jitter) * direction}, behavior: 'auto'}})")
                        scrolled = target_scrolled
                    
                    # Variable frame timing (simulating 30-60fps input)
                    await asyncio.sleep(random.uniform(0.016, 0.05))
                
            else:  # momentum
                # Touch/momentum: initial velocity with decay
                # Simulate finger flick with momentum decay
                
                # Phase 1: Initial fast scroll (finger on screen)
                initial_burst = int(total_distance * random.uniform(0.4, 0.6))
                burst_steps = random.randint(5, 10)
                
                for i in range(burst_steps):
                    chunk = initial_burst // burst_steps
                    jitter = random.randint(-3, 3)
                    await self.tab.evaluate(f"window.scrollBy({{top: {(chunk + jitter) * direction}, behavior: 'auto'}})")
                    scrolled += chunk
                    await asyncio.sleep(random.uniform(0.01, 0.03))
                
                # Phase 2: Momentum decay (finger lifted)
                remaining = total_distance - scrolled
                velocity = remaining * random.uniform(0.15, 0.25)  # Initial momentum velocity
                friction = random.uniform(0.85, 0.92)  # Decay rate
                
                while velocity > 2 and scrolled < total_distance:
                    step = min(int(velocity), total_distance - scrolled)
                    if step < 1:
                        break
                    
                    await self.tab.evaluate(f"window.scrollBy({{top: {step * direction}, behavior: 'auto'}})")
                    scrolled += step
                    velocity *= friction
                    
                    # Momentum frames get slower as velocity decreases
                    await asyncio.sleep(random.uniform(0.02, 0.04))
            
            # Occasional overshoot and correction (very human behavior)
            if random.random() < 0.2 and total_distance > 100:
                overshoot = random.randint(20, 60)
                self.logger.debug(f"Simulating overshoot correction: {overshoot}px")
                await self.tab.evaluate(f"window.scrollBy({{top: {overshoot * direction}, behavior: 'smooth'}})")
                await asyncio.sleep(random.uniform(0.3, 0.6))
                # Correct back
                await self.tab.evaluate(f"window.scrollBy({{top: {-overshoot * direction}, behavior: 'smooth'}})")
                await asyncio.sleep(random.uniform(0.2, 0.4))
            
            # Random micro-adjustment at end (settling)
            if random.random() < 0.3:
                micro = random.randint(-15, 15)
                await self.tab.evaluate(f"window.scrollBy({{top: {micro}, behavior: 'smooth'}})")
                await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # Occasional reading pause after scroll completes
            if random.random() < 0.25:
                pause = random.uniform(0.8, 2.5)
                self.logger.debug(f"Adding reading pause: {pause:.1f}s")
                await asyncio.sleep(pause)
            
            self.logger.info(f"Scrolled page by {pixels} pixels ({scroll_style} style)")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to scroll page: {e}")
            return False
    
    async def get_current_url(self) -> str:
        """
        Get the current page URL.
        
        Returns:
            Current URL as string
        """
        try:
            if not self.tab:
                return ""
            
            # In ZenDriver, tab.url is a property, not a method
            return self.tab.url or ""
            
        except Exception as e:
            self.logger.error(f"Failed to get current URL: {e}")
            return ""
    
    async def find_elements(self, selector: str) -> List[Any]:
        """
        Find multiple page elements using latest ZenDriver API.
        
        Args:
            selector: Element selector
            
        Returns:
            List of Elements (empty if none found)
        """
        try:
            if not self.tab:
                raise RuntimeError("Browser not initialized")
            
            # ZenDriver's query_selector_all method for multiple elements (latest API)
            if selector.startswith(('.', '#', '[')):
                # CSS selector
                elements = await self.tab.query_selector_all(selector)
            else:
                # Text search - find all matching elements
                elements = await self.tab.find_all(selector)
            
            return elements or []
            
        except Exception as e:
            self.logger.warning(f"Elements not found: {selector} - {e}")
            return []
    
    async def click_element(self, element: Any) -> bool:
        """
        Click element with human-like behavior.
        
        Args:
            element: Element to click
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not element:
                return False
            
            # Add delay before clicking (human-like behavior)
            await self._add_human_delay(0.2, 0.8)
            
            # ZenDriver's click method (includes humanization)
            result = element.click()
            if hasattr(result, '__await__'):
                await result
            
            # Add post-click delay
            await self._add_human_delay(0.3, 1.0)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to click element: {e}")
            return False
    
    async def type_text(self, element: Any, text: str, clear_first: bool = True) -> bool:
        """
        Type text with human-like timing using latest ZenDriver API.
        
        Args:
            element: Element to type into
            text: Text to type
            clear_first: Whether to clear existing text first
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not element or not text:
                return False
            
            # Clear existing text if requested
            if clear_first:
                try:
                    # Try to clear using ZenDriver's clear_input_by_deleting method (v0.9.0+)
                    if hasattr(element, 'clear_input_by_deleting'):
                        await element.clear_input_by_deleting()
                    elif hasattr(element, 'clear'):
                        await element.clear()
                    else:
                        # Fallback: select all and delete
                        await element.click()
                        await asyncio.sleep(0.1)
                        # Send Ctrl+A to select all, then delete
                        await element.send_keys('\x01')  # Ctrl+A
                        await asyncio.sleep(0.1)
                        await element.send_keys('\x08')  # Backspace
                except Exception as e:
                    self.logger.debug(f"Could not clear element: {e}")
                
                await self._add_human_delay(0.1, 0.3)
            
            # Click to focus
            await element.click()
            await self._add_human_delay(0.2, 0.5)
            
            # Type text with ZenDriver's send_keys (includes humanization)
            # Use special_characters flag for emojis and special chars (v0.8.1+)
            try:
                await element.send_keys(text, special_characters=True)
            except TypeError:
                # Fallback for older versions without special_characters parameter
                await element.send_keys(text)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to type text: {e}")
            return False
    
    async def execute_script(self, script: str, *args) -> Any:
        """
        Execute JavaScript in page context.
        
        Args:
            script: JavaScript code to execute
            *args: Arguments to pass to script
            
        Returns:
            Script execution result
        """
        try:
            if not self.tab:
                raise RuntimeError("Browser not initialized")
            
            return await self.tab.evaluate(script, *args)
            
        except Exception as e:
            self.logger.error(f"Failed to execute script: {e}")
            return None
    
    async def get_cookies(self) -> List[Dict]:
        """
        Get all cookies from current session using ZenDriver's latest CookieJar API.
        
        Returns:
            List of cookie dictionaries
        """
        try:
            if not self.browser:
                self.logger.warning("Browser not available for cookie retrieval")
                return []
            
            # Method 1: Use ZenDriver's built-in CookieJar (most reliable)
            # browser.cookies is a CookieJar with get_all() method
            try:
                if hasattr(self.browser, 'cookies') and self.browser.cookies:
                    # get_all() returns cookies - can use requests_cookie_format=True for compatibility
                    cookies = await self.browser.cookies.get_all()
                    if cookies:
                        # Convert to list of dicts if needed
                        formatted_cookies = []
                        for cookie in cookies:
                            if hasattr(cookie, '__dict__'):
                                # It's an object, convert to dict
                                # Handle sameSite Enum if present
                                same_site = getattr(cookie, 'same_site', getattr(cookie, 'sameSite', 'Lax'))
                                if hasattr(same_site, 'value'):
                                    same_site = same_site.value
                                elif not isinstance(same_site, (str, type(None))):
                                    same_site = str(same_site)

                                cookie_dict = {
                                    'name': getattr(cookie, 'name', ''),
                                    'value': getattr(cookie, 'value', ''),
                                    'domain': getattr(cookie, 'domain', ''),
                                    'path': getattr(cookie, 'path', '/'),
                                    'secure': getattr(cookie, 'secure', False),
                                    'httpOnly': getattr(cookie, 'http_only', getattr(cookie, 'httpOnly', False)),
                                    'sameSite': same_site,
                                    'expires': getattr(cookie, 'expires', None)
                                }
                                formatted_cookies.append(cookie_dict)
                            elif isinstance(cookie, dict):
                                # Sanitize dict for serialization
                                if 'sameSite' in cookie and not isinstance(cookie['sameSite'], (str, type(None))):
                                    if hasattr(cookie['sameSite'], 'value'):
                                        cookie['sameSite'] = cookie['sameSite'].value
                                    else:
                                        cookie['sameSite'] = str(cookie['sameSite'])
                                if 'same_site' in cookie and not isinstance(cookie['same_site'], (str, type(None))):
                                    if hasattr(cookie['same_site'], 'value'):
                                        cookie['same_site'] = cookie['same_site'].value
                                    else:
                                        cookie['same_site'] = str(cookie['same_site'])
                                formatted_cookies.append(cookie)
                            else:
                                # Try to use it as-is
                                formatted_cookies.append({'raw': str(cookie)})
                        
                        self.logger.info(f"Retrieved {len(formatted_cookies)} cookies using ZenDriver CookieJar")
                        return formatted_cookies
                    
            except Exception as e:
                self.logger.debug(f"ZenDriver CookieJar method failed: {e}")
            
            # Method 2: Use CDP Network.getAllCookies directly
            try:
                from zendriver.cdp import network
                
                # Get cookies via CDP
                cookies_result = await self.tab.send(network.get_all_cookies())
                
                if cookies_result:
                    formatted_cookies = []
                    # cookies_result is typically a list of Cookie objects
                    cookies_list = cookies_result if isinstance(cookies_result, list) else getattr(cookies_result, 'cookies', [])
                    
                    for cookie in cookies_list:
                        cookie_dict = {
                            'name': getattr(cookie, 'name', ''),
                            'value': getattr(cookie, 'value', ''),
                            'domain': getattr(cookie, 'domain', ''),
                            'path': getattr(cookie, 'path', '/'),
                            'secure': getattr(cookie, 'secure', False),
                            'httpOnly': getattr(cookie, 'http_only', getattr(cookie, 'httpOnly', False)),
                            'sameSite': str(getattr(cookie, 'same_site', getattr(cookie, 'sameSite', 'Lax'))),
                            'expires': getattr(cookie, 'expires', None)
                        }
                        formatted_cookies.append(cookie_dict)
                    
                    if formatted_cookies:
                        self.logger.info(f"Retrieved {len(formatted_cookies)} cookies using CDP Network.getAllCookies")
                        return formatted_cookies
                        
            except Exception as e:
                self.logger.debug(f"CDP Network.getAllCookies failed: {e}")
            
            # Method 3: Use JavaScript as last resort (can only get non-httpOnly cookies)
            try:
                if self.tab:
                    cookie_script = """
                    const cookies = [];
                    if (document.cookie) {
                        document.cookie.split(';').forEach(cookie => {
                            const [name, ...valueParts] = cookie.trim().split('=');
                            const value = valueParts.join('=');
                            if (name && value !== undefined) {
                                cookies.push({
                                    name: name.trim(),
                                    value: value.trim(),
                                    domain: window.location.hostname,
                                    path: '/',
                                    secure: window.location.protocol === 'https:',
                                    httpOnly: false,
                                    sameSite: 'Lax'
                                });
                            }
                        });
                    }
                    return cookies;
                    """
                    
                    cookies = await self.tab.evaluate(cookie_script)
                    if cookies and len(cookies) > 0:
                        self.logger.info(f"Retrieved {len(cookies)} cookies using JavaScript (non-httpOnly only)")
                        return cookies
                        
            except Exception as e:
                self.logger.debug(f"JavaScript cookie method failed: {e}")
            
            self.logger.info("No cookies could be retrieved")
            return []
            
        except Exception as e:
            self.logger.error(f"Unexpected error in get_cookies: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            return []
    
    async def set_cookies(self, cookies: List[Dict]) -> bool:
        """
        Set cookies in current session using ZenDriver's latest CookieJar API.
        
        Args:
            cookies: List of cookie dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.browser or not cookies:
                return False
            
            self.logger.info(f"Setting {len(cookies)} cookies")
            
            # Method 1: Use ZenDriver's CookieJar (most reliable)
            try:
                if hasattr(self.browser, 'cookies') and self.browser.cookies:
                    # CookieJar has set() method for adding cookies
                    for cookie in cookies:
                        # ZenDriver's CookieJar may have different interface
                        # Try direct set if available
                        if hasattr(self.browser.cookies, 'set'):
                            await self.browser.cookies.set(cookie)
                    self.logger.info(f"Set {len(cookies)} cookies using ZenDriver CookieJar")
                    return True
            except Exception as e:
                self.logger.debug(f"ZenDriver CookieJar set failed: {e}")
            
            # Method 2: Use CDP Network.setCookie
            try:
                from zendriver.cdp import network
                
                successful_cookies = 0
                for cookie in cookies:
                    try:
                        # Build cookie parameters for CDP
                        cookie_params = {
                            'name': cookie.get('name', ''),
                            'value': cookie.get('value', ''),
                        }
                        
                        # Add optional fields
                        if cookie.get('domain'):
                            cookie_params['domain'] = cookie['domain']
                        if cookie.get('path'):
                            cookie_params['path'] = cookie['path']
                        if cookie.get('secure') is not None:
                            cookie_params['secure'] = cookie['secure']
                        if cookie.get('httpOnly') is not None:
                            cookie_params['http_only'] = cookie['httpOnly']
                        if cookie.get('sameSite'):
                            cookie_params['same_site'] = cookie['sameSite']
                        if cookie.get('expires'):
                            cookie_params['expires'] = cookie['expires']
                        
                        await self.tab.send(network.set_cookie(**cookie_params))
                        successful_cookies += 1
                        
                    except Exception as e:
                        self.logger.debug(f"Failed to set cookie {cookie.get('name', 'unknown')}: {e}")
                        continue
                
                if successful_cookies > 0:
                    self.logger.info(f"Set {successful_cookies}/{len(cookies)} cookies using CDP")
                    return True
                    
            except Exception as e:
                self.logger.debug(f"CDP cookie setting failed: {e}")
            
            # Method 3: Use JavaScript as fallback (limited to non-httpOnly cookies)
            try:
                js_cookies_set = 0
                for cookie in cookies:
                    # Skip httpOnly cookies as they can't be set via JavaScript
                    if cookie.get('httpOnly', False):
                        continue
                        
                    cookie_string = f"{cookie.get('name', '')}={cookie.get('value', '')}"
                    
                    # Add optional attributes
                    if cookie.get('path'):
                        cookie_string += f"; path={cookie['path']}"
                    if cookie.get('domain'):
                        cookie_string += f"; domain={cookie['domain']}"
                    if cookie.get('secure'):
                        cookie_string += "; secure"
                    if cookie.get('sameSite'):
                        cookie_string += f"; samesite={cookie['sameSite']}"
                    
                    # Set cookie via JavaScript
                    await self.tab.evaluate(f"document.cookie = '{cookie_string}'")
                    js_cookies_set += 1
                
                if js_cookies_set > 0:
                    self.logger.info(f"Set {js_cookies_set} cookies using JavaScript (non-httpOnly only)")
                    return True
                
            except Exception as e:
                self.logger.debug(f"JavaScript cookie setting failed: {e}")
            
            self.logger.warning("All cookie setting methods failed")
            return False
            
        except Exception as e:
            self.logger.error(f"Unexpected error setting cookies: {e}")
            return False
    
    async def take_screenshot(self, filename: str = None) -> Optional[str]:
        """
        Take screenshot of current page.
        
        Args:
            filename: Optional filename for screenshot
            
        Returns:
            Screenshot filename if successful, None otherwise
        """
        try:
            if not self.tab:
                return None
            
            if not filename:
                timestamp = int(time.time())
                filename = f"screenshot_{timestamp}.png"
            
            # Ensure screenshots directory exists
            screenshots_dir = Path("screenshots")
            screenshots_dir.mkdir(exist_ok=True)
            
            filepath = screenshots_dir / filename
            
            # ZenDriver's save_screenshot method
            await self.tab.save_screenshot(str(filepath))
            
            self.logger.debug(f"Screenshot saved: {filepath}")
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"Failed to take screenshot: {e}")
            return None
    
    async def close_browser(self) -> None:
        """Close browser and cleanup resources."""
        try:
            if self.browser:
                await self.browser.stop()
            
            self.browser = None
            self.tab = None
            
            self.logger.info("ZenDriver browser closed")
        except Exception as e:
            self.logger.error(f"Error closing browser: {e}")
            # Force cleanup
            self.browser = None
            self.tab = None
    
    async def _add_human_delay(self, min_seconds: float, max_seconds: float) -> None:
        """
        Add random delay to simulate human behavior.
        
        Args:
            min_seconds: Minimum delay in seconds
            max_seconds: Maximum delay in seconds
        """
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)
    
    
    async def get_page_title(self) -> str:
        """Get current page title."""
        try:
            if self.tab:
                return await self.tab.evaluate("document.title")
            return ""
        except Exception:
            return ""
    
    async def is_browser_alive(self) -> bool:
        """Check if browser is still running."""
        try:
            if not self.tab or not self.browser:
                return False
            # Try to get current URL as a simple health check
            self.tab.url
            return True
        except Exception:
            return False
    
    async def refresh_page(self) -> bool:
        """Refresh current page."""
        try:
            if not self.tab:
                return False
            
            await self.tab.reload()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to refresh page: {e}")
            return False

    async def element_has_child(self, parent_element: Any, child_selector: str) -> bool:
        """
        Check if a parent element has a child matching the selector.
        
        Args:
            parent_element: Parent element to search within
            child_selector: CSS selector for child element
            
        Returns:
            True if child exists, False otherwise
        """
        try:
            if not self.tab or not parent_element:
                return False
            
            # Use querySelector on the parent element
            script = f"""
            (element) => {{
                return element.querySelector('{child_selector}') !== null;
            }}
            """
            
            result = await parent_element.apply(script)
            return bool(result)
            
        except Exception as e:
            self.logger.debug(f"Error checking for child element: {e}")
            return False
    
    async def find_element_in_parent(self, parent_element: Any, selector: str) -> Optional[Any]:
        """
        Find an element within a parent element.
        
        Args:
            parent_element: Parent element to search within
            selector: CSS selector for element to find
            
        Returns:
            Element if found, None otherwise
        """
        try:
            if not self.tab or not parent_element:
                return None
            
            # Use querySelector on the parent element
            script = f"""
            (element) => {{
                return element.querySelector('{selector}');
            }}
            """
            
            result = await parent_element.apply(script)
            return result if result else None
            
        except Exception as e:
            self.logger.debug(f"Error finding element in parent: {e}")
            return None
    
    async def get_element_text(self, element: Any) -> str:
        """
        Get text content of an element.
        
        Args:
            element: Element to get text from
            
        Returns:
            Text content or empty string
        """
        try:
            if not element:
                return ""
            
            # Get text content
            script = """
            (element) => {
                return element.textContent || element.innerText || '';
            }
            """
            
            text = await element.apply(script)
            return str(text).strip() if text else ""
            
        except Exception as e:
            self.logger.debug(f"Error getting element text: {e}")
            return ""
    
    async def scroll_element_into_view(self, element: Any, smooth: bool = None) -> bool:
        """
        Scroll an element into view with human-like behavior.
        
        Args:
            element: Element to scroll into view
            smooth: Whether to use smooth scrolling (None = random choice)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not element:
                return False
            
            # Randomize behavior if not specified (70% smooth, 30% auto)
            if smooth is None:
                smooth = random.random() < 0.7
            
            behavior = "smooth" if smooth else "auto"
            
            # Randomize vertical alignment for natural variation
            block_options = ['center', 'start', 'nearest']
            block_weights = [0.6, 0.25, 0.15]  # Prefer center, but vary
            block = random.choices(block_options, weights=block_weights)[0]
            
            # Occasionally use 'end' if element is far down
            if random.random() < 0.1:
                block = 'end'
            
            script = f"""
            (element) => {{
                element.scrollIntoView({{
                    behavior: '{behavior}',
                    block: '{block}',
                    inline: 'nearest'
                }});
            }}
            """
            
            await element.apply(script)
            
            # Variable wait based on scroll type
            if smooth:
                # Smooth scrolling takes longer
                await asyncio.sleep(random.uniform(0.8, 1.5))
            else:
                # Auto scroll is instant but humans still pause
                await asyncio.sleep(random.uniform(0.3, 0.7))
            
            # 15% chance: small adjustment scroll after main scroll (reading/positioning)
            if random.random() < 0.15:
                adjustment = random.randint(-50, 50)
                await self.tab.evaluate(f"window.scrollBy({{top: {adjustment}, behavior: 'smooth'}})")
                await asyncio.sleep(random.uniform(0.2, 0.5))
            
            # 20% chance: brief pause as if reading/locating element
            if random.random() < 0.2:
                await asyncio.sleep(random.uniform(0.3, 0.8))
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error scrolling element into view: {e}")
            return False
    
    async def wait_for_element_with_text(self, selector: str, text: str, timeout: int = 10) -> Optional[Any]:
        """
        Wait for an element with specific text content to appear.
        
        Args:
            selector: CSS selector for element
            text: Text content to match
            timeout: Maximum wait time in seconds
            
        Returns:
            Element if found, None otherwise
        """
        try:
            if not self.tab:
                return None
            
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                elements = await self.find_elements(selector)
                
                for element in elements:
                    element_text = await self.get_element_text(element)
                    if text.lower() in element_text.lower():
                        self.logger.debug(f"Found element with text: {text}")
                        return element
                
                await asyncio.sleep(0.5)
            
            self.logger.debug(f"Element with text '{text}' not found within {timeout}s")
            return None
            
        except Exception as e:
            self.logger.error(f"Error waiting for element with text: {e}")
            return None

"""
Proxy management system for the Enhanced Twitter Bot.
"""

import asyncio
import random
import logging
import aiohttp
import requests
import time
from datetime import datetime
from typing import List, Optional, Dict, Callable
from pathlib import Path
import json
import concurrent.futures

from ..models.proxy import ProxyData
from ..utils.file_manager import FileManager


class ProxyManager:
    """Manages proxy operations, testing, and rotation."""
    
    def __init__(self, config: Dict):
        """Initialize proxy manager."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.file_manager = FileManager()
        
        # Proxy storage
        self.proxies: Dict[str, ProxyData] = {}
        self.proxy_file = Path("data/proxies.json")
        
        # Load existing proxies
        self.load_proxies()
    
    def load_proxies(self) -> None:
        """Load proxies from file."""
        try:
            self.logger.info(f"Attempting to load proxies from: {self.proxy_file}")
            if self.proxy_file.exists():
                self.logger.info(f"Proxy file exists, size: {self.proxy_file.stat().st_size} bytes")
                
                # Read and parse JSON directly
                with open(self.proxy_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                self.logger.info(f"Loaded proxy data: {list(data.keys()) if data else 'No data'}")
                
                for proxy_id, proxy_data in data.items():
                    self.proxies[proxy_id] = ProxyData.from_dict(proxy_data)
                    
                self.logger.info(f"Loaded {len(self.proxies)} proxies")
            else:
                self.logger.info(f"No existing proxy file found at: {self.proxy_file}")
        except Exception as e:
            self.logger.error(f"Failed to load proxies: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
    
    def save_proxies(self) -> None:
        """Save proxies to file."""
        try:
            # Ensure data directory exists
            self.proxy_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to serializable format
            data = {
                proxy_id: proxy.to_dict() 
                for proxy_id, proxy in self.proxies.items()
            }
            
            # Write JSON directly
            with open(self.proxy_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Saved {len(self.proxies)} proxies to {self.proxy_file}")
            
            # Verify the file was actually written
            if self.proxy_file.exists():
                file_size = self.proxy_file.stat().st_size
                self.logger.debug(f"Proxy file size: {file_size} bytes")
            else:
                self.logger.error("Proxy file was not created after save attempt")
                
        except Exception as e:
            self.logger.error(f"Failed to save proxies: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
    
    def add_proxy(self, host: str, port: int, username: str = None, 
                  password: str = None, rotation_url: str = None, 
                  protocol: str = "http") -> str:
        """Add a new proxy."""
        try:
            # Use a simple ID format without protocol prefix to avoid URL issues
            proxy_id = f"{host}_{port}_{protocol}"
            
            proxy = ProxyData(
                host=host,
                port=port,
                username=username,
                password=password,
                protocol=protocol,
                rotation_url=rotation_url
            )
            
            self.proxies[proxy_id] = proxy
            self.save_proxies()
            
            self.logger.info(f"Added proxy: {proxy.display_url}")
            return proxy_id
            
        except Exception as e:
            self.logger.error(f"Failed to add proxy: {e}")
            raise
    
    def remove_proxy(self, proxy_id: str) -> bool:
        """Remove a proxy."""
        try:
            if proxy_id in self.proxies:
                proxy = self.proxies[proxy_id]
                del self.proxies[proxy_id]
                self.save_proxies()
                self.logger.info(f"Removed proxy: {proxy.display_url}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to remove proxy: {e}")
            return False
    
    def get_working_proxies(self) -> List[str]:
        """Get list of working proxy IDs."""
        max_failures = self.config.get("proxy_max_failures", 3)
        return [
            proxy_id for proxy_id, proxy in self.proxies.items()
            if proxy.status == "active" and proxy.failure_count < max_failures
        ]
    
    def get_random_proxy(self) -> Optional[ProxyData]:
        """Get a random working proxy."""
        working_proxies = self.get_working_proxies()
        if not working_proxies:
            return None
        
        proxy_id = random.choice(working_proxies)
        proxy = self.proxies[proxy_id]
        proxy.last_used = datetime.now()
        self.save_proxies()
        return proxy
    
    def rotate_proxy_ip(self, proxy_id: str) -> bool:
        """Rotate IP for a specific proxy using its rotation URL."""
        if proxy_id not in self.proxies:
            self.logger.error(f"Proxy {proxy_id} not found")
            return False
        
        proxy = self.proxies[proxy_id]
        if not proxy.rotation_url:
            self.logger.error(f"Proxy {proxy_id} has no rotation URL")
            return False
        
        try:
            response = requests.get(proxy.rotation_url, timeout=10)
            if response.status_code == 200:
                self.logger.info(f"Successfully rotated IP for proxy {proxy.display_url}")
                return True
            else:
                self.logger.error(f"Failed to rotate IP for proxy {proxy.display_url}: HTTP {response.status_code}")
                return False
        except Exception as e:
            self.logger.error(f"Error rotating IP for proxy {proxy.display_url}: {e}")
            return False
    
    async def test_proxy(self, proxy: ProxyData) -> bool:
        """Test if a proxy is working."""
        start_time = time.time()
        
        try:
            proxy.status = "testing"
            
            # Choose test method based on protocol
            if proxy.protocol in ["socks4", "socks5"]:
                success = await self._test_socks_proxy(proxy)
            else:
                success = await self._test_http_proxy(proxy)
            
            response_time = time.time() - start_time
            
            if success:
                proxy.update_success(response_time)
                self.logger.info(f"Proxy {proxy.display_url} is working (response time: {response_time:.2f}s)")
            else:
                proxy.update_failure()
                self.logger.warning(f"Proxy {proxy.display_url} failed test")
            
            return success
            
        except Exception as e:
            proxy.update_failure()
            self.logger.warning(f"Proxy {proxy.display_url} failed: {e}")
            return False
    
    async def _test_http_proxy(self, proxy: ProxyData) -> bool:
        """Test HTTP/HTTPS proxy using aiohttp."""
        proxy_url = proxy.url
        timeout = aiohttp.ClientTimeout(total=self.config.get("proxy_test_timeout", 10))
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    "https://httpbin.org/ip",
                    proxy=proxy_url
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        current_ip = data.get('origin', 'unknown')
                        self.logger.debug(f"Proxy {proxy.display_url} working - IP: {current_ip}")
                        return True
                    else:
                        raise Exception(f"HTTP {response.status}")
        except Exception as e:
            raise e
    
    async def _test_socks_proxy(self, proxy: ProxyData) -> bool:
        """Test SOCKS proxy using requests with PySocks in a thread."""
        def test_socks_sync():
            try:
                import socks
                import socket
                
                # Create a session with SOCKS proxy
                session = requests.Session()
                session.proxies = {
                    'http': proxy.url,
                    'https': proxy.url
                }
                
                # Test the proxy
                response = session.get(
                    "https://httpbin.org/ip", 
                    timeout=self.config.get("proxy_test_timeout", 10)
                )
                
                if response.status_code == 200:
                    data = response.json()
                    current_ip = data.get('origin', 'unknown')
                    self.logger.debug(f"SOCKS proxy {proxy.display_url} working - IP: {current_ip}")
                    return True
                else:
                    raise Exception(f"HTTP {response.status_code}")
                    
            except ImportError:
                self.logger.error("PySocks not installed. Install with: pip install pysocks")
                raise Exception("PySocks not installed")
            except Exception as e:
                raise e
        
        # Run in thread pool
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            try:
                await loop.run_in_executor(executor, test_socks_sync)
                return True
            except Exception as e:
                raise e
    
    async def test_all_proxies(self, progress_callback: Optional[Callable] = None) -> Dict[str, bool]:
        """Test all proxies and return results."""
        self.logger.info("Testing all proxies...")
        results = {}
        
        total_count = len(self.proxies)
        current = 0
        
        for proxy_id, proxy in self.proxies.items():
            current += 1
            
            if progress_callback:
                await progress_callback(current, total_count, proxy.display_url)
            
            results[proxy_id] = await self.test_proxy(proxy)
            
            # Small delay between tests
            await asyncio.sleep(random.uniform(0.5, 1.5))
        
        self.save_proxies()
        
        working_count = sum(1 for success in results.values() if success)
        self.logger.info(f"Proxy test complete: {working_count}/{total_count} working")
        
        return results
    
    def import_proxies_from_file(self, file_path: str) -> int:
        """Import proxies from a text file."""
        imported_count = 0
        
        try:
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    try:
                        # Parse proxy format: host:port or username:password@host:port
                        if '@' in line:
                            # Format: username:password@host:port
                            auth_part, host_port = line.split('@', 1)
                            username, password = auth_part.split(':', 1)
                            host, port = host_port.split(':', 1)
                        else:
                            # Format: host:port
                            username = password = None
                            host, port = line.split(':', 1)
                        
                        # Add proxy
                        self.add_proxy(host, int(port), username, password, None, 'http')
                        imported_count += 1
                        
                    except Exception as e:
                        self.logger.warning(f"Failed to parse line {line_num}: {line} - {e}")
                        continue
                        
        except Exception as e:
            self.logger.error(f"Error importing proxies from {file_path}: {e}")
            raise
        
        self.logger.info(f"Imported {imported_count} proxies from {file_path}")
        return imported_count
    
    def get_proxy_stats(self) -> Dict[str, int]:
        """Get proxy statistics."""
        stats = {
            'total': len(self.proxies),
            'active': 0,
            'failed': 0,
            'unknown': 0,
            'with_rotation': 0
        }
        
        for proxy in self.proxies.values():
            if proxy.status == 'active':
                stats['active'] += 1
            elif proxy.status == 'failed':
                stats['failed'] += 1
            else:
                stats['unknown'] += 1
            
            if proxy.rotation_url:
                stats['with_rotation'] += 1
        
        return stats
    
    def get_all_proxies(self) -> Dict[str, ProxyData]:
        """Get all proxies."""
        return self.proxies.copy()
    
    def test_proxy_sync(self, proxy_id: str) -> bool:
        """Test a single proxy synchronously."""
        if proxy_id not in self.proxies:
            return False
        
        proxy = self.proxies[proxy_id]
        try:
            # Use requests for synchronous testing instead of asyncio
            return self._test_proxy_requests(proxy)
        except Exception as e:
            self.logger.error(f"Failed to test proxy {proxy_id}: {e}")
            return False
    
    def _test_proxy_requests(self, proxy: ProxyData) -> bool:
        """Test proxy using requests library synchronously."""
        try:
            proxy.status = "testing"
            
            # Build proxy URL
            if proxy.username and proxy.password:
                proxy_url = f"{proxy.protocol}://{proxy.username}:{proxy.password}@{proxy.host}:{proxy.port}"
            else:
                proxy_url = f"{proxy.protocol}://{proxy.host}:{proxy.port}"
            
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            # Test with a simple HTTP request
            response = requests.get(
                'https://httpbin.org/ip',
                proxies=proxies,
                timeout=10
            )
            
            if response.status_code == 200:
                proxy.status = "active"
                self.save_proxies()
                return True
            else:
                proxy.status = "failed"
                self.save_proxies()
                return False
                
        except Exception as e:
            proxy.status = "failed"
            self.save_proxies()
            self.logger.debug(f"Proxy test failed: {e}")
            return False
    
    def test_all_proxies_sync(self) -> Dict[str, str]:
        """Test all proxies synchronously and return results."""
        results = {}
        for proxy_id, proxy in self.proxies.items():
            try:
                is_working = self._test_proxy_requests(proxy)
                results[proxy_id] = "working" if is_working else "failed"
            except Exception as e:
                self.logger.error(f"Failed to test proxy {proxy_id}: {e}")
                results[proxy_id] = "failed"
                proxy.status = "failed"
        
        self.save_proxies()
        return results
    
    def clear_failed_proxies(self) -> int:
        """Remove all failed proxies."""
        failed_proxies = [
            proxy_id for proxy_id, proxy in self.proxies.items()
            if proxy.status == "failed"
        ]
        
        for proxy_id in failed_proxies:
            self.remove_proxy(proxy_id)
        
        self.logger.info(f"Cleared {len(failed_proxies)} failed proxies")
        return len(failed_proxies)
    
    def format_proxy_for_zendriver(self, proxy: ProxyData) -> str:
        """Format proxy configuration for ZenDriver browser."""
        if proxy.username and proxy.password:
            return f"{proxy.protocol}://{proxy.username}:{proxy.password}@{proxy.host}:{proxy.port}"
        else:
            return f"{proxy.protocol}://{proxy.host}:{proxy.port}"
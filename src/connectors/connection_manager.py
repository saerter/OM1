"""
Enhanced Connection Manager for OM1
This improves the reliability of API connections and reduces timeouts
"""

import asyncio
import logging
from typing import Callable, Any, Optional
from functools import wraps
import time

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages robust connections with automatic retry and backoff
    """
    
    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0, base_timeout: int = 10):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.base_timeout = base_timeout
        self.connection_attempts = 0
        self.successful_connections = 0
        self.failed_connections = 0
    
    async def robust_connect(self, connection_func: Callable, *args, **kwargs) -> Any:
        """
        Attempts to establish a connection with automatic retry logic
        
        Args:
            connection_func: The function to call for connection
            *args: Arguments to pass to the connection function
            **kwargs: Keyword arguments to pass to the connection function
            
        Returns:
            The result of the connection function
            
        Raises:
            Exception: If all retry attempts fail
        """
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                self.connection_attempts += 1
                logger.info(f"Connection attempt {attempt + 1}/{self.max_retries}")
                
                # Add timeout to the connection
                timeout = self.base_timeout + (attempt * 2)  # Increase timeout with each retry
                result = await asyncio.wait_for(connection_func(*args, **kwargs), timeout=timeout)
                
                logger.info(f"Connection successful on attempt {attempt + 1}")
                self.successful_connections += 1
                return result
                
            except asyncio.TimeoutError:
                last_exception = Exception(f"Connection timed out after {timeout} seconds")
                logger.warning(f"Connection attempt {attempt + 1} timed out after {timeout} seconds")
            except Exception as e:
                last_exception = e
                logger.warning(f"Connection attempt {attempt + 1} failed: {str(e)}")
            
            if attempt < self.max_retries - 1:
                wait_time = self.backoff_factor ** attempt
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
        
        self.failed_connections += 1
        logger.error(f"All {self.max_retries} connection attempts failed")
        raise last_exception
    
    def get_stats(self) -> dict:
        """Get connection statistics"""
        return {
            "total_attempts": self.connection_attempts,
            "successful_connections": self.successful_connections,
            "failed_connections": self.failed_connections,
            "success_rate": self.successful_connections / max(self.connection_attempts, 1) * 100
        }

def retry_on_failure(max_retries: int = 3, backoff_factor: float = 2.0, timeout: int = 10):
    """
    Decorator to add retry logic to any async function
    
    Usage:
        @retry_on_failure(max_retries=5)
        async def my_api_call():
            # Your API call code here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            manager = ConnectionManager(max_retries, backoff_factor, timeout)
            return await manager.robust_connect(func, *args, **kwargs)
        return wrapper
    return decorator

class APIConnectionManager:
    """
    Specialized connection manager for API calls
    """
    
    def __init__(self):
        self.connection_manager = ConnectionManager(max_retries=5, base_timeout=15)
        self.last_successful_call = None
        self.consecutive_failures = 0
    
    async def make_api_call(self, api_func: Callable, *args, **kwargs) -> Any:
        """
        Make an API call with enhanced error handling
        """
        try:
            result = await self.connection_manager.robust_connect(api_func, *args, **kwargs)
            self.last_successful_call = time.time()
            self.consecutive_failures = 0
            return result
        except Exception as e:
            self.consecutive_failures += 1
            logger.error(f"API call failed (consecutive failures: {self.consecutive_failures}): {str(e)}")
            raise
    
    def is_healthy(self) -> bool:
        """
        Check if the API connection is healthy
        """
        if self.last_successful_call is None:
            return False
        
        # Consider unhealthy if no successful call in the last 5 minutes
        return (time.time() - self.last_successful_call) < 300
    
    def get_health_status(self) -> dict:
        """
        Get detailed health status
        """
        return {
            "is_healthy": self.is_healthy(),
            "last_successful_call": self.last_successful_call,
            "consecutive_failures": self.consecutive_failures,
            "stats": self.connection_manager.get_stats()
        }

# Example usage and testing
if __name__ == "__main__":
    import aiohttp
    import asyncio
    
    async def test_api_call(url: str):
        """Test API call function"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                return await response.json()
    
    async def main():
        # Test the connection manager
        manager = APIConnectionManager()
        
        try:
            # This will automatically retry if it fails
            result = await manager.make_api_call(test_api_call, "https://api.github.com/zen")
            print(f"API call successful: {result}")
            print(f"Health status: {manager.get_health_status()}")
        except Exception as e:
            print(f"API call failed: {e}")
            print(f"Health status: {manager.get_health_status()}")
    
    # Run the test
    # asyncio.run(main())

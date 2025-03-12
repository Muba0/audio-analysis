#apimanager.py

import os
import asyncio
from datetime import datetime
import time
from typing import Optional, Dict

class APIKeyManager:
    def __init__(self):
        self._api_keys = self._load_api_keys()
        self._key_status: Dict[str, Dict] = {}  # Stores key usage status
        self._lock = asyncio.Lock()
        self.USAGE_TIMEOUT = 30  # seconds
        self.MAX_RETRIES = 3  # Maximum retries for obtaining a key
        self.RETRY_DELAY = 2  # Seconds between retries

    def _load_api_keys(self) -> list:
        """Load API keys from environment variables"""
        api_keys = []
        for i in range(0, 9):  # Support up to 9 API keys
            key = os.getenv(f"GOOGLE_API_KEY_{i}")
            if key:
                api_keys.append(key)
        
        if not api_keys:
            raise ValueError("No Google API keys configured")
        return api_keys

    async def _is_key_available(self, api_key: str) -> bool:
        """Check if an API key is available for use"""
        if api_key not in self._key_status:
            return True
        
        last_used = self._key_status[api_key]['last_used']
        if (datetime.now() - last_used).total_seconds() > self.USAGE_TIMEOUT:
            return True
        
        return False

    async def _get_key_by_second_digit(self, second_digit: int) -> Optional[str]:
        """Choose an API key based on the second digit of the current seconds"""
        index = second_digit % len(self._api_keys)  # To avoid index out of range
        selected_key = self._api_keys[index]
        if self._is_key_available(selected_key):
            return selected_key
        return None

    async def get_available_key(self) -> Optional[str]:
        """Get an available key, retrying if needed"""
        retries = 0
        while retries < self.MAX_RETRIES:
            current_time = datetime.now()
            second_digit = current_time.second % 10  # Get the last digit of seconds
            key = await self._get_key_by_second_digit(second_digit)
            
            if key:
                # Mark the key as used
                async with self._lock:
                    self._key_status[key] = {'last_used': datetime.now(), 'in_use': True}
                return key
            retries += 1
            await asyncio.sleep(self.RETRY_DELAY)
        
        return None

    async def release_key(self, api_key: str):
        """Mark an API key as no longer in use"""
        async with self._lock:
            if api_key in self._key_status:
                self._key_status[api_key]['in_use'] = False

    async def wait_for_available_key(self, timeout: int = 60) -> Optional[str]:
        """Wait for an available API key with timeout"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            key = await self.get_available_key()
            if key:
                return key
            await asyncio.sleep(1)
        return None

    def get_key_status(self) -> Dict:
        """Get current status of all API keys"""
        return {
            key: {
                'in_use': self._key_status.get(key, {}).get('in_use', False),
                'last_used': self._key_status.get(key, {}).get('last_used', None)
            }
            for key in self._api_keys
        }

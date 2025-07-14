"""
Duffel API HTTP client with authentication and error handling.
"""
import httpx
import asyncio
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta

from ..config import config


class DuffelAPIError(Exception):
    """Duffel API error exception."""
    
    def __init__(self, error: Any, status_code: Optional[int] = None):
        self.error = error
        self.status_code = status_code
        
        if isinstance(error, dict):
            message = error.get('detail') or error.get('message') or error.get('title') or str(error)
        elif hasattr(error, 'detail'):
            message = error.detail
        else:
            message = str(error)
        
        super().__init__(message)
    
    def __str__(self):
        return f"Duffel API Error: {super().__str__()}"


class DuffelClient:
    """HTTP client for the Duffel API."""
    
    def __init__(self):
        self._client = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with proper configuration."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=config.DUFFEL_BASE_URL,
                timeout=httpx.Timeout(config.REQUEST_TIMEOUT),
                headers=self._get_default_headers()
            )
        return self._client
    
    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for API requests."""
        return {
            "Authorization": f"Bearer {config.DUFFEL_API_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip",
            "Duffel-Version": config.DUFFEL_API_VERSION,
            "User-Agent": "BookedAI-Agent/1.0"
        }
    
    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make GET request to Duffel API."""
        return await self._request("GET", endpoint, params=params)
    
    async def post(self, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make POST request to Duffel API."""
        return await self._request("POST", endpoint, json=data)
    
    async def patch(self, endpoint: str, data: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make PATCH request to Duffel API."""
        return await self._request("PATCH", endpoint, json=json or data)
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        retries: int = 0
    ) -> Dict[str, Any]:
        """Make HTTP request with error handling and retries."""
        try:
            # Remove leading slash if present to avoid double slashes
            endpoint = endpoint.lstrip('/')
            
            response = await self.client.request(
                method=method,
                url=endpoint,
                params=params,
                json=json
            )
            
            # Check for HTTP errors
            if response.status_code >= 400:
                await self._handle_error_response(response)
            
            return response.json()
            
        except httpx.HTTPStatusError as e:
            await self._handle_error_response(e.response)
        except httpx.RequestError as e:
            if retries < config.MAX_RETRIES:
                # Exponential backoff
                delay = 2 ** retries
                await asyncio.sleep(delay)
                return await self._request(method, endpoint, params, json, retries + 1)
            else:
                raise DuffelAPIError(f"Request failed after {config.MAX_RETRIES} retries: {e}")
        except Exception as e:
            raise DuffelAPIError(f"Unexpected error: {e}")
    
    async def _handle_error_response(self, response: httpx.Response) -> None:
        """Handle error responses from the API."""
        try:
            error_data = response.json()
            
            # Duffel API returns errors in a specific format
            if "errors" in error_data:
                errors = error_data["errors"]
                if errors and len(errors) > 0:
                    raise DuffelAPIError(errors[0], response.status_code)
            
            # Fallback error handling
            raise DuffelAPIError({
                "type": "http_error",
                "title": f"HTTP {response.status_code}",
                "detail": error_data.get("message", response.text)
            }, response.status_code)
            
        except Exception:
            # If we can't parse the error response, use status code
            raise DuffelAPIError({
                "type": "http_error",
                "title": f"HTTP {response.status_code}",
                "detail": response.text or "Unknown error"
            }, response.status_code)
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()


# Global client instance
_client: Optional[DuffelClient] = None


def get_client() -> DuffelClient:
    """Get global Duffel client instance."""
    global _client
    if _client is None:
        _client = DuffelClient()
    return _client


def set_client(client: DuffelClient):
    """Set global Duffel client instance."""
    global _client
    _client = client 
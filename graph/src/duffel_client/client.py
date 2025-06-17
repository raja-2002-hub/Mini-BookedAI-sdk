"""
Main HTTP client for Duffel API interactions.
"""
import asyncio
from typing import Dict, Any, Optional, Union
import httpx
from pydantic import ValidationError

from ..config import config
from .models.common import DuffelError, DuffelResponse


class DuffelAPIError(Exception):
    """Exception raised for Duffel API errors."""
    
    def __init__(self, error: DuffelError, status_code: int = None):
        self.error = error
        self.status_code = status_code
        super().__init__(str(error))


class DuffelClient:
    """HTTP client for Duffel API."""
    
    def __init__(self, api_token: str = None, base_url: str = None):
        """Initialize the Duffel client.
        
        Args:
            api_token: Duffel API token. If None, uses config.DUFFEL_API_TOKEN
            base_url: Duffel API base URL. If None, uses config.DUFFEL_BASE_URL
        """
        self.api_token = api_token or config.DUFFEL_API_TOKEN
        self.base_url = base_url or config.DUFFEL_BASE_URL
        
        if not self.api_token:
            raise ValueError("Duffel API token is required")
        
        # Configure HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._get_headers(),
            timeout=config.REQUEST_TIMEOUT,
        )
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Duffel-Version": config.DUFFEL_API_VERSION,
            "User-Agent": "BookedAI-LangGraph/1.0",
        }
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        retries: int = None,
    ) -> Dict[str, Any]:
        """Make a request to the Duffel API with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json_data: JSON body data
            retries: Number of retries (defaults to config.MAX_RETRIES)
            
        Returns:
            Parsed JSON response
            
        Raises:
            DuffelAPIError: For API errors
            httpx.HTTPError: For HTTP errors
        """
        if retries is None:
            retries = config.MAX_RETRIES
        
        last_exception = None
        
        for attempt in range(retries + 1):
            try:
                response = await self.client.request(
                    method=method,
                    url=endpoint,
                    params=params,
                    json=json_data,
                )
                
                # Check for successful response
                if response.is_success:
                    return response.json()
                
                # Handle API errors
                if response.status_code >= 400:
                    try:
                        error_data = response.json()
                        if "errors" in error_data and error_data["errors"]:
                            # Duffel returns errors as a list
                            error_info = error_data["errors"][0]
                            error = DuffelError(**error_info)
                        else:
                            # Generic error
                            error = DuffelError(
                                type="api_error",
                                title=f"HTTP {response.status_code}",
                                detail=response.text or "Unknown error",
                                status=response.status_code
                            )
                        raise DuffelAPIError(error, response.status_code)
                    except (ValidationError, KeyError):
                        # Fallback for unexpected error format
                        error = DuffelError(
                            type="api_error", 
                            title=f"HTTP {response.status_code}",
                            detail=response.text,
                            status=response.status_code
                        )
                        raise DuffelAPIError(error, response.status_code)
                
            except httpx.RequestError as e:
                last_exception = e
                if attempt < retries:
                    # Wait before retrying (exponential backoff)
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise
            except DuffelAPIError:
                # Don't retry API errors (client errors)
                raise
        
        # If we get here, all retries failed
        if last_exception:
            raise last_exception
    
    async def get(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a GET request."""
        return await self._make_request("GET", endpoint, params=params)
    
    async def post(
        self, 
        endpoint: str, 
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a POST request."""
        return await self._make_request("POST", endpoint, params=params, json_data=json_data)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Singleton client instance
_client: Optional[DuffelClient] = None


def get_client() -> DuffelClient:
    """Get or create a singleton Duffel client instance."""
    global _client
    if _client is None:
        _client = DuffelClient()
    return _client


async def close_client():
    """Close the singleton client instance."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None 
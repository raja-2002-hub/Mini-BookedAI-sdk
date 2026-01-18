"""
HTTP Middleware for OAuth Authentication (Optional)

This middleware can be used for traditional HTTP API routes.
For MCP tool calls, use authenticate_mcp_request instead.
"""

from __future__ import annotations

import logging
from typing import Set, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from .clerk_oauth import ClerkOAuthProvider, get_config

log = logging.getLogger("auth_middleware")


@dataclass
class AuthConfig:
    """Configuration for auth middleware."""
    
    public_paths: Set[str] = field(default_factory=lambda: {
        "/",
        "/health",
        "/mcp",
    })
    
    public_prefixes: Set[str] = field(default_factory=lambda: {
        "/.well-known/",
        "/oauth/",
    })
    
    protected_paths: Set[str] = field(default_factory=set)
    protected_prefixes: Set[str] = field(default_factory=lambda: {"/api/"})
    
    path_scopes: Dict[str, List[str]] = field(default_factory=dict)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces authentication on HTTP routes.
    
    Note: For MCP tool authentication, use authenticate_mcp_request instead.
    """
    
    def __init__(
        self,
        app,
        config: Optional[AuthConfig] = None,
        provider: Optional[ClerkOAuthProvider] = None,
    ):
        super().__init__(app)
        self.config = config or AuthConfig()
        self.provider = provider or ClerkOAuthProvider()
        self.clerk_config = get_config()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        # Skip auth if disabled
        if not self.clerk_config.enabled:
            return await call_next(request)
        
        # Check if path is public
        if self._is_public_path(path):
            return await call_next(request)
        
        # Check if path requires auth
        if not self._requires_auth(path):
            return await call_next(request)
        
        # Extract token
        auth_header = request.headers.get("Authorization")
        token = request.query_params.get("access_token")
        
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:]
        
        if not token:
            return self._unauthorized_response("No access token provided")
        
        # Get required scopes for this path
        required_scopes = self.config.path_scopes.get(path)
        
        # Verify token
        result = await self.provider.verify_token(token, required_scopes)
        
        if not result.valid:
            return self._unauthorized_response(
                result.error or "Invalid token",
                required_scopes,
            )
        
        # Attach user to request state
        request.state.user = result.user
        
        return await call_next(request)
    
    def _is_public_path(self, path: str) -> bool:
        if path in self.config.public_paths:
            return True
        for prefix in self.config.public_prefixes:
            if path.startswith(prefix):
                return True
        return False
    
    def _requires_auth(self, path: str) -> bool:
        if path in self.config.protected_paths:
            return True
        for prefix in self.config.protected_prefixes:
            if path.startswith(prefix):
                return True
        return False
    
    def _unauthorized_response(
        self,
        message: str,
        required_scopes: Optional[List[str]] = None,
    ) -> JSONResponse:
        www_authenticate = self.provider.get_www_authenticate_challenge(
            error="invalid_token",
            error_description=message,
            required_scopes=required_scopes,
        )
        
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "message": message},
            headers={"WWW-Authenticate": www_authenticate},
        )
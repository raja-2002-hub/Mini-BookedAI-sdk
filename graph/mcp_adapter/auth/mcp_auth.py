"""
MCP Authentication Helpers for BookedAI

This module provides MCP-specific authentication utilities.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .clerk_oauth import (
    ClerkOAuthProvider,
    ClerkUser,
    TokenVerificationResult,
    verify_clerk_token,
    get_config,
)

log = logging.getLogger("mcp_auth")


# ============================================================================
# Authentication Context
# ============================================================================

@dataclass
class AuthContext:
    """Authentication context for an MCP request."""

    authenticated: bool = False
    user: Optional["ClerkUser"] = None
    token: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

    @property
    def user_id(self) -> Optional[str]:
        """Get the authenticated user's ID."""
        return self.user.user_id if self.user else None

    @property
    def scopes(self) -> List[str]:
        """Expose scopes for logging / adapters."""
        return list(self.user.scopes) if self.user else []

    @property
    def raw_claims(self) -> Dict[str, Any]:
        """Expose raw JWT claims for logging / adapters."""
        return dict(self.user.raw_claims) if self.user else {}

    def has_scope(self, scope: str) -> bool:
        """Check if the user has a specific scope."""
        if not self.user:
            return False
        return self.user.has_scope(scope) or "*" in self.user.scopes


async def authenticate_mcp_request(
    authorization_header: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    required_scopes: Optional[List[str]] = None,
) -> AuthContext:
    """
    Authenticate an MCP request.
    
    Args:
        authorization_header: The Authorization header value
        meta: Optional MCP _meta dictionary
        required_scopes: Scopes required for this request
        
    Returns:
        AuthContext with authentication result
    """
    config = get_config()
    
    # If auth is disabled, return anonymous context
    if not config.enabled:
        return AuthContext(
            authenticated=True,
            user=ClerkUser(user_id="anonymous", scopes=["*"]),
        )
    
    # Extract token
    token = None
    if authorization_header:
        if authorization_header.lower().startswith("bearer "):
            token = authorization_header[7:]
        else:
            token = authorization_header
    
    if not token:
        return AuthContext(
            authenticated=False,
            error="No access token provided",
            error_code="missing_token",
        )
    
    # Verify token
    result = await verify_clerk_token(token, required_scopes=required_scopes)
    
    if result.valid:
        return AuthContext(
            authenticated=True,
            user=result.user,
            token=token,
        )
    else:
        return AuthContext(
            authenticated=False,
            error=result.error,
            error_code=result.error_code,
        )


def create_auth_error_result(
    error: str = "invalid_token",
    error_description: str = "Authentication required",
    scopes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create an MCP tool result that triggers authentication.
    """
    config = get_config()
    resource_metadata_url = f"{config.mcp_server_url}/.well-known/oauth-protected-resource"
    
    www_auth_parts = [
        f'Bearer resource_metadata="{resource_metadata_url}"',
        f'error="{error}"',
        f'error_description="{error_description}"',
    ]
    
    if scopes:
        www_auth_parts.append(f'scope="{" ".join(scopes)}"')
    
    return {
        "content": [
            {
                "type": "text",
                "text": f"Authentication required: {error_description}",
            }
        ],
        "_meta": {
            "mcp/www_authenticate": [", ".join(www_auth_parts)],
        },
        "isError": True,
    }
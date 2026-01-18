# OAuth Authentication Module for BookedAI MCP Server
# Uses Clerk as the OAuth 2.1 provider with Dynamic Client Registration

from .clerk_oauth import (
    ClerkOAuthProvider,
    verify_clerk_token,
    get_user_from_token,
    require_auth,
    get_config,
    ClerkUser,
    TokenVerificationResult,
    AuthenticationError,
    InsufficientScopeError,
)
from .middleware import AuthMiddleware
from .endpoints import (
    oauth_protected_resource_metadata,
    oauth_authorization_server_metadata,
    get_oauth_routes,
)
from .mcp_auth import (
    authenticate_mcp_request,
    AuthContext,
    create_auth_error_result,
)

__all__ = [
    "ClerkOAuthProvider",
    "verify_clerk_token",
    "get_user_from_token",
    "require_auth",
    "get_config",
    "ClerkUser",
    "TokenVerificationResult",
    "AuthenticationError",
    "InsufficientScopeError",
    "AuthMiddleware",
    "oauth_protected_resource_metadata",
    "oauth_authorization_server_metadata",
    "get_oauth_routes",
    "authenticate_mcp_request",
    "AuthContext",
    "create_auth_error_result",
]
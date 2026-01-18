"""
auth.py - Clerk OAuth Authentication Module for MCP Server

This module handles all authentication logic for the MCP server:
- Token verification with Clerk
- User context management
- OAuth discovery endpoints
- Authentication middleware

Usage:
    from auth import register_clerk_oauth, get_current_user, require_auth
    
    # In server.py:
    app = mcp.streamable_http_app()
    register_clerk_oauth(app)
    
    # In tool handlers:
    user = get_current_user()
"""

import os
import logging
import time
from typing import Optional, Dict
import contextvars
from jose import jwt, JWTError
import requests
from dotenv import load_dotenv
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from pathlib import Path

# ✅ ADD THIS SECTION:
from dotenv import load_dotenv

# Load .env from graph folder (parent of mcp_adapter)
OAUTH_FILE = Path(__file__).resolve()
MCP_ADAPTER_DIR = OAUTH_FILE.parent
GRAPH_ROOT = MCP_ADAPTER_DIR.parent
ENV_FILE = GRAPH_ROOT / ".env"

# Load environment variables
load_dotenv(ENV_FILE)

import os  # Import again after load_dotenv to ensure it's available
# ============================================================================
# CONFIGURATION
# ============================================================================

CLERK_SECRET_KEY = "sk_test_hygxtbWCctq53nqzaxV98lxazWPDUPmC4V3mWPIqCU"
CLERK_PUBLISHABLE_KEY = "pk_test_bW9yZS10dXJ0bGUtOTUuY2xlcmsuYWNjb3VudHMuZGV2JA"
CLERK_DOMAIN = "more-turtle-95.clerk.accounts.dev"
CLERK_JWKS_URL = "https://more-turtle-95.clerk.accounts.dev/.well-known/jwks.json"
MCP_SERVER_URL = "https://maryalice-vitrifiable-ross.ngrok-free.dev"

# Validate configuration
if not CLERK_SECRET_KEY or not CLERK_DOMAIN:
    logging.warning("⚠️ Clerk OAuth not configured - authentication disabled")
    CLERK_ENABLED = False
else:
    CLERK_ENABLED = True
    logging.info(f"✅ Clerk OAuth enabled for domain: {CLERK_DOMAIN}")

# Context variable to pass user info from HTTP layer to MCP layer
user_context_var = contextvars.ContextVar('user_context', default=None)

# Cache for Clerk's public keys (1 hour cache)
_clerk_jwks_cache = None
_clerk_jwks_cache_time = 0


# ============================================================================
# TOKEN VERIFICATION
# ============================================================================

def get_clerk_jwks() -> Optional[Dict]:
    """
    Fetch Clerk's public keys for JWT verification.
    Cached for 1 hour to reduce API calls.
    
    Returns:
        Dict with JWKS keys or None if failed
    """
    global _clerk_jwks_cache, _clerk_jwks_cache_time
    
    current_time = time.time()
    
    # Return cached if less than 1 hour old
    if _clerk_jwks_cache and (current_time - _clerk_jwks_cache_time) < 3600:
        logging.debug("Using cached JWKS")
        return _clerk_jwks_cache
    
    try:
        logging.info(f"📡 Fetching JWKS from {CLERK_JWKS_URL}")
        response = requests.get(CLERK_JWKS_URL, timeout=5)
        response.raise_for_status()
        
        _clerk_jwks_cache = response.json()
        _clerk_jwks_cache_time = current_time
        
        num_keys = len(_clerk_jwks_cache.get('keys', []))
        logging.info(f"✅ JWKS fetched successfully ({num_keys} keys)")
        return _clerk_jwks_cache
        
    except requests.RequestException as e:
        logging.error(f"❌ Failed to fetch JWKS: {e}")
        return None
    except Exception as e:
        logging.error(f"❌ Unexpected error fetching JWKS: {e}")
        return None


def verify_clerk_token(token: str) -> Optional[Dict]:
    """
    Verify JWT token from Clerk OAuth.
    
    Args:
        token: JWT token string from Authorization header
    
    Returns:
        User info dict if valid:
        {
            "user_id": "user_abc123",
            "email": "user@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "full_name": "John Doe",
            "email_verified": "true",
            "verified": True
        }
        
        Returns None if token is invalid.
    """
    if not CLERK_ENABLED:
        logging.debug("Clerk OAuth disabled, skipping verification")
        return None
    
    try:
        # Get Clerk's public keys
        jwks = get_clerk_jwks()
        if not jwks:
            logging.error("Cannot verify token: JWKS not available")
            return None
        
        # Decode token header to get key ID
        unverified_header = jwt.get_unverified_header(token)
        key_id = unverified_header.get("kid")
        
        if not key_id:
            logging.error("Token missing 'kid' in header")
            return None
        
        # Find matching public key
        signing_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == key_id:
                signing_key = key
                break
        
        if not signing_key:
            logging.error(f"Key ID {key_id} not found in JWKS")
            return None
        
        # Verify and decode token
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=MCP_SERVER_URL,
            issuer=f"https://{CLERK_DOMAIN}"
        )
        
        # Extract user information
        # Note: Clerk auto-includes 'sub' (user ID) even if not in custom template
        user_info = {
            "user_id": payload.get("sub") or payload.get("user_id"),
            "email": payload.get("email"),
            "first_name": payload.get("first_name"),
            "last_name": payload.get("last_name"),
            "full_name": payload.get("full_name"),
            "email_verified": payload.get("email_verified"),
            "created_at": payload.get("created_at"),
            "verified": True,
            "token_issued_at": payload.get("iat"),
            "token_expires_at": payload.get("exp")
        }
        
        logging.info(f"✅ Token verified for user: {user_info['email']} (ID: {user_info['user_id']})")
        return user_info
        
    except jwt.ExpiredSignatureError:
        logging.warning("❌ Token has expired")
        return None
    except jwt.JWTClaimsError as e:
        logging.error(f"❌ Invalid token claims: {e}")
        return None
    except JWTError as e:
        logging.error(f"❌ JWT verification failed: {e}")
        return None
    except Exception as e:
        logging.error(f"❌ Unexpected error verifying token: {e}")
        import traceback
        logging.debug(traceback.format_exc())
        return None


# ============================================================================
# AUTHENTICATION MIDDLEWARE
# ============================================================================

class ClerkAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and verify Clerk OAuth token from requests.
    Stores user info in context variable for access in tool handlers.
    """
    
    # Paths that should skip authentication (discovery, health checks)
    SKIP_AUTH_PATHS = {
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
        "/.well-known/openid-configuration",
        "/success",
        "/cancel",
        "/stripe/webhook",
    }
    
    async def dispatch(self, request: Request, call_next):
        """
        Process each request:
        1. Skip auth for discovery endpoints
        2. Extract Authorization header
        3. Verify token with Clerk
        4. Store user info in context
        5. Continue processing
        """
        path = request.url.path
        
        # Skip auth for discovery and webhook endpoints
        if path in self.SKIP_AUTH_PATHS or path.startswith("/.well-known/"):
            return await call_next(request)
        
        # Extract Authorization header
        auth_header = request.headers.get("Authorization", "")
        
        user_info = None
        
        if auth_header.startswith("Bearer "):
            # Extract token
            token = auth_header.replace("Bearer ", "").strip()
            
            # Verify token with Clerk
            user_info = verify_clerk_token(token)
            
            if user_info:
                # Store in context variable (available in all async code)
                user_context_var.set(user_info)
                logging.info(f"🔐 Authenticated request from: {user_info['email']}")
            else:
                logging.warning("⚠️ Invalid or expired OAuth token")
        else:
            logging.debug(f"ℹ️ No authentication token for path: {path}")
        
        # Continue processing request (don't block unauthenticated requests)
        response = await call_next(request)
        
        return response
# ============================================================================
# OAUTH DISCOVERY ENDPOINTS
# ============================================================================

async def oauth_protected_resource(request: Request):
    """
    Protected resource metadata endpoint.
    Required by OpenAI Apps SDK for OAuth discovery.
    
    Tells ChatGPT where to find the OAuth authorization server (Clerk).
    """
    return JSONResponse({
        "resource": MCP_SERVER_URL,
        "authorization_servers": [f"https://{CLERK_DOMAIN}"]
    })


async def oauth_openid_configuration(request: Request):
    """
    OpenID Connect configuration endpoint.
    Points ChatGPT to Clerk's OAuth endpoints.
    
    This allows ChatGPT to discover how to perform the OAuth flow.
    """
    return JSONResponse({
        "issuer": f"https://{CLERK_DOMAIN}",
        "authorization_endpoint": f"https://{CLERK_DOMAIN}/oauth/authorize",
        "token_endpoint": f"https://{CLERK_DOMAIN}/oauth/token",
        "jwks_uri": CLERK_JWKS_URL,
        "userinfo_endpoint": f"https://{CLERK_DOMAIN}/oauth/userinfo",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"]
    })


# ============================================================================
# REGISTRATION FUNCTION
# ============================================================================

def register_clerk_oauth(mcp_app):
    """
    Register Clerk OAuth with your FastMCP application.
    
    NOTE: OAuth discovery routes are registered manually in Server_F.py
    This function only registers middleware.
    """
    print("=" * 60)
    print("🔧 register_clerk_oauth() CALLED")
    print("=" * 60)
    
    from starlette.middleware.cors import CORSMiddleware
    
    # Add CORS middleware
    mcp_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    print("✅ CORS middleware registered")
    
    # Add authentication middleware
    mcp_app.add_middleware(ClerkAuthMiddleware)
    print("✅ Clerk authentication middleware registered")
    
    # NOTE: Routes are registered manually in Server_F.py at the end
    # because FastMCP handles routing differently
    
    print("=" * 60)
    print("🎉 Clerk OAuth middleware configured!")
    print(f"📍 Server: {MCP_SERVER_URL}")
    print(f"🔐 Auth Provider: https://{CLERK_DOMAIN}")
    print("=" * 60)

# ============================================================================
# HELPER FUNCTIONS (Public API)
# ============================================================================

def get_current_user() -> Optional[Dict]:
    """
    Get the currently authenticated user from context.
    
    Returns:
        User info dict if authenticated:
        {
            "user_id": str,
            "email": str,
            "first_name": str,
            "last_name": str,
            "full_name": str,
            "email_verified": str,
            "verified": bool
        }
        
        Returns None if not authenticated.
    
    Usage in tool handlers:
        from auth import get_current_user
        
        user = get_current_user()
        if user:
            user_id = user["user_id"]
            email = user["email"]
            print(f"Tool called by {email}")
    """
    return user_context_var.get()


def is_authenticated() -> bool:
    """
    Check if current request is authenticated.
    
    Returns:
        True if user is authenticated, False otherwise
    
    Usage:
        from auth import is_authenticated
        
        if is_authenticated():
            # Do authenticated action
        else:
            # Return error or public data
    """
    return get_current_user() is not None


def require_auth(func):
    """
    Decorator to require authentication for a function.
    Returns error if user is not authenticated.
    
    Args:
        func: Async function to wrap
    
    Returns:
        Wrapped function that checks authentication
    
    Usage:
        from auth import require_auth, get_current_user
        
        @require_auth
        async def protected_tool_handler(args):
            user = get_current_user()
            # user is guaranteed to exist here
            return f"Hello {user['email']}"
    """
    from functools import wraps
    
    @wraps(func)
    async def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            # Return authentication error
            from mcp.types import ServerResult, CallToolResult, TextContent
            return ServerResult(CallToolResult(
                content=[TextContent(
                    type="text",
                    text="🔒 Authentication required. Please connect your account to use this feature."
                )],
                isError=True
            ))
        return await func(*args, **kwargs)
    
    return wrapper


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'register_clerk_oauth',
    'get_current_user',
    'is_authenticated',
    'require_auth',
    'CLERK_ENABLED',
    'MCP_SERVER_URL',
]

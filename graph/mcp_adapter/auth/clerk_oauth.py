"""
Clerk OAuth Provider for BookedAI MCP Server

This module implements OAuth 2.1 authentication using Clerk as the identity provider.
It handles:
- JWT token verification using Clerk's JWKS
- User identity extraction from tokens
- Token scope validation
- Dynamic client registration support
- User info fetching from /oauth/userinfo endpoint
"""

from __future__ import annotations

import os
import json
import logging
from functools import wraps
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timezone
import asyncio
import httpx
from jose import jwt, jwk, JWTError
from jose.exceptions import JWKError

log = logging.getLogger("clerk_oauth")


# ============================================================================
# Custom Exceptions
# ============================================================================

class AuthenticationError(Exception):
    """Raised when authentication fails."""
    def __init__(self, message: str, error_code: str = "authentication_failed"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class InsufficientScopeError(AuthenticationError):
    """Raised when user lacks required scopes."""
    def __init__(self, required_scopes: List[str], user_scopes: List[str]):
        self.required_scopes = required_scopes
        self.user_scopes = user_scopes
        missing = set(required_scopes) - set(user_scopes)
        message = f"Missing required scopes: {', '.join(missing)}"
        super().__init__(message, "insufficient_scope")


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class ClerkConfig:
    """Clerk OAuth configuration loaded from environment variables."""
    
    # Clerk identifiers
    publishable_key: str = field(default_factory=lambda: os.getenv("CLERK_PUBLISHABLE_KEY", ""))
    secret_key: str = field(default_factory=lambda: os.getenv("CLERK_SECRET_KEY", ""))
    client_secret: str = field(default_factory=lambda: os.getenv("CLERK_CLIENT_SECRET", ""))
    domain: str = field(default_factory=lambda: os.getenv("CLERK_DOMAIN", ""))
    
    # OAuth endpoints
    jwks_url: str = field(default_factory=lambda: os.getenv("CLERK_JWKS_URL", ""))
    discovery_url: str = field(default_factory=lambda: os.getenv("CLERK_DISCOVERY_URL", ""))
    
    # MCP Server configuration
    mcp_server_url: str = field(default_factory=lambda: os.getenv("MCP_SERVER_URL", "http://localhost:8000"))
    
    # Feature flags
    enabled: bool = field(default_factory=lambda: os.getenv("CLERK_ENABLED", "true").lower() == "true")
    
    def __post_init__(self):
        """Derive missing URLs from domain if not explicitly set."""
        if self.domain and not self.jwks_url:
            self.jwks_url = f"https://{self.domain}/.well-known/jwks.json"
        if self.domain and not self.discovery_url:
            self.discovery_url = f"https://{self.domain}/.well-known/openid-configuration"
    
    @property
    def authorization_server_url(self) -> str:
        """Get the authorization server base URL."""
        return f"https://{self.domain}" if self.domain else ""
    
    @property
    def userinfo_url(self) -> str:
        """Get the userinfo endpoint URL."""
        return f"https://{self.domain}/oauth/userinfo" if self.domain else ""
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of missing required fields."""
        missing = []
        if not self.publishable_key:
            missing.append("CLERK_PUBLISHABLE_KEY")
        if not self.secret_key:
            missing.append("CLERK_SECRET_KEY")
        if not self.domain:
            missing.append("CLERK_DOMAIN")
        return missing


# Global configuration instance
_config: Optional[ClerkConfig] = None


def get_config() -> ClerkConfig:
    """Get or create the global Clerk configuration."""
    global _config
    if _config is None:
        _config = ClerkConfig()
    return _config


# ============================================================================
# JWKS Cache for Token Verification
# ============================================================================

@dataclass
class JWKSCache:
    """Caches JWKS keys to avoid fetching on every request."""
    
    keys: Dict[str, Any] = field(default_factory=dict)
    last_fetched: Optional[datetime] = None
    cache_duration_seconds: int = 3600  # 1 hour default
    
    def is_expired(self) -> bool:
        """Check if the cache has expired."""
        if self.last_fetched is None:
            return True
        elapsed = (datetime.now(timezone.utc) - self.last_fetched).total_seconds()
        return elapsed > self.cache_duration_seconds
    
    def get_key(self, kid: str) -> Optional[Dict[str, Any]]:
        """Get a key by its ID."""
        return self.keys.get(kid)
    
    def update(self, keys_data: List[Dict[str, Any]]):
        """Update the cache with new keys."""
        self.keys = {k.get("kid"): k for k in keys_data if k.get("kid")}
        self.last_fetched = datetime.now(timezone.utc)


# Global JWKS cache
_jwks_cache = JWKSCache()


async def fetch_jwks(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetch JWKS from Clerk's well-known endpoint.
    
    Args:
        force_refresh: Force a refresh even if cache is valid
        
    Returns:
        Dictionary mapping key IDs to their key data
    """
    global _jwks_cache
    
    config = get_config()
    
    if not force_refresh and not _jwks_cache.is_expired():
        return _jwks_cache.keys
    
    if not config.jwks_url:
        raise ValueError("CLERK_JWKS_URL is not configured")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(config.jwks_url)
            response.raise_for_status()
            data = response.json()
            
            keys = data.get("keys", [])
            _jwks_cache.update(keys)
            log.info(f"Fetched {len(keys)} JWKS keys from Clerk")
            
            return _jwks_cache.keys
            
    except httpx.HTTPError as e:
        log.error(f"Failed to fetch JWKS: {e}")
        # Return cached keys if available
        if _jwks_cache.keys:
            log.warning("Using stale JWKS cache due to fetch failure")
            return _jwks_cache.keys
        raise


# ============================================================================
# User Info Endpoint (NEW)
# ============================================================================

async def fetch_user_info(access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch additional user information from Clerk's /oauth/userinfo endpoint.
    
    This is necessary because OAuth access tokens don't include custom claims
    by default - they only contain sub, iss, aud, exp, iat, nbf.
    
    The /oauth/userinfo endpoint returns:
    - email
    - email_verified  
    - given_name (first name)
    - family_name (last name)
    - name (full name)
    - And other profile information based on granted scopes
    
    Args:
        access_token: The validated OAuth access token
    
    Returns:
        Dict with user info, or None if request fails
    """
    config = get_config()
    userinfo_url = config.userinfo_url
    
    if not userinfo_url:
        log.warning("Userinfo URL not configured, skipping userinfo fetch")
        return None
    
    try:
        log.info(f"🔍 Fetching user info from: {userinfo_url}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                userinfo_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                }
            )
            
            if response.status_code == 200:
                user_info = response.json()
                log.info("✅ Successfully fetched user info from /oauth/userinfo")
                log.info("=" * 80)
                log.info("🔍 USER INFO FROM /oauth/userinfo:")
                log.info("=" * 80)
                for key, value in user_info.items():
                    log.info(f"   {key}: {value}")
                log.info("=" * 80)
                return user_info
            else:
                log.error(f"❌ Failed to fetch user info: {response.status_code}")
                log.error(f"Response: {response.text}")
                return None
                
    except Exception as e:
        log.error(f"❌ Exception fetching user info: {e}")
        return None


# ============================================================================
# User Data Model
# ============================================================================

@dataclass
class ClerkUser:
    """Represents an authenticated Clerk user."""
    
    user_id: str
    email: Optional[str] = None
    email_verified: bool = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    profile_image_url: Optional[str] = None
    public_metadata: Dict[str, Any] = field(default_factory=dict)
    private_metadata: Dict[str, Any] = field(default_factory=dict)
    scopes: List[str] = field(default_factory=list)
    raw_claims: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def full_name(self) -> str:
        """Get the user's full name."""
        parts = [self.first_name, self.last_name]
        return " ".join(p for p in parts if p) or self.username or self.email or self.user_id
    
    @property
    def display_name(self) -> str:
        """Get a display-friendly name."""
        return self.first_name or self.username or self.email or self.user_id
    
    def has_scope(self, scope: str) -> bool:
        """Check if the user has a specific scope."""
        return scope in self.scopes
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "email_verified": self.email_verified,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "username": self.username,
            "profile_image_url": self.profile_image_url,
            "public_metadata": self.public_metadata,
            "scopes": self.scopes,
        }


# ============================================================================
# Token Verification
# ============================================================================

@dataclass
class TokenVerificationResult:
    """Result of token verification."""
    
    valid: bool
    user: Optional[ClerkUser] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    @classmethod
    def success(cls, user: ClerkUser) -> "TokenVerificationResult":
        return cls(valid=True, user=user)
    
    @classmethod
    def failure(cls, error: str, error_code: str = "invalid_token") -> "TokenVerificationResult":
        return cls(valid=False, error=error, error_code=error_code)


async def verify_clerk_token(
    token: str,
    required_scopes: Optional[List[str]] = None,
    verify_audience: bool = False,  # ✅ Changed for ChatGPT MCP compatibility
) -> TokenVerificationResult:
    """
    Verify a Clerk JWT access token and fetch additional user information.
    
    Steps:
    1. Validate JWT signature using JWKS
    2. Verify expiration and basic claims
    3. Fetch additional user data from /oauth/userinfo endpoint
    4. Merge JWT claims with userinfo data
    
    Args:
        token: The JWT access token to verify
        required_scopes: List of scopes that must be present
        verify_audience: Whether to verify the audience claim (disabled for ChatGPT MCP)
        
    Returns:
        TokenVerificationResult with user data if valid
    """
    config = get_config()
    
    if not config.enabled:
        # Auth disabled - return anonymous user
        return TokenVerificationResult.success(ClerkUser(
            user_id="anonymous",
            scopes=["*"],
        ))
    
    if not token:
        return TokenVerificationResult.failure(
            "No access token provided",
            "missing_token"
        )
    
    # Strip "Bearer " prefix if present
    if token.lower().startswith("bearer "):
        token = token[7:]
    
    try:
        # Decode header to get key ID
        try:
            unverified_header = jwt.get_unverified_header(token)
        except JWTError as e:
            return TokenVerificationResult.failure(
                f"Invalid token format: {e}",
                "invalid_format"
            )
        
        kid = unverified_header.get("kid")
        if not kid:
            return TokenVerificationResult.failure(
                "Token missing key ID (kid)",
                "missing_kid"
            )
        
        # Fetch JWKS and get the signing key
        keys = await fetch_jwks()
        key_data = keys.get(kid)
        
        if not key_data:
            # Try refreshing keys in case of key rotation
            keys = await fetch_jwks(force_refresh=True)
            key_data = keys.get(kid)
        
        if not key_data:
            return TokenVerificationResult.failure(
                f"Unknown signing key: {kid}",
                "unknown_key"
            )
        
        # Convert to RSA public key
        try:
            public_key = jwk.construct(key_data)
        except JWKError as e:
            return TokenVerificationResult.failure(
                f"Invalid key format: {e}",
                "invalid_key"
            )
        
        # ✅ Build verification options - relaxed for ChatGPT MCP
        options = {
            "verify_signature": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iat": True,
            "verify_aud": False,  # ✅ Don't verify audience for ChatGPT MCP
        }
        
        # ✅ Don't check audience for ChatGPT MCP compatibility
        audience = None
        
        # ✅ Decode and verify the token - removed issuer check for ChatGPT MCP
        try:
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                # ✅ Removed audience and issuer checks for ChatGPT MCP compatibility
                options=options,
            )
        except jwt.ExpiredSignatureError:
            return TokenVerificationResult.failure(
                "Token has expired",
                "expired"
            )
        except jwt.JWTClaimsError as e:
            return TokenVerificationResult.failure(
                f"Invalid token claims: {e}",
                "invalid_claims"
            )
        except JWTError as e:
            return TokenVerificationResult.failure(
                f"Token verification failed: {e}",
                "verification_failed"
            )
        
        # Log JWT claims for debugging
        log.info("=" * 80)
        log.info("🔍 JWT CLAIMS DECODED:")
        log.info("=" * 80)
        for key, value in claims.items():
            log.info(f"   {key}: {value}")
        log.info("=" * 80)
        
        # ✅ NEW: Fetch additional user info from /oauth/userinfo
        user_info = await fetch_user_info(token)
        
        # ✅ NEW: Merge JWT claims with userinfo data
        if user_info:
            # Userinfo takes precedence for profile data
            merged_claims = {**claims, **user_info}
            log.info("✅ Merged JWT claims with userinfo data")
        else:
            log.warning("⚠️ Could not fetch userinfo, using JWT claims only")
            merged_claims = claims
        
        # Extract user information from merged claims
        user = _extract_user_from_claims(merged_claims)
        
        # Verify required scopes
        if required_scopes:
            missing_scopes = set(required_scopes) - set(user.scopes)
            if missing_scopes and "*" not in user.scopes:
                return TokenVerificationResult.failure(
                    f"Missing required scopes: {', '.join(missing_scopes)}",
                    "insufficient_scope"
                )
        
        return TokenVerificationResult.success(user)
        
    except Exception as e:
        log.error(f"Unexpected error during token verification: {e}")
        return TokenVerificationResult.failure(
            f"Token verification error: {e}",
            "server_error"
        )


def _extract_user_from_claims(claims: Dict[str, Any]) -> ClerkUser:
    """
    Extract user information from claims (JWT + userinfo merged).
    
    This works with BOTH JWT claims AND userinfo endpoint data.
    """
    
    # Clerk uses 'sub' for user ID
    user_id = claims.get("sub") or claims.get("user_id") or ""
    
    # Email might be in different places
    email = (
        claims.get("email") or 
        claims.get("email_address") or
        claims.get("primary_email_address")
    )
    email_verified = claims.get("email_verified", False)
    
    # Name fields
    first_name = claims.get("first_name") or claims.get("given_name")
    last_name = claims.get("last_name") or claims.get("family_name")
    username = claims.get("username") or claims.get("preferred_username")
    
    # Profile image
    profile_image_url = claims.get("profile_image_url") or claims.get("picture")
    
    # Metadata
    public_metadata = claims.get("public_metadata", {})
    private_metadata = claims.get("private_metadata", {})
    
    # Scopes - might be space-separated string or list
    scope_claim = claims.get("scope") or claims.get("scopes") or ""
    if isinstance(scope_claim, str):
        scopes = scope_claim.split() if scope_claim else []
    elif isinstance(scope_claim, list):
        scopes = scope_claim
    else:
        scopes = []
    
    # Add default scopes based on what's in the token
    if email:
        scopes = list(set(scopes) | {"email"})
    if first_name or last_name:
        scopes = list(set(scopes) | {"profile"})
    
    log.info("=" * 80)
    log.info("👤 EXTRACTED USER DATA:")
    log.info("=" * 80)
    log.info(f"   User ID: {user_id}")
    log.info(f"   Email: {email}")
    log.info(f"   Email Verified: {email_verified}")
    log.info(f"   First Name: {first_name}")
    log.info(f"   Last Name: {last_name}")
    log.info(f"   Scopes: {scopes}")
    log.info("=" * 80)
    
    return ClerkUser(
        user_id=user_id,
        email=email,
        email_verified=email_verified,
        first_name=first_name,
        last_name=last_name,
        username=username,
        profile_image_url=profile_image_url,
        public_metadata=public_metadata,
        private_metadata=private_metadata,
        scopes=scopes,
        raw_claims=claims,
    )


# ============================================================================
# Convenience Functions
# ============================================================================

async def get_user_from_token(token: str) -> Optional[ClerkUser]:
    """
    Get user from token, returning None if invalid.
    
    This is a convenience wrapper around verify_clerk_token.
    """
    result = await verify_clerk_token(token)
    return result.user if result.valid else None


def require_auth(scopes: Optional[List[str]] = None):
    """
    Decorator to require authentication for a function.
    
    Usage:
        @require_auth(scopes=["bookings:read"])
        async def get_bookings(user: ClerkUser):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Look for token in kwargs
            token = kwargs.pop("_token", None) or kwargs.pop("token", None)
            
            if not token:
                raise AuthenticationError("No authentication token provided")
            
            result = await verify_clerk_token(token, required_scopes=scopes)
            
            if not result.valid:
                raise AuthenticationError(
                    result.error or "Authentication failed",
                    result.error_code or "invalid_token"
                )
            
            # Inject user into kwargs
            kwargs["user"] = result.user
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# ============================================================================
# OAuth Provider Class
# ============================================================================

class ClerkOAuthProvider:
    """
    Main OAuth provider class for Clerk integration.
    
    This class provides methods for:
    - Token verification
    - Protected resource metadata generation
    - WWW-Authenticate header generation
    """
    
    def __init__(self):
        self.config = get_config()
    
    async def verify_token(
        self,
        token: str,
        required_scopes: Optional[List[str]] = None,
    ) -> TokenVerificationResult:
        """Verify an access token."""
        return await verify_clerk_token(token, required_scopes)
    
    def get_protected_resource_metadata(self) -> Dict[str, Any]:
        """
        Generate OAuth Protected Resource Metadata (RFC 9728).
        
        This is served at /.well-known/oauth-protected-resource
        """
        return {
            "resource": self.config.mcp_server_url,
            "authorization_servers": [self.config.authorization_server_url],
            "scopes_supported": [
                "openid",
                "profile",
                "email",
                "public_metadata",
                "private_metadata",
                "flights:read",
                "flights:write",
                "hotels:read",
                "hotels:write",
                "bookings:read",
                "bookings:write",
            ],
            "bearer_methods_supported": ["header"],
            "resource_documentation": f"{self.config.mcp_server_url}/docs",
        }
    
    def get_www_authenticate_challenge(
        self,
        error: Optional[str] = None,
        error_description: Optional[str] = None,
        required_scopes: Optional[List[str]] = None,
    ) -> str:
        """
        Build a WWW-Authenticate header value.
        
        This header triggers the OAuth flow in ChatGPT when returned
        with a 401 response.
        """
        resource_metadata_url = f"{self.config.mcp_server_url}/.well-known/oauth-protected-resource"
        
        parts = [f'Bearer resource_metadata="{resource_metadata_url}"']
        
        if error:
            parts.append(f'error="{error}"')
        if error_description:
            parts.append(f'error_description="{error_description}"')
        if required_scopes:
            parts.append(f'scope="{" ".join(required_scopes)}"')
        
        return ", ".join(parts)
"""
OAuth Endpoints for BookedAI MCP Server - FIXED FOR CHATGPT MCP
"""

from __future__ import annotations

import os
import logging
import secrets
import httpx
from urllib.parse import urlencode, parse_qs, urlparse
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, RedirectResponse
from starlette.routing import Route

from .clerk_oauth import ClerkOAuthProvider, get_config

log = logging.getLogger("oauth_endpoints")

# In-memory store for OAuth state (use Redis in production)
OAUTH_STATE_STORE: dict[str, dict] = {}

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")


# ============================================================================
# Protected Resource Metadata (RFC 9728)
# ============================================================================

async def oauth_protected_resource_metadata(request: Request) -> JSONResponse:
    """
    Serve the OAuth Protected Resource Metadata document.
    """
    provider = ClerkOAuthProvider()
    metadata = provider.get_protected_resource_metadata()
    
    return JSONResponse(
        content=metadata,
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=3600",
        },
    )


# ============================================================================
# Authorization Server Metadata
# ============================================================================

async def oauth_authorization_server_metadata(request: Request) -> Response:
    """
    Return OAuth Authorization Server Metadata.
    
    Points to OUR endpoints to intercept the OAuth flow.
    """
    config = get_config()
    
    # Fetch Clerk's metadata to get some base values
    clerk_metadata = {}
    if config.discovery_url:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(config.discovery_url)
                if response.status_code == 200:
                    clerk_metadata = response.json()
        except Exception as e:
            log.warning(f"Could not fetch Clerk metadata: {e}")
    
    # Build metadata pointing to OUR endpoints
    metadata = {
        "issuer": PUBLIC_BASE_URL,
        "authorization_endpoint": f"{PUBLIC_BASE_URL}/oauth/authorize",
        "token_endpoint": f"{PUBLIC_BASE_URL}/oauth/callback",  # ← Point to callback for ChatGPT MCP
        "registration_endpoint": f"{PUBLIC_BASE_URL}/oauth/register",
        "jwks_uri": f"{PUBLIC_BASE_URL}/.well-known/jwks.json",
        "scopes_supported": ["openid", "profile", "email", "bookings:read", "bookings:write"],
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic", "none"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "subject_types_supported": clerk_metadata.get("subject_types_supported", ["public"]),
    }
    
    return JSONResponse(
        content=metadata,
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=3600",
        },
    )


# ============================================================================
# OAuth Authorization Endpoint
# ============================================================================

async def oauth_authorize(request: Request) -> Response:
    """
    OAuth 2.0 Authorization Endpoint.
    
    ChatGPT redirects users here to authenticate.
    We capture params, then redirect to Clerk for actual auth.
    """
    config = get_config()
    
    # Extract OAuth params from ChatGPT's request
    client_id = request.query_params.get("client_id", "")
    redirect_uri = request.query_params.get("redirect_uri", "")
    state = request.query_params.get("state", "")
    scope = request.query_params.get("scope", "openid profile email")
    response_type = request.query_params.get("response_type", "code")
    code_challenge = request.query_params.get("code_challenge", "")
    code_challenge_method = request.query_params.get("code_challenge_method", "")
    
    log.info("=" * 80)
    log.info("🔐 OAuth authorization request from ChatGPT")
    log.info("=" * 80)
    log.info(f"  client_id: {client_id}")
    log.info(f"  redirect_uri: {redirect_uri}")
    log.info(f"  state: {state}")
    log.info(f"  scope: {scope}")
    
    # Generate an internal state to track this flow
    internal_state = secrets.token_urlsafe(32)
    
    # Store the original OAuth params
    OAUTH_STATE_STORE[internal_state] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "original_state": state,
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
    }
    
    # Build the redirect to Clerk's authorization endpoint
    clerk_auth_url = f"https://{config.domain}/oauth/authorize"
    
    params = {
    "client_id": config.publishable_key,
    "redirect_uri": f"{PUBLIC_BASE_URL}/oauth/callback",
    "response_type": "code",
    "scope": scope,  # ✅ forward what ChatGPT asked for
    "state": internal_state,
   }

    
    # Add PKCE if provided
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = code_challenge_method or "S256"
    
    clerk_redirect = f"{clerk_auth_url}?{urlencode(params)}"
    
    log.info(f"↪️  Redirecting to Clerk for authentication")
    log.info("=" * 80)
    
    return RedirectResponse(clerk_redirect, status_code=302)


# ============================================================================
# OAuth Callback Endpoint - FIXED FOR CHATGPT MCP
# ============================================================================

async def oauth_callback(request: Request) -> Response:
    """
    OAuth 2.0 Callback from Clerk - FIXED for ChatGPT MCP.
    
    ChatGPT MCP expects a direct JSON response with the token,
    NOT a redirect back with an authorization code.
    """
    
    config = get_config()
    
    # Get params from Clerk's callback
    code = request.query_params.get("code", "")
    internal_state = request.query_params.get("state", "")
    error = request.query_params.get("error", "")
    error_description = request.query_params.get("error_description", "")
    
    log.info("=" * 80)
    log.info("🔐 OAuth callback received from Clerk")
    log.info("=" * 80)
    log.info(f"  code: {code[:20]}..." if code else "  code: (none)")
    log.info(f"  internal_state: {internal_state}")
    log.info(f"  error: {error}")
    
    # Retrieve the stored OAuth params
    stored = OAUTH_STATE_STORE.pop(internal_state, None)
    
    if not stored:
        log.error(f"❌ Unknown or expired state: {internal_state}")
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_state", "error_description": "Unknown or expired state"},
        )
    
    # If Clerk returned an error
    if error:
        log.warning(f"❌ Clerk returned error: {error} - {error_description}")
        return JSONResponse(
            status_code=400,
            content={"error": error, "error_description": error_description},
        )
    
    if not code:
        log.error("❌ No code received from Clerk")
        return JSONResponse(
            status_code=400,
            content={"error": "server_error", "error_description": "No authorization code received"},
        )
    
    # Exchange Clerk's code for tokens (server-to-server)
    log.info("🔄 Exchanging Clerk code for tokens...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                f"https://{config.domain}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": f"{PUBLIC_BASE_URL}/oauth/callback",
                    "client_id": config.publishable_key,
                    "client_secret": config.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            
            if token_response.status_code != 200:
                log.error(f"❌ Token exchange failed: {token_response.status_code}")
                log.error(f"   Response: {token_response.text}")
                return JSONResponse(
                    status_code=400,
                    content={"error": "server_error", "error_description": "Token exchange failed"},
                )
            
            tokens = token_response.json()
            log.info("✅ Token exchange successful")
            log.info(f"   Access token: {tokens.get('access_token', '')[:20]}...")
            
    except Exception as e:
        log.exception(f"❌ Token exchange error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "server_error", "error_description": "Authentication failed"},
        )
    
    # ============================================================================
    # CRITICAL FIX: Return token directly to ChatGPT MCP as JSON
    # ============================================================================
    
    access_token = tokens.get("access_token")
    expires_in = tokens.get("expires_in", 3600)
    refresh_token = tokens.get("refresh_token")
    id_token = tokens.get("id_token")
    
    # Build the response ChatGPT MCP expects
    response_data = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
    }
    
    # Add optional tokens if present
    if refresh_token:
        response_data["refresh_token"] = refresh_token
    
    if id_token:
        response_data["id_token"] = id_token
    
    # Add scope if it was in the original request
    if stored.get("scope"):
        response_data["scope"] = stored["scope"]
    
    log.info("📤 Returning token directly to ChatGPT MCP")
    log.info(f"   Token type: Bearer")
    log.info(f"   Expires in: {expires_in}s")
    log.info("=" * 80)
    
    return JSONResponse(
        content=response_data,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )


# ============================================================================
# OAuth Token Endpoint (Kept for Compatibility)
# ============================================================================

async def oauth_token(request: Request) -> Response:
    """
    OAuth 2.0 Token Endpoint.
    
    This might not be called by ChatGPT MCP since we return
    the token directly from /oauth/callback, but kept for compatibility.
    """
    log.info("⚠️ /oauth/token called - this is unexpected for ChatGPT MCP")
    log.info("   (token should have been returned from /oauth/callback)")
    
    # Parse the request body
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        try:
            body = await request.json()
        except:
            body = {}
    else:
        form = await request.form()
        body = dict(form)
    
    grant_type = body.get("grant_type", "")
    code = body.get("code", "")
    
    log.info(f"  grant_type: {grant_type}")
    log.info(f"  code: {code[:20]}..." if code else "  code: (none)")
    
    if grant_type != "authorization_code":
        return JSONResponse(
            status_code=400,
            content={
                "error": "unsupported_grant_type",
                "error_description": f"Grant type '{grant_type}' is not supported",
            },
        )
    
    # Look up stored tokens
    stored = OAUTH_STATE_STORE.pop(f"code:{code}", None)
    
    if not stored:
        log.error("❌ Unknown or expired code")
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "Invalid or expired authorization code",
            },
        )
    
    tokens = stored["tokens"]
    
    response = {
        "access_token": tokens.get("access_token"),
        "token_type": "Bearer",
        "expires_in": tokens.get("expires_in", 3600),
    }
    
    if tokens.get("refresh_token"):
        response["refresh_token"] = tokens["refresh_token"]
    
    if tokens.get("id_token"):
        response["id_token"] = tokens["id_token"]
    
    return JSONResponse(
        content=response,
        headers={"Cache-Control": "no-store"},
    )


# ============================================================================
# OpenID Connect Discovery (Proxy to Clerk)
# ============================================================================

async def openid_configuration(request: Request) -> Response:
    """Proxy the OpenID Connect Discovery document from Clerk."""
    config = get_config()
    
    if not config.discovery_url:
        return JSONResponse(
            status_code=503,
            content={"error": "OpenID configuration not available"},
        )
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(config.discovery_url)
            response.raise_for_status()
            return JSONResponse(
                content=response.json(),
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "public, max-age=3600",
                },
            )
    except httpx.HTTPError as e:
        log.error(f"Failed to fetch OpenID configuration: {e}")
        return JSONResponse(
            status_code=502,
            content={"error": "Failed to fetch OpenID configuration"},
        )


# ============================================================================
# Dynamic Client Registration Proxy
# ============================================================================

async def oauth_register(request: Request) -> Response:
    """Proxy dynamic client registration requests to Clerk."""
    config = get_config()
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            meta_response = await client.get(config.discovery_url)
            meta_response.raise_for_status()
            metadata = meta_response.json()
            
            registration_endpoint = metadata.get("registration_endpoint")
            
            if not registration_endpoint:
                return JSONResponse(
                    status_code=501,
                    content={
                        "error": "registration_not_supported",
                        "error_description": "Dynamic client registration is not enabled",
                    },
                )
            
            try:
                body = await request.json()
            except Exception:
                body = {}
            
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            
            if "Authorization" in request.headers:
                headers["Authorization"] = request.headers["Authorization"]
            
            reg_response = await client.post(
                registration_endpoint,
                json=body,
                headers=headers,
            )
            
            return Response(
                content=reg_response.content,
                status_code=reg_response.status_code,
                media_type="application/json",
            )
            
    except httpx.HTTPError as e:
        log.error(f"Failed to proxy registration: {e}")
        return JSONResponse(
            status_code=502,
            content={
                "error": "server_error",
                "error_description": "Failed to complete client registration",
            },
        )


# ============================================================================
# JWKS Proxy
# ============================================================================

async def jwks_json(request: Request) -> Response:
    """Proxy the JWKS from Clerk."""
    config = get_config()
    
    if not config.jwks_url:
        return JSONResponse(
            status_code=503,
            content={"error": "JWKS not configured"},
        )
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(config.jwks_url)
            response.raise_for_status()
            
            return JSONResponse(
                content=response.json(),
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "public, max-age=86400",
                },
            )
    except httpx.HTTPError as e:
        log.error(f"Failed to fetch JWKS: {e}")
        return JSONResponse(
            status_code=502,
            content={"error": "Failed to fetch signing keys"},
        )


# ============================================================================
# Route Registration Helper
# ============================================================================

def get_oauth_routes() -> list:
    """
    Get all OAuth-related routes for registration with Starlette.
    """
    return [
        Route(
            "/.well-known/oauth-protected-resource",
            oauth_protected_resource_metadata,
            methods=["GET"],
        ),
        Route(
            "/.well-known/oauth-authorization-server",
            oauth_authorization_server_metadata,
            methods=["GET"],
        ),
        Route(
            "/.well-known/openid-configuration",
            openid_configuration,
            methods=["GET"],
        ),
        Route(
            "/.well-known/jwks.json",
            jwks_json,
            methods=["GET"],
        ),
        Route(
            "/oauth/authorize",
            oauth_authorize,
            methods=["GET"],
        ),
        Route(
            "/oauth/callback",
            oauth_callback,
            methods=["GET"],
        ),
        Route(
            "/oauth/token",
            oauth_token,
            methods=["POST"],
        ),
        Route(
            "/oauth/register",
            oauth_register,
            methods=["POST"],
        ),
    ]

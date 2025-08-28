import os
os.environ.setdefault("LANGGRAPH_UI", "0")
os.environ.setdefault("LANGGRAPH_CONFIG", "")
from typing import Any, Dict, Optional

from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.requests import Request
from starlette.routing import Route
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import json










async def healthcheck(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


from .auth.fake_auth import fake_auth, get_current_user

class HeaderMiddleware(BaseHTTPMiddleware):
    """Middleware to capture headers and add them to request state."""
    
    async def dispatch(self, request: Request, call_next):
        # Capture user headers
        user_headers = {
            'X-User-ID': request.headers.get('X-User-ID'),
            'X-User-Email': request.headers.get('X-User-Email'),
        }
        
        # Store headers in request state for later use
        request.state.user_headers = user_headers
        
        # For POST requests to LangGraph endpoints, modify the request body
        if request.method == "POST" and any(path in request.url.path for path in ["/threads", "/runs"]):
            try:
                # Read the original body
                body = await request.body()
                if body:
                    body_data = json.loads(body)
                    
                    # Add headers to the request body
                    if isinstance(body_data, dict):
                        # Ensure config exists
                        if 'config' not in body_data:
                            body_data['config'] = {}
                        if 'configurable' not in body_data['config']:
                            body_data['config']['configurable'] = {}
                        
                        # Add headers to configurable
                        body_data['config']['configurable']['headers'] = user_headers
                        
                        # Also add to metadata for thread creation
                        if 'metadata' not in body_data:
                            body_data['metadata'] = {}
                        body_data['metadata']['user_id'] = user_headers['X-User-ID']
                        body_data['metadata']['user_email'] = user_headers['X-User-Email']
                        
                        # Create a new request with modified body
                        from starlette.requests import Request
                        from starlette.datastructures import Headers
                        
                        # Reconstruct the request with modified body
                        modified_body = json.dumps(body_data).encode()
                        request._body = modified_body
                        request.headers = Headers({
                            **dict(request.headers),
                            'content-length': str(len(modified_body))
                        })
                        
            except Exception as e:
                print(f"Error modifying request body: {e}")
        
        response = await call_next(request)
        return response

async def auth_initialize(request: Request) -> JSONResponse:
    """Initialize authentication with fake auth system."""
    try:
        # Get authorization header
        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        
        if auth_header and auth_header.lower().startswith("bearer "):
            # Extract token
            token = auth_header.split(" ", 1)[1].strip()
            user = fake_auth.get_user_from_token(token)
            
            if user:
                return JSONResponse({
                    "ok": True, 
                    "uid": user.id, 
                    "is_guest": user.is_guest,
                    "email": user.email,
                    "name": user.name
                })
        
        # If no valid token, create anonymous user
        user = fake_auth.get_or_create_anonymous_user()
        token = fake_auth.create_session_token(user.id)
        
        return JSONResponse({
            "ok": True, 
            "uid": user.id, 
            "is_guest": user.is_guest,
            "email": user.email,
            "name": user.name,
            "token": token
        })
        
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


routes = [
    Route("/health", healthcheck, methods=["GET"]),
    Route("/auth/initialize", auth_initialize, methods=["POST"]),
]


@asynccontextmanager
async def _noop_lifespan(app):
    # Explicitly disable third-party lifespans (e.g., LangGraph runtime) in this app
    yield


def create_app() -> Starlette:
    app = Starlette(routes=routes, lifespan=_noop_lifespan)
    
    # Add our custom header middleware first
    app.add_middleware(HeaderMiddleware)
    
    # CORS: allow UI origins
    allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in allowed_origins if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    return app


app = create_app()
# Force-disable any third-party lifespan handlers that might have been attached
try:
    app.router.lifespan_context = _noop_lifespan  # type: ignore[attr-defined]
except Exception:
    pass


class _NoLifespanWrapper:
    def __init__(self, inner_app):
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "lifespan":
            # Immediately acknowledge startup/shutdown without delegating
            while True:
                message = await receive()
                if message.get("type") == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message.get("type") == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        else:
            await self.inner_app(scope, receive, send)


# Wrap the Starlette app so any external lifespan hooks are ignored by uvicorn
app = _NoLifespanWrapper(app)



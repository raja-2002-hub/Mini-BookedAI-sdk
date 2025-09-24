"""
LangGraph server with proper header handling for local development.
"""
import logging
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Configure logging - reduced verbosity for better performance
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Aggressively suppress LangGraph framework logging
logging.getLogger("langgraph").setLevel(logging.CRITICAL)
logging.getLogger("langchain").setLevel(logging.CRITICAL)
logging.getLogger("langgraph_api").setLevel(logging.CRITICAL)
logging.getLogger("fastapi").setLevel(logging.CRITICAL)
logging.getLogger("uvicorn").setLevel(logging.CRITICAL)
logging.getLogger("uvicorn.access").setLevel(logging.CRITICAL)

# Suppress specific LangGraph execution loggers
logging.getLogger("__src__agent__graph").setLevel(logging.CRITICAL)

def create_custom_app():
    """Create LangGraph app with proper header injection."""
    
    # Set required environment variables for LangGraph
    os.environ.setdefault("LANGGRAPH_RUNTIME_EDITION", "inmem")
    os.environ.setdefault("DATABASE_URI", "sqlite:///test.db")
    os.environ.setdefault("REDIS_URI", "redis://localhost:6379")
    
    # Completely disable LangGraph execution logging
    os.environ.setdefault("LANGGRAPH_LOG_LEVEL", "CRITICAL")
    os.environ.setdefault("LANGGRAPH_DEBUG", "false")
    os.environ.setdefault("LANGGRAPH_VERBOSE", "false")
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    
    # Import after setting environment variables
    from langgraph_api.server import create_app as create_langgraph_app
    
    # Create the base LangGraph app
    app = create_langgraph_app()
    
    # Add middleware to properly inject headers into the graph execution context
    @app.middleware("http")
    async def inject_headers_middleware(request, call_next):
        """Middleware to inject request headers into the graph execution context."""
        
        # Extract all headers from the request
        headers = dict(request.headers)
        
        # Log the headers being processed 
        logger.debug(f"[SERVER] Processing request with headers: {list(headers.keys())}")
        
        # Store headers in request state for the graph to access
        request.state.injected_headers = headers
        
        response = await call_next(request)
        return response
    
    # Override the graph execution to inject headers
    original_stream = app.stream
    
    async def stream_with_headers(*args, **kwargs):
        """Stream with proper header injection."""
        # Get headers from request state if available
        headers = getattr(args[0].state, 'injected_headers', {}) if hasattr(args[0], 'state') else {}
        
        # Inject headers into the graph execution context
        if headers:
            # Add headers to the configurable context
            if 'configurable' not in kwargs:
                kwargs['configurable'] = {}
            if 'headers' not in kwargs['configurable']:
                kwargs['configurable']['headers'] = {}
            kwargs['configurable']['headers'].update(headers)
            
            # Also add to metadata
            if 'metadata' not in kwargs:
                kwargs['metadata'] = {}
            kwargs['metadata']['headers'] = headers
            
            logger.debug(f"[SERVER] Injected headers into graph execution: {list(headers.keys())}")
        
        return await original_stream(*args, **kwargs)
    
    # Replace the stream method
    app.stream = stream_with_headers
    
    return app

# Create the app
app = create_custom_app()

if __name__ == "__main__":
    import uvicorn
    logger.debug("Starting LangGraph server with proper header injection on port 2024")
    uvicorn.run(app, host="0.0.0.0", port=2024, log_level="critical")

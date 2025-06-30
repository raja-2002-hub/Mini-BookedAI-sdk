FROM langchain/langgraph-api:3.11

# Set environment variables for uv
ENV UV_SYSTEM_PYTHON=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install Node.js 22 LTS and npm for UI compilation using NodeSource (most reliable for mixed environments)
RUN apt-get update && \
    apt-get install -y ca-certificates curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    node --version && \
    npm --version && \
    npx --version && \
    rm -f /usr/lib/python3.11/EXTERNALLY-MANAGED /usr/lib/python3/dist-packages/EXTERNALLY-MANAGED || true

# Copy project files to expected location
COPY . /deps/graph
WORKDIR /deps/graph

# Install dependencies into system Python using uv pip (needed for LangGraph compatibility)
RUN uv pip install --system --no-cache-dir .

# Set the graph configuration
ENV LANGSERVE_GRAPHS='{"agent": "/deps/graph/src/agent/graph.py:graph"}'

# Set UI environment variables for production
ENV LANGGRAPH_UI='{"agent": "./src/agent/ui.tsx"}'
ENV LANGGRAPH_UI_BUNDLER=true

# Set explicit NODE_PATH and PATH for UI bundler subprocess
ENV NODE_PATH=/usr/lib/node_modules
ENV PATH=/usr/bin:$PATH
# Ensure subprocess environment compatibility
ENV PYTHONUNBUFFERED=1
ENV SHELL=/bin/bash

# Create required UI bundler directories
RUN mkdir -p /deps/graph/.langgraph_api/ui

# Pre-install common UI dependencies to avoid subprocess issues
RUN npm install -g typescript @types/react @types/react-dom || true

# Ensure langgraph-api components remain accessible
RUN mkdir -p /api/langgraph_api /api/langgraph_runtime /api/langgraph_license && \
    touch /api/langgraph_api/__init__.py /api/langgraph_runtime/__init__.py /api/langgraph_license/__init__.py

# CRITICAL: Reinstall LangGraph API components (including UI) to prevent overwriting
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir --no-deps -e /api

# Add our project to Python path
ENV PYTHONPATH="/deps/graph:$PYTHONPATH"

# Allow pip system installs
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Patch Python runtime to ensure asyncio subprocess env is a dict (uvloop compatibility)
RUN printf '%s\n' "import asyncio, os\n_orig_create = asyncio.create_subprocess_exec\nasync def _fixed_create(*args, **kwargs):\n    env = kwargs.get('env')\n    if isinstance(env, os._Environ):\n        kwargs['env'] = dict(env)\n    return await _orig_create(*args, **kwargs)\nasyncio.create_subprocess_exec = _fixed_create\n" > /usr/local/lib/python3.11/site-packages/sitecustomize.py

WORKDIR /deps/graph 
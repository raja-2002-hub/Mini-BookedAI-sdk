# --------------------------
# Base image
# --------------------------
FROM langchain/langgraph-api:3.11

# --------------------------
# Environment setup
# --------------------------
ENV UV_SYSTEM_PYTHON=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENV SHELL=/bin/bash

# --------------------------
# Install Node.js 22 LTS for UI
# --------------------------
RUN apt-get update && \
    apt-get install -y build-essential ca-certificates curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    node --version && npm --version && npx --version

# --------------------------
# Copy project code
# --------------------------
COPY . /deps/graph
WORKDIR /deps/graph

# --------------------------
# Install Python project dependencies
# --------------------------
RUN uv pip install --system --no-cache-dir .

# --------------------------
# LangGraph configuration
# --------------------------
ENV LANGSERVE_GRAPHS='{"agent": "/deps/graph/src/agent/graph.py:graph"}'
ENV LANGGRAPH_UI='{"agent": "/deps/graph/src/agent/ui.tsx"}'
ENV LANGGRAPH_UI_BUNDLER=true

# --------------------------
# Node.js PATH for UI bundler
# --------------------------
ENV NODE_PATH=/usr/lib/node_modules
ENV PATH=/usr/bin:$PATH

# --------------------------
# LangGraph UI bundler setup
# --------------------------
RUN mkdir -p /deps/graph/.langgraph_api/ui
RUN npm install -g typescript @types/react @types/react-dom react react-dom next esbuild || true

# Fix 'uuid' import in LangGraph UI
ENV LANGGRAPH_UI_EXTERNALS='["uuid"]'
RUN npm install uuid

# --------------------------
# Patch asyncio for uvloop subprocess env
# --------------------------
RUN cat > /usr/local/lib/python3.11/site-packages/sitecustomize.py <<'PYEOF'
import asyncio, os
_orig_create = asyncio.create_subprocess_exec
async def _fixed_create(*args, **kwargs):
    env = kwargs.get('env')
    if isinstance(env, os._Environ):
        kwargs['env'] = dict(env)
    return await _orig_create(*args, **kwargs)
asyncio.create_subprocess_exec = _fixed_create
PYEOF

# --------------------------
# Python path for project
# --------------------------
ENV PYTHONPATH="/deps/graph:$PYTHONPATH"

# --------------------------
# Default WORKDIR
# --------------------------
WORKDIR /deps/graph

# --------------------------
# Start LangGraph API for Railway
# --------------------------
CMD ["uvicorn", "--host", "0.0.0.0", "--port", "8080", "langgraph_api.server:app"]

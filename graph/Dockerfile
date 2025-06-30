FROM langchain/langgraph-api:3.11

# Set environment variables for uv
ENV UV_SYSTEM_PYTHON=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy project files to expected location
COPY . /deps/graph
WORKDIR /deps/graph

# Install dependencies into system Python using uv pip (needed for LangGraph compatibility)
RUN uv pip install --system --no-cache-dir .

# Set the graph configuration
ENV LANGSERVE_GRAPHS='{"agent": "/deps/graph/src/agent/graph.py:graph"}'

# Ensure langgraph-api components remain accessible
RUN mkdir -p /api/langgraph_api /api/langgraph_runtime /api/langgraph_license && \
    touch /api/langgraph_api/__init__.py /api/langgraph_runtime/__init__.py /api/langgraph_license/__init__.py

# CRITICAL: Reinstall LangGraph API components (including UI) to prevent overwriting
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir --no-deps -e /api

# Add our project to Python path
ENV PYTHONPATH="/deps/graph:$PYTHONPATH"

WORKDIR /deps/graph 
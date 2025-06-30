FROM langchain/langgraph-api:3.11

# Set environment variables for uv
ENV UV_SYSTEM_PYTHON=1
ENV UV_PROJECT_ENVIRONMENT=/usr/local
ENV PYTHONDONTWRITEBYTECODE=1

# Copy project files to expected location
COPY . /deps/graph

# Install project dependencies using pure uv (no pip interface)
WORKDIR /deps/graph
RUN uv sync --frozen --no-dev

# Set the graph configuration
ENV LANGSERVE_GRAPHS='{"agent": "/deps/graph/src/agent/graph.py:graph"}'

# Ensure langgraph-api components remain accessible
RUN mkdir -p /api/langgraph_api /api/langgraph_runtime /api/langgraph_license && \
    touch /api/langgraph_api/__init__.py /api/langgraph_runtime/__init__.py /api/langgraph_license/__init__.py

# Make sure our package is available in the Python path
ENV PYTHONPATH="/deps/graph:$PYTHONPATH"

WORKDIR /deps/graph
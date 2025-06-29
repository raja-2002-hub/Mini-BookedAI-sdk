# Railway Deployment Guide

This guide walks through deploying the BookedAI monorepo to Railway with two separate services.

## Architecture

- **UI Service** (`/ui`): Next.js frontend using pnpm, based on [LangChain agent-chat-ui](https://github.com/langchain-ai/agent-chat-ui)
- **Graph Service** (`/graph`): LangGraph Python backend using uv

## Railway Setup

### 1. Create Two Services

In your Railway project, create two services from the same GitHub repository:

#### Service 1: UI (Frontend)
- **Service Name**: `bookedai-ui`
- **Root Directory**: `ui`
- **Railway Config**: `railway-ui.json`
- **Nixpacks Config**: `ui/nixpacks.toml`

#### Service 2: Graph (Backend)  
- **Service Name**: `bookedai-graph`
- **Root Directory**: `graph`
- **Railway Config**: `railway-graph.json`
- **Nixpacks Config**: `graph/nixpacks.toml`

### 2. Configure Service Settings

For each service in Railway dashboard:

#### UI Service Settings:
1. **Root Directory**: `ui`
2. **Custom Config File Path**: `railway-ui.json`
3. **Watch Paths**: `ui/**`

#### Graph Service Settings:
1. **Root Directory**: `graph` 
2. **Custom Config File Path**: `railway-graph.json`
3. **Watch Paths**: `graph/**`

### 3. Environment Variables

#### UI Service Variables:
```bash
# Required: Point to your graph service
NEXT_PUBLIC_API_URL=https://bookedai-graph.railway.app
NEXT_PUBLIC_ASSISTANT_ID=agent

# Optional: For production API passthrough
LANGGRAPH_API_URL=https://bookedai-graph.railway.app
LANGSMITH_API_KEY=lsv2_your_langsmith_key
```

#### Graph Service Variables:
```bash
# Required API Keys
OPENAI_API_KEY=your_openai_api_key
DUFFEL_API_TOKEN=your_duffel_api_token

# Optional LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=BookedAI-Production

# Optional configuration
REQUEST_TIMEOUT=30
MAX_RETRIES=3
```

## Deployment Flow

1. **Connect Repository**: Connect your GitHub repo to Railway
2. **Create Services**: Set up both services with proper root directories
3. **Configure Build**: Railway will auto-detect and use the nixpacks configs
4. **Set Environment Variables**: Add required env vars to each service
5. **Deploy**: Commit to trigger deployments

## URLs After Deployment

- **UI**: `https://bookedai-ui.railway.app`
- **Graph API**: `https://bookedai-graph.railway.app`

## Package Managers

- **UI**: Uses `pnpm` (faster, more efficient than npm)
- **Graph**: Uses `uv` (faster Python package management)

## File Structure

```
mini_bookedai/
├── ui/                          # Next.js frontend
│   ├── nixpacks.toml           # UI-specific nixpacks config
│   ├── package.json            # pnpm dependencies
│   └── src/                    # UI source code
├── graph/                       # LangGraph backend  
│   ├── nixpacks.toml           # Graph-specific nixpacks config
│   ├── pyproject.toml          # uv dependencies
│   ├── langgraph.json          # LangGraph config
│   └── src/                    # Graph source code
├── railway-ui.json             # Railway config for UI
├── railway-graph.json          # Railway config for Graph
└── RAILWAY_DEPLOYMENT.md       # This guide
```

## Troubleshooting

### Build Issues
- Check nixpacks configs match your package managers
- Verify root directories are set correctly
- Ensure watch paths prevent cross-service builds

### Connection Issues  
- Verify `NEXT_PUBLIC_API_URL` points to graph service
- Check CORS settings if needed
- Ensure both services are deployed and running

### LangGraph Issues
- Verify `langgraph.json` configuration
- Check environment variables are set
- Monitor logs for startup errors

## Production Considerations

1. **API Authentication**: Consider implementing custom auth instead of API passthrough
2. **CORS**: Configure proper CORS settings for production
3. **Environment Separation**: Use different Railway projects for staging/production
4. **Monitoring**: Set up proper logging and monitoring
5. **Scaling**: Configure auto-scaling based on usage

## References

- [Railway Monorepo Guide](https://docs.railway.app/guides/monorepo)
- [LangChain Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui)
- [LangGraph Deployment](https://langchain-ai.github.io/langgraph/concepts/deployment_options/) 
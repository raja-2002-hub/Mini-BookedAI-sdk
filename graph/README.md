# BookedAI LangGraph Agent

A pre-built LangGraph agent with tools for time, mathematics, and web search capabilities.

## Features

- **Time Tool**: Get current date and time
- **Math Calculator**: Perform simple arithmetic calculations
- **Web Search**: Mock web search functionality (can be extended with real APIs)
- **Human-in-the-loop**: Support for human intervention during conversations
- **Memory**: Persistent conversation memory across sessions

## Setup

### 1. Install Dependencies

```bash
# Install dependencies using uv
uv sync

# Or using pip
pip install -e .
```

### 2. Configure Environment Variables

```bash
# Copy the example environment file
cp env.example .env

# Edit .env with your API keys
nano .env
```

Required environment variables:
- `OPENAI_API_KEY`: Your OpenAI API key

### 3. Run the Agent

```bash
# Start the LangGraph development server
langgraph dev
```

This will start the LangGraph API server locally, typically on `http://localhost:8123`.

### 4. Connect to UI

If you have the LangGraph Chat UI running (via `pnpm run dev`), you can:

1. Navigate to your Chat UI (typically `http://localhost:3000`)
2. Connect to the local LangGraph server (`http://localhost:8123`)
3. Select the "BookedAI Agent" graph
4. Start chatting!

## Usage Examples

### Basic Conversation
```
User: Hello! What can you help me with?
Agent: I'm a helpful AI assistant for BookedAI. I can get the current time, perform calculations, and search for information. How can I assist you today?
```

### Using Tools
```
User: What time is it?
Agent: [Uses get_current_time tool] The current time is 2024-01-15 14:30:22

User: Calculate 25 * 4 + 10
Agent: [Uses calculate_simple_math tool] The result is 110

User: Search for information about Python
Agent: [Uses search_web tool] Mock search results for: Python...
```

### Human-in-the-loop
The agent can request human input by saying "human input needed" in its response.

## Development

### Project Structure
```
├── src/
│   └── agent/
│       ├── __init__.py
│       └── graph.py          # Main agent implementation
├── langgraph.json            # LangGraph configuration
├── pyproject.toml           # Python dependencies
├── env.example              # Environment variables template
└── README.md               # This file
```

### Extending the Agent

To add new tools:

1. Define your tool function in `src/agent/graph.py`:
```python
@tool
def my_new_tool(param: str) -> str:
    """Description of what this tool does."""
    # Your implementation here
    return result
```

2. Add it to the tools list in `create_graph()` and `agent_node()` functions.

### Configuration

The agent configuration is defined in `langgraph.json`:
- **graphs.agent.path**: Points to the compiled graph object
- **env**: Environment file location
- **dependencies**: Python package dependencies

## Troubleshooting

### Common Issues

1. **Missing OpenAI API Key**: Make sure your `.env` file contains a valid `OPENAI_API_KEY`
2. **Import Errors**: Run `uv sync` to ensure all dependencies are installed
3. **Port Conflicts**: LangGraph dev server runs on port 8123 by default

### Logs

Check the LangGraph dev server logs for detailed error information and debugging.

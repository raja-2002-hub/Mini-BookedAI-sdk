# BookedAI LangGraph Agent

A pre-built LangGraph agent with tools for time, mathematics, web search, and **hotel search capabilities** using the Duffel API.

## Features

- **Time Tool**: Get current date and time
- **Math Calculator**: Perform simple arithmetic calculations
- **Web Search**: Mock web search functionality (can be extended with real APIs)
- **🏨 Hotel Search**: Real hotel search using Duffel Stays API
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
- `DUFFEL_API_TOKEN`: Your Duffel API token for hotel search

### 3. Get Duffel API Access

1. Sign up for a Duffel account at [https://duffel.com](https://duffel.com)
2. Get your API token from the Duffel dashboard
3. Add it to your `.env` file as `DUFFEL_API_TOKEN`

### 4. Run the Agent

```bash
# LangGraph development server
langgraph dev

# Option B: Unified backend with Starlette (auth + profiles)
uvicorn src.server:app --host 0.0.0.0 --port 8080 --reload
```


### 5. Connect to UI

If you have the LangGraph Chat UI running (via `pnpm run dev`), you can:

1. Navigate to your Chat UI (typically `http://localhost:3000`)
2. Connect to the local LangGraph server (`http://localhost:2024`)
3. Select the "BookedAI Agent" graph
4. Start chatting!

## Usage Examples

### Basic Conversation
```
User: Hello! What can you help me with?
Agent: I'm a helpful AI assistant for BookedAI specializing in travel assistance. I can get the current time, perform calculations, search for information, and search for hotels. How can I assist you today?
```

### Using Tools
```
User: What time is it?
Agent: [Uses get_current_time tool] The current time is 2024-06-17 14:30:22

User: Calculate 25 * 4 + 10
Agent: [Uses calculate_simple_math tool] The result is 110

User: Search for information about Python
Agent: [Uses search_web tool] Mock search results for: Python...
```

### Hotel Search Examples
```
User: Find hotels in Tokyo for December 15-22, 2024
Agent: I'd be happy to help you find hotels in Tokyo! To search for the best options, could you please let me know how many guests will be staying? (number of adults and children)

User: 2 adults
Agent: [Uses search_hotels_tool] Found 8 hotels:

1. Park Hyatt Tokyo (5★) in Tokyo - from USD 450.00
2. Hotel Okura Tokyo (5★) in Tokyo - from USD 320.00
3. The Ritz-Carlton Tokyo (5★) in Tokyo - from USD 580.00
4. Shangri-La Hotel Tokyo (5★) in Tokyo - from USD 420.00
5. Mandarin Oriental Tokyo (5★) in Tokyo - from USD 650.00

User: Find cheaper options in Paris for 2024-12-20 to 2024-12-23, 1 adult
Agent: [Uses search_hotels_tool with Paris location] Found 10 hotels:

1. Hotel Malte Opera (3★) in Paris - from EUR 89.00
2. Hotel des Grands Boulevards (4★) in Paris - from EUR 195.00
...
```

### Human-in-the-loop
The agent can request human input by saying "human input needed" in its response.

## Development

### Project Structure
```
├── src/
│   ├── agent/
│   │   ├── __init__.py
│   │   └── graph.py          # Main agent implementation with hotel search
│   ├── duffel_client/        # Duffel API integration
│   │   ├── __init__.py
│   │   ├── client.py         # HTTP client with auth and retry logic
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── common.py     # Shared models (Money, Location, etc.)
│   │   │   └── stays.py      # Hotel search models
│   │   └── endpoints/
│   │       ├── __init__.py
│   │       └── stays.py      # Hotel search API endpoint
│   └── config.py             # Configuration management
├── langgraph.json            # LangGraph configuration
├── pyproject.toml           # Python dependencies
├── env.example              # Environment variables template
└── README.md               # This file
```

### Available Tools

1. **get_current_time()** - Returns current date and time
2. **calculate_simple_math(expression)** - Safe arithmetic evaluation
3. **search_web(query)** - Mock web search (for demo)
4. **search_hotels_tool(location, check_in_date, check_out_date, adults, children, max_results)** - Real hotel search

### Hotel Search Tool Details

The hotel search tool supports:
- **Location**: City names, regions (e.g., "Tokyo", "New York", "Paris")
- **Dates**: Must be in YYYY-MM-DD format (e.g., "2024-12-15")
- **Guests**: Specify adults (required, ≥1) and children (optional, ≥0)
- **Results**: Returns up to 20 hotels with names, ratings, locations, and prices
- **Validation**: Comprehensive input validation with helpful error messages

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
2. **Missing Duffel API Token**: Make sure your `.env` file contains a valid `DUFFEL_API_TOKEN`
3. **Import Errors**: Run `uv sync` to ensure all dependencies are installed
4. **Port Conflicts**: LangGraph dev server runs on port 2024 by default
5. **Hotel Search Unavailable**: Check that your Duffel API token is valid and has access to the Stays API

### Hotel Search Troubleshooting

- **Date Format Errors**: Ensure dates are in YYYY-MM-DD format
- **Invalid Date Range**: Check-out must be after check-in, dates cannot be in the past
- **No Results**: Try different locations or date ranges
- **API Limits**: Duffel has rate limits; wait a moment between searches

### Logs

Check the LangGraph dev server logs for detailed error information and debugging.

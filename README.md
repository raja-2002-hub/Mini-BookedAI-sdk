# Mini Booked AI w/ LangGraph UI & Agent

## Project Overview

A hands-on mini project designed for new team members to learn LangGraph agent development while building a practical travel search application using the Duffel API.

## Initial Concept Evolution

**Original Idea**: Simple agent with basic tool calling (calculator, weather, etc.)
**Final Concept**: Travel search agent using Duffel API v2 for flights and hotels/stays with a modern chat interface

## Current Status

✅ **Phase 1 Complete**: Basic LangGraph agent with tools and dev server
- LangGraph agent with time, math, and web search tools
- Working `langgraph dev` server setup
- Human-in-the-loop capabilities
- Ready for UI integration

✅ **Phase 2 Partial**: Duffel API integration for flights
- Complete flight search and booking functionality with Duffel API
- Flight tools with comprehensive validation and error handling
- Hotel/stays search tools (existing implementation)
- Comprehensive Pydantic models for flight data

🚧 **Next Phase**: Agent Chat UI setup and enhanced hotel functionality

## Quick Start (Current Implementation)

### Prerequisites
- **Python 3.11+** (required for langgraph dev server)
- **uv** - Install from [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/)
- **OpenAI API Key** - For the language model
- **Duffel API Token** - For flight and hotel search functionality

### Setup Instructions

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd mini_bookedai
   ```

2. **Setup the LangGraph agent**:
   ```bash
   cd graph/
   
   # Install dependencies (automatically creates venv with Python 3.11)
   uv sync
   
   # Configure environment variables
   cp env.example .env
   # Edit .env and add your OPENAI_API_KEY and DUFFEL_API_TOKEN
   ```

3. **Start the LangGraph development server**:
   ```bash
   # From the graph/ directory
   source .venv/bin/activate
   langgraph dev --no-browser
   ```
   
   The server will start on `http://127.0.0.1:2024` with:
   - 🚀 **API**: http://127.0.0.1:2024
   - 📚 **API Docs**: http://127.0.0.1:2024/docs
   - 🎨 **Studio UI**: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024

### Testing the Agent

You can test the agent using the LangGraph Studio UI or API endpoints:

**Available Tools**:
- `get_current_time()` - Get current date and time
- `calculate_simple_math(expression)` - Perform arithmetic calculations
- `search_web(query)` - Mock web search (demo purposes)
- `validate_phone_number_tool(phone, region)` - Phone number validation
- `search_hotels_tool()` - Hotel/stays search with Duffel API
- `fetch_hotel_rates_tool()` - Hotel rate details and quotes
- `create_quote_tool()` - Hotel booking quotes
- `create_booking_tool()` - Hotel booking creation
- **NEW**: `search_flights_tool()` - Flight search with Duffel API
- **NEW**: `fetch_flight_quote_tool()` - Flight offer quote refresh
- **NEW**: `create_flight_booking_tool()` - Flight booking creation

**Example Interactions**:
```
User: "What time is it?"
Agent: [Uses get_current_time tool] The current time is 2024-06-16 15:30:22

User: "Calculate 25 * 4 + 10"  
Agent: [Uses calculate_simple_math tool] The result is 110

User: "Search for flights from JFK to LAX on December 15th"
Agent: [Uses search_flights_tool] Found 5 flight options from JFK to LAX on 2024-12-15:
       - American Airlines: $299, departing 8:00 AM
       - Delta: $325, departing 10:30 AM
       - United: $342, departing 2:15 PM

User: "Find hotels in Los Angeles for December 15-17"  
Agent: [Uses search_hotels_tool] Found 8 hotels in Los Angeles for your dates:
       - The Beverly Hills Hotel: $450/night
       - Hotel Figueroa: $180/night
       - The Standard Downtown: $220/night
```

### Project Structure (Current)

```
mini_bookedai/
├── graph/                        # ✅ LangGraph implementation with Duffel API
│   ├── pyproject.toml           # uv project configuration with langgraph-cli[inmem]
│   ├── .python-version          # Python 3.11 requirement
│   ├── langgraph.json           # LangGraph server configuration
│   ├── env.example              # Environment variables template (OPENAI_API_KEY, DUFFEL_API_TOKEN)
│   ├── src/
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   └── graph.py         # Complete agent with flight/hotel tools
│   │   ├── duffel_client/       # ✅ Duffel API integration
│   │   │   ├── client.py        # Main Duffel API client
│   │   │   ├── endpoints/
│   │   │   │   ├── flights.py   # Flight search and booking endpoints
│   │   │   │   └── stays.py     # Hotel/stays search endpoints
│   │   │   └── models/
│   │   │       ├── flights.py   # Flight Pydantic models
│   │   │       └── stays.py     # Hotel/stays Pydantic models
│   │   └── config.py            # Configuration management
│   └── README.md                # Detailed setup instructions
├── ui/                          # 🚧 Agent Chat UI (PLANNED)
│   └── (to be implemented)
└── README.md                    # This file
```

## Key Components

### Technical Stack
- **LangGraph** - Agent framework with tool calling (managed with uv)
- **Agent Chat UI** - Pre-built Next.js interface from LangChain for agent interaction
- **Duffel API v2** - Flight and hotel search capabilities
- **Pydantic** - Data validation and modeling
- **Python** - Backend agent implementation
- **uv** - Python package management for the graph server

### Architecture
- **Frontend**: Agent Chat UI (Next.js) in `ui/` directory
- **Backend**: LangGraph server running locally in `graph/` directory
- **API**: Duffel API integration for travel search functionality

### Core Functionality
- **Flight Search Tool** - Search flights using Duffel Flights API
- **Hotel Search Tool** - Search accommodations using Duffel Stays API  
- **Conversational Interface** - Natural language queries via modern chat UI
- **Local Development** - LangGraph server running locally with hot reload

## Full Project Structure (Planned)

```
mini_bookedai/
├── ui/                           # Agent Chat UI (Next.js frontend)
│   ├── src/
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── next.config.mjs
│   └── README.md
├── graph/                        # LangGraph implementation (Python backend)
│   ├── pyproject.toml           # uv project configuration
│   ├── .python-version          # Python version specification
│   ├── src/
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   ├── graph.py         # LangGraph agent implementation
│   │   │   ├── tools.py         # Travel search tools
│   │   │   └── prompts.py       # Agent prompts/instructions
│   │   ├── duffel_client/
│   │   │   ├── __init__.py
│   │   │   ├── client.py        # Main Duffel API client
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── flights.py   # Pydantic models for flights
│   │   │   │   ├── stays.py     # Pydantic models for stays
│   │   │   │   └── common.py    # Shared models (locations, dates, etc.)
│   │   │   └── endpoints/
│   │   │       ├── __init__.py
│   │   │       ├── flights.py   # Flight search endpoints
│   │   │       └── stays.py     # Stay search endpoints
│   │   └── config.py            # Configuration management
│   ├── tests/
│   │   ├── test_duffel_client.py
│   │   └── test_agent_tools.py
│   └── langgraph.json           # LangGraph server configuration
├── .env.example
└── README.md
```

## Development Setup (Full Implementation)

### Prerequisites
- **Python 3.11+** (managed via uv)
- **Node.js 18+** (for the UI)
- **pnpm** - Install from [https://pnpm.io/installation](https://pnpm.io/installation)
- **uv** - Install from [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/)

### Full Setup (When UI is implemented)

1. **Clone and setup the LangGraph server**:
   ```bash
   cd graph/
   uv sync  # Install dependencies
   uv run langgraph dev  # Start the development server
   ```

2. **Setup the UI** (in a separate terminal):
   ```bash
   cd ui/
   pnpm install
   pnpm dev
   ```

3. **Configure environment**:
   - Copy `.env.example` to `.env`
   - Add your Duffel API credentials
   - Set `NEXT_PUBLIC_API_URL=http://localhost:2024` (LangGraph dev server)

## Implementation Phases

### Phase 1: Foundation ✅ COMPLETE
- ✅ Set up basic LangGraph project with uv
- ✅ Implement basic tools (time, math, web search)
- ✅ Configure langgraph dev server
- ✅ Human-in-the-loop capabilities
- ✅ Memory and conversation state

### Phase 2: Core Features ✅ PARTIAL
- ✅ Implement comprehensive flight search tool using Duffel API
- ✅ Add flight booking functionality with quote refresh
- ✅ Implement stays/hotel search functionality
- ✅ Add hotel booking tools with quote and booking creation
- 🚧 Set up Agent Chat UI with basic configuration
- 🚧 Establish UI ↔ Graph server communication

### Phase 3: Enhanced UX
- Implement location lookup/suggestions
- Enhanced error handling and validation
- UI improvements for travel search results
- Natural language date parsing

### Phase 4: Advanced Features
- Multi-step conversations
- Human-in-the-loop for booking confirmation
- Result formatting and comparison in chat
- Concurrent flight + hotel searches

## Learning Objectives

### For New Team Members
1. **LangGraph Development** - Building agents with local development server
2. **uv Package Management** - Modern Python dependency management
3. **Agent Chat UI** - Frontend integration with LangGraph backends
4. **API Integration** - Working with external REST APIs (Duffel)
5. **Pydantic Validation** - Data modeling and validation patterns
6. **Full-Stack Architecture** - Frontend/backend separation and communication

## Local Development Workflow

### LangGraph Server (Backend)
```bash
cd graph/
uv run langgraph dev --port 2024  # Runs on localhost:2024
```

### Agent Chat UI (Frontend)
```bash
cd ui/
pnpm dev  # Runs on localhost:3000
```

### Environment Configuration
- **Backend**: Duffel API keys in `graph/.env`
- **Frontend**: `NEXT_PUBLIC_API_URL=http://localhost:2024` in `ui/.env`

## Sample User Interactions

```
User: "I need flights from San Francisco to Tokyo next month"
Agent: "I'll search for flights from San Francisco to Tokyo. Could you specify:
        - Exact departure date?
        - Are you looking for a round trip?
        - How many passengers?"

User: "December 15th, round trip returning December 22nd, 2 passengers"
Agent: [Searches flights] "Found 5 flight options ranging from $1,200-$2,100 per person..."

User: "Also find hotels in Tokyo for those dates"
Agent: [Searches stays] "Found 12 accommodation options near Tokyo city center..."
```

## Pydantic Model Examples

### Flight Search Request
```python
class FlightSearchRequest(BaseModel):
    origin: str
    destination: str  
    departure_date: date
    return_date: Optional[date] = None
    passengers: int = 1
    cabin_class: Optional[str] = "economy"
    
class FlightOffer(BaseModel):
    id: str
    total_amount: str
    total_currency: str
    slices: List[FlightSlice]
    # ... other fields from Duffel API
```

## LangGraph Tools Structure

### Key Tools to Implement
- `search_flights_tool` - Handles flight search requests
- `search_stays_tool` - Handles accommodation search  
- `get_location_suggestions_tool` - Help with airport/city codes

### Agent Capabilities
- Parse natural language travel requests
- Handle date parsing and validation
- Provide formatted, user-friendly results
- Ask clarifying questions when needed
- Handle errors gracefully

## Linear Project Details

**Project Created**: Mini Booked w/ Langgraph UI & Agent
- **Project ID**: `014fc74c-26c9-4031-8f50-a71a5647e31c`
- **Team**: Booked AI (`8d07af27-a7ee-41a2-80b5-62d618d34ed6`)
- **URL**: [https://linear.app/booked-ai/project/mini-booked-w-langgraph-ui-and-agent-42c4f9ffd5cc](https://linear.app/booked-ai/project/mini-booked-w-langgraph-ui-and-agent-42c4f9ffd5cc)

## Success Criteria

- ✅ LangGraph server runs locally with hot reload via uv
- ✅ Agent can handle tool calls and human-in-the-loop interactions
- ✅ Proper error handling and user feedback
- ✅ Clean, maintainable code structure with modern tooling
- ✅ Agent can search flights using natural language with Duffel API
- ✅ Agent can search hotels/stays using natural language with Duffel API
- ✅ Complete flight and hotel booking functionality
- ✅ Comprehensive Pydantic models for travel data validation
- 🚧 Agent Chat UI connects to local LangGraph server
- 🚧 Complete documentation for future team members

## Key Resources

- **Agent Chat UI**: [https://github.com/langchain-ai/agent-chat-ui](https://github.com/langchain-ai/agent-chat-ui)
- **LangGraph Local Deployment**: [https://langchain-ai.github.io/langgraph/agents/deployment/#launch-langgraph-server-locally](https://langchain-ai.github.io/langgraph/agents/deployment/#launch-langgraph-server-locally)
- **uv Documentation**: [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/)
- **Duffel API Documentation**: [https://duffel.com/docs](https://duffel.com/docs)

## Project Benefits

This project hits the sweet spot of being:
- **Practical** - Real travel search functionality with modern UI
- **Educational** - Multiple learning opportunities across full stack
- **Scalable** - Can grow with additional features and UI enhancements
- **Modern** - Uses latest tooling (uv, Agent Chat UI, LangGraph dev server)
- **Engaging** - More interesting than toy examples with professional UX

## Next Steps

1. Create detailed Linear issues for each implementation phase
2. Set up Agent Chat UI in `ui/` directory
3. Initialize Duffel API integration in LangGraph agent
4. Establish UI ↔ Graph server communication workflow
5. Begin Phase 2 implementation
6. Plan onboarding materials for new team members 
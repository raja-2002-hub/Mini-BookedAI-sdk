# Mini Booked AI w/ LangGraph UI & Agent

## Project Overview

A hands-on mini project designed for new team members to learn LangGraph agent development while building a practical travel search application using the Duffel API.

## Initial Concept Evolution

**Original Idea**: Simple agent with basic tool calling (calculator, weather, etc.)
**Final Concept**: Travel search agent using Duffel API v2 for flights and hotels/stays with a modern chat interface

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

## Project Structure

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

## Development Setup

### Prerequisites
- **Python 3.11+** (managed via uv)
- **Node.js 18+** (for the UI)
- **pnpm** - Install from [https://pnpm.io/installation](https://pnpm.io/installation)
- **uv** - Install from [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/)

### Quick Start

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

### Phase 1: Foundation
- Set up Agent Chat UI with basic configuration
- Initialize LangGraph project with uv
- Implement simple flight search tool
- Establish UI ↔ Graph server communication

### Phase 2: Core Features
- Add stays search functionality
- Implement location lookup/suggestions
- Enhanced error handling and validation
- UI improvements for travel search results

### Phase 3: Enhanced UX
- Natural language date parsing
- Multi-step conversations
- Human-in-the-loop for booking confirmation
- Result formatting and comparison in chat

### Phase 4: Advanced Features
- Concurrent flight + hotel searches
- Price comparison and sorting
- Search history and preferences
- Advanced chat UI customizations

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

- LangGraph server runs locally with hot reload via uv
- Agent Chat UI connects to local LangGraph server
- Agent can search flights using natural language
- Agent can search hotels/stays using natural language
- Proper error handling and user feedback
- Clean, maintainable code structure with modern tooling
- Complete documentation for future team members

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
3. Initialize LangGraph project with uv in `graph/` directory
4. Establish local development workflow
5. Begin Phase 1 implementation
6. Plan onboarding materials for new team members 
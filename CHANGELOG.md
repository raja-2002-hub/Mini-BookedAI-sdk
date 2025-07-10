# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2024-12

### Added - Flight Search & Booking Implementation
- **Complete Flight Search Tool** - `search_flights_tool` with comprehensive parameter validation
  - Origin/destination airport code support
  - Departure and return date handling with validation
  - Passenger count (1-9) and cabin class selection
  - Flight search results formatting for JSON output
  - Integration with Duffel Flights API
- **Flight Booking Functionality**
  - `fetch_flight_quote_tool` - Refresh offer details and get passenger IDs
  - `create_flight_booking_tool` - Complete flight booking with passenger and payment data
  - Comprehensive error handling for Duffel API responses
- **New Duffel Client Architecture**
  - `src/duffel_client/endpoints/flights.py` - Flight API endpoint implementations
  - `src/duffel_client/models/flights.py` - Pydantic models for flight data structures
  - Flight search request/response models with UI-friendly JSON formatting
  - FlightSearchRequest, FlightSearchResponse, FlightOffer, and FlightSegment models

### Technical Implementation - Flights
- **Search Capabilities**:
  - Natural language date parsing and validation
  - Round-trip and one-way flight support
  - Cabin class options: economy, premium_economy, business, first
  - Results limiting and pagination support
- **Booking Features**:
  - Offer quote refresh functionality
  - Multi-passenger booking support
  - Contact information validation (email, phone)
  - Payment integration framework
- **Data Models**:
  - Comprehensive flight segment data (times, airlines, aircraft, etc.)
  - Price and currency handling
  - Refundable and baggage inclusion flags
  - UI-optimized JSON response formatting

### Updated Tool Set
- **Tools Implemented**:
  - `get_current_time()` - Current date and time retrieval
  - `calculate_simple_math(expression)` - Safe arithmetic evaluation
  - `search_web(query)` - Mock web search functionality
  - `validate_phone_number_tool(phone, region)` - Phone number validation
  - `search_hotels_tool()` - Hotel/stays search (existing)
  - `fetch_hotel_rates_tool()` - Hotel rate details (existing)
  - `create_quote_tool()` - Hotel booking quotes (existing)
  - `create_booking_tool()` - Hotel booking creation (existing)
  - **NEW**: `search_flights_tool()` - Flight search with Duffel API
  - **NEW**: `fetch_flight_quote_tool()` - Flight offer quote refresh
  - **NEW**: `create_flight_booking_tool()` - Flight booking creation

### Enhanced Project Structure
```
graph/src/
├── agent/
│   └── graph.py                    # Updated with flight tools
├── duffel_client/
│   ├── client.py                   # Main Duffel API client
│   ├── endpoints/
│   │   ├── flights.py             # NEW: Flight API endpoints
│   │   └── stays.py               # Hotel/stays endpoints  
│   └── models/
│       ├── flights.py             # NEW: Flight Pydantic models
│       └── stays.py               # Hotel/stays models
└── config.py                      # Configuration management
```

### Configuration Updates
- **Environment Variables**: Added DUFFEL_API_TOKEN requirement for flight functionality
- **Tool Registration**: Updated agent tool lists to include all flight tools
- **Error Handling**: Enhanced Duffel API error handling for both hotels and flights

### Removed/Changed
- **UI Mapping**: Removed custom UI mapping for flight results (now uses generic JSON renderer)
- **Tool Lists**: Updated all tool registration points to include new flight tools

## [Unreleased]

### Added
- Complete LangGraph agent implementation with tools and development server setup
- Basic tool set including time retrieval, mathematical calculations, and web search (mock)
- Human-in-the-loop workflow capabilities using GraphInterrupt
- LangGraph development server configuration for local development
- Comprehensive project setup with uv package management
- Python 3.11+ requirement and virtual environment configuration
- Environment variable configuration system
- Complete documentation and setup instructions

### Technical Implementation
- **Agent Framework**: LangGraph with state management and tool calling
- **Development Server**: `langgraph dev` with hot reloading on port 2024
- **Package Management**: uv with `langgraph-cli[inmem]` for development mode
- **Tools Implemented**:
  - `get_current_time()` - Current date and time retrieval
  - `calculate_simple_math(expression)` - Safe arithmetic evaluation
  - `search_web(query)` - Mock web search functionality
- **State Management**: Conversation memory and message history
- **Error Handling**: Graceful tool error handling and user feedback

### Project Structure
```
graph/
├── src/agent/
│   ├── __init__.py          # Package initialization
│   └── graph.py             # Complete LangGraph agent implementation
├── langgraph.json           # LangGraph server configuration
├── pyproject.toml           # uv dependencies with langgraph-cli[inmem]
├── .python-version          # Python 3.11 requirement
├── env.example              # Environment template (OPENAI_API_KEY)
└── README.md                # Detailed setup and usage instructions
```

### Configuration Files
- **langgraph.json**: Server configuration pointing to `src.agent.graph:graph`
- **pyproject.toml**: Updated with all required dependencies including LangChain and OpenAI
- **.python-version**: Set to 3.11 for langgraph dev server compatibility
- **env.example**: Template for required environment variables

### Development Workflow
- Local development server accessible at `http://127.0.0.1:2024`
- API documentation available at `http://127.0.0.1:2024/docs`
- LangGraph Studio UI integration at `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`
- Hot reloading for development efficiency

### Dependencies Added
- `langgraph>=0.4.8` - Core graph framework
- `langgraph-cli[inmem]>=0.3.0` - Development server with in-memory runtime
- `langchain>=0.3.0` - LangChain framework integration
- `langchain-openai>=0.2.0` - OpenAI LLM integration
- `langchain-community>=0.3.0` - Community tools and integrations
- `python-dotenv>=1.0.0` - Environment variable management
- `httpx>=0.27.0` - HTTP client for API requests

### Documentation
- Updated main README.md with current implementation status
- Added detailed setup instructions for immediate use
- Documented available tools and example interactions
- Included troubleshooting and development workflow information
- Created comprehensive README in graph/ directory

### Removed
- `graph/hello.py` - Placeholder file removed in favor of complete agent implementation

## [0.1.0] - 2024-06-16

### Project Initialization
- Initial project structure and documentation
- Project concept and technical architecture planning
- Linear project setup and team organization
- Development roadmap and phase planning

---

## Development Notes

### Current Status
✅ **Phase 1 Complete**: Basic LangGraph agent with tools and dev server
- Functional LangGraph agent with multiple tools
- Working development server setup
- Ready for UI integration and Duffel API implementation

✅ **Phase 2 Partial**: Duffel API integration for flights
- Complete flight search and booking functionality
- Flight tools integrated with comprehensive validation
- Duffel API client architecture implemented
- Flight models and endpoints established

### Next Steps
🚧 **Phase 2 Completion**: Agent Chat UI setup and hotels integration
- Agent Chat UI implementation in `ui/` directory
- Complete UI ↔ Graph server communication establishment
- Enhanced hotel/stays functionality (basic implementation exists)

### Technical Decisions
- **Python 3.11+**: Required for langgraph dev server functionality
- **uv Package Management**: Modern Python dependency management
- **In-Memory Runtime**: Development-focused setup for rapid iteration
- **OpenAI Integration**: GPT-3.5-turbo for language model capabilities
- **No Custom Checkpointer**: Leveraging LangGraph API's built-in persistence 
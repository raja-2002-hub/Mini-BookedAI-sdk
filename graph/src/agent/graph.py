"""
LangGraph Agent for BookedAI
"""
from typing import Annotated, List, Dict, Any, Sequence, Optional
from typing_extensions import TypedDict
import os
import logging
from datetime import date, datetime
from dotenv import load_dotenv

import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import SecretStr

from langgraph.graph import StateGraph, START, END
from langgraph.graph.ui import AnyUIMessage, ui_message_reducer, push_ui_message
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.errors import GraphInterrupt

# Import our Duffel client
from src.duffel_client.endpoints.stays import search_hotels
from src.duffel_client.client import DuffelAPIError
from src.config import config

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TOOL_UI_MAPPING = {
    "search_hotels_tool": "hotelResults",
    "search_flights_tool": "flightResults",
}

# Define the agent state
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]  
    ui: Annotated[Sequence[AnyUIMessage], ui_message_reducer]
    ui_enabled: Optional[bool]

# Define tools
@tool
def get_current_time() -> str:
    """Get the current time and date."""
    logger.debug("get_current_time tool called")    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"Current time retrieved: {current_time}")
    return current_time


@tool  
def calculate_simple_math(expression: str) -> str:
    """Calculate simple mathematical expressions. Only supports basic arithmetic (+, -, *, /)."""
    logger.debug(f"calculate_simple_math tool called with expression: {expression}")
    try:
        # Basic safety check - only allow numbers, operators, and parentheses
        allowed_chars = set('0123456789+-*/().')
        if not all(c in allowed_chars or c.isspace() for c in expression):
            return "Error: Expression contains invalid characters"
        
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error calculating expression: {str(e)}"


@tool
def search_web(query: str) -> str:
    """Search the web for information. This is a mock tool for demonstration."""
    logger.debug(f"search_web tool called with query: {query}")
    # This is a mock implementation - in a real scenario you'd integrate with a search API
    logger.info(f"Performing mock web search for: {query}")
    result = f"Mock search results for: {query}. This would normally return real web search results."
    logger.debug("Mock web search completed")
    return result

@tool
async def search_hotels_tool(
    location: str,
    check_in_date: str,
    check_out_date: str,
    adults: int = 1,
    children: int = 0,
    max_results: int = 5
) -> str:
    """Search for hotels.
    
    Args:
    - location: City name (e.g., "Tokyo")
    - check_in_date: Check-in date (YYYY-MM-DD)
    - check_out_date: Check-out date (YYYY-MM-DD)
    - adults: Number of adults (default: 1)
    - children: Number of children (default: 0)
    - max_results: Max number of results (default: 5)

    Ask the user for any missing required details.
        
    Returns:
        A JSON string with hotel search results.
    """
    logger.info(f"Hotel search initiated - Location: {location}, Check-in: {check_in_date}, Check-out: {check_out_date}, Adults: {adults}, Children: {children}, Max results: {max_results}")
    try:
        # Validate date format and parse dates
        logger.debug("Validating and parsing input dates")
        try:
            check_in = datetime.strptime(check_in_date, "%Y-%m-%d").date()
            check_out = datetime.strptime(check_out_date, "%Y-%m-%d").date()
            logger.debug(f"Dates parsed successfully - Check-in: {check_in}, Check-out: {check_out}")
        except ValueError as ve:
            logger.warning(f"Date parsing failed for check-in: {check_in_date}, check-out: {check_out_date} - {ve}")
            return "Error: Dates must be in YYYY-MM-DD format (e.g., '2024-12-15')"
        
        # Validate date logic
        logger.debug("Validating date logic")
        if check_out <= check_in:
            logger.warning(f"Invalid date range: check-out ({check_out}) not after check-in ({check_in})")
            return "Error: Check-out date must be after check-in date"
        
        if check_in < date.today():
            logger.warning(f"Check-in date ({check_in}) is in the past")
            return "Error: Check-in date cannot be in the past"
        
        # Validate guest counts
        logger.debug(f"Validating guest counts - Adults: {adults}, Children: {children}")
        if adults < 1 or children < 0:
            logger.warning(f"Invalid guest counts - Adults: {adults}, Children: {children}")
            return "Error: Must have at least 1 adult guest, children cannot be negative"
        
        # Validate max_results
        if max_results < 1 or max_results > 20:
            logger.warning(f"Invalid max_results: {max_results} (must be 1-20)")
            return "Error: max_results must be between 1 and 20"
        
        # Check if Duffel API token is configured
        logger.debug("Checking Duffel API configuration")
        if not config.DUFFEL_API_TOKEN:
            logger.error("Duffel API token not configured")
            return "Hotel search is currently unavailable. Please configure the Duffel API token."
        
        # Perform hotel search
        logger.info(f"Calling Duffel API for hotel search in {location}")
        response = await search_hotels(
            location=location,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children,
            limit=max_results
        )
        logger.info("Hotel search completed")

        # Use the new JSON formatter
        json_data = response.format_for_json(max_results=max_results)
        return json.dumps(json_data)
        
    except DuffelAPIError as e:
        logger.error(f"Duffel API error during hotel search: {e}")
        # Handle both dictionary and object-style error formats
        error_title = "API Error"
        error_detail = "Please try again later"
        
        if hasattr(e, 'error'):
            if isinstance(e.error, dict):
                error_title = e.error.get('title', 'API Error')
                error_detail = e.error.get('detail', 'Please try again later')
            elif hasattr(e.error, 'title'):
                error_title = e.error.title
                error_detail = getattr(e.error, 'detail', 'Please try again later')
        
        return f"Hotel search error: {error_title} - {error_detail}"
    except Exception as e:
        logger.error(f"Unexpected error during hotel search: {str(e)}", exc_info=True)
        return f"Unexpected error during hotel search: {str(e)}"

# Create the LLM
def create_llm():
    """Create and configure the language model."""
    logger.debug("Creating LLM instance")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable not set")
        raise ValueError("OPENAI_API_KEY environment variable is required")

    logger.info("LLM instance created successfully with gpt-3.5-turbo")
    return ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.1,
        api_key=SecretStr(api_key)
    )

def should_push_ui_message(tool_message: ToolMessage, tool_data: Dict[str, Any]) -> tuple[bool, str | None]:
    """
    Determine if we should push a UI message based on tool output.
    
    Returns:
        tuple: (should_push, ui_type)
    """
    tool_name = tool_message.name
    
    # Check if tool has UI mapping
    ui_type = TOOL_UI_MAPPING.get(tool_name)
    if not ui_type:
        return False, None
    
    # Tool-specific logic
    if tool_name == "search_hotels_tool":
        # Only push UI if we have actual hotel results
        hotels = tool_data.get("hotels", [])
        if isinstance(hotels, list) and len(hotels) > 0:
            # Verify hotels have required fields for UI
            first_hotel = hotels[0]
            required_fields = ["name", "location", "price"]
            if all(field in first_hotel for field in required_fields):
                return True, ui_type
        return False, None
    
    elif tool_name == "search_flights_tool":
        # Only push UI if we have valid flight results
        flights = tool_data.get("flights", [])
        if isinstance(flights, list) and len(flights) > 0:
            # Verify flights have required fields
            first_flight = flights[0]
            required_fields = ["airline", "departure", "arrival", "price"]
            if all(field in first_flight for field in required_fields):
                return True, ui_type
        return False, None
    
    # For other tools, check if data is rich enough for UI
    elif isinstance(tool_data, dict) and len(tool_data) > 2:
        # Has enough structured data to warrant UI
        return True, ui_type
    
    return False, None

# Define the agent logic
def agent_node(state: AgentState) -> Dict[str, Any]:
    """Main agent reasoning node."""

    logger.info("Agent node started - processing conversation state")    

    llm = create_llm()
    tools = [get_current_time, calculate_simple_math, search_web, search_hotels_tool]
    llm_with_tools = llm.bind_tools(tools)
    
    # System prompt
    system_prompt = """
<identity>
You are a helpful AI assistant for BookedAI, specializing in travel assistance
</identity>

<instructions>
Help the user with their travel plans.
</instructions>

<rules>
Only discuss travel related topics.
</rules>
"""
    
    # Create messages with system prompt
    messages = [HumanMessage(content=system_prompt)] +  state["messages"]
    for idx, msg in enumerate(messages):
            logger.info(f"Message {idx}: role={getattr(msg, 'role', None)}, content={getattr(msg, 'content', None)}, tool_calls={getattr(msg, 'tool_calls', None)}")
    
    response = llm_with_tools.invoke(messages)

    ui_enabled = state.get("ui_enabled", True)
    logger.info(f"UI enabled: {ui_enabled}")

    # Handle push UI message with improved logic for multiple tool calls
    if ui_enabled:
        # Find all recent tool messages that could need UI components
        # Look for tool messages that came after the last human/AI message
        recent_tool_messages = []
        
        # Work backwards from the end to find recent tool calls in this turn
        for i in range(len(state["messages"]) - 1, -1, -1):
            msg = state["messages"][i]
            if isinstance(msg, ToolMessage):
                recent_tool_messages.insert(0, msg)  # Keep chronological order
            elif msg.type in ["human", "ai"]:
                # Stop when we hit a non-tool message (start of this tool sequence)
                break
        
        logger.info(f"Found {len(recent_tool_messages)} recent tool messages to process for UI")
        
        # Process each tool message for potential UI
        ui_components_created = 0
        for tool_message in recent_tool_messages:
            try:
                # Parse tool result data
                tool_data = json.loads(tool_message.content)
                
                # Use decision function to determine if UI should be pushed
                should_push, ui_type = should_push_ui_message(tool_message, tool_data)
                
                if should_push and ui_type:
                    logger.info(f"Pushing UI message for {ui_type} from tool {tool_message.name} with {len(tool_data)} data fields")
                    push_ui_message(ui_type, tool_data, message=response)
                    ui_components_created += 1
                    
                else:
                    logger.debug(f"Not pushing UI for {tool_message.name}: insufficient or invalid data for UI display")
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool result as JSON for UI from {tool_message.name}: {e}")
            except Exception as e:
                logger.error(f"Error processing UI message for {tool_message.name}: {e}", exc_info=True)
        
        if ui_components_created > 0:
            logger.info(f"Created {ui_components_created} UI components for this agent response")
            # Optionally modify the text response to be more concise since UI will show details
            logger.debug("UI components will show detailed results, keeping text response concise")

    return {"messages": [response]}


def human_input_node(state: AgentState) -> Dict[str, Any]:
    """Node for handling human input interrupts."""
    logger.info("Human input node triggered - pausing for user interaction")
    # This will pause execution and wait for human input
    raise GraphInterrupt("Please provide additional input or guidance for the agent.")


def should_continue(state: AgentState) -> str:
    """Determine if the agent should continue or end."""
    logger.debug("Evaluating should_continue condition")
    last_message = state["messages"][-1]
    
    # If the last message has tool calls, continue to tools
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        logger.info("Last message has tool calls - continuing to tools")
        return "tools"
    
    # Check if we need human input
    if "human input needed" in last_message.content.lower():
        logger.info("Last message has human input needed - continuing to human input")
        return "human_input"
        
    # Otherwise, end the conversation
    logger.info("No tool calls or human input needed - ending conversation")
    return "end"


# Create the graph
def create_graph():
    """Create and configure the LangGraph workflow."""
    logger.info("Creating LangGraph workflow")
    
    try:
        # Initialize tools
        tools = [get_current_time, calculate_simple_math, search_web, search_hotels_tool]
        logger.debug(f"Initializing ToolNode with {len(tools)} tools: {[tool.name for tool in tools]}")
        tool_node = ToolNode(tools)

        # Create the graph
        logger.debug("Creating StateGraph with AgentState")
        workflow = StateGraph(AgentState)

        # Add nodes
        logger.debug("Adding nodes to workflow")
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        workflow.add_node("human_input", human_input_node)
        logger.info("Added 3 nodes: agent, tools, human_input")

        # Set the entry point
        logger.debug("Setting entry point from START to agent")
        workflow.add_edge(START, "agent")

        # Add conditional edges
        logger.debug("Adding conditional edges from agent node")
        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {
                "tools": "tools",
                "human_input": "human_input", 
                "end": END
            }
        )

        # After tools, go back to agent
        logger.debug("Adding edge from tools back to agent")
        workflow.add_edge("tools", "agent")

        # After human input, go back to agent
        logger.debug("Adding edge from human_input back to agent")
        workflow.add_edge("human_input", "agent")

        # Compile the graph without custom checkpointer (LangGraph API handles persistence)
        logger.info("Compiling workflow graph")
        compiled_graph = workflow.compile()
        logger.info("LangGraph workflow created and compiled successfully")

        return compiled_graph

    except Exception as e:
        logger.error(f"Error creating graph: {str(e)}", exc_info=True)
        raise   


# Export the compiled graph
logger.info("Initializing BookedAI agent graph...")
graph = create_graph() 
logger.info("BookedAI agent graph successfully initialized and ready for use")
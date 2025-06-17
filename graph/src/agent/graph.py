"""
LangGraph Agent for BookedAI
"""
from typing import Annotated, List, Dict, Any, Optional
from typing_extensions import TypedDict
import os
from datetime import date, datetime
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.errors import GraphInterrupt

# Import our Duffel client
from ..duffel_client.endpoints.stays import search_hotels
from ..duffel_client.client import DuffelAPIError
from ..config import config

# Load environment variables
load_dotenv()

# Define the agent state
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]


# Define tools
@tool
def get_current_time() -> str:
    """Get the current time and date."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool  
def calculate_simple_math(expression: str) -> str:
    """Calculate simple mathematical expressions. Only supports basic arithmetic (+, -, *, /)."""
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
    # This is a mock implementation - in a real scenario you'd integrate with a search API
    return f"Mock search results for: {query}. This would normally return real web search results."


@tool
async def search_hotels_tool(
    location: str,
    check_in_date: str,
    check_out_date: str,
    adults: int = 1,
    children: int = 0,
    max_results: int = 5
) -> str:
    """Search for hotels in a specific location and date range.
    
    Args:
        location: City or location name to search for hotels (e.g., "Tokyo", "New York", "Paris")
        check_in_date: Check-in date in YYYY-MM-DD format (e.g., "2024-12-15")  
        check_out_date: Check-out date in YYYY-MM-DD format (e.g., "2024-12-22")
        adults: Number of adult guests (default: 1)
        children: Number of child guests (default: 0)
        max_results: Maximum number of hotel results to return (default: 5)
        
    Returns:
        Formatted string with hotel search results including names, ratings, and prices
    """
    try:
        # Validate date format and parse dates
        try:
            check_in = datetime.strptime(check_in_date, "%Y-%m-%d").date()
            check_out = datetime.strptime(check_out_date, "%Y-%m-%d").date()
        except ValueError:
            return "Error: Dates must be in YYYY-MM-DD format (e.g., '2024-12-15')"
        
        # Validate date logic
        if check_out <= check_in:
            return "Error: Check-out date must be after check-in date"
        
        if check_in < date.today():
            return "Error: Check-in date cannot be in the past"
        
        # Validate guest counts
        if adults < 1 or children < 0:
            return "Error: Must have at least 1 adult guest, children cannot be negative"
        
        # Validate max_results
        if max_results < 1 or max_results > 20:
            return "Error: max_results must be between 1 and 20"
        
        # Check if Duffel API token is configured
        if not config.DUFFEL_API_TOKEN:
            return "Hotel search is currently unavailable. Please configure the Duffel API token."
        
        # Perform hotel search
        response = await search_hotels(
            location=location,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children,
            limit=max_results
        )
        
        # Format results for display
        return response.format_for_display(max_results=max_results)
        
    except DuffelAPIError as e:
        return f"Hotel search error: {e.error.title} - {e.error.detail or 'Please try again later'}"
    except Exception as e:
        return f"Unexpected error during hotel search: {str(e)}"


# Create the LLM
def create_llm():
    """Create and configure the language model."""
    return ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.1,
        api_key=os.getenv("OPENAI_API_KEY")
    )


# Define the agent logic
def agent_node(state: AgentState) -> Dict[str, Any]:
    """Main agent reasoning node."""
    llm = create_llm()
    tools = [get_current_time, calculate_simple_math, search_web, search_hotels_tool]
    llm_with_tools = llm.bind_tools(tools)
    
    # System prompt
    system_prompt = """You are a helpful AI assistant for BookedAI, specializing in travel assistance. You have access to the following tools:

1. **get_current_time()** - Get the current date and time
2. **calculate_simple_math(expression)** - Perform arithmetic calculations  
3. **search_web(query)** - Search for general information (mock implementation)
4. **search_hotels_tool(location, check_in_date, check_out_date, adults, children, max_results)** - Search for hotels and accommodations

**Hotel Search Capabilities:**
- Search hotels in any city or location worldwide
- Dates must be in YYYY-MM-DD format (e.g., "2024-12-15")
- Can specify number of adult and child guests
- Returns hotel names, ratings, locations, and pricing information

**Important Guidelines:**
- Always validate dates are in the correct format and logical (check-out after check-in, not in the past)
- When users request hotel searches, use the search_hotels_tool with appropriate parameters
- If users provide incomplete information, ask clarifying questions about:
  - Specific dates (if they say "next month" or "December", ask for exact dates)
  - Number of guests (adults and children)
  - Location (if ambiguous, ask for city name)
- Be helpful, accurate, and conversational in your responses
- Format hotel results in a user-friendly way
- If you encounter errors, explain them clearly and suggest corrections

**Example interactions:**
- "Find hotels in Tokyo for December 15-22" → Ask for number of guests, then search
- "Hotels in Paris for 2 adults, December 15-17" → Use search_hotels_tool with those parameters
- "What time is it?" → Use get_current_time tool
- "Calculate 25 * 4" → Use calculate_simple_math tool

Be conversational and helpful while being precise with tool usage."""
    
    # Create messages with system prompt
    messages = [HumanMessage(content=system_prompt)] + state["messages"]
    
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def human_input_node(state: AgentState) -> Dict[str, Any]:
    """Node for handling human input interrupts."""
    # This will pause execution and wait for human input
    raise GraphInterrupt("Please provide additional input or guidance for the agent.")


def should_continue(state: AgentState) -> str:
    """Determine if the agent should continue or end."""
    last_message = state["messages"][-1]
    
    # If the last message has tool calls, continue to tools
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    
    # Check if we need human input
    if "human input needed" in last_message.content.lower():
        return "human_input"
        
    # Otherwise, end the conversation
    return "end"


# Create the graph
def create_graph():
    """Create and configure the LangGraph workflow."""
    # Initialize tools
    tools = [get_current_time, calculate_simple_math, search_web, search_hotels_tool]
    tool_node = ToolNode(tools)
    
    # Create the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("human_input", human_input_node)
    
    # Set the entry point
    workflow.add_edge(START, "agent")
    
    # Add conditional edges
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
    workflow.add_edge("tools", "agent")
    
    # After human input, go back to agent
    workflow.add_edge("human_input", "agent")
    
    # Compile the graph without custom checkpointer (LangGraph API handles persistence)
    return workflow.compile()


# Export the compiled graph
graph = create_graph() 
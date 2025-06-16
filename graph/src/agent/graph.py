"""
LangGraph Agent for BookedAI
"""
from typing import Annotated, List, Dict, Any, Optional
from typing_extensions import TypedDict
import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.errors import GraphInterrupt

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
    tools = [get_current_time, calculate_simple_math, search_web]
    llm_with_tools = llm.bind_tools(tools)
    
    # System prompt
    system_prompt = """You are a helpful AI assistant for BookedAI. You can:
    
    1. Get the current time and date
    2. Perform simple mathematical calculations
    3. Search the web for information (mock implementation)
    
    Be helpful, accurate, and concise in your responses. If you need to use tools, explain what you're doing.
    If you're unsure about something, ask for clarification.
    """
    
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
    tools = [get_current_time, calculate_simple_math, search_web]
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
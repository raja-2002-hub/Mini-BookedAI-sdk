"""
LangGraph Agent for BookedAI
"""
from typing import Annotated, List, Dict, Any, Sequence, Optional
from typing_extensions import TypedDict
import os
import logging
from datetime import date, datetime
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException
import dateparser
import re

# Try to load dotenv, but don't fail if it's not available (e.g., in production)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, likely in production where env vars are provided directly
    pass

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
from src.duffel_client.endpoints.stays import search_hotels, fetch_hotel_rates, create_quote, create_booking
from src.duffel_client.endpoints.flights import search_flights, format_flights_markdown, get_seat_maps,fetch_flight_offer, create_flight_booking, list_airline_initiated_changes, update_airline_initiated_change, accept_airline_initiated_change
from src.duffel_client.client import DuffelAPIError
from src.config import config

# --- Flight Order Change Tools ---
from src.duffel_client.endpoints.flights import (
    create_order_change_request_api,
    get_order_change_request_api,
    list_order_change_offers_api,
    get_order_change_offer_api,
    confirm_order_change_api,
    get_order_change_api,
    create_order_change_api,
    list_order_cancellations,
    get_order_cancellation,
    confirm_order_cancellation,
    create_order_cancellation,
)

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TOOL_UI_MAPPING = {
    "search_hotels_tool": "hotelResults",
    "search_flights_tool": "flightResults",

}

# Log UI-related imports and configurations
logger.info(f"[MODULE INIT] TOOL_UI_MAPPING loaded: {TOOL_UI_MAPPING}")
try:
    from langgraph.graph.ui import push_ui_message
    logger.info("[MODULE INIT] ✓ push_ui_message import successful")
except ImportError as e:
    logger.error(f"[MODULE INIT] ✗ Failed to import push_ui_message: {e}")
    raise

# Define the agent state
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]  
    ui: Annotated[Sequence[AnyUIMessage], ui_message_reducer]
    ui_enabled: Optional[bool]

def parse_and_normalize_date(input_date: str) -> str:
    """
    Parse a date string using dateparser and ensure it is in the future.
    If the date is in the past, roll it forward to the next year.
    Returns a string in YYYY-MM-DD format.
    """
    today = date.today()
    try:
        dt = dateparser.parse(input_date, settings={'PREFER_DATES_FROM': 'future'})
        if not dt:
            return input_date  # fallback if parsing fails
        dt = dt.date()
        if dt < today:
            try:
                dt = dt.replace(year=today.year)
                if dt < today:
                    dt = dt.replace(year=today.year + 1)
            except ValueError:
                dt = today
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return input_date


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
def validate_phone_number_tool(phone: str, region: str = "AU") -> str:
    """
    Use this tool to validate and format phone numbers to E.164 format before making a booking or whenever a user provides a phone number.
    Returns the formatted phone number or an error message if invalid.
    """
    try:
        parsed = phonenumbers.parse(phone, region)
        if not phonenumbers.is_valid_number(parsed):
            return "Error: Invalid phone number"
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException as e:
        return f"Error: Invalid phone number: {e}"

@tool
async def search_flights_tool(
    slices: list,
    passengers: int = 1,
    cabin_class: str = "economy",
    max_results: int = 5
) -> str:
    """
    Search for flights (supports one-way, round-trip, and multi-city itineraries).

    Use this tool for any flight search, including multi-city or multi-leg trips. 
    If the user asks for a journey with multiple legs (e.g., "from A to B and then B to C"), 
    combine all legs into a single call by providing a 'slices' list with each segment.

    Args:
        slices: List of flight segments, each as a dict with 'origin', 'destination', and 'departure_date'.
            Example for multi-city:
                [
                    {"origin": "MEL", "destination": "SYD", "departure_date": "2025-11-08"},
                    {"origin": "SYD", "destination": "BER", "departure_date": "2025-11-08"}
                ]
        passengers: Number of passengers (default: 1)
        cabin_class: Cabin class (economy, premium_economy, business, first)
        max_results: Max number of results (default: 5)

    Returns:
        A JSON string with flight search results.

    Example user queries:
        - "I want to book a flight from Melbourne to Sydney and then from Sydney to Berlin on November 8, 2025."
        - "Book a multi-city trip: NYC to London on June 1, then London to Paris on June 5."
    Example tool call:
        search_flights_tool(
            slices=[
                {"origin": "NYC", "destination": "LON", "departure_date": "2024-06-01"},
                {"origin": "LON", "destination": "PAR", "departure_date": "2024-06-05"}
            ],
            passengers=1,
            cabin_class="economy"
        )
    """
    logger.info(f"Flight search initiated - Slices: {slices}, Passengers: {passengers}, Cabin: {cabin_class}, Max results: {max_results}")
    try:
        # Validate slices
        if not isinstance(slices, list) or not slices:
            return "Error: 'slices' must be a non-empty list of segment dicts."
        for seg in slices:
            if not all(k in seg for k in ("origin", "destination", "departure_date")):
                return "Error: Each slice must have 'origin', 'destination', and 'departure_date'."
            # Date validation
            try:
                dep_date = datetime.strptime(seg["departure_date"], "%Y-%m-%d").date()
                if dep_date < date.today():
                    return f"Error: Departure date {dep_date} cannot be in the past"
            except Exception:
                return f"Error: Invalid date format for departure_date in slice: {seg['departure_date']}"

        # Validate passenger count
        logger.debug(f"Validating passenger count: {passengers}")
        if passengers < 1 or passengers > 9:
            return "Error: Number of passengers must be between 1 and 9"
        if max_results < 1 or max_results > 20:
            return "Error: max_results must be between 1 and 20"
        if not config.DUFFEL_API_TOKEN:
            return "Flight search is currently unavailable. Please configure the Duffel API token."

        response = await search_flights(
            slices=slices,
            passengers=passengers,
            cabin_class=cabin_class,
            limit=max_results
        )
        json_data = response.format_for_json(max_results=max_results) if hasattr(response, "format_for_json") else response
        return json.dumps(json_data)
    except DuffelAPIError as e:
        return f"Flight search error: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error during flight search: {str(e)}", exc_info=True)
        return f"Unexpected error during flight search: {str(e)}"

@tool
async def search_hotels_tool(
    location: str,
    check_in_date: str,
    check_out_date: str,
    adults: int = None,
    children: int = None,
    max_results: int = 5
) -> str:

    """
    Searches for hotels based on location, dates, and guest details.

    Location and dates are required, while the number of adults and children is optional. If not provided, the search will assume 1 adult and 0 children—no need to ask the user or mention these defaults unless you're quoting or booking.

    Check-in and check-out dates can be entered in natural language or standard formats, but they must resolve to future dates. If a past date is given, it’ll be automatically adjusted to the next valid future date. The check-out date must always be after the check-in date, or an error will be returned.

    If any required information is missing (except adults or children), ask the user for clarification.

    By default, up to 5 results will be returned, unless a different max is specified.
    """

    logger.info(f"Hotel search initiated - Location: {location}, Check-in: {check_in_date}, Check-out: {check_out_date}, Adults: {adults}, Children: {children}, Max results: {max_results}")
    try:
        if adults is None:
            adults = 1
        if children is None:
            children = 0
        # Validate date format and parse dates
        check_in_date = parse_and_normalize_date(check_in_date)
        check_out_date = parse_and_normalize_date(check_out_date)
        logger.debug (f"Normalized dates - Check-in: {check_in_date}, Check-out: {check_out_date}")
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
            elif hasattr(e, 'error') and hasattr(e.error, 'title'):
                error_title = e.error.title
                error_detail = getattr(e.error, 'detail', 'Please try again later')
        
        return f"Hotel search error: {error_title} - {error_detail}"
    except Exception as e:
        logger.error(f"Unexpected error during hotel search: {str(e)}", exc_info=True)
        return f"Unexpected error during hotel search: {str(e)}"

@tool
async def fetch_hotel_rates_tool(search_result_id: str) -> str:
    """Fetch detailed room and rate information for a specific hotel.
    
    Args:
        search_result_id: The search result ID from hotel search (srr_...)
        
    Returns:
        JSON string with detailed room/rate information including rate IDs (rat_...)
    """
    logger.info(f"Fetching rates for search result: {search_result_id}")
    
    # Validate search_result_id format
    if not search_result_id or not search_result_id.startswith("srr_"):
        return "Error: search_result_id must start with 'srr_' and be a valid search result ID"
    
    # Check if Duffel API token is configured
    if not config.DUFFEL_API_TOKEN:
        logger.error("Duffel API token not configured")
        return "Rate fetching is currently unavailable. Please configure the Duffel API token."
    
    try:        
        response = await fetch_hotel_rates(search_result_id)
        logger.info(f"Successfully fetched rates for {search_result_id}")
        
        return json.dumps(response)
        
    except DuffelAPIError as e:
        logger.error(f"Duffel API error during rate fetch: {e}")
        error_title = "API Error"
        error_detail = "Please try again later"
        
        if hasattr(e, 'error'):
            if isinstance(e.error, dict):
                error_title = e.error.get('title', 'API Error')
                error_detail = e.error.get('detail', 'Please try again later')
            elif hasattr(e.error, 'title'):
                error_title = e.error.title
                error_detail = getattr(e.error, 'detail', 'Please try again later')
        
        return f"Rate fetch error: {error_title} - {error_detail}"
    except Exception as e:
        logger.error(f"Unexpected error during rate fetch: {str(e)}", exc_info=True)
        return f"Unexpected error during rate fetch: {str(e)}"

@tool
async def create_quote_tool(rate_id: str) -> str:
    """Create a Duffel stay quote for a given rate.

    Args:
        rate_id: The Duffel rate identifier (e.g. 'rat_XXXX').

    Returns:
        JSON string of the quote response, or an error message.
    """
    logger.info(f"Quote creation initiated for rate_id: {rate_id}")

    # Basic validation
    if not rate_id or not rate_id.startswith("rat_"):
        return "Error: `rate_id` must start with 'rat_' and be a valid Duffel rate ID."

    if not config.DUFFEL_API_TOKEN:
        logger.error("Duffel API token not configured")
        return "Quote creation is currently unavailable. Please configure the Duffel API token."

    try:
        response = await create_quote(rate_id)
        logger.info("Quote created successfully")
        return json.dumps(response)

    except DuffelAPIError as e:
        logger.error(f"Duffel API error during quote creation: {e}")
        # Friendly error surface
        title = "API Error"
        detail = "Please try again later"
        if hasattr(e, "error"):
            if isinstance(e.error, dict):
                title = e.error.get("title", title)
                detail = e.error.get("detail", detail)
            elif hasattr(e.error, "title") and not callable(getattr(e.error, "title", None)):
                title = getattr(e.error, "title", title)
                detail = getattr(e.error, "detail", detail)
            else:
                title = str(e.error) if e.error else "API Error"
        return f"Quote creation error: {title} - {detail}"

    except Exception as exc:
        logger.error("Unexpected error during quote creation", exc_info=True)
        return f"Unexpected error during quote creation: {exc}"

@tool
async def create_booking_tool(
    quote_id: str,
    guests: list,
    email: str,
    stay_special_requests: str = "",
    phone_number: str = ""
) -> str:
    """
    Book a hotel stay using a Duffel quote.
    Args:
        quote_id: The quote ID (quo_...)
        guests: List of guest dicts (given_name, family_name, born_on)
        email: Contact email
        stay_special_requests: (optional) Special requests
        phone_number: (optional) Contact number
    Returns:
        JSON string of the booking response, or an error message.
    """
    logger.info(f"Booking creation initiated for quote_id: {quote_id}")

    if not quote_id or not quote_id.startswith("quo_"):
        return "Error: `quote_id` must start with 'quo_' and be a valid Duffel quote ID."

    if not config.DUFFEL_API_TOKEN:
        logger.error("Duffel API token not configured")
        return "Booking creation is currently unavailable. Please configure the Duffel API token."

    try:
        response = await create_booking(
            quote_id, guests, email, stay_special_requests, phone_number
        )
        logger.info("Booking created successfully")
        return json.dumps(response)

    except DuffelAPIError as e:
        logger.error(f"Duffel API error during booking creation: {e}")
        title = "API Error"
        detail = "Please try again later"
        if hasattr(e, "error"):
            if isinstance(e.error, dict):
                title = e.error.get("title", title)
                detail = e.error.get("detail", detail)
            elif hasattr(e.error, "title") and not callable(getattr(e.error, "title", None)):
                title = getattr(e.error, "title", "API Error")
                detail = getattr(e.error, "detail", detail)
            else:
                title = str(e.error) if e.error else "API Error"
        return f"Booking creation error: {title} - {detail}"

    except Exception as exc:
        logger.error("Unexpected error during booking creation", exc_info=True)
        return f"Unexpected error during booking creation: {exc}"

@tool
async def fetch_flight_quote_tool(offer_id: str) -> str:
    """Fetch the latest details for a flight offer (quote refresh).
    Args:
        offer_id: The Duffel offer ID (off_...)
    Returns:
        JSON string of the refreshed offer/quote with passenger IDs needed for booking.
    """
    logger.info(f"Fetching flight quote for offer_id: {offer_id}")
    if not offer_id or not offer_id.startswith("off_"):
        return "Error: `offer_id` must start with 'off_' and be a valid Duffel offer ID."
    if not config.DUFFEL_API_TOKEN:
        logger.error("Duffel API token not configured")
        return "Quote fetching is currently unavailable. Please configure the Duffel API token."
    try:
        response = await fetch_flight_offer(offer_id)
        logger.info("Flight quote fetched successfully")
        
        # Add helpful information about passenger IDs
        passengers = response.get("data", {}).get("passengers", [])
        if passengers:
            logger.info(f"Quote contains {len(passengers)} passengers with IDs: {[p.get('id') for p in passengers]}")
        
        return json.dumps(response)
    except DuffelAPIError as e:
        logger.error(f"Duffel API error during quote fetch: {e}")
        title = "API Error"
        detail = "Please try again later"
        if hasattr(e, "error"):
            if isinstance(e.error, dict):
                title = e.error.get("title", title)
                detail = e.error.get("detail", detail)
            elif hasattr(e.error, "title") and not callable(getattr(e.error, "title", None)):
                title = getattr(e.error, "title", title)
                detail = getattr(e.error, "detail", detail)
            else:
                title = str(e.error) if e.error else "API Error"
        return f"Quote fetch error: {title} - {detail}"
    except Exception as exc:
        logger.error("Unexpected error during quote fetch", exc_info=True)
        return f"Unexpected error during quote fetch: {exc}"

@tool
async def create_flight_booking_tool(
    offer_id: str,
    passengers: list,
    payments: list,
    **kwargs
) -> str:
    """
    Book a flight using a Duffel offer.
    Example:
        payments = [{
            "type": "balance",
            "amount": "1041.41",
            "currency": "AUD"
        }]
    Args:
        offer_id: The offer ID (off_...)
        passengers: List of passenger dicts. Each passenger MUST have:
                   - id (Duffel-generated, from offer)
                   - given_name, family_name, born_on, email, phone_number, etc.
        payments: List of payment dicts (see Duffel API)
    Returns:
        JSON string of the booking/order response, or an error message.
    """
    logger.info(f"Booking creation initiated for offer_id: {offer_id}")

    if not offer_id or not offer_id.startswith("off_"):
        return "Error: `offer_id` must start with 'off_' and be a valid Duffel offer ID."

    if not config.DUFFEL_API_TOKEN:
        logger.error("Duffel API token not configured")
        return "Booking creation is currently unavailable. Please configure the Duffel API token."

    # Optionally, validate that each passenger has an 'id'
    for i, p in enumerate(passengers):
        if "id" not in p or not p["id"]:
            return f"Error: Passenger {i+1} is missing a Duffel-generated 'id'."

    try:
        response = await create_flight_booking(offer_id, passengers, payments)
        logger.info("Booking created successfully")
        return json.dumps(response)
    except Exception as exc:
        logger.error(f"Booking creation failed: {exc}")
        return f"Booking creation failed: {str(exc)}"
    
@tool
async def get_seat_maps_tool(offer_id: str) -> str:
    """
    Retrieve seat maps for a given flight offer.

    Use this tool when the user asks about seat maps, available seats, seat selection, or wants to see the seating layout for a specific flight offer.

    If the offer ID is not provided, ask the user to specify which flight offer they mean (e.g., by offer ID or by referencing a previous search result).

    Args:
        offer_id: The Duffel offer ID (e.g., 'off_...'). This is required to fetch the seat map.

    Returns:
        JSON string containing seat map data, or an error message.

    Example user queries:
        - "Show me the seat map for this flight."
        - "What seats are available on my flight?"
        - "Can I see the seating layout for offer off_0000AvxAOZxt37kKXb9IeY?"
        - "Show me the seat map for the flight above."
        - "What seats are available for my last search?"

    Example tool call:
        get_seat_maps_tool("off_0000AvxAOZxt37kKXb9IeY")
    """
    try:
        seat_maps = await get_seat_maps(offer_id)
        return json.dumps(seat_maps)
    except DuffelAPIError as e:
        title = "API Error"
        detail = "Please try again later"
        if hasattr(e, "error"):
            if isinstance(e.error, dict):
                title = e.error.get("title", title)
                detail = e.error.get("detail", detail)
            elif isinstance(e.error, str):
                title = e.error
                detail = ""
            elif hasattr(e.error, "title") and not callable(getattr(e.error, "title", None)):
                title = getattr(e.error, "title", title)
                detail = getattr(e.error, "detail", detail)
            else:
                title = str(e.error) if e.error else "API Error"
        return f"Seat map fetch error: {title} {detail}"
    except Exception as e:
        return f"Error fetching seat maps: {str(e)}"

@tool
async def list_airline_initiated_changes_tool() -> str:
    """List all airline-initiated changes."""
    try:
        changes = await list_airline_initiated_changes()
        return json.dumps(changes)
    except Exception as e:
        return f"Error listing airline-initiated changes: {str(e)}"

@tool
async def update_airline_initiated_change_tool(change_id: str, data: dict) -> str:
    """
    Update an airline-initiated change.

    Args:
        change_id: The unique ID of the airline-initiated change (e.g., 'aic_...').
        data: A dictionary of fields to update, wrapped in a 'data' key, e.g., {"data": {"action_taken": "accepted"}}.

    Returns:
        JSON string of the update response, or an error message.

    Example:
        update_airline_initiated_change_tool("aic_0000AmalsdUQCYnNTVj9e4", {"data": {"action_taken": "accepted"}})
    """
    try:
        # Auto-wrap if needed
        if "data" not in data:
            data = {"data": data}
        result = await update_airline_initiated_change(change_id, data)
        return json.dumps(result)
    except DuffelAPIError as e:
        title = "API Error"
        detail = "Please try again later"
        if hasattr(e, "error"):
            if isinstance(e.error, dict):
                title = e.error.get("title", title)
                detail = e.error.get("detail", detail)
            elif isinstance(e.error, str):
                # If the error is a string, just use it directly
                title = e.error
                detail = ""
            elif hasattr(e.error, "title") and not callable(getattr(e.error, "title", None)):
                title = getattr(e.error, "title", title)
                detail = getattr(e.error, "detail", detail)
            else:
                title = str(e.error) if e.error else "API Error"
        return f"Accept airline-initiated change error: {title} {detail}"
    except Exception as e:
        return f"Error updating airline-initiated change: {str(e)}"

@tool
async def accept_airline_initiated_change_tool(change_id: str) -> str:
    """
    Accept an airline-initiated change.

    Args:
        change_id: The unique ID of the airline-initiated change (e.g., 'aic_...').

    Returns:
        JSON string of the acceptance response, or an error message.

    Example:
        accept_airline_initiated_change_tool("aic_0000AmalsdUQCYnNTVj9e4")
    """
    try:
        result = await accept_airline_initiated_change(change_id)
        return json.dumps(result)
    except DuffelAPIError as e:
        title = "API Error"
        detail = "Please try again later"
        if hasattr(e, "error"):
            if isinstance(e.error, dict):
                title = e.error.get("title", title)
                detail = e.error.get("detail", detail)
            elif isinstance(e.error, str):
                title = e.error
                detail = ""
            elif hasattr(e.error, "title") and not callable(getattr(e.error, "title", None)):
                title = getattr(e.error, "title", title)
                detail = getattr(e.error, "detail", detail)
            else:
                title = str(e.error) if e.error else "API Error"
        return f"Accept airline-initiated change error: {title} {detail}"
    except Exception as e:
        return f"Error accepting airline-initiated change: {str(e)}"

@tool
def cancel_flight_booking_tool(order_id: str) -> str:
    """
    Cancel a flight booking by order ID. This will:
    1. Find or create an order cancellation for the given order_id.
    2. Confirm the cancellation.
    Returns a JSON string with the cancellation result or a clear error message.
    """
    import asyncio
    import json
    async def do_cancel():
        try:
            # 1. List all cancellations
            cancels = await list_order_cancellations()
            found = None
            for c in cancels.get("data", []):
                if c.get("order_id") == order_id:
                    found = c
                    break
            if not found:
                # Create a cancellation request
                created = await create_order_cancellation(order_id)
                found = created.get("data")
                if not found:
                    return json.dumps({"error": f"Could not create cancellation for order_id {order_id}"})
            cancel_id = found["id"]
            # 2. Confirm the cancellation
            confirm = await confirm_order_cancellation(cancel_id)
            return json.dumps(confirm)
        except Exception as e:
            return json.dumps({"error": f"Cancellation failed: {str(e)}"})
    return asyncio.run(do_cancel())


@tool
async def create_order_change_request_tool(
    order_id: str,
    slices: Optional[List[Dict[str, str]]] = None,
    type: str = "update"
) -> str:
    """
    Create a Duffel order change request. Requires `type`, and slices which includes origin, destination, and departure_date if `type` is 'update'.
    """
    try:
        if type == "update" and not slices:
            return "Error: Slices must be provided when type is 'update'."
        result = await create_order_change_request_api(order_id=order_id, slices=slices, type=type)
        return json.dumps(result)
    except DuffelAPIError as e:
        title = "Duffel API Error"
        detail = "Unknown error"
        err = getattr(e, "error", None)
        if isinstance(err, dict):
            title = err.get("title", title)
            detail = err.get("detail", detail)
        elif isinstance(err, str):
            detail = err
        else:
            try:
                title = str(err.title()) if callable(getattr(err, "title", None)) else str(err.title)
                detail = str(getattr(err, "detail", ""))
            except Exception:
                detail = str(err)
        return f"Error creating order change request: {title} - {detail}"
    except Exception as e:
        return f"Unexpected error creating order change request: {str(e)}"

@tool
async def get_order_change_request_tool(request_id: str) -> str:
    """Get details for a flight order change request. Args: request_id (str). Returns: JSON string of the order change request details."""
    try:
        result = await get_order_change_request_api(request_id=request_id)
        return json.dumps(result)
    except Exception as e:
        return f"Error getting order change request: {str(e)}"

@tool
async def list_order_change_offers_tool(request_id: str = None) -> str:
    """
    List change offers for a flight order change request, with full flight details for each offer.
    Args: request_id (str, optional).
    Returns: JSON string of the change offers, each with detailed flight info.
    """
    import logging
    try:
        offers_result = await list_order_change_offers_api(request_id=request_id)
        offers = offers_result.get("data", [])
        detailed_offers = []
        for offer in offers:
            offer_id = offer.get("id")
            if not offer_id:
                continue
            # Fetch full details for each offer
            offer_details = await get_order_change_offer_api(offer_id=offer_id)
            if isinstance(offer_details, str):
                print(f"DEBUG: offer_details for offer_id {offer_id}: {offer_details}")
                try:
                    offer_details = json.loads(offer_details)
                except Exception as parse_exc:
                    logging.warning(f"Could not parse offer_details for offer_id {offer_id}: {offer_details}")
                    continue  # Skip this offer if not valid JSON
            if not isinstance(offer_details, dict):
                logging.warning(f"offer_details for offer_id {offer_id} is not a dict: {offer_details}")
                continue
            data = offer_details.get("data", {})
            # Extract relevant flight details from the offer
            slices = data.get("slices", [])
            segments = []
            for s in slices:
                for seg in s.get("segments", []):
                    passenger = seg.get("passengers", [{}])[0] if seg.get("passengers") else {}
                    segments.append({
                        "origin": seg.get("origin", {}).get("iata_code", "Unknown"),
                        "origin_name": seg.get("origin", {}).get("name", "Unknown"),
                        "destination": seg.get("destination", {}).get("iata_code", "Unknown"),
                        "destination_name": seg.get("destination", {}).get("name", "Unknown"),
                        "departure_time": seg.get("departing_at", "N/A"),
                        "arrival_time": seg.get("arriving_at", "N/A"),
                        "duration": seg.get("duration", "N/A"),
                        "airline": seg.get("operating_carrier", {}).get("name", "Unknown"),
                        "flight_number": seg.get("marketing_carrier_flight_number", "Unknown"),
                        "aircraft": seg.get("aircraft", {}).get("name", "Unknown"),
                        "cabin_class": passenger.get("cabin_class_marketing_name", "Unknown"),
                        "baggage": passenger.get("baggages", []),
                    })
            # Use first segment for summary fields
            first_segment = segments[0] if segments else {}
            detailed_offers.append({
                "offer_id": offer_id,
                "total_amount": data.get("total_amount", "N/A"),
                "currency": data.get("total_currency", "N/A"),
                "cabin": first_segment.get("cabin_class", "Unknown"),
                "flight_number": first_segment.get("flight_number", "Unknown"),
                "airline": first_segment.get("airline", "Unknown"),
                "origin": first_segment.get("origin", "Unknown"),
                "origin_name": first_segment.get("origin_name", "Unknown"),
                "destination": first_segment.get("destination", "Unknown"),
                "destination_name": first_segment.get("destination_name", "Unknown"),
                "departure_time": first_segment.get("departure_time", "N/A"),
                "arrival_time": first_segment.get("arrival_time", "N/A"),
                "duration": first_segment.get("duration", "N/A"),
                "aircraft": first_segment.get("aircraft", "Unknown"),
                "baggage": first_segment.get("baggage", []),
                "segments": segments,
            })
        return json.dumps({"offers": detailed_offers})
    except Exception as e:
        return f"Error listing order change offers: {str(e)}"

@tool
async def get_order_change_offer_tool(offer_id: str) -> str:
    """Get details for a flight order change offer. Args: offer_id (str). Returns: JSON string of the order change offer details."""
    try:
        result = await get_order_change_offer_api(offer_id=offer_id)
        return json.dumps(result)
    except Exception as e:
        return f"Error getting order change offer: {str(e)}"

@tool
async def confirm_order_change_tool(change_id: str) -> str:
    """
    Confirm a flight order change.
    Args:
        change_id (str): The ID returned from create_order_change_api (not an offer_id or request_id!).
            - To confirm an order change, you must:
                1. Create an order change from a selected offer (using create_order_change_api or create_order_change_tool).
                2. Extract the 'id' from the response (this is the change_id).
                3. Pass this change_id to this tool to confirm the order change.
            - Do NOT use an offer_id (oco_...) or request_id (ocr_...) here; only use the change_id (oce_... or similar).
    Returns:
        JSON string of the confirmation response.
    """
    try:
        result = await confirm_order_change_api(change_id=change_id)
        return json.dumps(result)
    except Exception as e:
        return f"Error confirming order change: {str(e)}"

@tool
async def get_order_change_tool(change_id: str) -> str:
    """Get details for a confirmed flight order change. Args: change_id (str). Returns: JSON string of the order change details."""
    try:
        result = await get_order_change_api(change_id=change_id)
        return json.dumps(result)
    except Exception as e:
        return f"Error getting order change: {str(e)}"

@tool
async def create_order_change_tool(offer_id: str) -> str:
    """Create a confirmed flight order change from an offer. Args: offer_id (str). Returns: JSON string of the created order change."""
    try:
        result = await create_order_change_api(offer_id=offer_id)
        return json.dumps(result)
    except Exception as e:
        return f"Error creating order change: {str(e)}"

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
        model="gpt-4o",
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
    logger.info(f"[UI PUSH] Evaluating UI push for tool: {tool_name}")
    logger.debug(f"[UI PUSH] Tool data keys: {list(tool_data.keys()) if isinstance(tool_data, dict) else 'not dict'}")
    logger.debug(f"[UI PUSH] Tool data type: {type(tool_data)}")
    
    # Check if tool has UI mapping
    ui_type = TOOL_UI_MAPPING.get(tool_name)
    if not ui_type:
        logger.info(f"[UI PUSH] No UI mapping found for tool: {tool_name}. Available mappings: {list(TOOL_UI_MAPPING.keys())}")
        return False, None
    
    logger.info(f"[UI PUSH] Found UI mapping: {tool_name} -> {ui_type}")
    
    # Tool-specific logic
    if tool_name == "search_hotels_tool":
        logger.info(f"[UI PUSH] Processing hotel search results for UI")
        # Only push UI if we have actual hotel results
        hotels = tool_data.get("hotels", [])
        logger.info(f"[UI PUSH] Hotels data type: {type(hotels)}, length: {len(hotels) if isinstance(hotels, list) else 'N/A'}")
        
        if isinstance(hotels, list) and len(hotels) > 0:
            logger.info(f"[UI PUSH] Found {len(hotels)} hotels, checking first hotel structure")
            # Verify hotels have required fields for UI
            first_hotel = hotels[0]
            logger.debug(f"[UI PUSH] First hotel keys: {list(first_hotel.keys()) if isinstance(first_hotel, dict) else 'not dict'}")
            required_fields = ["name", "location", "price"]
            
            missing_fields = [field for field in required_fields if field not in first_hotel]
            if not missing_fields:
                logger.info(f"[UI PUSH] Hotel data validation passed - all required fields present: {required_fields}")
                return True, ui_type
            else:
                logger.warning(f"[UI PUSH] Hotel data validation failed - missing fields: {missing_fields}")
                logger.debug(f"[UI PUSH] Available fields in first hotel: {list(first_hotel.keys()) if isinstance(first_hotel, dict) else 'not dict'}")
        else:
            logger.info(f"[UI PUSH] No valid hotels data found - hotels is not a list or is empty")
        
        logger.info(f"[UI PUSH] Rejecting UI push for {tool_name} - insufficient hotel data")
        return False, None
    
    elif tool_name == "search_flights_tool":
        logger.info(f"[UI PUSH] Flight search - using generic JSON renderer (no custom UI)")
        # Don't push UI for flights - use generic JSON renderer
        return False, None
    
    # For other tools, check if data is rich enough for UI
    elif isinstance(tool_data, dict) and len(tool_data) > 2:
        logger.info(f"[UI PUSH] Generic tool data check passed - dict with {len(tool_data)} fields > 2")
        # Has enough structured data to warrant UI
        return True, ui_type
    
    logger.info(f"[UI PUSH] Rejecting UI push for {tool_name} - generic data check failed")
    logger.debug(f"[UI PUSH] Data type: {type(tool_data)}, dict length: {len(tool_data) if isinstance(tool_data, dict) else 'N/A'}")
    return False, None

# Define the agent logic
def agent_node(state: AgentState) -> Dict[str, Any]:
    """Main agent reasoning node."""

    logger.info("Agent node started - processing conversation state")
    logger.debug(f"[INIT] Available UI mappings: {TOOL_UI_MAPPING}")
    logger.debug(f"[INIT] State keys: {list(state.keys())}")
    logger.debug(f"[INIT] UI enabled setting: {state.get('ui_enabled', 'not_set')}")    


    llm = create_llm()
    tools = [
        get_current_time, calculate_simple_math, search_web, validate_phone_number_tool, search_flights_tool, search_hotels_tool, get_seat_maps_tool, fetch_hotel_rates_tool, create_quote_tool, create_booking_tool, fetch_flight_quote_tool, create_flight_booking_tool, list_airline_initiated_changes_tool, update_airline_initiated_change_tool, accept_airline_initiated_change_tool, create_order_change_request_tool, get_order_change_request_tool, get_order_change_offer_tool, confirm_order_change_tool, get_order_change_tool, create_order_change_tool, cancel_flight_booking_tool
    ]
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
    
    # Check if we'll have UI components to adjust the response style
    logger.info("[UI PREVIEW] Checking if UI components will be generated to adjust response style")
    will_have_ui_components = False
    ui_enabled_for_preview = state.get("ui_enabled", True)
    logger.debug(f"[UI PREVIEW] UI enabled for preview check: {ui_enabled_for_preview}")
    
    if ui_enabled_for_preview:
        logger.debug(f"[UI PREVIEW] Scanning {len(state['messages'])} messages for potential UI components")
        # Look for recent tool messages that would generate UI
        for i in range(len(state["messages"]) - 1, -1, -1):
            msg = state["messages"][i]
            logger.debug(f"[UI PREVIEW] Message {i}: type={type(msg).__name__}, msg_type={getattr(msg, 'type', 'unknown')}")
            
            if isinstance(msg, ToolMessage):
                logger.debug(f"[UI PREVIEW] Found ToolMessage: {msg.name}")
                try:
                    tool_data = json.loads(msg.content)
                    logger.debug(f"[UI PREVIEW] Parsed JSON for preview check from {msg.name}")
                    should_push, ui_type = should_push_ui_message(msg, tool_data)
                    logger.debug(f"[UI PREVIEW] Preview decision for {msg.name}: should_push={should_push}, ui_type={ui_type}")
                    
                    if should_push:
                        will_have_ui_components = True
                        logger.info(f"[UI PREVIEW] ✓ Found UI component candidate: {msg.name} -> {ui_type}")
                        break
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug(f"[UI PREVIEW] Failed to parse/check {msg.name} for preview: {e}")
                    continue
            elif msg.type in ["human", "ai"]:
                logger.debug(f"[UI PREVIEW] Hit {msg.type} message, stopping preview scan")
                break
    
    logger.info(f"[UI PREVIEW] Preview result: will_have_ui_components={will_have_ui_components}")
    
    # Modify system prompt if UI components will be shown
    if will_have_ui_components:
        system_prompt += """

<ui_response_style>
Since rich UI components (hotel cards, flight results, etc.) will be displayed to show detailed information with images and structured data, keep your text response concise and conversational. Focus on:
- Brief summary of results found
- Key insights or recommendations
- Next steps or questions for the user
- Avoid describing visual details that will be shown in the UI components
- Important: do not show images as they will be shown in the UI components
</ui_response_style>
"""
        logger.info("[UI PREVIEW] ✓ Modified system prompt for concise response due to upcoming UI components")
    else:
        logger.info("[UI PREVIEW] No UI components expected - using standard response style")

    # Create messages with system prompt
    messages = [HumanMessage(content=system_prompt)] +  state["messages"]
    for idx, msg in enumerate(messages):
            logger.info(f"Message {idx}: role={getattr(msg, 'role', None)}, content={getattr(msg, 'content', None)}, tool_calls={getattr(msg, 'tool_calls', None)}")
    
    response = llm_with_tools.invoke(messages)

    ui_enabled = state.get("ui_enabled", True)
    logger.info(f"UI enabled: {ui_enabled}")

    # Handle push UI message with improved logic for multiple tool calls
    logger.info(f"[UI PROCESSING] Starting UI component processing - UI enabled: {ui_enabled}")
    if ui_enabled:
        logger.info(f"[UI PROCESSING] Total messages in state: {len(state['messages'])}")
        
        # Find all recent tool messages that could need UI components
        # Look for tool messages that came after the last human/AI message
        recent_tool_messages = []
        
        # Work backwards from the end to find recent tool calls in this turn
        logger.debug(f"[UI PROCESSING] Scanning messages backwards to find recent tool calls")
        for i in range(len(state["messages"]) - 1, -1, -1):
            msg = state["messages"][i]
            logger.debug(f"[UI PROCESSING] Message {i}: type={type(msg).__name__}, msg_type={getattr(msg, 'type', 'unknown')}")
            
            if isinstance(msg, ToolMessage):
                logger.debug(f"[UI PROCESSING] Found ToolMessage at index {i}: tool={msg.name}")
                recent_tool_messages.insert(0, msg)  # Keep chronological order
            elif msg.type in ["human", "ai"]:
                logger.debug(f"[UI PROCESSING] Hit {msg.type} message at index {i}, stopping scan")
                # Stop when we hit a non-tool message (start of this tool sequence)
                break
        
        logger.info(f"[UI PROCESSING] Found {len(recent_tool_messages)} recent tool messages to process for UI")
        
        # Log details of each tool message found
        for idx, tool_msg in enumerate(recent_tool_messages):
            logger.debug(f"[UI PROCESSING] Tool message {idx}: name={tool_msg.name}, content_length={len(tool_msg.content)}")
        
        # Process each tool message for potential UI
        ui_components_created = 0
        for idx, tool_message in enumerate(recent_tool_messages):
            logger.info(f"[UI PROCESSING] Processing tool message {idx+1}/{len(recent_tool_messages)}: {tool_message.name}")
            
            try:
                # Parse tool result data
                logger.debug(f"[UI PROCESSING] Parsing JSON content from {tool_message.name}")
                tool_data = json.loads(tool_message.content)
                logger.info(f"[UI PROCESSING] Successfully parsed JSON for {tool_message.name} - data type: {type(tool_data)}")
                
                # Log a sample of the data structure (safely)
                if isinstance(tool_data, dict):
                    logger.debug(f"[UI PROCESSING] Data keys for {tool_message.name}: {list(tool_data.keys())}")
                    # Log size of main data arrays if present
                    for key in ['hotels', 'flights', 'results']:
                        if key in tool_data and isinstance(tool_data[key], list):
                            logger.info(f"[UI PROCESSING] {tool_message.name} has {len(tool_data[key])} items in '{key}' array")
                
                # Use decision function to determine if UI should be pushed
                logger.info(f"[UI PROCESSING] Calling should_push_ui_message for {tool_message.name}")
                should_push, ui_type = should_push_ui_message(tool_message, tool_data)
                logger.info(f"[UI PROCESSING] Decision for {tool_message.name}: should_push={should_push}, ui_type={ui_type}")
                
                if should_push and ui_type:
                    logger.info(f"[UI PROCESSING] ✓ Pushing UI message for {ui_type} from tool {tool_message.name}")
                    logger.debug(f"[UI PROCESSING] UI data summary - type: {ui_type}, data_fields: {len(tool_data) if isinstance(tool_data, dict) else 'N/A'}")
                    
                    # Attempt the actual UI push
                    try:
                        logger.debug(f"[UI PROCESSING] Calling push_ui_message with ui_type='{ui_type}'")
                        push_ui_message(ui_type, tool_data, message=response)
                        ui_components_created += 1
                        logger.info(f"[UI PROCESSING] ✓ Successfully pushed UI component #{ui_components_created} for {tool_message.name}")
                    except Exception as push_error:
                        logger.error(f"[UI PROCESSING] ✗ Failed to push UI component for {tool_message.name}: {push_error}", exc_info=True)
                        logger.error(f"[UI PROCESSING] Push error details - ui_type: {ui_type}, data_type: {type(tool_data)}")
                    
                else:
                    logger.info(f"[UI PROCESSING] ✗ Not pushing UI for {tool_message.name}: should_push={should_push}, ui_type={ui_type}")
                    
            except json.JSONDecodeError as e:
                logger.warning(f"[UI PROCESSING] ✗ Failed to parse tool result as JSON for UI from {tool_message.name}: {e}")
                logger.debug(f"[UI PROCESSING] Raw content (first 200 chars): {tool_message.content[:200]}...")
            except Exception as e:
                logger.error(f"[UI PROCESSING] ✗ Unexpected error processing UI message for {tool_message.name}: {e}", exc_info=True)
        
        logger.info(f"[UI PROCESSING] UI processing complete - created {ui_components_created} UI components")
        
        if ui_components_created > 0:
            logger.info(f"[UI PROCESSING] ✓ Successfully created {ui_components_created} UI components for this agent response")
            # Optionally modify the text response to be more concise since UI will show details
            logger.debug("[UI PROCESSING] UI components will show detailed results, text response will be concise")
        else:
            logger.info(f"[UI PROCESSING] No UI components created - all {len(recent_tool_messages)} tool messages were rejected for UI display")
    else:
        logger.info("[UI PROCESSING] UI disabled - skipping all UI component processing")

    logger.info("[UI PROCESSING] Agent node completed, returning response")
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
        tools = [
            get_current_time, calculate_simple_math, search_web, validate_phone_number_tool, search_flights_tool, search_hotels_tool, get_seat_maps_tool, fetch_hotel_rates_tool, create_quote_tool, create_booking_tool, fetch_flight_quote_tool, create_flight_booking_tool, list_airline_initiated_changes_tool, update_airline_initiated_change_tool, accept_airline_initiated_change_tool, create_order_change_request_tool, get_order_change_request_tool, get_order_change_offer_tool, confirm_order_change_tool, get_order_change_tool, create_order_change_tool, cancel_flight_booking_tool
        ]
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
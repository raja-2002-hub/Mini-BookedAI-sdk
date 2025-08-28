"""
LangGraph Agent for BookedAI
"""
from typing import Annotated, List, Dict, Any, Sequence, Optional, Deque
from typing_extensions import TypedDict
import os
from collections import deque
import logging
import asyncio
from datetime import date, datetime
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException
import httpx

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
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, SystemMessage, AIMessage
from langchain_core.tools import tool
from pydantic import SecretStr

from langgraph.graph import StateGraph, START, END
from langgraph.graph.ui import AnyUIMessage, ui_message_reducer, push_ui_message
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.errors import GraphInterrupt
from langgraph.checkpoint.memory import MemorySaver

# Import our Duffel client
from src.duffel_client.endpoints.stays import search_hotels, fetch_hotel_rates, create_quote, create_booking, cancel_hotel_booking, update_hotel_booking
from src.duffel_client.endpoints.flights import search_flights, format_flights_markdown, get_seat_maps,fetch_flight_offer, create_flight_booking, list_airline_initiated_changes, update_airline_initiated_change, accept_airline_initiated_change
from src.duffel_client.client import DuffelAPIError
from src.config import config
from mem0 import AsyncMemoryClient


# --- Flight Order Change Tools ---
from src.duffel_client.endpoints.flights import (
    create_order_change_request_api,  # Only this is needed for changing flights
)

from src.duffel_client.endpoints.flights import create_order_cancellation, confirm_order_cancellation

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)



class UserIDManager:
    """Simple class to manage the current user ID for mem0 operations."""
    
    def __init__(self):
        self._current_user_id = None  # No default fallback
        logger.info(f"[USER MANAGER] Initialized with no default user ID")
    
    @property
    def current_user_id(self) -> str:
        if self._current_user_id is None:
            # If no user ID is set, we should fail rather than use a default
            raise ValueError("No user ID has been set. Headers must contain X-User-ID.")
        return self._current_user_id
    
    @current_user_id.setter
    def current_user_id(self, user_id: str):
        self._current_user_id = user_id
        logger.info(f"[USER MANAGER] Updated user ID to: {user_id}")
    
    def get_user_id(self) -> str:
        return self.current_user_id

# Global instance of the user ID manager
user_id_manager = UserIDManager()

def get_current_user_id() -> str:
    """Get the current user ID for mem0 operations."""
    return user_id_manager.current_user_id


TOOL_UI_MAPPING = {
    "search_hotels_tool": "hotelResults",
    "search_flights_tool": "flightResults",
}

# Module-level scratchpad for recent user texts (set by context preparation)
LAST_USER_TEXTS: Deque[str] = deque(maxlen=5)

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
    context_prepared: Optional[bool]  # Track if context has been prepared



async def parse_and_normalize_date(input_date: str) -> str:
    """
    Parse a date string using dateparser and ensure it is in the future.
    If the date is in the past (even after rolling to this year), keep rolling forward to the next year until it is in the future.
    Returns a string in YYYY-MM-DD format.
    """
    today = date.today()
    try:
        logger.info(f"[DEBUG] parse_and_normalize_date called with input: {input_date}")
        
        # First try to parse with dateparser (offload to thread to avoid blocking event loop)
        dt = None
        try:
            dt = await asyncio.to_thread(
                dateparser.parse,
                input_date,
                settings={'PREFER_DATES_FROM': 'future'}
            )
        except Exception as parse_error:
            logger.info(f"[DEBUG] dateparser.parse failed: {parse_error}")
        
        # If dateparser failed, try to parse as YYYY-MM-DD format
        if not dt:
            try:
                dt = datetime.strptime(input_date, "%Y-%m-%d").date()
                logger.info(f"[DEBUG] Parsed as YYYY-MM-DD: {dt}")
            except ValueError:
                logger.info(f"[DEBUG] Could not parse as YYYY-MM-DD either, returning as is: {input_date}")
                return input_date  # fallback if all parsing fails
        
        # Convert to date if it's a datetime
        if hasattr(dt, 'date'):
            dt = dt.date()
        
        # Always roll forward if in the past
        original_dt = dt
        while dt < today:
            try:
                dt = dt.replace(year=dt.year + 1)
                logger.info(f"[DEBUG] Rolled forward to: {dt}")
            except ValueError:
                # Handles Feb 29 on non-leap years, etc.
                logger.info(f"[DEBUG] ValueError when rolling forward, using today")
                dt = today
                break
        
        result = dt.strftime("%Y-%m-%d")
        logger.info(f"[DEBUG] parse_and_normalize_date output: {result} (from {original_dt})")
        return result
        
    except Exception as e:
        logger.info(f"[DEBUG] parse_and_normalize_date exception: {e}, input: {input_date}")
        # Last resort: return today's date
        today_str = today.strftime("%Y-%m-%d")
        logger.info(f"[DEBUG] Returning today's date as fallback: {today_str}")
        return today_str


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
async def validate_phone_number_tool(phone: str) -> str:
    """
    Validates a phone number using automatic IP-based region detection and asks for confirmation.
    If the phone starts with '+', no region is needed.
    If not, automatically detects user's country from their IP address.
    
    This tool should be used when collecting phone numbers for bookings to ensure accuracy.
    """
    try:
        if phone.startswith("+"):
            parsed = phonenumbers.parse(phone, None)
            country_name = "Unknown"
        else:
            # Automatically detect user's country from IP
            try:
                async with httpx.AsyncClient() as client:
                    # Get user's IP address automatically
                    ip_response = await client.get("https://api.ipify.org?format=json")
                    user_ip = ip_response.json().get("ip")
                    
                    # Get country from IP
                    geo_response = await client.get(f"https://ipapi.co/{user_ip}/json/")
                    region = geo_response.json().get("country")
                    country_name = geo_response.json().get("country_name", "Unknown")
                    
                    if not region:
                        return "Error: Could not detect your country automatically. Please provide phone number with country code (e.g., +1 for US, +44 for UK)"
                    
                    parsed = phonenumbers.parse(phone, region)
            except Exception as e:
                return f"Error: Could not detect your country automatically. Please provide phone number with country code (e.g., +1 for US, +44 for UK). Error: {str(e)}"

        if not phonenumbers.is_valid_number(parsed):
            return "Error: Invalid phone number"

        formatted_number = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        
        # Return validated phone number without confirmation
        return f"Valid phone number: {formatted_number} (detected country: {country_name})"
        
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
    Search for flights across all airlines! 

    I can find flights for one-way, round-trip, or multi-city journeys. 
    Supports all cabin classes (Economy, Premium Economy, Business, First) and up to 9 passengers.

    Dates can be natural language like "next Friday" or "December 15th".
    Returns up to 5 options by default.
    """
    logger.info(f"Flight search initiated - Slices: {slices}, Passengers: {passengers}, Cabin: {cabin_class}, Max results: {max_results}")
    try:
        # Validate slices
        if not isinstance(slices, list) or not slices:
            return "Error: 'slices' must be a non-empty list of segment dicts."
        # Normalize all departure_date fields using parse_and_normalize_date
        for seg in slices:
            if not all(k in seg for k in ("origin", "destination", "departure_date")):
                return "Error: Each slice must have 'origin', 'destination', and 'departure_date'."
            # Normalize the departure_date (async)
            seg["departure_date"] = await parse_and_normalize_date(seg["departure_date"])
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
        # Validate date format and parse dates (async)
        check_in_date = await parse_and_normalize_date(check_in_date)
        check_out_date = await parse_and_normalize_date(check_out_date)
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
async def validate_offer_tool(offer_id: str) -> str:
    """
    Validate if a flight offer is still available for booking.
    This helps prevent booking errors by checking offer status before attempting to book.
    """
    try:
        from src.duffel_client.endpoints.flights import fetch_flight_offer
        offer = await fetch_flight_offer(offer_id)
        
        # Check if offer is still valid
        if offer and 'data' in offer:
            offer_data = offer['data']
            return json.dumps({
                "valid": True,
                "offer_id": offer_id,
                "airline": offer_data.get('owner', {}).get('name', 'Unknown'),
                "price": offer_data.get('total_amount'),
                "currency": offer_data.get('total_currency'),
                "message": "Offer is valid and available for booking"
            })
        else:
            return json.dumps({
                "valid": False,
                "offer_id": offer_id,
                "message": "Offer not found or no longer available"
            })
    except Exception as e:
        logger.error(f"Error validating offer: {e}")
        return json.dumps({
            "valid": False,
            "offer_id": offer_id,
            "message": f"Error validating offer: {str(e)[:50]}"
        })

@tool
async def create_flight_booking_tool(
    offer_id: str,
    passengers: list,
    payments: list,
    services: list = None,
    loyalty_programme_reference: str = "",
    loyalty_account_number: str = "",
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
        # First, refresh the offer to ensure it's still valid and get fresh passenger IDs
        logger.info(f"Refreshing offer {offer_id} before booking")
        refreshed_offer = await fetch_flight_offer(offer_id)
        
        if not refreshed_offer or 'data' not in refreshed_offer:
            return "Error: Offer is no longer available. Please search for flights again."
        
        # Update passenger IDs with fresh ones from the refreshed offer
        refreshed_passengers = refreshed_offer['data'].get('passengers', [])
        if len(refreshed_passengers) != len(passengers):
            return "Error: Number of passengers doesn't match the offer. Please refresh your search."
        
        # Update passenger IDs with fresh ones
        for i, passenger in enumerate(passengers):
            if i < len(refreshed_passengers):
                passenger['id'] = refreshed_passengers[i]['id']
        
        # Now attempt the booking with fresh offer data
        response = await create_flight_booking(
            offer_id, 
            passengers, 
            payments, 
            loyalty_programme_reference=loyalty_programme_reference,
            loyalty_account_number=loyalty_account_number,
            services=services
        )
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
    Cancel a flight booking by order ID using the full Duffel flow:
    1. Create a pending order cancellation
    2. Confirm the cancellation
    Returns a JSON string with the final cancellation result or a clear error message.
    """
    import asyncio
    import json
    async def do_cancel():
        try:
            # Step 1: Create the cancellation
            create_resp = await create_order_cancellation(order_id)
            cancellation_data = create_resp.get("data")
            if not cancellation_data or not cancellation_data.get("id"):
                return json.dumps({"error": "Could not create cancellation or missing cancellation ID.", "raw": create_resp})
            cancellation_id = cancellation_data["id"]
            # Step 2: Confirm the cancellation
            from src.duffel_client.endpoints.flights import confirm_order_cancellation
            confirm_resp = await confirm_order_cancellation(cancellation_id)
            return json.dumps(confirm_resp)
        except Exception as e:
            return json.dumps({"error": f"Cancellation failed: {str(e)}"})
    return asyncio.run(do_cancel())

@tool
async def cancel_hotel_booking_tool(booking_id: str) -> str:
    """Cancel a hotel booking by booking_id. Returns a JSON string with the cancellation result or error."""
    import json
    try:
        response = await cancel_hotel_booking(booking_id)
        return json.dumps(response)
    except DuffelAPIError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"})

@tool
async def list_loyalty_programmes_tool() -> str:
    """List all loyalty programmes supported by Duffel Stays."""
    try:
        from src.duffel_client.endpoints.stays import fetch_loyalty_programmes
        loyalty_programmes = await fetch_loyalty_programmes()
        
        if loyalty_programmes:
            result = "Supported loyalty programmes:\n"
            for i, programme in enumerate(loyalty_programmes[:10], 1):  # Limit to 10
                result += f"{i}. {programme.name} (Reference: {programme.reference})\n"
            return result
        else:
            return "No loyalty programmes found or error fetching programmes"
    except Exception as e:
        logger.error(f"Error listing loyalty programmes: {e}")
        return f"Error listing loyalty programmes: {str(e)[:50]}"

@tool
async def list_flight_loyalty_programmes_tool() -> str:
    """
    List all loyalty programmes supported by Duffel Flights.
    
    Use this tool when the user asks about loyalty programs, frequent flyer programs, or when you want to offer loyalty program options during flight booking. This helps users earn points and miles on their flights.
    """
    try:
        # This would need to be implemented based on your flight loyalty API
        return "Flight loyalty programmes: American Airlines AAdvantage, Delta SkyMiles, United MileagePlus, etc."
    except Exception as e:
        logger.error(f"Error listing flight loyalty programmes: {e}")
        return f"Error listing flight loyalty programmes: {str(e)[:50]}"

@tool
async def update_hotel_booking_tool(
    booking_id: str, 
    email: str = None,
    phone_number: str = None,
    stay_special_requests: str = None
) -> str:
    """Update a hotel booking by booking_id. Provide any fields you want to update. Returns a JSON string with the update result or error."""
    import json
    try:
        # Build the data dictionary from provided fields
        data = {}
        if email is not None:
            data["email"] = email
        if phone_number is not None:
            data["phone_number"] = phone_number
        if stay_special_requests is not None:
            data["stay_special_requests"] = stay_special_requests
        
        if not data:
            return json.dumps({"error": "No fields provided to update"})
        
        response = await update_hotel_booking(booking_id, data)
        return json.dumps(response)
    except DuffelAPIError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


@tool
async def fetch_extra_baggage_options_tool(offer_id: str) -> str:
    """Fetch extra baggage options for a flight offer."""
    try:
        from src.duffel_client.endpoints.flights import get_available_services
        services = await get_available_services(offer_id)
        
        # Extract and format baggage-related services
        baggage_options = []
        if isinstance(services, dict) and 'data' in services:
            available_services = services.get('data', {}).get('available_services', [])
            for service in available_services:
                service_type = service.get('type', '')
                if 'baggage' in service_type.lower() or 'luggage' in service_type.lower():
                    baggage_options.append({
                        'id': service.get('id'),
                        'type': service.get('type'),
                        'name': service.get('metadata', {}).get('name', ''),
                        'description': service.get('metadata', {}).get('description', ''),
                        'price': service.get('total_amount'),
                        'currency': service.get('total_currency')
                    })
        
        if baggage_options:
            return json.dumps({
                'baggage_options': baggage_options,
                'message': f'Found {len(baggage_options)} extra baggage options. To add baggage to your booking, include the selected services in the create_flight_booking_tool call with the services parameter.',
                'usage_note': 'When booking, pass selected baggage services as: [{"id": "service_id", "passenger_ids": ["passenger_id"], "quantity": 1}]'
            })
        else:
            return json.dumps({
                'baggage_options': [],
                'message': 'No additional baggage options available for this flight'
            })
            
    except Exception as e:
        logger.error(f"Error fetching baggage options: {e}")
        return f"Error fetching baggage options: {str(e)[:50]}"





@tool
async def get_available_services_tool(offer_id: str) -> str:
    """Get available services for a flight offer."""
    try:
        from src.duffel_client.endpoints.flights import get_available_services
        services = await get_available_services(offer_id)
        return json.dumps(services)
    except Exception as e:
        logger.error(f"Error fetching available services: {e}")
        return f"Error fetching available services: {str(e)[:50]}"

@tool
async def fetch_accommodation_reviews_tool(accommodation_id: str, limit: int = 5) -> str:
    """Fetch reviews for an accommodation."""
    try:
        from src.duffel_client.endpoints.stays import fetch_accommodation_reviews
        reviews = await fetch_accommodation_reviews(accommodation_id, limit)
        return json.dumps(reviews)
    except Exception as e:
        logger.error(f"Error fetching accommodation reviews: {e}")
        return f"Error fetching accommodation reviews: {str(e)[:50]}"

@tool
async def change_flight_booking_tool(
    order_id: str,
    slices: Optional[List[Dict[str, str]]] = None,
    type: str = "update",
    cabin_class: str = None
) -> str:
    """
    Use this tool to request a change to an existing flight booking (e.g., change date, route, etc.).
    - If the user does not explicitly mention their current flight or booking, you should cancel the current booking (if any) and search for a new flight instead of attempting a change.
    - Only use this tool if the user clearly wants to change their existing booking (e.g., "change my current flight to 10 Dec").
    - If the user asks for a new route, origin, or destination, or does not specify a current booking, cancel and search for a new flight.

    Requires `type`, and slices which includes origin, destination, and departure_date if `type` is 'update'.
    Requires `cabin_class` (economy, premium_economy, business, first).
    """
    CABIN_CLASSES = ["economy", "premium_economy", "business", "first"]
    if not cabin_class or cabin_class.lower() not in CABIN_CLASSES:
        return "Which cabin class would you like for your new flight? (Economy, Premium Economy, Business, First)"
    try:
        if type == "update" and not slices:
            return "Error: Slices must be provided when type is 'update'."
        result = await create_order_change_request_api(order_id=order_id, slices=slices, type=type)
        # If offers are present, filter by cabin_class
        if isinstance(result, dict) and "offers" in result:
            filtered = [o for o in result["offers"] if o.get("cabin", "").lower() == cabin_class.lower()]
            result["offers"] = filtered
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
        return f"Error requesting flight change: {title} - {detail}"
    except Exception as e:
        return f"Unexpected error requesting flight change: {str(e)}"



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
        get_current_time,
        calculate_simple_math,
        search_web,
        validate_phone_number_tool,
        search_flights_tool,
        search_hotels_tool,
        fetch_hotel_rates_tool,
        create_quote_tool,
        create_booking_tool,
        fetch_flight_quote_tool,
        create_flight_booking_tool,
        get_seat_maps_tool,
        list_airline_initiated_changes_tool,
        update_airline_initiated_change_tool,
        accept_airline_initiated_change_tool,
        change_flight_booking_tool,
        cancel_flight_booking_tool,
        cancel_hotel_booking_tool,
        update_hotel_booking_tool,
        list_loyalty_programmes_tool,
        list_flight_loyalty_programmes_tool,
        fetch_extra_baggage_options_tool,
        get_available_services_tool,
            fetch_accommodation_reviews_tool,
        remember_tool,
            recall_tool,
            extract_entities_tool,
            traverse_memory_graph_tool,
            list_memories_tool,
            delete_memory_tool,
            delete_memories_by_query_tool,
            delete_all_namespace_memories_tool,
            pin_memory_tool,
            unpin_memory_tool,
            update_memory_importance_tool,
            prune_memories_tool
    ]
    llm_with_tools = llm.bind_tools(tools)
    
    # System prompt
    system_prompt = """
<identity>
You are a helpful AI assistant for BookedAI, specializing in travel assistance
</identity>

<instructions>
Help the user with their travel plans in a conversational, personal way.
Be friendly and natural - like chatting with a helpful travel friend who remembers your preferences and mentions them naturally throughout the conversation.
</instructions>

 <memory_instructions>
 Store user preferences with remember_tool when they mention likes/dislikes. When searching for preferences, use recall_tool with specific terms from the user's request (e.g., "paris", "melbourne", "window seat") along with generic queries. ALWAYS call recall_tool first before any other actions.
 </memory_instructions>


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


async def context_preparation_node(state: AgentState) -> Dict[str, Any]:
    """
    Always fetch memories in the background for context preparation.
    """
    logger.info("Context preparation started")

    # Extract user metadata from headers if available
    # Headers are passed in the state metadata
    metadata = state.get("metadata", {})
    headers = metadata.get("headers", {})
    
    # Debug: Log the entire state structure
    logger.info(f"[CONTEXT PREP] State keys: {list(state.keys())}")
    logger.info(f"[CONTEXT PREP] State metadata: {state.get('metadata', {})}")
    logger.info(f"[CONTEXT PREP] State configurable: {state.get('configurable', {})}")
    
    # Use fake auth to get or create a user
    from src.auth.fake_auth import get_or_create_user_by_name
    
    # Get or create a user named "rifah"
    user = get_or_create_user_by_name("rifah")
    user_id = user.id
    user_id_manager.current_user_id = user_id
    logger.info(f"[CONTEXT PREP] Using fake user: {user.name} (ID: {user_id})")

    messages = state["messages"]
    out_messages: List[BaseMessage] = []
    
    if not messages:
        return {"context_prepared": True}

    # Find the latest human message
    latest_human_message = None
    for msg in reversed(messages):
        if hasattr(msg, 'type') and msg.type == "human":
            latest_human_message = msg
            break

    if not latest_human_message:
        return {"context_prepared": True}

    user_input = str(latest_human_message.content) if latest_human_message.content else ""
    
    # Update module-level scratch
    try:
        from collections import deque as _deque
        global LAST_USER_TEXTS
        LAST_USER_TEXTS.append(user_input)
    except Exception:
        pass
    
    logger.info(f"Fetching memories for: {user_input[:50]}...")

    # Always fetch memories if mem0 is configured
    if config.MEM0_API_KEY:
        try:
            # Show context preparation status in chat
            out_messages.append(
                SystemMessage(content=f"🔍 Searching memories for user '{user.name}'...")
            )

            logger.info(f"[CONTEXT PREP] Calling recall_tool with query: '{user_input[:50]}...'")
            start_time = time.time()
            recall_out = await recall_tool.ainvoke({
                "query": user_input,
                "top_k": 6,
            })
            duration = time.time() - start_time
            logger.info(f"[CONTEXT PREP] recall_tool completed in {duration:.2f}s, result length: {len(str(recall_out))}")
            
            if isinstance(recall_out, str) and recall_out.strip():
                # Push UI message with memory results
                try:
                    if recall_out.lower().startswith("related memories:"):
                        memories_text = recall_out.replace("Related memories:", "").strip()
                        memories_list = [m.strip() for m in memories_text.split(";") if m.strip()]
                        
                        # Show memory results in chat
                        out_messages.append(
                            SystemMessage(content=f"🧠 Found {len(memories_list)} memories for user '{user.name}': {memories_list[0] if memories_list else 'None'}")
                        )

                    else:
                        # No memories found
                        logger.info(f"No memories found for user '{user.name}'")
                        out_messages.append(
                            SystemMessage(content=f"🧠 No memories found for user '{user.name}'")
                        )

                except Exception as e:
                    logger.debug(f"Failed to push memory results UI: {e}")
                
                # Add visible tool message
                if recall_out.lower().startswith("related memories:"):
                    out_messages.append(
                        ToolMessage(
                            content=recall_out,
                            name="recall_tool",
                            tool_call_id=f"auto_recall_context_{datetime.utcnow().isoformat()}",
                        )
                    )
                    # Add compact system hint
                    try:
                        compact = recall_out.replace("Related memories:", "").strip()
                        compact = "; ".join([s.strip() for s in compact.split(";")[:3] if s.strip()])
                        if compact:
                            out_messages.insert(0, SystemMessage(content=f"Internal recall: {compact}"))
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Context preparation memory fetch failed: {e}")
            
            # Push error status
            try:
                push_ui_message("contextProgress", {
                    "status": "error",
                    "query": user_input[:100],
                    "error": str(e)[:100],
                    "timestamp": datetime.utcnow().isoformat()
                })
            except Exception as ui_error:
                logger.debug(f"Failed to push error UI: {ui_error}")

    # Always mark prepared for this turn
    if out_messages:
        return {"context_prepared": True, "messages": out_messages}
    return {"context_prepared": True}

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


@tool
async def remember_tool(memory_content: str, context: str = "") -> str:
    """
    Store a natural language memory using mem0's full associative power.
    
    Args:
        memory_content: Natural language description of what to remember
        context: Additional context about when/why this was remembered
    """
    # Create enhanced memory with context
    enhanced_content = memory_content
    if context:
        enhanced_content = f"{memory_content} | Context: {context}"
    
    # Store in mem0 cloud
    if not config.MEM0_API_KEY:
        logger.info("MEM0_API_KEY not configured")
        return f"Memory not stored: {memory_content} (mem0 not configured)"
    
    try:
        logger.info(f"Storing memory in mem0: {memory_content[:50]}...")

        # Define custom categories using the shape expected by mem0 (name + description)

        custom_categories_definitions = [
            {"name": "airline_entities", "description": "Airlines, frequent flyer programs, airline experiences, and airline preferences."},
            {"name": "destination_entities", "description": "Cities, countries, regions, landmarks, and travel destinations."},
            {"name": "travel_preferences", "description": "Seat preferences, cabin class, budget, travel frequency, and style preferences."},
            {"name": "seasonal_patterns", "description": "Seasonal travel preferences, weather preferences, and time-based patterns."},
            {"name": "accommodation_entities", "description": "Hotels, room types, amenities, and accommodation experiences."},
            {"name": "travel_context", "description": "Living in a place vs visiting, business vs leisure, solo vs group travel."},
            {"name": "loyalty_relationships", "description": "Loyalty program memberships, points, miles, and reward preferences."},
            {"name": "travel_history", "description": "Past trips, experiences, and travel memories that inform future decisions."},
            {"name": "preference_inferences", "description": "Inferred preferences based on behavior, choices, and expressed likes/dislikes."},
            {"name": "semantic_connections", "description": "Associative connections between entities, preferences, and contexts."},
        ]
        

        # Ensure project is on API version v2 (best-effort, no-op if already set)
        try:
            from mem0 import MemoryClient as _SyncClient
            _ver_client = _SyncClient(api_key=config.MEM0_API_KEY)
            try:
                _ver_client.project.update(version="v2")
            except Exception:
                try:
                    _ver_client.update_project(version="v2")
                except Exception:
                    pass
        except Exception:
            pass

        # Compute an importance score and TTL policy
        def _score_importance(text: str) -> tuple[str, float, int]:
            t = text.lower()
            # Heuristics: loyalty/preferences higher, transient context lower
            high_markers = ["loyalty", "frequent flyer", "always", "never", "prefers", "preference"]
            med_markers = ["hotel", "flight", "window seat", "aisle seat", "economy", "business", "direct flight"]
            if any(m in t for m in high_markers):
                return ("high", 0.9, 365)
            if any(m in t for m in med_markers):
                return ("medium", 0.6, 120)
            return ("low", 0.3, 30)

        importance, importance_score, ttl_days = _score_importance(enhanced_content)

        # Deduplicate: if an identical memory exists, increment counters and return
        try:
            ac = AsyncMemoryClient(api_key=config.MEM0_API_KEY)
            existing = await ac.search(
                memory_content,
                version="v2",
                filters={"user_id": get_current_user_id()},
            )
            if existing:
                # Simple exact-match check (normalized)
                norm_new = memory_content.strip().lower().rstrip(". ")
                for m in existing[:5]:
                    if (m.get("memory") or "").strip().lower().rstrip(". ") == norm_new:
                        try:
                            from mem0 import MemoryClient
                            def _bump():
                                c = MemoryClient(api_key=config.MEM0_API_KEY)
                                md = m.get("metadata") or {}
                                acc = int(md.get("access_count", 0)) + 1
                                md.update({
                                    "access_count": acc,
                                    "last_accessed": datetime.utcnow().isoformat() + "Z",
                                })
                                c.update(m.get("id"), metadata=md)
                            await asyncio.to_thread(_bump)
                        except Exception:
                            pass
                        return f"Remembered (updated existing): {memory_content}"
        except Exception:
            pass

        # Add the memory and pass explicit categories to ensure assignment
        try:
            client = AsyncMemoryClient(api_key=config.MEM0_API_KEY)
            result = await client.add(
                [
                    {"role": "user", "content": memory_content},
                    {"role": "assistant", "content": enhanced_content},
                ],
                user_id=get_current_user_id(),
                custom_categories=custom_categories_definitions,
                metadata={
                    "importance": importance,
                    "importance_score": importance_score,
                    "ttl_days": ttl_days,
                },
                output_format="v1.1",
            )
        except Exception as async_err:
            logger.warning(
                "Async mem0 add failed (will fallback to sync in thread): %s",
                str(async_err),
            )
            from mem0 import MemoryClient

            def _sync_add() -> Any:
                sync_client = MemoryClient(api_key=config.MEM0_API_KEY)
                return sync_client.add(
                    [
                        {"role": "user", "content": memory_content},
                        {"role": "assistant", "content": enhanced_content},
                    ],
                    user_id=get_current_user_id(),
                    custom_categories=custom_categories_definitions,
                    metadata={
                        "importance": importance,
                        "importance_score": importance_score,
                        "ttl_days": ttl_days,
                    },
                    output_format="v1.1",
                )

            result = await asyncio.to_thread(_sync_add)

        logger.info("Successfully stored memory in mem0")
        return f"Remembered: {memory_content}"

    except asyncio.TimeoutError:
        logger.error("mem0 timeout")
        return f"Memory not stored: mem0 timeout"
    except Exception as e:
        logger.error(f"mem0 failed: {e}")
        return f"Memory not stored: {str(e)[:50]}"

@tool
async def recall_tool(query: str, top_k: int = 6) -> str:
    """
    Simple memory recall with debug logging.
    """
    if not config.MEM0_API_KEY:
        return "No memories available: mem0 not configured"

    try:
        logger.info(f"[RECALL DEBUG] Searching for: '{query}' in namespace: '{get_current_user_id()}'")
        
        # Use sync client in thread to avoid blocking calls
        from mem0 import MemoryClient
        
        # Try different search approaches
        search_results = []
        
        # 1. Simple search without version
        try:
            logger.info(f"[RECALL DEBUG] Trying simple search for: '{query}'")
            def _sync_search_simple():
                client = MemoryClient(api_key=config.MEM0_API_KEY)
                return client.search(query, filters={"user_id": get_current_user_id()})
            simple_results = await asyncio.to_thread(_sync_search_simple)
            logger.info(f"[RECALL DEBUG] Simple search returned {len(simple_results or [])} results")
            if simple_results:
                search_results.extend(simple_results)
        except Exception as e:
            logger.error(f"[RECALL DEBUG] Simple search failed: {e}")
        
        # 2. Search with v2 version
        try:
            logger.info(f"[RECALL DEBUG] Trying v2 search for: '{query}'")
            def _sync_search_v2():
                client = MemoryClient(api_key=config.MEM0_API_KEY)
                return client.search(query, version="v2", filters={"user_id": get_current_user_id()})
            v2_results = await asyncio.to_thread(_sync_search_v2)
            logger.info(f"[RECALL DEBUG] V2 search returned {len(v2_results or [])} results")
            if v2_results:
                search_results.extend(v2_results)
        except Exception as e:
            logger.error(f"[RECALL DEBUG] V2 search failed: {e}")
        
        # 3. Search without filters (all memories)
        try:
            logger.info(f"[RECALL DEBUG] Trying search without filters for: '{query}'")
            def _sync_search_no_filter():
                client = MemoryClient(api_key=config.MEM0_API_KEY)
                return client.search(query)
            no_filter_results = await asyncio.to_thread(_sync_search_no_filter)
            logger.info(f"[RECALL DEBUG] No-filter search returned {len(no_filter_results or [])} results")
            if no_filter_results:
                search_results.extend(no_filter_results)
        except Exception as e:
            logger.error(f"[RECALL DEBUG] No-filter search failed: {e}")
        
        # 4. List all memories to see what's available
        try:
            logger.info(f"[RECALL DEBUG] Listing all memories in namespace: '{get_current_user_id()}'")
            def _sync_list_all():
                client = MemoryClient(api_key=config.MEM0_API_KEY)
                return client.search("*", filters={"user_id": get_current_user_id()})
            all_memories = await asyncio.to_thread(_sync_list_all)
            logger.info(f"[RECALL DEBUG] Total memories in namespace: {len(all_memories or [])}")
            if all_memories:
                logger.info(f"[RECALL DEBUG] Sample memories: {[m.get('memory', '')[:50] for m in all_memories[:3]]}")
        except Exception as e:
            logger.error(f"[RECALL DEBUG] List all failed: {e}")
        
        # Deduplicate results
        unique_memories = {}
        for memory in search_results:
            memory_id = memory.get('id')
            if memory_id and memory_id not in unique_memories:
                unique_memories[memory_id] = memory
        
        memories = list(unique_memories.values())
        logger.info(f"[RECALL DEBUG] Final deduplicated results: {len(memories)}")
        
        if memories:
            # Extract memory content
            memory_texts = []
            for memory in memories[:top_k]:
                content = memory.get('memory', '')
                if content:
                    memory_texts.append(content)
            
            if memory_texts:
                return "Related memories: " + "; ".join(memory_texts)
        
        return f"No memories found related to: {query}"

    except Exception as e:
        logger.error(f"[RECALL DEBUG] Recall failed: {e}")
        return f"No memories found related to your request. Error: {str(e)[:100]}"



@tool
async def extract_entities_tool(text: str) -> str:
    """
    Extract travel-related entities from text for associative memory.
    
    Identifies cities, airlines, preferences, and other travel entities
    to enable knowledge graph traversal and semantic connections.
    
    Args:
        text: Text to extract entities from
        
    Returns:
        JSON string with extracted entities and their categories
    """
    try:
        # Define travel entities to look for
        travel_entities = {
            'cities': ['paris', 'london', 'new york', 'tokyo', 'sydney', 'melbourne', 'brisbane', 'perth', 'singapore', 'dubai'],
            'airlines': ['american airlines', 'delta', 'united', 'qantas', 'virgin', 'jetstar', 'emirates', 'singapore airlines'],
            'preferences': ['window seat', 'aisle seat', 'economy', 'business', 'first class', 'morning flight', 'direct flight'],
            'seasons': ['spring', 'summer', 'autumn', 'winter', 'fall'],
            'accommodations': ['hotel', 'gym', 'city center', 'downtown', 'airport hotel'],
            'activities': ['business', 'leisure', 'vacation', 'sightseeing']
        }
        
        text_lower = text.lower()
        found_entities = {}
        
        # Extract entities by category
        for category, items in travel_entities.items():
            found = []
            for item in items:
                if item in text_lower:
                    found.append(item)
            if found:
                found_entities[category] = found
        
        # Also find capitalized words that might be entities
        import re
        capitalized_words = re.findall(r'\b[A-Z][a-z]+\b', text)
        if capitalized_words:
            found_entities['potential_entities'] = capitalized_words
        
        return json.dumps({
            'entities': found_entities,
            'text': text,
            'message': f'Extracted {sum(len(v) for v in found_entities.values())} entities from text'
        })
    except Exception as e:
        logger.error(f"Error extracting entities: {e}")
        return json.dumps({
            'error': f'Error extracting entities: {str(e)}',
            'text': text
        })

@tool
async def traverse_memory_graph_tool(start_entity: str, depth: int = 2) -> str:
    """
    Traverse the memory graph starting from a specific entity.

    What it does:
    - Finds direct memories related to `start_entity` (e.g., "Paris").
    - Extracts related terms from those memories.
    - If `depth > 1`, searches those related terms to surface indirect associations.

    When to use:
    - After calling `recall_tool` if results are thin or ambiguous, and you need connected context.
    - When the user mentions a strong anchor entity (city/airline) and richer associations could improve recommendations.

    Guidance:
    - Prefer `depth=1` for speed; use `depth=2` only when the query is complex and the extra context is valuable.
    - Do not dump raw memories verbatim to the user. Use the associations to personalize and justify suggestions naturally.

    Args:
        start_entity: The entity to start traversal from (e.g., "Paris", "American Airlines").
        depth: How many levels deep to traverse (default: 2).

    Returns:
        JSON string with traversal results and discovered relationships.
    """
    try:
        logger.info(f"Traversing memory graph from '{start_entity}' with depth {depth}")
        
        # Use sync client in a background thread for traversal searches to avoid event-loop blocking
        from mem0 import MemoryClient
        def _sync_search_start() -> Any:
            sync_client = MemoryClient(api_key=config.MEM0_API_KEY)
            return sync_client.search(
                start_entity,
                version="v2",
                filters={"user_id": get_current_user_id()},
            )
        direct_memories = await asyncio.to_thread(_sync_search_start)
        direct_memories = direct_memories or []
        
        # Extract related terms from direct memories
        related_terms = []
        for memory in direct_memories:
            content = memory.get('memory', '').lower()
            # Find other entities mentioned in these memories
            for term in content.split():
                if len(term) > 3 and term not in [start_entity.lower(), 'user', 'prefers', 'likes', 'travel']:
                    related_terms.append(term)
        
        # If depth > 1, search for memories related to the related terms
        indirect_memories = []
        if depth > 1 and related_terms:
            # Take top related terms and search for them
            top_terms = list(set(related_terms))[:3]  # Limit to 3 terms
            for term in top_terms:
                try:
                    def _sync_search_term() -> Any:
                        sc = MemoryClient(api_key=config.MEM0_API_KEY)
                        return sc.search(
                            term,
                            version="v2",
                            filters={"user_id": get_current_user_id()},
                        )
                    term_memories = await asyncio.to_thread(_sync_search_term)
                    if term_memories:
                        indirect_memories.extend(term_memories)
                except Exception as e2:
                    logger.warning(f"Traversal term search failed for '{term}': {e2}")
                    continue
        
        # Format results
        traversal_result = {
            'start_entity': start_entity,
            'depth': depth,
            'direct_memories': [m.get('memory', '') for m in direct_memories],
            'related_terms': list(set(related_terms)),
            'indirect_memories': [m.get('memory', '') for m in indirect_memories],
            'total_memories_found': len(direct_memories) + len(indirect_memories),
            'message': f'Traversed memory graph from "{start_entity}" - found {len(direct_memories)} direct and {len(indirect_memories)} indirect memories'
        }
        
        return json.dumps(traversal_result, indent=2)
                
    except Exception as e:
        logger.error(f"Error traversing memory graph: {e}")
        return json.dumps({
            'error': f'Error traversing memory graph: {str(e)}',
            'start_entity': start_entity
        })

@tool
async def pin_memory_tool(memory_id: str) -> str:
    """Pin a memory (prevent expiry) by setting metadata.pinned=true."""
    if not config.MEM0_API_KEY:
        return "Cannot pin: mem0 not configured"
    try:
        from mem0 import MemoryClient
        import asyncio as _asyncio
        def _pin() -> dict:
            c = MemoryClient(api_key=config.MEM0_API_KEY)
            return c.update(memory_id, metadata={"pinned": True})
        res = await _asyncio.to_thread(_pin)
        return json.dumps({"status": "pinned", "id": memory_id, "response": res})
    except Exception as e:
        return json.dumps({"error": f"Pin failed: {str(e)[:200]}", "id": memory_id})

@tool
async def unpin_memory_tool(memory_id: str) -> str:
    """Unpin a memory by setting metadata.pinned=false."""
    if not config.MEM0_API_KEY:
        return "Cannot unpin: mem0 not configured"
    try:
        from mem0 import MemoryClient
        import asyncio as _asyncio
        def _unpin() -> dict:
            c = MemoryClient(api_key=config.MEM0_API_KEY)
            return c.update(memory_id, metadata={"pinned": False})
        res = await _asyncio.to_thread(_unpin)
        return json.dumps({"status": "unpinned", "id": memory_id, "response": res})
    except Exception as e:
        return json.dumps({"error": f"Unpin failed: {str(e)[:200]}", "id": memory_id})

@tool
async def update_memory_importance_tool(memory_id: str, importance: str = "medium", importance_score: float = 0.6, ttl_days: int = 120) -> str:
    """Update a memory's importance and TTL metadata."""
    if not config.MEM0_API_KEY:
        return "Cannot update: mem0 not configured"
    try:
        from mem0 import MemoryClient
        import asyncio as _asyncio
        def _upd() -> dict:
            c = MemoryClient(api_key=config.MEM0_API_KEY)
            md = {
                "importance": importance,
                "importance_score": float(importance_score),
                "ttl_days": int(ttl_days),
            }
            return c.update(memory_id, metadata=md)
        res = await _asyncio.to_thread(_upd)
        return json.dumps({"status": "updated", "id": memory_id, "response": res})
    except Exception as e:
        return json.dumps({"error": f"Update importance failed: {str(e)[:200]}", "id": memory_id})

@tool
async def prune_memories_tool(max_age_days: int = 180, min_importance: str = "low") -> str:
    """Prune memories older than max_age_days and with importance below threshold (low < medium < high)."""
    if not config.MEM0_API_KEY:
        return "Cannot prune: mem0 not configured"
    order = {"low": 0, "medium": 1, "high": 2}
    try:
        from mem0 import MemoryClient
        import asyncio as _asyncio
        from datetime import datetime, timezone
        def _prune() -> dict:
            c = MemoryClient(api_key=config.MEM0_API_KEY)
            results = c.search("*", version="v2", filters={"user_id": get_current_user_id()}) or []
            cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
            to_delete = []
            for m in results:
                md = m.get("metadata") or {}
                imp = md.get("importance", "low").lower()
                if order.get(imp, 0) < order.get(min_importance, 0):
                    continue
                # Use created_at timestamp
                created = m.get("created_at")
                try:
                    ts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp() if created else None
                except Exception:
                    ts = None
                if ts is not None and ts < cutoff:
                    to_delete.append(m.get("id"))
            if to_delete:
                c.batch_delete([i for i in to_delete if i])
            return {"deleted": len(to_delete), "ids": to_delete[:50]}
        res = await _asyncio.to_thread(_prune)
        return json.dumps(res)
    except Exception as e:
        return json.dumps({"error": f"Prune failed: {str(e)[:200]}"})
@tool
async def delete_memory_tool(memory_id: str) -> str:
    """Delete a single memory by its ID in mem0."""
    if not config.MEM0_API_KEY:
        return "Cannot delete: mem0 not configured"
    try:
        from mem0 import MemoryClient
        import asyncio as _asyncio
        def _do_delete() -> dict:
            client = MemoryClient(api_key=config.MEM0_API_KEY)
            return client.delete(memory_id)
        resp = await _asyncio.to_thread(_do_delete)
        return json.dumps({"status": "deleted", "id": memory_id, "response": resp})
    except Exception as e:
        return json.dumps({"error": f"Delete failed: {str(e)[:200]}", "id": memory_id})

@tool
async def delete_memories_by_query_tool(query: str, top_k: int = 10) -> str:
    """Search for memories matching `query` (scoped to this namespace) and delete up to `top_k` results."""
    if not config.MEM0_API_KEY:
        return "Cannot delete: mem0 not configured"
    try:
        from mem0 import MemoryClient
        import asyncio as _asyncio
        def _do_search_and_delete() -> dict:
            client = MemoryClient(api_key=config.MEM0_API_KEY)
            results = client.search(query, version="v2", filters={"user_id": get_current_user_id()}) or []
            ids = [r.get("id") for r in results[: max(1, min(int(top_k), 100))] if r.get("id")]
            if not ids:
                return {"deleted": 0, "ids": []}
            resp = client.batch_delete([{"memory_id": i} for i in ids])
            return {"deleted": len(ids), "ids": ids, "response": resp}
        data = await _asyncio.to_thread(_do_search_and_delete)
        return json.dumps(data)
    except Exception as e:
        return json.dumps({"error": f"Batch delete failed: {str(e)[:200]}"})

@tool
async def delete_all_namespace_memories_tool(confirm: bool = False) -> str:
    """Delete ALL memories for the current namespace (irreversible). Pass confirm=True to proceed."""
    if not config.MEM0_API_KEY:
        return "Cannot delete: mem0 not configured"
    if not confirm:
        return "Refused: set confirm=True to delete all memories for this namespace"
    try:
        from mem0 import MemoryClient
        import asyncio as _asyncio
        def _wipe() -> dict:
            client = MemoryClient(api_key=config.MEM0_API_KEY)
            total = 0
            while True:
                results = client.search("*", version="v2", filters={"user_id": get_current_user_id()}) or []
                ids = [r.get("id") for r in results[:100] if r.get("id")]
                if not ids:
                    break
                client.batch_delete([{"memory_id": i} for i in ids])
                total += len(ids)
                if len(ids) < 100:
                    break
            return {"deleted_total": total}
        res = await _asyncio.to_thread(_wipe)
        return json.dumps(res)
    except Exception as e:
        return json.dumps({"error": f"Namespace wipe failed: {str(e)[:200]}"})

@tool
async def list_memories_tool() -> str:
    """List all memories stored in mem0."""
    if not config.MEM0_API_KEY:
        return "No memories available: mem0 not configured"
    
    try:
        logger.info("Listing all memories from mem0 (sync in thread)")
        from mem0 import MemoryClient
        import asyncio as _asyncio
        def _sync_list() -> Any:
            try:
                c = MemoryClient(api_key=config.MEM0_API_KEY)
                return c.search("*", version="v2", filters={"user_id": get_current_user_id()}) or []
            except Exception:
                return []
        memories = await _asyncio.to_thread(_sync_list)
        if memories:
            memory_list = []
            for i, memory in enumerate(memories[:10], 1):
                content = memory.get('memory', 'No content found')
                # Sanitize any runtime guard noise
                if isinstance(content, str) and 'Blocking call to socket' in content:
                    continue
                md = memory.get('metadata') or {}
                imp = md.get('importance')
                ttl = md.get('ttl_days')
                pin = md.get('pinned')
                suffix = []
                if imp:
                    suffix.append(f"importance={imp}")
                if ttl:
                    suffix.append(f"ttl_days={ttl}")
                if pin:
                    suffix.append("pinned")
                extra = f" ({', '.join(suffix)})" if suffix else ""
                memory_list.append(f"{i}. {content}{extra}")
            return f"Found {len(memories)} memories:\n" + "\n".join(memory_list)
        else:
            return "No memories found"
    except Exception as e:
        logger.error(f"Failed to list memories: {e}")
        return f"Error listing memories: {str(e)[:50]}"

# Create the graph
def create_graph():
    """Create and configure the LangGraph workflow."""
    logger.info("Creating LangGraph workflow")
    
    try:
        # Initialize tools
        tools = [
            get_current_time,
            calculate_simple_math,
            search_web,
            validate_phone_number_tool,
            search_flights_tool,
            search_hotels_tool,
            fetch_hotel_rates_tool,
            create_quote_tool,
            create_booking_tool,
            fetch_flight_quote_tool,
            create_flight_booking_tool,
            get_seat_maps_tool,
            list_airline_initiated_changes_tool,
            update_airline_initiated_change_tool,
            accept_airline_initiated_change_tool,
            change_flight_booking_tool,
            cancel_flight_booking_tool,
            cancel_hotel_booking_tool,
            update_hotel_booking_tool,
            list_loyalty_programmes_tool,
            list_flight_loyalty_programmes_tool,
            fetch_extra_baggage_options_tool,
            get_available_services_tool,
            fetch_accommodation_reviews_tool,
            remember_tool,
            recall_tool,
            extract_entities_tool,
            traverse_memory_graph_tool,
            list_memories_tool,
            delete_memory_tool,
            delete_memories_by_query_tool,
            delete_all_namespace_memories_tool,
            pin_memory_tool,
            unpin_memory_tool,
            update_memory_importance_tool,
            prune_memories_tool
        ]
        logger.debug(f"Initializing ToolNode with {len(tools)} tools: {[tool.name for tool in tools]}")
        tool_node = ToolNode(tools)

        # Create the graph
        logger.debug("Creating StateGraph with AgentState")
        workflow = StateGraph(AgentState)

        # Add nodes
        logger.debug("Adding nodes to workflow")
        workflow.add_node("context_preparation", context_preparation_node)
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        workflow.add_node("human_input", human_input_node)
        logger.info("Added 4 nodes: context_preparation, agent, tools, human_input")

        # Set the entry point
        logger.debug("Setting entry point from START to context_preparation")
        workflow.add_edge(START, "context_preparation")
        workflow.add_edge("context_preparation", "agent")

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

        # After human input, go back to context_preparation (to prepare context for new input)
        logger.debug("Adding edge from human_input back to context_preparation")
        workflow.add_edge("human_input", "context_preparation")

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

# Global user metadata storage
global_user_metadata = {}

def set_user_metadata(user_id: str, user_email: str):
    """Set global user metadata for thread creation."""
    global global_user_metadata
    global_user_metadata = {
        "user_id": user_id,
        "user_email": user_email
    }
    logger.info(f"[USER METADATA] Set global user metadata: {global_user_metadata}")

def get_user_metadata():
    """Get global user metadata."""
    global global_user_metadata
    return global_user_metadata.copy()
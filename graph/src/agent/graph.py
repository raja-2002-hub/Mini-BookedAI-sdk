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
from langgraph.types import Command
from typing import Literal
from langgraph.checkpoint.memory import MemorySaver
import psycopg

# Import our Duffel client
from src.duffel_client.endpoints.stays import search_hotels, fetch_hotel_rates, create_quote, create_booking, cancel_hotel_booking, update_hotel_booking, extend_hotel_stay
from src.duffel_client.endpoints.flights import search_flights, format_flights_markdown, get_seat_maps,fetch_flight_offer, create_flight_booking, list_airline_initiated_changes, update_airline_initiated_change, accept_airline_initiated_change
from src.duffel_client.client import DuffelAPIError
from src.config import config


# --- Flight Order Change Tools ---
from src.duffel_client.endpoints.flights import (
    create_order_change_request_api,  # Only this is needed for changing flights
)

from src.duffel_client.endpoints.flights import create_order_cancellation, confirm_order_cancellation, cancel_flight_booking_with_refund

from src.duffel_client.endpoints.payments import (
    create_stripe_payment_intent,
    create_stripe_token
)

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


logger = logging.getLogger(__name__)

TOOL_UI_MAPPING = {
    "search_hotels_tool": "hotelResults",
    "search_flights_tool": "flightResults",
    "flight_payment_sequence_tool": "paymentForm",
    "hotel_payment_sequence_tool": "paymentForm",
    "extend_hotel_stay_tool": "paymentForm"
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
    booking_intent: Optional[bool]
    current_agent: Optional[str]    




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
async def validate_phone_number_tool(phone: str, client_country: str | None = None) -> str:
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
            # Require client-provided country (from browser). Do not use server IP geolocation in production.
            if not client_country or not isinstance(client_country, str):
                return (
                    "Error: Could not determine your country automatically. "
                    "Please enter the phone with +<country_code> (e.g., +1..., +44...)."
                )
            region = client_country.strip().upper()[:2]
            country_name = region
            try:
                parsed = phonenumbers.parse(phone, region)
            except Exception as e:
                return (
                    "Error: Please include your country code (e.g., +1 for US, +44 for UK). "
                    f"Parsing failed with region {region}: {str(e)}"
                )

        if not phonenumbers.is_valid_number(parsed):
            return "Error: Invalid phone number"

        formatted_number = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        
        # Return validated phone number without confirmation
        return f"Valid phone number: {formatted_number} (region: {country_name})"
        
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
    max_results: int = 5,
    hotel_name: str = None
) -> str:

    """
    Searches for hotels based on location, dates, guest details and optionally a specific hotel name.

    Location and dates are required, while the number of adults and children is optional. If not provided, the search will assume 1 adult and 0 children—no need to ask the user or mention these defaults unless you're quoting or booking.

    Check-in and check-out dates can be entered in natural language or standard formats, but they must resolve to future dates. If a past date is given, it’ll be automatically adjusted to the next valid future date. The check-out date must always be after the check-in date, or an error will be returned.

    If any required information is missing (except adults or children), ask the user for clarification.

    If `hotel_name` is provided, the tool will attempt to geocode the hotel name (optionally with city/location) to obtain latitude and longitude, and perform a targeted search with a small radius.
    If `hotel_name` is not provided, the tool will search by the given location (city/country).
    
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
        
        if hotel_name:
            location = f"{hotel_name}, {location}"
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
async def create_hotel_quote_tool(rate_id: str) -> str:
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
async def create_hotel_booking_tool(
    quote_id: str,
    guests: list,
    email: str,
    payments: list = None,
    stay_special_requests: str = "",
    phone_number: str = ""
) -> str:
    """
    Book a hotel stay using a Duffel quote.
    Args:
        quote_id: The quote ID (quo_...)
        guests: List of guest dicts (given_name, family_name, born_on)
        email: Contact email
        payments: List of payment objects (from capture_payment_tool)
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
        # Handle payment tokenization if raw card data is provided
        if payments and isinstance(payments, list) and len(payments) > 0:
            payment = payments[0]
            if isinstance(payment, dict) and payment.get("number") and not payment.get("card_id"):
                try:
                    # Tokenize raw card
                    tokenized_payment = await build_card_payment(
                        payment, quote_id, config.DUFFEL_API_TOKEN
                    )
                    payments = [tokenized_payment]
                    logger.info("Card tokenized successfully")
                except Exception as tok_err:
                    return f"Error tokenizing card: {tok_err}"

        response = await create_booking(
            quote_id, guests, email, stay_special_requests, phone_number, payments
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

    Args:
        offer_id: The offer ID (off_...)
        passengers: List of passenger dicts.
        payments: List of payment dicts.

    Returns:
        JSON string of the booking/order response or error message.
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

    # ---------- Tokenise raw card if needed ----------
    if payments and isinstance(payments[0], dict) and payments[0].get("number") and not payments[0].get("card_id"):
        try:
            payments = [
                await build_card_payment(
                    payments[0],        # raw card dict
                    offer_id,           # resource the card will pay for
                    config.DUFFEL_API_TOKEN,
                )
            ]
        except Exception as tok_err:
            return f"Error tokenising card: {tok_err}"
    
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
async def extend_hotel_stay_tool(
    booking_id: str,
    check_in_date: str,
    check_out_date: str,
    preferred_rate_id: Optional[str] = None,
    customer_confirmation: bool = False,
    payment: Optional[Dict[str, Any]] = None
) -> str:
    """
    Extend a hotel booking's stay dates by cancelling the existing booking and creating a new one.

    Use this tool when the user wants to extend their hotel stay (e.g., change check-in or check-out date).
    This tool will:
    1. Fetch existing booking details
    2. Search for availability for the new dates
    3. Fetch detailed rates
    4. Return cost change for confirmation (if customer_confirmation=False)
    5. Return payment form if no payment provided
    6. Cancel the original booking and create a new one (if customer_confirmation=True and payment provided)

    Args:
        booking_id: The ID of the booking to extend (e.g., "bok_0000AxNtHvxFHgcXbJQFW4").
        check_in_date: The new check-in date in natural language or YYYY-MM-DD (e.g., "2025-09-14").
        check_out_date: The new check-out date in natural language or YYYY-MM-DD (e.g., "2025-09-16").
        preferred_rate_id: Optional rate ID to use (e.g., "rat_0000AxOD48JMHJGKwszWYI").
        customer_confirmation: If False, returns cost change; if True, proceeds.
        payment: Optional payment details (e.g., {"type": "balance"} or card details).

    Returns:
        JSON string with booking ID, cost change, payment form, or error message.
    """
    logger.info(f"Extend hotel stay initiated for booking: {booking_id}, check-in: {check_in_date}, check-out: {check_out_date}")
    try:
        # Normalize dates
        check_in_date = await parse_and_normalize_date(check_in_date)
        check_out_date = await parse_and_normalize_date(check_out_date)
        logger.debug(f"Normalized dates - Check-in: {check_in_date}, Check-out: {check_out_date}")

        # Validate dates
        check_in = datetime.strptime(check_in_date, "%Y-%m-%d").date()
        check_out = datetime.strptime(check_out_date, "%Y-%m-%d").date()
        if check_out <= check_in:
            return json.dumps({"error": "Check-out date must be after check-in date"})
        if check_in < date.today():
            return json.dumps({"error": "Check-in date cannot be in the past"})

        # Validate booking_id
        if not booking_id or not booking_id.startswith("bok_"):
            return json.dumps({"error": "Invalid booking_id, must start with 'bok_'"})

        # Check API token
        if not config.DUFFEL_API_TOKEN:
            logger.error("Duffel API token not configured")
            return json.dumps({"error": "Hotel stay extension unavailable: Duffel API token not configured"})
        
        logger.info(f"Fetching existing booking details:{booking_id}")

        # Call the stays endpoint
        response = await extend_hotel_stay(
            booking_id, check_in_date, check_out_date, preferred_rate_id, customer_confirmation, payment
        )
        logger.info(f"Extend hotel stay completed for booking: {booking_id}")
        return json.dumps(response)

    except GraphInterrupt as gi:
        # Propagate interruption for human input
        logger.info(f"GraphInterrupt caught: {gi}")
        raise

    except DuffelAPIError as e:
        logger.error(f"Duffel API error during hotel stay extension: {e}")
        error_title = "API Error"
        error_detail = "Please try again later"
        if hasattr(e, "error"):
            if isinstance(e.error, dict):
                error_title = e.error.get("title", error_title)
                error_detail = e.error.get("detail", error_detail)
            else:
                error_title = str(e.error) if e.error else "API Error"
        error_response = {"error": f"{error_title} - {error_detail}"}
        return json.dumps(error_response)
    except Exception as e:
        logger.error(f"Unexpected error during hotel stay extension: {str(e)}")
        error_response = {"error": f"Unexpected error: {str(e)}"}
        return json.dumps(error_response)
    
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
async def flight_payment_sequence_tool(
    offer_id: str,
    passengers: list,
    email: str,
    payment_method: Dict[str, Any]=None,
    phone_number: str = "",
    include_seat_map: bool = False,
    **kwargs
) -> str:
    """
    Complete FLIGHT booking payment sequence.
    Use this tool ONLY for FLIGHT bookings.
    
    IMPORTANT: Before calling this tool, collect ALL required information:
    - Passenger details (name, birth date, email, phone)
    - Payment method (card details, balance, etc.) 
    - Seat selection preference (yes/no)    
    
    Args:
        offer_id: The flight offer ID (off_...)
        passengers: List of passenger details (must include given_name,born_on and family_name)
        email: Contact email
        payment_method: Payment information (card details, balance, etc.)
        phone_number: Contact phone number
        include_seat_map: If True, retrieve seat map before booking
    
    Returns:
        JSON string with booking confirmation or error
    """
    logger.info(f"Flight payment sequence initiated for offer: {offer_id}")
    quote_data = await fetch_flight_offer(offer_id)
    logger.info(quote_data)
    amount = quote_data.get("data", {}).get("total_amount")
    currency = quote_data.get("data", {}).get("total_currency")
    if not passengers or not all(['given_name' in g and 'family_name' in g and 'born_on' in g for g in passengers]):
        return json.dumps({
            "status": "need_guest_info",
            "message": "Please provide complete guest details (given_name and family_name)"
        })
    
    # Step 1: Get seat map if requested
    if include_seat_map and not kwargs.get("selected_seats"):
        logger.info("Step 1: Retrieving seat map")
        try:
            seat_maps = await get_seat_maps(offer_id)
            return json.dumps({
            "status": "seat_map_retrieved",
            "message": "Seat map retrieved. Please choose seats by their service_id and call again with 'selected_seats'.",
            "seat_map": seat_maps,
            "metadata": {
                "offer_id": offer_id,
                "passengers": passengers,
                "email": email,
                "phone_number": phone_number,
                "payment_method": payment_method
                }
            })
        except Exception as e:
            return json.dumps({"error": f"Seat map retrieval failed: {str(e)}"})
    
    # STEP 2 — Ask for payment if not provided
    if not payment_method:        

        return json.dumps({
            "ui_type": "paymentForm",
            "data": {
                "title": "Complete Payment",
                "amount": amount,
                "currency": currency,
                "fields": [
                    {
                        "name": "cardNumber",
                        "label": "Card Number",
                        "type": "text",
                        "required": True
                    },
                    {
                        "name": "expiryDate",
                        "label": "Expiry Date",
                        "type": "text",
                        "required": True
                    },
                    {
                        "name": "cvc",
                        "label": "CVC",
                        "type": "text", 
                        "required": True
                    },
                    {
                        "name": "name",
                        "label": "Cardholder Name",
                        "type": "text",
                        "required": True
                    }
                ]
            },
            "metadata": {
                "guests": passengers,
                "email": email,
                "phone_number": phone_number,
                "offer_id": offer_id
            }
        })
    
    # STEP 3 — Process payment
        
    logger.info("Step 2: Processing payment")
    logger.info(f"Stripe Integration: Creating test balance payment::{payment_method}")
    card_details = {
        "card[number]": payment_method.get("card_number"),
        "card[exp_month]": payment_method.get("expiry_month"),
        "card[exp_year]": payment_method.get("expiry_year"),
        "card[cvc]": payment_method.get("cvc") or payment_method.get("cvv"),
        "card[name]": payment_method.get("cardholder_name")
    }
    token_response = await create_stripe_token(card_details)
    token_id = token_response["token_id"]
    logger.info(f"Created Stripe token: {token_id}")

    # Create Stripe Payment Intent
    intent_response = await create_stripe_payment_intent(
        amount=amount,
        currency=currency,
        token_id=token_id,
        return_url="https://your-server.com/return"
    )
    payment_intent_id = intent_response["payment_intent_id"]
    logger.info(f"Created Stripe Payment Intent: {payment_intent_id}")
    
    # Create payment object for Duffel
    payment = {
        "type": "balance",  
        "amount": amount,
        "currency": currency,
        "stripe_payment_intent_id": payment_intent_id
    }
    payments = [payment]       
    
    # STEP 4 — Build services list if selected seats provided
    services = []
    if kwargs.get("selected_seats"):
        logger.info(f"Adding {len(kwargs['selected_seats'])} selected seats to services list")
        for seat in kwargs["selected_seats"]:
            services.append({"id": seat["service_id"], "quantity": 1})

    logger.info("Step 3: Creating booking")

    # Ensure email and phone number are inside passengers
    for passenger in passengers:
        if "email" not in passenger:
            passenger["email"] = email
        if "phone_number" not in passenger:
            passenger["phone_number"] = phone_number

    try:
        # Direct function call instead of tool
        booking_result = await create_flight_booking(offer_id, passengers, payments,services=services if services else None)
        logger.info("Flight payment sequence completed successfully")
        
        return json.dumps(booking_result)
    except Exception as e:
        return json.dumps({"error": f"Booking creation failed: {str(e)}"})

@tool
async def hotel_payment_sequence_tool(
    rate_id: str,
    guests: list,
    email: str,
    payment_method: Dict[str, Any]=None,
    phone_number: str = "",
    stay_special_requests: str = "",
    **kwargs
) -> str:
    """
    Complete HOTEL booking payment sequence.
    Use this tool ONLY for HOTEL bookings.
    
    IMPORTANT: Before calling this tool, collect ALL required information:
    - Guest details (name, email, phone)
    - Payment method (card details, balance, etc.)
    
    Args:
        rate_id: The hotel rate ID (rat_...)
        guests: List of guest details (must include given_name and family_name)
        email: Contact email
        payment_method: Payment information (card details, balance, etc.)
        phone_number: Contact phone number
        stay_special_requests: Special requests for the stay
    
    Returns:
        JSON string with booking confirmation or error
    """
    logger.info(f"Hotel payment sequence initiated for rate: {rate_id}")
    logger.debug(f"[PAYMENT FLOW] Payment method received: {json.dumps(payment_method, indent=2)}")
    quote_data = await create_quote(rate_id)

    
    # Validate required fields
    if not guests or not all(['given_name' in g and 'family_name' in g for g in guests]):
        return json.dumps({
            "status": "need_guest_info",
            "message": "Please provide complete guest details (given_name and family_name)"
        })
    
    if not payment_method:
        # Get price info first to show in payment form
        try:
            
            amount = quote_data.get("data", {}).get("total_amount")
            currency = quote_data.get("data", {}).get("total_currency")
        except Exception as e:
            logger.error(f"Failed to get quote: {str(e)}")
            amount = "0.00"
            currency = "AUD"
        return json.dumps({
            "ui_type": "paymentForm",
            "data": {
                "title": "Complete Payment",
                "amount": amount,
                "currency": currency,
                "fields": [
                    {
                        "name": "cardNumber",
                        "label": "Card Number",
                        "type": "text",
                        "required": True
                    },
                    {
                        "name": "expiryDate",
                        "label": "Expiry Date",
                        "type": "text",
                        "required": True
                    },
                    {
                        "name": "cvc",
                        "label": "CVC",
                        "type": "text", 
                        "required": True
                    },
                    {
                        "name": "name",
                        "label": "Cardholder Name",
                        "type": "text",
                        "required": True
                    }
                ]
            },
            "metadata": {
                "guests": guests,
                "email": email,
                "phone_number": phone_number,
                "stay_special_requests": stay_special_requests               
            }
        })
    
    try:
        # Step 1: Create quote
        logger.info("Step 1: Creating quote")
        
        if "error" in quote_data:
            if "rate_unavailable" in quote_data["error"]:
                return json.dumps({
                    "status": "rate_expired",
                    "message": "This rate is no longer available. Please search again for fresh rates."
                })
            return json.dumps({"error": f"Quote creation failed: {quote_data['error']}"})
        
        quote_id = quote_data.get("data", {}).get("id") or quote_data.get("quote_id")
        total_currency= quote_data.get("data", {}).get("total_currency") or quote_data.get("total_currency")
        total_amount= quote_data.get("data", {}).get("total_amount") or quote_data.get("total_amount")
        
        if not quote_id:
            return json.dumps({"error": "Could not extract quote ID from response"})
        
        # Step 2: Process payment
        logger.info("Step 2: Processing payment")        
        logger.info(f"Stripe Integration: Creating balance payment::{payment_method}")
        card_details = {
            "card[number]": payment_method.get("card_number"),
            "card[exp_month]": payment_method.get("expiry_month"),
            "card[exp_year]": payment_method.get("expiry_year"),
            "card[cvc]": payment_method.get("cvc") or payment_method.get("cvv"),
            "card[name]": payment_method.get("cardholder_name")
        }
        token_response = await create_stripe_token(card_details)
        token_id = token_response["token_id"]
        logger.info(f"Created Stripe token: {token_id}")

        # Create Stripe Payment Intent
        intent_response = await create_stripe_payment_intent(
            amount=total_amount,
            currency=total_currency,
            token_id=token_id,
            return_url="https://your-server.com/return"
        )
        payment_intent_id = intent_response["payment_intent_id"]
        logger.info(f"Created Stripe Payment Intent: {payment_intent_id}")
        
        # Create payment object for Duffel
        payment = {
            "stripe_payment_intent_id": payment_intent_id
        }        
        
        # Step 3: Create booking
        logger.info("Step 3: Creating booking")
        logger.info(f"Payment: {payment}")
        booking_result = await create_booking(
            quote_id=quote_id,
            guests=guests,
            email=email,
            stay_special_requests=stay_special_requests,
            phone_number=phone_number,
            payment=payment if payment else None
        )
        
        logger.info("Hotel payment sequence completed successfully")        
        return json.dumps(booking_result)
        
    except Exception as e:
        logger.error(f"Hotel payment sequence failed: {str(e)}")
        return json.dumps({"error": f"Booking sequence failed: {str(e)}"})

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
async def cancel_flight_booking_tool(
    order_id: str,
    proceed_despite_warnings: bool = False  # New param
) -> str:
    """
    Cancel a flight booking and optionally process a refund.
    
    If the booking is non-refundable or past the cancellation deadline, this tool will return an error requiring user confirmation.
    On the next call, set proceed_despite_warnings=True to force proceed (even if no refund is issued).
    
    Args:
        order_id: The flight order ID to cancel (e.g., "ord_0000AxNtHvxFHgcXbJQFW4").
        proceed_despite_warnings: Set to True if the user has confirmed to proceed even if non-refundable or past deadline. Default False.
        
    Returns:
        JSON string with cancellation details or error message.
    """
    try:
        return await cancel_flight_booking_with_refund(
            order_id=order_id,
            proceed_despite_warnings=proceed_despite_warnings 
        )
    except GraphInterrupt as gi:
            return json.dumps({"error": str(gi), "requires_confirmation": True})
    except DuffelAPIError as e:
            error_data = {
                'type': e.error.get('type', 'client_error') if hasattr(e, 'error') and isinstance(e.error, dict) else 'client_error',
                'title': e.error.get('title', 'Cancellation failed') if hasattr(e, 'error') and isinstance(e.error, dict) else 'Cancellation failed',
                'detail': e.error.get('detail', str(e)) if hasattr(e, 'error') and isinstance(e.error, dict) else str(e)
            }
            return json.dumps({"error": f"{error_data['title']}: {error_data['detail']}"})
    except Exception as e:
            return json.dumps({"error": f"Unexpected error: {str(e)}"})

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

    if isinstance(tool_data, str):
        try:
            tool_data = json.loads(tool_data)
        except json.JSONDecodeError:
            # Special case: Check if it's a payment sequence tool with raw string
            if tool_message.name in ["flight_payment_sequence_tool", "hotel_payment_sequence_tool"]:
                return True, "paymentForm"
            return False, None
        
    tool_name = tool_message.name
    logger.info(f"[UI PUSH] Evaluating UI push for tool: {tool_name}")
    logger.debug(f"[UI PUSH] Tool data keys: {list(tool_data.keys()) if isinstance(tool_data, dict) else 'not dict'}")
    logger.debug(f"[UI PUSH] Tool data type: {type(tool_data)}")

    # First check for explicit UI type in the tool data (highest priority)
    if isinstance(tool_data, dict) and "ui_type" in tool_data:
        ui_type = tool_data["ui_type"]
        logger.info(f"[UI PUSH] Found explicit ui_type in data: {ui_type}")
        return True, ui_type
    
    # Check if tool has UI mapping
    ui_type = TOOL_UI_MAPPING.get(tool_name)
    if not ui_type:
        logger.info(f"[UI PUSH] No UI mapping found for tool: {tool_name}. Available mappings: {list(TOOL_UI_MAPPING.keys())}")
        return False, None
    
    logger.info(f"[UI PUSH] Found UI mapping: {tool_name} -> {ui_type}")

    # Payment sequence tools - highest priority
    if tool_name in ["flight_payment_sequence_tool", "hotel_payment_sequence_tool"]:
        logger.info(f"[UI PUSH] Processing payment sequence tool")
        if isinstance(tool_data, dict):
            # Explicit payment request status
            if tool_data.get("status") == "need_payment_info":
                logger.info(f"[UI PUSH] ✓ Payment form needed (explicit request)")
                return True, "paymentForm"
            
    if tool_name == "extend_hotel_stay_tool":
        logger.info(f"[UI PUSH] Processing extend_hotel_stay_tool")
        if isinstance(tool_data, dict):
            # Handle confirmation text
            if "message" in tool_data and "rates" in tool_data:
                logger.info(f"[UI PUSH] ✓ Returning confirmation text")
                return True, None  # Return text without specific UI type
            # Only push payment form if payment is not provided and status isn't success
            if tool_data.get("payment_provided", False) or tool_data.get("status") == "success":
                logger.info(f"[UI PUSH] ✗ Payment provided or success status, skipping payment form")
                return False, None
            logger.info(f"[UI PUSH] ✓ Payment form needed (no payment provided)")
            return True, "paymentForm"
    
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
        if isinstance(tool_data, dict) and tool_data.get("status") in ["need_payment_info"]:
            logger.info(f"[UI PUSH] ✓ Payment form needed")
            return True, ui_type
        logger.info(f"[UI PUSH] ✗ No payment form needed")
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
    logger.debug(f"[AGENT FLOW] Current messages: {[msg.type for msg in state['messages']]}")
    logger.debug(f"[INIT] Available UI mappings: {TOOL_UI_MAPPING}")
    logger.debug(f"[INIT] State keys: {list(state.keys())}")
    logger.debug(f"[INIT] UI enabled setting: {state.get('ui_enabled', 'not_set')}")    

    llm = create_llm()
    tools = [
        get_current_time,
        calculate_simple_math,
        validate_phone_number_tool,
        search_flights_tool,
        search_hotels_tool,
        fetch_hotel_rates_tool,
        create_hotel_quote_tool,
        fetch_flight_quote_tool,
        get_seat_maps_tool,
        list_airline_initiated_changes_tool,
        update_airline_initiated_change_tool,
        accept_airline_initiated_change_tool,
        change_flight_booking_tool,
        cancel_flight_booking_tool,
        cancel_hotel_booking_tool,
        update_hotel_booking_tool,        
        flight_payment_sequence_tool,
        hotel_payment_sequence_tool,
        list_loyalty_programmes_tool,
        list_flight_loyalty_programmes_tool,
        fetch_extra_baggage_options_tool,
        get_available_services_tool,
        fetch_accommodation_reviews_tool,
        extend_hotel_stay_tool
    ]
    llm_with_tools = llm.bind_tools(tools)
    
    # System prompt
    system_prompt = """
<identity>
You are Luna, a knowledgeable and personable AI travel consultant for BookedAI. You combine the expertise of a seasoned travel agent with the efficiency of AI to create perfectly tailored travel experiences.
</identity>

<personality>
- Warm, enthusiastic, and genuinely excited about helping people discover amazing travel experiences
- Professional yet conversational - like talking to a friend who happens to be a travel expert
- Patient and thorough, ensuring no detail is overlooked
- Culturally aware and sensitive to different travel styles and preferences
</personality>

<instructions>
Act as a proactive travel consultant who builds a complete understanding of each traveler's unique needs before making recommendations. Guide users through a personalized consultation process to uncover their ideal trip.
</instructions>

<response_format>
When providing recommendations:
- Start with a brief summary of understanding their needs
- Present options in order of best match to preferences
- Include specific reasons why each suggestion suits them
- Add "insider tips" or "local secrets" to add value
- Mention potential drawbacks honestly
- End with a question to guide next steps
</response_format>

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
        pass
            # logger.info(f"Message {idx}: role={getattr(msg, 'role', None)}, content={getattr(msg, 'content', None)}, tool_calls={getattr(msg, 'tool_calls', None)}")
    
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
    logger.debug(f"[AGENT FLOW] Last message content: {state['messages'][-1].content if state['messages'] else 'No messages'}")
    # This will pause execution and wait for human input
    raise GraphInterrupt("Please provide additional input or guidance for the agent.")


 # context_preparation node removed

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
            get_current_time,
            calculate_simple_math,
            validate_phone_number_tool,
            search_flights_tool,
            search_hotels_tool,
            fetch_hotel_rates_tool,
            create_hotel_quote_tool,
            fetch_flight_quote_tool,
            get_seat_maps_tool,
            list_airline_initiated_changes_tool,
            update_airline_initiated_change_tool,
            accept_airline_initiated_change_tool,
            change_flight_booking_tool,
            cancel_flight_booking_tool,
            cancel_hotel_booking_tool,
            update_hotel_booking_tool,            
            flight_payment_sequence_tool,
            hotel_payment_sequence_tool,
            list_loyalty_programmes_tool,
            list_flight_loyalty_programmes_tool,
            fetch_extra_baggage_options_tool,
            get_available_services_tool,
            fetch_accommodation_reviews_tool,
            extend_hotel_stay_tool
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

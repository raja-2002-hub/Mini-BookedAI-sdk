"""
Duffel Stays API endpoint for hotel search functionality.
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import date, datetime, timezone
from langgraph.errors import GraphInterrupt

from geopy.geocoders import Nominatim

from ..client import DuffelClient, DuffelAPIError
from ..models.stays import HotelSearchRequest, HotelSearchResponse, Hotel, Room, Rate, Amenity
from ..models.common import Money, Address, Coordinates, DateRange, Guest


logger = logging.getLogger(__name__)
geolocator = Nominatim(user_agent="booked-ai")

class StaysEndpoint:
    """Handles Duffel Stays API operations."""
    
    def __init__(self, client: DuffelClient):
        self.client = client
    
    async def search_hotels(self, request: HotelSearchRequest) -> HotelSearchResponse:
        """Search for hotels using Duffel Stays API.
        
        Args:
            request: Hotel search request parameters
            
        Returns:
            Hotel search response with results
            
        Raises:
            DuffelAPIError: For API errors
        """
        try:
            # Convert search request to Duffel API JSON body
            request_data = await request.to_duffel_request()
            
            # Make POST request to Duffel Stays API
            response_data = await self.client.post("/stays/search", data=request_data)
            
            # Parse response into our models
            hotels = self._parse_hotels_response(response_data)
            
            return HotelSearchResponse(
                data=hotels,
                meta=response_data.get("meta", {})
            )
            
        except DuffelAPIError:
            raise
        except Exception as e:
            # Wrap unexpected errors
            raise DuffelAPIError({
                'type': 'client_error',
                'title': 'Hotel search failed',
                'detail': str(e)
            })
        
    async def fetch_all_rates(self, search_result_id: str) -> Dict[str, Any]:
        """Fetch all rates for a specific search result.
        
        Args:
            search_result_id: The search result ID (srr_...)
            
        Returns:
            Raw API response with detailed room/rate information
            
        Raises:
            DuffelAPIError: For API errors
        """
        try:
            # Make POST request to Duffel Stays API
            endpoint = f"/stays/search_results/{search_result_id}/actions/fetch_all_rates"
            response_data = await self.client.post(endpoint, data={})
            
            logger.info(f"Successfully fetched rates for {search_result_id}")
            return response_data
        
        except Exception as e:
            # Wrap unexpected errors
            logger.error(f"Error fetching rates for {search_result_id}: {e}")
            raise DuffelAPIError(f"Failed to fetch rates: {str(e)}")
        
    async def create_quote(self, rate_id: str) -> dict:
        """Create a quote for a given rate."""
        endpoint = "/stays/quotes"
        data = {"data": {"rate_id": rate_id}}
        return await self.client.post(endpoint, data=data)
    
    async def create_booking(
        self,
        quote_id: str,
        guests: list,
        email: str,
        stay_special_requests: str = "",
        phone_number: str = "",
        payment: dict = None
    ) -> dict:
        """Create a booking for a given quote."""
        endpoint = "/stays/bookings"
        data = {
            "data": {
                "quote_id": quote_id,
                "guests": guests,
                "email": email,
                "stay_special_requests": stay_special_requests,
                "phone_number": phone_number,
            }
        }
        logger.info(f"Payment in stays.py: {payment}")
        # if payment:            
        #     data["data"]["payment"] = payment
        logger.info(f"Data in stays.py before sending to api: {data}")
        return await self.client.post(endpoint, data=data)
    
    async def cancel_booking(self, booking_id: str) -> dict:
        """Cancel a hotel booking by booking_id."""
        endpoint = f"/stays/bookings/{booking_id}/actions/cancel"
        try:
            response = await self.client.post(endpoint, data={})
            return response
        except Exception as e:
            logger.error(f"Error cancelling hotel booking {booking_id}: {e}")
            raise DuffelAPIError({
                'type': 'client_error',
                'title': 'Hotel booking cancellation failed',
                'detail': str(e)
            })
    
    async def update_booking(self, booking_id: str, data: dict) -> dict:
        """Update a hotel booking by booking_id using PATCH."""
        endpoint = f"/stays/bookings/{booking_id}"
        try:
            # First, get the existing booking to preserve required fields like 'users'
            existing_booking = await self.client.get(f"/stays/bookings/{booking_id}")
            existing_data = existing_booking.get("data", {})
            
            # Merge the update data with existing data, preserving required fields
            updated_data = {**existing_data, **data}
            
            # Ensure users field is preserved
            if "users" not in updated_data and "users" in existing_data:
                updated_data["users"] = existing_data["users"]
            
            # Wrap data in 'data' key as required by Duffel API
            request_body = {"data": updated_data}
            response = await self.client.patch(endpoint, json=request_body)
            return response
        except Exception as e:
            logger.error(f"Error updating hotel booking {booking_id}: {e}")
            raise DuffelAPIError({
                'type': 'client_error',
                'title': 'Hotel booking update failed',
                'detail': str(e)
            })
        
    async def extend_hotel_stay(
        self,
        booking_id: str,
        check_in_date: str,
        check_out_date: str,
        preferred_rate_id: Optional[str] = None,
        customer_confirmation: bool = False,
        payment: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extend a hotel booking's stay dates by cancelling the existing booking and creating a new one.

        Args:
            booking_id: The ID of the booking to extend (e.g., "bok_0000AxNtHvxFHgcXbJQFW4").
            check_in_date: The new check-in date in YYYY-MM-DD format (e.g., "2025-09-14").
            check_out_date: The new check-out date in YYYY-MM-DD format (e.g., "2025-09-16").
            preferred_rate_id: Optional rate ID to use for the new booking (e.g., "rat_0000AxOD48JMHJGKwszWYI").
            customer_confirmation: If False, returns cost_change for confirmation; if True, proceeds.
            payment: Optional payment details (e.g., {"type": "balance"} or card details).

        Returns:
            Dict with booking details, cost change, payment form, or error information.

        Raises:
            DuffelAPIError: For API errors.
        """
        try:
            # Validate inputs
            if not booking_id or not isinstance(booking_id, str):
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Invalid booking ID',
                    'detail': 'Booking ID must be a non-empty string'
                })
            check_in = datetime.strptime(check_in_date, "%Y-%m-%d").date()
            check_out = datetime.strptime(check_out_date, "%Y-%m-%d").date()
            if check_out <= check_in:
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Invalid dates',
                    'detail': 'Check-out date must be after check-in date'
                })

            # Step 1: Get existing booking details
            booking_response = await self.client.get(f"/stays/bookings/{booking_id}")
            booking = booking_response.get("data", {})
            if not booking:
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Booking not found',
                    'detail': f"Booking {booking_id} not found"
                })
            logger.info(f"Fetched booking details for {booking_id}")
            logger.debug(f"Booking data: {booking}")

            # Validate booking status
            if booking.get("status") != "confirmed":
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Invalid booking status',
                    'detail': f"Booking {booking_id} is not in confirmed status: {booking.get('status')}"
                })

            accommodation_id = booking["accommodation"]["id"]
            rooms = booking.get("accommodation", {}).get("rooms", [])
            if not rooms or not isinstance(rooms, list):
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Invalid booking data',
                    'detail': 'No valid room data found in booking.accommodation.rooms'
                })
            if any(not room.get("rates") for room in rooms):
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Invalid booking data',
                    'detail': 'One or more rooms have no rates'
                })

            # Validate room count
            expected_room_count = booking.get("rooms", 0)
            if isinstance(expected_room_count, int) and len(rooms) != expected_room_count:
                logger.warning(f"Room count mismatch: booking.rooms={expected_room_count}, accommodation.rooms={len(rooms)}")

            original_cost = sum(float(room["rates"][0]["total_amount"]) for room in rooms)
            original_currency = rooms[0]["rates"][0]["total_currency"]
            guest_details = booking["guests"]
            email = booking["email"]
            phone_number = booking["phone_number"]
            stay_special_requests = booking.get("stay_special_requests", "")
            original_nights = (datetime.fromisoformat(booking["check_out_date"].replace("Z", "+00:00")) -
                            datetime.fromisoformat(booking["check_in_date"].replace("Z", "+00:00"))).days
            
            logger.info(f"Original booking cost: {original_cost} {original_currency} for {original_nights} nights")

            # Calculate adults/children based on born_on
            adults = 0
            children = 0
            child_ages = []
            today = date.today()
            for g in guest_details:
                if "born_on" in g:
                    born_date = date.fromisoformat(g["born_on"])
                    age = (today - born_date).days // 365
                    if age < 18:
                        children += 1
                        child_ages.append(age)
                    else:
                        adults += 1
                else:
                    logger.warning(f"Guest {g.get('given_name', '')} {g.get('family_name', '')} has no 'born_on' field; defaulting to adult")
                    adults += 1
            if adults < 1:
                adults = 1

            # Step 2: Check original cancellation timeline
            original_cancellation_timeline = rooms[0]["rates"][0].get("cancellation_timeline", [])
            cancel_deadline = None
            for timeline in original_cancellation_timeline:
                if timeline.get("refund_amount") == rooms[0]["rates"][0]["total_amount"]:
                    cancel_deadline = datetime.fromisoformat(timeline["before"].replace("Z", "+00:00"))
                    break
            current_time = datetime.now(tz=cancel_deadline.tzinfo if cancel_deadline else timezone.utc)
            if cancel_deadline and current_time > cancel_deadline:
                raise GraphInterrupt(
                    f"Cancellation deadline has passed for your original booking ({cancel_deadline}). "
                    f"Do you still want to proceed with the extension (this may incur extra charges or be non-refundable)?"
                )
            elif not cancel_deadline:
                logger.warning("No full refund cancellation timeline found; proceeding with potential charges")

            # Step 3: Search for availability
            guests = Guest(adults=adults, children=children, ages=child_ages)
            address = booking["accommodation"]["location"]["address"]
            city = address.get("city_name") or address.get("city")
            if not city:
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Invalid booking data',
                    'detail': 'No city found in accommodation address'
                })
            logger.info(f"Searching for hotels in {city} from {check_in} to {check_out} for {guests.adults} adults and {guests.children} children")
            
            search_response = await self.search_hotels(
                HotelSearchRequest(
                    location=city,
                    dates=DateRange(check_in=check_in, check_out=check_out),
                    guests=guests,
                    limit=1,
                    accommodation_ids=[accommodation_id]
                )
            )
            search_result = search_response.data
            if not search_result:
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'No availability',
                    'detail': 'No availability found for the requested dates in this hotel'
                })
            search_result_id = search_result[0].id

            # Step 4: Fetch detailed rates
            logger.info(f"Fetching rates for search result {search_result_id}")
            rates_response = await self.fetch_all_rates(search_result_id)
            rates = rates_response.get("data", {}).get("accommodation", {}).get("rooms", [])
            if not rates:
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'No rates available',
                    'detail': 'No rates available for the requested dates'
                })

            # Step 5: Select a matching rate
            logger.info(f"Selecting a suitable rate for the new dates")
            selected_rate = None
            rate_id_to_use = preferred_rate_id or rooms[0]["rates"][0].get("id")
            if rate_id_to_use:
                for room in rates:
                    for rate in room["rates"]:
                        if rate["id"] == rate_id_to_use:
                            selected_rate = rate
                            break
                    if selected_rate:
                        break

            if not selected_rate:
                for room in rates:
                    for rate in room["rates"]:
                        if (rate["board_type"] == "room_only" and
                            rate["payment_type"] == "pay_now" and
                            "balance" in rate["available_payment_methods"]):
                            selected_rate = rate
                            break
                    if selected_rate:
                        break
            if not selected_rate:
                logger.error(f"No suitable rate found. Available rates: {rates}")
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'No suitable rate',
                    'detail': 'Could not find a suitable rate for the new dates'
                })

            # Step 6: Calculate cost change
            logger.info(f"Selected rate {selected_rate['id']} for new booking")
            new_cost = float(selected_rate["total_amount"])  # Single room assumption
            new_currency = selected_rate["total_currency"]
            new_nights = (check_out - check_in).days
            cost_change = {
                "original_cost": original_cost,
                "original_currency": original_currency,
                "original_nights": original_nights,
                "original_per_night": original_cost / original_nights if original_nights else 0,
                "new_cost": new_cost,
                "new_currency": new_currency,
                "new_nights": new_nights,
                "new_per_night": new_cost / new_nights if new_nights else 0,
                "rate_id": selected_rate["id"],
                "room_name": next(room["name"] for room in rates if any(r["id"] == selected_rate["id"] for r in room["rates"])),
                "board_type": selected_rate["board_type"],
                "cancellation_timeline": selected_rate["cancellation_timeline"]
            }

            # Step 7: Handle confirmation
            if not customer_confirmation:
                logger.info("Returning cost change for confirmation")
                return {
                    "message": (
                        f"Your new stay will cost {cost_change['new_cost']} {cost_change['new_currency']} "
                        f"for {cost_change['new_nights']} nights (was {cost_change['original_cost']} {cost_change['original_currency']} "
                        f"for {cost_change['original_nights']} nights).\n"
                        "Do you want to proceed?"
                    ),
                    "rates": [
                        {
                            "rate_id": r["id"],
                            "room_name": room["name"],
                            "total_amount": r["total_amount"],
                            "board_type": r["board_type"]
                        }
                        for room in rates for r in room["rates"]
                    ]
                }

            # Step 8: Create quote
            logger.info(f"Creating quote for rate {selected_rate['id']}")
            quote_response = await self.create_quote(selected_rate["id"])
            quote_id = quote_response.get("data", {}).get("id")
            if not quote_id:
                logger.error(f"Quote creation failed. Response: {quote_response}")
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Quote creation failed',
                    'detail': 'Could not create quote for the selected rate'
                })

            # Step 9: Handle payment
            if payment is None:
                amount = quote_response.get("data", {}).get("total_amount", "0.00")
                currency = quote_response.get("data", {}).get("total_currency", "USD")
                return {
                    "ui_type": "paymentForm",
                    "data": {
                        "title": "Complete Payment for Extended Stay",
                        "amount": amount,
                        "currency": currency,
                        "fields": [
                            {"name": "cardNumber", "label": "Card Number", "type": "text", "required": True},
                            {"name": "expiryDate", "label": "Expiry Date", "type": "text", "required": True},
                            {"name": "cvc", "label": "CVC", "type": "text", "required": True},
                            {"name": "name", "label": "Cardholder Name", "type": "text", "required": True}
                        ]
                    },
                    "metadata": {
                        "guests": guest_details
                    }
                }
            elif payment.get("type") not in ["balance", "card"]:
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Invalid payment',
                    'detail': 'Payment type must be "balance" or "card"'
                })
            logger.info(f"Processing payment: {payment}")

            # Step 10: Cancel the original booking
            logger.info(f"Attempting to cancel booking {booking_id}")
            cancel_response = await self.cancel_booking(booking_id)
            if "error" in cancel_response:
                logger.error(f"Cancellation failed. API response: {cancel_response}")
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Cancellation failed',
                    'detail': f"Could not cancel the original booking: {cancel_response.get('error', {}).get('message', 'Unknown error')}"
                })
            if cancel_response.get("data", {}).get("status") != "cancelled" or not cancel_response.get("data", {}).get("cancelled_at"):
                logger.error(f"Cancellation failed. API response: {cancel_response}")
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Cancellation failed',
                    'detail': 'Could not confirm cancellation of the original booking'
                })
            logger.info(f"Successfully canceled booking {booking_id}")

            # Step 11: Create the new booking
            logger.info(f"Creating new booking with quote {quote_id}")
            booking_body = {
                "quote_id": quote_id,
                "guests": guest_details,
                "email": email,
                "phone_number": phone_number,
                "stay_special_requests": stay_special_requests
                # "payment": payment
            }
            if booking.get("metadata"):
                booking_body["metadata"] = booking["metadata"]
            if booking.get("loyalty_programme_account_number"):
                booking_body["loyalty_programme_account_number"] = booking["loyalty_programme_account_number"]
            new_booking_response = await self.create_booking(**booking_body)
            if "error" in new_booking_response:
                logger.error(f"New booking creation failed. API response: {new_booking_response}")
                raise DuffelAPIError({
                    'type': 'client_error',
                    'title': 'Booking creation failed',
                    'detail': f"Could not create new booking: {new_booking_response.get('error', {}).get('message', 'Unknown error')}"
                })
            new_booking = new_booking_response.get("data", {})

            return {
                "status": "success",
                "new_booking_id": new_booking.get("id"),
                "cost_change": cost_change,
                "payment_provided": True,
                "_payment_mode": "test"
            }

        except DuffelAPIError as e:
            logger.error(f"Duffel API error extending booking {booking_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error extending booking {booking_id}: {e}")
            raise DuffelAPIError({
                'type': 'client_error',
                'title': 'Hotel stay extension failed',
                'detail': str(e)
            })
    
    def _parse_hotels_response(self, response_data: Dict[str, Any]) -> List[Hotel]:
        """Parse Duffel API response into Hotel models.
        
        Args:
            response_data: Raw API response data
            
        Returns:
            List of parsed Hotel objects
        """
        hotels = []
        
        # Duffel returns search results in data.results array
        results = response_data.get("data", {}).get("results", [])
        
        for result_data in results:
            try:
                hotel = self._parse_hotel_from_search_result(result_data)
                hotels.append(hotel)
            except Exception as e:
                # Log parsing error but continue with other hotels
                logger.warning(f"Failed to parse hotel data: {e}")
                continue
        
        return hotels
    
    def _parse_hotel_from_search_result(self, result_data: Dict[str, Any]) -> Hotel:
        """Parse a single hotel from search result.
        
        Args:
            result_data: Raw search result data from API
            
        Returns:
            Parsed Hotel object
        """
        # Duffel search results have accommodation data nested
        accommodation = result_data.get("accommodation", {})
        
        # Parse basic hotel information
        name = accommodation.get("name", "")
        description = accommodation.get("description")
        
        # Parse location
        address = None
        coordinates = None
        location_data = accommodation.get("location", {})
        
        if "address" in location_data:
            address_data = location_data["address"]
            address = Address(
                line_one=address_data.get("line_one"),
                line_two=address_data.get("line_two"),
                city=address_data.get("city_name"),
                region=address_data.get("region"),
                postal_code=address_data.get("postal_code"),
                country_code=address_data.get("country_code"),
            )
        
        if "geographic_coordinates" in location_data:
            coord_data = location_data["geographic_coordinates"]
            coordinates = Coordinates(
                latitude=coord_data["latitude"],
                longitude=coord_data["longitude"]
            )
        
        # Parse ratings
        star_rating = accommodation.get("rating")
        guest_rating = accommodation.get("review_score")
        
        # Parse amenities
        amenities = []
        for amenity_data in accommodation.get("amenities", []):
            amenity = Amenity(
                id=amenity_data.get("type", ""),
                name=amenity_data.get("description", amenity_data.get("type", "")),
                category=amenity_data.get("type")
            )
            amenities.append(amenity)
        
        # Parse images
        images = []
        for photo in accommodation.get("photos", []):
            if photo.get("url"):
                images.append(photo["url"])
        
        # Parse room information from search result
        rooms = []
        
        # Get cheapest rate info from search result
        cheapest_rate_amount = result_data.get("cheapest_rate_total_amount")
        cheapest_rate_currency = result_data.get("cheapest_rate_currency")
        hotel_id = result_data.get("id", "")
        
        if cheapest_rate_amount and cheapest_rate_currency:
            # Create a simplified room with the cheapest rate
            rate = Rate(
                total_amount=Money(
                    amount=cheapest_rate_amount,
                    currency=cheapest_rate_currency
                )
            )
            
            # Create a basic room entry
            room = Room(
                id=f"{hotel_id}_basic",
                name="Standard Room",
                rate=rate
            )
            rooms.append(room)
        
        # Also parse detailed rooms if available
        for room_data in accommodation.get("rooms", []):
            room = self._parse_room(room_data)
            rooms.append(room)
        
        return Hotel(
            id=hotel_id,
            name=name,
            description=description,
            address=address,
            coordinates=coordinates,
            star_rating=star_rating,
            guest_rating=guest_rating,
            amenities=amenities,
            images=images,
            rooms=rooms or [Room(id=f"{hotel_id}_unknown", name="Room", rate=Rate(total_amount=Money(amount="0", currency="USD")))]
        )
    
    def _parse_room(self, room_data: Dict[str, Any]) -> Room:
        """Parse a room from API response.
        
        Args:
            room_data: Raw room data from API
            
        Returns:
            Parsed Room object
        """
        # Parse basic room information
        room_id = room_data.get("id", "")
        name = room_data.get("name", "")
        description = room_data.get("description")
        
        # Parse bed information
        beds = room_data.get("beds", [])
        bed_count = sum(bed.get("count", 1) for bed in beds)
        bed_type = beds[0].get("type") if beds else None
        
        # Parse room amenities
        amenities = []
        for amenity_data in room_data.get("amenities", []):
            amenity = Amenity(
                id=amenity_data.get("type", ""),
                name=amenity_data.get("description", amenity_data.get("type", "")),
                category=amenity_data.get("type")
            )
            amenities.append(amenity)
        
        # Parse rates - use the first available rate
        rates = room_data.get("rates", [])
        if rates:
            rate_data = rates[0]  # Take first rate
            rate = self._parse_rate(rate_data)
        else:
            # Fallback rate
            rate = Rate(total_amount=Money(amount="0", currency="USD"))
        
        return Room(
            id=room_id,
            name=name,
            description=description,
            bed_count=bed_count,
            bed_type=bed_type,
            amenities=amenities,
            rate=rate
        )
    
    def _parse_rate(self, rate_data: Dict[str, Any]) -> Rate:
        """Parse rate information from API response.
        
        Args:
            rate_data: Raw rate data from API
            
        Returns:
            Parsed Rate object
        """
        # Parse total amount
        total_amount = Money(
            amount=rate_data.get("total_amount", "0"),
            currency=rate_data.get("total_currency", "USD")
        )
        
        # Parse optional amounts
        base_amount = None
        if rate_data.get("base_amount"):
            base_amount = Money(
                amount=rate_data.get("base_amount", "0"),
                currency=rate_data.get("base_currency", "USD")
            )
        
        tax_amount = None
        if rate_data.get("tax_amount"):
            tax_amount = Money(
                amount=rate_data.get("tax_amount", "0"),
                currency=rate_data.get("tax_currency", "USD")
            )
        
        return Rate(
            total_amount=total_amount,
            base_amount=base_amount,
            tax_amount=tax_amount,
            refundable=rate_data.get("refundable")
        )

async def get_geocode(location: str) -> Optional[Dict[str, float]]:
    """
    Get coordinates for a location string using geopy.

    Args:
        location: Location name (city, etc.)

    Returns:
        Dictionary with latitude and longitude, 
        or None if not found
    """
    try:
        logger.info(f"Geocoding {location}")
        loc = await asyncio.to_thread(geolocator.geocode, location)
        logger.info(f"Geocoding result: {loc}")
        if loc:
            return {"latitude": loc.latitude, "longitude": loc.longitude}
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
    return None

# Convenience function for direct hotel search
async def search_hotels(
    location: str,
    check_in: date,
    check_out: date,
    adults: int = 1,
    children: int = 0,
    limit: int = 10
) -> HotelSearchResponse:
    """Convenience function for hotel search.
    
    Args:
        location: Location to search (city name, etc.)
        check_in: Check-in date
        check_out: Check-out date  
        adults: Number of adult guests
        children: Number of child guests
        limit: Maximum number of results
        
    Returns:
        Hotel search response
    """
    from ..client import get_client
    
    client = get_client()
    stays_endpoint = StaysEndpoint(client)
    
    request = HotelSearchRequest(
        location=location,
        dates=DateRange(check_in=check_in, check_out=check_out),
        guests=Guest(adults=adults, children=children),
        limit=limit
    )
    
    return await stays_endpoint.search_hotels(request) 

async def fetch_hotel_rates(search_result_id: str) -> Dict[str, Any]:
    """Convenience function to fetch all rates for a hotel.
    
    Args:
        search_result_id: The search result ID (srr_...)
        
    Returns:
        API response with detailed room/rate information
    """
    from ..client import get_client
    
    client = get_client()
    stays_endpoint = StaysEndpoint(client)
    
    return await stays_endpoint.fetch_all_rates(search_result_id)

async def create_quote(rate_id: str) -> dict:
    """Convenience function to create a quote for a rate."""
    from ..client import get_client

    client = get_client()
    stays_endpoint = StaysEndpoint(client)
    return await stays_endpoint.create_quote(rate_id)

async def create_booking(
    quote_id: str,
    guests: list,
    email: str,
    stay_special_requests: str = "",
    phone_number: str = "",
    payment: dict = None
) -> dict:
    """Convenience function to create a booking from a quote."""
    from ..client import get_client

    client = get_client()
    stays_endpoint = StaysEndpoint(client)
    return await stays_endpoint.create_booking(
        quote_id, guests, email, stay_special_requests, phone_number,payment
    )

async def cancel_hotel_booking(booking_id: str) -> dict:
    """Convenience function to cancel a hotel booking by booking_id."""
    from ..client import get_client
    client = get_client()
    stays_endpoint = StaysEndpoint(client)
    return await stays_endpoint.cancel_booking(booking_id)

async def update_hotel_booking(booking_id: str, data: dict) -> dict:
    """Convenience function to update a hotel booking by booking_id."""
    from ..client import get_client
    client = get_client()
    stays_endpoint = StaysEndpoint(client)
    return await stays_endpoint.update_booking(booking_id, data)

async def extend_hotel_stay(
    booking_id: str,
    check_in_date: str,
    check_out_date: str,
    preferred_rate_id: Optional[str] = None,
    customer_confirmation: bool = False,
    payment: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Convenience function to extend a hotel booking by booking_id."""
    from ..client import get_client
    client = get_client()
    stays_endpoint = StaysEndpoint(client)
    return await stays_endpoint.extend_hotel_stay(
        booking_id, check_in_date, check_out_date, preferred_rate_id, customer_confirmation, payment
    )
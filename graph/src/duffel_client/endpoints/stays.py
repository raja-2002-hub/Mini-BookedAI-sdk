"""
Duffel Stays API endpoint for hotel search functionality.
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import date

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
        if payment:            
            data["data"]["payment"] = payment
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
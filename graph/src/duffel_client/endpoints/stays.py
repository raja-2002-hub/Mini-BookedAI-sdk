"""
Duffel Stays API endpoint for hotel search functionality.
"""
from typing import List, Dict, Any, Optional
from datetime import date
import asyncio

from ..client import DuffelClient, DuffelAPIError
from ..models.stays import HotelSearchRequest, HotelSearchResponse, Hotel, Room, Rate, Amenity
from ..models.common import Money, Address, Coordinates, DateRange, Guest


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
            # Convert search request to Duffel API parameters
            params = request.to_duffel_params()
            
            # Make API request
            response_data = await self.client.get("/v2/stays/search", params=params)
            
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
            raise DuffelAPIError(
                error=type('DuffelError', (), {
                    'type': 'client_error',
                    'title': 'Hotel search failed',
                    'detail': str(e)
                })()
            )
    
    def _parse_hotels_response(self, response_data: Dict[str, Any]) -> List[Hotel]:
        """Parse Duffel API response into Hotel models.
        
        Args:
            response_data: Raw API response data
            
        Returns:
            List of parsed Hotel objects
        """
        hotels = []
        
        # Duffel returns data as a list of accommodation objects
        for hotel_data in response_data.get("data", []):
            try:
                hotel = self._parse_hotel(hotel_data)
                hotels.append(hotel)
            except Exception as e:
                # Log parsing error but continue with other hotels
                print(f"Warning: Failed to parse hotel data: {e}")
                continue
        
        return hotels
    
    def _parse_hotel(self, hotel_data: Dict[str, Any]) -> Hotel:
        """Parse a single hotel from API response.
        
        Args:
            hotel_data: Raw hotel data from API
            
        Returns:
            Parsed Hotel object
        """
        # Parse basic hotel information
        hotel_id = hotel_data.get("id", "")
        name = hotel_data.get("name", "")
        description = hotel_data.get("description")
        
        # Parse address
        address = None
        if "address" in hotel_data and hotel_data["address"]:
            address_data = hotel_data["address"]
            address = Address(
                line_one=address_data.get("line_one"),
                line_two=address_data.get("line_two"),
                city=address_data.get("city"),
                region=address_data.get("region"),
                postal_code=address_data.get("postal_code"),
                country_code=address_data.get("country_code"),
            )
        
        # Parse coordinates
        coordinates = None
        if "coordinates" in hotel_data and hotel_data["coordinates"]:
            coord_data = hotel_data["coordinates"]
            coordinates = Coordinates(
                latitude=coord_data["latitude"],
                longitude=coord_data["longitude"]
            )
        
        # Parse ratings
        star_rating = hotel_data.get("star_rating")
        guest_rating = hotel_data.get("guest_rating")
        review_count = hotel_data.get("review_count")
        
        # Parse amenities
        amenities = []
        for amenity_data in hotel_data.get("amenities", []):
            amenity = Amenity(
                id=amenity_data.get("id", ""),
                name=amenity_data.get("name", ""),
                category=amenity_data.get("category")
            )
            amenities.append(amenity)
        
        # Parse images
        images = hotel_data.get("images", [])
        
        # Parse rooms and rates
        rooms = []
        for room_data in hotel_data.get("rooms", []):
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
            review_count=review_count,
            amenities=amenities,
            images=images,
            rooms=rooms
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
        
        bed_count = room_data.get("bed_count")
        bed_type = room_data.get("bed_type")
        max_occupancy = room_data.get("max_occupancy")
        size_sqm = room_data.get("size_sqm")
        
        # Parse room amenities
        amenities = []
        for amenity_data in room_data.get("amenities", []):
            amenity = Amenity(
                id=amenity_data.get("id", ""),
                name=amenity_data.get("name", ""),
                category=amenity_data.get("category")
            )
            amenities.append(amenity)
        
        # Parse rate information
        rate = self._parse_rate(room_data.get("rate", {}))
        
        return Room(
            id=room_id,
            name=name,
            description=description,
            bed_count=bed_count,
            bed_type=bed_type,
            max_occupancy=max_occupancy,
            size_sqm=size_sqm,
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
        total_amount_data = rate_data.get("total_amount", {})
        total_amount = Money(
            amount=total_amount_data.get("amount", "0"),
            currency=total_amount_data.get("currency", "USD")
        )
        
        # Parse optional amounts
        base_amount = None
        if "base_amount" in rate_data and rate_data["base_amount"]:
            base_data = rate_data["base_amount"]
            base_amount = Money(
                amount=base_data.get("amount", "0"),
                currency=base_data.get("currency", "USD")
            )
        
        tax_amount = None
        if "tax_amount" in rate_data and rate_data["tax_amount"]:
            tax_data = rate_data["tax_amount"]
            tax_amount = Money(
                amount=tax_data.get("amount", "0"),
                currency=tax_data.get("currency", "USD")
            )
        
        # Parse fees
        fees = []
        for fee_data in rate_data.get("fees", []):
            fee = Money(
                amount=fee_data.get("amount", "0"),
                currency=fee_data.get("currency", "USD")
            )
            fees.append(fee)
        
        return Rate(
            total_amount=total_amount,
            base_amount=base_amount,
            tax_amount=tax_amount,
            fees=fees if fees else None,
            cancellation_policy=rate_data.get("cancellation_policy"),
            refundable=rate_data.get("refundable")
        )


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
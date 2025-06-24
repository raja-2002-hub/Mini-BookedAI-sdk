"""
Pydantic models for Duffel Stays API (hotels/accommodations).
"""
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
import asyncio
import logging

from .common import Money, Location, Address, Coordinates, DateRange, Guest, DuffelResponse

logger = logging.getLogger(__name__)

class Amenity(BaseModel):
    """Hotel or room amenity."""
    id: str = Field(..., description="Amenity ID")
    name: str = Field(..., description="Amenity name")
    category: Optional[str] = Field(None, description="Amenity category")


class Rate(BaseModel):
    """Hotel room rate information."""
    total_amount: Money = Field(..., description="Total amount for the stay")
    base_amount: Optional[Money] = Field(None, description="Base amount before taxes/fees")
    tax_amount: Optional[Money] = Field(None, description="Tax amount")
    fees: Optional[List[Money]] = Field(None, description="Additional fees")
    
    cancellation_policy: Optional[str] = Field(None, description="Cancellation policy")
    refundable: Optional[bool] = Field(None, description="Whether the rate is refundable")
    
    def __str__(self) -> str:
        return f"{self.total_amount}"


class Room(BaseModel):
    """Hotel room information."""
    id: str = Field(..., description="Room ID")
    name: str = Field(..., description="Room name/type")
    description: Optional[str] = Field(None, description="Room description")
    
    bed_count: Optional[int] = Field(None, description="Number of beds")
    bed_type: Optional[str] = Field(None, description="Type of beds")
    max_occupancy: Optional[int] = Field(None, description="Maximum occupancy")
    
    size_sqm: Optional[float] = Field(None, description="Room size in square meters")
    amenities: Optional[List[Amenity]] = Field(None, description="Room amenities")
    
    rate: Rate = Field(..., description="Rate information for this room")
    
    def __str__(self) -> str:
        return f"{self.name} - {self.rate}"


class Hotel(BaseModel):
    """Hotel information."""
    id: str = Field(..., description="Hotel ID")
    name: str = Field(..., description="Hotel name")
    description: Optional[str] = Field(None, description="Hotel description")
    
    address: Optional[Address] = Field(None, description="Hotel address")
    coordinates: Optional[Coordinates] = Field(None, description="Hotel coordinates")
    
    star_rating: Optional[float] = Field(None, description="Hotel star rating")
    guest_rating: Optional[float] = Field(None, description="Guest rating")
    review_count: Optional[int] = Field(None, description="Number of reviews")
    
    amenities: Optional[List[Amenity]] = Field(None, description="Hotel amenities")
    images: Optional[List[str]] = Field(None, description="Hotel image URLs")
    
    rooms: List[Room] = Field(..., description="Available rooms")
    
    @property
    def min_rate(self) -> Optional[Rate]:
        """Get the minimum rate from available rooms."""
        if not self.rooms:
            return None
        return min(self.rooms, key=lambda r: r.rate.total_amount.decimal_amount).rate
    
    def __str__(self) -> str:
        rating = f" ({self.star_rating}★)" if self.star_rating else ""
        location = f" - {self.address.city}" if self.address and self.address.city else ""
        return f"{self.name}{rating}{location}"


class HotelSearchRequest(BaseModel):
    """Request model for hotel search."""
    location: str = Field(..., description="Location to search (city name, coordinates, etc.)")
    dates: DateRange = Field(..., description="Check-in and check-out dates")
    guests: Guest = Field(default_factory=Guest, description="Guest information")
    
    # Optional filters
    max_price: Optional[Money] = Field(None, description="Maximum price per night")
    min_star_rating: Optional[float] = Field(None, description="Minimum star rating")
    amenities: Optional[List[str]] = Field(None, description="Required amenities")
    
    # Search parameters
    limit: int = Field(10, ge=1, le=50, description="Maximum number of results")
    sort_by: str = Field("price", description="Sort criteria (price, rating, distance)")
    
    async def to_duffel_request(self) -> Dict[str, Any]:
        """Convert to Duffel API POST request body."""
        from ..endpoints.stays import get_coordinates_for_location
        
        # Get coordinates for the location
        coordinates = await get_coordinates_for_location(self.location)
        logger.info(f"Coordinates: {coordinates}")
        if not coordinates:
            raise ValueError(f"Could not find coordinates for location: {self.location}")
        
        # Build guests array
        guests = []
        for _ in range(self.guests.adults):
            guests.append({"type": "adult"})
        for _ in range(self.guests.children):
            guests.append({"type": "child"})
        
        # Build the request body according to Duffel API schema
        request_body = {
            "data": {
                "location": {
                    "radius": 5,  # 5km radius
                    "geographic_coordinates": {
                        "latitude": coordinates["latitude"],
                        "longitude": coordinates["longitude"]
                    }
                },
                "check_in_date": self.dates.check_in.isoformat(),
                "check_out_date": self.dates.check_out.isoformat(),
                "guests": guests,
                "rooms": 1,  # For now, assume 1 room
                "mobile": False,
                "free_cancellation_only": False
            }
        }
        
        return request_body


class HotelSearchResponse(DuffelResponse):
    """Response model for hotel search."""
    data: List[Hotel] = Field(..., description="List of hotels")
    
    @property
    def hotels(self) -> List[Hotel]:
        """Get the list of hotels."""
        return self.data
    
    @property
    def count(self) -> int:
        """Get the number of hotels returned."""
        return len(self.data)
    
    def format_for_display(self, max_results: int = 5) -> str:
        """Format the search results for display in chat."""
        if not self.hotels:
            return "No hotels found for your search criteria."
        
        results = []
        for i, hotel in enumerate(self.hotels[:max_results], 1):
            min_rate = hotel.min_rate
            price_str = f"from {min_rate}" if min_rate else "Price unavailable"
            
            location_str = ""
            if hotel.address and hotel.address.city:
                location_str = f" in {hotel.address.city}"
            
            rating_str = ""
            if hotel.star_rating:
                rating_str = f" ({hotel.star_rating}★)"
            
            results.append(f"{i}. {hotel.name}{rating_str}{location_str} - {price_str}")
        
        total_str = f" (showing {max_results} of {self.count})" if self.count > max_results else ""
        return f"Found {self.count} hotels{total_str}:\n\n" + "\n".join(results)


class StayBookingRequest(BaseModel):
    """Request model for booking a stay (future implementation)."""
    hotel_id: str = Field(..., description="Hotel ID to book")
    room_id: str = Field(..., description="Room ID to book")
    dates: DateRange = Field(..., description="Check-in and check-out dates")
    guests: Guest = Field(..., description="Guest information")
    
    # Guest details would be added here for actual booking
    # For now, this is a placeholder for future implementation 
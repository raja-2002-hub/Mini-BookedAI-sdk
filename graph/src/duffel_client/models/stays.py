"""
Pydantic models for Duffel Stays API (hotels/accommodations).
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import logging

from .common import Money, Address, Coordinates, DateRange, Guest, DuffelResponse

logger = logging.getLogger(__name__)

class Amenity(BaseModel):
    """Hotel or room amenity."""
    id: str = Field(..., description="Amenity ID")
    name: str = Field(..., description="Amenity name")
    category: Optional[str] = Field(None, description="Amenity category")


class LoyaltyProgramme(BaseModel):
    """Accommodation Loyalty Programme information."""
    reference: str = Field(..., description="The reference of this loyalty programme.")
    name: str = Field(..., description="The name of the loyalty programme.")
    logo_url_svg: Optional[str] = Field(None, description="The URL of the loyalty programme's SVG logo.")
    logo_url_png_small: Optional[str] = Field(None, description="The URL of the loyalty programme's PNG logo.")


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
    loyalty_programmes: Optional[List[LoyaltyProgramme]] = Field(None, description="Supported loyalty programmes")
    
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


class AccommodationReview(BaseModel):
    text: str
    score: float
    reviewer_name: str
    created_at: str


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
        from ..endpoints.stays import get_geocode
        
        # Get coordinates for the location
        coordinates = await get_geocode(self.location)
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
    
    def format_for_json(self, max_results: int = 5) -> Dict[str, Any]:
        """Format the search results as JSON data for UI components."""
        if not self.hotels:
            return {
                "hotels": [],
                "summary": "No hotels found for your search criteria.",
                "count": 0
            }
        
        hotel_data = []
        for hotel in self.hotels[:max_results]:
            # Get location string
            location_str = ""
            if hotel.address and hotel.address.city:
                location_str = hotel.address.city
            
            # Get price string
            price_str = str(hotel.min_rate.total_amount) if hotel.min_rate else "Price unavailable"
            
            # Get amenities
            amenities = [amenity.name for amenity in hotel.amenities[:5]] if hotel.amenities else []
            
            # Get first image
            image = hotel.images[0] if hotel.images else ""
            
            # Get loyalty programmes
            loyalty_programmes = [lp.dict() for lp in hotel.loyalty_programmes] if hotel.loyalty_programmes else []
            
            # Try to extract accommodation_id (acc_...) from the first room's id or from a nested property
            accommodation_id = None
            if hasattr(hotel, 'rooms') and hotel.rooms:
                for room in hotel.rooms:
                    if hasattr(room, 'id') and isinstance(room.id, str) and room.id.startswith('acc_'):
                        accommodation_id = room.id
                        break
            # Fallback: try to extract acc_... from hotel.id if it matches
            if not accommodation_id and isinstance(hotel.id, str) and hotel.id.startswith('acc_'):
                accommodation_id = hotel.id
            hotel_data.append({
                "name": hotel.name,
                "rating": hotel.star_rating or 0,
                "price": price_str,
                "location": location_str,
                "image": image,
                "amenities": amenities,
                "description": hotel.description[:100]+"..." if hotel.description else "",
                "id": hotel.id,
                "accommodation_id": accommodation_id,
                "loyalty_programmes": loyalty_programmes
            })
        
        return {
            "hotels": hotel_data,
            "summary": f"Found {self.count} hotels in your search",
            "count": self.count,
            "showing": min(max_results, self.count)
        }


class StayBookingRequest(BaseModel):
    """Request model for booking a stay (future implementation)."""
    hotel_id: str = Field(..., description="Hotel ID to book")
    room_id: str = Field(..., description="Room ID to book")
    dates: DateRange = Field(..., description="Check-in and check-out dates")
    guests: Guest = Field(..., description="Guest information")
    
    # Guest details would be added here for actual booking
    # For now, this is a placeholder for future implementation 
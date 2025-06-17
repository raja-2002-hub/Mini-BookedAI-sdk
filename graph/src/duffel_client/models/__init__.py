"""
Pydantic models for Duffel API data structures.
"""

from .common import *
from .stays import *

__all__ = [
    # Common models
    "Location",
    "Money",
    "Address",
    "Coordinates",
    
    # Stays models
    "HotelSearchRequest",
    "HotelSearchResponse",
    "Hotel",
    "Room",
    "Rate",
    "Amenity",
] 
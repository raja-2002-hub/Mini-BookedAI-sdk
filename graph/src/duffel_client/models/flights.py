"""
Flight models for Duffel API integration.
"""
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import date, datetime
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FlightLoyaltyProgramme(BaseModel):
    """Flight Loyalty Programme information."""
    reference: str = Field(..., description="The reference of this loyalty programme.")
    name: str = Field(..., description="The name of the loyalty programme.")
    logo_url_svg: Optional[str] = Field(None, description="The URL of the loyalty programme's SVG logo.")
    logo_url_png_small: Optional[str] = Field(None, description="The URL of the loyalty programme's PNG logo (small).")


class FlightSegment(BaseModel):
    """Represents a flight segment."""
    origin: str = Field(..., description="Origin airport code")
    destination: str = Field(..., description="Destination airport code")
    departure_time: str = Field(..., description="Departure time (ISO format)")
    arrival_time: str = Field(..., description="Arrival time (ISO format)")
    duration: str = Field(..., description="Flight duration")
    airline: str = Field(..., description="Airline name")
    flight_number: str = Field(..., description="Flight number")
    aircraft: Optional[str] = Field(None, description="Aircraft type")
    cabin_class: str = Field(..., description="Cabin class")


class FlightOffer(BaseModel):
    """Represents a flight offer."""
    id: str = Field(..., description="Offer ID")
    price: str = Field(..., description="Price amount")
    currency: str = Field(..., description="Currency code")
    segments: List[FlightSegment] = Field(..., description="Flight segments")
    total_duration: str = Field(..., description="Total journey duration")
    stops: int = Field(..., description="Number of stops")
    cabin_class: str = Field(..., description="Cabin class")
    refundable: bool = Field(False, description="Whether the ticket is refundable")
    baggage_included: bool = Field(False, description="Whether baggage is included")
    supported_loyalty_programmes: Optional[List[str]] = Field(None, description="List of supported loyalty programme references")


class FlightSearchRequest(BaseModel):
    """Request model for flight search."""
    slices: List[Dict[str, Any]] = Field(..., description="List of slices (segments) for the itinerary")
    passengers: int = Field(1, ge=1, le=9, description="Number of passengers")
    cabin_class: str = Field("economy", description="Cabin class (economy, premium_economy, business, first)")

    def to_duffel_request(self) -> Dict[str, Any]:
        """Convert to Duffel API POST request body."""
        passengers_list = [{"type": "adult"} for _ in range(self.passengers)]
        request_body = {
            "data": {
                "slices": self.slices,
                "passengers": passengers_list,
                "cabin_class": self.cabin_class
            }
        }
        return request_body


class FlightSearchResponse(BaseModel):
    """Response model for flight search."""
    offers: List[Union[FlightOffer, Dict[str, Any]]] = Field(..., description="Flight offers")
    total_results: int = Field(..., description="Total number of results")
    search_id: str = Field(..., description="Search request ID")
    

    def format_for_json(self, max_results: int = 10) -> Dict[str, Any]:
        limited_offers = self.offers[:max_results]
        flights = []
        for offer in limited_offers:
            if isinstance(offer, dict):
                flight_data = {
                    "offer_id": offer.get("offer_id", "Unknown"),
                    "airline": offer.get("airline", "Unknown"),
                    "price": offer.get("price", "Unknown"),
                    "slices": offer.get("slices", []),
                    "instant_payment": offer.get("instant_payment", "N/A"),
                    "loyalty": offer.get("loyalty", "N/A"),
                    "total_journey_duration": offer.get("total_journey_duration", "N/A"),
                    "layovers": offer.get("layovers", []),
                    "passenger_ids": offer.get("passenger_ids", []),
                }
            else:
                # Handle FlightOffer objects
                flight_data = {
                    "offer_id": offer.id,
                    "airline": "Unknown",  # Would need to extract from segments
                    "price": f"{offer.price} {offer.currency}",
                    "slices": [],  # Would need to convert segments to slices format
                    "instant_payment": "N/A",
                    "loyalty": ", ".join(offer.supported_loyalty_programmes) if offer.supported_loyalty_programmes else "N/A",
                    "total_journey_duration": offer.total_duration,
                    "layovers": [],
                    "passenger_ids": [],
                }
            flights.append(flight_data)
        
        return {
            "flights": flights,
            "total_results": self.total_results,
            "search_id": self.search_id
        }

# --- Order Change Models ---
class OrderChangeRequest(BaseModel):
    """Model for creating an order change request."""
    order_id: str = Field(..., description="The ID of the order to change")
    slices: Optional[list] = Field(None, description="List of slices to change (Duffel API format)")
    type: Optional[str] = Field(None, description="Type of change (e.g., 'date_change')")
    # Add more fields as needed for Duffel API

class OrderChangeRequestResponse(BaseModel):
    """Response model for an order change request."""
    id: str = Field(..., description="Order change request ID")
    order_id: str = Field(..., description="Order ID")
    status: str = Field(..., description="Status of the change request")
    offers: Optional[list] = Field(None, description="List of change offers")
    # Add more fields as needed

class OrderChangeOffer(BaseModel):
    """Model for an order change offer."""
    id: str = Field(..., description="Order change offer ID")
    change_request_id: str = Field(..., description="Order change request ID")
    total_amount: str = Field(..., description="Total amount for the change offer")
    currency: str = Field(..., description="Currency code")
    # Add more fields as needed

class OrderChangeOfferResponse(BaseModel):
    """Response model for an order change offer."""
    id: str = Field(..., description="Order change offer ID")
    status: str = Field(..., description="Status of the offer")
    # Add more fields as needed

class OrderChange(BaseModel):
    """Model for an order change (confirmed change)."""
    id: str = Field(..., description="Order change ID")
    order_id: str = Field(..., description="Order ID")
    status: str = Field(..., description="Status of the change")
    # Add more fields as needed 


class BaggageService(BaseModel):
    """Baggage service information."""
    id: str = Field(..., description="Service ID")
    type: str = Field(..., description="Service type (should be 'baggage')")
    name: str = Field(..., description="Service name")
    description: Optional[str] = Field(None, description="Service description")
    price: Optional[str] = Field(None, description="Service price")
    currency: Optional[str] = Field(None, description="Currency code")
    quantity: Optional[int] = Field(None, description="Quantity available")
    weight: Optional[str] = Field(None, description="Weight limit")
    dimensions: Optional[str] = Field(None, description="Dimension limits")
    passenger_ids: Optional[List[str]] = Field(None, description="Applicable passenger IDs") 

"""
Common Pydantic models shared across Duffel API endpoints.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


class Money(BaseModel):
    """Represents a monetary amount with currency."""
    amount: str = Field(..., description="Amount as a string to preserve precision")
    currency: str = Field(..., description="ISO 4217 currency code")
    
    @property
    def decimal_amount(self) -> Decimal:
        """Get amount as a Decimal for calculations."""
        return Decimal(self.amount)
    
    def __str__(self) -> str:
        return f"{self.currency} {self.amount}"


class Coordinates(BaseModel):
    """Geographic coordinates."""
    latitude: float = Field(..., description="Latitude in decimal degrees")
    longitude: float = Field(..., description="Longitude in decimal degrees")


class Address(BaseModel):
    """Physical address information."""
    line_one: Optional[str] = Field(None, description="First line of address")
    line_two: Optional[str] = Field(None, description="Second line of address")
    city: Optional[str] = Field(None, description="City name")
    region: Optional[str] = Field(None, description="State/region/province")
    postal_code: Optional[str] = Field(None, description="Postal/ZIP code")
    country_code: Optional[str] = Field(None, description="ISO 3166-1 alpha-2 country code")
    
    def __str__(self) -> str:
        parts = [self.line_one, self.city, self.region, self.country_code]
        return ", ".join(part for part in parts if part)


class Location(BaseModel):
    """Location information for searches and results."""
    id: Optional[str] = Field(None, description="Duffel location ID")
    name: str = Field(..., description="Location name (city, region, etc.)")
    type: Optional[str] = Field(None, description="Location type (city, airport, etc.)")
    iata_code: Optional[str] = Field(None, description="IATA code for airports")
    iata_country_code: Optional[str] = Field(None, description="ISO 3166-1 alpha-2 country code")
    coordinates: Optional[Coordinates] = Field(None, description="Geographic coordinates")
    
    def __str__(self) -> str:
        if self.iata_code:
            return f"{self.name} ({self.iata_code})"
        return self.name


class DateRange(BaseModel):
    """Date range for searches."""
    check_in: date = Field(..., description="Check-in date")
    check_out: date = Field(..., description="Check-out date")
    
    @validator('check_out')
    def check_out_after_check_in(cls, v, values):
        if 'check_in' in values and v <= values['check_in']:
            raise ValueError('Check-out date must be after check-in date')
        return v
    
    @property
    def nights(self) -> int:
        """Number of nights for the stay."""
        return (self.check_out - self.check_in).days
    
    def __str__(self) -> str:
        return f"{self.check_in} to {self.check_out} ({self.nights} nights)"


class Guest(BaseModel):
    """Guest information for booking."""
    adults: int = Field(1, ge=1, description="Number of adult guests")
    children: int = Field(0, ge=0, description="Number of child guests")
    
    @property
    def total(self) -> int:
        """Total number of guests."""
        return self.adults + self.children
    
    def __str__(self) -> str:
        if self.children > 0:
            return f"{self.adults} adults, {self.children} children"
        return f"{self.adults} adult{'s' if self.adults != 1 else ''}"


class DuffelError(BaseModel):
    """Duffel API error response."""
    type: str = Field(..., description="Error type")
    title: str = Field(..., description="Error title")
    detail: Optional[str] = Field(None, description="Detailed error message")
    status: Optional[int] = Field(None, description="HTTP status code")
    
    def __str__(self) -> str:
        return f"{self.title}: {self.detail or 'No additional details'}"


class DuffelResponse(BaseModel):
    """Base class for Duffel API responses."""
    data: Any = Field(..., description="Response data")
    meta: Optional[Dict[str, Any]] = Field(None, description="Response metadata")
    
    class Config:
        extra = "allow"  # Allow additional fields from API 
from typing import List, Dict, Any, Optional
from ..client import DuffelClient, DuffelAPIError, get_client
from ..models.flights import FlightSearchRequest, FlightSearchResponse, FlightLoyaltyProgramme, BaggageService
from datetime import datetime, date, timedelta
import isodate
import logging

logger = logging.getLogger(__name__)

class FlightsEndpoint:
    def __init__(self, client: DuffelClient):
        self.client = client

    async def search_flights(
        self,
        slices: list,
        passengers: int = 1,
        cabin_class: str = "economy",
        limit: int = 10
    ):
        """
        Search for flights (single or multi-city).
        Args:
            slices: List of dicts with 'origin', 'destination', 'departure_date'
            passengers: Number of passengers
            cabin_class: Cabin class
            limit: Max results (not used in Duffel API, but can be used for formatting)
        Returns:
            FlightSearchResponse
        """
        passengers_list = [{"type": "adult"} for _ in range(passengers)]
        request_body = {
            "data": {
                "slices": slices,
                "passengers": passengers_list,
                "cabin_class": cabin_class
            }
        }
        response = await self.client.post("/air/offer_requests", data=request_body)
        offer_request_id = response["data"]["id"]
        offers_response = await self.client.get(f"/air/offers?offer_request_id={offer_request_id}")
        offers = offers_response["data"]
        flight_offers = self._parse_flight_offers(offers)
        return FlightSearchResponse(
            offers=flight_offers,
            total_results=len(flight_offers),
            search_id=offer_request_id
        )
    
    @staticmethod
    def format_iso_duration(iso_str):
        try:
            d = isodate.parse_duration(iso_str)
            total_minutes = int(d.total_seconds() // 60)
            hours = total_minutes // 60
            minutes = total_minutes % 60
            return f"{hours}h {minutes}m"
        except Exception:
            return iso_str or "N/A"

    @staticmethod
    def get_total_journey_duration(slices):
        all_departures = []
        all_arrivals = []
        for sli in slices:
            segments = sli.get('segments', [])
            if segments:
                dep = segments[0].get('departing_at') or segments[0].get('departure_time')
                arr = segments[-1].get('arriving_at') or segments[-1].get('arrival_time')
                if dep and arr:
                    all_departures.append(dep)
                    all_arrivals.append(arr)
        if all_departures and all_arrivals:
            try:
                t1 = datetime.fromisoformat(all_departures[0])
                t2 = datetime.fromisoformat(all_arrivals[-1])
                total_seconds = int((t2 - t1).total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return f"{hours}h {minutes}m"
            except Exception:
                return "N/A"
        return "N/A"

    @staticmethod
    def get_slice_layovers(segments):
        """Calculate layovers within a slice (connecting flights)."""
        layovers = []
        for i in range(1, len(segments)):
            prev_arrival = segments[i-1].get('arriving_at')
            next_departure = segments[i].get('departing_at')
            location = segments[i-1].get('destination', {}).get('city_name', 'N/A')
            if prev_arrival and next_departure:
                try:
                    t1 = datetime.fromisoformat(prev_arrival)
                    t2 = datetime.fromisoformat(next_departure)
                    layover_minutes = int((t2 - t1).total_seconds() // 60)
                    hours = layover_minutes // 60
                    minutes = layover_minutes % 60
                    layovers.append({
                        "duration": f"{hours}h {minutes}m",
                        "location": location
                    })
                except Exception:
                    pass
        return layovers
    
    @staticmethod
    def get_stopover_layovers(slices):
        """Calculate layovers/stopovers between slices (multi-city)."""
        layovers = []
        for i in range(1, len(slices)):
            prev_segments = slices[i-1].get('segments', [])
            next_segments = slices[i].get('segments', [])
            if prev_segments and next_segments:
                prev_arrival = prev_segments[-1].get('arriving_at') or prev_segments[-1].get('arrival_time')
                next_departure = next_segments[0].get('departing_at') or next_segments[0].get('departure_time')
                location = prev_segments[-1].get('destination', {}).get('city_name', 'N/A')
                if prev_arrival and next_departure:
                    try:
                        t1 = datetime.fromisoformat(prev_arrival)
                        t2 = datetime.fromisoformat(next_departure)
                        layover_minutes = int((t2 - t1).total_seconds() // 60)
                        hours = layover_minutes // 60
                        minutes = layover_minutes % 60
                        layovers.append({
                            "duration": f"{hours}h {minutes}m",
                            "location": location
                        })
                    except Exception:
                        pass
        return layovers
    
    def _parse_flight_offers(self, offers: list) -> list:        
        formatted = []
        for offer in offers:
            airline = offer.get('owner', {}).get('name', 'N/A')
            airline_logo = offer.get('owner', {}).get('logo_symbol_url', None)
            price = f"{offer.get('total_amount', 'N/A')} {offer.get('total_currency', 'N/A')}"
            offer_id = offer.get('id', 'N/A')
            passenger_ids = [p.get("id") for p in offer.get("passengers", []) if p.get("id")]
            emissions = offer.get('total_emissions_kg', 'N/A')
            loyalty = ', '.join(offer.get('supported_loyalty_programmes', [])) or 'N/A'

            conditions = offer.get('conditions') or {}
            refund_before = conditions.get('refund_before_departure') or {}
            refundable = "Yes" if refund_before.get('allowed') else "No"
            change_before = conditions.get('change_before_departure') or {}
            changeable = "Yes" if change_before.get('allowed') else "No"

            payment_by = offer.get('payment_requirements', {}).get('payment_required_by', 'N/A')
            instant_payment = "Yes" if offer.get('payment_requirements', {}).get('requires_instant_payment') else "No"

            slices = offer.get('slices', [])
            total_journey_duration = self.get_total_journey_duration(slices)
            stopover_layovers = self.get_stopover_layovers(slices)

            slices_info = []
            for slice_idx, sli in enumerate(slices, 1):
                fare_brand = sli.get('fare_brand_name', 'N/A')
                duration_iso = sli.get('duration', 'N/A')
                duration = self.format_iso_duration(duration_iso)
                segments_info = []
                segments = sli.get('segments', [])
                slice_layovers = self.get_slice_layovers(segments)
                for seg_idx, seg in enumerate(segments):
                    flight_number = (
                        seg.get('marketing_carrier_flight_number')
                        or seg.get('operating_carrier_flight_number')
                        or 'N/A'
                    )
                    origin = seg.get('origin', {}).get('iata_code', 'N/A')
                    origin_city = seg.get('origin', {}).get('city_name', 'N/A')
                    origin_terminal = seg.get('origin_terminal', 'N/A')
                    destination = seg.get('destination', {}).get('iata_code', 'N/A')
                    destination_city = seg.get('destination', {}).get('city_name', 'N/A')
                    destination_terminal = seg.get('destination_terminal', 'N/A')
                    dep_time = seg.get('departing_at', 'N/A')
                    arr_time = seg.get('arriving_at', 'N/A')
                    cabin = seg.get('passengers', [{}])[0].get('cabin', {}).get('marketing_name', 'N/A')
                    baggages = seg.get('passengers', [{}])[0].get('baggages', [])
                    baggage_str = ', '.join(f"{b.get('quantity', 1)} {b.get('type', '')}" for b in baggages) or 'N/A'
                    amenities = seg.get('passengers', [{}])[0].get('cabin', {}).get('amenities') or {}
                    wifi = amenities.get('wifi', {}).get('available')
                    power = amenities.get('power', {}).get('available')
                    seat_pitch = amenities.get('seat', {}).get('pitch')
                    segments_info.append({
                        "flight_number": flight_number,
                        "origin": origin,
                        "origin_city": origin_city,
                        "origin_terminal": origin_terminal,
                        "destination": destination,
                        "destination_city": destination_city,
                        "destination_terminal": destination_terminal,
                        "departure_time": dep_time,
                        "arrival_time": arr_time,
                        "cabin": cabin,
                        "baggage": baggage_str,
                        "wifi": wifi,
                        "power": power,
                        "seat_pitch": seat_pitch,
                    })
                slices_info.append({
                    "fare_brand": fare_brand,
                    "duration": duration,
                    "segments": segments_info,
                    "layovers": slice_layovers,
                })
            formatted.append({
                "airline": airline,
                "airline_logo": airline_logo,
                "price": price,
                "offer_id": offer_id,
                "emissions": emissions,
                "loyalty": loyalty,
                "refundable": refundable,
                "changeable": changeable,
                "payment_by": payment_by,
                "instant_payment": instant_payment,
                "total_journey_duration": total_journey_duration,
                "layovers": stopover_layovers,
                "slices": slices_info,
                "passenger_ids": passenger_ids,
            })
        return formatted
    
    async def get_seat_maps(self, offer_id: str) -> dict:
        return await self.client.get(f"/air/seat_maps?offer_id={offer_id}")

    async def get_offer(self, offer_id: str) -> Dict[str, Any]:
        """
        Retrieve detailed information for a specific flight offer by its ID.
        """
        return await self.client.get(f"/air/offers/{offer_id}")
    
    async def book_flight(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Book a flight using the provided order data.
        """
        return await self.client.post("/air/orders", data={"data": order_data})
    
    async def list_airline_initiated_changes(self) -> list:
        """List all airline-initiated changes."""
        return await self.client.get("/air/airline_initiated_changes")

    async def update_airline_initiated_change(self, change_id: str, data: dict) -> dict:
        """Update an airline-initiated change."""
        return await self.client.patch(f"/air/airline_initiated_changes/{change_id}", data=data)

    async def accept_airline_initiated_change(self, change_id: str) -> dict:
        """Accept an airline-initiated change."""
        return await self.client.post(f"/air/airline_initiated_changes/{change_id}/actions/accept")

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        Retrieve detailed information for a specific order by its ID.
        """
        return await self.client.get(f"/air/orders/{order_id}")

    async def list_order_cancellations(self, params: dict = None) -> dict:
        """GET /air/order_cancellations: List all order cancellations."""
        return await self.client.get("/air/order_cancellations", params=params)

    async def get_order_cancellation(self, cancellation_id: str) -> dict:
        """GET /air/order_cancellations/{id}: Get details for a specific cancellation."""
        return await self.client.get(f"/air/order_cancellations/{cancellation_id}")

    async def confirm_order_cancellation(self, cancellation_id: str) -> dict:
        """POST /air/order_cancellations/{id}/actions/confirm: Confirm a cancellation."""
        return await self.client.post(f"/air/order_cancellations/{cancellation_id}/actions/confirm")

    async def create_order_cancellation(self, order_id: str) -> dict:
        """POST /air/order_cancellations: Create a cancellation request for an order."""
        data = {"data": {"order_id": order_id}}
        return await self.client.post("/air/order_cancellations", data=data)

    # --- Order Change Methods ---
    async def create_order_change_request(self, order_id: str, slices: Optional[list] = None, type: Optional[str] = None) -> Dict[str, Any]:
        """Create a request to change an order."""
        logger.info(f"Creating order change request for order {order_id}, type: {type}")
        
        data = {"data": {"order_id": order_id}}
        
        if type is not None:
            data["data"]["type"] = type
        
        if slices is not None:
            # For Duffel API, slices should be directly in the data, not nested under "add"
            data["data"]["slices"] = slices
            logger.info(f"Added {len(slices)} slices to change request")
        
        logger.debug(f"Order change request data: {data}")
        
        try:
            response = await self.client.post("/air/order_change_requests", data=data)
            logger.info(f"Order change request created successfully: {response.get('data', {}).get('id', 'unknown')}")
            return response
        except Exception as e:
            logger.error(f"Error creating order change request: {e}")
            raise
    
    async def fetch_loyalty_programmes(self) -> list:
        """Fetch all loyalty programmes supported by Duffel Flights."""
        try:
            response = await self.client.get("/air/loyalty_programmes")
            # Parse into FlightLoyaltyProgramme objects
            programmes = []
            for prog_data in response.get("data", []):
                programmes.append(FlightLoyaltyProgramme(
                    reference=prog_data.get("reference"),
                    name=prog_data.get("name"),
                    logo_url_svg=prog_data.get("logo_url_svg"),
                    logo_url_png_small=prog_data.get("logo_url_png_small")
                ))
            return programmes
        except Exception as e:
            logger.error(f"Error fetching loyalty programmes: {e}")
            raise DuffelAPIError(f"Failed to fetch loyalty programmes: {str(e)}")

    async def get_available_services(self, offer_id: str) -> Dict[str, Any]:
        """
        Get available services (including baggage) for a flight offer.
        
        Args:
            offer_id: The flight offer ID
            
        Returns:
            Dict with available services
        """
        try:
            # Use the existing fetch_offer_with_services function
            response = await self.client.get(f"/air/offers/{offer_id}?return_available_services=true")
            return response
        except Exception as e:
            logger.error(f"Error fetching available services: {e}")
            raise DuffelAPIError(f"Failed to fetch available services: {str(e)}")


# --- Standalone functions for agent use ---
async def search_flights(
    slices: list,
    passengers: int = 1,
    cabin_class: str = "economy",
    limit: int = 10
) -> FlightSearchResponse:
    client = get_client()
    endpoint = FlightsEndpoint(client)
    try:
        response = await endpoint.search_flights(
            slices=slices,
            passengers=passengers,
            cabin_class=cabin_class,
            limit=limit
        )
        return response
    except Exception as e:
        raise DuffelAPIError(str(e))
    
async def get_seat_maps(offer_id: str) -> dict:
    client = get_client()
    endpoint = FlightsEndpoint(client)
    try:
        return await endpoint.get_seat_maps(offer_id)
    except Exception as e:
        raise DuffelAPIError(str(e))
    
async def fetch_flight_offer(offer_id: str) -> Dict[str, Any]:
    """
    Retrieve detailed information for a specific flight offer by its ID.
    """
    client = get_client()
    endpoint = FlightsEndpoint(client)
    return await endpoint.get_offer(offer_id)

async def create_flight_booking(offer_id: str, passengers: list, payments: list, loyalty_programme_reference: str = "", loyalty_account_number: str = "", services: list = None) -> Dict[str, Any]:
    """
    Book a flight using the provided order data.
    This endpoint will fetch the offer, extract Duffel passenger IDs,
    and merge them with the user-supplied passenger info.
    Supports optional 'services' (e.g., seat selections).
    
    Args:
        offer_id: The Duffel offer ID
        passengers: List of passenger dicts with user info
        payments: List of payment dicts
        loyalty_programme_reference: Optional loyalty programme reference
        loyalty_account_number: Optional loyalty programme account number
        services: Optional list of service dicts with id, passenger_ids, and quantity
    """
    
    client = get_client()
    endpoint = FlightsEndpoint(client)

    # 1. Fetch the offer to get Duffel passenger IDs
    offer_response = await endpoint.get_offer(offer_id)
    offer_passengers = offer_response.get("data", {}).get("passengers", [])

    if not offer_passengers:
        raise ValueError("No passenger data found in offer. Please try fetching the offer again.")

    if len(passengers) != len(offer_passengers):
        raise ValueError(f"Number of passengers ({len(passengers)}) doesn't match offer ({len(offer_passengers)}).")

    # 2. Merge user info with Duffel IDs
    final_passengers = []
    for i, (user_passenger, offer_passenger) in enumerate(zip(passengers, offer_passengers)):
        email = user_passenger.get('email', '').strip()
        phone_number = user_passenger.get('phone_number', '').strip()
        if not email or not phone_number:
            raise ValueError(f"Missing required contact info for passenger {i+1}. Please provide both email and phone number.")

        final_passenger = {
            "id": offer_passenger["id"],
            "title": user_passenger.get("title", "mr"),
            "given_name": user_passenger.get("given_name", ""),
            "family_name": user_passenger.get("family_name", ""),
            "born_on": user_passenger.get("born_on", ""),
            "gender": user_passenger.get("gender", "m"),
            "email": email,
            "phone_number": phone_number
        }
        
        # Add loyalty program information if provided
        if loyalty_programme_reference and loyalty_account_number:
            final_passenger["loyalty_programme"] = {
                "reference": loyalty_programme_reference,
                "account_number": loyalty_account_number
            }
        
        final_passengers.append(final_passenger)

    # 3. Prepare order data
    order_data = {
        "selected_offers": [offer_id],
        "passengers": final_passengers,
        "payments": payments
    }

    if services:
        order_data["services"] = services  # Add seat selections if provided

    # 4. Add services if provided (following Duffel API structure)
    if services and len(services) > 0:
        order_data["services"] = services
    
    try:
        logger.info(f"Booking flight with order data: {order_data}")
        return await endpoint.book_flight(order_data)
    except DuffelAPIError as e:
        # Try to extract a useful error message
        error_data = None
        if hasattr(e, "args") and e.args:
            error_data = e.args[0]
        else:
            error_data = e

        if isinstance(error_data, dict):
            error_title = error_data.get("title", "Duffel Error")
            error_message = error_data.get("message", str(error_data))
            raise ValueError(f"{error_title}: {error_message}")
        elif isinstance(error_data, str):
            raise ValueError(f"Duffel API Error: {error_data}")
        else:
            # Fallback: always use str(e)
            raise ValueError(f"Duffel API Error: {str(e)}")
    except Exception as e:
        raise ValueError(f"Booking failed: {str(e)}")

async def list_airline_initiated_changes() -> list:
    client = get_client()
    endpoint = FlightsEndpoint(client)
    return await endpoint.list_airline_initiated_changes()

async def update_airline_initiated_change(change_id: str, data: dict) -> dict:
    client = get_client()
    endpoint = FlightsEndpoint(client)
    return await endpoint.update_airline_initiated_change(change_id, data)

async def accept_airline_initiated_change(change_id: str) -> dict:
    client = get_client()
    endpoint = FlightsEndpoint(client)
    return await endpoint.accept_airline_initiated_change(change_id)

async def fetch_offer_with_services(offer_id: str) -> dict:
    """
    Fetch a flight offer with available services (e.g., extra baggage).
    """
    client = get_client()
    endpoint = FlightsEndpoint(client)
    return await endpoint.client.get(f"/air/offers/{offer_id}?return_available_services=true")


async def fetch_flight_loyalty_programmes() -> list:
    """
    Fetch all loyalty programmes supported by Duffel Flights.
    """
    client = get_client()
    endpoint = FlightsEndpoint(client)
    return await endpoint.fetch_loyalty_programmes()


async def get_available_services(offer_id: str) -> Dict[str, Any]:
    """
    Get available services (including baggage) for a flight offer.
    
    Args:
        offer_id: The flight offer ID
        
    Returns:
        Dict with available services
    """
    client = get_client()
    endpoint = FlightsEndpoint(client)
    return await endpoint.get_available_services(offer_id)


def format_flights_table(flights):
    header = "| # | Airline | Price | Leg | From | To | Departure | Arrival | Flight # | Layover (min) | Journey Time |\n"
    header += "|---|---------|-------|-----|------|----|-----------|---------|----------|--------------|--------------|\n"
    rows = []
    for idx, f in enumerate(flights, 1):
        for slice_ in f.get("slices", []):
            layover_str = ", ".join(str(l) for l in slice_.get("layovers", [])) if slice_.get("layovers") else "-"
            rows.append(
                f"| {idx} | {f['airline']} | {f['price']} | {slice_['leg']} | {slice_['origin']} | {slice_['destination']} | {slice_['departure_time']} | {slice_['arrival_time']} | {slice_.get('flight_number', 'Unknown')} | {layover_str} | {slice_.get('journey_time', '-') } |"
            )
    return header + "\n".join(rows)

def format_flights_markdown(flights: list) -> str:
    md = []
    for idx, f in enumerate(flights, 1):
        md.append(f"### Option {idx}: {f.get('airline', 'N/A')}")
        md.append(f"**Price:** {f.get('price', 'N/A')}  \n**Offer ID:** `{f.get('offer_id', f.get('id', 'N/A'))}`")
        md.append(f"**Instant Payment Required:** {f.get('instant_payment', 'N/A')}")
        md.append(f"**Supported Loyalty Programmes:** {f.get('loyalty', 'N/A')}")
        md.append(f"**Total Journey Duration:** {f.get('total_journey_duration', 'N/A')}")
        # Layovers/stopovers between slices
        layovers = f.get('layovers', [])
        if layovers:
            for lidx, l in enumerate(layovers, 1):
                md.append(f"**Layover {lidx}:** {l.get('duration', 'N/A')} in {l.get('location', 'N/A')}")
        for slice_idx, sli in enumerate(f.get('slices', []), 1):
            md.append(f"\n**Leg {slice_idx}** ({sli.get('fare_brand', 'N/A')}, Duration: {sli.get('duration', 'N/A')})")
            
            for lidx, l in enumerate(sli.get('layovers', []), 1):
                md.append(f"  - **Layover {lidx}:** {l.get('duration', 'N/A')} in {l.get('location', 'N/A')}")

            for seg_idx, seg in enumerate(sli.get('segments', []), 1):
                md.append(
                    f"- **Segment {seg_idx}:** {seg.get('origin_city', 'N/A')} ({seg.get('origin', 'N/A')}) Terminal {seg.get('origin_terminal', 'N/A')} → "
                    f"{seg.get('destination_city', 'N/A')} ({seg.get('destination', 'N/A')}) Terminal {seg.get('destination_terminal', 'N/A')}\n"
                    f"  - **Flight #:** {seg.get('flight_number', 'N/A')}\n"
                    f"  - **Departure:** {seg.get('departure_time', 'N/A')}  \n  - **Arrival:** {seg.get('arrival_time', 'N/A')}\n"
                    f"  - **Cabin:** {seg.get('cabin', 'N/A')}  \n  - **Baggage:** {seg.get('baggage', 'N/A')}\n"
                    f"  - **Amenities:** WiFi: {'Yes' if seg.get('wifi') else 'No'}, Power: {'Yes' if seg.get('power') else 'No'}, Seat Pitch: {seg.get('seat_pitch', 'N/A')}"
                )
        md.append("---")
    return "\n".join(md)

# --- Order Cancellation Functions ---
async def list_order_cancellations(params: dict = None) -> dict:
    """GET /air/order_cancellations: List all order cancellations."""
    client = get_client()
    return await client.get("/air/order_cancellations", params=params)

async def get_order_cancellation(cancellation_id: str) -> dict:
    """GET /air/order_cancellations/{id}: Get details for a specific cancellation."""
    client = get_client()
    return await client.get(f"/air/order_cancellations/{cancellation_id}")

async def confirm_order_cancellation(cancellation_id: str) -> dict:
    """POST /air/order_cancellations/{id}/actions/confirm: Confirm a cancellation."""
    client = get_client()
    return await client.post(f"/air/order_cancellations/{cancellation_id}/actions/confirm")

async def create_order_cancellation(order_id: str) -> dict:
    """POST /air/order_cancellations: Create a cancellation request for an order."""
    client = get_client()
    data = {"data": {"order_id": order_id}}
    return await client.post("/air/order_cancellations", data=data)

async def create_order_change_request_api(*, order_id: str, slices: Optional[list] = None, type: Optional[str] = None) -> Dict[str, Any]:
    client = get_client()
    endpoint = FlightsEndpoint(client)
    return await endpoint.create_order_change_request(order_id=order_id, slices=slices, type=type)



    

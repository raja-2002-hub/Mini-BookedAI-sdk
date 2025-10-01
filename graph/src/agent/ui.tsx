import React, { useState, useEffect } from 'react';
import { v4 as uuidv4 } from "uuid";
import { useStreamContext } from "@langchain/langgraph-sdk/react-ui";
import { Message } from "@langchain/langgraph-sdk";

// Luhn algorithm for card number validation
const isValidCardNumber = (cardNumber) => {
  const cleanNumber = cardNumber.replace(/\s/g, '');
  if (!/^\d{12,19}$/.test(cleanNumber)) return false;

  let sum = 0;
  let isEven = false;
  for (let i = cleanNumber.length - 1; i >= 0; i--) {
    let digit = parseInt(cleanNumber[i], 10);
    if (isEven) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    sum += digit;
    isEven = !isEven;
  }
  return sum % 10 === 0;
};

// Hotel search result component
const HotelResultCard = ({ hotels }) => {
  const stream = useStreamContext();

  // Add null check and early return
  if (!hotels || !Array.isArray(hotels) || hotels.length === 0) {
    return null;
  }

  // Handle hotel card click to submit hotel selection
const handleHotelSelect = async (hotel, index) => {
  if (!stream) {
    console.error('Stream context not available');
    return;
  }

  try {
    const safeHotel = {
      name: hotel?.name || 'Hotel Name',
      location: hotel?.location || 'Location',
      rating: hotel?.rating || '0.0',
      price: hotel?.price || 'Price N/A',
      image: hotel?.image || 'https://via.placeholder.com/300x400?text=Hotel+Image',
      amenities: hotel?.amenities || []
    };

    const hotelMessage = {
      id: uuidv4(),
      type: "human",
      content: `
Selected Hotel:
Hotel Name: ${safeHotel.name}
Location: ${safeHotel.location}
Rating: ${safeHotel.rating} stars
Price: ${safeHotel.price}
${safeHotel.amenities.length > 0 ? `Amenities: ${safeHotel.amenities.join(', ')}` : ''}
      `.trim()
    };

    await stream.submit(
      {
        threadId: stream.threadId,
        messages: [hotelMessage]
      },
      {
        streamMode: ["values"],
        optimisticValues: (prev) => ({
          ...prev,
          messages: [...(prev.messages ?? []), hotelMessage]
        })
      }
    );

  } catch (error) {
    console.error('Hotel selection error:', error);
    alert(error instanceof Error ? error.message : "An error occurred while selecting the hotel");
  }
};

  // Inline styles for scoped Tailwind CSS with adjusted text proportions
  const scopedStyles = `
    #hotel-cards-scope .grid { display: grid; }
    #hotel-cards-scope .grid-cols-1 { grid-template-columns: repeat(1, minmax(0, 1fr)); }
    #hotel-cards-scope .sm\\:grid-cols-2 { @media (min-width: 640px) { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    #hotel-cards-scope .md\\:grid-cols-3 { @media (min-width: 768px) { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
    #hotel-cards-scope .lg\\:grid-cols-4 { @media (min-width: 1024px) { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
    #hotel-cards-scope .xl\\:grid-cols-5 { @media (min-width: 1280px) { grid-template-columns: repeat(5, minmax(0, 1fr)); } }
    #hotel-cards-scope .gap-4 { gap: 1rem; }
    #hotel-cards-scope .w-full { width: 100%; }
    #hotel-cards-scope .relative { position: relative; }
    #hotel-cards-scope .aspect-\\[3\\/4\\] { aspect-ratio: 3/4; }
    #hotel-cards-scope .rounded-xl { border-radius: 0.75rem; }
    #hotel-cards-scope .overflow-hidden { overflow: hidden; }
    #hotel-cards-scope .shadow-lg { box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05); }
    #hotel-cards-scope .absolute { position: absolute; }
    #hotel-cards-scope .inset-0 { top: 0; right: 0; bottom: 0; left: 0; }
    #hotel-cards-scope .bg-black\\/40 { background-color: rgba(0, 0, 0, 0.4); }
    #hotel-cards-scope .h-full { height: 100%; }
    #hotel-cards-scope .flex { display: flex; }
    #hotel-cards-scope .flex-col { flex-direction: column; }
    #hotel-cards-scope .justify-between { justify-content: space-between; }
    #hotel-cards-scope .p-3 { padding: 0.75rem; }
    #hotel-cards-scope .text-white { color: white; }
    #hotel-cards-scope .text-sm { font-size: 0.875rem; line-height: 1.25rem; }
    #hotel-cards-scope .font-bold { font-weight: 700; }
    #hotel-cards-scope .leading-tight { line-height: 1.25; }
    #hotel-cards-scope .flex-wrap { flex-wrap: wrap; }
    #hotel-cards-scope .items-center { align-items: center; }
    #hotel-cards-scope .gap-1 { gap: 0.25rem; }
    #hotel-cards-scope .gap-2 { gap: 0.5rem; }
    #hotel-cards-scope .mt-1 { margin-top: 0.25rem; }
    #hotel-cards-scope .text-xs { font-size: 0.75rem; line-height: 1rem; }
    #hotel-cards-scope .text-2xs { font-size: 0.625rem; line-height: 0.875rem; }
    #hotel-cards-scope .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    #hotel-cards-scope .inline-flex { display: inline-flex; }
    #hotel-cards-scope .bg-white\\/20 { background-color: rgba(255, 255, 255, 0.2); }
    #hotel-cards-scope .backdrop-blur-sm { backdrop-filter: blur(4px); }
    #hotel-cards-scope .px-1\\.5 { padding-left: 0.375rem; padding-right: 0.375rem; }
    #hotel-cards-scope .px-1 { padding-left: 0.25rem; padding-right: 0.25rem; }
    #hotel-cards-scope .py-0\\.5 { padding-top: 0.125rem; padding-bottom: 0.125rem; }
    #hotel-cards-scope .py-0 { padding-top: 0; padding-bottom: 0; }
    #hotel-cards-scope .rounded-full { border-radius: 9999px; }
    #hotel-cards-scope .mt-auto { margin-top: auto; }
    #hotel-cards-scope .text-base { font-size: 1rem; line-height: 1.5rem; }
    #hotel-cards-scope .mb-1 { margin-bottom: 0.25rem; }
    #hotel-cards-scope .font-medium { font-weight: 500; }
  `;

  return (
    <React.Fragment>
      <style dangerouslySetInnerHTML={{ __html: scopedStyles }} />
      <div id="hotel-cards-scope">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {hotels.map((hotel, index) => {
            // Add safety checks for hotel properties
            const safeHotel = {
              name: hotel?.name || 'Hotel Name',
              location: hotel?.location || 'Location',
              rating: hotel?.rating || '0.0',
              price: hotel?.price || 'Price N/A',
              image: hotel?.image || 'https://via.placeholder.com/300x400?text=Hotel+Image',
              amenities: hotel?.amenities || []
            };

            return (
              <div key={`hotel-${index}`} className="w-full"> 
                <div 
                  className="relative w-full aspect-[3/4] rounded-xl overflow-hidden shadow-lg cursor-pointer transition-all duration-300 hover:shadow-xl hover:scale-105"
                  onClick={() => handleHotelSelect(hotel, index)}
                  style={{ 
                    backgroundImage: `url(${safeHotel.image})`, 
                    backgroundSize: 'cover', 
                    backgroundPosition: 'center',
                    cursor: 'pointer'
                  }}
                >
                  <div className="absolute inset-0 bg-black/40" />
                  <div className="relative h-full flex flex-col justify-between p-3 text-white">
                    <div>
                      <h1 className="text-sm font-bold leading-tight">{safeHotel.name}</h1>
                      <div className="flex flex-wrap items-center gap-1 mt-1">
                        <span className="text-xs truncate">{safeHotel.location}</span>
                        <span className="inline-flex items-center bg-white/20 backdrop-blur-sm px-1.5 py-0.5 rounded-full text-xs font-bold">
                          ⭐ {safeHotel.rating}
                        </span>
                      </div>
                    </div>
                    <div className="mt-auto">
                      <div className="text-base font-bold mb-1">{safeHotel.price}</div>
                      <div className="flex flex-wrap gap-1">
                        {safeHotel.amenities.slice(0, 3).map((amenity, i) => (
                          <span key={`amenity-${i}`} className="bg-white/20 backdrop-blur-sm px-1 py-0 rounded-full text-2xs font-medium">
                            {amenity}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </React.Fragment>
  );
};  

// Flight search result component 
const FlightResultCard = (props) => {

  const stream = useStreamContext();
  
  if (!props.flights || !Array.isArray(props.flights) || props.flights.length === 0) {
    return null;
  }

  const parseTime = (isoString) => {
    if (!isoString) return '--:--';
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString(undefined, { 
        hour: '2-digit', 
        minute: '2-digit',
        hour12: false 
      });
    } catch {
      return '--:--';
    }
  };

  const parseDate = (isoString) => {
    if (!isoString) return '';
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString('en-US', { 
        weekday: 'short',
        day: 'numeric',
        month: 'short'
      });
    } catch {
      return '';
    }
  };

  const calculateStops = (slices) => {
    if (!slices || !Array.isArray(slices) || slices.length === 0) return 0;
    const firstSlice = slices[0];
    if (!firstSlice || !firstSlice.segments) return 0;
    return Math.max(0, firstSlice.segments.length - 1);
  };

  const handleFlightSelect = async (flight, index) => {
    if (!stream) {
      console.error('Stream context not available');
      return;
    }

    try {
      const isReturnFlight = flight.slices && flight.slices.length > 1;
      
      let content = '';
      
      if (isReturnFlight) {
        // Return flight
        const outboundSlice = flight.slices[0];
        const returnSlice = flight.slices[1];
        
        const outboundFirstSeg = outboundSlice?.segments?.[0];
        const outboundLastSeg = outboundSlice?.segments?.[outboundSlice.segments.length - 1];
        const returnFirstSeg = returnSlice?.segments?.[0];
        const returnLastSeg = returnSlice?.segments?.[returnSlice.segments.length - 1];
        
        const outboundStops = Math.max(0, (outboundSlice?.segments?.length || 1) - 1);
        const returnStops = Math.max(0, (returnSlice?.segments?.length || 1) - 1);
        
        content = `
Selected Return Flight:
Offer ID: ${flight.offer_id || 'N/A'}
Airline: ${flight.airline || 'Unknown Airline'}
Total Price: ${flight.price || 'Price N/A'}

Outbound Journey:
Route: ${outboundFirstSeg?.origin || ''} → ${outboundLastSeg?.destination || ''}
Departure: ${parseDate(outboundFirstSeg?.departure_time)} at ${parseTime(outboundFirstSeg?.departure_time)}
Arrival: ${parseDate(outboundLastSeg?.arrival_time)} at ${parseTime(outboundLastSeg?.arrival_time)}
Duration: ${outboundSlice?.duration || 'N/A'}
Stops: ${outboundStops === 0 ? 'Non-stop' : outboundStops === 1 ? '1 Stop' : `${outboundStops} Stops`}

Return Journey:
Route: ${returnFirstSeg?.origin || ''} → ${returnLastSeg?.destination || ''}
Departure: ${parseDate(returnFirstSeg?.departure_time)} at ${parseTime(returnFirstSeg?.departure_time)}
Arrival: ${parseDate(returnLastSeg?.arrival_time)} at ${parseTime(returnLastSeg?.arrival_time)}
Duration: ${returnSlice?.duration || 'N/A'}
Stops: ${returnStops === 0 ? 'Non-stop' : returnStops === 1 ? '1 Stop' : `${returnStops} Stops`}
        `.trim();
      } else {
        // One-way flight
        const firstSlice = flight.slices?.[0];
        const firstSegment = firstSlice?.segments?.[0];
        const lastSegment = firstSlice?.segments?.[firstSlice.segments.length - 1];
        
        const departure = firstSegment ? parseTime(firstSegment.departure_time) : '--:--';
        const arrival = lastSegment ? parseTime(lastSegment.arrival_time) : '--:--';
        const duration = firstSlice?.duration || 'N/A';
        const stops = calculateStops(flight.slices);

        content = `
Selected Flight:
Offer ID: ${flight.offer_id || 'N/A'}
Airline: ${flight.airline || 'Unknown Airline'}
Route: ${firstSegment?.origin || ''} → ${lastSegment?.destination || ''}
Departure: ${departure}
Arrival: ${arrival}
Duration: ${duration}
Stops: ${stops === 0 ? 'Non-stop' : stops === 1 ? '1 Stop' : `${stops} Stops`}
Price: ${flight.price || 'Price N/A'}
        `.trim();
      }

      const flightMessage = {
        id: uuidv4(),
        type: "human",
        content: content
      };

      await stream.submit(
        {
          threadId: stream.threadId,
          messages: [flightMessage]
        },
        {
          streamMode: ["values"],
          optimisticValues: (prev) => ({
            ...prev,
            messages: [...(prev.messages ?? []), flightMessage]
          })
        }
      );

    } catch (error) {
      console.error('Flight selection error:', error);
      alert(error instanceof Error ? error.message : "An error occurred while selecting the flight");
    }
  };

  const renderJourneySection = (slice, label, airline) => {
    if (!slice) return null;
    
    const firstSegment = slice.segments?.[0];
    const lastSegment = slice.segments?.[slice.segments.length - 1];
    
    const departure = firstSegment ? parseTime(firstSegment.departure_time) : '--:--';
    const arrival = lastSegment ? parseTime(lastSegment.arrival_time) : '--:--';
    const departureDate = firstSegment ? parseDate(firstSegment.departure_time) : '';
    const arrivalDate = lastSegment ? parseDate(lastSegment.arrival_time) : '';
    const duration = slice.duration || 'N/A';
    const stops = Math.max(0, (slice.segments?.length || 1) - 1);
    const originCity = firstSegment?.origin_city || '';
    const destinationCity = lastSegment?.destination_city || '';
    const originCode = firstSegment?.origin || '';
    const destinationCode = lastSegment?.destination || '';

    // Build stops details
    const stopsDetails: string[] = [];
    if (stops > 0 && slice.segments) {
      for (let i = 0; i < slice.segments.length - 1; i++) {
        const segment = slice.segments[i];
        const nextSegment = slice.segments[i + 1];
        if (segment && nextSegment) {
          const stopCode = segment.destination;
          const stopCity = segment.destination_city;
          stopsDetails.push(`${stopCode} ${stopCity || ''}`);
        }
      }
    }

    return (
      <div className="journey-section">
        <div className="journey-header">
          <div className="journey-label">{label}: {departureDate}</div>
          <div className="journey-airline">{airline}</div>
        </div>
        
        {/* Route Section */}
        <div className="route-section">
          {/* Origin */}
          <div className="airport-info">
            <div className="airport-code">{originCode}</div>
            <div className="airport-name">{originCity}</div>
            <div className="flight-date">{departureDate}</div>
            <div className="flight-time">{departure}</div>
          </div>

          {/* Duration */}
          <div className="duration-section">
            <div className="duration-badge">{duration}</div>
          </div>

          {/* Destination */}
          <div className="airport-info" style={{ textAlign: 'right' }}>
            <div className="airport-code">{destinationCode}</div>
            <div className="airport-name">{destinationCity}</div>
            <div className="flight-date">{arrivalDate}</div>
            <div className="flight-time">{arrival}</div>
          </div>
        </div>

        {/* Stops Info */}
        {stops > 0 && (
          <div className="stops-info">
            <div className="stops-detail">
              {stops} stop{stops > 1 ? 's' : ''}
            </div>
            {stopsDetails.map((stop, idx) => (
              <div key={idx} className="stops-detail">{stop}</div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const scopedStyles = `
    #flight-cards-scope { 
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      color: #1f2937;
    }
    #flight-cards-scope .grid { display: grid; }
    #flight-cards-scope .grid-cols-1 { grid-template-columns: repeat(1, minmax(0, 1fr)); }
    #flight-cards-scope .sm\\:grid-cols-2 { @media (min-width: 640px) { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    #flight-cards-scope .md\\:grid-cols-3 { @media (min-width: 768px) { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
    #flight-cards-scope .lg\\:grid-cols-4 { @media (min-width: 1024px) { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
    #flight-cards-scope .xl\\:grid-cols-5 { @media (min-width: 1280px) { grid-template-columns: repeat(5, minmax(0, 1fr)); } }
    #flight-cards-scope .gap-4 { gap: 1rem; }
    #flight-cards-scope .return-flight-wrapper {
      grid-column: 1 / -1;
    }
    @media (min-width: 768px) {
      #flight-cards-scope .return-flight-wrapper {
        grid-column: span 2;
      }
    }
    @media (min-width: 1024px) {
      #flight-cards-scope .return-flight-wrapper {
        grid-column: span 3;
      }
    }
    #flight-cards-scope .flight-card {
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 16px;
      transition: all 0.2s ease;
      cursor: pointer;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
    #flight-cards-scope .flight-card:hover {
      border-color: #2196f3;
      box-shadow: 0 4px 12px rgba(33, 150, 243, 0.15);
    }
    #flight-cards-scope .return-flight-card {
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 16px;
      transition: all 0.2s ease;
      cursor: pointer;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
    #flight-cards-scope .return-flight-card:hover {
      border-color: #2196f3;
      box-shadow: 0 4px 12px rgba(33, 150, 243, 0.15);
    }
    #flight-cards-scope .journey-container {
      display: flex;
      flex-direction: column;
      gap: 0;
    }
    @media (min-width: 768px) {
      #flight-cards-scope .journey-container {
        flex-direction: row;
        gap: 0;
      }
    }
    #flight-cards-scope .journey-section {
      flex: 1;
      min-width: 0;
      padding: 16px;
    }
    #flight-cards-scope .journey-section:first-child {
      padding-right: 20px;
    }
    #flight-cards-scope .journey-section:last-child {
      padding-left: 20px;
    }
    @media (max-width: 767px) {
      #flight-cards-scope .journey-section:first-child {
        padding-right: 16px;
        padding-bottom: 12px;
      }
      #flight-cards-scope .journey-section:last-child {
        padding-left: 16px;
        padding-top: 12px;
      }
    }
    #flight-cards-scope .journey-divider {
      display: none;
    }
    @media (min-width: 768px) {
      #flight-cards-scope .journey-divider {
        display: block;
        width: 1px;
        background: #e5e7eb;
        align-self: stretch;
      }
    }
    @media (max-width: 767px) {
      #flight-cards-scope .journey-divider {
        display: block;
        height: 1px;
        background: #e5e7eb;
        margin: 0;
      }
    }
    #flight-cards-scope .journey-label {
      font-size: 11px;
      font-weight: 700;
      color: #1f2937;
      margin-bottom: 12px;
      letter-spacing: 0;
    }
    #flight-cards-scope .journey-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }
    #flight-cards-scope .journey-airline {
      font-size: 11px;
      color: #6b7280;
      font-weight: 500;
    }
    #flight-cards-scope .airline-logo {
      height: 20px;
      width: auto;
      max-width: 100%;
      object-fit: contain;
      margin-bottom: 12px;
    }
    #flight-cards-scope .route-section {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }
    #flight-cards-scope .airport-info {
      flex: 1;
      min-width: 0;
    }
    #flight-cards-scope .airport-code {
      font-size: 9px;
      color: #6b7280;
      font-weight: 600;
      margin-bottom: 2px;
    }
    #flight-cards-scope .airport-name {
      font-size: 9px;
      color: #6b7280;
      margin-bottom: 6px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    #flight-cards-scope .flight-time {
      font-size: 14px;
      font-weight: 700;
      color: #1f2937;
      margin-bottom: 2px;
    }
    #flight-cards-scope .flight-date {
      font-size: 9px;
      color: #6b7280;
      margin-top: 0;
    }
    #flight-cards-scope .duration-section {
      flex: 0 0 auto;
      text-align: center;
      padding: 0 12px;
      align-self: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
    }
    #flight-cards-scope .duration-badge {
      background: transparent;
      color: #6b7280;
      font-size: 9px;
      font-weight: 500;
      padding: 0;
      border-radius: 0;
      display: inline-block;
      white-space: nowrap;
    }
    #flight-cards-scope .info-row {
      display: flex;
      justify-content: space-between;
      padding: 6px 0;
      border-top: 1px solid #f3f4f6;
      font-size: 10px;
    }
    #flight-cards-scope .info-label {
      color: #6b7280;
      font-weight: 500;
    }
    #flight-cards-scope .info-value {
      color: #6b7280;
      font-weight: 500;
      text-align: right;
    }
    #flight-cards-scope .stops-info {
      margin-top: 4px;
    }
    #flight-cards-scope .stops-detail {
      font-size: 10px;
      color: #6b7280;
      font-weight: 500;
      line-height: 1.6;
    }
    #flight-cards-scope .price-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 8px;
      border-top: 1px solid #f3f4f6;
    }
    #flight-cards-scope .price-label {
      font-size: 10px;
      color: #6b7280;
      font-weight: 500;
    }
    #flight-cards-scope .price-value {
      font-size: 16px;
      font-weight: 700;
      color: #1f2937;
    }
  `;

  return (
    <React.Fragment>
      <style dangerouslySetInnerHTML={{ __html: scopedStyles }} />
      <div id="flight-cards-scope">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {props.flights.map((flight, index) => {
            const isReturnFlight = flight.slices && flight.slices.length > 1;
            
            if (isReturnFlight) {
              return (
                <div key={`flight-${index}`} className="return-flight-wrapper">
                  <div className="return-flight-card" onClick={() => handleFlightSelect(flight, index)}>
                    {/* Airline Logo */}
                    <div style={{ marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      {flight.airline_logo ? (
                        <img src={flight.airline_logo} alt={flight.airline || 'Airline'} className="airline-logo" style={{ marginBottom: '0' }} />
                      ) : (
                        <div className="airline-logo" style={{ fontSize: '14px', fontWeight: '600', marginBottom: '0' }}>{flight.airline || 'Unknown Airline'}</div>
                      )}
                    </div>

                    {/* Journey Container */}
                    <div className="journey-container">
                      {/* Outbound Journey */}
                      {renderJourneySection(flight.slices[0], 'Depart', flight.airline)}
                      
                      {/* Divider */}
                      <div className="journey-divider"></div>
                      
                      {/* Return Journey */}
                      {renderJourneySection(flight.slices[1], 'Return', flight.airline)}
                    </div>

                    {/* Price Row */}
                    <div className="price-row" style={{ marginTop: '16px' }}>
                      <span className="price-label">Total cost</span>
                      <span className="price-value">{flight.price || 'Price N/A'}</span>
                    </div>
                  </div>
                </div>
              );
            } else {
              // One-way flight (existing code)
              const firstSlice = flight.slices?.[0];
              const firstSegment = firstSlice?.segments?.[0];
              const lastSegment = firstSlice?.segments?.[firstSlice.segments.length - 1];
              
              const airline = flight.airline || 'Unknown Airline';
              const airlineLogo = flight.airline_logo || null;
              const airlineCode = flight.airline_code || '';
              const departure = firstSegment ? parseTime(firstSegment.departure_time) : '--:--';
              const arrival = lastSegment ? parseTime(lastSegment.arrival_time) : '--:--';
              const departureDate = firstSegment ? parseDate(firstSegment.departure_time) : '';
              const duration = firstSlice?.duration || 'N/A';
              const price = flight.price || 'Price N/A';
              const stops = calculateStops(flight.slices);
              const originCity = firstSegment?.origin_city || '';
              const destinationCity = lastSegment?.destination_city || '';
              const originCode = firstSegment?.origin || '';
              const destinationCode = lastSegment?.destination || '';

              return (
                <div key={`flight-${index}`}>
                  <div className="flight-card" onClick={() => handleFlightSelect(flight, index)}>
                    {/* Airline Logo */}
                    {airlineLogo ? (
                      <img src={airlineLogo} alt={airline} className="airline-logo" />
                    ) : (
                      <div className="airline-logo" style={{ fontSize: '14px', fontWeight: '600' }}>{airline}</div>
                    )}

                    {/* Route Section */}
                    <div className="route-section">
                      {/* Origin */}
                      <div className="airport-info">
                        <div className="airport-code">{originCode}</div>
                        <div className="airport-name">{originCity}</div>
                        <div className="flight-date">{departureDate}</div>
                        <div className="flight-time">{departure}</div>
                      </div>

                      {/* Duration */}
                      <div className="duration-section">
                        <div className="duration-badge">{duration}</div>
                      </div>

                      {/* Destination */}
                      <div className="airport-info" style={{ textAlign: 'right' }}>
                        <div className="airport-code">{destinationCode}</div>
                        <div className="airport-name">{destinationCity}</div>
                        <div className="flight-date">{departureDate}</div>
                        <div className="flight-time">{arrival}</div>
                      </div>
                    </div>

                    {/* Stops Info */}
                    <div className="info-row">
                      <span className="info-label">Stops</span>
                      <span className="info-value">{stops === 0 ? '0 stops' : `${stops} stop${stops > 1 ? 's' : ''}`}</span>
                    </div>

                    {/* Airline Code */}
                    {airlineCode && (
                      <div className="info-row">
                        <span className="info-label">{airline}</span>
                        <span className="info-value">{airlineCode}</span>
                      </div>
                    )}

                    {/* Price */}
                    <div className="price-row">
                      <span className="price-label">Total cost</span>
                      <span className="price-value">{price}</span>
                    </div>
                  </div>
                </div>
              );
            }
          })}
        </div>
      </div>
    </React.Fragment>
  );
};


interface FlightSlice {
  origin_city: string;
  destination_city: string;
  departure_time: string;
  arrival_time: string;
  fare_brand?: string;
  cabin?: string;
}

interface FlightMetadata {
  offer_id: string;
  passengers?: Array<{ given_name: string; family_name: string }>;
  email: string;
  phone_number: string;
  airline: string;
  airline_code: string;
  airline_logo: string;
  price: string;
  currency: string;
  outbound?: FlightSlice;
  return?: FlightSlice;
}

interface HotelMetadata {
  rate_id: string;
  hotel_name: string;
  room_type: string;
  check_in: string;
  check_out: string;
  guests?: Array<{ given_name: string; family_name: string }>;
}

type BookingMetadata = FlightMetadata | HotelMetadata;

interface PaymentData {
  cardNumber: string;
  expiryMonth: string;
  expiryYear: string;
  cvc: string;
  name: string;
  metadata?: BookingMetadata;
}

interface FormField {
  name: string;
  label: string;
  type: string;
  required: boolean;
  placeholder?: string;
}

interface BookingFormData {
  title?: string;
  amount?: string;
  currency?: string;
  fields?: FormField[];
}

interface BookingFormProps {
  amount?: string;
  currency?: string;
  data?: BookingFormData;
  metadata?: BookingMetadata;
}

const BookingForm: React.FC<BookingFormProps> = ({
  amount,
  currency,
  data,
  metadata
}) => {
  const stream = useStreamContext();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [paymentData, setPaymentData] = useState({
    cardNumber: '',
    expiryMonth: '',
    expiryYear: '',
    cvc: '',
    name: ''
  });
  const [cardError, setCardError] = useState('');

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleInputChange = (field: string, value: string) => {
    setPaymentData(prev => ({ ...prev, [field]: value }));
    if (field === 'cardNumber') {
      const cleanNumber = value.replace(/\s/g, '');
      setCardError(cleanNumber && !isValidCardNumber(cleanNumber) ? 'Invalid card number' : '');
    }
  };

  const handleCardNumberChange = (value: string) => {
    const formattedValue = value.replace(/\s/g, '').replace(/(\d{4})/g, '$1 ').trim();
    handleInputChange('cardNumber', formattedValue);
  };

  const handleSubmit = async () => {
    if (!stream) {
      console.error('Stream context not available');
      return;
    }

    setIsSubmitting(true);

    try {
      const cleanCardNumber = paymentData.cardNumber.replace(/\s/g, '');
      if (!isValidCardNumber(cleanCardNumber)) {
        throw new Error('Invalid card number');
      }

      const processedData: PaymentData = {
        ...paymentData,
        cardNumber: cleanCardNumber,
        expiryMonth: paymentData.expiryMonth.padStart(2, '0'),
        expiryYear: paymentData.expiryYear.length === 2 ? `20${paymentData.expiryYear}` : paymentData.expiryYear,
        cvc: paymentData.cvc,
        name: paymentData.name,
        metadata
      };

      if (!processedData.cardNumber || !processedData.expiryMonth || !processedData.expiryYear || !processedData.cvc || !processedData.name) {
        throw new Error("Please fill in all required fields");
      }

      const newHumanMessage: Message = {
        id: uuidv4(),
        type: "human",
        content:
          `
          Payment Details:
          Paying By Card
          Card Number: ${processedData.cardNumber}
          Expiry: Month: ${processedData.expiryMonth}, Year: ${processedData.expiryYear}
          CVC: ${processedData.cvc}
          Name: ${processedData.name}
          Amount: ${data?.amount || amount}
          Currency: ${data?.currency || currency}
          `
      };

      await stream.submit(
        {
          threadId: stream.threadId,
          messages: [newHumanMessage]
        },
        {
          streamMode: ["values"],
          optimisticValues: (prev) => ({
            ...prev,
            messages: [...(prev.messages ?? []), newHumanMessage]
          })
        }
      );

    } catch (error) {
      console.error('Payment submission error:', error);
      alert(error instanceof Error ? error.message : "An unknown error occurred");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!mounted) {
    return null;
  }

  const displayAmount = data?.amount || amount;
  const displayCurrency = data?.currency || currency;

  // Modern styled container
  const containerStyle: React.CSSProperties = {
    maxWidth: '500px',
    width: '100%',
    background: 'rgba(255, 255, 255, 0.95)',
    backdropFilter: 'blur(20px)',
    borderRadius: '24px',
    boxShadow: '0 20px 40px rgba(0, 0, 0, 0.1)',
    overflow: 'hidden',
    border: '1px solid rgba(255, 255, 255, 0.2)',
    margin: '0 auto',
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
  };

  const darkContainerStyle: React.CSSProperties = {
    background: 'rgba(15, 23, 42, 0.95)',
    boxShadow: '0 20px 40px rgba(0, 0, 0, 0.6)',
    border: '1px solid rgba(148, 163, 184, 0.2)'
  };

  // Header styles
  const headerStyle: React.CSSProperties = {
    background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
    padding: '30px',
    textAlign: 'center',
    color: 'white',
    position: 'relative',
    overflow: 'hidden'
  };

  const headerTitleStyle: React.CSSProperties = {
    fontSize: '24px',
    fontWeight: '700',
    marginBottom: '8px',
    position: 'relative',
    zIndex: 1,
    margin: '0 0 8px 0'
  };

  const headerSubtitleStyle: React.CSSProperties = {
    fontSize: '14px',
    opacity: 0.9,
    position: 'relative',
    zIndex: 1,
    margin: 0
  };

  // Summary styles
  const summaryStyle: React.CSSProperties = {
    padding: '30px',
    borderBottom: '1px solid #e5e7eb'
  };

  const darkSummaryStyle: React.CSSProperties = {
    borderBottom: '1px solid #475569'
  };

  const summaryTitleStyle: React.CSSProperties = {
    fontSize: '20px',
    fontWeight: '700',
    color: '#1f2937',
    marginBottom: '20px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    margin: '0 0 20px 0'
  };

  const darkSummaryTitleStyle: React.CSSProperties = {
    color: '#f8fafc'
  };

  const flightInfoStyle: React.CSSProperties = {
    background: 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)',
    borderRadius: '16px',
    padding: '20px',
    marginBottom: '20px',
    border: '1px solid #cbd5e1'
  };

  const darkFlightInfoStyle: React.CSSProperties = {
    background: 'linear-gradient(135deg, #1e293b 0%, #334155 100%)',
    border: '1px solid #475569'
  };

  const passengerInfoStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: '16px'
  };

  const passengerAvatarStyle: React.CSSProperties = {
    width: '40px',
    height: '40px',
    background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'white',
    fontWeight: '700',
    fontSize: '16px'
  };

  const passengerNameStyle: React.CSSProperties = {
    fontWeight: '600',
    color: '#1f2937',
    fontSize: '16px'
  };

  const darkPassengerNameStyle: React.CSSProperties = {
    color: '#f8fafc'
  };

  const airlineInfoStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    marginBottom: '20px'
  };

  const airlineLogoStyle: React.CSSProperties = {
    width: '50px',
    height: '30px',
    background: '#ffffff',
    borderRadius: '8px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: '1px solid #e5e7eb',
    fontWeight: '700',
    color: '#4f46e5',
    fontSize: '12px'
  };

  const darkAirlineLogoStyle: React.CSSProperties = {
    background: '#0f172a',
    border: '1px solid #475569'
  };

  const airlineNameStyle: React.CSSProperties = {
    fontWeight: '600',
    color: '#1f2937',
    fontSize: '16px'
  };

  const darkAirlineNameStyle: React.CSSProperties = {
    color: '#f8fafc'
  };

  const totalAmountStyle: React.CSSProperties = {
    background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
    color: 'white',
    padding: '16px',
    borderRadius: '12px',
    textAlign: 'center',
    fontSize: '20px',
    fontWeight: '700',
    marginTop: '20px',
    boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)'
  };

  // Form styles
  const paymentFormStyle: React.CSSProperties = {
    padding: '30px'
  };

  const formTitleStyle: React.CSSProperties = {
    fontSize: '18px',
    fontWeight: '700',
    color: '#1f2937',
    marginBottom: '20px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    margin: '0 0 20px 0'
  };

  const darkFormTitleStyle: React.CSSProperties = {
    color: '#f8fafc'
  };

  const formGroupStyle: React.CSSProperties = {
    marginBottom: '20px'
  };

  const formLabelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '14px',
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: '8px'
  };

  const darkFormLabelStyle: React.CSSProperties = {
    color: '#f8fafc'
  };

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '14px 16px',
    border: '2px solid #e5e7eb',
    borderRadius: '12px',
    fontSize: '16px',
    backgroundColor: '#ffffff',
    color: '#1f2937',
    transition: 'all 0.3s ease',
    boxSizing: 'border-box',
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
  };

  const darkInputStyle: React.CSSProperties = {
    border: '2px solid #475569',
    backgroundColor: '#1e293b',
    color: '#f8fafc'
  };

  const cardRowStyle: React.CSSProperties = {
    display: 'flex',
    gap: '12px',
    alignItems: 'center'
  };

  const cardLogosStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '8px'
  };

  const cardLogoStyle: React.CSSProperties = {
    width: '32px',
    height: '20px',
    borderRadius: '4px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '10px',
    fontWeight: '700',
    border: '1px solid #e5e7eb'
  };

  const visaLogoStyle: React.CSSProperties = {
    background: 'linear-gradient(135deg, #1a1f71 0%, #0f4c81 100%)',
    color: 'white',
    border: 'none'
  };

  const mastercardLogoStyle: React.CSSProperties = {
    background: 'linear-gradient(135deg, #eb001b 0%, #f79e1b 100%)',
    color: 'white',
    border: 'none'
  };

  const expiryCvcStyle: React.CSSProperties = {
    display: 'flex',
    gap: '12px'
  };

  const expiryGroupStyle: React.CSSProperties = {
    display: 'flex',
    gap: '8px',
    flex: 1
  };

  const cvcGroupStyle: React.CSSProperties = {
    flex: 1
  };

  const buttonStyle: React.CSSProperties = {
    width: '100%',
    background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
    color: 'white',
    border: 'none',
    borderRadius: '16px',
    padding: '16px',
    fontSize: '18px',
    fontWeight: '700',
    cursor: 'pointer',
    transition: 'all 0.3s ease',
    boxShadow: '0 4px 12px rgba(79, 70, 229, 0.3)',
    position: 'relative',
    overflow: 'hidden',
    opacity: isSubmitting || (stream && stream.isLoading) ? 0.5 : 1
  };

  const requiredStyle: React.CSSProperties = {
    color: '#ef4444'
  };

  const errorStyle: React.CSSProperties = {
    color: '#ef4444',
    fontSize: '12px',
    marginTop: '5px'
  };

  const textStyle: React.CSSProperties = {
    color: '#6b7280',
    fontWeight: '500'
  };

  const darkTextStyle: React.CSSProperties = {
    color: '#cbd5e1'
  };

  const valueStyle: React.CSSProperties = {
    color: '#1f2937',
    fontWeight: '600'
  };

  const darkValueStyle: React.CSSProperties = {
    color: '#f8fafc'
  };

  return (
    <div style={containerStyle} className="dark:bg-slate-900/95 dark:shadow-black/60 dark:border-slate-400/20">
      <style>
        {`
          @media (prefers-color-scheme: dark) {
            .booking-form-container {
              background: rgba(15, 23, 42, 0.95) !important;
              box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6) !important;
              border: 1px solid rgba(148, 163, 184, 0.2) !important;
            }
          }
        `}
      </style>
      
      <div className="booking-form-container">
        {/* Header */}
        <div style={headerStyle}>
          <h1 style={headerTitleStyle}>Booking</h1>
          <p style={headerSubtitleStyle}>Complete your reservation</p>
        </div>

        {/* Booking Summary */}
        <div style={{...summaryStyle, ...darkSummaryStyle}} className="dark:border-slate-600">
          <h3 style={{color: 'white'}} className="text-xl font-bold mb-5 flex items-center gap-2.5">
            ✈️ Booking Summary
          </h3>
          
          <div style={flightInfoStyle} className="dark:bg-gradient-to-br dark:from-slate-700 dark:to-slate-600 dark:border-slate-500">
            {"hotel_name" in (metadata || {}) && (
              <>
                <div style={passengerInfoStyle}>
                  <div style={passengerAvatarStyle}>
                    {metadata.guests?.[0]?.given_name?.[0] || 'G'}
                    {metadata.guests?.[0]?.family_name?.[0] || 'G'}
                  </div>
                  <div style={passengerNameStyle} className="dark:text-slate-50">
                    {metadata.guests?.map((g) => `${g.given_name} ${g.family_name}`).join(', ')}
                  </div>
                </div>
                
                <div style={airlineInfoStyle}>
                  <div style={airlineLogoStyle} className="dark:bg-slate-900 dark:border-slate-500">🏨</div>
                  <div style={airlineNameStyle} className="dark:text-slate-50">{metadata.hotel_name}</div>
                </div>

                <p style={textStyle} className="dark:text-slate-300">
                  <span style={{fontWeight: '500'}}>Room:</span> <span style={valueStyle} className="dark:text-slate-50">{metadata.room_type}</span>
                </p>
                <p style={textStyle} className="dark:text-slate-300">
                  <span style={{fontWeight: '500'}}>Stay:</span> <span style={valueStyle} className="dark:text-slate-50">{metadata.check_in} → {metadata.check_out}</span>
                </p>
              </>
            )}
            
            {metadata && "outbound" in metadata && (() => {
              const flightMetadata = metadata as FlightMetadata;
              return (
                <>
                  <div style={passengerInfoStyle}>
                    <div style={passengerAvatarStyle}>
                      {metadata.passengers?.[0]?.given_name?.[0] || 'S'}
                      {metadata.passengers?.[0]?.family_name?.[0] || 'K'}
                    </div>
                    <div style={passengerNameStyle} className="dark:text-slate-50">
                      {metadata.passengers?.map((g) => `${g.given_name} ${g.family_name}`).join(', ')}
                    </div>
                  </div>

                  <div style={airlineInfoStyle}>
                    {flightMetadata.airline_logo && (
                      <img src={flightMetadata.airline_logo} alt="Airline logo" style={{ height: '20px' }} />
                    )}
                    <div style={airlineLogoStyle} className="dark:bg-slate-900 dark:border-slate-500">{flightMetadata.airline_code}</div>
                    <div style={airlineNameStyle} className="dark:text-slate-50">{flightMetadata.airline}</div>
                  </div>           
                
                {metadata.outbound && (
                  <>
                    <p style={textStyle} className="dark:text-slate-300">
                      <span style={{fontWeight: '500'}}>Outbound:</span>{" "}
                      <span style={valueStyle} className="dark:text-slate-50">{metadata.outbound.origin_city} → {metadata.outbound.destination_city}</span>
                    </p>
                    <p style={textStyle} className="dark:text-slate-300">
                      <span style={{fontWeight: '500'}}>Departure:</span> <span style={valueStyle} className="dark:text-slate-50">{metadata.outbound.departure_time}</span>
                    </p>
                    <p style={textStyle} className="dark:text-slate-300">
                      <span style={{fontWeight: '500'}}>Arrival:</span> <span style={valueStyle} className="dark:text-slate-50">{metadata.outbound.arrival_time}</span>
                    </p>
                    {metadata.outbound.fare_brand && (
                      <p style={textStyle} className="dark:text-slate-300">
                        <span style={{fontWeight: '500'}}>Fare Brand:</span> <span style={valueStyle} className="dark:text-slate-50">{metadata.outbound.fare_brand}</span>
                      </p>
                    )}
                    {metadata.outbound.cabin && (
                      <p style={textStyle} className="dark:text-slate-300">
                        <span style={{fontWeight: '500'}}>Cabin:</span> <span style={valueStyle} className="dark:text-slate-50">{metadata.outbound.cabin}</span>
                      </p>
                    )}
                  </>
                )}
                
                {metadata.return && (
                  <>
                    <p style={textStyle} className="dark:text-slate-300">
                      <span style={{fontWeight: '500'}}>Return:</span>{" "}
                      <span style={valueStyle} className="dark:text-slate-50">{metadata.return.origin_city} → {metadata.return.destination_city}</span>
                    </p>
                    <p style={textStyle} className="dark:text-slate-300">
                      <span style={{fontWeight: '500'}}>Departure:</span> <span style={valueStyle} className="dark:text-slate-50">{metadata.return.departure_time}</span>
                    </p>
                    <p style={textStyle} className="dark:text-slate-300">
                      <span style={{fontWeight: '500'}}>Arrival:</span> <span style={valueStyle} className="dark:text-slate-50">{metadata.return.arrival_time}</span>
                    </p>
                    {metadata.return.fare_brand && (
                      <p style={textStyle} className="dark:text-slate-300">
                        <span style={{fontWeight: '500'}}>Fare Brand:</span> <span style={valueStyle} className="dark:text-slate-50">{metadata.return.fare_brand}</span>
                      </p>
                    )}
                    {metadata.return.cabin && (
                      <p style={textStyle} className="dark:text-slate-300">
                        <span style={{fontWeight: '500'}}>Cabin:</span> <span style={valueStyle} className="dark:text-slate-50">{metadata.return.cabin}</span>
                      </p>
                    )}
                  </>
                )}
              </>
            );})()}
            
            {displayAmount && displayCurrency && (
              <div style={totalAmountStyle}>
                Total: {displayAmount} {displayCurrency}
              </div>
            )}
          </div>
        </div>

        {/* Payment Form */}
        <div style={paymentFormStyle}>
          <h3 style={{color: 'white'}} className="text-xl font-bold mb-5 flex items-center gap-2.5">
            💳 Payment Details
          </h3>
          
          <div style={formGroupStyle}>
            <label style={{color: 'white'}} className="text-xl font-bold mb-5 flex items-center gap-2.5">
              Cardholder Name<span style={requiredStyle}>*</span>
            </label>
            <input
              type="text"
              placeholder="e.g. Jane Appleseed"
              style={inputStyle}
              className="dark:border-slate-500 dark:bg-slate-700 dark:text-slate-50 dark:placeholder-slate-400"
              value={paymentData.name}
              onChange={(e) => handleInputChange('name', e.target.value)}
              onFocus={(e) => {
                e.target.style.borderColor = '#4f46e5';
                e.target.style.boxShadow = '0 0 0 3px rgba(79, 70, 229, 0.2)';
                e.target.style.transform = 'translateY(-1px)';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = '#e5e7eb';
                e.target.style.boxShadow = 'none';
                e.target.style.transform = 'translateY(0)';
              }}
              required
            />
          </div>

          <div style={formGroupStyle}>
            <label style={{color: 'white'}} className="text-xl font-bold mb-5 flex items-center gap-2.5">
              Card Number<span style={requiredStyle}>*</span>
            </label>
            <div style={cardRowStyle}>
              <input
                type="text"
                placeholder="e.g. 4242 4242 4242 4242"
                style={{...inputStyle, flex: 1}}
                className="dark:border-slate-500 dark:bg-slate-700 dark:text-slate-50 dark:placeholder-slate-400"
                value={paymentData.cardNumber}
                onChange={(e) => handleCardNumberChange(e.target.value)}
                maxLength={19}
                onFocus={(e) => {
                  e.target.style.borderColor = '#4f46e5';
                  e.target.style.boxShadow = '0 0 0 3px rgba(79, 70, 229, 0.2)';
                  e.target.style.transform = 'translateY(-1px)';
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = '#e5e7eb';
                  e.target.style.boxShadow = 'none';
                  e.target.style.transform = 'translateY(0)';
                }}
                required
              />
              <div style={cardLogosStyle}>
                <img
                  src="https://upload.wikimedia.org/wikipedia/commons/4/41/Visa_Logo.png"
                  alt="Visa"
                  style={{ height: '20px', width: 'auto' }}
                />
                <img
                  src="https://upload.wikimedia.org/wikipedia/commons/2/2a/Mastercard-logo.svg"
                  alt="Mastercard"
                  style={{ height: '20px', width: 'auto' }}
                />
              </div>
            </div>
            {cardError && (
              <p style={errorStyle}>{cardError}</p>
            )}
          </div>

          <div style={formGroupStyle}>
            <label style={{color: 'white'}} className="text-xl font-bold mb-5 flex items-center gap-2.5">
              EXP. DATE (MM/YY) / CVC<span style={requiredStyle}>*</span>
            </label>
            <div style={expiryCvcStyle}>
              <div style={expiryGroupStyle}>
                <input
                  type="text"
                  placeholder="MM"
                  style={inputStyle}
                  className="dark:border-slate-500 dark:bg-slate-700 dark:text-slate-50 dark:placeholder-slate-400"
                  value={paymentData.expiryMonth}
                  onChange={(e) => handleInputChange('expiryMonth', e.target.value)}
                  maxLength={2}
                  onFocus={(e) => {
                    e.target.style.borderColor = '#4f46e5';
                    e.target.style.boxShadow = '0 0 0 3px rgba(79, 70, 229, 0.2)';
                    e.target.style.transform = 'translateY(-1px)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = '#e5e7eb';
                    e.target.style.boxShadow = 'none';
                    e.target.style.transform = 'translateY(0)';
                  }}
                  required
                />
                <input
                  type="text"
                  placeholder="YY"
                  style={inputStyle}
                  className="dark:border-slate-500 dark:bg-slate-700 dark:text-slate-50 dark:placeholder-slate-400"
                  value={paymentData.expiryYear}
                  onChange={(e) => handleInputChange('expiryYear', e.target.value)}
                  maxLength={2}
                  onFocus={(e) => {
                    e.target.style.borderColor = '#4f46e5';
                    e.target.style.boxShadow = '0 0 0 3px rgba(79, 70, 229, 0.2)';
                    e.target.style.transform = 'translateY(-1px)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = '#e5e7eb';
                    e.target.style.boxShadow = 'none';
                    e.target.style.transform = 'translateY(0)';
                  }}
                  required
                />
              </div>
              <div style={cvcGroupStyle}>
                <input
                  type="text"
                  placeholder="e.g. 123"
                  style={inputStyle}
                  className="dark:border-slate-500 dark:bg-slate-700 dark:text-slate-50 dark:placeholder-slate-400"
                  value={paymentData.cvc}
                  onChange={(e) => handleInputChange('cvc', e.target.value)}
                  maxLength={4}
                  onFocus={(e) => {
                    e.target.style.borderColor = '#4f46e5';
                    e.target.style.boxShadow = '0 0 0 3px rgba(79, 70, 229, 0.2)';
                    e.target.style.transform = 'translateY(-1px)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = '#e5e7eb';
                    e.target.style.boxShadow = 'none';
                    e.target.style.transform = 'translateY(0)';
                  }}
                  required
                />
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={handleSubmit}
            style={buttonStyle}
            disabled={isSubmitting || (stream && stream.isLoading) || !!cardError}
            onMouseOver={(e) => {
              if (!isSubmitting && (!stream || !stream.isLoading) && !cardError) {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow = '0 8px 24px rgba(79, 70, 229, 0.4)';
              }
            }}
            onMouseOut={(e) => {
              if (!isSubmitting && (!stream || !stream.isLoading) && !cardError) {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = '0 4px 12px rgba(79, 70, 229, 0.3)';
              }
            }}
          >
            {isSubmitting ? (
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                <span style={{ 
                  display: 'inline-block',
                  width: '16px',
                  height: '16px',
                  border: '2px solid rgba(255,255,255,0.3)',
                  borderTop: '2px solid white',
                  borderRadius: '50%',
                  animation: 'spin 1s linear infinite'
                }} />
                Processing Payment...
              </span>
            ) : (
              'Confirm Booking'
            )}
          </button>
        </div>
      </div>
      
      <style>
        {`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}
      </style>
    </div>
    );
};

export default {
  hotelResults: HotelResultCard,
  flightResults: FlightResultCard,
  paymentForm: BookingForm
};

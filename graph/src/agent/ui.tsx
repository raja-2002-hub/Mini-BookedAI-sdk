import React, { useState } from 'react';
import { v4 as uuidv4 } from "uuid";
import { useStreamContext } from "@langchain/langgraph-sdk/react-ui";
import { Message } from "@langchain/langgraph-sdk";

// Hotel search result component
const HotelResultCard = ({ hotels }) => {
  if (!hotels.length) return null;

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
    <>
      <style>{scopedStyles}</style>
      <div id="hotel-cards-scope">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {hotels.map((hotel, index) => (
            <div key={index} className="w-full"> 
              <div 
                className="relative w-full aspect-[3/4] rounded-xl overflow-hidden shadow-lg"
                style={{ backgroundImage: `url(${hotel.image})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
              >
                <div className="absolute inset-0 bg-black/40" />
                <div className="relative h-full flex flex-col justify-between p-3 text-white">
                  <div>
                    <h1 className="text-sm font-bold leading-tight">{hotel.name}</h1>
                    <div className="flex flex-wrap items-center gap-1 mt-1">
                      <span className="text-xs truncate">{hotel.location}</span>
                      <span className="inline-flex items-center bg-white/20 backdrop-blur-sm px-1.5 py-0.5 rounded-full text-xs font-bold">
                        ⭐ {hotel.rating}
                      </span>
                    </div>
                  </div>
                  <div className="mt-auto">
                    <div className="text-base font-bold mb-1">{hotel.price}</div>
                    <div className="flex flex-wrap gap-1">
                      {hotel.amenities.slice(0, 3).map((amenity, i) => (
                        <span key={i} className="bg-white/20 backdrop-blur-sm px-1 py-0 rounded-full text-2xs font-medium">
                          {amenity}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
};  
  // Flight search result component  
  const FlightResultCard = (props: {
    flights: Array<{
      airline: string;
      departure: string;
      arrival: string;
      duration: string;
      price: string;
      stops: number;
    }>;
  }) => {
    return (
      <div className="space-y-3">
        {props.flights.map((flight, index) => (
          <div key={index} className="border rounded-lg p-4 bg-white shadow-sm">
            <div className="flex justify-between items-center">
              <div className="flex-1">
                <div className="font-semibold">{flight.airline}</div>
                <div className="flex items-center gap-4 mt-2">
                  <span className="text-lg font-mono">{flight.departure}</span>
                  <span className="text-gray-400">→</span>
                  <span className="text-lg font-mono">{flight.arrival}</span>
                  <span className="text-sm text-gray-600">({flight.duration})</span>
                  {flight.stops === 0 ? (
                    <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded">
                      Non-stop
                    </span>
                  ) : (
                    <span className="px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded">
                      {flight.stops} stop{flight.stops > 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-blue-600">{flight.price}</div>
                <button className="mt-2 bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
                  Select
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  interface BookingMetadata {   
    guests?: Array<{
      given_name: string;
      family_name: string;
    }>;
  }
  
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
    const [paymentData, setPaymentData] = useState({
      cardNumber: '',
      expiryDate: '',
      cvc: '',
      name: ''
    });
  
    const handleInputChange = (field: string, value: string) => {
      setPaymentData(prev => ({ ...prev, [field]: value }));
    };
  
    const handleCardNumberChange = (value: string) => {
      const formattedValue = value.replace(/\s/g, '').replace(/(\d{4})/g, '$1 ').trim();
      handleInputChange('cardNumber', formattedValue);
    };
  
    const handleExpiryDateChange = (value: string) => {
      const formattedValue = value.replace(/\D/g, '').replace(/(\d{2})(\d{0,2})/, '$1/$2').trim();
      handleInputChange('expiryDate', formattedValue);
    };
  
    const handleSubmit = async () => {
      setIsSubmitting(true);
    
      try {
        let expiryMonth = '';
        let expiryYear = '';
    
        if (paymentData.expiryDate) {
          const [month, year] = paymentData.expiryDate.split('/').filter(Boolean);
          if (month && year) {
            expiryMonth = month.padStart(2, '0');
            expiryYear = year.length === 2 ? `20${year}` : year;
          }
        }
    
        const processedData: PaymentData = {
          ...paymentData,
          cardNumber: paymentData.cardNumber.replace(/\s/g, ''),
          expiryMonth,
          expiryYear,
          metadata
        };
    
        // Validation
        if (!processedData.cardNumber || !processedData.expiryMonth || !processedData.expiryYear || !processedData.cvc || !processedData.name) {
          throw new Error("Please fill in all required fields");
        }
    
        // Human confirmation message for chat history
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
              messages: [...(prev.messages ?? []), newHumanMessage] // Show human message immediately
            })
          }
        );
    
      } catch (error) {
        alert(error instanceof Error ? error.message : "An unknown error occurred");
      } finally {
        setIsSubmitting(false);
      }
    };
  
    const displayAmount = data?.amount || amount;
    const displayCurrency = data?.currency || currency;
    const formTitle = data?.title || "Complete Payment";
  
    return (
      <div className="max-w-md mx-auto bg-white rounded-lg shadow-md p-6">
        {/* Booking Summary */}
        {metadata && (
          <div className="mb-6 bg-gray-50 p-4 rounded-md border border-gray-200">
            <h3 className="font-bold text-lg mb-2 text-gray-800">Booking Summary</h3>          
            {metadata.guests && (
              <p className="text-sm text-gray-700">
                <span className="font-medium">Guests:</span> {metadata.guests.map((g) => `${g.given_name} ${g.family_name}`).join(', ')}
              </p>
            )}
          </div>
        )}
  
        {/* Payment Amount Display */}
        {displayAmount && displayCurrency && (
          <div className="bg-blue-50 border border-blue-200 rounded-md p-4 mb-6 text-center">
            <p className="text-sm text-blue-800 mb-1">Total Amount</p>
            <p className="text-xl font-medium text-blue-800">
              {displayAmount} {displayCurrency}
            </p>
          </div>
        )}
  
        {/* Payment Form */}
        <div className="space-y-4">
          {data?.fields ? (
            data.fields.map(field => (
              <div key={field.name}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {field.label}
                  {field.required && <span className="text-red-500">*</span>}
                </label>
                <input
                  type={field.type}
                  placeholder={field.placeholder}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={paymentData[field.name as keyof typeof paymentData] || ''}
                  onChange={(e) => handleInputChange(field.name, e.target.value)}
                  required={field.required}
                />
              </div>
            ))
          ) : (
            <>
              {/* Card Number */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Card Number
                </label>
                <input
                  type="text"
                  placeholder="1234 5678 9012 3456"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={paymentData.cardNumber}
                  onChange={(e) => handleCardNumberChange(e.target.value)}
                  maxLength={19}
                  required
                />
              </div>
  
              <div className="grid grid-cols-2 gap-4">
                {/* Expiry Date */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Expiry Date
                  </label>
                  <input
                    type="text"
                    placeholder="MM/YY"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={paymentData.expiryDate}
                    onChange={(e) => handleExpiryDateChange(e.target.value)}
                    maxLength={5}
                    required
                  />
                </div>
  
                {/* CVC */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    CVC
                  </label>
                  <input
                    type="text"
                    placeholder="123"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={paymentData.cvc}
                    onChange={(e) => handleInputChange('cvc', e.target.value)}
                    maxLength={4}
                    required
                  />
                </div>
              </div>
  
              {/* Cardholder Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Cardholder Name
                </label>
                <input
                  type="text"
                  placeholder="John Smith"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={paymentData.name}
                  onChange={(e) => handleInputChange('name', e.target.value)}
                  required
                />
              </div>
            </>
          )}
        </div>
  
        {/* Submit Button */}
        <button
          type="button"
          onClick={handleSubmit}
          className="w-full mt-6 bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-md transition duration-150 ease-in-out disabled:opacity-50"
          disabled={isSubmitting || stream.isLoading}
        >
          {isSubmitting ? 'Processing Payment...' : 'Pay Now'}
        </button>
      </div>
    );
  };
  
  export default {
    hotelResults: HotelResultCard,
    flightResults: FlightResultCard,
    paymentForm: BookingForm
  };
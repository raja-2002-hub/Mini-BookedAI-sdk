import React, {
  useMemo,
  useState,
  useSyncExternalStore,
  useEffect,
  useRef,
} from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

/* -----------------------------
   Constants
------------------------------ */
const OFFER_EXPIRY_MINUTES = 30;

/* -----------------------------
   Host globals (window.openai.*)
------------------------------ */
const SET_GLOBALS_EVENT_TYPE = "openai:set_globals";

function useOpenAiGlobal(key) {
  return useSyncExternalStore(
    (onChange) => {
      const handler = (ev) => {
        if (ev?.detail?.globals?.[key] !== undefined) onChange();
      };
      window.addEventListener(SET_GLOBALS_EVENT_TYPE, handler, { passive: true });
      return () => window.removeEventListener(SET_GLOBALS_EVENT_TYPE, handler);
    },
    () => (window.openai ? window.openai[key] : undefined),
    () => undefined
  );
}

function hostCaps() {
  const oa = window.openai;
  return {
    hasFollowUp: !!oa?.sendFollowUpMessage,
    hasAppendUser: !!oa?.appendUserMessage,
    hasSendMessage: !!oa?.sendMessage,
  };
}

async function sendFollowUpMessage(prompt) {
  const oa = window.openai;
  try { if (oa?.sendFollowUpMessage) { await oa.sendFollowUpMessage({ prompt }); return; } } catch (e) { console.warn("sendFollowUpMessage failed", e); }
  try { if (oa?.appendUserMessage) { await oa.appendUserMessage(prompt); return; } } catch (e) { console.warn("appendUserMessage failed", e); }
  try { if (oa?.sendMessage) { await oa.sendMessage({ role: "user", content: prompt }); return; } } catch (e) { console.warn("sendMessage failed", e); }
  try { window.dispatchEvent(new CustomEvent("openai:append_user_message", { detail: { text: prompt } })); return; } catch (e) { console.warn("dispatchEvent fallback failed", e); }
  try { window.parent?.postMessage({ type: "openai:append_user_message", text: prompt }, "*"); return; } catch (e) { console.warn("postMessage fallback failed", e); }
  console.log("[fallback] would send follow-up message:", prompt);
}

async function blockNextFlightSearchOnServer() {
  try {
    await fetch("http://localhost:8000/widget/flight/block_next", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  } catch (e) {
    console.warn("Failed to block next flight search:", e);
  }
}

/* -----------------------------------------
   Helpers: map flights
------------------------------------------ */
function mapFlights(output) {
  const src =
    (output && (output.flights || output.results)) ||
    (Array.isArray(output?.data) ? output.data : []);

  if (!Array.isArray(src)) return [];

  return src.map((f, i) => {
    let priceValue = f.price || f.total_amount || f.total_price || f.amount || f.fare || "";
    if (typeof priceValue === "number") priceValue = `$${priceValue}`;
    if (typeof priceValue === "object" && priceValue !== null) {
      const amt = priceValue.amount || priceValue.value || priceValue.total || "";
      const curr = priceValue.currency || "$";
      priceValue = amt ? `${curr}${amt}` : "";
    }

    let taxValue = f.tax || f.tax_amount || f.taxes || "";
    if (typeof taxValue === "number") taxValue = `incl. $${taxValue} tax`;

    // Parse stops - could be number or string
    let stopsCount = f.stops || f.stop_count || f.connections || 0;
    if (typeof stopsCount === "string") {
      const match = stopsCount.match(/(\d+)/);
      stopsCount = match ? parseInt(match[1], 10) : 0;
    }

    // Parse stop locations/layovers
    let stopLocations = f.stopLocations || f.stop_locations || f.layovers || f.connections_details || [];
    if (typeof stopLocations === "string") {
      stopLocations = stopLocations.split(",").map(s => s.trim()).filter(Boolean);
    }

    return {
      id: f.id || f.offer_id || `flight_${i}`,
      airlineShort: f.airlineShort || f.airline || f.owner || "",
      airlineLogo: f.airlineLogo || f.logo || (f.marketing_carrier && (f.marketing_carrier.logo || f.marketing_carrier.logo_url)) || "",
      weekday: f.weekday || "",
      date: f.date || "",
      depart: f.depart || f.departure_time || "",
      arrive: f.arrive || f.arrival_time || "",
      returnDepart: f.returnDepart || f.return_depart || f.return_departure_time || "",
      returnArrive: f.returnArrive || f.return_arrive || f.return_arrival_time || "",
      returnRoute: f.returnRoute || f.return_route || "",
      returnDate: f.returnDate || f.return_date || "",
      returnWeekday: f.returnWeekday || f.return_weekday || "",
      route: f.route || "",
      duration: f.duration || "",
      highlight: !!f.highlight || i === 0,
      price: priceValue,
      tax: taxValue,
      flightNumber: f.flightNumber || f.flight_number || f.flight_no || "",
      stops: stopsCount,
      stopLocations: stopLocations,
      cabin: f.cabin || f.cabin_class || "Economy",
      baggage: f.baggage || f.included_baggage || "1 checked, 1 carry-on",
      refunds: f.refunds || f.refundable || f.cancellation_policy || "N/A",
    };
  });
}

/* -----------------------------------------
   Timer Hook
------------------------------------------ */
function useCountdown(startTime, expiryMinutes = OFFER_EXPIRY_MINUTES) {
  const [remainingSeconds, setRemainingSeconds] = useState(() => {
    if (!startTime) return expiryMinutes * 60;
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    return Math.max(0, expiryMinutes * 60 - elapsed);
  });

  useEffect(() => {
    if (remainingSeconds <= 0) return;
    const timer = setInterval(() => {
      setRemainingSeconds((prev) => {
        if (prev <= 1) { clearInterval(timer); return 0; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [remainingSeconds > 0]);

  const isExpired = remainingSeconds <= 0;
  const formatTime = () => {
    if (isExpired) return "Expired";
    const minutes = Math.floor(remainingSeconds / 60);
    const seconds = remainingSeconds % 60;
    if (minutes >= 60) {
      const hours = Math.floor(minutes / 60);
      const mins = minutes % 60;
      return `${hours}h ${mins}m`;
    }
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  };

  return { remainingSeconds, isExpired, timeDisplay: formatTime() };
}

/* -----------------------------------------
   Formatting helpers
------------------------------------------ */
function formatDateForDisplay(weekday, dateStr) {
  let wk = weekday || "";
  let formatted = dateStr || "";
  formatted = formatted.replace(/,?\s*\d{4}\s*$/, "").trim();

  const dayMonthMatch = formatted.match(/^(\d{1,2})\s+([A-Za-z]+)$/);
  if (dayMonthMatch) {
    formatted = `${dayMonthMatch[2]} ${parseInt(dayMonthMatch[1], 10)}`;
  }

  const monthDayMatch = formatted.match(/^([A-Za-z]+)\s+(\d{1,2})$/);
  if (monthDayMatch) {
    formatted = `${monthDayMatch[1]} ${parseInt(monthDayMatch[2], 10)}`;
  }

  if (!wk && formatted.includes(",")) {
    const parts = formatted.split(",");
    if (parts[0].trim().length <= 3) {
      wk = parts[0].trim();
      formatted = parts.slice(1).join(",").trim();
      const innerMatch = formatted.match(/^([A-Za-z]+)\s+(\d{1,2})$/);
      if (innerMatch) {
        formatted = `${innerMatch[1]} ${parseInt(innerMatch[2], 10)}`;
      }
    }
  }

  return { weekday: wk, date: formatted };
}

function formatRoute(route) {
  if (!route) return "";
  let r = String(route).trim().toUpperCase();
  r = r.replace(/\s*(–|—|-|->|=>|→)\s*/g, " → ");
  r = r.replace(/\s+/g, " ").trim();
  return r;
}

function formatTime(timeStr) {
  if (!timeStr) return "";
  const s = String(timeStr).trim();
  if (s.includes("-")) {
    const [start, end] = s.split("-").map((p) => p.trim());
    const fs = formatTime(start);
    const fe = formatTime(end);
    if (fs && fe) return `${fs} - ${fe}`;
    return s;
  }
  const m = s.match(/^(\d{1,2}):(\d{2})(?:\s*(AM|PM|am|pm))?$/);
  if (!m) return s.replace(/\s*(AM|PM|am|pm)\s*$/i, "");
  let [, hStr, mStr, ampm] = m;
  let h = parseInt(hStr, 10);
  if (ampm) {
    const upper = ampm.toUpperCase();
    if (upper === "AM" && h === 12) h = 0;
    else if (upper === "PM" && h !== 12) h += 12;
  }
  return `${String(h).padStart(2, "0")}:${mStr}`;
}

function formatStops(stops) {
  if (!stops || stops === 0) return "Non-stop";
  return `${stops} Stop${stops > 1 ? "s" : ""}`;
}

/* --------------- UI Components --------------- */

function TimerPill({ timeDisplay, isExpired }) {
  return (
    <span className={`fc-pill ${isExpired ? "fc-pill--expired" : "fc-pill--time"}`}>
      {timeDisplay}
    </span>
  );
}

function BestPill() {
  return <span className="fc-pill fc-pill--best">Best</span>;
}

function StopsPill({ stops }) {
  if (!stops || stops === 0) return null;
  return <span className="fc-pill fc-pill--stops">{formatStops(stops)}</span>;
}

function AirlineLogo({ airline, logo }) {
  if (logo) {
    return <img src={logo} alt={airline || "Airline"} className="fc-airline-logo" referrerPolicy="no-referrer" />;
  }
  if (airline) {
    return <div className="fc-airline-name">{airline}</div>;
  }
  return <div className="fc-airline-logo fc-airline-logo--placeholder" />;
}

function DateDisplay({ weekday, date }) {
  const { weekday: wk, date: dt } = formatDateForDisplay(weekday, date);
  return (
    <div className="fc-date-text">
      {wk && <span className="fc-weekday">{wk},</span>}
      {dt && <span className="fc-date"> {dt}</span>}
    </div>
  );
}

function TimeRange({ depart, arrive }) {
  const d = formatTime(depart);
  const a = formatTime(arrive);
  if (d && a) return <span className="fc-time-range">{d} - {a}</span>;
  return <span className="fc-time-range">{d || a || "—"}</span>;
}

function RouteDisplay({ route }) {
  const formatted = formatRoute(route);
  if (!formatted) return null;
  const parts = formatted.split("→").map(s => s.trim());
  if (parts.length === 2) {
    return (
      <div className="fc-route">
        {parts[0]}<span className="fc-route-arrow">→</span>{parts[1]}
      </div>
    );
  }
  return <div className="fc-route">{formatted}</div>;
}

function MoreInfoButton({ open, onToggle }) {
  return (
    <button className="fc-more-info" onClick={onToggle} type="button">
      {open ? "Less Info" : "More Info"}
      <svg 
        className={`fc-more-info-chevron ${open ? "fc-more-info-chevron--open" : ""}`}
        width="14" height="14" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round"
      >
        <path d="M6 9l6 6 6-6" />
      </svg>
    </button>
  );
}

function PriceDisplay({ price, tax }) {
  const displayPrice = price || "$161";
  const displayTax = tax || "incl. $15 tax";
  return (
    <div className="fc-price-block">
      <div className="fc-price">{displayPrice}</div>
      <div className="fc-tax">{displayTax}</div>
    </div>
  );
}

function SelectButton({ onClick, disabled, isExpired }) {
  return (
    <button
      type="button"
      className={`fc-select-btn ${isExpired ? "fc-select-btn--expired" : ""}`}
      onClick={onClick}
      disabled={disabled || isExpired}
    >
      Select
    </button>
  );
}

function DetailsPanel({ flight }) {
  const stopsText = formatStops(flight.stops);
  const stopLocations = flight.stopLocations || [];
  
  // Extract stop location codes for display
  const stopCodes = stopLocations.map(s => {
    if (typeof s === "string") return s;
    return s.code || s.iata || s.airport || "";
  }).filter(Boolean);

  return (
    <div className="fc-details-panel">
      {/* Airline */}
      <div className="fc-details-row">
        <span className="fc-details-label">Airline:</span>
        <span className="fc-details-value">{flight.airlineShort || "—"}</span>
      </div>
      
      {/* Flight Number */}
      <div className="fc-details-row">
        <span className="fc-details-label">Flight Number:</span>
        <span className="fc-details-value">{flight.flightNumber || "—"}</span>
      </div>
      
      {/* Stops */}
      <div className="fc-details-row">
        <span className="fc-details-label">Stops:</span>
        <span className="fc-details-value">{stopsText}</span>
      </div>
      
      {/* Cabin */}
      <div className="fc-details-row">
        <span className="fc-details-label">Cabin:</span>
        <span className="fc-details-value">{flight.cabin || "Economy"}</span>
      </div>
      
      {/* Baggage */}
      <div className="fc-details-row">
        <span className="fc-details-label">Baggage:</span>
        <span className="fc-details-value">{flight.baggage || "—"}</span>
      </div>
      
      {/* Refunds */}
      <div className="fc-details-row">
        <span className="fc-details-label">Refunds:</span>
        <span className="fc-details-value">{flight.refunds || "N/A"}</span>
      </div>
      
      {/* Duration */}
      <div className="fc-details-row">
        <span className="fc-details-label">Duration:</span>
        <span className="fc-details-value">{flight.duration || "—"}</span>
      </div>
      
      {/* Stop Locations (only show if there are stops) */}
      {flight.stops > 0 && stopCodes.length > 0 && (
        <div className="fc-details-row">
          <span className="fc-details-label">Stop Locations:</span>
          <span className="fc-details-value">{stopCodes.join(", ")}</span>
        </div>
      )}
      
      {/* Individual stop details with layover duration */}
      {flight.stops > 0 && stopLocations.map((stop, idx) => {
        if (typeof stop === "object" && stop.name && stop.duration) {
          return (
            <div className="fc-details-row" key={idx}>
              <span className="fc-details-label">{stop.name}:</span>
              <span className="fc-details-value">{stop.duration}</span>
            </div>
          );
        }
        if (typeof stop === "object" && (stop.city || stop.airport) && stop.layover_duration) {
          return (
            <div className="fc-details-row" key={idx}>
              <span className="fc-details-label">{stop.city || stop.airport}:</span>
              <span className="fc-details-value">{stop.layover_duration}</span>
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}

/* ------------ Flight Card ------------ */
function FlightCard({ f, index, onSelect, disabled, startTime }) {
  const [showDetails, setShowDetails] = useState(false);
  const { isExpired, timeDisplay } = useCountdown(startTime);
  
  const isBest = !!f.highlight || index === 0;
  const hasStops = f.stops > 0;

  const { outboundRoute, returnRoute } = useMemo(() => {
    const full = (f.route || "").trim();
    const explicitReturn = (f.returnRoute || "").trim();
    let out = full;
    let ret = explicitReturn;
    if (full.includes("/")) {
      const parts = full.split("/").map((s) => s.trim());
      out = parts[0] || "";
      ret = ret || parts[1] || "";
    }
    return { outboundRoute: out, returnRoute: ret };
  }, [f.route, f.returnRoute]);

  const hasReturn = useMemo(() => {
    return !!(f.returnDepart || f.returnArrive || f.returnRoute || f.returnDate || returnRoute);
  }, [f.returnDepart, f.returnArrive, f.returnRoute, f.returnDate, returnRoute]);

  const { outboundDate, returnDate } = useMemo(() => {
    const raw = f.date || "";
    if (raw.includes("→")) {
      const [out, ret] = raw.split("→").map((s) => s.trim());
      return { outboundDate: out, returnDate: ret };
    }
    return { outboundDate: raw, returnDate: f.returnDate || "" };
  }, [f.date, f.returnDate]);

  const handleSelect = (e) => {
    e.stopPropagation();
    if (!isExpired) onSelect(f, index);
  };

  const handleToggleDetails = (e) => {
    e.stopPropagation();
    setShowDetails((v) => !v);
  };

  return (
    <div className={`fc-card ${isBest ? "fc-card--best" : ""} ${isExpired ? "fc-card--expired" : ""}`}>
      {/* Header with timer and best pill */}
      <div className="fc-card-header">
        <TimerPill timeDisplay={timeDisplay} isExpired={isExpired} />
        {isBest && <BestPill />}
      </div>

      {/* Airline logo */}
      <div className="fc-airline-section">
        <AirlineLogo airline={f.airlineShort} logo={f.airlineLogo} />
      </div>

      {/* Flight leg(s) */}
      <div className="fc-legs-section">
        {/* Departure leg */}
        <div className="fc-leg">
          <div className="fc-leg-left">
            <DateDisplay weekday={f.weekday} date={outboundDate} />
            <div className="fc-leg-label">DEPARTURE</div>
          </div>
          
          {/* Divider */}
          <div className="fc-divider" />
          
          <div className="fc-leg-middle">
            <div className="fc-time-row">
              <TimeRange depart={f.depart} arrive={f.arrive} />
              {hasStops && <StopsPill stops={f.stops} />}
            </div>
            <RouteDisplay route={outboundRoute} />
          </div>
          
          {/* Divider */}
          <div className="fc-divider" />
          
          <div className="fc-leg-right">
            <MoreInfoButton open={showDetails} onToggle={handleToggleDetails} />
          </div>
        </div>

        {/* Details panel (expandable) */}
        {showDetails && <DetailsPanel flight={f} />}

        {/* Return leg (if exists) */}
        {hasReturn && (
          <div className="fc-leg fc-leg--return">
            <div className="fc-leg-left">
              <DateDisplay weekday={f.returnWeekday} date={returnDate} />
              <div className="fc-leg-label">RETURN</div>
            </div>
            
            {/* Divider */}
            <div className="fc-divider" />
            
            <div className="fc-leg-middle">
              <TimeRange depart={f.returnDepart} arrive={f.returnArrive} />
              <RouteDisplay route={returnRoute} />
            </div>
            
            {/* Divider */}
            <div className="fc-divider" />
            
            <div className="fc-leg-right" />
          </div>
        )}
      </div>

      {/* Price and select */}
      <div className="fc-footer">
        <PriceDisplay price={f.price} tax={f.tax} />
        <SelectButton onClick={handleSelect} disabled={disabled} isExpired={isExpired} />
      </div>
    </div>
  );
}

/* ----------- App ----------- */
function App() {
  const toolOutput = useOpenAiGlobal("toolOutput");
  const toolMeta = useOpenAiGlobal("toolResponseMetadata") || toolOutput?.meta || {};

  const [frozenFlights, setFrozenFlights] = useState(null);
  const [picked, setPicked] = useState(null);
  const [sending, setSending] = useState(false);
  const [sentOnce, setSentOnce] = useState(false);
  const [sendError, setSendError] = useState(null);
  const [flightsLoadedAt, setFlightsLoadedAt] = useState(null);

  const scrollRef = useRef(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const flights = useMemo(() => {
    if (frozenFlights) return frozenFlights;
    return mapFlights(toolOutput || {});
  }, [toolOutput, frozenFlights]);

  useEffect(() => {
    if (flights.length > 0 && !frozenFlights) {
      setFlightsLoadedAt(Date.now());
    }
  }, [flights.length, frozenFlights]);

  const caps = hostCaps();

  const updateScrollButtons = () => {
    if (!scrollRef.current) return;
    const { scrollLeft, scrollWidth, clientWidth } = scrollRef.current;
    setCanScrollLeft(scrollLeft > 0);
    setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 1);
  };

  useEffect(() => {
    updateScrollButtons();
    const scrollEl = scrollRef.current;
    if (scrollEl) {
      scrollEl.addEventListener("scroll", updateScrollButtons);
      window.addEventListener("resize", updateScrollButtons);
      return () => {
        scrollEl.removeEventListener("scroll", updateScrollButtons);
        window.removeEventListener("resize", updateScrollButtons);
      };
    }
  }, [flights]);

  const scroll = (direction) => {
    if (!scrollRef.current) return;
    const scrollAmount = 400;
    const newScrollLeft = scrollRef.current.scrollLeft + (direction === "left" ? -scrollAmount : scrollAmount);
    scrollRef.current.scrollTo({ left: newScrollLeft, behavior: "smooth" });
  };

  useEffect(() => {
    if (!frozenFlights || !toolOutput) return;
    const newFlights = mapFlights(toolOutput);
    if (newFlights.length === 0) return;
    const newIds = new Set(newFlights.map((f) => f.id));
    const oldIds = new Set(frozenFlights.map((f) => f.id));
    const isDifferent = newIds.size !== oldIds.size || ![...newIds].every((id) => oldIds.has(id));
    if (isDifferent) {
      setFrozenFlights(null);
      setPicked(null);
      setSending(false);
      setSentOnce(false);
      setSendError(null);
      setFlightsLoadedAt(Date.now());
    }
  }, [toolOutput, frozenFlights]);

  async function onSelectFlight(f, index) {
    if (sending) return;
    await blockNextFlightSearchOnServer();
    setFrozenFlights(flights);

    const flightInfo = {
      offer_id: f.id,
      airline: f.airlineShort || "",
      route: f.route || "",
      date: f.date || "",
      departure_time: f.depart || "",
      arrival_time: f.arrive || "",
      duration: f.duration || "",
      price: f.price || "",
      index,
    };

    setPicked(flightInfo);
    setSending(true);
    setSendError(null);

    const promptLines = [
      "I have selected this flight from the widget:",
      "",
      `• Offer ID: ${flightInfo.offer_id}`,
      `• Airline: ${flightInfo.airline || "-"}`,
      `• Route: ${flightInfo.route || "-"}`,
      `• Date: ${flightInfo.date || "-"}`,
      `• Time: ${flightInfo.departure_time || "-"} - ${flightInfo.arrival_time || "-"}`,
      flightInfo.duration ? `• Duration: ${flightInfo.duration}` : null,
      flightInfo.price ? `• Price: ${flightInfo.price}` : null,
      "",
      "Please:",
      "1. Confirm my selection",
      "2. Call `select_flight_offer` with these details",
      "3. Ask for my seat preference (aisle/window/middle/none)",
      "4. Collect passenger details, email, and phone",
      "5. Proceed to `start_flight_checkout`",
      "",
      "Do NOT call `search_flights_ui` again.",
    ].filter(Boolean);

    try {
      await sendFollowUpMessage(promptLines.join("\n"));
      setSentOnce(true);
    } catch (e) {
      console.error("Error sending follow-up message", e);
      setSendError("Could not notify assistant.");
    } finally {
      setSending(false);
    }
  }

  const routeSummary =
    toolMeta && (toolMeta.origin || toolMeta.destination)
      ? `${toolMeta.origin || ""} → ${toolMeta.destination || ""}${toolMeta.date ? ` · ${toolMeta.date}` : ""}`
      : "";

  return (
    <div className="fc-wrap">
      <div className="fc-header">
        <div className="fc-title">{routeSummary || "Flights"}</div>
        <div className="fc-count">
          {flights.length > 0 && `${flights.length} option${flights.length === 1 ? "" : "s"}`}
        </div>
      </div>

      {!flights.length && (
        <div className="fc-empty">Waiting for flight results…</div>
      )}

      {flights.length > 0 && (
        <div className="fc-scroll-container">
          {canScrollLeft && (
            <button className="fc-scroll-btn fc-scroll-btn--left" onClick={() => scroll("left")} aria-label="Scroll left">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
          )}

          <div className="fc-scroll" ref={scrollRef}>
            <div className="fc-cards">
              {flights.map((f, idx) => (
                <FlightCard key={f.id || idx} f={f} index={idx} onSelect={onSelectFlight} disabled={sending} startTime={flightsLoadedAt} />
              ))}
            </div>
          </div>

          {canScrollRight && (
            <button className="fc-scroll-btn fc-scroll-btn--right" onClick={() => scroll("right")} aria-label="Scroll right">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6" /></svg>
            </button>
          )}
        </div>
      )}

      {picked && (
        <div className={`fc-selection ${sentOnce ? "fc-selection--sent" : ""}`}>
          <div className="fc-selection-title">Selected flight:</div>
          <div className="fc-selection-details">
            <span>{picked.airline}</span>
            <span>{picked.route}</span>
            <span>{picked.date}</span>
            {picked.price && <span>{picked.price}</span>}
          </div>
          <div className="fc-selection-status">
            {sending ? "Sending…" : sentOnce ? "✓ Selection sent" : ""}
          </div>
          {sendError && <div className="fc-selection-error">{sendError}</div>}
        </div>
      )}

      <div className="fc-diag" aria-hidden="true">
        {caps.hasFollowUp ? "followUp " : ""}
        {caps.hasAppendUser ? "appendUser " : ""}
        {caps.hasSendMessage ? "sendMsg " : ""}
        {frozenFlights ? "[FROZEN]" : ""}
      </div>
    </div>
  );
}

const mount = document.getElementById("flight-card-root");
if (mount) {
  const root = createRoot(mount);
  root.render(<App />);
}

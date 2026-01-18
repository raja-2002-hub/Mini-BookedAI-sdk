// Hotel Card Widget - Matching Document 1 Target Design
import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

/* -----------------------------
   Host globals (window.openai.*)
------------------------------ */

const SET_GLOBALS_EVENT_TYPE = "openai:set_globals";

function useOpenAiGlobal(key) {
  return useSyncExternalStore(
    (onChange) => {
      const h = (ev) => {
        if (ev?.detail?.globals?.[key] !== undefined) onChange();
      };
      window.addEventListener(SET_GLOBALS_EVENT_TYPE, h, { passive: true });
      return () => window.removeEventListener(SET_GLOBALS_EVENT_TYPE, h);
    },
    () => (window.openai ? window.openai[key] : undefined),
    () => undefined
  );
}

/* -----------------------------------------
   Capabilities (diagnostics only)
------------------------------------------ */

function hostCaps() {
  const oa = window.openai;
  return {
    hasFollowUp: !!oa?.sendFollowUpMessage,
    hasAppend: !!oa?.appendUserMessage,
    hasSend: !!oa?.sendMessage,
  };
}

/* -------- send follow-up -------- */

async function sendFollowUpMessage(prompt) {
  const oa = window.openai;

  try {
    if (oa?.sendFollowUpMessage) {
      await oa.sendFollowUpMessage({ prompt });
      return;
    }
  } catch (e) {
    console.warn("sendFollowUpMessage failed", e);
  }

  try {
    if (oa?.appendUserMessage) {
      await oa.appendUserMessage(prompt);
      return;
    }
  } catch (e) {
    console.warn("appendUserMessage failed", e);
  }

  try {
    if (oa?.sendMessage) {
      await oa.sendMessage({ role: "user", content: prompt });
      return;
    }
  } catch (e) {
    console.warn("sendMessage failed", e);
  }

  try {
    window.dispatchEvent(
      new CustomEvent("openai:append_user_message", { detail: { text: prompt } })
    );
    return;
  } catch (e) {
    console.warn("dispatchEvent fallback failed", e);
  }

  try {
    window.parent?.postMessage(
      { type: "openai:append_user_message", text: prompt },
      "*"
    );
    return;
  } catch (e) {
    console.warn("postMessage fallback failed", e);
  }

  console.log("[fallback] would send follow-up message:", prompt);
}

/* -----------------------------------------
   Backend helper: one-shot block flag
------------------------------------------ */

async function blockNextHotelSearchOnServer() {
  try {
    await fetch("http://localhost:8000/widget/hotel/block_next", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  } catch (e) {
    console.warn("Failed to block next hotel search:", e);
  }
}

/* -----------------------------------------
   Helpers: SRR extraction + hotel mapping
------------------------------------------ */

function extractSrr(raw) {
  const candidates = [
    raw?.search_result_id,
    raw?.srr,
    raw?.hotel?.search_result_id,
    raw?.hotel?.srr,
    typeof raw?.id === "string" && raw.id.startsWith("srr_") ? raw.id : null,
    typeof raw?.hotel?.id === "string" && raw.hotel.id.startsWith("srr_")
      ? raw.hotel.id
      : null,
  ].filter(Boolean);
  const v = candidates[0];
  return typeof v === "string" && v.startsWith("srr_") ? v : "";
}

function mapHotels(output) {
  const src =
    (output && (output.hotels || output.results || output.stays)) ||
    (Array.isArray(output?.data) ? output.data : []);
  if (!Array.isArray(src)) return [];

  return src.map((it, i) => {
    const hotel = it.hotel || it;

    const price =
      typeof it.price === "string"
        ? it.price
        : it.price && it.price.amount && it.price.currency
        ? `${it.price.currency} ${Number(it.price.amount).toFixed(2)}`
        : "";

    const photo =
      it.photo ||
      it.image ||
      (Array.isArray(it.images) ? it.images[0]?.url || it.images[0] : "") ||
      (Array.isArray(hotel.photos) ? hotel.photos[0]?.url : "") ||
      "";

    const srr = extractSrr(it);

    const city =
      hotel.city ||
      it.city ||
      hotel?.location?.address?.city_name ||
      hotel?.location?.address?.line_one ||
      it.location ||
      "";

    return {
      id: hotel.id || it.id || `hotel_${i}`,
      name: hotel.name || it.name || "Hotel",
      city,
      rating:
        hotel.rating ??
        it.rating ??
        hotel.star_rating ??
        it.star_rating ??
        null,
      price,
      photo,
      amenities: it.amenities || hotel.amenities || [],
      highlight: !!it.highlight,
      srr,
      search_result_id: srr,
    };
  });
}

/* -----------------------------------------
   UI helpers (formatting)
------------------------------------------ */

const CURRENCY_SYMBOL = {
  USD: "$",
  AUD: "$",
  NZD: "$",
  CAD: "$",
  SGD: "$",
  EUR: "€",
  GBP: "£",
  INR: "₹",
  JPY: "¥",
};

function formatHotelPrice(priceStr) {
  if (!priceStr) return "—";
  const s = String(priceStr).trim();

  const m = s.match(/^([A-Za-z]{3})\s*([0-9,]+(?:\.[0-9]+)?)$/);
  if (m) {
    const ccy = m[1].toUpperCase();
    const num = Number(String(m[2]).replace(/,/g, ""));
    if (!Number.isFinite(num)) return s;
    const sym = CURRENCY_SYMBOL[ccy] || `${ccy} `;
    const rounded = Math.round(num);
    return `${sym}${rounded.toLocaleString("en-US")}`;
  }

  const num2 = Number(s.replace(/[^0-9.]/g, ""));
  if (Number.isFinite(num2) && num2 > 0) {
    const rounded = Math.round(num2);
    return `$${rounded.toLocaleString("en-US")}`;
  }

  return s;
}

/* --------------- UI Components --------------- */

function StarBadge({ value }) {
  if (!value) return null;
  return (
    <div className="hc-rating" title={`${value} star rating`}>
      <svg className="hc-rating-star" viewBox="0 0 20 20">
        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
      </svg>
      <span className="hc-rating-value">{value}</span>
    </div>
  );
}

function AmenityChips({ list }) {
  if (!list?.length) return null;
  const shown = list.slice(0, 2);
  const rest = Math.max(0, list.length - shown.length);
  return (
    <div className="hc-chips">
      {shown.map((a, i) => (
        <span key={i} className="hc-chip">{String(a)}</span>
      ))}
      {rest > 0 && (
        <span className="hc-chip hc-chip--more">+{rest}</span>
      )}
    </div>
  );
}

function LocationRow({ city }) {
  return (
    <div className="hc-location">
      <svg className="hc-location-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
      <span className="hc-location-text">{city || "Location"}</span>
    </div>
  );
}

function HotelCard({ h, onSelect }) {
  const disabled = !h.srr && !h.search_result_id;
  const displayPrice = formatHotelPrice(h.price);

  return (
    <button
      type="button"
      className={
        "hc-card " +
        (h.highlight ? "hc-card--highlight " : "") +
        (disabled ? "hc-card--disabled" : "")
      }
      onClick={() => !disabled && onSelect(h)}
      disabled={disabled}
      title={disabled ? "No room rates available for this result" : h.name}
    >
      {h.photo ? (
        <img
          className="hc-img"
          src={h.photo}
          alt=""
          referrerPolicy="no-referrer"
          onError={(e) => {
            e.currentTarget.src = 'https://via.placeholder.com/400x300?text=Hotel+Image';
          }}
        />
      ) : (
        <div className="hc-img hc-img--placeholder" aria-hidden="true" />
      )}

      <div className="hc-body">
        {/* Title */}
        <div className="hc-title-row">
          <div className="hc-title" title={h.name}>{h.name}</div>
        </div>

        {/* Location row with rating on same line */}
        <div className="hc-location-row">
          <LocationRow city={h.city} />
          <StarBadge value={h.rating} />
        </div>

        {/* Amenity chips */}
        <AmenityChips list={h.amenities} />

        {/* Footer: price + select */}
        <div className="hc-footer-row">
          <div className="hc-price-block">
            <div className="hc-price">{displayPrice}</div>
            <div className="hc-price-sub">per night</div>
          </div>
          <span className="hc-select-pill">Select</span>
        </div>
      </div>
    </button>
  );
}

/* ----------- App ----------- */

function App() {
  const toolOutput = useOpenAiGlobal("toolOutput");

  const [frozenHotels, setFrozenHotels] = useState(null);

  const hotels = useMemo(() => {
    if (frozenHotels) return frozenHotels;
    return mapHotels(toolOutput || {});
  }, [toolOutput, frozenHotels]);

  const railRef = useRef(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(false);

  const [picked, setPicked] = useState(null);
  const [sending, setSending] = useState(false);
  const [sentOnce, setSentOnce] = useState(false);
  const [sendError, setSendError] = useState(null);

  const caps = hostCaps();

  const updateNavState = () => {
    const el = railRef.current;
    if (!el) return;
    const maxLeft = el.scrollWidth - el.clientWidth;
    setCanLeft(el.scrollLeft > 0);
    setCanRight(el.scrollLeft < maxLeft - 1);
  };

  useEffect(() => {
    updateNavState();
    const el = railRef.current;
    if (!el) return;
    const onScroll = () => updateNavState();
    const onResize = () => updateNavState();
    el.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize, { passive: true });
    return () => {
      el.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
    };
  }, [hotels.length]);

  useEffect(() => {
    if (frozenHotels && toolOutput) {
      const newHotels = mapHotels(toolOutput);
      if (newHotels.length > 0) {
        const newIds = new Set(newHotels.map((h) => h.id));
        const oldIds = new Set(frozenHotels.map((h) => h.id));
        const isDifferent =
          newIds.size !== oldIds.size ||
          ![...newIds].every((id) => oldIds.has(id));
        if (isDifferent) {
          setFrozenHotels(null);
          setPicked(null);
          setSending(false);
          setSentOnce(false);
          setSendError(null);
        }
      }
    }
  }, [toolOutput, frozenHotels]);

  const scrollByOneCard = (dir) => {
    const el = railRef.current;
    if (!el) return;
    // Scroll by 300px (slightly more than card width of 240px + gap)
    el.scrollBy({ left: 300 * dir, behavior: "smooth" });
    setTimeout(updateNavState, 350);
  };

  async function onSelectHotel(h) {
    await blockNextHotelSearchOnServer();
    setFrozenHotels(hotels);

    const srr = h.search_result_id || h.srr || "";

    const hotelInfo = {
      search_result_id: srr,
      hotel_id: h.id,
      hotel_name: h.name,
      location: h.city || "",
      rating: h.rating ?? null,
      price: h.price || "",
      amenities: h.amenities || [],
    };

    const promptLines = [
      "I have just clicked and selected this hotel in the hotels widget.",
      "",
      "Selected hotel details:",
      `- search_result_id (srr): ${hotelInfo.search_result_id || "(missing - cannot proceed)"}`,
      `- Hotel name: ${hotelInfo.hotel_name || "-"}`,
      `- Location: ${hotelInfo.location || "-"}`,
      `- Rating: ${hotelInfo.rating ?? "-"} stars`,
      `- Price: ${hotelInfo.price || "-"}`,
      hotelInfo.amenities.length
        ? `- Amenities: ${hotelInfo.amenities.join(", ")}`
        : null,
      "",
      "IMPORTANT INSTRUCTIONS:",
      "1. Do NOT call `search_hotels_ui` again for this selection (it will be blocked by the server).",
      "",
      "2. IMMEDIATELY call `fetch_hotel_rates_ui` with these exact parameters:",
      `   {`,
      `     "search_result_id": "${hotelInfo.search_result_id}",`,
      `     "hotel_name": "${hotelInfo.hotel_name}",`,
      `     "location": "${hotelInfo.location}"`,
      `   }`,
      "",
      "3. After showing the available rooms, ask me which room I prefer.",
      "",
      "4. Once I select a room, collect:",
      "   - Guest name(s) (given_name and family_name)",
      "   - Email address",
      "   - Phone number",
      "   - Any special requests",
      "",
      "5. Then call `start_hotel_checkout` with all the collected information to proceed with payment.",
    ].filter(Boolean);

    const prompt = promptLines.join("\n");

    setPicked(hotelInfo);
    setSending(true);
    setSendError(null);

    try {
      await sendFollowUpMessage(prompt);
      setSentOnce(true);
    } catch (e) {
      console.error("Error sending follow-up message", e);
      setSendError("Could not notify the assistant about this selection.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="hc-wrap">
      <div className="hc-rail">
        <button
          className="hc-nav hc-nav--left"
          aria-label="Scroll left"
          onClick={() => scrollByOneCard(-1)}
          disabled={!canLeft}
          style={{ display: canLeft ? 'flex' : 'none' }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        <div ref={railRef} className="hc-scroll" aria-label="Hotel results">
          {hotels.map((h) => (
            <HotelCard key={h.id} h={h} onSelect={onSelectHotel} />
          ))}
        </div>

        <button
          className="hc-nav hc-nav--right"
          aria-label="Scroll right"
          onClick={() => scrollByOneCard(1)}
          disabled={!canRight}
          style={{ display: canRight ? 'flex' : 'none' }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>

      {!hotels.length && (
        <div className="hc-empty">Waiting for hotel results…</div>
      )}

      {picked && (
        <div
          className={
            "hc-bubble " +
            (sending ? "is-sending " : "") +
            (sentOnce ? "is-sent " : "")
          }
        >
          <div><b>✓ Selected hotel:</b></div>
          <div><b>Hotel:</b> {picked.hotel_name}</div>
          <div><b>Location:</b> {picked.location || "-"}</div>
          <div><b>Rating:</b> {picked.rating ?? "-"} stars</div>
          <div><b>Price:</b> {picked.price || "-"}</div>
          {picked.amenities?.length ? (
            <div><b>Amenities:</b> {picked.amenities.join(", ")}</div>
          ) : null}
          <div className="hc-bubble-cta">
            {sending
              ? "Notifying assistant…"
              : sentOnce
              ? "Assistant notified ✓"
              : "Ready to notify assistant"}
          </div>
          {sendError && <div className="hc-error">{sendError}</div>}
        </div>
      )}

      <div className="hc-diagnostics" aria-hidden="true">
        caps:
        {caps.hasFollowUp ? " sendFollowUpMessage" : ""}
        {caps.hasAppend ? " appendUserMessage" : ""}
        {caps.hasSend ? " sendMessage" : ""}
        {!caps.hasFollowUp && !caps.hasAppend && !caps.hasSend ? " none" : ""}
        {frozenHotels ? " [FROZEN]" : ""}
      </div>
    </div>
  );
}

const mount = document.getElementById("hotel-card-root");
if (mount) {
  const root = createRoot(mount);
  root.render(<App />);
}

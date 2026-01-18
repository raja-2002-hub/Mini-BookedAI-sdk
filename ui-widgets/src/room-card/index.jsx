// Room Card Widget - Redesigned to match Hotel Card
import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const SET_GLOBALS_EVENT_TYPE = "openai:set_globals";

/* -------------------- OpenAI widget globals -------------------- */
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

/* -------------------- Capabilities -------------------- */
function hostCaps() {
  const oa = window.openai;
  return {
    hasFollowUp: !!oa?.sendFollowUpMessage,
    hasAppendUser: !!oa?.appendUserMessage,
    hasSendMessage: !!oa?.sendMessage,
  };
}

/* -------------------- sendFollowUp -------------------- */
async function sendFollowUpMessage(prompt) {
  const oa = window.openai;
  let lastError = null;

  try {
    if (oa?.sendFollowUpMessage) {
      await oa.sendFollowUpMessage({ prompt });
      return;
    }
  } catch (e) {
    console.warn("sendFollowUpMessage failed", e);
    lastError = e;
  }

  try {
    if (oa?.appendUserMessage) {
      await oa.appendUserMessage(prompt);
      return;
    }
  } catch (e) {
    console.warn("appendUserMessage failed", e);
    lastError = e;
  }

  try {
    if (oa?.sendMessage) {
      await oa.sendMessage({ role: "user", content: prompt });
      return;
    }
  } catch (e) {
    console.warn("sendMessage failed", e);
    lastError = e;
  }

  try {
    window.dispatchEvent(
      new CustomEvent("openai:append_user_message", { detail: { text: prompt } })
    );
    return;
  } catch (e) {
    console.warn("dispatchEvent fallback failed", e);
    lastError = e;
  }

  try {
    window.parent?.postMessage(
      { type: "openai:append_user_message", text: prompt },
      "*"
    );
    return;
  } catch (e) {
    console.warn("postMessage fallback failed", e);
    lastError = e;
  }

  console.log("[fallback] would send follow-up message:", prompt);
  if (lastError) throw lastError;
}

/* -------------------- Server block -------------------- */
async function blockNextRoomRatesOnServer() {
  try {
    await fetch("http://localhost:8000/widget/room/block_next", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  } catch (e) {
    console.warn("Failed to block next room rates fetch:", e);
  }
}

/* -------------------- Helpers -------------------- */
function coerceRooms(output) {
  const src =
    (output && (output.rooms || output.rates || (output.data || {}).rates)) ||
    [];
  if (!Array.isArray(src)) return [];
  return src.map((r, i) => ({
    id: r.id || `rat_${i}`,
    name: r.name || r.room_name || r.room_type || `Room ${i + 1}`,
    price: r.price || "",
    price_amount: r.price_amount ?? null,
    currency: r.currency || null,
    bed: r.bed || "",
    board: r.board || "",
    cancellation: r.cancellation || "",
    quantity: r.quantity ?? null,
    photos: Array.isArray(r.photos) ? r.photos : [],
    highlight: !!r.highlight,
  }));
}

/* Format price for display */
function formatPrice(priceStr) {
  if (!priceStr) return "—";
  const s = String(priceStr).trim();
  
  // Handle "AUD 1511.72" format
  const match = s.match(/^([A-Za-z]{3})\s*([0-9,]+(?:\.[0-9]+)?)$/);
  if (match) {
    const currency = match[1].toUpperCase();
    const amount = parseFloat(match[2].replace(/,/g, ""));
    if (!isNaN(amount)) {
      const symbols = { USD: "$", AUD: "$", EUR: "€", GBP: "£", JPY: "¥" };
      const sym = symbols[currency] || `${currency} `;
      return `${sym}${Math.round(amount).toLocaleString()}`;
    }
  }
  
  return s;
}

/* Format cancellation text */
function formatCancellation(text) {
  if (!text) return "";
  // Shorten ISO dates like "2026-01-15T13:00:00Z"
  const shortened = text.replace(/(\d{4}-\d{2}-\d{2})T[\d:]+Z?/g, (_, date) => {
    const d = new Date(date);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  });
  // Shorten "Refundable until" to "Free cancel until"
  return shortened.replace(/Refundable until/i, "Free cancel until");
}

/* -------------------- Image Gallery Component -------------------- */
function ImageGallery({ photos, onOpenLightbox }) {
  const [currentIdx, setCurrentIdx] = useState(0);
  
  if (!photos.length) {
    return (
      <div className="rc-gallery">
        <div className="rc-gallery__main" style={{ background: "#f3f4f6" }} />
      </div>
    );
  }

  const goNext = (e) => {
    e.stopPropagation();
    setCurrentIdx((prev) => (prev + 1) % photos.length);
  };

  const goPrev = (e) => {
    e.stopPropagation();
    setCurrentIdx((prev) => (prev - 1 + photos.length) % photos.length);
  };

  const handleImageClick = (e) => {
    e.stopPropagation();
    onOpenLightbox(currentIdx);
  };

  return (
    <div className="rc-gallery">
      <img
        className="rc-gallery__main"
        src={photos[currentIdx]}
        alt=""
        referrerPolicy="no-referrer"
        onClick={handleImageClick}
      />
      
      {photos.length > 1 && (
        <>
          <button className="rc-gallery__nav rc-gallery__nav--left" onClick={goPrev}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>
          <button className="rc-gallery__nav rc-gallery__nav--right" onClick={goNext}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
          
          <div className="rc-gallery__count">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="M21 15l-5-5L5 21" />
            </svg>
            {currentIdx + 1}/{photos.length}
          </div>
        </>
      )}
    </div>
  );
}

/* -------------------- Lightbox Modal -------------------- */
function Lightbox({ photos, isOpen, initialIdx, onClose }) {
  const [idx, setIdx] = useState(initialIdx);

  useEffect(() => {
    setIdx(initialIdx);
  }, [initialIdx]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") setIdx((p) => (p - 1 + photos.length) % photos.length);
      if (e.key === "ArrowRight") setIdx((p) => (p + 1) % photos.length);
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, photos.length, onClose]);

  if (!photos.length) return null;

  return (
    <div className={`rc-lightbox ${isOpen ? "rc-lightbox--open" : ""}`} onClick={onClose}>
      <div className="rc-lightbox__content" onClick={(e) => e.stopPropagation()}>
        <button className="rc-lightbox__close" onClick={onClose}>×</button>
        
        {photos.length > 1 && (
          <button
            className="rc-lightbox__nav rc-lightbox__nav--left"
            onClick={() => setIdx((p) => (p - 1 + photos.length) % photos.length)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>
        )}
        
        <img
          className="rc-lightbox__img"
          src={photos[idx]}
          alt=""
          referrerPolicy="no-referrer"
        />
        
        {photos.length > 1 && (
          <button
            className="rc-lightbox__nav rc-lightbox__nav--right"
            onClick={() => setIdx((p) => (p + 1) % photos.length)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
        )}
        
        {photos.length > 1 && (
          <div className="rc-lightbox__counter">{idx + 1} / {photos.length}</div>
        )}
      </div>
    </div>
  );
}

/* -------------------- Room Card -------------------- */
function RoomCard({ r, onSelect, disabled }) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxIdx, setLightboxIdx] = useState(0);
  
  const isRefundable = /refund|free|cancel/i.test(r.cancellation || "");
  const formattedPrice = formatPrice(r.price);
  const formattedCancellation = formatCancellation(r.cancellation);

  const handleCardClick = () => {
    if (disabled) return;
    onSelect(r);
  };

  const handleSelectClick = (e) => {
    e.stopPropagation();
    if (disabled) return;
    onSelect(r);
  };

  const openLightbox = (idx) => {
    setLightboxIdx(idx);
    setLightboxOpen(true);
  };

  return (
    <>
      <button
        type="button"
        className={`rc-card ${r.highlight ? "rc-card--highlight" : ""} ${disabled ? "rc-card--disabled" : ""}`}
        onClick={handleCardClick}
        disabled={disabled}
        title={disabled ? "Processing..." : r.name}
      >
        {r.highlight && <div className="rc-badge">Best Value</div>}
        
        <ImageGallery photos={r.photos} onOpenLightbox={openLightbox} />
        
        <div className="rc-body">
          {/* Title and Price */}
          <div className="rc-title-row">
            <div className="rc-title">{r.name}</div>
            <div className="rc-price">
              <div className="rc-price__amount">{formattedPrice}</div>
              <div className="rc-price__period">per night</div>
              {r.quantity != null && r.quantity <= 3 && (
                <div className="rc-price__qty">{r.quantity} left</div>
              )}
            </div>
          </div>
          
          {/* Info chips */}
          <div className="rc-chips">
            {r.bed && <span className="rc-chip">{r.bed}</span>}
            {r.board && <span className="rc-chip">{r.board}</span>}
            {formattedCancellation && (
              <span className={`rc-chip ${isRefundable ? "rc-chip--good" : "rc-chip--warn"}`}>
                {formattedCancellation}
              </span>
            )}
          </div>
          
          {/* Footer */}
          <div className="rc-footer">
            <button type="button" className="rc-details-btn" onClick={(e) => e.stopPropagation()}>
              View details
            </button>
            <span className="rc-select-btn">Select</span>
          </div>
        </div>
      </button>
      
      <Lightbox
        photos={r.photos}
        isOpen={lightboxOpen}
        initialIdx={lightboxIdx}
        onClose={() => setLightboxOpen(false)}
      />
    </>
  );
}

/* -------------------- App -------------------- */
function App() {
  const toolOutput = useOpenAiGlobal("toolOutput");
  const [frozenRooms, setFrozenRooms] = useState(null);

  const rooms = useMemo(() => {
    if (frozenRooms) return frozenRooms;
    return coerceRooms(toolOutput || {});
  }, [toolOutput, frozenRooms]);

  const meta = (toolOutput && toolOutput.meta) || {};
  const hotelName = meta.hotelName || "Hotel";
  const hotelLocation = meta.location || "";
  const srr = meta.search_result_id || meta.srr || meta.searchResultId || "";

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
    el.addEventListener("scroll", updateNavState, { passive: true });
    window.addEventListener("resize", updateNavState, { passive: true });
    return () => {
      el.removeEventListener("scroll", updateNavState);
      window.removeEventListener("resize", updateNavState);
    };
  }, [rooms.length]);

  useEffect(() => {
    if (frozenRooms && toolOutput) {
      const newRooms = coerceRooms(toolOutput || {});
      if (newRooms.length > 0) {
        const newIds = new Set(newRooms.map((r) => r.id));
        const oldIds = new Set(frozenRooms.map((r) => r.id));
        const isDifferent = newIds.size !== oldIds.size || [...newIds].some((id) => !oldIds.has(id));
        if (isDifferent) {
          setFrozenRooms(null);
          setPicked(null);
          setSending(false);
          setSentOnce(false);
          setSendError(null);
        }
      }
    }
  }, [toolOutput, frozenRooms]);

  const scrollByOneCard = (dir) => {
    const el = railRef.current;
    if (!el) return;
    const card = el.querySelector(".rc-card");
    const gap = 16;
    const cardWidth = card ? card.getBoundingClientRect().width : 300;
    el.scrollBy({ left: (cardWidth + gap) * dir, behavior: "smooth" });
  };

  async function handleSelect(room) {
    if (sending) return;

    const roomInfo = {
      rate_id: room.id,
      room_name: room.name,
      price_label: room.price || "",
      price_amount: room.price_amount,
      currency: room.currency,
      bed: room.bed || "",
      board: room.board || "",
      cancellation: room.cancellation || "",
      quantity: room.quantity,
      hotel_name: hotelName,
      hotel_location: hotelLocation,
      search_result_id: srr,
    };

    const promptLines = [
      "I just selected this room and want to book it.",
      "",
      "Selected room details:",
      `- Hotel: ${roomInfo.hotel_name}`,
      `- Location: ${roomInfo.hotel_location || "-"}`,
      `- Room: ${roomInfo.room_name}`,
      `- Rate ID: ${roomInfo.rate_id}`,
      `- Price: ${roomInfo.price_label}`,
      roomInfo.bed ? `- Bed: ${roomInfo.bed}` : null,
      roomInfo.board ? `- Board: ${roomInfo.board}` : null,
      roomInfo.cancellation ? `- Cancellation: ${roomInfo.cancellation}` : null,
      roomInfo.search_result_id ? `- search_result_id: ${roomInfo.search_result_id}` : null,
      "",
      "Please:",
      "1) Call `select_hotel_room_rate` with the details above",
      "2) Ask me for guest names, email, and phone",
      "3) Call `start_hotel_checkout` once I provide the info",
      "4) Give me the Stripe payment link",
    ].filter(Boolean);

    setFrozenRooms(rooms);
    setPicked(roomInfo);
    setSending(true);
    setSendError(null);

    try {
      await blockNextRoomRatesOnServer();
      await sendFollowUpMessage(promptLines.join("\n"));
      setSentOnce(true);
    } catch (e) {
      console.error("Error sending message", e);
      setSendError("Could not send selection.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="rc-wrap">
      {meta?.message && (
        <div className="rc-bubble">
          {meta.message.split("\n").map((l, i) => <div key={i}>{l}</div>)}
        </div>
      )}

      <div className="rc-rail">
        <button
          className="rc-nav rc-nav--left"
          aria-label="Scroll left"
          onClick={() => scrollByOneCard(-1)}
          disabled={!canLeft}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>

        <div ref={railRef} className="rc-scroll">
          {rooms.map((r) => (
            <RoomCard
              key={r.id}
              r={r}
              onSelect={handleSelect}
              disabled={sending}
            />
          ))}
        </div>

        <button
          className="rc-nav rc-nav--right"
          aria-label="Scroll right"
          onClick={() => scrollByOneCard(1)}
          disabled={!canRight}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 18l6-6-6-6" />
          </svg>
        </button>
      </div>

      {!rooms.length && (
        <div className="rc-skeleton">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rc-skeleton__card">
              <div className="rc-skeleton__img" />
              <div className="rc-skeleton__body">
                <div className="rc-skeleton__line" />
                <div className="rc-skeleton__line rc-skeleton__line--short" />
                <div className="rc-skeleton__line--chips">
                  <div className="rc-skeleton__chip" />
                  <div className="rc-skeleton__chip" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {picked && (
        <div className="rc-select-bubble">
          <b>Selected:</b> {picked.room_name} at {picked.hotel_name}
          <div>{sending ? "Sending..." : sentOnce ? "✓ Sent" : ""}</div>
          {sendError && <div className="rc-error">{sendError}</div>}
        </div>
      )}

      <div className="rc-diagnostics">
        {caps.hasFollowUp ? "followUp " : ""}
        {caps.hasAppendUser ? "append " : ""}
        {caps.hasSendMessage ? "send " : ""}
        {frozenRooms ? "[FROZEN]" : ""}
      </div>
    </div>
  );
}

const mount = document.getElementById("room-card-root");
if (mount) createRoot(mount).render(<App />);

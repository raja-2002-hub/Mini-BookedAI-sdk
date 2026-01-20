// ui-widgets/src/payment-card/index.jsx
// ✅ Stripe checkout layout: order summary left, payment form right
// ✅ Card-only payment
// ✅ Fixed-height (600px) widget with internal scroll
// ✅ SIMPLIFIED: Server handles duplicate blocking via ctx_id - no widget blocking calls needed

import React, { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
import { createPortal } from "react-dom";
import "./styles.css";

/* -----------------------------
   CRITICAL: Prevent frame auto-resize
------------------------------ */
(function preventFrameResize() {
  const FIXED_HEIGHT = 600;

  document.documentElement.style.cssText = `height: ${FIXED_HEIGHT}px !important; max-height: ${FIXED_HEIGHT}px !important; overflow: hidden !important;`;
  document.body.style.cssText = `height: ${FIXED_HEIGHT}px !important; max-height: ${FIXED_HEIGHT}px !important; overflow: hidden !important; margin: 0 !important; padding: 0 !important;`;

  const OriginalResizeObserver = window.ResizeObserver;
  if (OriginalResizeObserver) {
    window.ResizeObserver = class extends OriginalResizeObserver {
      constructor(callback) {
        super((entries, observer) => {
          const validEntries = entries.filter((entry) => {
            const target = entry.target;
            if (
              target === document.documentElement ||
              target === document.body ||
              target.id === "payment-card-root" ||
              target.classList?.contains("sc-container") ||
              target.classList?.contains("sc-layout")
            ) {
              return false;
            }
            return true;
          });
          if (validEntries.length > 0) callback(validEntries, observer);
        });
      }
    };
  }

  const originalPostMessage = window.parent.postMessage.bind(window.parent);
  window.parent.postMessage = function (message, targetOrigin, transfer) {
    if (typeof message === "object" && message !== null) {
      const msgStr = JSON.stringify(message).toLowerCase();
      if (msgStr.includes("height") || msgStr.includes("resize") || msgStr.includes("size")) {
        return;
      }
    }
    if (typeof message === "string") {
      const msgLower = message.toLowerCase();
      if (msgLower.includes("height") || msgLower.includes("resize") || msgLower.includes("size")) {
        return;
      }
    }
    return originalPostMessage(message, targetOrigin, transfer);
  };

  const originalWindowPostMessage = window.postMessage.bind(window);
  window.postMessage = function (message, targetOrigin, transfer) {
    if (typeof message === "object" && message !== null) {
      const msgStr = JSON.stringify(message).toLowerCase();
      if (msgStr.includes("height") || msgStr.includes("resize") || msgStr.includes("size")) {
        return;
      }
    }
    return originalWindowPostMessage(message, targetOrigin, transfer);
  };

  const OriginalMutationObserver = window.MutationObserver;
  if (OriginalMutationObserver) {
    window.MutationObserver = class extends OriginalMutationObserver {
      constructor(callback) {
        super((mutations, observer) => {
          const validMutations = mutations.filter((mutation) => {
            if (mutation.type === "attributes" && (mutation.attributeName === "style" || mutation.attributeName === "class")) {
              const target = mutation.target;
              if (target === document.documentElement || target === document.body || target.id === "payment-card-root") {
                return false;
              }
            }
            return true;
          });
          if (validMutations.length > 0) callback(validMutations, observer);
        });
      }
    };
  }

  console.log("[payment-card] Frame resize prevention active");
})();

/* -----------------------------
   Config
------------------------------ */
const STRIPE_PUBLISHABLE_KEY = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY;
const API_BASE = import.meta.env.VITE_API_BASE;

/* -----------------------------
   Stripe.js loader (CDN)
------------------------------ */
let stripeInstance = null;

function loadStripeCDN() {
  return new Promise((resolve, reject) => {
    if (window.Stripe) {
      if (!stripeInstance) stripeInstance = window.Stripe(STRIPE_PUBLISHABLE_KEY);
      resolve(stripeInstance);
      return;
    }

    const existing = document.querySelector('script[src*="js.stripe.com"]');
    if (existing) {
      existing.addEventListener("load", () => {
        stripeInstance = window.Stripe(STRIPE_PUBLISHABLE_KEY);
        resolve(stripeInstance);
      });
      return;
    }

    const script = document.createElement("script");
    script.src = "https://js.stripe.com/v3/";
    script.async = true;
    script.onload = () => {
      if (!window.Stripe) return reject(new Error("Stripe failed to load"));
      stripeInstance = window.Stripe(STRIPE_PUBLISHABLE_KEY);
      resolve(stripeInstance);
    };
    script.onerror = () => reject(new Error("Failed to load Stripe script"));
    document.head.appendChild(script);
  });
}

/* -----------------------------
   Session ID extraction
------------------------------ */
function extractSessionId() {
  const currentUrl = window.location.href;
  if (currentUrl.includes("/c/")) {
    const match = currentUrl.match(/\/c\/([a-f0-9-]+)/);
    if (match) return match[1];
  }

  try {
    const parentUrl = window.parent?.location?.href;
    if (parentUrl && parentUrl.includes("/c/")) {
      const match = parentUrl.match(/\/c\/([a-f0-9-]+)/);
      if (match) return match[1];
    }
  } catch {}

  if (document.referrer.includes("/c/")) {
    const match = document.referrer.match(/\/c\/([a-f0-9-]+)/);
    if (match) return match[1];
  }

  const conversationId = window.openai?.conversationId;
  if (conversationId) return conversationId;

  return `browser_${navigator.userAgent.substring(0, 18).replace(/\W/g, "")}`;
}

/* -----------------------------
   OpenAI globals hook
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

/* -----------------------------
   Follow-up message helper
------------------------------ */
async function sendFollowUpMessage(prompt) {
  const oa = window.openai;

  try {
    if (oa?.sendFollowUpMessage) {
      await oa.sendFollowUpMessage({ prompt });
      return;
    }
  } catch (e) {
    console.warn("payment-card: sendFollowUpMessage failed", e);
  }

  try {
    if (oa?.appendUserMessage) {
      await oa.appendUserMessage(prompt);
      return;
    }
  } catch (e) {
    console.warn("payment-card: appendUserMessage failed", e);
  }

  try {
    if (oa?.sendMessage) {
      await oa.sendMessage({ role: "user", content: prompt });
      return;
    }
  } catch (e) {
    console.warn("payment-card: sendMessage failed", e);
  }

  try {
    window.dispatchEvent(new CustomEvent("openai:append_user_message", { detail: { text: prompt } }));
    return;
  } catch (e) {
    console.warn("payment-card: dispatchEvent fallback failed", e);
  }

  try {
    window.parent?.postMessage({ type: "openai:append_user_message", text: prompt }, "*");
    return;
  } catch (e) {
    console.warn("payment-card: postMessage fallback failed", e);
  }

  console.log("[payment-card fallback] would send follow-up:", prompt);
}

/* -----------------------------
   PaymentIntent endpoints
------------------------------ */
async function createPaymentIntent(ctxId, type) {
  const endpoint =
    type === "flight"
      ? `${API_BASE}/api/flight/payment/create-intent`
      : `${API_BASE}/api/hotel/payment/create-intent`;

  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ctx_id: ctxId }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to create PaymentIntent");
  }

  return res.json();
}

async function confirmBookingOnServer(ctxId, paymentIntentId, type) {
  const endpoint =
    type === "flight"
      ? `${API_BASE}/api/flight/payment/confirm-booking`
      : `${API_BASE}/api/hotel/payment/confirm-booking`;

  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ctx_id: ctxId, payment_intent_id: paymentIntentId }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to confirm booking");
  }

  return res.json();
}

/* -----------------------------
   UI helpers
------------------------------ */
function normalizeToolOutput(raw) {
  if (!raw || typeof raw !== "object") return {};

  const status = raw.status || {};
  const payment = raw.payment || {};
  const metadata = raw.metadata || {};

  return {
    status: status.status || raw.status || "pending",
    type: status.type || raw.type || "hotel",
    ctx_id: status.ctx_id || payment.ctx_id || raw.ctx_id || "",
    amount: status.amount ?? payment.amount ?? raw.amount ?? null,
    currency: status.currency || payment.currency || raw.currency || null,
    email: status.email || raw.email || metadata.email || null,
    hotel_name: status.hotel_name || metadata.hotel_name || null,
    room_name: metadata.room_type || metadata.room_name || null,
    rawStatus: status,
    metadata,
    raw,
  };
}

function formatAmount(amount) {
  if (amount === null || amount === undefined) return null;
  if (typeof amount === "number") return amount.toFixed(2);
  if (typeof amount === "string") return amount;
  return String(amount);
}

/* -----------------------------
   Confirm Dialog (Portal)
------------------------------ */
function ConfirmDialog({ open, kind, ctxId, onClose, onConfirm, busy, error }) {
  if (!open) return null;

  const dialogContent = (
    <div className="sc-overlay" onClick={onClose}>
      <div className="sc-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="sc-dialog-header">
          <div className="sc-dialog-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
              <path
                d="M20 6L9 17L4 12"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <h3>Payment successful</h3>
          <button className="sc-close-btn" onClick={onClose} aria-label="Close">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="sc-dialog-body">
          <p>Your {kind === "flight" ? "flight" : "hotel"} booking has been confirmed.</p>
          <div className="sc-dialog-info">
            <span className="sc-info-label">Booking Reference</span>
            <code className="sc-info-code">{ctxId}</code>
          </div>
          {error && <div className="sc-error-msg">{error}</div>}
        </div>

        <div className="sc-dialog-footer">
          <button className="sc-btn-primary" onClick={onConfirm} disabled={busy}>
            {busy ? (
              <>
                <span className="sc-spinner"></span>
                Processing...
              </>
            ) : (
              "Done"
            )}
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(dialogContent, document.body);
}

/* -----------------------------
   Stripe Card Form
------------------------------ */
function CardPaymentForm({ ctxId, type, amount, currency, clientSecret, email, onSuccess, onError }) {
  const stripeRef = useRef(null);
  const cardElementRef = useRef(null);
  const mountRef = useRef(null);

  const [ready, setReady] = useState(false);
  const [complete, setComplete] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [err, setErr] = useState(null);
  const [cardholderName, setCardholderName] = useState("");
  const [country, setCountry] = useState("AU");

  useEffect(() => {
    let alive = true;

    async function setup() {
      try {
        const stripe = await loadStripeCDN();
        if (!alive) return;
        stripeRef.current = stripe;

        const elements = stripe.elements({
          clientSecret,
          appearance: {
            theme: "stripe",
            variables: {
              colorPrimary: "#0570de",
              colorBackground: "#ffffff",
              colorText: "#30313d",
              colorDanger: "#df1b41",
              fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
              fontSizeBase: "16px",
              spacingUnit: "4px",
              borderRadius: "6px",
            },
            rules: {
              ".Input": {
                border: "1px solid #e0e0e0",
                boxShadow: "none",
                padding: "12px",
              },
              ".Input:focus": {
                border: "1px solid #0570de",
                boxShadow: "0 0 0 1px #0570de",
              },
            },
          },
        });

        const card = elements.create("card", {
          style: {
            base: {
              fontSize: "16px",
              color: "#30313d",
              fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
              "::placeholder": { color: "#a0aec0" },
            },
            invalid: { color: "#df1b41" },
          },
          hidePostalCode: true,
        });

        if (mountRef.current) {
          card.mount(mountRef.current);
          cardElementRef.current = card;

          card.on("ready", () => alive && setReady(true));
          card.on("change", (event) => {
            if (!alive) return;
            setComplete(!!event.complete);
            setErr(event.error ? event.error.message : null);
          });
        }
      } catch (e) {
        if (!alive) return;
        setErr(e.message || "Failed to load payment form");
      }
    }

    setup();

    return () => {
      alive = false;
      try {
        cardElementRef.current?.destroy?.();
      } catch {}
      cardElementRef.current = null;
    };
  }, [clientSecret]);

  async function submit(e) {
    e.preventDefault();
    if (!stripeRef.current || !cardElementRef.current) return;

    if (!complete) {
      setErr("Please complete your card details");
      return;
    }

    setProcessing(true);
    setErr(null);

    try {
      const { error, paymentIntent } = await stripeRef.current.confirmCardPayment(clientSecret, {
        payment_method: {
          card: cardElementRef.current,
          billing_details: { name: cardholderName || undefined, email: email || undefined },
        },
      });

      if (error) {
        setErr(error.message || "Payment failed");
        onError?.(error.message);
        setProcessing(false);
        return;
      }

      if (paymentIntent?.status === "succeeded") {
        try {
          const bookingResult = await confirmBookingOnServer(ctxId, paymentIntent.id, type);
          onSuccess?.({ payment_intent_id: paymentIntent.id, bookingResult });
        } catch {
          setErr("Payment succeeded but booking failed. Please contact support.");
          setProcessing(false);
          return;
        }
      } else {
        setErr(`Payment status: ${paymentIntent?.status || "unknown"}`);
        setProcessing(false);
      }
    } catch (e2) {
      setErr(e2.message || "Payment failed");
      onError?.(e2.message);
      setProcessing(false);
    }
  }

  return (
    <form className="sc-form" onSubmit={submit}>
      <div className="sc-section-header">Pay with card</div>

      <div className="sc-field">
        <label className="sc-label">Email</label>
        <input type="email" className="sc-input" value={email || ""} readOnly disabled />
      </div>

      <div className="sc-field">
        <label className="sc-label">Card information</label>
        <div className="sc-card-wrapper">
          <div className="sc-card-element" ref={mountRef} />
        </div>
      </div>

      <div className="sc-field">
        <label className="sc-label">Name on card</label>
        <input
          type="text"
          className="sc-input"
          placeholder="Full name on card"
          value={cardholderName}
          onChange={(e) => setCardholderName(e.target.value)}
        />
      </div>

      <div className="sc-field">
        <label className="sc-label">Country or region</label>
        <div className="sc-select-wrapper">
          <select className="sc-select" value={country} onChange={(e) => setCountry(e.target.value)}>
            <option value="AU">Australia</option>
            <option value="US">United States</option>
            <option value="GB">United Kingdom</option>
            <option value="CA">Canada</option>
            <option value="NZ">New Zealand</option>
            <option value="SG">Singapore</option>
            <option value="JP">Japan</option>
            <option value="DE">Germany</option>
            <option value="FR">France</option>
          </select>
          <svg className="sc-select-arrow" width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </div>

      {err && (
        <div className="sc-error">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1a7 7 0 100 14A7 7 0 008 1zM7.5 4.5h1v5h-1v-5zm0 6h1v1h-1v-1z" />
          </svg>
          <span>{err}</span>
        </div>
      )}

      <button type="submit" className="sc-pay-btn" disabled={!ready || processing}>
        {processing ? (
          <>
            <span className="sc-spinner"></span>
            Processing...
          </>
        ) : (
          `Pay ${currency} ${amount}`
        )}
      </button>
    </form>
  );
}

/* -----------------------------
   Embedded Payment Container
------------------------------ */
function EmbeddedPayment({ ctxId, type, amount, currency, email, onSuccess }) {
  const [clientSecret, setClientSecret] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!ctxId) return;

    let cancelled = false;

    async function init() {
      try {
        setLoading(true);
        setErr(null);
        const r = await createPaymentIntent(ctxId, type);
        if (cancelled) return;
        setClientSecret(r.clientSecret);
      } catch (e) {
        if (cancelled) return;
        setErr(e.message || "Failed to initialize payment");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    init();
    return () => {
      cancelled = true;
    };
  }, [ctxId, type]);

  if (loading) {
    return (
      <div className="sc-loading">
        <span className="sc-spinner sc-spinner-lg"></span>
        <span>Loading payment form...</span>
      </div>
    );
  }

  if (err) {
    return (
      <div className="sc-error-state">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <circle cx="24" cy="24" r="22" stroke="#df1b41" strokeWidth="2" />
          <path d="M24 14v12m0 6h.01" stroke="#df1b41" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <p>{err}</p>
        <button className="sc-btn-secondary" onClick={() => window.location.reload()}>
          Try again
        </button>
      </div>
    );
  }

  if (!clientSecret) return <div className="sc-error">Missing payment configuration.</div>;

  return (
    <CardPaymentForm
      ctxId={ctxId}
      type={type}
      amount={amount}
      currency={currency}
      email={email}
      clientSecret={clientSecret}
      onSuccess={onSuccess}
      onError={(e) => setErr(e)}
    />
  );
}

/* -----------------------------
   Main Component
------------------------------ */
function App() {
  const toolOutput = useOpenAiGlobal("toolOutput");
  const toolMeta = useOpenAiGlobal("toolResponseMetadata") || toolOutput?.meta || {};
  const caps = hostCaps();

  // Freeze the payment context so toolOutput refresh doesn't restart checkout UI
  const [frozenPayment, setFrozenPayment] = useState(null);

  // One-shot sending guard per ctx_id
  const [sending, setSending] = useState(false);
  const [sentOnce, setSentOnce] = useState(false);
  const sentForCtxRef = useRef(new Set());

  const initial = useMemo(() => normalizeToolOutput(toolOutput || {}), [toolOutput]);

  const [ctxId, setCtxId] = useState(initial.ctx_id || "");
  const [kind, setKind] = useState(initial.type || "hotel");
  const [status, setStatus] = useState(initial.status || "pending");
  const [amount, setAmount] = useState(initial.amount);
  const [currency, setCurrency] = useState(initial.currency);
  const [email, setEmail] = useState(initial.email);
  const [hotelName, setHotelName] = useState(initial.hotel_name);
  const [roomName, setRoomName] = useState(initial.room_name);
  const [details, setDetails] = useState(initial.rawStatus || {});

  const [paid, setPaid] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmSent, setConfirmSent] = useState(false);
  const [confirmErr, setConfirmErr] = useState(null);

  const confirmedCtxSet = useRef(new Set());

  // Keep in sync with toolOutput; reset flow if ctx changes
  useEffect(() => {
    const norm = normalizeToolOutput(toolOutput || {});
    const newCtx = norm.ctx_id || "";

    if (newCtx && newCtx !== ctxId) {
      setCtxId(newCtx);
      setKind(norm.type || "hotel");
      setStatus(norm.status || "pending");
      setAmount(norm.amount);
      setCurrency(norm.currency);
      setEmail(norm.email);
      setHotelName(norm.hotel_name);
      setRoomName(norm.room_name);
      setDetails(norm.rawStatus || {});

      // Reset local flow
      setPaid(false);
      setShowConfirm(false);
      setConfirmBusy(false);
      setConfirmSent(false);
      setConfirmErr(null);

      // Reset guards
      setFrozenPayment(null);
      setSending(false);
      setSentOnce(false);
      sentForCtxRef.current.clear();
      confirmedCtxSet.current.clear();
    }
  }, [toolOutput, ctxId]);

  const displayAmountLive = formatAmount(amount ?? details.amount);
  const displayCurrencyLive = currency || details.currency || "AUD";

  const effectiveCtxId = frozenPayment?.ctxId || ctxId;
  const effectiveKind = frozenPayment?.kind || kind;
  const effectiveAmount = frozenPayment?.amount || displayAmountLive;
  const effectiveCurrency = frozenPayment?.currency || displayCurrencyLive;
  const effectiveEmail = frozenPayment?.email || email;

  async function handleEmbeddedSuccess({ payment_intent_id } = {}) {
    setPaid(true);
    setStatus("paid");

    // Freeze values used for UI + follow-up so toolOutput refresh won't restart the flow
    setFrozenPayment({
      ctxId,
      kind,
      amount: displayAmountLive,
      currency: displayCurrencyLive,
      email,
      payment_intent_id: payment_intent_id || null,
    });

    if (!confirmedCtxSet.current.has(ctxId)) setShowConfirm(true);
  }

  /**
   * ✅ SIMPLIFIED: Just send follow-up message
   * Server handles duplicate blocking via ctx_id check in PENDING_*_CHECKOUTS
   */
  async function onConfirm() {
    if (!effectiveCtxId || confirmBusy || sending) return;

    // No duplicates per ctx
    if (sentForCtxRef.current.has(effectiveCtxId) || confirmedCtxSet.current.has(effectiveCtxId)) {
      setShowConfirm(false);
      return;
    }

    setConfirmBusy(true);
    setSending(true);
    setConfirmErr(null);

    try {
      confirmedCtxSet.current.add(effectiveCtxId);
      sentForCtxRef.current.add(effectiveCtxId);

      // ✅ Just send follow-up message - server blocks duplicate checkout calls via ctx_id
      const promptLines = [
        "Payment succeeded and booking is already confirmed server-side.",
        "",
        `Booking reference (ctx_id): ${effectiveCtxId}`,
        "",
        "Please call `confirm_booking_from_ctx` with this ctx_id to get booking details and send the final confirmation message to the user.",
      ].join("\n");

      await sendFollowUpMessage(promptLines);

      setConfirmSent(true);
      setSentOnce(true);
      setShowConfirm(false);
    } catch (e) {
      setConfirmErr(e.message || "Failed to send confirmation.");
      confirmedCtxSet.current.delete(effectiveCtxId);
      sentForCtxRef.current.delete(effectiveCtxId);
    } finally {
      setSending(false);
      setConfirmBusy(false);
    }
  }

  const itemName = effectiveKind === "flight" ? "Flight Booking" : hotelName || "Hotel Booking";

  return (
    <div className="sc-container">
      <ConfirmDialog
        open={showConfirm}
        kind={effectiveKind}
        ctxId={effectiveCtxId}
        onClose={() => setShowConfirm(false)}
        onConfirm={onConfirm}
        busy={confirmBusy || sending}
        error={confirmErr}
      />

      <div className="sc-layout">
        {/* Left Side - Order Summary (Dark) */}
        <div className="sc-summary">
          <div className="sc-summary-inner">
            <button className="sc-back-btn" type="button" aria-label="Back">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10 12L6 8l4-4" />
              </svg>
            </button>

            <div className="sc-merchant">
              <span className="sc-merchant-name">Payment</span>
            </div>

            <div className="sc-amount">
              <span className="sc-currency">{effectiveCurrency}</span>
              <span className="sc-amount-value">{effectiveAmount || "0.00"}</span>
            </div>

            <div className="sc-line-items">
              <div className="sc-line-item">
                <span className="sc-item-name">{itemName}</span>
                <span className="sc-item-price">
                  {effectiveCurrency} {effectiveAmount || "0.00"}
                </span>
              </div>

              {effectiveKind === "hotel" && roomName && (
                <div className="sc-line-item sc-line-item-sub">
                  <span className="sc-item-detail">Room: {roomName}</span>
                </div>
              )}
            </div>
          </div>

          <div className="sc-summary-footer">
            <div className="sc-powered">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor" opacity="0.6">
                <path d="M7 0C3.134 0 0 3.134 0 7s3.134 7 7 7 7-3.134 7-7-3.134-7-7-7zm0 1.5c3.038 0 5.5 2.462 5.5 5.5S10.038 12.5 7 12.5 1.5 10.038 1.5 7 3.962 1.5 7 1.5z" />
              </svg>
              <span>
                Powered by <strong>stripe</strong>
              </span>
            </div>
            <div className="sc-footer-links">
              <a href="#">Terms</a>
              <a href="#">Privacy</a>
            </div>
          </div>
        </div>

        {/* Right Side - Payment Form (Light) */}
        <div className="sc-payment">
          {confirmSent && (
            <div className="sc-success-banner">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="9" fill="#10b981" />
                <path d="M5.5 9l2.5 2.5 4.5-5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span>Confirmation sent to assistant</span>
            </div>
          )}

          {!paid && effectiveCtxId && effectiveAmount && effectiveCurrency && (
            <EmbeddedPayment
              ctxId={effectiveCtxId}
              type={effectiveKind}
              amount={effectiveAmount}
              currency={effectiveCurrency}
              email={effectiveEmail}
              onSuccess={handleEmbeddedSuccess}
            />
          )}

          {paid && (
            <div className="sc-paid-state">
              <div className="sc-paid-icon">
                <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
                  <circle cx="20" cy="20" r="20" fill="#10b981" />
                  <path d="M12 20l6 6 10-12" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <h3>Payment successful</h3>
              <p>Your {effectiveKind === "flight" ? "flight" : "hotel"} booking is confirmed.</p>
              <button className="sc-btn-primary" onClick={() => setShowConfirm(true)}>
                Continue
              </button>
            </div>
          )}

          {/* Diagnostic info */}
          <div className="sc-diag" aria-hidden="true" style={{ marginTop: 8, opacity: 0.55, fontSize: 11 }}>
            {caps.hasFollowUp ? "followUp " : ""}
            {frozenPayment ? "[FROZEN] " : ""}
            {sentOnce ? "[SENT] " : ""}
          </div>
        </div>
      </div>
    </div>
  );
}

const mount = document.getElementById("payment-card-root");
if (mount) {
  const root = createRoot(mount);
  root.render(<App />);
}

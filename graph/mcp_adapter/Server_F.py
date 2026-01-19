# graph/mcp_adapter/server.py
from __future__ import annotations

import os, sys, site, logging, json, re, traceback
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from datetime import datetime
from urllib.parse import urlencode
from time import time  

# --- import roots / .env ---
HERE = Path(__file__).resolve()
GRAPH_ROOT = HERE.parents[1]
if str(GRAPH_ROOT) not in sys.path:
    sys.path.insert(0, str(GRAPH_ROOT))

from dotenv import load_dotenv
load_dotenv(GRAPH_ROOT / ".env")   # load .../graph/.env (not parent)

# --- Stripe + Starlette ---
import stripe
from starlette.responses import RedirectResponse, PlainTextResponse,HTMLResponse,JSONResponse
from starlette.routing import Route
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.middleware.cors import CORSMiddleware 

# Duffle endpoints imports 
from src.duffel_client.endpoints.stays import create_quote, fetch_quote_details, create_booking
from src.duffel_client.endpoints.flights import (
    get_seat_maps,
    calculate_seat_costs,
    create_flight_booking,   
    fetch_flight_offer,      
)

# ---------- ephemeral checkout context cache ----------
CHECKOUT_CTX: Dict[str, dict] = {}
FLIGHT_CHECKOUT_CTX: Dict[str, dict] = {}
CHECKOUT_STATUS: Dict[str, dict] = {}  # shared status map for chat notification

# TTL for hosted checkout links (seconds)
CHECKOUT_TTL_SECONDS = int(os.getenv("CHECKOUT_TTL_SECONDS", "900"))          # 15 minutes default
FLIGHT_CHECKOUT_TTL_SECONDS = int(os.getenv("FLIGHT_CHECKOUT_TTL_SECONDS", "900"))


#  One-shot toggle to block the *next* search_hotels_ui
BLOCK_NEXT_HOTEL_SEARCH: bool = False

#  One-shot toggle to block the *next* search_flights_ui
BLOCK_NEXT_FLIGHT_SEARCH: bool = False
#  One-shot toggle to block the *next* fetch_hotel_rates_ui
BLOCK_NEXT_ROOM_RATES: bool = False

# One-shot toggle to block the *next* start_hotel_checkout
BLOCK_NEXT_HOTEL_CHECKOUT: bool = False

# One-shot toggle to block the *next* start_flight_checkout
BLOCK_NEXT_FLIGHT_CHECKOUT: bool = False

PENDING_FLIGHT_CHECKOUTS: dict[str, str] = {}  # Key: "flight:offer_id:email" -> ctx_id
PENDING_HOTEL_CHECKOUTS: dict[str, str] = {}   # Key: "hotel:rate_id:email" -> ctx_id

# ---------- simple validation helpers ----------
import re
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CURRENCY_WHITELIST = {"AUD"}
ZERO_DECIMAL = {"JPY", "KRW"}

# Basic phone sanity check (server-side guard, not as strict as libphonenumber)
PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{7,20}$")


from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware

# Global context variable to store HTTP request
_http_request: ContextVar = ContextVar('http_request', default=None)

# Middleware to capture the HTTP request
class CaptureRequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        _http_request.set(request)
        response = await call_next(request)
        return response

def _is_valid_phone(phone: str) -> bool:
    """
    Very basic phone validator.
    Accepts E.164-style or simple local-looking numbers:
    digits, spaces, dashes, and parentheses.
    """
    if not phone:
        return False
    return bool(PHONE_RE.match(phone))



STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY is not set. Expected it in graph/.env")

stripe.api_key = STRIPE_SECRET_KEY

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
SUCCESS_URL     = os.getenv("STRIPE_SUCCESS_URL", f"{PUBLIC_BASE_URL}/success")
CANCEL_URL      = os.getenv("STRIPE_CANCEL_URL", f"{PUBLIC_BASE_URL}/cancel")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")  # optional

# --- harden sys.path (avoid user-site shadowing) ---
try:
    USER_SITE = site.getusersitepackages()
except Exception:
    USER_SITE = None
if USER_SITE:
    sys.path[:] = [p for p in sys.path if not (p and p.startswith(USER_SITE))]
os.environ.setdefault("PYTHONNOUSERSITE", "1")

# --- import roots / .env (parent) ---
HERE = Path(__file__).resolve()
GRAPH_ROOT = HERE.parents[1]
if str(GRAPH_ROOT) not in sys.path:
    sys.path.insert(0, str(GRAPH_ROOT))

from dotenv import load_dotenv
load_dotenv(GRAPH_ROOT.parent / ".env")

# --- logging ---
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mcp_adapter")

# --- xxhash sanity (LangGraph likes this impl) ---
try:
    import xxhash as _xx
    assert hasattr(_xx, "xxh3_128_hexdigest")
except Exception:
    raise RuntimeError("Install xxhash wheel: pip install --only-binary=:all: xxhash>=3.5.0")

# --- MCP types ---
from mcp.server.fastmcp import FastMCP
from mcp import types

# --- import your LangGraph tool(s) ---
from src.agent.graph import (
    search_flights_tool,
    search_hotels_tool,
    fetch_hotel_rates_tool,
    get_seat_maps_tool,
    hotel_payment_sequence_tool,
    #  post-booking flights
    cancel_flight_booking_tool,
    change_flight_booking_tool,
    list_airline_initiated_changes_tool,
    accept_airline_initiated_change_tool,
    update_airline_initiated_change_tool,
    fetch_extra_baggage_options_tool,
    get_available_services_tool,

    #  post-booking hotels
    cancel_hotel_booking_tool,
    extend_hotel_stay_tool,
    update_hotel_booking_tool,

    #  utilities
    fetch_accommodation_reviews_tool,
    list_loyalty_programmes_tool,
    list_flight_loyalty_programmes_tool,
    validate_phone_number_tool,
    remember_tool,
    recall_tool,
)


# ============================================================================
# OAUTH AUTHENTICATION IMPORTS
# ============================================================================
try:
    from auth.clerk_oauth import ClerkOAuthProvider, get_config as get_clerk_config
    from auth.endpoints import get_oauth_routes
    from auth.mcp_auth import authenticate_mcp_request, AuthContext
    OAUTH_AVAILABLE = True
    log.info("OAuth module loaded successfully")
except ImportError as e:
    log.warning(f"OAuth module not available: {e}")
    OAUTH_AVAILABLE = False

# ---------- constants ----------
MIME_TYPE = "text/html+skybridge"
ASSETS_DIR = GRAPH_ROOT.parent / "ui-widgets" / "dist" / "assets"
ASSETS_BASE_URL = os.environ.get("ASSETS_BASE_URL", "http://localhost:4444/assets")

# ---------- helpers for interpreting the Ui-widgets ----------
def _pick_hashed_asset(assets_dir: Path, prefix: str, ext: str) -> str:
    files = sorted(assets_dir.glob(f"{prefix}-*.{ext}"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No {prefix}-*.{ext} in {assets_dir}")
    return files[-1].name

def _widget_html(root_id: str, css_url: str, js_url: str) -> str:
    return (
        f'<div id="{root_id}"></div>\n'
        f'<link rel="stylesheet" href="{css_url}">\n'
        f'<script type="module" src="{js_url}"></script>'
    )

def resolve_widget_html(name: str, root_id: str) -> str:
    """
    Try to load widget HTML from local assets.
    If local assets don't exist, return a remote-loading stub.
    """
    try:
        html_name = _pick_hashed_asset(ASSETS_DIR, name, "html")
        raw_html = (ASSETS_DIR / html_name).read_text(encoding="utf-8")
        return (
            raw_html
            .replace('src="/assets/', f'src="{ASSETS_BASE_URL}/')
            .replace('href="/assets/', f'href="{ASSETS_BASE_URL}/')
        )
    except FileNotFoundError:
        # Local assets not found - use remote URL fallback
        # This happens in production when ui-widgets is a separate service
        log.info(f"Local assets not found for {name}, using remote ASSETS_BASE_URL: {ASSETS_BASE_URL}")
        
        # Return a simple stub that loads from remote
        return (
            f'<div id="{root_id}"></div>\n'
            f'<link rel="stylesheet" href="{ASSETS_BASE_URL}/{name}.css">\n'
            f'<script type="module" src="{ASSETS_BASE_URL}/{name}.js"></script>'
        )
    except Exception as e:
        log.warning(f"Error resolving widget {name}: {e}")
        return (
            f'<div style="padding:12px;font-family:system-ui">'
            f'<b>{name} widget loading from remote...</b></div>'
        )

@dataclass(frozen=True)
class Widget:
    tool_name: str
    title: str
    template_uri: str
    root_id: str
    html: str

# flight ui declaration
FLIGHT = Widget(
    tool_name="flight-card",
    title="Show Flight Card",
    template_uri="ui://widget/flight-card.html",
    root_id="flight-card-root",
    html=resolve_widget_html("flight-card", "flight-card-root"),
)

# hotel ui declaration 
HOTEL = Widget(
    tool_name="hotel-card",
    title="Show Hotel Card",
    template_uri="ui://widget/hotel-card.html",
    root_id="hotel-card-root",
    html=resolve_widget_html("hotel-card", "hotel-card-root"),
)


# Room ui declaration
ROOM = Widget(
    tool_name="room-card",
    title="Show Room Card",
    template_uri="ui://widget/room-card.html",
    root_id="room-card-root",
    html=resolve_widget_html("room-card", "room-card-root"),
)

# Payment ui declaration
PAYMENT = Widget(
    tool_name="payment-card",
    title="Show Payment Status",
    template_uri="ui://widget/payment-card.html",
    root_id="payment-card-root",
    html=resolve_widget_html("payment-card", "payment-card-root"),
)


WIDGETS = {w.tool_name: w for w in (FLIGHT, HOTEL, ROOM, PAYMENT)}
URI_TO_WIDGET = {w.template_uri: w for w in WIDGETS.values()}


# Tool metadata ( used by the cgpt to call the tools )
def _tool_meta(w: Widget) -> Dict[str, Any]:
    return {
        "openai/outputTemplate": w.template_uri,
        "openai/toolInvocation/invoking": f"Rendering {w.title}…",
        "openai/toolInvocation/invoked": f"{w.title} rendered.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
        "annotations": {"destructiveHint": False, "openWorldHint": False, "readOnlyHint": True},
    }

# Ui-widgets resources 
def _embedded_widget_resource(w: Widget) -> types.EmbeddedResource:
    return types.EmbeddedResource(
        type="resource",
        resource=types.TextResourceContents(
            uri=w.template_uri,
            mimeType=MIME_TYPE,
            text=w.html,
            title=w.title,
        ),
    )


# ----------flight data  normalizers to feed Ui  ----------
def _iso_to_local_hm(iso_str: str) -> str:
    try:
        d = datetime.fromisoformat(iso_str.replace("Z", "+00:00")) if iso_str else None
        if not d:
            return ""
        try:
            return d.strftime("%-I:%M %p")
        except ValueError:
            return d.strftime("%#I:%M %p")  # Windows
    except Exception:
        m = re.search(r"T(\d{2}:\d{2})", iso_str or "")
        return m.group(1) if m else (iso_str or "")

def _weekday_date_from_iso(iso_str: str) -> tuple[str, str]:
    """
    Parse an ISO timestamp into:
      - weekday short name, e.g. "Mon"
      - date label, e.g. "22 Dec"
    """
    try:
        d = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return d.strftime("%a"), d.strftime("%d %b")
    except Exception:
        return "", ""


def _duration_label(total_minutes: int | None, fallback="—") -> str:
    if not isinstance(total_minutes, int) or total_minutes <= 0:
        return fallback
    h, m = divmod(total_minutes, 60)
    return f"{h}h {m}m" if m else f"{h}h"


# ============================================================================
# FIXED _normalize_any_to_flights function for server.py
# ============================================================================
#
# Replace the entire _normalize_any_to_flights function with this version.
# The key fixes:
# 1. Look for offers in data.data (Duffel nests inside "data" key)
# 2. Also look at owner.name for airline name
# 3. Better price extraction from Duffel's structure
#
# ============================================================================

def _normalize_any_to_flights(data: dict) -> dict:
    """
    Normalises various Duffel-like flight offer payloads into a simple list of
    cards that the FlightCard widget can render.
    """
    # Already-normalised form from our own widget (pass-through)
    if isinstance(data, dict) and isinstance(data.get("flights"), list):
        rows = data["flights"]
        if rows and (rows[0].get("airlineShort") or rows[0].get("depart") or rows[0].get("route")):
            if not any(bool(r.get("highlight")) for r in rows):
                rows[0]["highlight"] = True
            return {"flights": rows, "meta": data.get("meta") or {}}
        src = rows
    elif isinstance(data, dict) and isinstance(data.get("offers"), list):
        src = data["offers"]
    # ✅ FIX: Duffel returns offers in data.data, not data.offers
    elif isinstance(data, dict) and isinstance(data.get("data"), list):
        src = data["data"]
    elif isinstance(data, dict) and isinstance((data.get("data") or {}).get("offers"), list):
        src = data["data"]["offers"]
    else:
        return {"flights": [], "meta": {"total": 0}}

    norm: list[dict] = []
    origin = destination = date_str = ""
    return_date_str = ""

    for i, item in enumerate(src):
        log.info(f"Duffel offer #{i} raw data: {json.dumps(item, indent=2)}")
        offer_id = item.get("id") or item.get("offer_id") or f"offer_{i}"

        # ✅ FIX: Duffel uses "owner" object with "name" for airline
        owner = item.get("owner") or {}
        airline = (
            item.get("airline")
            or (owner.get("name") if isinstance(owner, dict) else owner)
            or item.get("airline_code")
            or "Airline"
        )
        
        # ✅ FIX: Duffel uses owner.logo_symbol_url or owner.logo_lockup_url
        airline_logo = (
            item.get("airline_logo")
            or (owner.get("logo_symbol_url") if isinstance(owner, dict) else None)
            or (owner.get("logo_lockup_url") if isinstance(owner, dict) else None)
            or (item.get("marketing_carrier") or {}).get("logo")
            or (item.get("marketing_carrier") or {}).get("logo_url")
            or None
        )

        # --- slices: outbound + (optional) inbound ---
        slices = item.get("slices") or []
        outbound_slice = slices[0] if slices else {}
        return_slice = slices[1] if len(slices) > 1 else None

        def _first_last(sl: dict) -> tuple[dict, dict]:
            segs = sl.get("segments") or []
            if not segs:
                return {}, {}
            return segs[0], segs[-1]

        # Outbound leg
        first, last = _first_last(outbound_slice) if outbound_slice else ({}, {})
        dep_iso = (
            first.get("departing_at")
            or first.get("depart_at")
            or first.get("departure_time")
            or ""
        )
        arr_iso = (
            last.get("arriving_at")
            or last.get("arrive_at")
            or last.get("arrival_time")
            or ""
        )

        depart = _iso_to_local_hm(dep_iso) if dep_iso else ""
        arrive = _iso_to_local_hm(arr_iso) if arr_iso else ""
        weekday, outbound_date_only = _weekday_date_from_iso(dep_iso or arr_iso or "")

        org = (
            (first.get("origin") or {}).get("iata_code")
            if isinstance(first.get("origin"), dict)
            else first.get("origin")
        ) or ""
        dst = (
            (last.get("destination") or {}).get("iata_code")
            if isinstance(last.get("destination"), dict)
            else last.get("destination")
        ) or ""

        # Inbound leg (if present)
        ret_depart = ret_arrive = ""
        ret_route = ""
        ret_weekday = ""
        ret_date_only = ""
        if return_slice:
            r_first, r_last = _first_last(return_slice)
            r_dep_iso = (
                r_first.get("departing_at")
                or r_first.get("depart_at")
                or r_first.get("departure_time")
                or ""
            )
            r_arr_iso = (
                r_last.get("arriving_at")
                or r_last.get("arrive_at")
                or r_last.get("arrival_time")
                or ""
            )

            ret_depart = _iso_to_local_hm(r_dep_iso) if r_dep_iso else ""
            ret_arrive = _iso_to_local_hm(r_arr_iso) if r_arr_iso else ""
            ret_weekday, ret_date_only = _weekday_date_from_iso(r_dep_iso or r_arr_iso or "")

            r_org = (
                (r_first.get("origin") or {}).get("iata_code")
                if isinstance(r_first.get("origin"), dict)
                else r_first.get("origin")
            ) or ""
            r_dst = (
                (r_last.get("destination") or {}).get("iata_code")
                if isinstance(r_last.get("destination"), dict)
                else r_last.get("destination")
            ) or ""

            ret_route = f"{r_org}–{r_dst}" if r_org and r_dst else ""

            if not return_date_str and ret_date_only:
                return_date_str = ret_date_only

        if not origin and org:
            origin = org
        if not destination and dst:
            destination = dst
        if not date_str and outbound_date_only:
            date_str = outbound_date_only

        if org and dst:
            route = f"{org}–{dst}"
            if ret_route:
                route = f"{route} / {ret_route}"
        else:
            route = ""

        date_display = outbound_date_only
        if ret_date_only and ret_date_only != outbound_date_only:
            date_display = f"{outbound_date_only} → {ret_date_only}"

        # Duration
        total_mins = None
        if isinstance(outbound_slice, dict):
            total_mins = (
                outbound_slice.get("journey_duration_minutes")
                or outbound_slice.get("duration_minutes")
            )

        if total_mins is None:
            dur_txt = (
                (outbound_slice.get("duration") if isinstance(outbound_slice, dict) else "")
                or item.get("total_journey_duration")
                or item.get("total_duration")
                or ""
            )
            m1 = re.search(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?", (dur_txt or "").lower())
            if m1 and (m1.group(1) or m1.group(2)):
                h = int(m1.group(1) or 0)
                m = int(m1.group(2) or 0)
                total_mins = h * 60 + m
            else:
                hh = re.search(r"(\d+)H", dur_txt)
                mm = re.search(r"(\d+)M", dur_txt)
                total_mins = (
                    (int(hh.group(1)) * 60 if hh else 0)
                    + (int(mm.group(1)) if mm else 0)
                )
                if total_mins == 0:
                    total_mins = None

        # ✅ FIX: Better price extraction - Duffel uses total_amount/total_currency
        total_amount = (
            item.get("total_amount")      # Duffel primary
            or item.get("price")
            or item.get("amount")
            or item.get("base_amount")
            or ""
        )
        total_currency = (
            item.get("total_currency")    # Duffel primary
            or item.get("currency")
            or item.get("price_currency")
            or item.get("base_currency")
            or ""
        )
        
        # Format price string
        price_str = ""
        if total_amount:
            try:
                amt = float(total_amount)
                ccy = str(total_currency).upper() if total_currency else ""
                # Format as "$107" or "$107.94"
                if amt == int(amt):
                    price_str = f"${int(amt)}"
                else:
                    price_str = f"${amt:.2f}"
            except (ValueError, TypeError):
                if total_currency:
                    price_str = f"{total_currency} {total_amount}"
                else:
                    price_str = str(total_amount)
        
        # ✅ FIX: Tax extraction - Duffel uses tax_amount/tax_currency
        tax_amount = item.get("tax_amount") or item.get("tax") or ""
        tax_str = ""
        if tax_amount:
            try:
                tax_f = float(tax_amount)
                if tax_f == int(tax_f):
                    tax_str = f"incl. ${int(tax_f)} tax"
                else:
                    tax_str = f"incl. ${tax_f:.2f} tax"
            except (ValueError, TypeError):
                tax_str = f"incl. {tax_amount} tax"
        elif total_amount:
            # Estimate ~10% tax if not provided
            try:
                est_tax = float(total_amount) * 0.1
                tax_str = f"incl. ~${int(est_tax)} tax"
            except:
                pass

        norm.append({
            "id": offer_id,
            "airlineShort": airline,
            "airlineLogo": airline_logo,
            "weekday": weekday,
            "date": date_display,
            "depart": depart,
            "arrive": arrive,
            "route": route,
            "duration": _duration_label(total_mins),
            "highlight": bool(item.get("highlight")) or (i == 0),
            "price": price_str,           # ✅ Now properly extracted
            "tax": tax_str,               # ✅ Now properly extracted
            "returnWeekday": ret_weekday,
            "returnDate": ret_date_only,
            "returnDepart": ret_depart,
            "returnArrive": ret_arrive,
            "returnRoute": ret_route,
        })

    return {
        "flights": norm,
        "meta": {
            "total": len(norm),
            "origin": origin,
            "destination": destination,
            "date": date_str or None,
            "return_date": return_date_str or None,
        },
    }

def _format_price(amount: Any, currency: str | None) -> Tuple[str, float | None, str | None]:
    if amount is None or not currency:
        return ("", None, currency)
    try:
        f = float(amount)
        return (f"{currency} {f:.2f}", f, currency)
    except Exception:
        return (f"{currency} {amount}", None, currency)


# ------------------ Hotel data  normalizers to feed Ui-----------------------------------
def _beds_to_label(beds: Any) -> str:
    if not isinstance(beds, list):
        return ""
    parts = []
    for b in beds:
        if isinstance(b, dict):
            t = str(b.get("type", "")).replace("_", " ").title().strip()
            c = b.get("count")
            parts.append(f"{c} {t}".strip() if c else t)
        else:
            parts.append(str(b))
    return ", ".join(p for p in parts if p)

def _room_media(room: Dict[str, Any], acc_photos: List[str]) -> List[str]:
    media = room.get("photos") or room.get("images") or []
    out = []
    if isinstance(media, list):
        for m in media:
            if isinstance(m, str):
                out.append(m)
            elif isinstance(m, dict) and isinstance(m.get("url"), str):
                out.append(m["url"])
    if not out and acc_photos:
        out = acc_photos[:]
    return out[:6]

def _rate_cancel_label(rate: Dict[str, Any]) -> str:
    cancel = rate.get("cancellation_policy") or rate.get("refundability") or ""
    tl = rate.get("cancellation_timeline")
    if isinstance(tl, list) and tl:
        latest = None
        for ent in tl:
            when = ent.get("before")
            if when and (latest is None or when > latest):
                latest = when
        if latest:
            cancel = f"Refundable until {latest}"
    return cancel

def _pluck_price_fields(rate: Dict[str, Any]) -> Tuple[str, float | None, str | None]:
    amt = rate.get("total_amount") or rate.get("public_amount") or rate.get("base_amount")
    ccy = rate.get("total_currency") or rate.get("public_currency") or rate.get("base_currency") or rate.get("currency")
    return _format_price(amt, ccy)

def _parse_json_lenient(s: str) -> Dict[str, Any]:
    if not isinstance(s, str):
        return {}
    try:
        return json.loads(s)
    except Exception:
        try:
            start = s.find("{"); end = s.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(s[start:end+1])
        except Exception:
            pass
    return {}

def _acc_photos_list(acc: Dict[str, Any]) -> List[str]:
    ph = acc.get("photos") or []
    out = []
    if isinstance(ph, list):
        for p in ph:
            if isinstance(p, str):
                out.append(p)
            elif isinstance(p, dict) and isinstance(p.get("url"), str):
                out.append(p["url"])
    return out[:6]

def _normalize_any_to_room_rates(data: dict | str, hotel_ctx: dict | None = None) -> dict:
    if isinstance(data, str):
        data = _parse_json_lenient(data)
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        inner = _parse_json_lenient(data["result"])
        if inner:
            data = inner
    payload = data.get("data", data) if isinstance(data, dict) else {}

    rooms_out: List[Dict[str, Any]] = []

    acc = (payload.get("accommodation") or {})
    rooms_list = None
    if isinstance(payload.get("rooms"), list):
        rooms_list = payload["rooms"]
    elif isinstance(acc.get("rooms"), list):
        rooms_list = acc["rooms"]
    else:
        rooms_list = []

    acc_photos = _acc_photos_list(acc)

    if isinstance(rooms_list, list) and rooms_list:
        for i, room in enumerate(rooms_list):
            room_name = room.get("name") or ""
            bed = _beds_to_label(room.get("beds"))
            photos = _room_media(room, acc_photos)

            for j, rate in enumerate(room.get("rates") or []):
                rid = rate.get("id") or f"rat_{i}_{j}"
                price_label, price_num, price_ccy = _pluck_price_fields(rate)
                board = rate.get("board_type") or rate.get("board") or rate.get("meal_plan") or ""
                cancel = _rate_cancel_label(rate)
                qty = rate.get("quantity_available")

                rooms_out.append({
                    "id": rid,
                    "name": room_name or rate.get("name") or "Room",
                    "price": price_label,
                    "price_amount": price_num,
                    "currency": price_ccy,
                    "bed": bed,
                    "board": board,
                    "cancellation": cancel,
                    "quantity": qty,
                    "photos": photos,
                })

    if not rooms_out and isinstance(payload, dict):
        possible_buckets = [payload, payload.get("data") or {}]
        rates = []
        for bucket in possible_buckets:
            for key in ("rates", "room_rates", "room_offers", "offers"):
                v = bucket.get(key)
                if isinstance(v, list) and v:
                    rates = v
                    break
            if rates:
                break

        for idx, r in enumerate(rates or []):
            rid = r.get("id") or f"rat_{idx}"
            price_label, price_num, price_ccy = _pluck_price_fields(r)
            bed = _beds_to_label(r.get("beds"))
            if not bed:
                bed = r.get("bed_type") or r.get("bed") or ""
            board = r.get("board_type") or r.get("board") or r.get("meal_plan") or ""
            cancel = _rate_cancel_label(r)

            photos = []
            for key in ("images", "photos", "media"):
                lst = r.get(key)
                if isinstance(lst, list):
                    for x in lst[:6]:
                        if isinstance(x, str):
                            photos.append(x)
                        elif isinstance(x, dict) and isinstance(x.get("url"), str):
                            photos.append(x["url"])
                    break
            if not photos and acc_photos:
                photos = acc_photos[:]

            rooms_out.append({
                "id": rid,
                "name": r.get("room_name") or r.get("room_type") or r.get("name") or f"Room {idx+1}",
                "price": price_label,
                "price_amount": price_num,
                "currency": price_ccy,
                "bed": bed,
                "board": board,
                "cancellation": cancel,
                "photos": photos,
            })

    rooms_out.sort(key=lambda x: (x.get("price_amount") is None, x.get("price_amount") or 9e18))
    if rooms_out:
        rooms_out[0]["highlight"] = True
        for k in range(1, len(rooms_out)):
            rooms_out[k]["highlight"] = False

    addr = (acc.get("location") or {}).get("address") or {}
    meta = {
        "hotelName": (hotel_ctx or {}).get("hotel_name") or acc.get("name") or payload.get("name") or "",
        "location": (hotel_ctx or {}).get("location") or addr.get("city_name") or addr.get("line_one") or "",
        "srr": (hotel_ctx or {}).get("search_result_id") or (hotel_ctx or {}).get("srr") or payload.get("id") or "",
        "message": (hotel_ctx or {}).get("message") or "",
        "count": len(rooms_out),
    }

    return {"rooms": rooms_out, "meta": meta}

def _normalize_any_to_hotels(data: dict | str) -> dict:
    """
    Accepts:
      A) dict with {"hotels":[...]}
      B) dict with {"result": "<stringified json>"}
      C) already-normalized {"hotels":[{...}]}
    Returns:
      {"hotels":[{id,name,city,rating,price,photo,amenities,srr,search_result_id}] , "meta":{...}}
    """
    # If it's a string, try to parse once
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return {"hotels": [], "meta": {"summary": str(data), "count": 0, "showing": 0}}

    # If it has a .result JSON string (some backends return this), parse again
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        try:
            data = json.loads(data["result"])
        except Exception:
            data = {}

    hotels_in = (data or {}).get("hotels") or []
    if not isinstance(hotels_in, list):
        hotels_in = []

    def _price_str(p):
        if isinstance(p, str):
            return p
        if isinstance(p, dict):
            amt = p.get("amount") or p.get("value") or p.get("total_amount") or p.get("price")
            ccy = p.get("currency") or p.get("currency_code") or p.get("total_currency") or p.get("price_currency")
            try:
                if amt is not None and ccy:
                    return f"{ccy} {float(amt):.2f}"
            except Exception:
                pass
        return ""

    hotels_out = []
    for i, h in enumerate(hotels_in):
        # Expose Duffel SRR (or similar) if present
        srr_value = (
            h.get("search_result_id")
            or h.get("srr")
            or (h.get("id") if isinstance(h.get("id"), str) and h.get("id", "").startswith("srr_") else None)
        )

        hotels_out.append({
            "id": h.get("id") or f"hotel_{i}",      # keep hotel id here (not SRR)
            "name": h.get("name") or "Hotel",
            "city": h.get("location") or h.get("city") or "",
            "rating": (float(h.get("rating")) if h.get("rating") is not None else None),
            "price": _price_str(h.get("price")),
            "photo": h.get("image") or h.get("photo") or (h.get("images", []) or [None])[0],
            "amenities": h.get("amenities") or [],
            "highlight": bool(h.get("highlight")),
            # explicitly expose SRR for the UI
            "srr": srr_value,
            "search_result_id": srr_value,
        })

    meta = {
        "summary": (data or {}).get("summary") or "",
        "count": (data or {}).get("count") or len(hotels_out),
        "showing": (data or {}).get("showing") or len(hotels_out),
    }
    return {"hotels": hotels_out, "meta": meta}



def _to_duffel_seatmaps(sm):
    if not sm: return None
    if isinstance(sm, dict):
        raw = sm.get("raw_data")
        if isinstance(raw, dict) and isinstance(raw.get("data"), list):
            return {"data": raw["data"]}
        if isinstance(sm.get("data"), list):
            return {"data": sm["data"]}
    if isinstance(sm, list):
        return {"data": sm}
    return None

def _collect_passenger_ids_from_seatmaps(seat_maps):
    ids = set()
    for sm in (seat_maps or {}).get("data", []):
        for cab in sm.get("cabins", []):
            for row in cab.get("rows", []):
                for sec in row.get("sections", []):
                    for el in sec.get("elements", []):
                        for svc in (el.get("available_services") or []):
                            pid = svc.get("passenger_id")
                            if pid: ids.add(pid)
    return [{"id": pid} for pid in ids]

# ---------- payment helpers (server-only) ----------
def _extract_amount_currency(payload: dict, args_dict: dict) -> tuple[str | None, str | None]:
    """
    Find amount/currency in typical locations or fall back to caller hints.
    Returns normalized (amount_str, currency_upper) or (None, None).
    """
    amount, ccy = None, None
    if isinstance(payload, dict):
        amount = payload.get("amount") or amount
        ccy = payload.get("currency") or ccy
        data = payload.get("data") or {}
        amount = data.get("amount") or amount
        ccy = data.get("currency") or ccy
        md = payload.get("metadata") or {}
        amount = md.get("amount") or amount
        ccy = md.get("currency") or ccy
    amount = args_dict.get("amount") if (amount is None) else amount
    ccy = args_dict.get("currency") if (ccy is None) else ccy
    try:
        if amount is not None:
            amount = str(float(amount))
    except Exception:
        amount = str(amount) if amount is not None else None
    ccy = (str(ccy).upper() if ccy else None)
    return amount, ccy

def _build_checkout_url(amount: str | None, currency: str | None, rate_id: str | None, email: str, desc: str) -> str | None:
    if not amount or not currency:
        return None
    public_base = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    params = {
        "amount": amount,
        "currency": currency,
        "rate_id": rate_id or "unknown_rate",
        "email": email or "",
        "desc": desc or f"Hotel rate: {rate_id}",
    }
    return f"{public_base}/checkout?{urlencode(params)}"

def error_result(msg: str):
    from mcp import types
    return types.ServerResult(types.CallToolResult(
        content=[types.TextContent(type="text", text=msg)],
        isError=True,
    ))

#--------------- seat map data  normalizers to feed Ui --------------------- ( but we wont use it , no ui for seat map)
def normalize_seat_maps(seat_maps_raw) -> tuple[list, int]:
    """
    Normalize Duffel seat maps from get_seat_maps(...) into a simple list.
    ...
    """
    available: list[dict] = []
    total = 0

    # Prefer formatted_seats; fall back if needed
    data = (
        seat_maps_raw.get("formatted_seats")
        or seat_maps_raw.get("available_seats")
        or seat_maps_raw.get("data")
        or []
    )

    for seat in data:
        if not seat.get("available"):
            continue

        total += 1

        designator = seat.get("designator") or seat.get("seat") or seat.get("label")
        position = None
        if isinstance(designator, str) and designator:
            # Very rough heuristic: map last letter to window/aisle/middle
            letter = designator[-1].upper()
            if letter in ("A", "F", "K", "L"):
                position = "window"
            elif letter in ("C", "D", "G", "H"):
                position = "aisle"
            elif letter in ("B", "E"):
                position = "middle"

        available.append({
            "service_id": seat.get("service_id"),
            "label": designator,
            "cabin": seat.get("cabin_class") or seat.get("cabin"),
            "position": position,
            "price": str(seat.get("price") or seat.get("amount") or "0"),
            "currency": (seat.get("currency") or "").upper(),
        })

    return available, total

# ---------- MCP app ----------
mcp = FastMCP(
    name="BookedAI",
    sse_path="/mcp",
    message_path="/mcp/messages",
    stateless_http=True,
)

# ---------- list tools (Registering All the tools and it Resources )----------
@mcp._mcp_server.list_tools()
async def _list_tools() -> List[types.Tool]:
    return [
        # search_flights_ui tool
        types.Tool(
            name="search_flights_ui",
            title="Search Flights (render FlightCard)",
            description=(
                "Search for flights and render results. "
                "After results are shown, ask the user to SELECT which flight they want. "
                "Do NOT ask for passenger details or seat preferences until they choose a flight."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "slices": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "origin": {"type": "string"},
                                "destination": {"type": "string"},
                                "departure_date": {"type": "string"},
                            },
                            "required": ["origin", "destination", "departure_date"],
                        },
                    },
                    "passengers": {"type": "integer", "default": 1},
                    "cabin_class": {"type": "string", "default": "economy"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["slices"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": True,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Searching flights…",
                "openai/toolInvocation/invoked": "Flights ready.",
                "openai/outputTemplate": FLIGHT.template_uri,
            },
        ),

        # search_hotels_ui
        types.Tool(
            name="search_hotels_ui",
            title="Search Hotels (render HotelCard)",
            description="Calls LangGraph search_hotels_tool and renders a horizontal HotelCard strip.",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "check_in_date": {"type": "string"},
                    "check_out_date": {"type": "string"},
                    "adults": {"type": "integer", "default": 1},
                    "children": {"type": "integer", "default": 0},
                    "max_results": {"type": "integer", "default": 10},
                    "hotel_name": {"type": "string"},
                },
                "required": ["location", "check_in_date", "check_out_date"],
                "additionalProperties": True,
            },
            _meta={
                "openai/resultCanProduceWidget": True,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Searching hotels…",
                "openai/toolInvocation/invoked": "Hotels ready.",
                "openai/outputTemplate": HOTEL.template_uri,
            },
        ),

        # Room-card Tool
        types.Tool(
            name="fetch_hotel_rates_ui",
            title="Fetch Hotel Room Rates (render RoomCard)",
            description="Given a hotel's search_result_id (srr_...), fetch room/rate options and render a horizontal RoomCard strip.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search_result_id": {"type": "string"},
                    "hotel_name": {"type": "string"},
                    "location": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["search_result_id"],
                "additionalProperties": True,
            },
            _meta={
                "openai/resultCanProduceWidget": True,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Fetching room rates…",
                "openai/toolInvocation/invoked": "Room rates ready.",
                "openai/outputTemplate": ROOM.template_uri,
            },
        ),
                types.Tool(
            name="start_hotel_checkout",
            title="Start hotel payment (return clickable Stripe Checkout URL)",
            description=(
                "Builds a Stripe Checkout link for a selected room and returns a clickable URL in the chat. "
                "Does not collect cards in chat. Opens in a new tab. "
                "IMPORTANT: After calling this tool, WAIT for the user to complete payment. "
                "Do NOT call this tool again until a new booking is requested."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "rate_id":  {"type": "string"},
                    "email":    {"type": "string"},
                    "phone_number":{"type":"string"},
                    "guests": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "given_name": {"type": "string"},
                                "family_name": {"type": "string"},
                                "phone_number": {"type": "string"}
                            },
                            "required": ["given_name", "family_name"]
                        },
                        "description": "At least one guest."
                    },
                    "search_result_id":{"type":"string"},
                    "stay_special_requests":{"type":"string"},
                    "hotel_name":{"type":"string"},
                    "room_name":{"type":"string"},
                    "desc":{"type":"string"}
                },
                "required":["rate_id","email","guests","phone_number"],
                "additionalProperties":True,
            },
            # ✅ ADD THIS: Standard MCP annotations (without openai/ prefix)
            annotations={
                "readOnlyHint": False,      # This tool creates a checkout (not read-only)
                "destructiveHint": False,   # Not destructive (doesn't delete data)
                "openWorldHint": False,     # ✅ KEY: Set to False to prevent re-invocation
                "idempotentHint": False,    # Not idempotent (creates new checkout each time)
            },
            _meta={
                "openai/resultCanProduceWidget": True,  # ✅ Changed to True - it produces PaymentCard
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Preparing Stripe Checkout…",
                "openai/toolInvocation/invoked": "Stripe Checkout ready. Please complete payment in the form above.",
                "openai/outputTemplate": PAYMENT.template_uri,
                # ✅ ADD: Annotations also in _meta for compatibility
                "annotations": {
                    "readOnlyHint": False,
                    "destructiveHint": False,
                    "openWorldHint": False,
                    "idempotentHint": False,
                },
            },
        ),
        types.Tool(
            name="finalize_hotel_checkout",
            title="Finalize hotel booking after Stripe Checkout",
            description=(
                "Given a Stripe Checkout session_id (from the success URL), verify payment "
                "and complete the hotel booking, then return booking details."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "rate_id": {"type": "string"},
                    "guests": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "given_name": {"type": "string"},
                                "family_name": {"type": "string"}
                            },
                            "required": ["given_name", "family_name"]
                        }
                    },
                    "email": {"type": "string"},
                    "quote_id": {"type": "string"}
                },
                "required": ["session_id", "rate_id", "guests", "email","phone_number"],
                "additionalProperties": True
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Verifying Stripe payment…",
                "openai/toolInvocation/invoked": "Booking confirmed.",
            },
        ),
        types.Tool(
            name="get_seat_maps_tool",
            title="Fetch available seats for a flight offer",
            description=(
                "Fetch available seats for a flight offer. Use this when the user wants to select a seat.\\n\\n"
                "WHEN TO USE:\\n"
                "- User said seat preference is aisle/middle/window (not 'none')\\n"
                "- Call this BEFORE start_flight_checkout\\n\\n"
                "AFTER CALLING:\\n"
                "- Show the user available seats matching their preference\\n"
                "- Ask them to pick a seat by service_id (ase_...)\\n"
                "- Then call start_flight_checkout with selected_seats"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "offer_id": {"type": "string", "description": "The flight offer ID (off_...)"},
                },
                "required": ["offer_id"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Fetching seat maps…",
                "openai/toolInvocation/invoked": "Seat maps ready.",
            },
        ),
        types.Tool(
            name="start_flight_checkout",
            title="Start flight payment (Stripe Checkout)",
            description=(
                "Create Stripe Checkout for a flight booking.\\n\\n"
                "PREREQUISITES - Collect these BEFORE calling:\\n"
                "1. offer_id (from select_flight_offer)\\n"
                "2. Passenger details (given_name, family_name, born_on)\\n"
                "3. Contact info (email, phone_number)\\n"
                "4. If user wanted seats: selected_seats from get_seat_maps_tool\\n\\n"
                "This tool creates the payment link and renders the PaymentCard widget.\\n\\n"
                "IMPORTANT: After calling this tool, WAIT for the user to complete payment. "
                "Do NOT call this tool again until a new booking is requested."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "offer_id": {"type": "string"},
                    "passengers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "given_name": {"type": "string"},
                                "family_name": {"type": "string"},
                                "born_on": {"type": "string"},
                                "email": {"type": "string"},
                                "phone_number": {"type": "string"},
                            },
                            "required": ["given_name", "family_name", "born_on"],
                        },
                        "description": "At least one passenger.",
                    },
                    "email": {"type": "string"},
                    "phone_number": {"type": "string"},
                    "selected_seats": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "service_id": {"type": "string"},
                                "label": {"type": "string"},
                            },
                            "required": ["service_id"],
                            "additionalProperties": True,
                        },
                        "description": "Optional. Seats selected via get_seat_maps_tool.",
                    },
                },
                "required": ["offer_id", "passengers", "email", "phone_number"],
                "additionalProperties": True,
            },
            # ✅ ADD THIS: Standard MCP annotations (without openai/ prefix)
            annotations={
                "readOnlyHint": False,      # This tool creates a checkout (not read-only)
                "destructiveHint": False,   # Not destructive (doesn't delete data)
                "openWorldHint": False,     # ✅ KEY: Set to False to prevent re-invocation
                "idempotentHint": False,    # Not idempotent (creates new checkout each time)
            },
            _meta={
                "openai/resultCanProduceWidget": True,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Preparing Stripe Checkout…",
                "openai/toolInvocation/invoked": "Stripe Checkout ready. Please complete payment in the form above.",
                "openai/outputTemplate": PAYMENT.template_uri,
                # ✅ ADD: Annotations also in _meta for compatibility
                "annotations": {
                    "readOnlyHint": False,
                    "destructiveHint": False,
                    "openWorldHint": False,
                    "idempotentHint": False,
                },
            },
        ),
        # --- Post-booking flights ---
        types.Tool(
            name="cancel_flight_booking_tool",
            title="Cancel a flight booking",
            description=(
                "Cancel an existing flight booking (Duffel order). "
                "Use only after the user confirms they want to cancel and accepts any penalties."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Duffel order ID of the booking to cancel (ord_...).",
                    },
                    "proceed_despite_warnings": {
                        "type": "boolean",
                        "description": (
                            "Set true only after you’ve shown any fees/penalties to the user "
                            "and they confirm they still want to cancel."
                        ),
                        "default": False,
                    },
                },
                "required": ["order_id"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Requesting flight cancellation…",
                "openai/toolInvocation/invoked": "Flight cancellation response received.",
            },
        ),

        types.Tool(
            name="change_flight_booking_tool",
            title="Change an existing flight booking",
            description=(
                "Begin a change request for an existing flight booking (Duffel order). "
                "Provide the new slices (origin, destination, departure_date, etc.)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Existing Duffel order ID (ord_...).",
                    },
                    "slices": {
                        "type": "array",
                        "description": "New itinerary slices for the updated booking.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "origin": {"type": "string"},
                                "destination": {"type": "string"},
                                "departure_date": {"type": "string"},
                            },
                            "required": ["origin", "destination", "departure_date"],
                        },
                    },
                    "type": {
                        "type": "string",
                        "description": "Change mode, e.g. 'update' or 'change'.",
                        "default": "update",
                    },
                    "cabin_class": {
                        "type": "string",
                        "description": "Cabin class for re-pricing, e.g. economy, business.",
                    },
                },
                "required": ["order_id", "slices"],
                "additionalProperties": True,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Requesting flight change…",
                "openai/toolInvocation/invoked": "Flight change quote received.",
            },
        ),

                types.Tool(
            name="select_hotel_result",
            title="User selected a hotel result",
            description=(
                "Record which hotel search result the user picked in the UI. "
                "After this tool is called, the assistant should typically call "
                "`fetch_hotel_rates_ui` with the provided search_result_id to "
                "show room options."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "search_result_id": {
                        "type": "string",
                        "description": "Duffel search_result_id (srr_...) for the hotel."
                    },
                    "hotel_id": {"type": "string"},
                    "hotel_name": {"type": "string"},
                    "location": {"type": "string"},
                    "price": {"type": "string"},
                    "rating": {"type": "number"},
                    "amenities": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["search_result_id"],
                "additionalProperties": True,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
            },
        ),


        types.Tool(
            name="list_airline_initiated_changes_tool",
            title="List airline-initiated changes",
            description=(
                "List any airline-initiated change proposals (schedule changes, reroutes) "
                "associated with the current context."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Fetching airline-initiated changes…",
                "openai/toolInvocation/invoked": "Airline-initiated changes listed.",
            },
        ),

                types.Tool(
            name="confirm_booking_from_ctx",
            title="Confirm a paid checkout and thank the user",
            description=(
                "Given a checkout ctx_id that has status=paid in CHECKOUT_STATUS, "
                "returns a concise confirmation and thank-you message. "
                "Use this after Stripe payment is complete."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ctx_id": {
                        "type": "string",
                        "description": (
                            "Checkout context id returned by start_hotel_checkout "
                            "or start_flight_checkout."
                        ),
                    },
                },
                "required": ["ctx_id"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Finalising booking confirmation…",
                "openai/toolInvocation/invoked": "Booking confirmation ready.",
            },
        ),


        types.Tool(
            name="accept_airline_initiated_change_tool",
            title="Accept an airline-initiated change",
            description=(
                "Accept a specific airline-initiated change proposal, using the change_id "
                "returned from list_airline_initiated_changes_tool."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "change_id": {
                        "type": "string",
                        "description": "The airline change proposal ID to accept.",
                    },
                },
                "required": ["change_id"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Accepting airline-initiated change…",
                "openai/toolInvocation/invoked": "Airline-initiated change accepted.",
            },
        ),

        types.Tool(
            name="update_airline_initiated_change_tool",
            title="Update an airline-initiated change",
            description=(
                "Update an airline-initiated change (e.g. accept/reject or provide preferences) "
                "by passing a change_id and a data payload."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "change_id": {
                        "type": "string",
                        "description": "The airline change proposal ID to update.",
                    },
                    "data": {
                        "type": "object",
                        "description": "Change update payload (e.g. user action / notes).",
                    },
                },
                "required": ["change_id", "data"],
                "additionalProperties": True,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Updating airline-initiated change…",
                "openai/toolInvocation/invoked": "Airline-initiated change updated.",
            },
        ),

        types.Tool(
            name="fetch_extra_baggage_options_tool",
            title="Fetch extra baggage options",
            description="Fetch extra paid baggage options for a priced flight offer (Duffel offer_id).",
            inputSchema={
                "type": "object",
                "properties": {
                    "offer_id": {
                        "type": "string",
                        "description": "Duffel offer ID to price extra baggage for (off_...).",
                    },
                },
                "required": ["offer_id"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Fetching extra baggage options…",
                "openai/toolInvocation/invoked": "Extra baggage options returned.",
            },
        ),

        types.Tool(
            name="get_available_services_tool",
            title="Fetch other ancillary services for a flight offer",
            description="Fetch other available services for a Duffel offer (seats, bags, etc.).",
            inputSchema={
                "type": "object",
                "properties": {
                    "offer_id": {
                        "type": "string",
                        "description": "Duffel offer ID to fetch services for (off_...).",
                    },
                },
                "required": ["offer_id"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Fetching available services…",
                "openai/toolInvocation/invoked": "Available services returned.",
            },
        ),

        # --- Post-booking hotels ---
        types.Tool(
            name="cancel_hotel_booking_tool",
            title="Cancel a hotel booking",
            description=(
                "Cancel an existing hotel booking. Use only after the user confirms they want "
                "to cancel and accepts any penalties."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "booking_id": {
                        "type": "string",
                        "description": "Hotel booking ID to cancel.",
                    },
                    "proceed_despite_warnings": {
                        "type": "boolean",
                        "description": (
                            "Set true only after you’ve shown any cancellation penalties to the user "
                            "and they still want to proceed."
                        ),
                        "default": False,
                    },
                },
                "required": ["booking_id"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Requesting hotel cancellation…",
                "openai/toolInvocation/invoked": "Hotel cancellation response received.",
            },
        ),

        types.Tool(
            name="extend_hotel_stay_tool",
            title="Extend a hotel stay",
            description=(
                "Extend an existing hotel stay by providing a new check-out date. "
                "Handles any repricing/availability with Duffel."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "booking_id": {
                        "type": "string",
                        "description": "Existing hotel booking ID.",
                    },
                    "new_check_out_date": {
                        "type": "string",
                        "description": "New check-out date (YYYY-MM-DD).",
                    },
                    "proceed_despite_warnings": {
                        "type": "boolean",
                        "description": (
                            "Set true only after you’ve shown any extra charges to the user "
                            "and they confirm they want to extend."
                        ),
                        "default": False,
                    },
                },
                "required": ["booking_id", "new_check_out_date"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Requesting hotel stay extension…",
                "openai/toolInvocation/invoked": "Hotel stay extension response received.",
            },
        ),

        
        types.Tool(
            name="update_hotel_booking_tool",
            title="Update hotel booking contact details / requests",
            description=(
                "Update certain fields on an existing hotel booking (email, phone number, "
                "special requests)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "booking_id": {
                        "type": "string",
                        "description": "Hotel booking ID to update.",
                    },
                    "email": {
                        "type": "string",
                        "description": "Updated contact email for the booking.",
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "Updated contact phone number for the booking.",
                    },
                    "stay_special_requests": {
                        "type": "string",
                        "description": "Special requests to pass through to the hotel.",
                    },
                },
                "required": ["booking_id"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Updating hotel booking…",
                "openai/toolInvocation/invoked": "Hotel booking updated.",
            },
        ),

        # --- Nice-to-have / utilities ---
        types.Tool(
            name="fetch_accommodation_reviews_tool",
            title="Fetch accommodation reviews",
            description="Fetch reviews for a specific accommodation (hotel) via Duffel.",
            inputSchema={
                "type": "object",
                "properties": {
                    "accommodation_id": {
                        "type": "string",
                        "description": "Duffel accommodation ID to fetch reviews for.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of reviews to return.",
                        "default": 10,
                    },
                },
                "required": ["accommodation_id"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Fetching accommodation reviews…",
                "openai/toolInvocation/invoked": "Accommodation reviews returned.",
            },
        ),

        types.Tool(
            name="list_loyalty_programmes_tool",
            title="List hotel & travel loyalty programmes",
            description="List supported loyalty programmes (e.g. hotel chains, generic programmes).",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Listing loyalty programmes…",
                "openai/toolInvocation/invoked": "Loyalty programmes listed.",
            },
        ),        types.Tool(
            name="select_hotel_room_rate",
            title="User selected a hotel room / rate",
            description=(
                "Record which specific room / rate the user selected in the RoomCard widget. "
                "After this tool is called, the assistant should:\n"
                "1) Confirm the room selection in natural language.\n"
                "2) Ask the user for guest details (given_name, family_name), email, phone number, "
                "and any special stay requests.\n"
                "3) Use those details to call `start_hotel_checkout` for payment."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "rate_id": {
                        "type": "string",
                        "description": "Duffel rate ID (rat_...) or equivalent for the selected room."
                    },
                    "hotel_id": {"type": "string"},
                    "hotel_name": {"type": "string"},
                    "hotel_location": {"type": "string"},
                    "room_name": {"type": "string"},
                    "search_result_id": {
                        "type": "string",
                        "description": "Duffel search_result_id (srr_...) that this room belongs to."
                    },
                    "price_label": {"type": "string"},
                    "price_amount": {"type": "number"},
                    "currency": {"type": "string"},
                    "bed": {"type": "string"},
                    "board": {"type": "string"},
                    "cancellation": {"type": "string"},
                    "quantity": {"type": "integer"},
                },
                "required": ["rate_id"],
                "additionalProperties": True,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
            },
        ),


        types.Tool(
            name="list_flight_loyalty_programmes_tool",
            title="List flight loyalty programmes",
            description="List supported flight frequent-flyer / airline loyalty programmes.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Listing flight loyalty programmes…",
                "openai/toolInvocation/invoked": "Flight loyalty programmes listed.",
            },
        ),

        types.Tool(
            name="validate_phone_number_tool",
            title="Validate and normalise a phone number",
            description=(
                "Validate and format a phone number using libphonenumber. "
                "Returns E.164 format and basic validation info."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "Raw phone number as provided by the user.",
                    },
                    "country": {
                        "type": "string",
                        "description": "User’s country (e.g. AU, US) to help parsing.",
                    },
                },
                "required": ["phone_number"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Validating phone number…",
                "openai/toolInvocation/invoked": "Phone number validation returned.",
            },
        ),

        types.Tool(
            name="remember_tool",
            title="Store conversational memory",
            description="Persist a short piece of memory about the user or their preferences.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_content": {
                        "type": "string",
                        "description": "What to remember (free-form text).",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional context for where/why this memory was stored.",
                    },
                },
                "required": ["memory_content"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Storing memory…",
                "openai/toolInvocation/invoked": "Memory stored.",
            },
        ),

        types.Tool(
            name="recall_tool",
            title="Recall conversational memory",
            description="Search for previously stored memories that match a query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for the memory store.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Maximum number of memories to return.",
                        "default": 3,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Recalling memory…",
                "openai/toolInvocation/invoked": "Memory recall completed.",
            },
        ),

        types.Tool(
            name="get_checkout_status",
            title="Get checkout / booking status",
            description=(
                "Check the status of a Stripe-hosted checkout created by start_hotel_checkout "
                "or start_flight_checkout using its ctx_id. "
                "Returns whether it is pending, paid, or unknown plus any booking payload."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ctx_id": {
                        "type": "string",
                        "description": "Context ID returned by start_hotel_checkout/start_flight_checkout or embedded in the checkout URL.",
                    },
                },
                "required": ["ctx_id"],
                "additionalProperties": False,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
                "openai/toolInvocation/invoking": "Checking checkout status…",
                "openai/toolInvocation/invoked": "Checkout status returned.",
            },
        ),

        types.Tool(
            name="select_flight_offer",
            title="User selected a flight offer",
            description=(
               "Record which flight offer the user picked.\\n\\n"
                "AFTER THIS TOOL, collect info in this order:\\n"
                "1. Passenger details: given_name, family_name, date of birth (YYYY-MM-DD)\\n"
                "2. Contact: email and phone number\\n"
                "3. Ask: 'Would you like to select a specific seat, or proceed without seat selection?'\\n"
                "4. If they want seats: call get_seat_maps_tool, show options, let them pick\\n"
                "5. Then call start_flight_checkout with all collected info"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "offer_id": {"type": "string"},
                    "airline": {"type": "string"},
                    "route": {"type": "string"},
                    "date": {"type": "string"},
                    "departure_time": {"type": "string"},
                    "arrival_time": {"type": "string"},
                    "price": {"type": "string"},
                },
                "required": ["offer_id"],
                "additionalProperties": True,
            },
            _meta={
                "openai/resultCanProduceWidget": False,
                "openai/widgetAccessible": True,
            },
        ),
    ]

# ---------- list resources / templates ----------
@mcp._mcp_server.list_resources()
async def _list_resources() -> List[types.Resource]:
    return [types.Resource(
        name=w.title, title=w.title, uri=w.template_uri,
        description=f"{w.title} UI template", mimeType=MIME_TYPE, _meta=_tool_meta(w)
    ) for w in WIDGETS.values()]

@mcp._mcp_server.list_resource_templates()
async def _list_resource_templates() -> List[types.ResourceTemplate]:
    return [types.ResourceTemplate(
        name=w.title, title=w.title, uriTemplate=w.template_uri,
        description=f"{w.title} UI template", mimeType=MIME_TYPE, _meta=_tool_meta(w)
    ) for w in WIDGETS.values()]

async def _handle_read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
    raw = str(req.params.uri)
    base = raw.split("?", 1)[0].split("#", 1)[0]
    w = URI_TO_WIDGET.get(base)
    if not w:
        return types.ServerResult(types.ReadResourceResult(contents=[], _meta={"error": "Unknown resource"}))
    return types.ServerResult(types.ReadResourceResult(contents=[
        types.TextResourceContents(uri=raw, mimeType=MIME_TYPE, text=w.html, _meta=_tool_meta(w))
    ]))


from decimal import Decimal
from uuid import uuid4

async def _create_checkout_session_from_ctx(ctx: dict) -> stripe.checkout.Session:
    """
    Uses the saved ctx (rate_id, email, etc.) to:
      1) Create a Duffel quote (locks amount/currency)
      2) Create a Stripe Checkout Session for that quote
      3) Return the Session (we redirect the user to session.url)
    """
    rate_id = (ctx.get("rate_id") or "").strip()
    email   = (ctx.get("email")   or "").strip()

    if not rate_id:
        raise ValueError("Missing rate_id")
    if not EMAIL_RE.match(email):
        raise ValueError("Invalid email")

    # 1) Create Duffel quote
    quote = await create_quote(rate_id)  # returns {"data":{"id","total_amount","total_currency",...}}
    if "error" in quote:
        raise RuntimeError(f"Quote creation failed: {quote.get('error')}")
    qdata = quote.get("data") or {}
    quote_id = qdata.get("id")
    total_amount = qdata.get("total_amount")
    currency = (qdata.get("total_currency") or "").upper()
    if not (quote_id and total_amount and currency):
        raise RuntimeError("Duffel quote missing id/amount/currency")
    if currency not in CURRENCY_WHITELIST:
        raise ValueError(f"Unsupported currency: {currency}")

    # 2) Convert to minor units
    cents = int(Decimal(total_amount) * (Decimal("1") if currency in ZERO_DECIMAL else Decimal("100")))

    # 3) Build Stripe Checkout Session
    meta = {
        "quote_id": quote_id,
        "rate_id": rate_id,
        "ctx_id": ctx.get("ctx_id",""),
        "email": email,
        "search_result_id": ctx.get("search_result_id",""),
        "hotel_name": ctx.get("hotel_name",""),
        "room_name": ctx.get("room_name",""),
    }
    idem = f"checkout|{quote_id}|{email}"

    session = stripe.checkout.Session.create(
        mode="payment",
        customer_email=email,
        line_items=[{
            "price_data": {
                "currency": currency,
                "unit_amount": cents,
                "product_data": {
                    "name": "Hotel booking",
                    "description": ctx.get("desc") or f"Hotel rate: {rate_id}",
                },
            },
            "quantity": 1,
        }],
        success_url=SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=CANCEL_URL,
        metadata=meta,
        idempotency_key=idem,
    )
    return session

# ---------- call tool { logics behide the tool call }----------
async def _call_tool_request(req: types.CallToolRequest) -> types.ServerResult:
    try:
        auth = None  # ✅ ADD THIS LINE
        http_req = _http_request.get()
        
        authorization_header = None
        if http_req:
            authorization_header = http_req.headers.get("Authorization")
            if authorization_header:
                log.info(f"🔑 Found Authorization header (length: {len(authorization_header)})")
        
        
    
        meta = getattr(req.params, "_meta", {}) or {}
        
        # Try multiple locations for auth token
        if hasattr(req, "headers"):
            authorization_header = req.headers.get("Authorization")
        if not authorization_header:
            authorization_header = meta.get("authorization") or meta.get("Authorization")
        
        # Authenticate if OAuth is available
        if OAUTH_AVAILABLE and oauth_provider:
            auth = await authenticate_mcp_request(
                authorization_header=authorization_header,
                meta=meta,
            )
        
        # Define protected tools and their required scopes
        protected_tools = {
            # "start_flight_checkout": [],  # ✅ Empty = just requires authentication
            #"start_hotel_checkout": [],
            #"complete_flight_payment": [],
            #"complete_hotel_payment": [],
        }
                
        # Get tool name first (we need it for the check)
        name = getattr(req.params, "name", "")
        args = getattr(req.params, "arguments", {}) or {}
                # ============================================================================
        # USER INFO LOGGING FOR TOOL CALLS
        # ============================================================================
        log.info("=" * 80)
        log.info(f"📞 TOOL CALL: {name}")
        log.info("=" * 80)

        # ✅ ADD THIS DEBUG LOGGING:
        log.info(f"🔍 DEBUG - oauth_provider value: {oauth_provider}")
        log.info(f"🔍 DEBUG - OAUTH_AVAILABLE value: {OAUTH_AVAILABLE}")
        log.info(f"🔍 DEBUG - Tool '{name}' in protected_tools: {name in protected_tools}")
        log.info(f"🔍 DEBUG - Auth object: {auth}")
        
        if auth and auth.authenticated and auth.user:
            log.info("👤 USER INFORMATION:")
            log.info(f"   📧 Email: {auth.user.email}")
            log.info(f"   🆔 User ID: {auth.user.user_id}")
            # ✅ FIXED: Construct full name from first_name and last_name
            full_name = f"{auth.user.first_name or ''} {auth.user.last_name or ''}".strip()
            if not full_name:
                full_name = auth.user.user_id  # Fallback to user_id
            log.info(f"   👨‍💼 Name: {full_name}")
            log.info(f"   🔑 Scopes: {', '.join(auth.scopes) if auth.scopes else 'None'}")
            log.info(f"   ✅ Authentication: Verified")
        else:

            log.info("👤 USER INFORMATION:")
            log.info("   ❌ Authentication: None (anonymous request)")
            log.info("   ⚠️  Protected tools will require sign-in")
        
        log.info("")
        log.info("🔧 TOOL DETAILS:")
        log.info(f"   Tool Name: {name}")
        log.info(f"   Is Protected: {'Yes' if name in protected_tools else 'No'}")
        if name in protected_tools:
            log.info(f"   Required Scopes: {', '.join(protected_tools[name])}")
        
        log.info("")
        log.info("📋 ARGUMENTS:")
        # Sanitize sensitive data in logs
        safe_args = {**args}
        for sensitive_key in ['payment_intent_id', 'session_id', 'phone_number', 'email']:
            if sensitive_key in safe_args:
                val = safe_args[sensitive_key]
                if isinstance(val, str) and len(val) > 8:
                    safe_args[sensitive_key] = f"{val[:4]}...{val[-4:]}"
        
        log.info(f"{json.dumps(safe_args, indent=3)}")
        log.info("=" * 80)
        log.info("")
        
        if name in protected_tools:
            # ✅ Check if OAuth is available AND enabled
            if not OAUTH_AVAILABLE or not oauth_provider:
                log.warning(f"⚠️ OAuth not available but {name} is protected!")
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text=f"🔐 Authentication required for {name.replace('_', ' ')}, but OAuth is not configured.",
                    )],
                    isError=True,
                ))
            

            # ✅ Check if user is authenticated
            if not auth or not auth.authenticated:
                log.info(f"🔒 Auth required for {name}, user not authenticated")
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text=f"🔐 Please sign in to use {name.replace('_', ' ')}.",
                    )],
                    isError=True,
                    _meta={
                        "mcp/www_authenticate": [
                            f'Bearer resource_metadata="{PUBLIC_BASE_URL}/.well-known/oauth-protected-resource", '
                            f'error="invalid_token", '
                            f'error_description="Sign in to continue with your booking"'
                        ],
                    },
                ))
            
            
            # Verify required scopes
            # ✅ Verify required scopes (only if any are required)
            required_scopes = protected_tools[name]
            if required_scopes:  # Only check if specific scopes are required
                log.info(f"🔍 Checking scopes for {name}: required={required_scopes}, user_has={auth.scopes}")
                for scope in required_scopes:
                    if not auth.has_scope(scope):
                        log.info(f"❌ Missing scope '{scope}' for {name}")
                        return types.ServerResult(types.CallToolResult(
                            content=[types.TextContent(
                                type="text",
                                text=f"Missing permission: {scope}",
                            )],
                            isError=True,
                            _meta={
                                "mcp/www_authenticate": [
                                    f'Bearer resource_metadata="{PUBLIC_BASE_URL}/.well-known/oauth-protected-resource", '
                                    f'error="insufficient_scope", '
                                    f'error_description="Additional permissions required", '
                                    f'scope="{" ".join(required_scopes)}"'
                                ],
                            },
                        ))
    
            # ✅ User is authenticated (and has required scopes if any)
            log.info(f"✅ User authenticated for {name}: {auth.user.email if auth.user else 'unknown'}")
        
        # Inject user context into args for tools to use
        if auth and auth.authenticated and auth.user:
            args["_user_id"] = auth.user.user_id
            args["_user_email"] = auth.user.email
        
        def _normalize_tool_result(raw: Any) -> tuple[str, Any]:
            if isinstance(raw, (dict, list)):
                return (json.dumps(raw, indent=2), raw)
            if isinstance(raw, str):
                try:
                    return (raw, json.loads(raw))
                except Exception:
                    return (raw, {"result": raw})
            return (str(raw), {"result": raw})

        # Flights UI
        if name == "search_flights_ui":
            global BLOCK_NEXT_FLIGHT_SEARCH

            slices = args.get("slices") or []
            passengers = int(args.get("passengers", 1))
            cabin_class = args.get("cabin_class", "economy")
            max_results = int(args.get("max_results", 5))

            args_dict = {
                "slices": slices,
                "passengers": passengers,
                "cabin_class": cabin_class,
                "max_results": max_results,
            }

            # One-shot guard:
            # If the widget has just set the block flag (because the user clicked a flight),
            # DO NOT call LangGraph. Instead, return an *error* telling the model what to do.
         

            # Normal path: actually run the LangGraph flights search tool
            raw = await search_flights_tool.ainvoke(args_dict)
            log.info(raw)

            try:
                data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text=str(raw))],
                    isError=True,
                ))

            normalized = _normalize_any_to_flights(data)
            w = FLIGHT
            res = _embedded_widget_resource(w)
            meta = {
                "openai.com/widget": res.model_dump(mode="json"),
                "openai/outputTemplate": w.template_uri,
                "openai/toolInvocation/invoking": "Searching flights…",
                "openai/toolInvocation/invoked": "Flights ready.",
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            }
            return types.ServerResult(types.CallToolResult(
            content=[
                res,
                types.TextContent(
                    type="text",
                    text=(
                        f"Found {normalized['meta'].get('total', 0)} flights. "
                        "Present these options to the user and ask them to select which flight they want. "
                        "Do NOT ask for seat preference or passenger details yet - wait for their selection first."
                    )
                ),
            ],
            structuredContent=normalized,
            _meta=meta,
        ))

        # Hotels UI
        if name == "search_hotels_ui":
            global BLOCK_NEXT_HOTEL_SEARCH

            if not search_hotels_tool:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text="search_hotels_tool is not available on this server."
                    )],
                    isError=True,
                ))

            # Normalise args first (useful for logging even when blocked)
            args_dict = {
                "location":       args.get("location"),
                "check_in_date":  args.get("check_in_date"),
                "check_out_date": args.get("check_out_date"),
                "adults":         int(args.get("adults", 1)),
                "children":       int(args.get("children", 0)),
                "max_results":    int(args.get("max_results", 10)),
                "hotel_name":     args.get("hotel_name") or "",
            }

            # One-shot guard:
            # If the widget has just set the block flag (because the user clicked a hotel),
            # DO NOT call LangGraph. Instead, return an *error* telling the model what to do.
            if BLOCK_NEXT_HOTEL_SEARCH:
                BLOCK_NEXT_HOTEL_SEARCH = False  # consume the token immediately
                log.info(
                    "search_hotels_ui one-shot block triggered; args=%s",
                    args_dict,
                )
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text=(
                            "Hotel search was blocked because the user just selected a hotel "
                            "in the widget.\n\n"
                            "Do NOT call `search_hotels_ui` again for this selection.\n"
                            "Instead you must:\n"
                            "1) Call `select_hotel_result` with the selected hotel details, and\n"
                            "2) Call `fetch_hotel_rates_ui` with that `search_result_id` to show room options."
                        ),
                    )],
                    structuredContent={"skipped": True, "reason": "widget_selection"},
                    isError=True,   # 👈 this is important so the model stops repeating this call
                    _meta={
                        "openai/resultCanProduceWidget": False,
                        "openai/widgetAccessible": True,
                    },
                ))

            # Normal path: actually run the LangGraph hotel search tool
            raw = await search_hotels_tool.ainvoke(args_dict)

            try:
                data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                data = {"result": str(raw)}

            normalized = _normalize_any_to_hotels(data)
            w = HOTEL
            res = _embedded_widget_resource(w)
            meta = {
                "openai.com/widget": res.model_dump(mode="json"),
                "openai/outputTemplate": w.template_uri,
                "openai/toolInvocation/invoking": "Searching hotels…",
                "openai/toolInvocation/invoked": "Hotels ready.",
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            }
            return types.ServerResult(types.CallToolResult(
                content=[
                    res,
                    types.TextContent(
                        type="text",
                        text=f"Found {normalized['meta'].get('count', 0)} hotels."
                    ),
                ],
                structuredContent=normalized,
                _meta=meta,
            ))
        


        if name == "select_hotel_room_rate":
            rate_id = (args.get("rate_id") or "").strip()
            if not rate_id:
                return error_result("rate_id is required")

            structured = {
                "rate_id": rate_id,
                "hotel_id": args.get("hotel_id"),
                "hotel_name": args.get("hotel_name"),
                "hotel_location": args.get("hotel_location"),
                "room_name": args.get("room_name"),
                "search_result_id": args.get("search_result_id"),
                "price_label": args.get("price_label"),
                "price_amount": args.get("price_amount"),
                "currency": args.get("currency"),
                "bed": args.get("bed"),
                "board": args.get("board"),
                "cancellation": args.get("cancellation"),
                "quantity": args.get("quantity"),
            }

            lines = [
                "User selected this hotel room / rate from the RoomCard widget:",
                f"- rate_id: {structured['rate_id']}",
            ]
            if structured["hotel_name"]:
                lines.append(f"- Hotel name: {structured['hotel_name']}")
            if structured["hotel_location"]:
                lines.append(f"- Location: {structured['hotel_location']}")
            if structured["room_name"]:
                lines.append(f"- Room name: {structured['room_name']}")
            if structured["search_result_id"]:
                lines.append(f"- search_result_id: {structured['search_result_id']}")
            if structured["price_label"]:
                lines.append(f"- Price label: {structured['price_label']}")
            if structured["currency"] and structured["price_amount"] is not None:
                lines.append(
                    f"- Price numeric: {structured['price_amount']} {structured['currency']}"
                )
            if structured["bed"]:
                lines.append(f"- Bed: {structured['bed']}")
            if structured["board"]:
                lines.append(f"- Board: {structured['board']}")
            if structured["cancellation"]:
                lines.append(f"- Cancellation: {structured['cancellation']}")
            if structured["quantity"] is not None:
                lines.append(f"- Quantity: {structured['quantity']}")

            text = "\n".join(lines)

            return types.ServerResult(
                types.CallToolResult(
                    content=[types.TextContent(type="text", text=text)],
                    structuredContent=structured,
                    _meta={
                        "openai/resultCanProduceWidget": False,
                        "openai/widgetAccessible": True,
                    },
                )
            )

        if name == "confirm_booking_from_ctx":
            global PENDING_FLIGHT_CHECKOUTS, PENDING_HOTEL_CHECKOUTS
            
            ctx_id = (args.get("ctx_id") or "").strip()
            if not ctx_id:
                return error_result("ctx_id is required")

            entry = CHECKOUT_STATUS.get(ctx_id)
            if not entry:
                return error_result(f"No checkout status found for ctx_id={ctx_id}")

            if entry.get("status") != "paid":
                return error_result(
                    f"Checkout for ctx_id={ctx_id} is not marked as paid yet "
                    f"(current status: {entry.get('status', 'unknown')})."
                )

            t = entry.get("type") or "hotel"
            is_flight = (t == "flight")

            amount = entry.get("amount")
            ccy = entry.get("currency")
            booking = entry.get("booking") or {}
            bdata = booking.get("data") or booking

            ref = (
                bdata.get("booking_reference")
                or bdata.get("reference")
                or bdata.get("id")
                or "confirmed_booking"
            )

            hotel_name = (
                entry.get("hotel_name")
                or bdata.get("hotel_name")
                or (bdata.get("accommodation") or {}).get("name")
                or None
            )
            room_name = (
                entry.get("room_name")
                or bdata.get("room_name")
                or bdata.get("room_type")
                or None
            )

            # ✅ NEW: Remove from pending checkouts when confirmed
            for key, cid in list(PENDING_FLIGHT_CHECKOUTS.items()):
                if cid == ctx_id:
                    PENDING_FLIGHT_CHECKOUTS.pop(key, None)
                    log.info(f"Removed {key} from PENDING_FLIGHT_CHECKOUTS")
                    break
            for key, cid in list(PENDING_HOTEL_CHECKOUTS.items()):
                if cid == ctx_id:
                    PENDING_HOTEL_CHECKOUTS.pop(key, None)
                    log.info(f"Removed {key} from PENDING_HOTEL_CHECKOUTS")
                    break

            if is_flight:
                title = "✈️ Your flight booking is confirmed."
            else:
                title = "🏨 Your hotel booking is confirmed."

            parts = [title]

            if hotel_name and not is_flight:
                parts.append(f"Hotel: {hotel_name}")
            if room_name and not is_flight:
                parts.append(f"Room: {room_name}")
            parts.append(f"Booking reference: {ref}")

            if amount is not None and ccy:
                try:
                    amt_f = float(amount)
                    parts.append(f"Paid: {ccy} {amt_f:.2f}")
                except Exception:
                    parts.append(f"Paid: {ccy} {amount}")

            msg = (
                "\n".join(parts)
                + "\n\n"
                + "Thank you for booking with BookedAI! "
                  "If you'd like, I can help you review the details or make changes."
            )

            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=msg)],
                structuredContent={
                    "ctx_id": ctx_id,
                    "status": "paid",
                    **entry,
                },
                _meta={
                    "openai/resultCanProduceWidget": False,
                    "openai/widgetAccessible": True,
                },
            ))

              
        # Room rates UI
        if name == "fetch_hotel_rates_ui":
            global BLOCK_NEXT_ROOM_RATES

            if not fetch_hotel_rates_tool:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text="fetch_hotel_rates_tool is not available on this server.",
                    )],
                    isError=True,
                ))

            srr = args.get("search_result_id") or args.get("srr")
            if not srr:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text="search_result_id (srr_...) is required",
                    )],
                    isError=True,
                ))
            if not str(srr).startswith("srr_"):
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text=f"Invalid search_result_id: {srr}",
                    )],
                    isError=True,
                ))

            # One-shot guard for RoomCard:
            # If the widget just set BLOCK_NEXT_ROOM_RATES (because the user clicked a room),
            # DO NOT call LangGraph again. Return an error that tells the model what to do instead.
            if BLOCK_NEXT_ROOM_RATES:
                BLOCK_NEXT_ROOM_RATES = False  # consume the token
                log.info(
                    "fetch_hotel_rates_ui one-shot block triggered; search_result_id=%s",
                    srr,
                )
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text=(
                            "Room rates fetch was blocked because the user just selected a room "
                            "in the RoomCard widget.\n\n"
                            "Do NOT call `fetch_hotel_rates_ui` again for this selection.\n"
                            "You should instead proceed towards booking by:\n"
                            "1) Using the room rate already selected (rate_id, hotel_name, room_name, etc.), and\n"
                            "2) Asking the user for guest names, email, phone number and special requests, then\n"
                            "3) Calling `start_hotel_checkout` with those details."
                        ),
                    )],
                    structuredContent={"skipped": True, "reason": "widget_room_selection"},
                    isError=True,  # forces the model to reconsider its plan
                    _meta={
                        "openai/resultCanProduceWidget": False,
                        "openai/widgetAccessible": True,
                    },
                ))

            hotel_ctx = {
                "search_result_id": srr,
                "hotel_name": args.get("hotel_name") or "",
                "location": args.get("location") or "",
                "message": args.get("message") or "",
            }

            raw = await fetch_hotel_rates_tool.ainvoke({"search_result_id": srr})

            if isinstance(raw, str):
                try:
                    data = json.loads(raw)
                except Exception:
                    return types.ServerResult(types.CallToolResult(
                        content=[types.TextContent(type="text", text=raw)],
                        isError=True,
                    ))
            else:
                data = raw or {}

            normalized = _normalize_any_to_room_rates(data, hotel_ctx)
            w = ROOM
            res = _embedded_widget_resource(w)
            meta = {
                "openai.com/widget": res.model_dump(mode="json"),
                "openai/outputTemplate": w.template_uri,
                "openai/toolInvocation/invoking": "Fetching room rates…",
                "openai/toolInvocation/invoked": "Room rates ready.",
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            }
            return types.ServerResult(types.CallToolResult(
                content=[
                    res,
                    types.TextContent(
                        type="text",
                        text=f"Found {normalized['meta']['count']} room options.",
                    ),
                ],
                structuredContent=normalized,
                _meta=meta,
            ))
        # --- Start hotel payment WITHOUT graph: just build Stripe Checkout and show link in chat ---
                # --- Start hotel payment WITHOUT graph: just build Stripe Checkout and show link in chat ---
        if name == "start_hotel_checkout":


            rate_id  = (args.get("rate_id") or "").strip()
            email    = (args.get("email") or "").strip()
            guests   = args.get("guests") or []
            srr      = (args.get("search_result_id") or args.get("srr") or "").strip()
            phone    = args.get("phone_number") or ""
            stay_req = args.get("stay_special_requests") or ""
            hotel    = (args.get("hotel_name") or "Hotel").strip()
            room     = (args.get("room_name") or "Room").strip()
            desc     = (args.get("desc") or f"{hotel} • {room}").strip()

            missing = []
            if not rate_id: missing.append("rate_id")
            if not email:   missing.append("email")
            if not isinstance(guests, list) or not guests: missing.append("guests")
            if not phone:   missing.append("phone_number")
            else:
                for i,g in enumerate(guests):
                    if not (isinstance(g,dict) and g.get("given_name") and g.get("family_name")):
                        missing.append(f"guests[{i}]")
            if missing:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text=f"Missing required fields: {', '.join(missing)}")],
                    isError=True,
                ))

            if not EMAIL_RE.match(email):
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text="Invalid email format")],
                    isError=True,
                ))

            if not _is_valid_phone(phone):
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text="Invalid phone number format")],
                    isError=True,
                ))

            # ✅ Check if a checkout is already pending for this rate+email (MULTI-USER SAFE)
            booking_key = f"hotel:{rate_id}:{email}"
            if booking_key in PENDING_HOTEL_CHECKOUTS:
                existing_ctx_id = PENDING_HOTEL_CHECKOUTS[booking_key]
                return types.ServerResult(types.CallToolResult(
                    content=[
                        types.TextContent(
                            type="text",
                            text=(
                                f"⚠️ A checkout is already in progress for this hotel booking.\n\n"
                                f"The user is completing payment in the widget.\n\n"
                                f"Please call `confirm_booking_from_ctx` with ctx_id: \"{existing_ctx_id}\" "
                                f"to get the booking confirmation details.\n\n"
                                f"Do NOT call start_hotel_checkout again."
                            ),
                        ),
                    ],
                    isError=True,
                ))

            # ✅ CREATE QUOTE FIRST to get amount/currency
            try:
                quote = await create_quote(rate_id)
                if "error" in quote:
                    return types.ServerResult(types.CallToolResult(
                        content=[types.TextContent(type="text", text=f"Quote creation failed: {quote.get('error')}")],
                        isError=True,
                    ))
                
                qdata = quote.get("data") or {}
                quote_id = qdata.get("id")
                total_amount = qdata.get("total_amount")
                currency = (qdata.get("total_currency") or "").upper()
                
                if not (quote_id and total_amount and currency):
                    return types.ServerResult(types.CallToolResult(
                        content=[types.TextContent(type="text", text="Duffel quote missing id/amount/currency")],
                        isError=True,
                    ))
                
                if currency not in CURRENCY_WHITELIST:
                    return types.ServerResult(types.CallToolResult(
                        content=[types.TextContent(type="text", text=f"Unsupported currency: {currency}")],
                        isError=True,
                    ))
            except Exception as e:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text=f"Failed to create quote: {e}")],
                    isError=True,
                ))

            # Save context with quote info
            ctx_id = uuid4().hex
            CHECKOUT_CTX[ctx_id] = {
                "ctx_id": ctx_id,
                "rate_id": rate_id,
                "quote_id": quote_id,
                "email": email,
                "guests": guests,
                "search_result_id": srr,
                "phone_number": phone,
                "stay_special_requests": stay_req,
                "hotel_name": hotel,
                "room_name": room,
                "desc": desc,
                "amount": str(total_amount),
                "currency": currency,
                "created_at": time(),
            }

            # ✅ Register this checkout as pending (MULTI-USER SAFE)
            PENDING_HOTEL_CHECKOUTS[booking_key] = ctx_id

            CHECKOUT_STATUS[ctx_id] = {
                "type": "hotel",
                "status": "pending",
                "created_at": time(),
                "email": email,
                "hotel_name": hotel,
                "room_name": room,
                "amount": float(total_amount),
                "currency": currency,
            }

            public_base = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
            checkout_url = f"{public_base}/checkout/link?ctx_id={ctx_id}"

            # ✅ Include amount/currency in payload
            payload = {
                "status": {
                    "type": "hotel",
                    "status": "pending",
                    "ctx_id": ctx_id,
                    "created_at": CHECKOUT_STATUS[ctx_id]["created_at"],
                    "email": email,
                    "hotel_name": hotel,
                    "room_name": room,
                    "amount": float(total_amount),
                    "currency": currency,
                },
                "payment": {
                    "mode": "stripe_checkout_only",
                    "stripe_checkout_url": checkout_url,
                    "ctx_id": ctx_id,
                    "amount": str(total_amount),
                    "currency": currency,
                },
                "metadata": {
                    "hotel_name": hotel,
                    "room_type": room,
                    "guests": guests,
                    "email": email,
                    "phone_number": phone,
                    "stay_special_requests": stay_req,
                }
            }

            w = PAYMENT
            res = _embedded_widget_resource(w)
            meta = {
                "openai.com/widget": res.model_dump(mode="json"),
                "openai/outputTemplate": w.template_uri,
                "openai/toolInvocation/invoking": "Preparing Stripe Checkout…",
                "openai/toolInvocation/invoked": "Stripe Checkout ready.",
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            }

            return types.ServerResult(types.CallToolResult(
                content=[
                    res,
                    types.TextContent(
                        type="text",
                        text=f"Pay {currency} {total_amount} via secure checkout:\n{checkout_url}"
                    ),
                    types.TextContent(
                        type="text",
                        text=f"[Open secure checkout]({checkout_url})"
                    ),
                ],
                structuredContent=payload,
                _meta=meta,
            ))

        # --- Finalize after Stripe success: verify + complete booking, return details (standalone) ---
        if name == "finalize_hotel_checkout":
            session_id = (args.get("session_id") or "").strip()
            if not session_id:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text="session_id is required")],
                    isError=True,
                ))

            # 1) Retrieve Checkout Session and expand details we need
            try:
                session = stripe.checkout.Session.retrieve(
                    session_id,
                    expand=["payment_intent", "payment_intent.latest_charge", "customer_details"]
                )
            except Exception as e:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text=f"Stripe session error: {e}")],
                    isError=True,
                ))

            # 2) Ensure payment completed
            if (session.get("payment_status") or "").lower() != "paid":
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text="Payment not completed yet.")],
                    isError=True,
                ))

            # 3) Gather booking inputs (prefer args; fallback to session metadata/customer email)
            payment_intent = session.get("payment_intent")
            pi_id = payment_intent.get("id") if isinstance(payment_intent, dict) else str(payment_intent)

            md = (session.get("metadata") or {})
            rate_id  = (args.get("rate_id") or md.get("rate_id") or "").strip()
            guests   = args.get("guests") or []
            email    = (args.get("email") or (session.get("customer_details") or {}).get("email") or "").strip()
            phone    = (args.get("phone_number") or "").strip()
            stay_reqs = (args.get("stay_special_requests") or "").strip()
            quote_id = args.get("quote_id")  # optional

            # 4) Validate required booking fields (standalone)
            missing = []
            if not rate_id: missing.append("rate_id")
            if not isinstance(guests, list) or not guests: missing.append("guests")
            if not email: missing.append("email")
            if missing:
                # Provide payment facts so the assistant can ask the user for what’s missing
                facts = {
                    "status": "paid",
                    "payment_intent_id": pi_id,
                    "amount": session.get("amount_total"),
                    "currency": (session.get("currency") or "").upper(),
                    "rate_id_hint": md.get("rate_id"),
                }
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(
                        type="text",
                        text=f"Payment verified, but missing fields to finalize booking: {', '.join(missing)}"
                    )],
                    structuredContent=facts,
                    isError=True,
                    _meta={"openai/widgetAccessible": False},
                ))

            # 5) Create booking using your OWN logic (no LangGraph)
            try:
                booking = {
                    "booking_reference": f"BK-{pi_id[-8:]}",
                    "id": f"bk_{pi_id[-10:]}",
                    "status": "confirmed",
                    "metadata": {
                        "hotel_name": args.get("hotel_name") or "Hotel",
                        "room_type":  args.get("room_name")  or "Room",
                        "check_in":   args.get("check_in")   or "",
                        "check_out":  args.get("check_out")  or "",
                    }
                }
            except Exception as e:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text=f"Booking creation failed: {e}")],
                    isError=True,
                ))

            # 6) Build payment summary for UI/debug
            latest_charge = (payment_intent or {}).get("latest_charge") if isinstance(payment_intent, dict) else None
            receipt_url = (latest_charge or {}).get("receipt_url") if isinstance(latest_charge, dict) else None

            payment_summary = {
                "payment_status": "paid",
                "payment_intent_id": pi_id,
                "currency": (session.get("currency") or "").upper(),
                "amount": (session.get("amount_total") or 0) / 100.0 if session.get("amount_total") else None,
                "rate_id": rate_id,
                "receipt_url": receipt_url,
                "customer_email": email,
                "customer_name": (session.get("customer_details") or {}).get("name"),
                "card_last4": ((latest_charge or {}).get("payment_method_details") or {}).get("card", {}).get("last4"),
                "brand": ((latest_charge or {}).get("payment_method_details") or {}).get("card", {}).get("brand"),
            }

            md2 = booking.get("metadata") or {}
            hotel_name = md2.get("hotel_name") or "Hotel"
            room_type  = md2.get("room_type")  or "Room"
            checkin    = md2.get("check_in") or ""
            checkout   = md2.get("check_out") or ""
            ref        = booking.get("booking_reference") or booking.get("id") or ""

            summary = f"✅ Booking confirmed: {hotel_name} • {room_type}"
            if checkin or checkout:
                summary += f" ({checkin} → {checkout})"
            if ref:
                summary += f" • Ref: {ref}"

            ccy = payment_summary["currency"]; amt = payment_summary["amount"]
            if ccy and amt is not None:
                summary += f"\nPaid {ccy} {amt:.2f} • PI: {pi_id}"

            booking_out = {**booking, "payment": payment_summary}

            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=summary)],
                structuredContent=booking_out,
                _meta={
                    "openai/resultCanProduceWidget": False,
                    "openai/toolInvocation/invoking": "Verifying Stripe payment…",
                    "openai/toolInvocation/invoked": "Booking confirmed.",
                },
            ))
        
        if name == "select_hotel_result":
            srr = (args.get("search_result_id") or args.get("srr") or "").strip()
            if not srr:
                return error_result("search_result_id is required")

            structured = {
                "search_result_id": srr,
                "hotel_id": args.get("hotel_id"),
                "hotel_name": args.get("hotel_name"),
                "location": args.get("location"),
                "price": args.get("price"),
                "rating": args.get("rating"),
                "amenities": args.get("amenities") or [],
            }

            lines = [
                "User selected this hotel from the UI:",
                f"- search_result_id: {structured['search_result_id']}",
            ]
            if structured["hotel_id"]:
                lines.append(f"- Hotel ID: {structured['hotel_id']}")
            if structured["hotel_name"]:
                lines.append(f"- Hotel name: {structured['hotel_name']}")
            if structured["location"]:
                lines.append(f"- Location: {structured['location']}")
            if structured["rating"] is not None:
                lines.append(f"- Rating: {structured['rating']}")
            if structured["price"]:
                lines.append(f"- Price label: {structured['price']}")
            if structured["amenities"]:
                lines.append(
                    "- Amenities: " + ", ".join(map(str, structured["amenities"]))
                )

            text = "\n".join(lines)

            return types.ServerResult(
                types.CallToolResult(
                    content=[types.TextContent(type="text", text=text)],
                    structuredContent=structured,
                    _meta={
                        "openai/resultCanProduceWidget": False,
                        "openai/widgetAccessible": True,
                    },
                )
            )
        
        if name == "start_flight_checkout":
        

            offer_id = (args.get("offer_id") or "").strip()
            passengers = args.get("passengers") or []
            email = (args.get("email") or "").strip()
            phone = (args.get("phone_number") or "").strip()
            selected_seats = args.get("selected_seats") or []

            # --- Validate basics ---
            missing = []
            if not offer_id:
                missing.append("offer_id")
            if not isinstance(passengers, list) or not passengers:
                missing.append("passengers")
            else:
                for i, p in enumerate(passengers):
                    if not (p.get("given_name") and p.get("family_name") and p.get("born_on")):
                        missing.append(f"passengers[{i}]")
            if not email or not EMAIL_RE.match(email):
                missing.append("email")
            if not phone:
                missing.append("phone_number")
            if missing:
                return error_result(f"Missing/invalid fields: {', '.join(missing)}")

            if not _is_valid_phone(phone):
                return error_result("Invalid phone number format")

            # ✅ Check if a checkout is already pending for this offer+email (MULTI-USER SAFE)
            booking_key = f"flight:{offer_id}:{email}"
            if booking_key in PENDING_FLIGHT_CHECKOUTS:
                existing_ctx_id = PENDING_FLIGHT_CHECKOUTS[booking_key]
                return types.ServerResult(types.CallToolResult(
                    content=[
                        types.TextContent(
                            type="text",
                            text=(
                                f"⚠️ A checkout is already in progress for this flight booking.\n\n"
                                f"The user is completing payment in the widget.\n\n"
                                f"Please call `confirm_booking_from_ctx` with ctx_id: \"{existing_ctx_id}\" "
                                f"to get the booking confirmation details.\n\n"
                                f"Do NOT call start_flight_checkout again."
                            ),
                        ),
                    ],
                    isError=True,
                ))

            # --- Get base price from Duffel offer ---
            try:
                offer = await fetch_flight_offer(offer_id)
                o = (offer or {}).get("data", {})
                base_amount = o.get("total_amount")
                currency = (o.get("total_currency") or "").upper()
                if not (base_amount and currency):
                    return error_result("Could not determine base price/currency from offer.")
            except Exception as e:
                return error_result(f"Failed to fetch offer: {e}")

            # --- Calculate seat costs ONLY if selected_seats provided ---
            seat_total = 0.0
            services = []
            if selected_seats:
                try:
                    sm_raw = await get_seat_maps(offer_id)
                    formatted = (
                        sm_raw.get("formatted_seats")
                        or sm_raw.get("available_seats")
                        or sm_raw.get("data")
                        or []
                    )
                    seat_total, _details = calculate_seat_costs(selected_seats, formatted)
                    services = [{"id": s["service_id"], "quantity": 1} for s in selected_seats]
                except Exception as e:
                    return error_result(f"Failed to calculate seat costs: {e}")

            # --- Final amount (ticket + seats if any) ---
            try:
                amount = round(float(base_amount) + float(seat_total), 2)
            except Exception:
                return error_result("Invalid base_amount/seat_total for total calculation.")

            # Inject contact into passengers for Duffel
            pax = []
            for p in passengers:
                p = dict(p)
                p.setdefault("email", email)
                p.setdefault("phone_number", phone)
                pax.append(p)

            ctx_id = uuid4().hex
            FLIGHT_CHECKOUT_CTX[ctx_id] = {
                "ctx_id": ctx_id,
                "offer_id": offer_id,
                "passengers": pax,
                "email": email,
                "phone_number": phone,
                "currency": currency,
                "base_amount": str(base_amount),
                "seat_total": str(seat_total),
                "amount": f"{amount:.2f}",
                "services": services,
                "created_at": time(),
            }

            # ✅ Register this checkout as pending (MULTI-USER SAFE)
            PENDING_FLIGHT_CHECKOUTS[booking_key] = ctx_id

            CHECKOUT_STATUS[ctx_id] = {
                "type": "flight",
                "status": "pending",
                "created_at": time(),
                "currency": currency,
                "amount": float(amount),
                "email": email,
            }

            public_base = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
            checkout_url = f"{public_base}/flight/checkout/link?ctx_id={ctx_id}"

            seat_text = ""
            if services:
                seat_text = f" (including seats: {currency} {seat_total:.2f})"

            # Build payload for widget
            payload = {
                "status": {
                    "type": "flight",
                    "status": "pending",
                    "ctx_id": ctx_id,
                    "created_at": CHECKOUT_STATUS[ctx_id]["created_at"],
                    "currency": currency,
                    "amount": float(amount),
                    "email": email,
                },
                "payment": {
                    "mode": "stripe_checkout_only",
                    "currency": currency,
                    "amount": f"{amount:.2f}",
                    "stripe_checkout_url": checkout_url,
                    "ctx_id": ctx_id,
                },
                "metadata": {
                    "offer_id": offer_id,
                    "email": email,
                    "phone_number": phone,
                    "passengers_count": len(pax),
                    "services_count": len(services),
                },
            }

            # Embed the PaymentCard widget
            w = PAYMENT
            res = _embedded_widget_resource(w)
            meta = {
                "openai.com/widget": res.model_dump(mode="json"),
                "openai/outputTemplate": w.template_uri,
                "openai/toolInvocation/invoking": "Preparing Stripe Checkout…",
                "openai/toolInvocation/invoked": "Stripe Checkout ready.",
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            }

            return types.ServerResult(types.CallToolResult(
                content=[
                    res,
                    types.TextContent(
                        type="text",
                        text=f"Pay {currency} {amount:.2f}{seat_text} via Stripe Checkout:\n{checkout_url}",
                    ),
                    types.TextContent(
                        type="text",
                        text=f"[Open secure checkout]({checkout_url})",
                    ),
                ],
                structuredContent=payload,
                _meta=meta,
            ))


        if name == "change_flight_booking_tool":
            order_id = (args.get("order_id") or "").strip()
            slices = args.get("slices") or []
            change_type = (args.get("type") or "update").strip() or "update"
            cabin_class = (args.get("cabin_class") or None)

            if not order_id:
                return error_result("order_id is required")
            if not isinstance(slices, list) or not slices:
                return error_result("slices must be a non-empty array")

            payload = {
                "order_id": order_id,
                "slices": slices,
                "type": change_type,
            }
            if cabin_class:
                payload["cabin_class"] = cabin_class

            raw = await change_flight_booking_tool.ainvoke(payload)
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
                _meta={
                    "openai/resultCanProduceWidget": False,
                    "openai/widgetAccessible": True,
                    "openai/toolInvocation/invoking": "Requesting flight change…",
                    "openai/toolInvocation/invoked": "Flight change quote received.",
                },
            ))

        if name == "list_airline_initiated_changes_tool":
            raw = await list_airline_initiated_changes_tool.ainvoke({})
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "accept_airline_initiated_change_tool":
            change_id = (args.get("change_id") or "").strip()
            if not change_id:
                return error_result("change_id is required")

            raw = await accept_airline_initiated_change_tool.ainvoke({"change_id": change_id})
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "update_airline_initiated_change_tool":
            change_id = (args.get("change_id") or "").strip()
            data = args.get("data") or {}
            if not change_id:
                return error_result("change_id is required")
            if not isinstance(data, dict):
                return error_result("data must be an object")

            raw = await update_airline_initiated_change_tool.ainvoke({
                "change_id": change_id,
                "data": data,
            })
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "fetch_extra_baggage_options_tool":
            offer_id = (args.get("offer_id") or "").strip()
            if not offer_id:
                return error_result("offer_id is required")

            raw = await fetch_extra_baggage_options_tool.ainvoke({"offer_id": offer_id})
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "get_available_services_tool":
            offer_id = (args.get("offer_id") or "").strip()
            if not offer_id:
                return error_result("offer_id is required")

            raw = await get_available_services_tool.ainvoke({"offer_id": offer_id})
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        # --- Post-booking hotels ---
        if name == "cancel_hotel_booking_tool":
            booking_id = (args.get("booking_id") or "").strip()
            proceed = bool(args.get("proceed_despite_warnings") or False)
            if not booking_id:
                return error_result("booking_id is required")

            raw = await cancel_hotel_booking_tool.ainvoke({
                "booking_id": booking_id,
                "proceed_despite_warnings": proceed,
            })
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "extend_hotel_stay_tool":
            booking_id = (args.get("booking_id") or "").strip()
            new_co = (args.get("new_check_out_date") or "").strip()
            proceed = bool(args.get("proceed_despite_warnings") or False)
            if not booking_id:
                return error_result("booking_id is required")
            if not new_co:
                return error_result("new_check_out_date is required")

            raw = await extend_hotel_stay_tool.ainvoke({
                "booking_id": booking_id,
                "new_check_out_date": new_co,
                "proceed_despite_warnings": proceed,
            })
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "update_hotel_booking_tool":
            booking_id = (args.get("booking_id") or "").strip()
            email = (args.get("email") or "").strip()
            phone_number = (args.get("phone_number") or "").strip()
            stay_special_requests = (args.get("stay_special_requests") or "").strip()

            if not booking_id:
                return error_result("booking_id is required")

            payload = {"booking_id": booking_id}
            if email:
                payload["email"] = email
            if phone_number:
                payload["phone_number"] = phone_number
            if stay_special_requests:
                payload["stay_special_requests"] = stay_special_requests

            raw = await update_hotel_booking_tool.ainvoke(payload)
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))
        # Helper to handel the tool call from the widgets
        if name == "select_flight_offer":
            offer_id = (args.get("offer_id") or "").strip()
            if not offer_id:
                return error_result("offer_id is required")

            structured = {
                "offer_id": offer_id,
                "airline": args.get("airline"),
                "route": args.get("route"),
                "date": args.get("date"),
                "departure_time": args.get("departure_time"),
                "arrival_time": args.get("arrival_time"),
                "price": args.get("price"),
            }

            text_lines = [
                "User selected this flight offer from the UI:",
                f"- Offer ID: {structured['offer_id']}",
            ]
            if structured["airline"]:
                text_lines.append(f"- Airline: {structured['airline']}")
            if structured["route"]:
                text_lines.append(f"- Route: {structured['route']}")
            if structured["date"]:
                text_lines.append(f"- Date: {structured['date']}")
            if structured["departure_time"]:
                text_lines.append(f"- Departure time: {structured['departure_time']}")
            if structured["arrival_time"]:
                text_lines.append(f"- Arrival time: {structured['arrival_time']}")
            if structured["price"]:
                text_lines.append(f"- Price: {structured['price']}")

            text = "\n".join(text_lines)

            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
                _meta={
                    "openai/resultCanProduceWidget": False,
                    "openai/widgetAccessible": True,
                },
            ))

        # --- Nice-to-have / utilities ---
        if name == "fetch_accommodation_reviews_tool":
            accommodation_id = (args.get("accommodation_id") or "").strip()
            limit = args.get("limit", 10)
            try:
                limit = int(limit)
            except Exception:
                limit = 10
            if not accommodation_id:
                return error_result("accommodation_id is required")

            raw = await fetch_accommodation_reviews_tool.ainvoke({
                "accommodation_id": accommodation_id,
                "limit": limit,
            })
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "list_loyalty_programmes_tool":
            raw = await list_loyalty_programmes_tool.ainvoke({})
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "list_flight_loyalty_programmes_tool":
            raw = await list_flight_loyalty_programmes_tool.ainvoke({})
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "validate_phone_number_tool":
            phone_number = (args.get("phone_number") or args.get("phone") or "").strip()
            country = (args.get("country") or args.get("client_country") or "").strip()
            if not phone_number:
                return error_result("phone_number is required")

            raw = await validate_phone_number_tool.ainvoke({
                "phone": phone_number,
                "client_country": country or None,
            })
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "remember_tool":
            memory_content = (args.get("memory_content") or "").strip()
            context = (args.get("context") or "").strip()
            if not memory_content:
                return error_result("memory_content is required")

            raw = await remember_tool.ainvoke({
                "memory_content": memory_content,
                "context": context,
            })
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "recall_tool":
            query = (args.get("query") or "").strip()
            top_k = args.get("top_k", 3)
            try:
                top_k = int(top_k)
            except Exception:
                top_k = 3
            if not query:
                return error_result("query is required")

            raw = await recall_tool.ainvoke({
                "query": query,
                "top_k": top_k,
            })
            text, structured = _normalize_tool_result(raw)
            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=structured,
            ))

        if name == "get_checkout_status":
            ctx_id = (args.get("ctx_id") or "").strip()
            if not ctx_id:
                return error_result("ctx_id is required")

            entry = CHECKOUT_STATUS.get(ctx_id)
            if not entry:
                status = {"status": "unknown", "ctx_id": ctx_id}
            else:
                status = entry

            return types.ServerResult(types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(status, indent=2))],
                structuredContent=status,
                _meta={
                    "openai/resultCanProduceWidget": False,
                    "openai/widgetAccessible": True,
                },
            ))
        
        # --- Get seat maps (no UI) ---
        if name == "get_seat_maps_tool":
            offer_id = args.get("offer_id")
            if not offer_id:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text="offer_id is required")],
                    isError=True,
                ))

            raw = await get_seat_maps_tool.ainvoke({"offer_id": str(offer_id)})

            structured = None
            is_error = False
            msg = "Seat maps response returned."

            if isinstance(raw, (dict, list)):
                structured = raw
            elif isinstance(raw, str):
                if raw.startswith("Seat map fetch error:") or raw.startswith("Error fetching seat maps:"):
                    is_error = True
                    msg = raw
                else:
                    try:
                        structured = json.loads(raw)
                    except Exception:
                        msg = raw

            if structured is not None and not is_error:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text=msg)],
                    structuredContent=structured,
                    _meta={
                        "openai/resultCanProduceWidget": False,
                        "openai/toolInvocation/invoking": "Fetching seat maps…",
                        "openai/toolInvocation/invoked": "Seat maps ready.",
                        "openai/widgetAccessible": False,
                    },
                ))
            else:
                return types.ServerResult(types.CallToolResult(
                    content=[types.TextContent(type="text", text=msg)],
                    isError=is_error,
                    _meta={
                        "openai/resultCanProduceWidget": False,
                        "openai/toolInvocation/invoking": "Fetching seat maps…",
                        "openai/toolInvocation/invoked": "Seat maps ready.",
                        "openai/widgetAccessible": False,
                    },
                ))

        return types.ServerResult(types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Unknown tool: {name}")],
            isError=True,
        ))
    
    

    except Exception as e:
        tb = traceback.format_exc()
        log.error("call_tool failed: %s\n%s", e, tb)
        return types.ServerResult(types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Internal error: {e}")],
            isError=True,
            _meta={"traceback": tb},
        ))

# register handlers
mcp._mcp_server.request_handlers[types.CallToolRequest] = _call_tool_request
mcp._mcp_server.request_handlers[types.ReadResourceRequest] = _handle_read_resource

# at top-level (module scope), define app once
app = mcp.streamable_http_app()

# ============================================================================
# OAUTH INITIALIZATION
# ============================================================================
oauth_provider = None

if OAUTH_AVAILABLE:
    clerk_config = get_clerk_config()
    if clerk_config.enabled:
        missing = clerk_config.validate()
        if missing:
            log.warning(f"OAuth disabled - missing config: {', '.join(missing)}")
        else:
            oauth_provider = ClerkOAuthProvider()
            log.info("✅ OAuth enabled with Clerk")
            
            # Register OAuth endpoints
            for route in get_oauth_routes():
                app.router.routes.append(route)
                log.info(f"  Registered OAuth route: {route.path}")
    else:
        log.info("OAuth disabled via CLERK_ENABLED=false")
else:
    log.info("OAuth module not installed - running without authentication")


app.add_middleware(CaptureRequestMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # or ["http://localhost:4444"] to be strict
    allow_credentials=True,
    allow_methods=["*"],          # includes OPTIONS, GET, POST, ...
    allow_headers=["*"],
)


from starlette.responses import RedirectResponse, PlainTextResponse

async def checkout_post_route(request: Request):
    """
    POST /checkout
    Body: { "ctx_id": "..." }
    Creates a Stripe Checkout session and 303-redirects to Stripe.
    """
    try:
        try:
            body = await request.json()
        except Exception:
            body = {}
        ctx_id = (body.get("ctx_id") or "").strip()
        if not ctx_id:
            return PlainTextResponse("Missing ctx_id", status_code=400)
        ctx = CHECKOUT_CTX.get(ctx_id)
        if not ctx:
            return PlainTextResponse("Unknown or expired ctx_id", status_code=404)
        session = await _create_checkout_session_from_ctx(ctx)
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        logging.exception("Checkout POST error")
        return PlainTextResponse(f"Checkout error: {e}", status_code=500)

async def checkout_link_route(request: Request):
    """
    GET /checkout/link?ctx_id=...
    Same as POST but via query param; handy for link-click from chat.
    """
    try:
        ctx_id = (request.query_params.get("ctx_id") or "").strip()
        if not ctx_id:
            return PlainTextResponse("Missing ctx_id", status_code=400)
        ctx = CHECKOUT_CTX.get(ctx_id)
        if not ctx:
            return PlainTextResponse("Unknown or expired ctx_id", status_code=404)

        # TTL check for hotel checkout links
        created_at = ctx.get("created_at") or 0
        if time() - created_at > CHECKOUT_TTL_SECONDS:
            CHECKOUT_CTX.pop(ctx_id, None)
            return PlainTextResponse("Checkout link expired.", status_code=410)

        session = await _create_checkout_session_from_ctx(ctx)
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        logging.exception("Checkout LINK error")
        return PlainTextResponse(f"Checkout error: {e}", status_code=500)
    
# --- Hosted Stripe Checkout endpoints (success/cancel + optional webhook) ---
async def success_route(request: Request):
    from decimal import Decimal
    session_id = (request.query_params.get("session_id") or "").strip()
    if not session_id:
        return PlainTextResponse("Missing session_id", status_code=400)
    try:
        session = stripe.checkout.Session.retrieve(
            session_id, expand=["payment_intent", "payment_intent.latest_charge", "customer_details"]
        )
        if (session.get("payment_status") or "").lower() != "paid":
            return PlainTextResponse("Payment not completed yet.", status_code=400)

        md = session.get("metadata") or {}
        quote_id = md.get("quote_id")
        ctx_id   = md.get("ctx_id","")
        if not quote_id:
            return PlainTextResponse("Missing quote_id in session metadata.", status_code=400)

        # Verify against quote
        quote = await fetch_quote_details(quote_id)
        q = quote.get("data", {})
        exp_ccy = (q.get("total_currency") or "").upper()
        exp_amt = q.get("total_amount") or "0"
        ses_ccy = (session.get("currency") or "").upper()
        ses_amt = session.get("amount_total") or 0
        exp_cents = int(Decimal(exp_amt) * (Decimal("1") if exp_ccy in ZERO_DECIMAL else Decimal("100")))
        if ses_ccy != exp_ccy or ses_amt != exp_cents:
            return PlainTextResponse("Amount/currency mismatch against quote.", status_code=400)

        # Pull booking inputs from ctx
        ctx = CHECKOUT_CTX.get(ctx_id, {})
        guests = ctx.get("guests") or []
        email  = (ctx.get("email") or (session.get("customer_details") or {}).get("email") or "").strip()
        phone  = ctx.get("phone_number") or ""
        stay   = ctx.get("stay_special_requests") or ""
        if not (guests and email):
            return PlainTextResponse("Missing guests/email context to finalize booking.", status_code=400)

        # Finalize booking with Duffel
        pi = session.get("payment_intent")
        payment_intent_id = pi.get("id") if isinstance(pi, dict) else str(pi)
        booking = await create_booking(
            quote_id=quote_id, guests=guests, email=email,
            stay_special_requests=stay, phone_number=phone,
            payment={"stripe_payment_intent_id": payment_intent_id},
        )

        # Clear short-lived context
        if ctx_id in CHECKOUT_CTX:
            CHECKOUT_CTX.pop(ctx_id, None)

        # Extract receipt URL (if available)
        payment_intent = session.get("payment_intent")
        latest_charge = (payment_intent or {}).get("latest_charge") if isinstance(payment_intent, dict) else None
        receipt_url = (latest_charge or {}).get("receipt_url") if isinstance(latest_charge, dict) else None

        ref = booking.get("data", {}).get("id") or "booking_confirmed"
        paid = Decimal(ses_amt) / (1 if ses_ccy in ZERO_DECIMAL else 100)

        # Record status for MCP polling / chat notification
        # Keep any pending metadata (hotel_name, room_name, etc.)
        prev = CHECKOUT_STATUS.get(ctx_id, {})

        CHECKOUT_STATUS[ctx_id] = {
            **prev,
            "type": "hotel",
            "status": "paid",
            "created_at": time(),
            "quote_id": quote_id,
            "booking": booking,
            "currency": ses_ccy,
            "amount": float(paid),
            "stripe_session_id": session_id,
            "receipt_url": receipt_url,
            "email": email,
        }


        html = f"""
        <!doctype html>
        <html>
          <head>
            <meta charset="utf-8">
            <title>Payment successful</title>
          </head>
          <body style="font-family: system-ui; padding: 24px; max-width: 640px; margin: 0 auto;">
            <h1>✅ Booking confirmed</h1>

            <section style="margin-top: 16px;">
              <p><strong>Reference:</strong> {ref}</p>
              <p><strong>Paid:</strong> {ses_ccy} {paid:.2f}</p>
            </section>

            <section style="margin-top: 16px;">
              {"<p><a href='" + receipt_url + "' target='_blank' rel='noopener noreferrer'>View Stripe receipt</a></p>" if receipt_url else "<p>Stripe receipt is not available for this payment.</p>"}
            </section>

            <hr style="margin: 24px 0;">

            <p>You can now return to ChatGPT to continue your booking flow.</p>
          </body>
        </html>
        """
        return HTMLResponse(html, status_code=200)

    except Exception as e:
        logging.exception("Finalize error")
        return PlainTextResponse(f"Finalize error: {e}", status_code=500)

async def cancel_route(request: Request):
    return PlainTextResponse("❌ Payment canceled.")

async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        return PlainTextResponse("Webhook not configured.", status_code=200)
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=signature, secret=STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        return PlainTextResponse(f"Webhook signature error: {e}", status_code=400)

    if event["type"] == "checkout.session.completed":
        sess = event["data"]["object"]
        # Optional: auto-finalize here using sess["metadata"]["quote_id"] and sess["payment_intent"]

    return PlainTextResponse("ok")

# Create Stripe Checkout for flights & redirect
async def flight_checkout_link_route(request: Request):
    try:
        ctx_id = (request.query_params.get("ctx_id") or "").strip()
        if not ctx_id:
            return PlainTextResponse("Missing ctx_id", status_code=400)
        ctx = FLIGHT_CHECKOUT_CTX.get(ctx_id)
        if not ctx:
            return PlainTextResponse("Unknown or expired ctx_id", status_code=404)

        # TTL check for flight checkout links
        created_at = ctx.get("created_at") or 0
        if time() - created_at > FLIGHT_CHECKOUT_TTL_SECONDS:
            FLIGHT_CHECKOUT_CTX.pop(ctx_id, None)
            return PlainTextResponse("Checkout link expired.", status_code=410)

        # Create Stripe Checkout Session
        cents = int(Decimal(ctx["amount"]) * (Decimal("1") if ctx["currency"] in ZERO_DECIMAL else Decimal("100")))
        session = stripe.checkout.Session.create(
            mode="payment",
            customer_email=ctx["email"],
            line_items=[{
                "price_data": {
                    "currency": ctx["currency"],
                    "unit_amount": cents,
                    "product_data": {
                        "name": "Flight booking",
                        "description": f'Offer {ctx["offer_id"]}',
                    },
                },
                "quantity": 1,
            }],
            success_url=SUCCESS_URL.replace("/success", "/flight/success") + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=CANCEL_URL,
            metadata={
                "ctx_id": ctx_id,
                "offer_id": ctx["offer_id"],
                "amount": ctx["amount"],
                "currency": ctx["currency"],
            },
        )
        return RedirectResponse(session.url, status_code=303)
    except Exception as e:
        logging.exception("Flight checkout LINK error")
        return PlainTextResponse(f"Checkout error: {e}", status_code=500)

# Success → verify payment → Duffel create_flight_booking
async def flight_success_route(request: Request):
    session_id = (request.query_params.get("session_id") or "").strip()
    if not session_id:
        return PlainTextResponse("Missing session_id", status_code=400)
    try:
        session = stripe.checkout.Session.retrieve(
            session_id, expand=["payment_intent", "payment_intent.latest_charge", "customer_details"]
        )
        if (session.get("payment_status") or "").lower() != "paid":
            return PlainTextResponse("Payment not completed yet.", status_code=400)

        md = session.get("metadata") or {}
        ctx_id = md.get("ctx_id", "")
        ctx = FLIGHT_CHECKOUT_CTX.get(ctx_id)
        if not ctx:
            return PlainTextResponse("Missing/expired context.", status_code=400)

        # Verify amount/currency
        ses_ccy = (session.get("currency") or "").upper()
        ses_amt = session.get("amount_total") or 0
        exp_ccy = ctx["currency"]
        exp_amt = ctx["amount"]
        exp_cents = int(Decimal(exp_amt) * (Decimal("1") if exp_ccy in ZERO_DECIMAL else Decimal("100")))
        if ses_ccy != exp_ccy or ses_amt != exp_cents:
            return PlainTextResponse("Amount/currency mismatch.", status_code=400)

        # Build Duffel payments + services
        pi = session.get("payment_intent")
        payment_intent_id = pi.get("id") if isinstance(pi, dict) else str(pi)

        payments = [{
            "type": "balance",
            "amount": ctx["amount"],
            "currency": ctx["currency"],
            "stripe_payment_intent_id": payment_intent_id,
        }]

        passengers = ctx["passengers"]  # already has email/phone injected
        services = ctx.get("services") or None

        booking = await create_flight_booking(
            offer_id=ctx["offer_id"],
            passengers=passengers,
            payments=payments,
            services=services
        )

        # Clear context
        FLIGHT_CHECKOUT_CTX.pop(ctx_id, None)

        # Extract receipt URL (if available)
        payment_intent = session.get("payment_intent")
        latest_charge = (payment_intent or {}).get("latest_charge") if isinstance(payment_intent, dict) else None
        receipt_url = (latest_charge or {}).get("receipt_url") if isinstance(latest_charge, dict) else None

        ref = (booking.get("data") or {}).get("id") or "flight_booking_confirmed"
        paid_display = Decimal(ses_amt) / (1 if ses_ccy in ZERO_DECIMAL else 100)

        # Record status for MCP polling / chat notification
        CHECKOUT_STATUS[ctx_id] = {
            "type": "flight",
            "status": "paid",
            "created_at": time(),
            "booking": booking,
            "currency": ses_ccy,
            "amount": float(paid_display),
            "stripe_session_id": session_id,
            "receipt_url": receipt_url,
        }

        # HTML success page with receipt link for flights
        html = f"""
        <!doctype html>
        <html>
          <head>
            <meta charset="utf-8">
            <title>Flight payment successful</title>
          </head>
          <body style="font-family: system-ui; padding: 24px; max-width: 640px; margin: 0 auto;">
            <h1> Flight booking confirmed</h1>

            <section style="margin-top: 16px;">
              <p><strong>Reference:</strong> {ref}</p>
              <p><strong>Paid:</strong> {ses_ccy} {paid_display:.2f}</p>
            </section>

            <section style="margin-top: 16px;">
              {"<p><a href='" + receipt_url + "' target='_blank' rel='noopener noreferrer'>View Stripe receipt</a></p>" if receipt_url else "<p>Stripe receipt is not available for this payment.</p>"}
            </section>

            <hr style="margin: 24px 0;">

            <p>You can now return to ChatGPT to continue your trip planning.</p>
          </body>
        </html>
        """
        return HTMLResponse(html, status_code=200)
    except Exception as e:
        logging.exception("Flight finalize error")
        return PlainTextResponse(f"Finalize error: {e}", status_code=500)
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse



# allow widget origin(s) to POST
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # or restrict to your widget origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def widget_block_next_hotel_search(request: Request):
    """
    POST /widget/hotel/block_next

    Called by the hotel widget AFTER a user clicks a hotel.
    It sets a one-shot flag so the *next* search_hotels_ui call is blocked.
    """
    global BLOCK_NEXT_HOTEL_SEARCH
    try:
        # just consume body; we don't care what it is
        await request.body()
    except Exception:
        pass

    BLOCK_NEXT_HOTEL_SEARCH = True
    log.info("BLOCK_NEXT_HOTEL_SEARCH set to True by widget")
    return PlainTextResponse("ok")

async def widget_block_next_flight_search(request: Request):
    """
    POST /widget/flight/block_next

    Called by the flight widget AFTER a user clicks a flight.
    It sets a one-shot flag so the *next* search_flights_ui call is blocked.
    """
    global BLOCK_NEXT_FLIGHT_SEARCH
    try:
        # just consume body; we don't care what it is
        await request.body()
    except Exception:
        pass

    # BLOCK_NEXT_FLIGHT_SEARCH = True
    log.info("BLOCK_NEXT_FLIGHT_SEARCH set to True by widget")
    return PlainTextResponse("ok")


async def widget_block_next_room_rates(request: Request):
    """
    POST /widget/room/block_next

    Called by the room widget AFTER a user clicks a room.
    It sets a one-shot flag so the *next* fetch_hotel_rates_ui call is blocked.
    """
    global BLOCK_NEXT_ROOM_RATES
    try:
        # just consume body; we don't care what it is
        await request.body()
    except Exception:
        pass

    BLOCK_NEXT_ROOM_RATES = True
    log.info("BLOCK_NEXT_ROOM_RATES set to True by widget")
    return PlainTextResponse("ok")


async def widget_checkout_status(request: Request):
    """
    GET /widget/checkout/status?ctx_id=...

    Used by the payment-card widget to poll the current payment/booking status.
    Reads CHECKOUT_STATUS[ctx_id] and returns it as JSON.
    """
    ctx_id = (request.query_params.get("ctx_id") or "").strip()
    if not ctx_id:
        return JSONResponse({"status": "error", "message": "Missing ctx_id"}, status_code=400)

    entry = CHECKOUT_STATUS.get(ctx_id)
    if not entry:
        status = {"status": "unknown", "ctx_id": ctx_id}
    else:
        status = dict(entry)
        status["ctx_id"] = ctx_id  # ensure ctx_id is always present

    return JSONResponse(status)

async def widget_block_next_hotel_checkout(request: Request):
    """
    POST /widget/hotel_checkout/block_next

    Called by the payment widget AFTER the user has completed payment
    and pressed the confirm/OK button in the dialog.

    It sets a one-shot flag so the *next* start_hotel_checkout call is blocked.
    """
    global BLOCK_NEXT_HOTEL_CHECKOUT
    try:
        await request.body()  # we ignore any body
    except Exception:
        pass

    BLOCK_NEXT_HOTEL_CHECKOUT = True
    log.info("BLOCK_NEXT_HOTEL_CHECKOUT set to True by widget")
    return PlainTextResponse("ok")

async def widget_block_next_flight_checkout(request: Request):
    """
    POST /widget/flight_checkout/block_next

    Called by the payment widget AFTER the user has completed payment
    and pressed the confirm/OK button in the dialog (for flight flows).

    It sets a one-shot flag so the *next* start_flight_checkout call is blocked.
    """
    global BLOCK_NEXT_FLIGHT_CHECKOUT
    try:
        await request.body()  # ignore body
    except Exception:
        pass

    BLOCK_NEXT_FLIGHT_CHECKOUT = True
    log.info("BLOCK_NEXT_FLIGHT_CHECKOUT set to True by widget")
    return PlainTextResponse("ok")



    
app.router.routes.append(Route("/checkout",      checkout_post_route, methods=["POST"]))
app.router.routes.append(Route("/checkout/link", checkout_link_route, methods=["GET"]))
app.router.routes.append(Route("/success",  success_route,  methods=["GET"]))
app.router.routes.append(Route("/cancel",   cancel_route,   methods=["GET"]))
app.router.routes.append(Route("/stripe/webhook", stripe_webhook, methods=["POST"]))
app.router.routes.append(Route("/flight/checkout/link", flight_checkout_link_route, methods=["GET"]))
app.router.routes.append(Route("/flight/success",       flight_success_route,       methods=["GET"]))

app.router.routes.append(
    Route("/widget/flight/block_next", widget_block_next_flight_search, methods=["POST"])
)
app.router.routes.append(
    Route("/widget/hotel/block_next", widget_block_next_hotel_search, methods=["POST"])

)
app.router.routes.append(
    Route("/widget/room/block_next", widget_block_next_room_rates, methods=["POST"])
)
app.router.routes.append(
    Route("/widget/hotel_checkout/block_next", widget_block_next_hotel_checkout, methods=["POST"])
)

app.router.routes.append(
    Route("/widget/flight_checkout/block_next", widget_block_next_flight_checkout, methods=["POST"])
)


# 🔹 ADD THIS:
app.router.routes.append(
    Route("/widget/checkout/status", widget_checkout_status, methods=["GET"])
)


async def create_hotel_payment_intent(request: Request):
    """
    POST /api/hotel/payment/create-intent
    Body: { "ctx_id": "..." }
    
    Creates a Stripe PaymentIntent and returns the client_secret
    for the embedded payment form.
    """
    try:
        body = await request.json()
        ctx_id = (body.get("ctx_id") or "").strip()
        
        if not ctx_id:
            return JSONResponse({"error": "Missing ctx_id"}, status_code=400)
        
        ctx = CHECKOUT_CTX.get(ctx_id)
        if not ctx:
            return JSONResponse({"error": "Unknown or expired ctx_id"}, status_code=404)
        
        # TTL check
        created_at = ctx.get("created_at") or 0
        if time() - created_at > CHECKOUT_TTL_SECONDS:
            CHECKOUT_CTX.pop(ctx_id, None)
            return JSONResponse({"error": "Checkout expired"}, status_code=410)
        
        # Create quote to get final amount
        rate_id = ctx.get("rate_id")
        if not rate_id:
            return JSONResponse({"error": "Missing rate_id in context"}, status_code=400)
        
        quote = await create_quote(rate_id)
        if "error" in quote:
            return JSONResponse({"error": f"Quote failed: {quote.get('error')}"}, status_code=400)
        
        qdata = quote.get("data") or {}
        quote_id = qdata.get("id")
        total_amount = qdata.get("total_amount")
        currency = (qdata.get("total_currency") or "").upper()
        
        if not (quote_id and total_amount and currency):
            return JSONResponse({"error": "Invalid quote response"}, status_code=400)
        
        if currency not in CURRENCY_WHITELIST:
            return JSONResponse({"error": f"Unsupported currency: {currency}"}, status_code=400)
        
        # Convert to cents
        cents = int(Decimal(total_amount) * (Decimal("1") if currency in ZERO_DECIMAL else Decimal("100")))
        
        # Store quote_id in context for later
        ctx["quote_id"] = quote_id
        ctx["amount"] = str(total_amount)
        ctx["currency"] = currency
        CHECKOUT_CTX[ctx_id] = ctx
        
        # Create PaymentIntent
        payment_intent = stripe.PaymentIntent.create(
            amount=cents,
            currency=currency.lower(),
            automatic_payment_methods={"enabled": True},
            metadata={
                "ctx_id": ctx_id,
                "quote_id": quote_id,
                "rate_id": rate_id,
                "type": "hotel",
                "email": ctx.get("email", ""),
                "hotel_name": ctx.get("hotel_name", ""),
                "room_name": ctx.get("room_name", ""),
            },
            receipt_email=ctx.get("email"),
        )
        
        logging.info(f"Created hotel PaymentIntent: {payment_intent.id} for ctx_id: {ctx_id}")
        
        return JSONResponse({
            "clientSecret": payment_intent.client_secret,
            "paymentIntentId": payment_intent.id,
            "amount": total_amount,
            "currency": currency,
            "quote_id": quote_id,
        })
        
    except Exception as e:
        logging.exception("Hotel PaymentIntent creation error")
        return JSONResponse({"error": str(e)}, status_code=500)


# =============================================================================
# NEW ENDPOINT: Confirm Hotel Booking after Payment
# =============================================================================
async def confirm_hotel_booking(request: Request):
    """
    POST /api/hotel/payment/confirm-booking
    Body: { "ctx_id": "...", "payment_intent_id": "..." }
    
    Verifies payment succeeded, creates booking via Duffel, returns booking details.
    """
    global PENDING_HOTEL_CHECKOUTS
    
    try:
        body = await request.json()
        ctx_id = (body.get("ctx_id") or "").strip()
        payment_intent_id = (body.get("payment_intent_id") or "").strip()
        
        if not ctx_id:
            return JSONResponse({"error": "Missing ctx_id"}, status_code=400)
        if not payment_intent_id:
            return JSONResponse({"error": "Missing payment_intent_id"}, status_code=400)
        
        # Verify payment intent
        try:
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        except Exception as e:
            return JSONResponse({"error": f"Invalid payment_intent_id: {e}"}, status_code=400)
        
        if payment_intent.status != "succeeded":
            return JSONResponse(
                {"error": f"Payment not completed. Status: {payment_intent.status}"},
                status_code=400
            )
        
        # Get context
        ctx = CHECKOUT_CTX.get(ctx_id)
        if not ctx:
            return JSONResponse({"error": "Unknown or expired ctx_id"}, status_code=404)
        
        quote_id = ctx.get("quote_id")
        guests = ctx.get("guests") or []
        email = ctx.get("email", "")
        phone = ctx.get("phone_number", "")
        stay_req = ctx.get("stay_special_requests", "")
        rate_id = ctx.get("rate_id", "")
        
        if not quote_id:
            return JSONResponse({"error": "Missing quote_id in context"}, status_code=400)
        if not guests:
            return JSONResponse({"error": "Missing guests in context"}, status_code=400)
        
        # Create booking via Duffel
        booking = await create_booking(
            quote_id=quote_id,
            guests=guests,
            email=email,
            stay_special_requests=stay_req,
            phone_number=phone,
            payment={"stripe_payment_intent_id": payment_intent_id},
        )
        
        
        # Clear context
        CHECKOUT_CTX.pop(ctx_id, None)
        
        # Get receipt URL
        receipt_url = None
        try:
            charges = stripe.Charge.list(payment_intent=payment_intent_id, limit=1)
            if charges.data:
                receipt_url = charges.data[0].receipt_url
        except Exception as e:
            logging.warning(f"Could not get receipt URL: {e}")
        
        # Update status
        amount = ctx.get("amount")
        currency = ctx.get("currency")
        
        CHECKOUT_STATUS[ctx_id] = {
            "type": "hotel",
            "status": "paid",
            "created_at": time(),
            "quote_id": quote_id,
            "booking": booking,
            "currency": currency,
            "amount": float(amount) if amount else None,
            "payment_intent_id": payment_intent_id,
            "receipt_url": receipt_url,
            "email": email,
            "hotel_name": ctx.get("hotel_name", ""),
            "room_name": ctx.get("room_name", ""),
        }
        
        booking_ref = (booking.get("data") or {}).get("id") or "confirmed"
        
        logging.info(f"Hotel booking confirmed: {booking_ref} for ctx_id: {ctx_id}")
        
        return JSONResponse({
            "success": True,
            "booking_reference": booking_ref,
            "booking": booking,
            "receipt_url": receipt_url,
            "amount": amount,
            "currency": currency,
        })
        
    except Exception as e:
        logging.exception("Hotel booking confirmation error")
        return JSONResponse({"error": str(e)}, status_code=500)


# =============================================================================
# NEW ENDPOINT: Create PaymentIntent for Flight
# =============================================================================
async def create_flight_payment_intent(request: Request):
    """
    POST /api/flight/payment/create-intent
    Body: { "ctx_id": "..." }
    
    Creates a Stripe PaymentIntent for flight checkout.
    """
    try:
        body = await request.json()
        ctx_id = (body.get("ctx_id") or "").strip()
        
        if not ctx_id:
            return JSONResponse({"error": "Missing ctx_id"}, status_code=400)
        
        ctx = FLIGHT_CHECKOUT_CTX.get(ctx_id)
        if not ctx:
            return JSONResponse({"error": "Unknown or expired ctx_id"}, status_code=404)
        
        # TTL check
        created_at = ctx.get("created_at") or 0
        if time() - created_at > FLIGHT_CHECKOUT_TTL_SECONDS:
            FLIGHT_CHECKOUT_CTX.pop(ctx_id, None)
            return JSONResponse({"error": "Checkout expired"}, status_code=410)
        
        # Get amount from context (already calculated in start_flight_checkout)
        amount = ctx.get("amount")
        currency = ctx.get("currency", "").upper()
        
        if not amount or not currency:
            return JSONResponse({"error": "Missing amount/currency in context"}, status_code=400)
        
        if currency not in CURRENCY_WHITELIST:
            return JSONResponse({"error": f"Unsupported currency: {currency}"}, status_code=400)
        
        # Convert to cents
        cents = int(Decimal(amount) * (Decimal("1") if currency in ZERO_DECIMAL else Decimal("100")))
        
        # Create PaymentIntent
        payment_intent = stripe.PaymentIntent.create(
            amount=cents,
            currency=currency.lower(),
            automatic_payment_methods={"enabled": True},
            metadata={
                "ctx_id": ctx_id,
                "offer_id": ctx.get("offer_id", ""),
                "type": "flight",
                "email": ctx.get("email", ""),
            },
            receipt_email=ctx.get("email"),
        )
        
        logging.info(f"Created flight PaymentIntent: {payment_intent.id} for ctx_id: {ctx_id}")
        
        return JSONResponse({
            "clientSecret": payment_intent.client_secret,
            "paymentIntentId": payment_intent.id,
            "amount": amount,
            "currency": currency,
        })
        
    except Exception as e:
        logging.exception("Flight PaymentIntent creation error")
        return JSONResponse({"error": str(e)}, status_code=500)


# =============================================================================
# NEW ENDPOINT: Confirm Flight Booking after Payment
# =============================================================================
async def confirm_flight_booking_endpoint(request: Request):
    """
    POST /api/flight/payment/confirm-booking
    Body: { "ctx_id": "...", "payment_intent_id": "..." }
    
    Verifies payment succeeded, creates Duffel flight booking.
    """
    global PENDING_FLIGHT_CHECKOUTS
    
    try:
        body = await request.json()
        ctx_id = (body.get("ctx_id") or "").strip()
        payment_intent_id = (body.get("payment_intent_id") or "").strip()
        
        if not ctx_id:
            return JSONResponse({"error": "Missing ctx_id"}, status_code=400)
        if not payment_intent_id:
            return JSONResponse({"error": "Missing payment_intent_id"}, status_code=400)
        
        # Verify payment intent
        try:
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        except Exception as e:
            return JSONResponse({"error": f"Invalid payment_intent_id: {e}"}, status_code=400)
        
        if payment_intent.status != "succeeded":
            return JSONResponse(
                {"error": f"Payment not completed. Status: {payment_intent.status}"},
                status_code=400
            )
        
        # Get context
        ctx = FLIGHT_CHECKOUT_CTX.get(ctx_id)
        if not ctx:
            return JSONResponse({"error": "Unknown or expired ctx_id"}, status_code=404)
        
        offer_id = ctx.get("offer_id")
        passengers = ctx.get("passengers") or []
        amount = ctx.get("amount")
        currency = ctx.get("currency")
        services = ctx.get("services") or []
        email = ctx.get("email", "")
        
        if not offer_id:
            return JSONResponse({"error": "Missing offer_id in context"}, status_code=400)
        if not passengers:
            return JSONResponse({"error": "Missing passengers in context"}, status_code=400)
        
        # Build Duffel payments
        payments = [{
            "type": "balance",
            "amount": amount,
            "currency": currency,
            "stripe_payment_intent_id": payment_intent_id,
        }]
        
        # Create booking via Duffel
        booking = await create_flight_booking(
            offer_id=offer_id,
            passengers=passengers,
            payments=payments,
            services=services if services else None,
        )
        
        
        # Clear context
        FLIGHT_CHECKOUT_CTX.pop(ctx_id, None)
        
        # Get receipt URL
        receipt_url = None
        try:
            charges = stripe.Charge.list(payment_intent=payment_intent_id, limit=1)
            if charges.data:
                receipt_url = charges.data[0].receipt_url
        except Exception as e:
            logging.warning(f"Could not get receipt URL: {e}")
        
        # Update status
        CHECKOUT_STATUS[ctx_id] = {
            "type": "flight",
            "status": "paid",
            "created_at": time(),
            "booking": booking,
            "currency": currency,
            "amount": float(amount) if amount else None,
            "payment_intent_id": payment_intent_id,
            "receipt_url": receipt_url,
            "email": email,
        }
        
        booking_ref = (booking.get("data") or {}).get("id") or "confirmed"
        
        logging.info(f"Flight booking confirmed: {booking_ref} for ctx_id: {ctx_id}")
        
        return JSONResponse({
            "success": True,
            "booking_reference": booking_ref,
            "booking": booking,
            "receipt_url": receipt_url,
            "amount": amount,
            "currency": currency,
        })
        
    except Exception as e:
        logging.exception("Flight booking confirmation error")
        return JSONResponse({"error": str(e)}, status_code=500)


app.router.routes.append(
    Route("/api/hotel/payment/create-intent", create_hotel_payment_intent, methods=["POST"]))
app.router.routes.append(
     Route("/api/hotel/payment/confirm-booking", confirm_hotel_booking, methods=["POST"]))
app.router.routes.append(
    Route("/api/flight/payment/create-intent", create_flight_payment_intent, methods=["POST"])
)
app.router.routes.append(
    Route("/api/flight/payment/confirm-booking", confirm_flight_booking_endpoint, methods=["POST"]))

if __name__ == "__main__":
    import uvicorn
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host=HOST, port=PORT, log_level="info", reload=False)

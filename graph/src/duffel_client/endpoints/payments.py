import httpx
import logging
from typing import Optional, Dict, Any
import os
import aiohttp

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

async def create_card(card_details: dict, duffel_token: str, multi_use: bool = False) -> dict:
    """
    Create a Duffel card record (single-use or multi-use)
    
    Args:
        card_details: Card information (number, name, expiry, cvc, address, etc.)
        duffel_token: Duffel API token
        multi_use: Whether to create a multi-use card (default: False)
    
    Returns:
        Card response with card_id
    """
    url = "https://api.duffel.cards/payments/cards"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Duffel-Version": "v2",
        "Authorization": f"Bearer {duffel_token}"
    }
    
    # For multi-use cards, remove CVC as it's not stored
    if multi_use and "cvc" in card_details:
        card_details = card_details.copy()
        del card_details["cvc"]
    
    data = {"data": {**card_details, "multi_use": multi_use}}
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=data)
        resp.raise_for_status()
        return resp.json()

async def create_single_use_from_multi_use(
    parent_card_id: str, 
    cvc: str, 
    expiry_month: str, 
    expiry_year: str, 
    duffel_token: str
) -> dict:
    """
    Create a single-use card derived from a multi-use card
    
    Args:
        parent_card_id: The multi-use card ID
        cvc: Card verification code
        expiry_month: Expiry month (MM)
        expiry_year: Expiry year (YY)
        duffel_token: Duffel API token
    
    Returns:
        Single-use card response with new card_id
    """
    url = "https://api.duffel.cards/payments/cards"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Duffel-Version": "v2",
        "Authorization": f"Bearer {duffel_token}"
    }
    
    data = {
        "data": {
            "card_id": parent_card_id,
            "cvc": cvc,
            "multi_use": False,
            "expiry_month": expiry_month,
            "expiry_year": expiry_year
        }
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=data)
        resp.raise_for_status()
        return resp.json()

async def create_3ds_session(
    card_id: str, 
    resource_id: str, 
    duffel_token: str, 
    services: list = None,
    exception: str = None
) -> dict:
    """
    Create a 3-D Secure session for a card and resource
    
    Args:
        card_id: The card ID from create_card
        resource_id: offer_id, quote_id, or order_id depending on context
        duffel_token: Duffel API token
        services: Optional services list for bags/seats
        exception: Optional exception for corporate payments
    
    Returns:
        3DS session response with session_id
    """
    url = "https://api.duffel.com/payments/three_d_secure_sessions"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Duffel-Version": "v2",
        "Authorization": f"Bearer {duffel_token}"
    }
    
    data = {
        "data": {
            "card_id": card_id,
            "resource_id": resource_id
        }
    }
    
    if services:
        data["data"]["services"] = services
    if exception:
        data["data"]["exception"] = exception
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=data)
        resp.raise_for_status()
        return resp.json()

async def build_card_payment(
    card_details: dict, 
    resource_id: str, 
    duffel_token: str,
    multi_use: bool = False
) -> dict:
    """
    Complete card payment flow: Create card + 3DS session
    
    Args:
        card_details: Card information
        resource_id: offer_id, quote_id, or order_id
        duffel_token: Duffel API token
        multi_use: Whether to create multi-use card
    
    Returns:
        Payment object ready for booking: {"type":"card","card_id":...,"three_d_secure_session_id":...}
    """
    logger.info(f"Building card payment for resource: {resource_id}")
    
    # Step 1: Create card
    card_resp = await create_card(card_details, duffel_token, multi_use)
    card_id = card_resp["data"]["id"]
    logger.info(f"Created card with ID: {card_id}")
    
    # Step 2: Create 3DS session
    three_ds_resp = await create_3ds_session(card_id, resource_id, duffel_token)
    three_ds_id = three_ds_resp["data"]["id"]
    logger.info(f"Created 3DS session with ID: {three_ds_id}")
    
    payment = {
        "type": "card",
        "card_id": card_id,
        "three_d_secure_session_id": three_ds_id
    }
    
    logger.info("Card payment built successfully")
    return payment

async def create_multi_use_card(card_details: dict, duffel_token: str) -> dict:
    """
    Create a multi-use card (reusable, no CVC stored)
    
    Args:
        card_details: Card information (CVC will be removed)
        duffel_token: Duffel API token
    
    Returns:
        Multi-use card response
    """
    return await create_card(card_details, duffel_token, multi_use=True)

async def pay_later_for_order(order_id: str, payment: dict, duffel_token: str) -> dict:
    """
    Pay for a hold order later
    
    Args:
        order_id: The hold order ID
        payment: Payment object (balance or card payment)
        duffel_token: Duffel API token
    
    Returns:
        Payment confirmation response
    """
    url = "https://api.duffel.com/air/payments"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Duffel-Version": "v2",
        "Authorization": f"Bearer {duffel_token}"
    }
    
    data = {
        "data": {
            "order_id": order_id,
            "payment": payment
        }
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=data)
        resp.raise_for_status()
        return resp.json()

async def create_balance_payment(amount: str, currency: str) -> dict:
    """
    Create a balance payment object
    
    Args:
        amount: Payment amount
        currency: Payment currency
    
    Returns:
        Balance payment object
    """
    return {
        "type": "balance",
        "amount": amount,
        "currency": currency
    }

async def create_stripe_token(card_details: dict) -> dict:
    """
    Create a Stripe token for a card.
    
    Args:
        card_details: Card information (number, exp_month, exp_year, cvc, name)
    
    Returns:
        Stripe token response with token_id
    
    Example:
        card_details = {
            "number": "4242424242424242",
            "exp_month": "12",
            "exp_year": "2030",
            "cvc": "123",
            "name": "John Doe"
        }
    """
    logger.info("Creating Stripe token")
    
    if not STRIPE_SECRET_KEY:
        logger.error("Stripe secret key not configured")
        raise ValueError("Stripe secret key not configured")
    
    url = "https://api.stripe.com/v1/tokens"
    headers = {
        "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data=card_details
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=data) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.error(f"Stripe token creation failed: {error_text}")
                raise Exception(f"Stripe token creation failed: {error_text}")
            result = await resp.json()
            logger.info(f"Stripe token created: {result.get('id')}")
            return {"token_id": result.get("id")}


async def create_stripe_payment_intent(
    amount: float, 
    currency: str, 
    token_id: str, 
    return_url: str = "https://your-server.com/return"
) -> dict:
    """
    Create a Stripe Payment Intent for a tokenized card using async HTTP client.
    
    Args:
        amount: Payment amount (in dollars, will be converted to cents)
        currency: Payment currency (e.g., "usd")
        token_id: Stripe token ID from create_stripe_token
        return_url: URL for 3DS redirect (if needed)
    
    Returns:
        Stripe Payment Intent response with payment_intent_id
    """
    logger.info(f"Creating Stripe Payment Intent for amount: {amount} {currency}")
    
    if not STRIPE_SECRET_KEY:
        logger.error("Stripe secret key not configured")
        raise ValueError("Stripe secret key not configured")
    
    url = "https://api.stripe.com/v1/payment_intents"
    headers = {
        "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "amount": str(int(float(amount)* 100)),  # Convert to cents
        "currency": currency,
        "payment_method_data[type]": "card",
        "payment_method_data[card][token]": token_id,
        "confirm": "true",
        "automatic_payment_methods[enabled]": "true",
        "return_url": return_url
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=data) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.error(f"Stripe Payment Intent creation failed: {error_text}")
                raise Exception(f"Stripe Payment Intent creation failed: {error_text}")
            result = await resp.json()
            logger.info(f"Stripe Payment Intent created: {result.get('id')}")
            return {"payment_intent_id": result.get("id")}
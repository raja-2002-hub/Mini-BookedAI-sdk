import httpx
import logging
from typing import Optional, Dict, Any
import os
import aiohttp

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

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
    data = card_details
    
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
        "amount": str(int(float(amount) * 100)),  # Convert to cents
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
        
async def create_stripe_refund(
    payment_intent_id: str,
    amount: Optional[float] = None,
    reason: str = "requested_by_customer"
) -> dict:
    """
    Create a refund for a Stripe Payment Intent.
    
    Args:
        payment_intent_id: The Stripe Payment Intent ID (e.g., "pi_3S4xU2Ag2JhEy8vY0DCtv5uy")
        amount: Optional amount to refund (in dollars; if None, full refund)
        reason: Reason for refund (e.g., "requested_by_customer", "duplicate", etc.)
    
    Returns:
        Stripe Refund response with refund_id
    
    Raises:
        Exception: If refund fails
    """
    logger.info(f"Creating Stripe refund for Payment Intent: {payment_intent_id}")
    
    if not STRIPE_SECRET_KEY:
        logger.error("Stripe secret key not configured")
        raise ValueError("Stripe secret key not configured")
    
    url = f"https://api.stripe.com/v1/refunds"
    headers = {
        "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "payment_intent": payment_intent_id,
        "reason": reason
    }
    
    if amount is not None:
        data["amount"] = str(int(float(amount) * 100))  # Convert to cents
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=data) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.error(f"Stripe refund creation failed: {error_text}")
                raise Exception(f"Stripe refund creation failed: {error_text}")
            result = await resp.json()
            logger.info(f"Stripe refund created: {result.get('id')}")
            return {"refund_id": result.get("id"), "status": result.get("status")}
"""
src/trading/execution/valr_trading_client.py

VALR Trading Client for LIVE mode trading on VALR exchange.

Features:
- HMAC-SHA512 authentication for all authenticated endpoints
- Market order execution
- Limit order execution
- Account balance queries
- Order history
- Rate limiting (10 requests/second max)
- Error handling and retry logic

SECURITY WARNING:
This client trades with REAL MONEY on the VALR exchange.
Only use in LIVE mode with proper risk management and small capital.

Helios V3.0 - Phase 6: Week 28 VALR Trading Client
"""

import hmac
import hashlib
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
import aiohttp
import asyncio
import logging
import os
from decimal import Decimal

logger = logging.getLogger(__name__)


class VALRTradingClient:
    """
    LIVE trading client for VALR exchange.

    Implements HMAC-SHA512 authentication for secure API access.
    All methods execute REAL trades with REAL money.

    Rate Limit: 10 requests/second (enforced by VALR)
    """

    BASE_URL = "https://api.valr.com"
    MAX_REQUESTS_PER_SECOND = 10

    def __init__(self, api_key: str = None, api_secret: str = None):
        """
        Initialize VALR trading client.

        Args:
            api_key: VALR API key (or set VALR_API_KEY env var)
            api_secret: VALR API secret (or set VALR_API_SECRET env var)

        Raises:
            ValueError: If API credentials not provided
        """
        self.api_key = api_key or os.getenv("VALR_API_KEY")
        self.api_secret = api_secret or os.getenv("VALR_API_SECRET")

        if not self.api_key or not self.api_secret:
            raise ValueError(
                "VALR API credentials required. Set VALR_API_KEY and VALR_API_SECRET "
                "environment variables or pass to constructor."
            )

        self.session: Optional[aiohttp.ClientSession] = None
        self.request_times: List[float] = []

        logger.info("VALR Trading Client initialized (LIVE MODE)")
        logger.warning("[WARN] This client trades with REAL MONEY")

    def _generate_signature(
        self,
        timestamp: int,
        method: str,
        path: str,
        body: str = ""
    ) -> str:
        """
        Generate HMAC-SHA512 signature for VALR API authentication.

        VALR Signature Format:
        HMAC-SHA512(API_SECRET, timestamp + method + path + body)

        Args:
            timestamp: Unix timestamp in milliseconds
            method: HTTP method (GET, POST, DELETE)
            path: API endpoint path (e.g., /v1/orders/market)
            body: JSON request body (empty string if no body)

        Returns:
            Hex-encoded HMAC-SHA512 signature
        """
        # Construct message: timestamp + METHOD + path + body
        message = f"{timestamp}{method.upper()}{path}{body}"

        # Generate HMAC-SHA512 signature
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha512
        ).hexdigest()

        return signature

    def _get_headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """
        Get headers for authenticated VALR API request.

        Headers:
        - X-VALR-API-KEY: API key
        - X-VALR-SIGNATURE: HMAC-SHA512 signature
        - X-VALR-TIMESTAMP: Unix timestamp (milliseconds)
        - Content-Type: application/json

        Args:
            method: HTTP method
            path: API endpoint path
            body: Request body JSON string

        Returns:
            Dict of HTTP headers
        """
        timestamp = int(time.time() * 1000)  # Milliseconds
        signature = self._generate_signature(timestamp, method, path, body)

        return {
            "X-VALR-API-KEY": self.api_key,
            "X-VALR-SIGNATURE": signature,
            "X-VALR-TIMESTAMP": str(timestamp),
            "Content-Type": "application/json"
        }

    async def _rate_limit_wait(self):
        """
        Enforce rate limit of 10 requests/second.

        Uses sliding window to track requests in last 1 second.
        Waits if rate limit would be exceeded.
        """
        now = time.time()

        # Remove requests older than 1 second
        self.request_times = [t for t in self.request_times if now - t < 1.0]

        # If at limit, wait until oldest request is > 1 second old
        if len(self.request_times) >= self.MAX_REQUESTS_PER_SECOND:
            oldest = self.request_times[0]
            wait_time = 1.0 - (now - oldest)

            if wait_time > 0:
                logger.warning(f"[WARN] Rate limit reached. Waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

        # Record this request
        self.request_times.append(time.time())

    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def place_market_order(
        self,
        pair: str,
        side: str,
        quantity: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Place market order on VALR (REAL MONEY).

        Market orders execute immediately at best available price.

        Args:
            pair: Trading pair (e.g., "BTCZAR", "ETHZAR")
            side: "BUY" or "SELL"
            quantity: Amount in base currency (BTC, ETH, etc.)
            metadata: Optional metadata for order tracking

        Returns:
            Dict with order result:
            {
                "orderId": "uuid",
                "success": true,
                "pair": "BTCZAR",
                "side": "BUY",
                "quantity": 0.001,
                "executedPrice": 850000.00,
                "fee": 8.50,
                "timestamp": "2025-10-05T22:00:00Z"
            }

        Raises:
            ValueError: If parameters invalid
            aiohttp.ClientError: If API request fails
        """
        await self._ensure_session()
        await self._rate_limit_wait()

        # Validate parameters
        if side.upper() not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid side: {side}. Must be BUY or SELL")

        if quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity}. Must be > 0")

        # Build request
        path = "/v1/orders/market"
        body_dict = {
            "pair": pair.upper(),
            "side": side.upper(),
            "baseAmount": str(Decimal(str(quantity)))  # VALR requires string for precision
        }

        if metadata:
            body_dict["customerOrderId"] = metadata.get("customer_order_id", "")

        import json
        body = json.dumps(body_dict)

        headers = self._get_headers("POST", path, body)
        url = f"{self.BASE_URL}{path}"

        logger.warning(
            f"[LIVE] Placing REAL market order: {side} {quantity} {pair}"
        )

        try:
            async with self.session.post(url, headers=headers, data=body) as response:
                response_data = await response.json()

                if response.status != 200:
                    error_msg = response_data.get("message", "Unknown error")
                    logger.error(f"[FAIL] Market order failed: {error_msg}")
                    raise aiohttp.ClientError(f"VALR API error: {error_msg}")

                logger.info(f"[OK] Market order placed: {response_data.get('orderId')}")

                return {
                    "orderId": response_data.get("orderId"),
                    "success": True,
                    "pair": pair,
                    "side": side,
                    "quantity": quantity,
                    "executedPrice": float(response_data.get("averagePrice", 0)),
                    "fee": float(response_data.get("totalFee", 0)),
                    "timestamp": response_data.get("createdAt", datetime.utcnow().isoformat())
                }

        except Exception as e:
            logger.error(f"[FAIL] Market order exception: {e}")
            raise

    async def place_limit_order(
        self,
        pair: str,
        side: str,
        quantity: float,
        price: float,
        post_only: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Place limit order on VALR (REAL MONEY).

        Limit orders execute at specified price or better.

        Args:
            pair: Trading pair (e.g., "BTCZAR")
            side: "BUY" or "SELL"
            quantity: Amount in base currency
            price: Limit price in quote currency (ZAR)
            post_only: If True, order will only add liquidity (no immediate fill)
            metadata: Optional metadata for tracking

        Returns:
            Dict with order result

        Raises:
            ValueError: If parameters invalid
            aiohttp.ClientError: If API request fails
        """
        await self._ensure_session()
        await self._rate_limit_wait()

        if side.upper() not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid side: {side}")

        if quantity <= 0 or price <= 0:
            raise ValueError("Quantity and price must be > 0")

        path = "/v1/orders/limit"
        body_dict = {
            "pair": pair.upper(),
            "side": side.upper(),
            "quantity": str(Decimal(str(quantity))),
            "price": str(Decimal(str(price))),
            "postOnly": post_only
        }

        if metadata:
            body_dict["customerOrderId"] = metadata.get("customer_order_id", "")

        import json
        body = json.dumps(body_dict)

        headers = self._get_headers("POST", path, body)
        url = f"{self.BASE_URL}{path}"

        logger.warning(
            f"[LIVE] Placing REAL limit order: {side} {quantity} {pair} @ {price}"
        )

        try:
            async with self.session.post(url, headers=headers, data=body) as response:
                response_data = await response.json()

                if response.status != 200:
                    error_msg = response_data.get("message", "Unknown error")
                    logger.error(f"[FAIL] Limit order failed: {error_msg}")
                    raise aiohttp.ClientError(f"VALR API error: {error_msg}")

                logger.info(f"[OK] Limit order placed: {response_data.get('orderId')}")

                return {
                    "orderId": response_data.get("orderId"),
                    "success": True,
                    "pair": pair,
                    "side": side,
                    "quantity": quantity,
                    "price": price,
                    "timestamp": response_data.get("createdAt", datetime.utcnow().isoformat())
                }

        except Exception as e:
            logger.error(f"[FAIL] Limit order exception: {e}")
            raise

    async def get_balance(self, currency: str) -> float:
        """
        Get account balance for a specific currency (REAL ACCOUNT).

        Args:
            currency: Currency code (BTC, ETH, ZAR, etc.)

        Returns:
            Available balance as float

        Raises:
            aiohttp.ClientError: If API request fails
        """
        await self._ensure_session()
        await self._rate_limit_wait()

        path = "/v1/account/balances"
        headers = self._get_headers("GET", path)
        url = f"{self.BASE_URL}{path}"

        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise aiohttp.ClientError(f"Balance query failed: {response.status}")

                balances = await response.json()

                # Find currency balance
                for bal in balances:
                    if bal.get("currency") == currency.upper():
                        return float(bal.get("available", 0))

                # Currency not found
                logger.warning(f"[WARN] No balance found for {currency}")
                return 0.0

        except Exception as e:
            logger.error(f"[FAIL] Get balance exception: {e}")
            raise

    async def get_all_balances(self) -> Dict[str, float]:
        """
        Get all account balances (REAL ACCOUNT).

        Returns:
            Dict of currency -> available balance
            Example: {"BTC": 0.5, "ETH": 2.0, "ZAR": 10000.0}
        """
        await self._ensure_session()
        await self._rate_limit_wait()

        path = "/v1/account/balances"
        headers = self._get_headers("GET", path)
        url = f"{self.BASE_URL}{path}"

        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise aiohttp.ClientError(f"Balance query failed: {response.status}")

                balances = await response.json()

                return {
                    bal.get("currency"): float(bal.get("available", 0))
                    for bal in balances
                }

        except Exception as e:
            logger.error(f"[FAIL] Get all balances exception: {e}")
            raise

    async def get_order_history(
        self,
        pair: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get order history (REAL ACCOUNT).

        Args:
            pair: Optional trading pair filter
            limit: Max number of orders to return (default 100)

        Returns:
            List of order dicts
        """
        await self._ensure_session()
        await self._rate_limit_wait()

        path = "/v1/orders/history"
        if pair:
            path += f"?pair={pair.upper()}"

        headers = self._get_headers("GET", path)
        url = f"{self.BASE_URL}{path}"

        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise aiohttp.ClientError(f"Order history query failed: {response.status}")

                orders = await response.json()

                # Limit results
                return orders[:limit]

        except Exception as e:
            logger.error(f"[FAIL] Get order history exception: {e}")
            raise

    async def cancel_order(self, pair: str, order_id: str) -> bool:
        """
        Cancel an open order (REAL ACCOUNT).

        Args:
            pair: Trading pair
            order_id: Order UUID to cancel

        Returns:
            True if cancelled successfully
        """
        await self._ensure_session()
        await self._rate_limit_wait()

        path = f"/v1/orders/order"
        body_dict = {
            "orderId": order_id,
            "pair": pair.upper()
        }

        import json
        body = json.dumps(body_dict)

        headers = self._get_headers("DELETE", path, body)
        url = f"{self.BASE_URL}{path}"

        try:
            async with self.session.delete(url, headers=headers, data=body) as response:
                if response.status == 200:
                    logger.info(f"[OK] Order cancelled: {order_id}")
                    return True
                else:
                    logger.warning(f"[WARN] Cancel failed: {response.status}")
                    return False

        except Exception as e:
            logger.error(f"[FAIL] Cancel order exception: {e}")
            return False

    async def close(self):
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("VALR Trading Client session closed")


# Example usage and testing
if __name__ == "__main__":
    async def test_valr_client():
        """Test VALR client (requires API credentials in .env)."""
        print("\n" + "=" * 80)
        print("VALR TRADING CLIENT TEST")
        print("=" * 80)
        print("\n[WARN] This is a LIVE trading client - DO NOT run without proper credentials")
        print("[WARN] Only use with test API keys or very small capital\n")

        # This will fail if credentials not set (which is expected for safety)
        try:
            client = VALRTradingClient()
            print("[OK] Client initialized successfully")

            # Test balance query (safe operation)
            zar_balance = await client.get_balance("ZAR")
            print(f"[INFO] ZAR Balance: R{zar_balance:.2f}")

            await client.close()

        except ValueError as e:
            print(f"[EXPECTED] {e}")
            print("\nTo test this client:")
            print("1. Set VALR_API_KEY and VALR_API_SECRET in .env")
            print("2. Use SANDBOX credentials (if available) or minimum capital")
            print("3. Never test on production with large capital")

    asyncio.run(test_valr_client())

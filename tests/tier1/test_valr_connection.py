"""
Test VALR API Connection
Verify credentials and test basic API calls
"""

import asyncio
import aiohttp
import hmac
import hashlib
import time
from datetime import datetime
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

VALR_API_KEY = os.getenv("VALR_API_KEY")
VALR_API_SECRET = os.getenv("VALR_API_SECRET")
VALR_BASE_URL = os.getenv("VALR_BASE_URL", "https://api.valr.com")


def generate_signature(api_secret: str, timestamp: int, method: str, path: str, body: str = "") -> str:
    """Generate VALR API signature"""
    payload = f"{timestamp}{method.upper()}{path}{body}"
    signature = hmac.new(
        api_secret.encode(),
        payload.encode(),
        hashlib.sha512
    ).hexdigest()
    return signature


async def test_public_api():
    """Test public API (no authentication required)"""
    print("\n" + "=" * 60)
    print("TEST 1: Public API - Get Market Summary")
    print("=" * 60)

    try:
        async with aiohttp.ClientSession() as session:
            url = f"{VALR_BASE_URL}/v1/public/BTCZAR/marketsummary"

            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"[OK] Public API Working!")
                    print(f"  BTC/ZAR Last Price: R{float(data['lastTradedPrice']):,.2f}")
                    print(f"  24h Change: {float(data['changeFromPrevious']):+.2f}%")
                    print(f"  24h Volume: {float(data['baseVolume']):,.2f} BTC")
                    return True
                else:
                    print(f"[FAIL] Public API Failed: HTTP {response.status}")
                    text = await response.text()
                    print(f"  Error: {text}")
                    return False
    except Exception as e:
        print(f"[FAIL] Public API Error: {e}")
        return False


async def test_authenticated_api():
    """Test authenticated API (requires valid credentials)"""
    print("\n" + "=" * 60)
    print("TEST 2: Authenticated API - Get Account Balances")
    print("=" * 60)

    if not VALR_API_KEY or not VALR_API_SECRET:
        print("[FAIL] API credentials not found in .env file")
        return False

    try:
        timestamp = int(time.time() * 1000)
        path = "/v1/account/balances"
        method = "GET"

        signature = generate_signature(VALR_API_SECRET, timestamp, method, path)

        headers = {
            "X-VALR-API-KEY": VALR_API_KEY,
            "X-VALR-SIGNATURE": signature,
            "X-VALR-TIMESTAMP": str(timestamp)
        }

        async with aiohttp.ClientSession() as session:
            url = f"{VALR_BASE_URL}{path}"

            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"[OK] Authenticated API Working!")
                    print(f"  Account Balances:")

                    for balance in data:
                        available = float(balance.get('available', 0))
                        reserved = float(balance.get('reserved', 0))
                        total = float(balance.get('total', 0))
                        currency = balance['currency']

                        if total > 0:
                            print(f"    - {currency}: {total:,.8f} (Available: {available:,.8f}, Reserved: {reserved:,.8f})")

                    return True
                elif response.status == 401:
                    print(f"[FAIL] Authentication Failed (HTTP 401)")
                    text = await response.text()
                    print(f"  Error: {text}")
                    print(f"\n  Possible issues:")
                    print(f"    - Invalid API key or secret")
                    print(f"    - API key may have been revoked")
                    print(f"    - Incorrect signature generation")
                    return False
                else:
                    print(f"[FAIL] Authenticated API Failed: HTTP {response.status}")
                    text = await response.text()
                    print(f"  Error: {text}")
                    return False
    except Exception as e:
        print(f"[FAIL] Authenticated API Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_orderbook():
    """Test orderbook API"""
    print("\n" + "=" * 60)
    print("TEST 3: Get Order Book")
    print("=" * 60)

    try:
        async with aiohttp.ClientSession() as session:
            url = f"{VALR_BASE_URL}/v1/marketdata/BTCZAR/orderbook"

            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"[OK] Order Book API Working!")

                    # Show top 3 bids and asks
                    bids = data.get('Bids', [])[:3]
                    asks = data.get('Asks', [])[:3]

                    print(f"\n  Top 3 Bids:")
                    for bid in bids:
                        print(f"    R{float(bid['price']):,.2f} x {float(bid['quantity']):,.8f} BTC")

                    print(f"\n  Top 3 Asks:")
                    for ask in asks:
                        print(f"    R{float(ask['price']):,.2f} x {float(ask['quantity']):,.8f} BTC")

                    # Calculate spread
                    if bids and asks:
                        best_bid = float(bids[0]['price'])
                        best_ask = float(asks[0]['price'])
                        spread = best_ask - best_bid
                        spread_pct = (spread / best_bid) * 100
                        print(f"\n  Spread: R{spread:,.2f} ({spread_pct:.3f}%)")

                    return True
                else:
                    print(f"[FAIL] Order Book API Failed: HTTP {response.status}")
                    return False
    except Exception as e:
        print(f"[FAIL] Order Book Error: {e}")
        return False


async def main():
    """Run all tests"""
    print("\n")
    print("=" * 60)
    print("  VALR API CONNECTION TEST")
    print("=" * 60)
    print(f"  Base URL: {VALR_BASE_URL}")
    print(f"  API Key: {VALR_API_KEY[:16]}..." if VALR_API_KEY else "  API Key: NOT SET")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = []

    # Test 1: Public API
    results.append(await test_public_api())
    await asyncio.sleep(1)

    # Test 2: Authenticated API
    results.append(await test_authenticated_api())
    await asyncio.sleep(1)

    # Test 3: Order Book
    results.append(await test_orderbook())

    # Summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)
    print(f"  Total Tests: {len(results)}")
    print(f"  Passed: {sum(results)}")
    print(f"  Failed: {len(results) - sum(results)}")

    if all(results):
        print("\n  [OK] ALL TESTS PASSED!")
        print("  VALR API connection is working correctly.")
        print("\n  Next step: Build Tier 1 WebSocket client")
    else:
        print("\n  [FAIL] SOME TESTS FAILED")
        if not results[1]:  # Auth test failed
            print("\n  Authentication failed - please verify:")
            print("    1. API key and secret are correct")
            print("    2. API key has not been revoked")
            print("    3. API key has appropriate permissions")

    print("=" * 60)
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())

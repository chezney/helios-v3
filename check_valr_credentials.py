"""
Check VALR API Credentials and Account Balance
This is for PRE-LIVE audit only - verifying we can connect to VALR
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def check_valr_connection():
    """Check VALR API connection and account balance"""

    # Check if credentials are loaded
    api_key = os.getenv("VALR_API_KEY")
    api_secret = os.getenv("VALR_API_SECRET")

    print("=" * 80)
    print("VALR API CREDENTIALS CHECK")
    print("=" * 80)

    if not api_key or not api_secret:
        print("[ERROR] VALR credentials not found in .env file")
        print("   Please set VALR_API_KEY and VALR_API_SECRET")
        return False

    print(f"[OK] API Key found: {api_key[:8]}...{api_key[-8:]}")
    print(f"[OK] API Secret found: {api_secret[:8]}...{api_secret[-8:]}")

    # Try to connect to VALR
    try:
        from src.trading.execution.valr_trading_client import VALRTradingClient

        client = VALRTradingClient(
            api_key=api_key,
            api_secret=api_secret
        )

        print("\n[CONNECTING] Connecting to VALR API...")

        # Get account balances
        balances = await client.get_all_balances()

        print("[SUCCESS] VALR API Connection: SUCCESS\n")

        print("Account Balances:")
        print("-" * 80)

        total_value_zar = 0.0
        for currency, balance in balances.items():
            if balance > 0:
                if currency == "ZAR":
                    print(f"  {currency:10s}: R{balance:15,.2f}")
                    total_value_zar += balance
                else:
                    print(f"  {currency:10s}: {balance:20,.8f}")

        # Get ZAR balance specifically
        zar_balance = await client.get_balance("ZAR")
        print(f"\n[BALANCE] Available ZAR: R{zar_balance:,.2f}")

        # Close connection
        await client.close()

        print("\n" + "=" * 80)
        print("RECOMMENDATION FOR LIVE MODE:")
        print("=" * 80)

        if zar_balance >= 500:
            print(f"[OK] Sufficient balance for LIVE mode testing (R{zar_balance:,.2f})")
            print("   Recommended starting capital: R500 - R1,000")
            print(f"   You have: R{zar_balance:,.2f}")
        else:
            print(f"[WARNING] Low balance: R{zar_balance:,.2f}")
            print("   Consider adding funds before LIVE testing")
            print("   Minimum recommended: R500")

        return True

    except Exception as e:
        print(f"\n[ERROR] VALR API Connection FAILED: {e}")
        print("\nPossible issues:")
        print("  1. Invalid API credentials")
        print("  2. API key permissions not set correctly")
        print("  3. Network connectivity issue")
        print("  4. VALR API temporarily down")
        return False

if __name__ == "__main__":
    asyncio.run(check_valr_connection())

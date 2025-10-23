"""
Create Tier 3 Database Tables

Creates tables for:
1. volatility_forecasts - GARCH volatility forecasts
2. aether_risk_decisions - Position sizing and leverage decisions
3. portfolio_state - Portfolio value and drawdown tracking
"""

import asyncio
import asyncpg
from config.settings import settings


async def create_tier3_tables():
    """Create all Tier 3 database tables."""

    conn = await asyncpg.connect(
        host=settings.database.postgres_host,
        port=settings.database.postgres_port,
        user=settings.database.postgres_user,
        password=settings.database.postgres_password,
        database=settings.database.postgres_db
    )

    try:
        print("Creating Tier 3 tables...")
        print("=" * 80)

        # Table 1: volatility_forecasts
        print("\n1. Creating volatility_forecasts table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS volatility_forecasts (
                id SERIAL PRIMARY KEY,
                pair VARCHAR(20) NOT NULL,

                -- Volatility metrics
                daily_volatility DECIMAL(10, 6),
                annualized_volatility DECIMAL(10, 6),
                volatility_regime VARCHAR(20),  -- LOW, MEDIUM, HIGH, EXTREME

                -- GARCH parameters
                garch_omega DECIMAL(15, 10),
                garch_alpha DECIMAL(10, 6),
                garch_beta DECIMAL(10, 6),

                forecast_timestamp TIMESTAMP DEFAULT NOW()
            )
        """)

        # Create index for fast lookups
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vol_pair_timestamp
            ON volatility_forecasts(pair, forecast_timestamp DESC)
        """)
        print("   [OK] volatility_forecasts table created")

        # Table 2: aether_risk_decisions
        print("\n2. Creating aether_risk_decisions table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS aether_risk_decisions (
                id SERIAL PRIMARY KEY,
                pair VARCHAR(20) NOT NULL,
                signal VARCHAR(10) NOT NULL,  -- BUY, SELL
                confidence DECIMAL(5, 4),

                -- Kelly calculations
                kelly_fraction DECIMAL(10, 6),
                fractional_kelly DECIMAL(10, 6),
                volatility_adjusted_fraction DECIMAL(10, 6),

                -- Trade parameters
                position_size_zar DECIMAL(20, 2),
                leverage DECIMAL(3, 1),
                stop_loss_pct DECIMAL(6, 4),
                take_profit_pct DECIMAL(6, 4),

                -- Market conditions at decision time
                daily_volatility DECIMAL(10, 6),
                volatility_regime VARCHAR(20),
                portfolio_value_zar DECIMAL(20, 2),
                drawdown_pct DECIMAL(6, 4),

                -- Outcome tracking
                executed BOOLEAN DEFAULT false,
                execution_id INTEGER,  -- References trades table (future)

                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Create index for fast lookups
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_aether_pair_created
            ON aether_risk_decisions(pair, created_at DESC)
        """)
        print("   [OK] aether_risk_decisions table created")

        # Table 3: portfolio_state
        print("\n3. Creating portfolio_state table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_state (
                id INTEGER PRIMARY KEY DEFAULT 1,
                total_value_zar DECIMAL(20, 2),
                peak_value_zar DECIMAL(20, 2),
                current_drawdown_pct DECIMAL(6, 4),
                max_drawdown_pct DECIMAL(6, 4),
                last_updated TIMESTAMP DEFAULT NOW(),

                -- Ensure only one row
                CONSTRAINT single_row CHECK (id = 1)
            )
        """)
        print("   [OK] portfolio_state table created")

        # Initialize portfolio state with default values
        print("\n4. Initializing portfolio state...")
        await conn.execute("""
            INSERT INTO portfolio_state (
                id, total_value_zar, peak_value_zar,
                current_drawdown_pct, max_drawdown_pct
            )
            VALUES (1, 100000.00, 100000.00, 0.0000, 0.0000)
            ON CONFLICT (id) DO NOTHING
        """)
        print("   [OK] Portfolio state initialized (R100,000)")

        print("\n" + "=" * 80)
        print("[SUCCESS] All Tier 3 tables created successfully!")
        print("\nTables created:")
        print("  1. volatility_forecasts (with index)")
        print("  2. aether_risk_decisions (with index)")
        print("  3. portfolio_state (initialized)")
        print("=" * 80)

    except Exception as e:
        print(f"\n[ERROR] Error creating tables: {e}")
        raise

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_tier3_tables())

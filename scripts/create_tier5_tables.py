"""
Create Tier 5 (Portfolio Manager) database tables.

Helios V3.0 - Phase 5: Guardian Portfolio Manager
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def create_tier5_tables():
    """Create all Tier 5 database tables and indexes."""

    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST'),
        port=int(os.getenv('POSTGRES_PORT')),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database=os.getenv('POSTGRES_DB')
    )

    try:
        print("=" * 60)
        print("CREATING TIER 5 (PORTFOLIO MANAGER) DATABASE TABLES")
        print("=" * 60)
        print()

        # Table 1: portfolio_state
        print("[1/4] Creating portfolio_state table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_state (
                id SERIAL PRIMARY KEY,
                total_value_zar DECIMAL(20, 2) NOT NULL,
                peak_value_zar DECIMAL(20, 2) NOT NULL,
                current_drawdown_pct DECIMAL(10, 4) DEFAULT 0.0,
                max_drawdown_pct DECIMAL(10, 4) DEFAULT 0.0,
                last_updated TIMESTAMP DEFAULT NOW()
            )
        """)
        print("[OK] Created table: portfolio_state")

        # Initialize portfolio_state with default R100,000
        await conn.execute("""
            INSERT INTO portfolio_state (id, total_value_zar, peak_value_zar, current_drawdown_pct, max_drawdown_pct)
            VALUES (1, 100000.00, 100000.00, 0.0, 0.0)
            ON CONFLICT (id) DO NOTHING
        """)
        print("[OK] Initialized portfolio_state with R100,000")

        # Table 2: positions (drop existing if schema mismatch)
        print("[2/4] Creating positions table...")
        await conn.execute("DROP TABLE IF EXISTS positions CASCADE")
        await conn.execute("""
            CREATE TABLE positions (
                id SERIAL PRIMARY KEY,
                pair VARCHAR(20) NOT NULL,
                signal VARCHAR(10) NOT NULL,

                -- Entry
                entry_price DECIMAL(20, 8),
                entry_time TIMESTAMP,
                quantity DECIMAL(20, 8),
                position_value_zar DECIMAL(20, 2),
                leverage DECIMAL(3, 1),

                -- Exit
                exit_price DECIMAL(20, 8),
                exit_time TIMESTAMP,
                pnl_pct DECIMAL(10, 4),
                pnl_zar DECIMAL(20, 2),

                -- Risk parameters
                stop_loss_price DECIMAL(20, 8),
                take_profit_price DECIMAL(20, 8),
                stop_loss_pct DECIMAL(6, 4),
                take_profit_pct DECIMAL(6, 4),

                -- Metadata
                strategic_reasoning TEXT,
                order_id VARCHAR(100),
                status VARCHAR(20) DEFAULT 'OPEN',
                close_reason VARCHAR(50),

                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("[OK] Created table: positions")

        # Indexes for positions
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_pair_created ON positions(pair, created_at DESC)
        """)
        print("[OK] Created indexes: idx_positions_status, idx_positions_pair_created")

        # Table 3: portfolio_snapshots
        print("[3/4] Creating portfolio_snapshots table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id SERIAL PRIMARY KEY,
                total_value_zar DECIMAL(20, 2),
                num_open_positions INTEGER,
                daily_pnl_zar DECIMAL(20, 2),
                daily_pnl_pct DECIMAL(10, 4),
                sharpe_ratio DECIMAL(10, 4),
                snapshot_time TIMESTAMP DEFAULT NOW()
            )
        """)
        print("[OK] Created table: portfolio_snapshots")

        # Index for portfolio_snapshots
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_time ON portfolio_snapshots(snapshot_time DESC)
        """)
        print("[OK] Created index: idx_snapshots_time")

        # Table 4: rebalancing_events
        print("[4/4] Creating rebalancing_events table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rebalancing_events (
                id SERIAL PRIMARY KEY,
                target_weights JSONB,
                actual_weights_before JSONB,
                actual_weights_after JSONB,
                trades_executed JSONB,
                reason TEXT,
                executed_at TIMESTAMP DEFAULT NOW()
            )
        """)
        print("[OK] Created table: rebalancing_events")

        print()
        print("=" * 60)
        print("[SUCCESS] ALL TIER 5 TABLES CREATED SUCCESSFULLY")
        print("=" * 60)
        print()
        print("Tables created:")
        print("  1. portfolio_state (with R100,000 initial value)")
        print("  2. positions (16 columns + 2 indexes)")
        print("  3. portfolio_snapshots (6 columns + 1 index)")
        print("  4. rebalancing_events (6 columns)")
        print()

        # Verify tables exist
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('portfolio_state', 'positions', 'portfolio_snapshots', 'rebalancing_events')
            ORDER BY table_name
        """)

        print("Verification:")
        for table in tables:
            print(f"  [OK] {table['table_name']}")

    except Exception as e:
        print(f"\n[ERROR] Failed to create Tier 5 tables: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_tier5_tables())

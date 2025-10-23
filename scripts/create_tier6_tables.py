"""
scripts/create_tier6_tables.py

Create Tier 6 (Autonomous Trading Engine) database tables.

Tables:
1. trading_mode_state - Current trading mode (PAPER vs LIVE)
2. trading_mode_history - Historical mode changes

Helios V3.0 - Phase 6: Autonomous Trading Engine Database Setup
"""

import asyncio
import asyncpg
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

POSTGRES_USER = os.getenv("POSTGRES_USER", "helios_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "helios_db")


async def create_tier6_tables():
    """Create all Tier 6 database tables."""

    print("=" * 80)
    print("TIER 6 - AUTONOMOUS TRADING ENGINE: DATABASE SETUP")
    print("=" * 80)
    print()

    # Connect to database
    conn = await asyncpg.connect(
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT
    )

    print(f"[OK] Connected to PostgreSQL: {POSTGRES_DB}")
    print()

    # -------------------------------------------------------------------------
    # TABLE 1: trading_mode_state
    # -------------------------------------------------------------------------
    print("Creating table: trading_mode_state")
    print("-" * 80)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS trading_mode_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            current_mode VARCHAR(10) NOT NULL DEFAULT 'PAPER',
            last_changed_at TIMESTAMP,
            changed_by VARCHAR(100),
            change_reason TEXT,
            created_at TIMESTAMP DEFAULT NOW(),

            CONSTRAINT check_id_is_one CHECK (id = 1),
            CONSTRAINT check_mode_valid CHECK (current_mode IN ('PAPER', 'LIVE'))
        )
    """)

    print("[OK] Table created: trading_mode_state")
    print()
    print("Schema:")
    print("  - id: INTEGER (always 1, singleton)")
    print("  - current_mode: VARCHAR(10) (PAPER or LIVE)")
    print("  - last_changed_at: TIMESTAMP")
    print("  - changed_by: VARCHAR(100)")
    print("  - change_reason: TEXT")
    print("  - created_at: TIMESTAMP")
    print()

    # -------------------------------------------------------------------------
    # TABLE 2: trading_mode_history
    # -------------------------------------------------------------------------
    print("Creating table: trading_mode_history")
    print("-" * 80)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS trading_mode_history (
            id SERIAL PRIMARY KEY,
            from_mode VARCHAR(10) NOT NULL,
            to_mode VARCHAR(10) NOT NULL,
            changed_at TIMESTAMP DEFAULT NOW(),
            reason TEXT,

            CONSTRAINT check_from_mode_valid CHECK (from_mode IN ('PAPER', 'LIVE')),
            CONSTRAINT check_to_mode_valid CHECK (to_mode IN ('PAPER', 'LIVE'))
        )
    """)

    print("[OK] Table created: trading_mode_history")
    print()
    print("Schema:")
    print("  - id: SERIAL PRIMARY KEY")
    print("  - from_mode: VARCHAR(10) (PAPER or LIVE)")
    print("  - to_mode: VARCHAR(10) (PAPER or LIVE)")
    print("  - changed_at: TIMESTAMP")
    print("  - reason: TEXT")
    print()

    # -------------------------------------------------------------------------
    # Create indexes
    # -------------------------------------------------------------------------
    print("Creating indexes...")
    print("-" * 80)

    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_mode_history_timestamp
        ON trading_mode_history(changed_at DESC)
    """)

    print("[OK] Index created: idx_mode_history_timestamp")
    print()

    # -------------------------------------------------------------------------
    # Initialize trading_mode_state with PAPER mode
    # -------------------------------------------------------------------------
    print("Initializing trading mode state...")
    print("-" * 80)

    await conn.execute("""
        INSERT INTO trading_mode_state (id, current_mode, last_changed_at, changed_by, change_reason)
        VALUES (1, 'PAPER', $1, 'system', 'Initial setup')
        ON CONFLICT (id) DO NOTHING
    """, datetime.utcnow())

    # Check if row was inserted
    row = await conn.fetchrow("SELECT current_mode FROM trading_mode_state WHERE id = 1")
    current_mode = row['current_mode']

    print(f"[OK] Trading mode initialized: {current_mode}")
    print()

    # -------------------------------------------------------------------------
    # Verify tables
    # -------------------------------------------------------------------------
    print("Verifying table creation...")
    print("-" * 80)

    # Check trading_mode_state
    state_count = await conn.fetchval("SELECT COUNT(*) FROM trading_mode_state")
    print(f"[OK] trading_mode_state: {state_count} row(s)")

    # Check trading_mode_history
    history_count = await conn.fetchval("SELECT COUNT(*) FROM trading_mode_history")
    print(f"[OK] trading_mode_history: {history_count} row(s)")
    print()

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print("=" * 80)
    print("TIER 6 DATABASE SETUP COMPLETE")
    print("=" * 80)
    print()
    print("Tables Created:")
    print("  1. trading_mode_state (singleton, tracks current mode)")
    print("  2. trading_mode_history (logs all mode changes)")
    print()
    print("Indexes Created:")
    print("  - idx_mode_history_timestamp (for fast history queries)")
    print()
    print("Initial State:")
    print(f"  Current Mode: {current_mode}")
    print()
    print("[OK] All Tier 6 tables created successfully!")
    print()

    await conn.close()


async def verify_tier6_tables():
    """Verify all Tier 6 tables exist and have correct schema."""

    print("=" * 80)
    print("TIER 6 TABLE VERIFICATION")
    print("=" * 80)
    print()

    conn = await asyncpg.connect(
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT
    )

    # Check trading_mode_state schema
    print("Checking trading_mode_state schema...")
    columns = await conn.fetch("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'trading_mode_state'
        ORDER BY ordinal_position
    """)

    print("Columns:")
    for col in columns:
        print(f"  - {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
    print()

    # Check trading_mode_history schema
    print("Checking trading_mode_history schema...")
    columns = await conn.fetch("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'trading_mode_history'
        ORDER BY ordinal_position
    """)

    print("Columns:")
    for col in columns:
        print(f"  - {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
    print()

    # Check constraints
    print("Checking constraints...")
    constraints = await conn.fetch("""
        SELECT constraint_name, constraint_type
        FROM information_schema.table_constraints
        WHERE table_name IN ('trading_mode_state', 'trading_mode_history')
        ORDER BY table_name, constraint_type
    """)

    for constraint in constraints:
        print(f"  - {constraint['constraint_name']}: {constraint['constraint_type']}")
    print()

    # Check indexes
    print("Checking indexes...")
    indexes = await conn.fetch("""
        SELECT indexname, tablename
        FROM pg_indexes
        WHERE tablename IN ('trading_mode_state', 'trading_mode_history')
    """)

    for idx in indexes:
        print(f"  - {idx['indexname']} on {idx['tablename']}")
    print()

    print("[OK] Tier 6 table verification complete!")
    print()

    await conn.close()


async def main():
    """Main execution function."""
    try:
        # Create tables
        await create_tier6_tables()

        # Verify tables
        await verify_tier6_tables()

    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

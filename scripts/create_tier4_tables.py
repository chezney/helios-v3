"""
Tier 4 Database Schema Creation Script

Creates tables for LLM Strategic Execution Layer:
- llm_strategic_decisions: Strategic trade decisions with LLM reasoning
- market_context_snapshots: Market context for debugging and analysis

Run: python scripts/create_tier4_tables.py
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()


async def create_tier4_tables():
    """Create Tier 4 database tables."""

    # Database connection
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'helios'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database=os.getenv('POSTGRES_DB', 'helios_v3')
    )

    try:
        print("Creating Tier 4 tables...")

        # Table 1: llm_strategic_decisions
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_strategic_decisions (
                id SERIAL PRIMARY KEY,
                pair VARCHAR(20) NOT NULL,
                signal VARCHAR(10) NOT NULL,
                ml_confidence DECIMAL(5, 4),

                -- Proposed trade parameters
                proposed_position_size_zar DECIMAL(20, 2),
                proposed_leverage DECIMAL(3, 1),

                -- LLM analysis
                llm_decision VARCHAR(10) NOT NULL,  -- APPROVE, REJECT, MODIFY
                llm_reasoning TEXT,
                confidence_adjustment DECIMAL(5, 4),
                position_size_multiplier DECIMAL(5, 2),
                risk_flags TEXT,  -- Comma-separated

                -- Final outcome
                final_approved BOOLEAN,
                final_position_size_zar DECIMAL(20, 2),

                -- Metadata
                llm_provider VARCHAR(20),
                llm_model VARCHAR(50),

                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        print("[OK] Created table: llm_strategic_decisions")

        # Table 2: market_context_snapshots
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS market_context_snapshots (
                id SERIAL PRIMARY KEY,
                pair VARCHAR(20) NOT NULL,

                -- Market context data (JSONB for flexibility)
                price_action JSONB,
                correlations JSONB,
                microstructure JSONB,

                -- Regime classifications
                trend_regime VARCHAR(20),
                volatility_regime VARCHAR(20),
                liquidity_regime VARCHAR(20),
                correlation_regime VARCHAR(20),

                -- Recent ML performance
                recent_predictions JSONB,

                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        print("[OK] Created table: market_context_snapshots")

        # Create indexes
        print("\nCreating indexes...")

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_decisions_pair_created
            ON llm_strategic_decisions(pair, created_at DESC);
        """)
        print("[OK] Created index: idx_llm_decisions_pair_created")

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_decisions_approved
            ON llm_strategic_decisions(final_approved, created_at DESC);
        """)
        print("[OK] Created index: idx_llm_decisions_approved")

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_llm_decisions_decision
            ON llm_strategic_decisions(llm_decision, created_at DESC);
        """)
        print("[OK] Created index: idx_llm_decisions_decision")

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_context_snapshots_pair
            ON market_context_snapshots(pair, created_at DESC);
        """)
        print("[OK] Created index: idx_context_snapshots_pair")

        # Verify tables
        print("\nVerifying tables...")
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('llm_strategic_decisions', 'market_context_snapshots')
            ORDER BY table_name;
        """)

        for table in tables:
            print(f"[OK] Verified: {table['table_name']}")

        print("\n[SUCCESS] Tier 4 tables created successfully!")
        print("\nTables created:")
        print("  - llm_strategic_decisions (strategic trade decisions)")
        print("  - market_context_snapshots (market context for debugging)")
        print("\nIndexes created:")
        print("  - idx_llm_decisions_pair_created")
        print("  - idx_llm_decisions_approved")
        print("  - idx_llm_decisions_decision")
        print("  - idx_context_snapshots_pair")

    except Exception as e:
        print(f"\n[ERROR] Error creating Tier 4 tables: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_tier4_tables())

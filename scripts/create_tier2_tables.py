"""
Helios V3.0 - Phase 2: Create Tier 2 Database Tables

Creates tables for:
- ML predictions storage
- Model version tracking

Usage:
    python scripts/create_tier2_tables.py
"""

import asyncio
import asyncpg
from config.settings import settings
from src.utils.logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__, component="tier2_db_setup")


async def create_tier2_tables():
    """Create Tier 2 database tables for ML predictions and model tracking."""

    logger.info("Connecting to PostgreSQL...")

    conn = await asyncpg.connect(
        host=settings.database.postgres_host,
        port=settings.database.postgres_port,
        user=settings.database.postgres_user,
        password=settings.database.postgres_password,
        database=settings.database.postgres_db
    )

    try:
        # =====================================================
        # Table 1: ML Predictions
        # =====================================================
        logger.info("Creating ml_predictions table...")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_predictions (
                id SERIAL PRIMARY KEY,
                pair VARCHAR(20) NOT NULL,
                model_version VARCHAR(50) NOT NULL,
                prediction VARCHAR(10) NOT NULL,
                buy_probability DECIMAL(5, 4),
                sell_probability DECIMAL(5, 4),
                hold_probability DECIMAL(5, 4),
                confidence_score DECIMAL(5, 4),
                max_probability DECIMAL(5, 4),
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        # Create indexes for fast queries
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ml_predictions_pair
            ON ml_predictions(pair);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ml_predictions_created_at
            ON ml_predictions(created_at DESC);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ml_predictions_pair_created
            ON ml_predictions(pair, created_at DESC);
        """)

        logger.info("✓ ml_predictions table created")

        # =====================================================
        # Table 2: ML Models
        # =====================================================
        logger.info("Creating ml_models table...")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_models (
                id SERIAL PRIMARY KEY,
                version VARCHAR(50) UNIQUE NOT NULL,
                validation_accuracy DECIMAL(5, 4),
                validation_loss DECIMAL(8, 6),
                train_accuracy DECIMAL(5, 4),
                train_loss DECIMAL(8, 6),
                total_parameters BIGINT,
                epochs_trained INTEGER,
                trained_at TIMESTAMP,
                model_path VARCHAR(255),
                scaler_path VARCHAR(255),
                config_json JSONB,
                active BOOLEAN DEFAULT false,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ml_models_active
            ON ml_models(active);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ml_models_version
            ON ml_models(version);
        """)

        logger.info("✓ ml_models table created")

        # =====================================================
        # Table 3: Prediction Performance (for backtesting)
        # =====================================================
        logger.info("Creating prediction_performance table...")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS prediction_performance (
                id SERIAL PRIMARY KEY,
                prediction_id INTEGER REFERENCES ml_predictions(id),
                pair VARCHAR(20) NOT NULL,
                predicted_class VARCHAR(10) NOT NULL,
                actual_outcome VARCHAR(10),
                actual_return DECIMAL(8, 6),
                time_horizon_minutes INTEGER,
                correct BOOLEAN,
                evaluated_at TIMESTAMP DEFAULT NOW()
            );
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_prediction_performance_pair
            ON prediction_performance(pair);
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_prediction_performance_correct
            ON prediction_performance(correct);
        """)

        logger.info("✓ prediction_performance table created")

        # =====================================================
        # Verification
        # =====================================================
        logger.info("Verifying table creation...")

        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('ml_predictions', 'ml_models', 'prediction_performance')
            ORDER BY table_name;
        """)

        logger.info(f"Created {len(tables)} Tier 2 tables:")
        for table in tables:
            logger.info(f"  - {table['table_name']}")

        # Display schema
        print("\n" + "=" * 80)
        print("  TIER 2 DATABASE SCHEMA")
        print("=" * 80)
        print()

        for table_name in ['ml_predictions', 'ml_models', 'prediction_performance']:
            columns = await conn.fetch("""
                SELECT column_name, data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_name = $1
                ORDER BY ordinal_position;
            """, table_name)

            print(f"Table: {table_name}")
            print("-" * 80)
            for col in columns:
                col_type = col['data_type']
                if col['character_maximum_length']:
                    col_type += f"({col['character_maximum_length']})"
                print(f"  {col['column_name']:30} {col_type}")
            print()

        print("=" * 80)
        print("  TIER 2 TABLES CREATED SUCCESSFULLY")
        print("=" * 80)
        print()

    except Exception as e:
        logger.error(f"Failed to create Tier 2 tables: {e}")
        raise

    finally:
        await conn.close()
        logger.info("Database connection closed")


async def main():
    """Main entry point."""
    print("=" * 80)
    print("  HELIOS V3.0 - TIER 2 DATABASE SETUP")
    print("  Phase 2: Neural Network Tables")
    print("=" * 80)
    print()

    await create_tier2_tables()

    print("\nNext steps:")
    print("  1. Train the neural network: python train_neural_network.py")
    print("  2. Start the prediction service via API")
    print("  3. Monitor predictions in ml_predictions table")
    print()


if __name__ == "__main__":
    asyncio.run(main())

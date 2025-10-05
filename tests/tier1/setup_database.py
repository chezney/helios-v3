"""
Setup and initialize Helios V3.0 databases
Creates database schema and verifies connections
"""

import sys
import os
# Add project root to path (two levels up from tests/tier1/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import asyncio
import asyncpg
from datetime import datetime
from pathlib import Path

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__, component="database_setup")


async def test_postgres_connection():
    """Test PostgreSQL connection"""
    print("\n" + "=" * 80)
    print("  TESTING POSTGRESQL CONNECTION")
    print("=" * 80)

    try:
        # Connect to default postgres database first
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database='postgres'  # Connect to default DB first
        )

        print(f"[OK] Connected to PostgreSQL server")
        print(f"  Host: {settings.database.postgres_host}")
        print(f"  Port: {settings.database.postgres_port}")
        print(f"  User: {settings.database.postgres_user}")

        # Check if helios_v3 database exists
        result = await conn.fetchrow(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            settings.database.postgres_db
        )

        if result:
            print(f"[OK] Database '{settings.database.postgres_db}' exists")
        else:
            print(f"[INFO] Database '{settings.database.postgres_db}' does not exist")
            print(f"[ACTION] Creating database '{settings.database.postgres_db}'...")

            # Create database
            await conn.execute(f'CREATE DATABASE {settings.database.postgres_db}')
            print(f"[OK] Database '{settings.database.postgres_db}' created")

        await conn.close()

        # Now connect to helios_v3 database
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        print(f"[OK] Connected to database '{settings.database.postgres_db}'")

        # Get PostgreSQL version
        version = await conn.fetchval("SELECT version()")
        print(f"[INFO] PostgreSQL Version: {version.split(',')[0]}")

        await conn.close()
        return True

    except Exception as e:
        print(f"[FAIL] PostgreSQL connection failed: {e}")
        return False




async def create_database_schema():
    """Create database schema from SQL file"""
    print("\n" + "=" * 80)
    print("  CREATING DATABASE SCHEMA")
    print("=" * 80)

    schema_file = Path("database/schema.sql")

    if not schema_file.exists():
        print(f"[WARNING] Schema file not found: {schema_file}")
        print(f"[INFO] Skipping schema creation")
        return False

    try:
        # Read schema file
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        print(f"[INFO] Reading schema from: {schema_file}")
        print(f"[INFO] Schema file size: {len(schema_sql)} characters")

        # Connect to database
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        # Execute schema
        print(f"[ACTION] Executing schema SQL...")
        await conn.execute(schema_sql)
        print(f"[OK] Schema created successfully")

        # List tables
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)

        print(f"\n[INFO] Created {len(tables)} tables:")
        for table in tables:
            # Get row count
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table['table_name']}")
            print(f"  - {table['table_name']:<30} ({count} rows)")

        await conn.close()
        return True

    except Exception as e:
        print(f"[FAIL] Schema creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main setup function"""
    print("\n" + "=" * 80)
    print("  HELIOS V3.0 DATABASE SETUP")
    print("  PostgreSQL Only (as per PRD Section 3)")
    print("=" * 80)
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = []

    # Test PostgreSQL (PRIMARY DATABASE)
    pg_result = await test_postgres_connection()
    results.append(("PostgreSQL", pg_result))

    # Create schema if PostgreSQL is working
    if pg_result:
        schema_result = await create_database_schema()
        results.append(("Schema Creation", schema_result))

    # Summary
    print("\n" + "=" * 80)
    print("  SETUP SUMMARY")
    print("=" * 80)

    for name, result in results:
        status = "[OK]" if result else "[FAIL]"
        print(f"  {status} {name}")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    print("\n" + "=" * 80)
    if passed == total:
        print("  [SUCCESS] All database tests passed!")
        print("  Helios V3.0 is ready to run with full database support.")
    else:
        print(f"  [PARTIAL] {passed}/{total} tests passed")
        print("  Some databases may not be available.")
        print("  Check the errors above and ensure Docker containers are running.")

    print("=" * 80 + "\n")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

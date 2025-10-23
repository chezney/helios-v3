"""
Database Connection Management for Helios V3.0

Provides database session management for SQLAlchemy and asyncpg.
"""

import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()

# Database configuration
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'helios')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'helios_v3')

# Create database URL
DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base for declarative models
Base = declarative_base()


def get_db_connection_string() -> str:
    """
    Get database connection string.

    Returns:
        Database connection string
    """
    return DATABASE_URL


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session (dependency injection for FastAPI).

    Yields:
        AsyncSession: Database session

    Example:
        @router.get("/test")
        async def test_endpoint(db: AsyncSession = Depends(get_db_session)):
            result = await db.execute(text("SELECT 1"))
            return {"result": result.scalar()}
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Alias for compatibility
get_db = get_db_session


async def init_database():
    """
    Initialize database (create tables if needed).

    This is called on application startup.
    """
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)


async def close_database():
    """
    Close database connections.

    This is called on application shutdown.
    """
    await engine.dispose()

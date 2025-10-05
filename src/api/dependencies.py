"""
Helios Trading System V3.0 - Database Dependencies
Connection management for PostgreSQL, Redis, and InfluxDB
"""

import asyncpg
import redis.asyncio as aioredis
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__, component="database")


class DatabaseProvider:
    """Centralized database connection management"""

    def __init__(self):
        self._postgres_pool: Optional[asyncpg.Pool] = None
        self._redis_client: Optional[aioredis.Redis] = None
        self._influx_client: Optional[InfluxDBClientAsync] = None

    async def initialize_postgres(self) -> asyncpg.Pool:
        """Initialize PostgreSQL connection pool"""
        if self._postgres_pool is None:
            logger.info("Initializing PostgreSQL connection pool")
            try:
                self._postgres_pool = await asyncpg.create_pool(
                    host=settings.database.postgres_host,
                    port=settings.database.postgres_port,
                    database=settings.database.postgres_db,
                    user=settings.database.postgres_user,
                    password=settings.database.postgres_password,
                    min_size=5,
                    max_size=20,
                    command_timeout=60,
                )
                logger.info("PostgreSQL pool created successfully")
            except Exception as e:
                logger.error(f"Failed to create PostgreSQL pool: {e}", exc_info=True)
                raise
        return self._postgres_pool

    async def initialize_redis(self) -> aioredis.Redis:
        """Initialize Redis connection"""
        if self._redis_client is None:
            logger.info("Initializing Redis connection")
            try:
                self._redis_client = aioredis.from_url(
                    settings.database.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=50,
                )
                # Test connection
                await self._redis_client.ping()
                logger.info("Redis connection established successfully")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
                raise
        return self._redis_client

    def initialize_influx(self) -> InfluxDBClientAsync:
        """Initialize InfluxDB connection"""
        if self._influx_client is None:
            logger.info("Initializing InfluxDB client")
            try:
                self._influx_client = InfluxDBClientAsync(
                    url=settings.database.influx_url,
                    token=settings.database.influx_token,
                    org=settings.database.influx_org,
                    timeout=30000,
                )
                logger.info("InfluxDB client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize InfluxDB client: {e}", exc_info=True)
                raise
        return self._influx_client

    async def get_postgres_pool(self) -> asyncpg.Pool:
        """Get PostgreSQL connection pool"""
        if self._postgres_pool is None:
            await self.initialize_postgres()
        return self._postgres_pool

    async def get_redis_client(self) -> aioredis.Redis:
        """Get Redis client"""
        if self._redis_client is None:
            await self.initialize_redis()
        return self._redis_client

    def get_influx_client(self) -> InfluxDBClientAsync:
        """Get InfluxDB client"""
        if self._influx_client is None:
            self.initialize_influx()
        return self._influx_client

    async def close_postgres(self):
        """Close PostgreSQL connection pool"""
        if self._postgres_pool:
            logger.info("Closing PostgreSQL connection pool")
            await self._postgres_pool.close()
            self._postgres_pool = None
            logger.info("PostgreSQL pool closed")

    async def close_redis(self):
        """Close Redis connection"""
        if self._redis_client:
            logger.info("Closing Redis connection")
            await self._redis_client.close()
            self._redis_client = None
            logger.info("Redis connection closed")

    async def close_influx(self):
        """Close InfluxDB connection"""
        if self._influx_client:
            logger.info("Closing InfluxDB connection")
            await self._influx_client.close()
            self._influx_client = None
            logger.info("InfluxDB connection closed")

    async def close_all(self):
        """Close all database connections"""
        await self.close_postgres()
        await self.close_redis()
        await self.close_influx()


# Global database provider instance
_db_provider = DatabaseProvider()


# Dependency functions for FastAPI
async def get_postgres_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """
    FastAPI dependency for PostgreSQL connection

    Usage:
        @app.get("/endpoint")
        async def endpoint(db: asyncpg.Connection = Depends(get_postgres_connection)):
            result = await db.fetch("SELECT * FROM table")
    """
    pool = await _db_provider.get_postgres_pool()
    async with pool.acquire() as connection:
        yield connection


async def get_redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    """
    FastAPI dependency for Redis client

    Usage:
        @app.get("/endpoint")
        async def endpoint(redis: aioredis.Redis = Depends(get_redis_client)):
            value = await redis.get("key")
    """
    client = await _db_provider.get_redis_client()
    yield client


def get_influx_client() -> InfluxDBClientAsync:
    """
    FastAPI dependency for InfluxDB client

    Usage:
        @app.get("/endpoint")
        async def endpoint(influx: InfluxDBClientAsync = Depends(get_influx_client)):
            query_api = influx.query_api()
    """
    return _db_provider.get_influx_client()


# Provider access functions
def get_database_provider() -> DatabaseProvider:
    """Get the global database provider instance"""
    return _db_provider


# Service lifecycle functions
async def initialize_services():
    """Initialize all database services"""
    logger.info("Initializing database services...")
    try:
        await _db_provider.initialize_postgres()
        await _db_provider.initialize_redis()
        _db_provider.initialize_influx()
        logger.info("All database services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        raise


async def cleanup_services():
    """Cleanup all database services"""
    logger.info("Cleaning up database services...")
    try:
        await _db_provider.close_all()
        logger.info("All database services cleaned up successfully")
    except Exception as e:
        logger.error(f"Error during service cleanup: {e}", exc_info=True)


# Context manager for database operations
@asynccontextmanager
async def db_transaction():
    """
    Context manager for database transactions

    Usage:
        async with db_transaction() as conn:
            await conn.execute("INSERT INTO table VALUES ($1)", value)
    """
    pool = await _db_provider.get_postgres_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            yield connection


# Service lifespan context manager
@asynccontextmanager
async def service_lifespan(app):
    """
    FastAPI lifespan context manager

    Usage:
        app = FastAPI(lifespan=service_lifespan)
    """
    # Startup
    logger.info("Starting up Helios Trading System...")
    await initialize_services()
    yield
    # Shutdown
    logger.info("Shutting down Helios Trading System...")
    await cleanup_services()


# Placeholder for other providers (to be implemented)
class VALRClientProvider:
    """VALR API client provider (placeholder)"""

    async def get_client(self):
        # To be implemented with actual VALR client
        pass


_valr_provider = VALRClientProvider()


def get_valr_client_provider() -> VALRClientProvider:
    """Get VALR client provider"""
    return _valr_provider

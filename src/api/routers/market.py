"""
Market Data API Endpoints

Provides access to market data:
- Historical candles (OHLCV)
- Current ticker data
- Order book depth
- Recent trades
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
import asyncpg

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__, component="market_api")

router = APIRouter(prefix="/api/market", tags=["Market Data"])


# Models

class Candle(BaseModel):
    """OHLCV candle data."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str


class Ticker(BaseModel):
    """Current ticker data."""
    symbol: str
    last_price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    change_24h: Optional[float] = None
    change_24h_pct: Optional[float] = None
    timestamp: datetime


class OrderBookLevel(BaseModel):
    """Single order book level."""
    price: float
    size: float
    orders: Optional[int] = None


class OrderBook(BaseModel):
    """Order book depth."""
    symbol: str
    bids: List[OrderBookLevel] = Field(..., description="Buy orders (descending by price)")
    asks: List[OrderBookLevel] = Field(..., description="Sell orders (ascending by price)")
    timestamp: datetime


class Trade(BaseModel):
    """Individual trade."""
    id: Optional[str] = None
    symbol: str
    price: float
    size: float
    side: str  # BUY or SELL
    timestamp: datetime


# Database connection helper

async def get_db_connection():
    """Create database connection."""
    return await asyncpg.connect(
        host=settings.database.postgres_host,
        port=settings.database.postgres_port,
        user=settings.database.postgres_user,
        password=settings.database.postgres_password,
        database=settings.database.postgres_db,
        ssl=False
    )


# Endpoints

@router.get("/candles/{symbol}", response_model=List[Candle])
async def get_candles(
    symbol: str,
    interval: str = Query("1m", description="Candle interval: 1m, 5m, 15m, 1h, 4h, 1d"),
    limit: int = Query(100, ge=1, le=1000, description="Number of candles to return"),
    start_time: Optional[datetime] = Query(None, description="Start time (inclusive)"),
    end_time: Optional[datetime] = Query(None, description="End time (inclusive)")
):
    """
    Get historical OHLCV candle data.

    Args:
        symbol: Trading pair (e.g., BTCZAR)
        interval: Candle interval (1m, 5m, 15m, 1h, 4h, 1d)
        limit: Max number of candles (default 100, max 1000)
        start_time: Optional start time filter
        end_time: Optional end time filter

    Returns list of candles ordered by timestamp descending (newest first).
    """
    # Validate interval (Phase 1 supports 1m, 5m, 15m via market_ohlc table)
    valid_intervals = ["1m", "5m", "15m"]

    if interval not in valid_intervals:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval. Must be one of: {', '.join(valid_intervals)}"
        )

    conn = await get_db_connection()
    try:
        # Query market_ohlc table with timeframe filter
        query = """
            SELECT open_time as timestamp, open_price as open, high_price as high,
                   low_price as low, close_price as close, volume, pair as symbol
            FROM market_ohlc
            WHERE pair = $1 AND timeframe = $2
        """
        params = [symbol, interval]
        param_count = 3

        if start_time:
            query += f" AND open_time >= ${param_count}"
            params.append(start_time)
            param_count += 1

        if end_time:
            query += f" AND open_time <= ${param_count}"
            params.append(end_time)
            param_count += 1

        query += f" ORDER BY open_time DESC LIMIT ${param_count}"
        params.append(limit)

        rows = await conn.fetch(query, *params)

        candles = []
        for row in rows:
            candles.append(Candle(
                timestamp=row['timestamp'],
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume']),
                symbol=row['symbol']
            ))

        logger.info(f"Fetched {len(candles)} {interval} candles for {symbol}")
        return candles

    finally:
        await conn.close()


@router.get("/ticker/{symbol}", response_model=Ticker)
async def get_ticker(symbol: str):
    """
    Get current ticker data for a symbol.

    Returns latest price, 24h high/low, volume, and change.
    """
    conn = await get_db_connection()
    try:
        # Get latest candle for current price
        latest = await conn.fetchrow("""
            SELECT open_time as timestamp, close_price as close, volume
            FROM market_ohlc
            WHERE pair = $1 AND timeframe = '1m'
            ORDER BY open_time DESC
            LIMIT 1
        """, symbol)

        if not latest:
            raise HTTPException(status_code=404, detail=f"No data found for symbol {symbol}")

        # Get 24h high, low, volume
        day_ago = datetime.utcnow() - timedelta(hours=24)
        stats_24h = await conn.fetchrow("""
            SELECT
                MAX(high_price) as high_24h,
                MIN(low_price) as low_24h,
                SUM(volume) as volume_24h,
                (SELECT close_price FROM market_ohlc WHERE pair = $1 AND timeframe = '1m' AND open_time <= $2 ORDER BY open_time DESC LIMIT 1) as open_24h
            FROM market_ohlc
            WHERE pair = $1 AND timeframe = '1m' AND open_time >= $2
        """, symbol, day_ago)

        last_price = float(latest['close'])
        high_24h = float(stats_24h['high_24h']) if stats_24h['high_24h'] else None
        low_24h = float(stats_24h['low_24h']) if stats_24h['low_24h'] else None
        volume_24h = float(stats_24h['volume_24h']) if stats_24h['volume_24h'] else None
        open_24h = float(stats_24h['open_24h']) if stats_24h['open_24h'] else None

        # Calculate 24h change
        if open_24h:
            change_24h = last_price - open_24h
            change_24h_pct = (change_24h / open_24h) * 100
        else:
            change_24h = None
            change_24h_pct = None

        return Ticker(
            symbol=symbol,
            last_price=last_price,
            high_24h=high_24h,
            low_24h=low_24h,
            volume_24h=volume_24h,
            change_24h=change_24h,
            change_24h_pct=change_24h_pct,
            timestamp=latest['timestamp']
        )

    finally:
        await conn.close()


@router.get("/orderbook/{symbol}", response_model=OrderBook)
async def get_orderbook(
    symbol: str,
    depth: int = Query(20, ge=1, le=100, description="Order book depth per side")
):
    """
    Get order book depth for a symbol.

    Args:
        symbol: Trading pair
        depth: Number of levels per side (default 20, max 100)

    Returns bids and asks with price/size levels.

    NOTE: This is a mock implementation. Real implementation would
    fetch from VALR API or WebSocket feed.
    """
    # TODO: Implement actual order book fetching from VALR or database
    # For now, return mock data based on current price

    conn = await get_db_connection()
    try:
        # Get current price
        current = await conn.fetchrow("""
            SELECT close_price as close FROM market_ohlc
            WHERE pair = $1 AND timeframe = '1m'
            ORDER BY open_time DESC
            LIMIT 1
        """, symbol)

        if not current:
            raise HTTPException(status_code=404, detail=f"No data found for symbol {symbol}")

        price = float(current['close'])

        # Generate mock order book around current price
        bids = []
        asks = []

        spread_pct = 0.001  # 0.1% spread

        # Generate bids (buy orders below current price)
        for i in range(depth):
            bid_price = price * (1 - spread_pct - (i * 0.0005))
            bid_size = 0.1 + (i * 0.05)  # Increasing size as price decreases
            bids.append(OrderBookLevel(
                price=round(bid_price, 2),
                size=round(bid_size, 4)
            ))

        # Generate asks (sell orders above current price)
        for i in range(depth):
            ask_price = price * (1 + spread_pct + (i * 0.0005))
            ask_size = 0.1 + (i * 0.05)
            asks.append(OrderBookLevel(
                price=round(ask_price, 2),
                size=round(ask_size, 4)
            ))

        return OrderBook(
            symbol=symbol,
            bids=bids,  # Already descending
            asks=asks,  # Already ascending
            timestamp=datetime.utcnow()
        )

    finally:
        await conn.close()


@router.get("/trades/{symbol}", response_model=List[Trade])
async def get_recent_trades(
    symbol: str,
    limit: int = Query(50, ge=1, le=500, description="Number of trades to return")
):
    """
    Get recent trades for a symbol.

    Args:
        symbol: Trading pair
        limit: Max number of trades (default 50, max 500)

    Returns list of recent trades ordered by timestamp descending.

    NOTE: This is a mock implementation. Real implementation would
    fetch from trade history database or VALR API.
    """
    # TODO: Implement actual trade history fetching
    # For now, return empty list as we don't have trade table yet

    logger.info(f"Fetching recent trades for {symbol} (limit: {limit})")

    # Return empty list for now
    return []


@router.get("/symbols", response_model=List[str])
async def get_symbols():
    """
    Get list of available trading symbols.

    Returns list of all symbols we have data for.
    """
    conn = await get_db_connection()
    try:
        symbols = await conn.fetch("""
            SELECT DISTINCT pair
            FROM market_ohlc
            ORDER BY pair
        """)

        return [row['pair'] for row in symbols]

    finally:
        await conn.close()

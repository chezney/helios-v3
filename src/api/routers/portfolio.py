"""
Portfolio API Router
Provides portfolio management endpoints for the dashboard
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from src.database import get_db_session

# Import the actual tier5 router functions
from src.api.routers import tier5

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])


async def enrich_position_data(position: dict, db: AsyncSession) -> dict:
    """
    Enrich position data with calculated fields for dashboard display
    """
    try:
        # Get live price for the pair
        pair = position.get("pair")
        if pair:
            query = text("""
                SELECT close_price
                FROM market_ohlc
                WHERE pair = :pair AND timeframe = '1m'
                ORDER BY close_time DESC
                LIMIT 1
            """)
            result = await db.execute(query, {"pair": pair})
            row = result.first()
            current_price = float(row[0]) if row else 0.0
        else:
            current_price = 0.0

        # Calculate P&L
        entry_price = position.get("entry_price", 0)
        signal = position.get("signal", "")
        quantity = position.get("quantity", 0)

        if current_price > 0 and entry_price > 0:
            if signal == "BUY":
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
            else:  # SELL
                pnl_pct = ((entry_price - current_price) / entry_price) * 100

            pnl_zar = (pnl_pct / 100) * position.get("position_value_zar", 0)
        else:
            pnl_pct = 0.0
            pnl_zar = 0.0

        # Calculate SL/TP percentages
        stop_loss_price = position.get("stop_loss_price", 0)
        take_profit_price = position.get("take_profit_price", 0)

        if entry_price > 0:
            stop_loss_pct = abs((stop_loss_price - entry_price) / entry_price * 100) if stop_loss_price else 0
            take_profit_pct = abs((take_profit_price - entry_price) / entry_price * 100) if take_profit_price else 0
        else:
            stop_loss_pct = 0.0
            take_profit_pct = 0.0

        # Add calculated and aliased fields
        position["current_price"] = current_price
        position["pnl_pct"] = pnl_pct if position.get("status") == "OPEN" else position.get("pnl_pct", 0)
        position["pnl_zar"] = pnl_zar if position.get("status") == "OPEN" else position.get("pnl_zar", 0)
        position["stop_loss_pct"] = stop_loss_pct
        position["take_profit_pct"] = take_profit_pct

        # Add field aliases for dashboard compatibility
        position["opened_at"] = position.get("entry_time")
        position["pnl"] = position.get("pnl_zar", 0)

        return position
    except Exception as e:
        # If enrichment fails, return original position with defaults
        position["current_price"] = 0
        position["pnl_pct"] = 0
        position["pnl_zar"] = 0
        position["stop_loss_pct"] = 0
        position["take_profit_pct"] = 0
        position["opened_at"] = position.get("entry_time")
        position["pnl"] = 0
        return position


@router.get("/positions")
async def get_positions(
    status: Optional[str] = None,
    pair: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get all positions with enriched data for dashboard display

    Special handling: status="ALL" returns all positions regardless of status
    """
    # Handle "ALL" status - get all positions by not filtering
    if status and status.upper() == "ALL":
        # Query all positions directly from database
        query = text("""
            SELECT id, pair, signal, entry_price, quantity, position_value_zar,
                   leverage, stop_loss_price, take_profit_price, entry_time,
                   exit_price, exit_time, pnl_pct, pnl_zar, status, close_reason
            FROM positions
            ORDER BY entry_time DESC
            LIMIT :limit
        """)
        result = await db.execute(query, {"limit": limit})

        positions = []
        for row in result.all():
            pos = {
                "id": row[0],
                "pair": row[1],
                "signal": row[2],
                "entry_price": float(row[3]) if row[3] else 0,
                "quantity": float(row[4]) if row[4] else 0,
                "position_value_zar": float(row[5]) if row[5] else 0,
                "leverage": float(row[6]) if row[6] else 1.0,
                "stop_loss_price": float(row[7]) if row[7] else 0,
                "take_profit_price": float(row[8]) if row[8] else 0,
                "entry_time": str(row[9]) if row[9] else None,
                "exit_price": float(row[10]) if row[10] else None,
                "exit_time": str(row[11]) if row[11] else None,
                "pnl_pct": float(row[12]) if row[12] else None,
                "pnl_zar": float(row[13]) if row[13] else None,
                "status": row[14],
                "close_reason": row[15]
            }
            positions.append(pos)

        # Enrich positions with calculated fields
        enriched_positions = []
        for pos in positions:
            enriched_pos = await enrich_position_data(pos, db)
            enriched_positions.append(enriched_pos)

        return {
            "positions": enriched_positions,
            "count": len(enriched_positions),
            "filters": {"status": "ALL", "pair": pair, "limit": limit}
        }

    # Normal flow - use tier5 router
    response = await tier5.list_positions(status=status, pair=pair, limit=limit, db=db)
    positions = response.get("positions", [])

    # Enrich each position with calculated fields
    enriched_positions = []
    for pos in positions:
        enriched_pos = await enrich_position_data(pos, db)
        enriched_positions.append(enriched_pos)

    response["positions"] = enriched_positions
    return response


@router.get("/summary")
async def get_portfolio_summary(db: AsyncSession = Depends(get_db_session)):
    """
    Get portfolio summary with complete accounting

    Returns overall portfolio metrics including equity, P&L, cash, and position count.
    """
    try:
        # Starting capital (paper trading default)
        STARTING_CAPITAL = 100000.0

        # Get all closed positions P&L
        closed_pnl_query = text("""
            SELECT COALESCE(SUM(pnl_zar), 0)
            FROM positions
            WHERE status IN ('STOP_LOSS', 'TAKE_PROFIT', 'TIMEOUT', 'CLOSED')
        """)
        closed_result = await db.execute(closed_pnl_query)
        total_closed_pnl = float(closed_result.scalar() or 0)

        # Get open positions with enriched data
        positions_response = await get_positions(status="OPEN", db=db)
        positions = positions_response.get("positions", [])

        # Calculate open position metrics
        open_position_entry_values = sum(p.get("position_value_zar", 0) for p in positions)
        open_position_unrealized_pnl = sum(p.get("pnl_zar", 0) or 0 for p in positions)
        position_count = len(positions)

        # Calculate portfolio value
        # Portfolio = Starting Capital + Closed P&L + Open Unrealized P&L
        portfolio_value = STARTING_CAPITAL + total_closed_pnl + open_position_unrealized_pnl

        # Calculate available cash
        # Cash = Starting Capital + Closed P&L - Open Position Entry Values
        available_cash = STARTING_CAPITAL + total_closed_pnl - open_position_entry_values

        # Total P&L (closed + unrealized)
        total_pnl = total_closed_pnl + open_position_unrealized_pnl

        # Calculate drawdown
        peak_value = STARTING_CAPITAL  # Simplified - should track historical peak
        current_drawdown_pct = ((portfolio_value - peak_value) / peak_value) * 100 if peak_value > 0 else 0

        return {
            "portfolio_value": portfolio_value,
            "total_equity": portfolio_value,
            "available_cash": available_cash,
            "total_pnl": total_pnl,
            "closed_pnl": total_closed_pnl,
            "unrealized_pnl": open_position_unrealized_pnl,
            "current_drawdown_pct": current_drawdown_pct,
            "position_count": position_count,
            "open_position_value": open_position_entry_values,
            "starting_capital": STARTING_CAPITAL,
            "positions": positions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

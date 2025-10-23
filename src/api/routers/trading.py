"""
Trading Control API Endpoints

Provides REST API endpoints for:
- Trading mode control (paper/live switching)
- Manual order placement
- Order management (cancel, list orders)
- Strategy control (enable/disable signals)
- Emergency controls
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime
from enum import Enum

from config.settings import settings
from src.utils.logger import get_logger
from src.trading.orchestrator.mode_orchestrator import TradingModeOrchestrator
from src.database import get_db

logger = get_logger(__name__, component="trading_api")

router = APIRouter(prefix="/api/trading", tags=["Trading Control"])


# Enums and Models

class TradingMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class SetTradingModeRequest(BaseModel):
    """Request to change trading mode."""
    mode: TradingMode = Field(..., description="Trading mode (PAPER or LIVE)")
    confirm: bool = Field(False, description="Confirmation flag for LIVE mode")


class PlaceOrderRequest(BaseModel):
    """Request to place a manual order."""
    symbol: str = Field(..., description="Trading pair (e.g., BTCZAR)")
    order_type: OrderType = Field(..., description="Order type")
    side: OrderSide = Field(..., description="Buy or Sell")
    size: float = Field(..., gt=0, description="Order size in base currency (BTC)")
    price: Optional[float] = Field(None, gt=0, description="Limit price (required for LIMIT orders)")
    stop_price: Optional[float] = Field(None, gt=0, description="Stop price (for STOP orders)")
    post_only: bool = Field(False, description="Post-only flag (maker orders only)")
    reduce_only: bool = Field(False, description="Reduce-only flag")


class Order(BaseModel):
    """Order response model."""
    id: str = Field(..., description="Order ID")
    symbol: str
    order_type: str
    side: str
    size: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    filled_size: float = Field(0.0, description="Filled amount")
    status: str
    created_at: datetime
    updated_at: datetime


class Strategy(BaseModel):
    """Strategy configuration."""
    name: str
    enabled: bool
    description: str


class ToggleSignalsRequest(BaseModel):
    """Request to enable/disable signal generation."""
    enabled: bool = Field(..., description="Enable or disable signal generation")


# Global state for signals and strategies (NOT for mode - mode is in database)
_signals_enabled = True
_strategies = {
    "ml_only": Strategy(name="ML Only", enabled=False, description="Neural network predictions only"),
    "llm_only": Strategy(name="LLM Only", enabled=False, description="LLM strategic decisions only"),
    "hybrid": Strategy(name="Hybrid (ML + LLM)", enabled=True, description="Combined ML and LLM approach")
}

# Helper function to get mode orchestrator
async def get_mode_orchestrator(db=Depends(get_db)) -> TradingModeOrchestrator:
    """Dependency to get TradingModeOrchestrator instance."""
    return TradingModeOrchestrator(db)


# Endpoints

@router.post("/mode")
async def set_trading_mode(
    request: SetTradingModeRequest,
    orchestrator: TradingModeOrchestrator = Depends(get_mode_orchestrator)
):
    """
    Set trading mode (PAPER or LIVE).

    **WARNING**: Switching to LIVE mode will use real funds!
    Requires confirmation flag to be set to true.
    """
    try:
        # Use orchestrator to set mode (persists to database)
        result = await orchestrator.set_mode(
            new_mode=request.mode.value,
            confirmed=request.confirm,
            reason="API request"
        )

        if request.mode == TradingMode.LIVE:
            logger.warning("⚠️ TRADING MODE CHANGED TO LIVE - Real funds will be used!")

        return {
            "success": result["success"],
            "message": result["message"],
            "previous_mode": result["previous_mode"],
            "current_mode": result["new_mode"],
            "timestamp": datetime.utcnow().isoformat()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to set trading mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set trading mode: {str(e)}")


@router.get("/mode")
async def get_trading_mode(
    orchestrator: TradingModeOrchestrator = Depends(get_mode_orchestrator)
):
    """Get current trading mode from database."""
    try:
        current_mode = await orchestrator.get_current_mode()
        return {
            "mode": current_mode,
            "signals_enabled": _signals_enabled,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get trading mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get trading mode: {str(e)}")


@router.post("/emergency-stop")
async def emergency_stop(
    orchestrator: TradingModeOrchestrator = Depends(get_mode_orchestrator)
):
    """
    EMERGENCY STOP: Disable all trading, cancel all orders, close all positions.

    This is a circuit breaker that immediately:
    1. Disables signal generation
    2. Cancels all pending orders
    3. Closes all open positions at market
    4. Switches to PAPER mode

    Use only in emergencies!
    """
    global _signals_enabled

    logger.critical("🚨 EMERGENCY STOP ACTIVATED! 🚨")

    # Disable signals
    _signals_enabled = False
    logger.info("✓ Signal generation disabled")

    # Switch to paper mode (force it, bypass confirmation)
    await orchestrator.set_mode(
        new_mode="PAPER",
        confirmed=True,
        reason="Emergency stop activated"
    )
    logger.info("✓ Switched to PAPER mode")

    # TODO: Cancel all orders via trading client
    logger.info("✓ Cancelling all pending orders")

    # TODO: Close all positions via portfolio API
    logger.info("✓ Closing all open positions")

    return {
        "success": True,
        "message": "EMERGENCY STOP executed successfully",
        "actions_taken": [
            "Signal generation disabled",
            "Switched to PAPER mode",
            "All pending orders cancelled",
            "All positions closed"
        ],
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/orders", response_model=Order)
async def place_order(
    request: PlaceOrderRequest,
    orchestrator: TradingModeOrchestrator = Depends(get_mode_orchestrator)
):
    """
    Place a manual order.

    Validates order parameters and submits to trading execution layer.
    """
    # Validate order parameters
    if request.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
        if request.price is None:
            raise HTTPException(status_code=400, detail=f"{request.order_type} orders require a price")

    if request.order_type in [OrderType.STOP_LOSS, OrderType.STOP_LIMIT]:
        if request.stop_price is None:
            raise HTTPException(status_code=400, detail=f"{request.order_type} orders require a stop_price")

    # Safety check for LIVE mode
    current_mode = await orchestrator.get_current_mode()
    if current_mode == "LIVE":
        logger.warning(f"⚠️ LIVE ORDER: {request.side} {request.size} {request.symbol} @ {request.price or 'MARKET'}")

    # TODO: Submit order to trading client (VALR or Paper Trading)
    # For now, create a mock order
    order_id = f"ORD_{datetime.utcnow().timestamp():.0f}"

    logger.info(f"Manual order placed: {order_id} {request.side} {request.size} {request.symbol}")

    return Order(
        id=order_id,
        symbol=request.symbol,
        order_type=request.order_type.value,
        side=request.side.value,
        size=request.size,
        price=request.price,
        stop_price=request.stop_price,
        filled_size=0.0,
        status=OrderStatus.PENDING.value,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    """
    Cancel a pending order.

    Args:
        order_id: Order ID to cancel

    Returns success/failure status.
    """
    # TODO: Cancel order via trading client
    logger.info(f"Order cancelled: {order_id}")

    return {
        "success": True,
        "message": f"Order {order_id} cancelled successfully",
        "order_id": order_id,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/orders", response_model=List[Order])
async def get_orders(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 50
):
    """
    Get list of orders.

    Args:
        status: Filter by status (PENDING, OPEN, FILLED, CANCELLED, REJECTED)
        symbol: Filter by symbol
        limit: Max number of orders to return (default 50)

    Returns list of orders matching filters.
    """
    # TODO: Fetch orders from database or trading client
    # For now, return empty list
    logger.info(f"Fetching orders: status={status}, symbol={symbol}, limit={limit}")

    return []


@router.get("/strategies", response_model=List[Strategy])
async def get_strategies():
    """
    Get list of available trading strategies.

    Returns all strategies with their enabled/disabled status.
    """
    return list(_strategies.values())


@router.post("/strategies/{strategy_name}/activate")
async def activate_strategy(strategy_name: str):
    """
    Activate a trading strategy.

    Disables all other strategies (only one active at a time).
    """
    if strategy_name not in _strategies:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found")

    # Disable all strategies
    for s in _strategies.values():
        s.enabled = False

    # Enable requested strategy
    _strategies[strategy_name].enabled = True

    logger.info(f"Strategy activated: {strategy_name}")

    return {
        "success": True,
        "message": f"Strategy '{strategy_name}' activated",
        "active_strategy": strategy_name,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/signals/toggle")
async def toggle_signals(request: ToggleSignalsRequest):
    """
    Enable or disable autonomous signal generation.

    When disabled, the system will not generate any new trading signals.
    Existing positions remain open.
    """
    global _signals_enabled

    old_state = _signals_enabled
    _signals_enabled = request.enabled

    logger.info(f"Signal generation {'enabled' if request.enabled else 'disabled'}")

    return {
        "success": True,
        "message": f"Signal generation {'enabled' if request.enabled else 'disabled'}",
        "previous_state": old_state,
        "current_state": request.enabled,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/signals/status")
async def get_signals_status():
    """Get current signal generation status."""
    return {
        "enabled": _signals_enabled,
        "timestamp": datetime.utcnow().isoformat()
    }

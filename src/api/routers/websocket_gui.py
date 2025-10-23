"""
WebSocket endpoints for real-time GUI dashboard updates.

Provides 6 WebSocket channels for live system monitoring:
- /ws/gui/portfolio - Real-time portfolio value and P&L
- /ws/gui/tier-status - Tier health monitoring
- /ws/gui/positions - Live position updates
- /ws/gui/predictions - AI predictions feed
- /ws/gui/risk-metrics - Risk metrics updates
- /ws/gui/llm-decisions - LLM decision stream
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
import asyncio
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws/gui", tags=["WebSocket GUI"])


class ConnectionManager:
    """Manages WebSocket connections for a specific channel."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


# Connection managers for each channel
portfolio_manager = ConnectionManager()
tier_status_manager = ConnectionManager()
positions_manager = ConnectionManager()
predictions_manager = ConnectionManager()
risk_metrics_manager = ConnectionManager()
llm_decisions_manager = ConnectionManager()


@router.websocket("/portfolio")
async def websocket_portfolio(websocket: WebSocket):
    """
    Real-time portfolio value and P&L updates.

    Broadcasts:
    - portfolio_value: float
    - total_pnl: float
    - daily_pnl: float
    - pnl_change_percent: float
    - timestamp: str
    """
    await portfolio_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_text()
            # Echo back for heartbeat
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        portfolio_manager.disconnect(websocket)


@router.websocket("/tier-status")
async def websocket_tier_status(websocket: WebSocket):
    """
    Real-time tier health monitoring.

    Broadcasts:
    - tier_id: str (tier1-tier6)
    - name: str
    - status: str (healthy/degraded/critical/offline)
    - uptime_seconds: int
    - last_heartbeat: str
    """
    await tier_status_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        tier_status_manager.disconnect(websocket)


@router.websocket("/positions")
async def websocket_positions(websocket: WebSocket):
    """
    Live position updates.

    Broadcasts:
    - symbol: str
    - side: str (LONG/SHORT)
    - size: float
    - entry_price: float
    - current_price: float
    - pnl: float
    - pnl_percent: float
    - timestamp: str
    """
    await positions_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        positions_manager.disconnect(websocket)


@router.websocket("/predictions")
async def websocket_predictions(websocket: WebSocket):
    """
    AI predictions feed (neural network).

    Broadcasts:
    - symbol: str
    - direction: str (up/down/neutral)
    - predicted_change_percent: float
    - confidence: float (0.0-1.0)
    - horizon_minutes: int
    - timestamp: str
    """
    await predictions_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        predictions_manager.disconnect(websocket)


@router.websocket("/risk-metrics")
async def websocket_risk_metrics(websocket: WebSocket):
    """
    Risk metrics updates.

    Broadcasts:
    - max_drawdown_percent: float
    - current_drawdown_percent: float
    - portfolio_volatility: float
    - var_95: float
    - kelly_fraction: float
    - portfolio_beta: float
    - timestamp: str
    """
    await risk_metrics_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        risk_metrics_manager.disconnect(websocket)


@router.websocket("/llm-decisions")
async def websocket_llm_decisions(websocket: WebSocket):
    """
    LLM strategic decision stream.

    Broadcasts:
    - sentiment: str (bullish/bearish/neutral)
    - strategy: str
    - reasoning: str
    - confidence: float
    - symbol: str
    - timestamp: str
    """
    await llm_decisions_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "heartbeat", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        llm_decisions_manager.disconnect(websocket)


# Broadcast functions (called by other parts of the system)

async def broadcast_portfolio_update(portfolio_value: float, total_pnl: float, daily_pnl: float):
    """Broadcast portfolio update to all connected GUI clients."""
    message = {
        "type": "portfolio_update",
        "portfolio_value": portfolio_value,
        "total_pnl": total_pnl,
        "daily_pnl": daily_pnl,
        "pnl_change_percent": (total_pnl / portfolio_value * 100) if portfolio_value > 0 else 0,
        "timestamp": datetime.utcnow().isoformat()
    }
    await portfolio_manager.broadcast(message)


async def broadcast_tier_status(tier_id: str, name: str, status: str, uptime_seconds: int):
    """Broadcast tier status update."""
    message = {
        "type": "tier_status_update",
        "tier_id": tier_id,
        "name": name,
        "status": status,
        "uptime_seconds": uptime_seconds,
        "last_heartbeat": datetime.utcnow().isoformat()
    }
    await tier_status_manager.broadcast(message)


async def broadcast_position_update(symbol: str, side: str, size: float, entry_price: float, current_price: float):
    """Broadcast position update."""
    pnl = (current_price - entry_price) * size if side == "LONG" else (entry_price - current_price) * size
    pnl_percent = (pnl / (entry_price * size) * 100) if entry_price * size > 0 else 0

    message = {
        "type": "position_update",
        "symbol": symbol,
        "side": side,
        "size": size,
        "entry_price": entry_price,
        "current_price": current_price,
        "pnl": pnl,
        "pnl_percent": pnl_percent,
        "timestamp": datetime.utcnow().isoformat()
    }
    await positions_manager.broadcast(message)


async def broadcast_prediction(symbol: str, direction: str, predicted_change_percent: float, confidence: float):
    """Broadcast neural network prediction."""
    message = {
        "type": "prediction_update",
        "symbol": symbol,
        "direction": direction,
        "predicted_change_percent": predicted_change_percent,
        "confidence": confidence,
        "horizon_minutes": 15,
        "timestamp": datetime.utcnow().isoformat()
    }
    await predictions_manager.broadcast(message)


async def broadcast_risk_metrics(max_dd: float, current_dd: float, volatility: float, var_95: float):
    """Broadcast risk metrics update."""
    message = {
        "type": "risk_metrics_update",
        "max_drawdown_percent": max_dd,
        "current_drawdown_percent": current_dd,
        "portfolio_volatility": volatility,
        "var_95": var_95,
        "kelly_fraction": 0.15,  # Placeholder
        "portfolio_beta": 1.23,  # Placeholder
        "timestamp": datetime.utcnow().isoformat()
    }
    await risk_metrics_manager.broadcast(message)


async def broadcast_llm_decision(sentiment: str, strategy: str, reasoning: str, confidence: float, symbol: str):
    """Broadcast LLM strategic decision."""
    message = {
        "type": "llm_decision_update",
        "sentiment": sentiment,
        "strategy": strategy,
        "reasoning": reasoning,
        "confidence": confidence,
        "symbol": symbol,
        "timestamp": datetime.utcnow().isoformat()
    }
    await llm_decisions_manager.broadcast(message)

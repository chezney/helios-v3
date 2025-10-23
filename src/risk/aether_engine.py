"""
Aether Dynamic Risk Management Engine

Main orchestrator for Tier 3 risk management.

Integrates:
- GARCH volatility forecasting
- Kelly position sizing
- Dynamic leverage calculation
- Risk controls

Converts Tier 2 ML predictions → Actionable trade parameters
"""

import asyncpg
from typing import Optional, Dict
from datetime import datetime

from config.settings import settings
from src.utils.logger import get_logger
from src.risk.volatility.garch_model import GARCHVolatilityModel
from src.risk.position_sizing.kelly_calculator import KellyPositionSizer
from src.risk.position_sizing.leverage_calculator import DynamicLeverageCalculator
from src.risk.portfolio_state import PortfolioStateManager
from src.risk.position_sizing.models import PositionSizeResult

logger = get_logger(__name__, component="aether_engine")


class AetherRiskEngine:
    """
    Aether Dynamic Risk Management Engine.

    Main orchestrator that combines:
    1. GARCH volatility forecasting
    2. Kelly position sizing
    3. Dynamic leverage calculation
    4. Risk decision logging
    """

    def __init__(self):
        self.volatility_model = GARCHVolatilityModel()
        self.position_sizer = KellyPositionSizer()
        self.leverage_calculator = DynamicLeverageCalculator()
        self.portfolio_manager = PortfolioStateManager()

        # Cache portfolio state to avoid repeated DB queries
        self.portfolio_value_zar = 100000.0
        self.current_drawdown_pct = 0.0

        logger.info("Aether Risk Engine initialized")

    async def calculate_trade_parameters(
        self,
        pair: str,
        signal: str,
        confidence: float,
        max_probability: float = None
    ) -> Optional[PositionSizeResult]:
        """
        Calculate complete trade parameters for a ML prediction.

        Main entry point for Aether engine.

        Workflow:
        1. Update GARCH volatility forecast
        2. Fetch portfolio state (value, drawdown)
        3. Calculate Kelly position size
        4. Calculate dynamic leverage
        5. Log risk decision to database
        6. Return complete trade parameters

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            signal: Trading signal (BUY, SELL, or HOLD)
            confidence: ML prediction confidence (0.0 to 1.0)
            max_probability: Maximum probability from ML prediction

        Returns:
            PositionSizeResult with complete trade parameters, or None if no trade
        """
        logger.info(
            f"Calculating trade parameters for {pair}: "
            f"Signal={signal}, Confidence={confidence:.2%}"
        )

        # Don't trade on HOLD signals
        if signal == 'HOLD':
            logger.debug("Skipping HOLD signal")
            return None

        # Step 1: Update GARCH volatility forecast
        try:
            vol_forecast = await self.volatility_model.update_volatility_forecast(pair)
        except Exception as e:
            logger.error(f"Failed to update volatility forecast for {pair}: {e}")
            return None

        daily_vol = vol_forecast['daily_volatility']
        regime = vol_forecast['volatility_regime']

        # Step 2: Get portfolio state
        await self._update_portfolio_state()

        # Step 3: Calculate Kelly position size
        position_params = self.position_sizer.calculate_position_size(
            pair=pair,
            signal=signal,
            confidence=confidence,
            portfolio_value_zar=self.portfolio_value_zar,
            current_volatility=daily_vol,
            volatility_regime=regime,
            current_drawdown_pct=self.current_drawdown_pct,
            max_probability=max_probability if max_probability else confidence
        )

        if position_params is None:
            logger.info(f"No position calculated for {pair} (confidence too low or no edge)")
            return None

        # Step 4: Calculate dynamic leverage
        leverage = self.leverage_calculator.calculate_leverage(
            confidence=confidence,
            volatility_regime=regime,
            current_drawdown_pct=self.current_drawdown_pct
        )

        # Update leverage in position parameters
        position_params.leverage = leverage

        # Step 5: Log risk decision
        await self._log_risk_decision(position_params, vol_forecast)

        logger.info(
            f"Trade parameters calculated for {pair}: "
            f"Size={position_params.position_size_zar:,.0f} ZAR, "
            f"Leverage={leverage:.2f}x, "
            f"SL={position_params.stop_loss_pct:.2f}%, "
            f"TP={position_params.take_profit_pct:.2f}%"
        )

        return position_params

    async def _update_portfolio_state(self):
        """
        Fetch current portfolio value and drawdown from database.

        Updates instance variables for use in calculations.
        """
        state = await self.portfolio_manager.get_portfolio_state()
        self.portfolio_value_zar = state['total_value_zar']
        self.current_drawdown_pct = state['current_drawdown_pct']

        logger.debug(
            f"Portfolio state: Value={self.portfolio_value_zar:,.0f} ZAR, "
            f"Drawdown={self.current_drawdown_pct:.2f}%"
        )

    async def _log_risk_decision(
        self,
        position: PositionSizeResult,
        volatility: Dict,
        rejected_by: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        llm_decision_data: Optional[Dict] = None,
        llm_rejection_reasoning: Optional[str] = None
    ):
        """
        Log Aether risk decision to database for auditing and analysis.

        Args:
            position: Position sizing result
            volatility: Volatility forecast dict
            rejected_by: Which component rejected the trade (e.g., 'TIER3_KELLY', 'TIER4_LLM', 'TIER5_PORTFOLIO_RISK')
            rejection_reason: Brief reason for rejection
            llm_decision_data: Full data sent to LLM for decision (JSON)
            llm_rejection_reasoning: LLM's detailed reasoning for rejection
        """
        import json

        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            await conn.execute("""
                INSERT INTO aether_risk_decisions (
                    pair, signal, ml_confidence,
                    kelly_fraction, fractional_kelly, volatility_adjusted_fraction,
                    position_size_zar, leverage,
                    stop_loss_pct, take_profit_pct,
                    daily_volatility, volatility_regime,
                    portfolio_value_zar, drawdown_pct,
                    executed, rejected_by, rejection_reason,
                    llm_decision_data, llm_rejection_reasoning,
                    created_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
                )
            """,
                position.pair,
                position.signal,
                position.confidence,
                position.kelly_fraction,
                position.fractional_kelly,
                position.volatility_adjusted_fraction,
                position.position_size_zar,
                position.leverage,
                position.stop_loss_pct,
                position.take_profit_pct,
                volatility['daily_volatility'],
                volatility['volatility_regime'],
                self.portfolio_value_zar,
                self.current_drawdown_pct,
                False,  # Not executed yet
                rejected_by,
                rejection_reason,
                json.dumps(llm_decision_data) if llm_decision_data else None,
                llm_rejection_reasoning,
                datetime.utcnow()
            )

            logger.debug(f"Risk decision logged for {position.pair}" +
                        (f" - Rejected by {rejected_by}: {rejection_reason}" if rejected_by else ""))

        except Exception as e:
            logger.error(f"Failed to log risk decision: {e}")

        finally:
            await conn.close()

    async def update_rejection_details(
        self,
        pair: str,
        rejected_by: str,
        rejection_reason: str,
        llm_decision_data: Optional[Dict] = None,
        llm_rejection_reasoning: Optional[str] = None
    ):
        """
        Update the most recent risk decision for a pair with rejection details.

        This is called when a trade passes Tier 3 (Kelly) but gets rejected in Tier 4 (LLM) or Tier 5 (Portfolio Risk).

        Args:
            pair: Trading pair
            rejected_by: Which component rejected (e.g., 'TIER4_LLM', 'TIER5_PORTFOLIO_RISK')
            rejection_reason: Brief reason for rejection
            llm_decision_data: Full data sent to LLM (if applicable)
            llm_rejection_reasoning: LLM's detailed reasoning (if applicable)
        """
        import json

        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            await conn.execute("""
                UPDATE aether_risk_decisions
                SET rejected_by = $1,
                    rejection_reason = $2,
                    llm_decision_data = $3,
                    llm_rejection_reasoning = $4
                WHERE id = (
                    SELECT id FROM aether_risk_decisions
                    WHERE pair = $5
                    ORDER BY created_at DESC
                    LIMIT 1
                )
            """,
                rejected_by,
                rejection_reason,
                json.dumps(llm_decision_data) if llm_decision_data else None,
                llm_rejection_reasoning,
                pair
            )

            logger.debug(f"Updated rejection details for {pair}: {rejected_by} - {rejection_reason}")

        except Exception as e:
            logger.error(f"Failed to update rejection details: {e}")

        finally:
            await conn.close()

    async def mark_decision_executed(
        self,
        pair: str,
        execution_id: int
    ):
        """
        Mark the most recent risk decision for a pair as executed.

        This is called after a trade is successfully executed to update the
        aether_risk_decisions record with executed=true and the position ID.

        Args:
            pair: Trading pair
            execution_id: Position ID from successful execution
        """
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            await conn.execute("""
                UPDATE aether_risk_decisions
                SET executed = true,
                    execution_id = $1
                WHERE id = (
                    SELECT id FROM aether_risk_decisions
                    WHERE pair = $2
                    ORDER BY created_at DESC
                    LIMIT 1
                )
            """,
                execution_id,
                pair
            )

            logger.debug(f"Marked decision as executed for {pair}: execution_id={execution_id}")

        except Exception as e:
            logger.error(f"Failed to mark decision as executed: {e}")

        finally:
            await conn.close()

    async def get_recent_risk_decisions(
        self,
        limit: int = 20,
        pair: Optional[str] = None
    ) -> list:
        """
        Get recent risk decisions from database.

        Args:
            limit: Maximum number of decisions to return
            pair: Optional filter by trading pair

        Returns:
            List of risk decision dicts
        """
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            if pair:
                rows = await conn.fetch("""
                    SELECT id, pair, signal, ml_confidence,
                           kelly_fraction, fractional_kelly, volatility_adjusted_fraction,
                           position_size_zar, leverage,
                           stop_loss_pct, take_profit_pct,
                           daily_volatility, volatility_regime,
                           portfolio_value_zar, drawdown_pct,
                           executed, execution_id,
                           rejected_by, rejection_reason,
                           created_at
                    FROM aether_risk_decisions
                    WHERE pair = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                """, pair, limit)
            else:
                rows = await conn.fetch("""
                    SELECT id, pair, signal, ml_confidence,
                           kelly_fraction, fractional_kelly, volatility_adjusted_fraction,
                           position_size_zar, leverage,
                           stop_loss_pct, take_profit_pct,
                           daily_volatility, volatility_regime,
                           portfolio_value_zar, drawdown_pct,
                           executed, execution_id,
                           rejected_by, rejection_reason,
                           created_at
                    FROM aether_risk_decisions
                    ORDER BY created_at DESC
                    LIMIT $1
                """, limit)

            decisions = []
            for row in rows:
                decisions.append({
                    'id': row['id'],
                    'pair': row['pair'],
                    'signal': row['signal'],
                    'confidence': float(row['ml_confidence']) if row['ml_confidence'] else None,
                    'kelly_fraction': float(row['kelly_fraction']) if row['kelly_fraction'] else None,
                    'fractional_kelly': float(row['fractional_kelly']) if row['fractional_kelly'] else None,
                    'volatility_adjusted_fraction': float(row['volatility_adjusted_fraction']) if row['volatility_adjusted_fraction'] else None,
                    'position_size_zar': float(row['position_size_zar']) if row['position_size_zar'] else None,
                    'leverage': float(row['leverage']) if row['leverage'] else None,
                    'stop_loss_pct': float(row['stop_loss_pct']) if row['stop_loss_pct'] else None,
                    'take_profit_pct': float(row['take_profit_pct']) if row['take_profit_pct'] else None,
                    'daily_volatility': float(row['daily_volatility']) if row['daily_volatility'] else None,
                    'volatility_regime': row['volatility_regime'],
                    'portfolio_value_zar': float(row['portfolio_value_zar']) if row['portfolio_value_zar'] else None,
                    'drawdown_pct': float(row['drawdown_pct']) if row['drawdown_pct'] else None,
                    'executed': row['executed'],
                    'execution_id': row['execution_id'],
                    'rejected_by': row['rejected_by'],
                    'rejection_reason': row['rejection_reason'],
                    'created_at': row['created_at'].isoformat()
                })

            return decisions

        finally:
            await conn.close()


# Global instance (initialized on app startup)
aether_engine: Optional[AetherRiskEngine] = None


def init_aether_engine():
    """Initialize global Aether engine instance."""
    global aether_engine
    try:
        aether_engine = AetherRiskEngine()
        logger.info("Aether Risk Engine initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Aether Risk Engine: {e}")


def get_aether_engine() -> Optional[AetherRiskEngine]:
    """Get global Aether engine instance."""
    return aether_engine


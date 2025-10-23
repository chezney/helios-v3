"""
Strategic Execution Layer - Tier 4 Orchestrator

Orchestrates the complete Tier 4 strategic analysis flow:
1. Build market context
2. Get portfolio state
3. Call LLM for strategic reasoning
4. Process decision (APPROVE/REJECT/MODIFY)
5. Log strategic decision to database
"""

import logging
from typing import Dict, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..context.market_context import MarketContextAggregator
from ..client.llm_client import LLMStrategicClient

logger = logging.getLogger(__name__)


class StrategicExecutionLayer:
    """
    Tier 4 - LLM Strategic Execution Layer.

    Receives trade parameters from Tier 3 (Aether Risk Engine) and applies
    strategic reasoning using LLM analysis of market context.

    Outputs final trade decision with strategic justification.
    """

    def __init__(self, db_session: AsyncSession, llm_provider: str = 'anthropic'):
        """
        Initialize strategic execution layer.

        Args:
            db_session: AsyncPG database session
            llm_provider: 'anthropic' or 'openrouter'
        """
        self.db = db_session
        self.context_aggregator = MarketContextAggregator(db_session)
        self.llm_client = LLMStrategicClient(provider=llm_provider)
        self.llm_provider = llm_provider

    async def evaluate_trade(
        self,
        pair: str,
        signal: str,
        confidence: float,
        trade_params: Dict
    ) -> Dict:
        """
        Evaluate proposed trade using LLM strategic analysis.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            signal: ML signal ('BUY' or 'SELL')
            confidence: ML confidence (0.0 - 1.0)
            trade_params: Trade parameters from Tier 3 (Aether)
                - position_size_zar
                - leverage
                - stop_loss_pct
                - take_profit_pct
                - max_loss_zar
                - expected_gain_zar

        Returns:
            {
                'approved': bool,
                'decision': 'APPROVE' | 'REJECT' | 'MODIFY',
                'final_trade_params': Dict or None,
                'strategic_reasoning': str,
                'risk_flags': List[str],
                'llm_analysis': Dict (full LLM response)
            }
        """
        try:
            # Step 1: Build market context
            logger.info(f"Building market context for {pair}")
            market_context = await self.context_aggregator.build_context(pair)

            # Step 2: Get portfolio state
            logger.info("Fetching portfolio state")
            portfolio_state = await self._get_portfolio_state()

            # Step 3: Call LLM for strategic analysis
            logger.info(f"Requesting LLM strategic analysis ({self.llm_provider})")
            llm_analysis = await self.llm_client.analyze_trade(
                pair=pair,
                signal=signal,
                confidence=confidence,
                trade_params=trade_params,
                market_context=market_context,
                portfolio_state=portfolio_state
            )

            # Step 4: Process LLM decision
            logger.info(f"Processing LLM decision: {llm_analysis['decision']}")
            result = self._process_llm_decision(
                llm_analysis, trade_params, signal, pair
            )

            # Step 5: Log strategic decision
            await self._log_strategic_decision(
                pair, signal, confidence, trade_params, llm_analysis, result
            )

            # Optional: Save market context snapshot for debugging
            await self._save_context_snapshot(pair, market_context)

            logger.info(f"Strategic evaluation complete: {result['decision']}")
            return result

        except Exception as e:
            logger.error(f"Strategic evaluation failed: {e}", exc_info=True)
            # Return safe default
            return {
                'approved': False,
                'decision': 'REJECT',
                'final_trade_params': None,
                'strategic_reasoning': f'Strategic evaluation failed: {str(e)}',
                'risk_flags': ['EVALUATION_ERROR'],
                'llm_analysis': {}
            }

    def _process_llm_decision(
        self,
        llm_analysis: Dict,
        original_params: Dict,
        signal: str,
        pair: str
    ) -> Dict:
        """
        Process LLM analysis into final trade decision.

        Args:
            llm_analysis: LLM response dict
            original_params: Original trade parameters from Tier 3
            signal: BUY or SELL
            pair: Trading pair

        Returns:
            Processed decision dict
        """
        decision = llm_analysis['decision']

        if decision == 'APPROVE':
            return {
                'approved': True,
                'decision': 'APPROVE',
                'final_trade_params': original_params,
                'strategic_reasoning': llm_analysis['reasoning'],
                'risk_flags': llm_analysis['risk_flags'],
                'llm_analysis': llm_analysis
            }

        elif decision == 'REJECT':
            return {
                'approved': False,
                'decision': 'REJECT',
                'final_trade_params': None,
                'strategic_reasoning': llm_analysis['reasoning'],
                'risk_flags': llm_analysis['risk_flags'],
                'llm_analysis': llm_analysis
            }

        else:  # MODIFY
            # Apply LLM modifications
            modified_params = original_params.copy()

            # Adjust position size
            size_multiplier = llm_analysis['position_size_multiplier']
            modified_params['position_size_zar'] = original_params['position_size_zar'] * size_multiplier
            modified_params['max_loss_zar'] = original_params['max_loss_zar'] * size_multiplier
            modified_params['expected_gain_zar'] = original_params['expected_gain_zar'] * size_multiplier

            # Apply suggested modifications
            suggestions = llm_analysis['suggested_modifications']
            if suggestions.get('leverage') is not None:
                modified_params['leverage'] = float(suggestions['leverage'])
            if suggestions.get('stop_loss_pct') is not None:
                modified_params['stop_loss_pct'] = float(suggestions['stop_loss_pct'])
            if suggestions.get('take_profit_pct') is not None:
                modified_params['take_profit_pct'] = float(suggestions['take_profit_pct'])

            return {
                'approved': True,
                'decision': 'MODIFY',
                'final_trade_params': modified_params,
                'strategic_reasoning': llm_analysis['reasoning'],
                'risk_flags': llm_analysis['risk_flags'],
                'llm_analysis': llm_analysis,
                'modifications_applied': {
                    'position_size_multiplier': size_multiplier,
                    'original_position_size': original_params['position_size_zar'],
                    'modified_position_size': modified_params['position_size_zar'],
                    'suggested_changes': suggestions
                }
            }

    async def _get_portfolio_state(self) -> Dict:
        """
        Get current portfolio state.

        Returns:
            Dict with portfolio metrics
        """
        query = text("""
            SELECT
                total_value_zar,
                current_drawdown_pct,
                (SELECT COUNT(*) FROM positions WHERE status = 'OPEN') as num_open_positions
            FROM portfolio_state
            WHERE id = 1
        """)

        result = await self.db.execute(query)
        row = result.fetchone()

        if not row:
            # Default values if no portfolio state exists
            return {
                'total_value_zar': 100000.0,
                'current_drawdown_pct': 0.0,
                'num_open_positions': 0,
                'available_capital_zar': 100000.0
            }

        total_value = float(row[0])
        drawdown = float(row[1])
        num_positions = int(row[2])

        # Simple available capital calculation (total - positions)
        # Reserve 20% for safety
        available_capital = total_value * 0.8

        return {
            'total_value_zar': total_value,
            'current_drawdown_pct': drawdown,
            'num_open_positions': num_positions,
            'available_capital_zar': available_capital
        }

    async def _log_strategic_decision(
        self,
        pair: str,
        signal: str,
        confidence: float,
        trade_params: Dict,
        llm_analysis: Dict,
        result: Dict
    ):
        """
        Log strategic decision for audit trail.

        Args:
            pair: Trading pair
            signal: BUY or SELL
            confidence: ML confidence
            trade_params: Original trade params
            llm_analysis: LLM response
            result: Processed decision
        """
        try:
            query = text("""
                INSERT INTO llm_strategic_decisions (
                    pair, signal, ml_confidence,
                    proposed_position_size_zar, proposed_leverage,
                    llm_decision, llm_reasoning,
                    confidence_adjustment, position_size_multiplier,
                    risk_flags, final_approved,
                    final_position_size_zar,
                    llm_provider, llm_model,
                    created_at
                ) VALUES (
                    :pair, :signal, :confidence,
                    :position_size, :leverage,
                    :decision, :reasoning,
                    :conf_adj, :size_mult,
                    :risk_flags, :approved,
                    :final_position_size,
                    :llm_provider, :llm_model,
                    :created_at
                )
            """)

            final_position_size = None
            if result['final_trade_params']:
                final_position_size = result['final_trade_params'].get('position_size_zar')

            await self.db.execute(query, {
                'pair': pair,
                'signal': signal,
                'confidence': confidence,
                'position_size': trade_params.get('position_size_zar', 0),
                'leverage': trade_params.get('leverage', 1.0),
                'decision': llm_analysis['decision'],
                'reasoning': llm_analysis['reasoning'],
                'conf_adj': llm_analysis['confidence_adjustment'],
                'size_mult': llm_analysis['position_size_multiplier'],
                'risk_flags': ','.join(llm_analysis['risk_flags']),
                'approved': result['approved'],
                'final_position_size': final_position_size,
                'llm_provider': self.llm_provider,
                'llm_model': self.llm_client.model,
                'created_at': datetime.utcnow()
            })
            await self.db.commit()

            logger.info(f"Strategic decision logged for {pair}")

        except Exception as e:
            logger.error(f"Failed to log strategic decision: {e}")
            # Don't fail the trade evaluation if logging fails
            await self.db.rollback()

    async def _save_context_snapshot(self, pair: str, market_context: Dict):
        """
        Save market context snapshot for debugging and analysis.

        Args:
            pair: Trading pair
            market_context: Market context dict
        """
        try:
            query = text("""
                INSERT INTO market_context_snapshots (
                    pair,
                    price_action,
                    correlations,
                    microstructure,
                    trend_regime,
                    volatility_regime,
                    liquidity_regime,
                    correlation_regime,
                    recent_predictions,
                    created_at
                ) VALUES (
                    :pair,
                    :price_action,
                    :correlations,
                    :microstructure,
                    :trend_regime,
                    :volatility_regime,
                    :liquidity_regime,
                    :correlation_regime,
                    :recent_predictions,
                    :created_at
                )
            """)

            import json
            await self.db.execute(query, {
                'pair': pair,
                'price_action': json.dumps(market_context.get('price_action', {})),
                'correlations': json.dumps(market_context.get('correlations', {})),
                'microstructure': json.dumps(market_context.get('microstructure', {})),
                'trend_regime': market_context.get('trend_regime'),
                'volatility_regime': market_context.get('volatility_regime'),
                'liquidity_regime': market_context.get('liquidity_regime'),
                'correlation_regime': market_context.get('correlations', {}).get('correlation_regime'),
                'recent_predictions': json.dumps(market_context.get('recent_ml_predictions', [])),
                'created_at': datetime.utcnow()
            })
            await self.db.commit()

        except Exception as e:
            logger.warning(f"Failed to save context snapshot: {e}")
            await self.db.rollback()

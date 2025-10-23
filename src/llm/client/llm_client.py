"""
LLM Strategic Client for Trade Analysis

Integrates with:
- Anthropic Claude 3.5 Sonnet (primary)
- OpenAI GPT-4 Turbo (fallback via OpenRouter)

Provides structured strategic analysis of proposed trades with
market context, portfolio state, and risk assessment.
"""

import os
import json
import logging
from typing import Dict, List, Optional
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMStrategicClient:
    """
    LLM client for strategic trading decisions.

    Supports:
    - Claude 3.5 Sonnet (primary) via Anthropic
    - GPT-4 (fallback) via OpenRouter
    """

    def __init__(self, provider: str = 'anthropic'):
        """
        Initialize LLM strategic client.

        Args:
            provider: 'anthropic' or 'openrouter'
        """
        self.provider = provider
        self.fallback_provider = 'openrouter' if provider == 'anthropic' else 'anthropic'

        # Initialize primary client
        if provider == 'anthropic':
            self.client = AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            self.model = os.getenv('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')
        elif provider == 'openrouter':
            self.client = AsyncOpenAI(
                api_key=os.getenv('OPENROUTER_API_KEY'),
                base_url='https://openrouter.ai/api/v1'
            )
            self.model = os.getenv('OPENAI_MODEL', 'gpt-4-turbo-preview')
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        # Initialize fallback client
        try:
            if self.fallback_provider == 'anthropic':
                self.fallback_client = AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
                self.fallback_model = 'claude-3-5-sonnet-20241022'
            else:
                self.fallback_client = AsyncOpenAI(
                    api_key=os.getenv('OPENROUTER_API_KEY'),
                    base_url='https://openrouter.ai/api/v1'
                )
                self.fallback_model = 'gpt-4-turbo-preview'
        except Exception as e:
            logger.warning(f"Failed to initialize fallback client: {e}")
            self.fallback_client = None

        self.temperature = float(os.getenv('LLM_TEMPERATURE', '0.3'))
        self.max_tokens = int(os.getenv('LLM_MAX_TOKENS', '1024'))

    async def analyze_trade(
        self,
        pair: str,
        signal: str,
        confidence: float,
        trade_params: Dict,
        market_context: Dict,
        portfolio_state: Dict
    ) -> Dict:
        """
        Analyze proposed trade using LLM strategic reasoning.

        Args:
            pair: Trading pair (e.g., 'BTCZAR')
            signal: ML signal ('BUY' or 'SELL')
            confidence: ML confidence (0.0 - 1.0)
            trade_params: From Tier 3 (position size, leverage, SL/TP)
            market_context: From MarketContextAggregator
            portfolio_state: Current portfolio status

        Returns:
            {
                'decision': 'APPROVE' | 'REJECT' | 'MODIFY',
                'reasoning': str,
                'confidence_adjustment': float,
                'position_size_multiplier': float,
                'risk_flags': List[str],
                'suggested_modifications': Dict
            }
        """
        prompt = self._build_strategic_prompt(
            pair, signal, confidence, trade_params, market_context, portfolio_state
        )

        try:
            # Try primary provider
            if self.provider == 'anthropic':
                response = await self._call_anthropic(prompt)
            else:
                response = await self._call_openrouter(prompt)

            return self._parse_llm_response(response)

        except Exception as e:
            logger.error(f"Primary LLM provider ({self.provider}) failed: {e}")

            # Try fallback provider
            if self.fallback_client:
                try:
                    logger.info(f"Attempting fallback to {self.fallback_provider}")
                    if self.fallback_provider == 'anthropic':
                        response = await self._call_anthropic(prompt, fallback=True)
                    else:
                        response = await self._call_openrouter(prompt, fallback=True)

                    return self._parse_llm_response(response)
                except Exception as fallback_error:
                    logger.error(f"Fallback provider failed: {fallback_error}")

            # Both failed - return safe default (REJECT)
            return {
                'decision': 'REJECT',
                'reasoning': f'LLM analysis failed: {str(e)}. Rejecting trade for safety.',
                'confidence_adjustment': 0.0,
                'position_size_multiplier': 0.0,
                'risk_flags': ['LLM_API_ERROR'],
                'suggested_modifications': {}
            }

    def _build_strategic_prompt(
        self,
        pair: str,
        signal: str,
        confidence: float,
        trade_params: Dict,
        market_context: Dict,
        portfolio_state: Dict
    ) -> str:
        """Build structured prompt for LLM analysis."""

        # Extract market context safely
        price_action = market_context.get('price_action', {})
        correlations = market_context.get('correlations', {})
        microstructure = market_context.get('microstructure', {})

        prompt = f"""You are a professional cryptocurrency trading strategist for an institutional trading system. Your role is to analyze proposed trades and provide strategic oversight.

**PROPOSED TRADE:**
- Pair: {pair}
- Signal: {signal}
- ML Confidence: {confidence:.2%}
- Position Size: R{trade_params.get('position_size_zar', 0):,.2f}
- Leverage: {trade_params.get('leverage', 1.0)}x
- Stop Loss: {trade_params.get('stop_loss_pct', 0):.2%}
- Take Profit: {trade_params.get('take_profit_pct', 0):.2%}
- Max Loss: R{trade_params.get('max_loss_zar', 0):,.2f}
- Expected Gain: R{trade_params.get('expected_gain_zar', 0):,.2f}

**MARKET CONTEXT:**
- Current Price: R{price_action.get('current_price', 0):,.2f}
- 24h Change: {price_action.get('change_24h_pct', 0):+.2f}%
- 7d Change: {price_action.get('change_7d_pct', 0):+.2f}%
- 30d Change: {price_action.get('change_30d_pct', 0):+.2f}%

- Trend Regime: {market_context.get('trend_regime', 'UNKNOWN')}
- Volatility Regime: {market_context.get('volatility_regime', 'UNKNOWN')}
- Liquidity Regime: {market_context.get('liquidity_regime', 'UNKNOWN')}

- Cross-Asset Correlations: {json.dumps(correlations.get('correlations', {}), indent=2)}
- Correlation Regime: {correlations.get('correlation_regime', 'UNKNOWN')}

- Bid-Ask Spread: {microstructure.get('bid_ask_spread_pct', 0):.2%}
- Orderbook Imbalance: {microstructure.get('orderbook_imbalance', 0):+.2f} (positive = buy pressure)

**PORTFOLIO STATE:**
- Total Value: R{portfolio_state.get('total_value_zar', 0):,.2f}
- Current Drawdown: {portfolio_state.get('current_drawdown_pct', 0):.2%}
- Open Positions: {portfolio_state.get('num_open_positions', 0)}
- Available Capital: R{portfolio_state.get('available_capital_zar', 0):,.2f}

**RECENT ML PERFORMANCE (Last 10 predictions):**
{self._format_recent_predictions(market_context.get('recent_ml_predictions', []))}

**YOUR TASK:**
Analyze this proposed trade and provide a strategic decision. Consider:
1. Does this trade make sense given the current market regime?
2. Are there any red flags in the market context (correlations, liquidity, news)?
3. Is the position size appropriate given portfolio state and drawdown?
4. Does the ML confidence align with market conditions?
5. Are there any tactical modifications you would recommend?

**OUTPUT FORMAT (JSON only, no explanation outside JSON):**
```json
{{
    "decision": "APPROVE | REJECT | MODIFY",
    "reasoning": "Detailed explanation of your decision (2-4 sentences)",
    "confidence_adjustment": 0.0 to 1.0 (1.0 = no adjustment),
    "position_size_multiplier": 0.0 to 2.0 (1.0 = no adjustment, <1.0 = reduce, >1.0 = increase),
    "risk_flags": ["List of any risk concerns"],
    "suggested_modifications": {{
        "leverage": null or new leverage,
        "stop_loss_pct": null or new stop loss,
        "take_profit_pct": null or new take profit
    }}
}}
```

Respond with JSON only."""

        return prompt

    def _format_recent_predictions(self, predictions: List[Dict]) -> str:
        """Format recent predictions for prompt."""
        if not predictions:
            return "No recent predictions available."

        lines = []
        correct_count = sum(1 for p in predictions if p.get('correct') is True)
        total_with_outcome = sum(1 for p in predictions if p.get('correct') is not None)

        accuracy = (correct_count / total_with_outcome * 100) if total_with_outcome > 0 else 0

        lines.append(f"Recent Accuracy: {accuracy:.1f}% ({correct_count}/{total_with_outcome})")
        lines.append("")

        for p in predictions[:5]:  # Show last 5
            outcome = "✓" if p.get('correct') is True else "✗" if p.get('correct') is False else "?"
            lines.append(f"  {outcome} {p['prediction']} (conf: {p['confidence']:.2%}) - {p['timestamp']}")

        return "\n".join(lines)

    async def _call_anthropic(self, prompt: str, fallback: bool = False) -> str:
        """Call Claude API."""
        client = self.fallback_client if fallback else self.client
        model = self.fallback_model if fallback else self.model

        message = await client.messages.create(
            model=model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        return message.content[0].text

    async def _call_openrouter(self, prompt: str, fallback: bool = False) -> str:
        """Call OpenRouter API (GPT-4)."""
        client = self.fallback_client if fallback else self.client
        model = self.fallback_model if fallback else self.model

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a professional cryptocurrency trading strategist."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )

        return response.choices[0].message.content

    def _parse_llm_response(self, response: str) -> Dict:
        """Parse LLM response (expecting JSON)."""
        try:
            # Extract JSON from response (in case LLM adds markdown)
            if '```json' in response:
                json_start = response.index('```json') + 7
                json_end = response.index('```', json_start)
                json_str = response[json_start:json_end].strip()
            elif '```' in response:
                json_start = response.index('```') + 3
                json_end = response.index('```', json_start)
                json_str = response[json_start:json_end].strip()
            else:
                json_str = response.strip()

            parsed = json.loads(json_str)

            # Validate required fields
            required = ['decision', 'reasoning', 'confidence_adjustment',
                       'position_size_multiplier', 'risk_flags', 'suggested_modifications']

            for field in required:
                if field not in parsed:
                    raise ValueError(f"Missing required field: {field}")

            # Validate decision value
            if parsed['decision'] not in ['APPROVE', 'REJECT', 'MODIFY']:
                raise ValueError(f"Invalid decision: {parsed['decision']}")

            # Clamp values to safe ranges
            parsed['confidence_adjustment'] = max(0.0, min(1.0, float(parsed['confidence_adjustment'])))
            parsed['position_size_multiplier'] = max(0.0, min(2.0, float(parsed['position_size_multiplier'])))

            return parsed

        except Exception as e:
            logger.error(f"LLM response parsing failed: {e}\nResponse: {response[:500]}")
            # Fallback if parsing fails
            return {
                'decision': 'REJECT',
                'reasoning': f'LLM response parsing failed: {str(e)}',
                'confidence_adjustment': 0.0,
                'position_size_multiplier': 0.0,
                'risk_flags': ['LLM_PARSE_ERROR'],
                'suggested_modifications': {}
            }

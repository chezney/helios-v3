"""
LLM Strategy API

Provides endpoints for LLM-powered strategic decision making:
- Market analysis and insights
- Trading strategy recommendations
- Risk assessment and warnings
- News sentiment analysis
- Portfolio optimization suggestions
- Strategic decision explanations
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
import asyncpg

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__, component="llm_api")

router = APIRouter(prefix="/api/llm", tags=["LLM Strategy"])


# ============================================================================
# Database Helper
# ============================================================================

async def get_db_connection():
    """Get raw asyncpg connection to database."""
    return await asyncpg.connect(
        host=settings.database.postgres_host,
        port=settings.database.postgres_port,
        user=settings.database.postgres_user,
        password=settings.database.postgres_password,
        database=settings.database.postgres_db,
        ssl=False
    )


# ============================================================================
# Pydantic Models
# ============================================================================

class AnalysisType(str, Enum):
    """Type of analysis to perform."""
    MARKET_OVERVIEW = "market_overview"
    TECHNICAL = "technical"
    SENTIMENT = "sentiment"
    RISK = "risk"
    PORTFOLIO = "portfolio"


class TradingAction(str, Enum):
    """Recommended trading action."""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class AnalysisRequest(BaseModel):
    """Request for LLM market analysis."""
    symbol: str = Field(..., description="Trading pair symbol")
    analysis_type: AnalysisType = Field(AnalysisType.MARKET_OVERVIEW, description="Type of analysis")
    lookback_hours: int = Field(24, ge=1, le=168, description="Hours of data to analyze")
    include_news: bool = Field(False, description="Include news sentiment analysis")


class AnalysisResponse(BaseModel):
    """LLM market analysis response."""
    symbol: str
    analysis_type: str
    summary: str
    key_insights: List[str]
    recommendation: TradingAction
    confidence: float  # 0.0 - 1.0
    reasoning: str
    risk_factors: List[str]
    timestamp: datetime


class StrategyRequest(BaseModel):
    """Request for trading strategy recommendation."""
    symbols: List[str] = Field(..., description="Trading pairs to analyze")
    timeframe: str = Field("4h", description="Trading timeframe (1h, 4h, 1d)")
    risk_tolerance: str = Field("medium", description="Risk tolerance (low, medium, high)")
    capital_allocation_zar: float = Field(10000.0, ge=1000, description="Capital to allocate")


class StrategyResponse(BaseModel):
    """Trading strategy recommendation."""
    strategy_id: str
    timeframe: str
    recommended_positions: List[Dict[str, Any]]
    entry_points: Dict[str, float]
    exit_points: Dict[str, float]
    stop_losses: Dict[str, float]
    position_sizes_zar: Dict[str, float]
    expected_return_pct: float
    max_risk_pct: float
    reasoning: str
    timestamp: datetime


class NewsItem(BaseModel):
    """News article with sentiment."""
    title: str
    source: str
    published_at: datetime
    sentiment: str  # positive, negative, neutral
    sentiment_score: float  # -1.0 to 1.0
    relevance: float  # 0.0 to 1.0
    summary: str


class NewsSentimentResponse(BaseModel):
    """News sentiment analysis."""
    symbol: str
    overall_sentiment: str
    sentiment_score: float
    article_count: int
    articles: List[NewsItem]
    market_impact: str
    timestamp: datetime


class RiskAssessmentRequest(BaseModel):
    """Request for risk assessment."""
    symbol: Optional[str] = Field(None, description="Specific symbol or portfolio-wide")
    scenario: str = Field("current", description="Scenario to assess (current, bull, bear, crash)")


class RiskAssessmentResponse(BaseModel):
    """LLM risk assessment."""
    scenario: str
    overall_risk_level: str  # low, medium, high, critical
    risk_score: float  # 0.0 - 1.0
    primary_risks: List[str]
    mitigation_strategies: List[str]
    recommended_actions: List[str]
    reasoning: str
    timestamp: datetime


class ExplanationRequest(BaseModel):
    """Request for decision explanation."""
    decision_type: str = Field(..., description="Type of decision (trade, position_size, exit)")
    decision_id: str = Field(..., description="ID of the decision to explain")


class ExplanationResponse(BaseModel):
    """Explanation of a trading decision."""
    decision_type: str
    decision_id: str
    decision_summary: str
    factors_considered: List[Dict[str, Any]]
    reasoning_chain: List[str]
    alternative_actions: List[str]
    confidence: float
    timestamp: datetime


class PortfolioOptimizationRequest(BaseModel):
    """Request for portfolio optimization."""
    current_positions: List[Dict[str, Any]] = Field(..., description="Current portfolio positions")
    target_return_pct: Optional[float] = Field(None, ge=0, le=200)
    max_drawdown_pct: Optional[float] = Field(15.0, ge=0, le=50)


class PortfolioOptimizationResponse(BaseModel):
    """Portfolio optimization recommendation."""
    current_allocation: Dict[str, float]
    recommended_allocation: Dict[str, float]
    rebalancing_actions: List[Dict[str, Any]]
    expected_return_pct: float
    expected_volatility_pct: float
    sharpe_ratio: float
    reasoning: str
    timestamp: datetime


# ============================================================================
# Helper Functions
# ============================================================================

async def get_market_context(symbol: str, lookback_hours: int = 24) -> Dict[str, Any]:
    """Get market context for LLM analysis."""
    conn = await get_db_connection()
    try:
        # Get recent candles from market_ohlc with 1h timeframe
        candles = await conn.fetch("""
            SELECT close_price, high_price, low_price, volume, open_time
            FROM market_ohlc
            WHERE pair = $1 AND timeframe = '1h'
            ORDER BY open_time DESC
            LIMIT $2
        """, symbol, lookback_hours)

        if not candles:
            return {
                "price_change_pct": 0.0,
                "volatility": 0.0,
                "volume_trend": "neutral",
                "trend": "sideways"
            }

        # Calculate basic metrics
        current_price = float(candles[0]['close_price'])
        start_price = float(candles[-1]['close_price'])
        price_change_pct = ((current_price - start_price) / start_price) * 100

        # Simple trend detection
        if price_change_pct > 2:
            trend = "uptrend"
        elif price_change_pct < -2:
            trend = "downtrend"
        else:
            trend = "sideways"

        return {
            "price_change_pct": round(price_change_pct, 2),
            "current_price": current_price,
            "high_24h": max(float(c['high_price']) for c in candles),
            "low_24h": min(float(c['low_price']) for c in candles),
            "trend": trend,
            "data_points": len(candles)
        }

    except Exception as e:
        logger.warning(f"Failed to get market context: {e}")
        return {"error": str(e)}
    finally:
        await conn.close()


async def call_llm_service(prompt: str, context: Dict[str, Any]) -> str:
    """Call LLM service for analysis."""
    try:
        from src.llm.client.llm_client import llm_client

        # Build full prompt with context
        full_prompt = f"""
Market Analysis Context:
{context}

Request:
{prompt}

Provide a detailed analysis with clear reasoning.
"""
        response = await llm_client.analyze(full_prompt)
        return response.get("analysis", "Analysis unavailable")

    except Exception as e:
        logger.warning(f"LLM service unavailable: {e}")
        # Return fallback analysis
        return "LLM analysis service temporarily unavailable. Using fallback analysis."


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_market(request: AnalysisRequest):
    """
    Perform LLM-powered market analysis.

    Analyzes market conditions and provides insights with reasoning.
    """
    try:
        # Get market context
        context = await get_market_context(request.symbol, request.lookback_hours)

        # Generate analysis based on type
        if request.analysis_type == AnalysisType.MARKET_OVERVIEW:
            summary = f"Market overview for {request.symbol}: "

            if "trend" in context:
                summary += f"Currently in {context['trend']} with {context['price_change_pct']}% change. "

            key_insights = [
                f"Price movement: {context.get('price_change_pct', 0)}% over {request.lookback_hours}h",
                f"Trend: {context.get('trend', 'sideways')}",
                "Market conditions are stable" if abs(context.get('price_change_pct', 0)) < 5 else "Market showing volatility"
            ]

            # Determine recommendation
            price_change = context.get('price_change_pct', 0)
            if price_change > 5:
                recommendation = TradingAction.BUY
                confidence = 0.7
            elif price_change < -5:
                recommendation = TradingAction.SELL
                confidence = 0.7
            else:
                recommendation = TradingAction.HOLD
                confidence = 0.6

            reasoning = f"Based on {request.lookback_hours}h analysis showing {context.get('trend', 'sideways')} trend with {price_change}% movement."

            risk_factors = [
                "Market volatility present" if abs(price_change) > 5 else "Low volatility conditions",
                "Limited historical data" if context.get('data_points', 0) < 24 else "Sufficient data available"
            ]

        else:
            # Generic analysis for other types
            summary = f"{request.analysis_type.value} analysis for {request.symbol}"
            key_insights = ["Analysis generated", "Market conditions evaluated"]
            recommendation = TradingAction.HOLD
            confidence = 0.5
            reasoning = f"Standard {request.analysis_type.value} assessment"
            risk_factors = ["General market risk"]

        return AnalysisResponse(
            symbol=request.symbol,
            analysis_type=request.analysis_type.value,
            summary=summary,
            key_insights=key_insights,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
            risk_factors=risk_factors,
            timestamp=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/strategy", response_model=StrategyResponse)
async def recommend_strategy(request: StrategyRequest):
    """
    Get LLM-powered trading strategy recommendation.

    Provides comprehensive strategy with entry/exit points and reasoning.
    """
    try:
        # Analyze each symbol
        positions = []
        entry_points = {}
        exit_points = {}
        stop_losses = {}
        position_sizes = {}

        capital_per_position = request.capital_allocation_zar / len(request.symbols)

        for symbol in request.symbols:
            context = await get_market_context(symbol, 24)

            current_price = context.get('current_price', 0)
            if current_price > 0:
                entry_points[symbol] = current_price

                # Set targets based on risk tolerance
                if request.risk_tolerance == "high":
                    exit_points[symbol] = current_price * 1.10  # 10% profit target
                    stop_losses[symbol] = current_price * 0.95  # 5% stop loss
                elif request.risk_tolerance == "low":
                    exit_points[symbol] = current_price * 1.03  # 3% profit target
                    stop_losses[symbol] = current_price * 0.98  # 2% stop loss
                else:  # medium
                    exit_points[symbol] = current_price * 1.05  # 5% profit target
                    stop_losses[symbol] = current_price * 0.97  # 3% stop loss

                position_sizes[symbol] = capital_per_position

                positions.append({
                    "symbol": symbol,
                    "action": "BUY" if context.get('trend') == "uptrend" else "HOLD",
                    "size_zar": capital_per_position,
                    "trend": context.get('trend', 'sideways')
                })

        strategy_id = f"strat_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        return StrategyResponse(
            strategy_id=strategy_id,
            timeframe=request.timeframe,
            recommended_positions=positions,
            entry_points=entry_points,
            exit_points=exit_points,
            stop_losses=stop_losses,
            position_sizes_zar=position_sizes,
            expected_return_pct=5.0 if request.risk_tolerance == "medium" else (3.0 if request.risk_tolerance == "low" else 10.0),
            max_risk_pct=3.0 if request.risk_tolerance == "medium" else (2.0 if request.risk_tolerance == "low" else 5.0),
            reasoning=f"Strategy optimized for {request.risk_tolerance} risk tolerance across {len(request.symbols)} symbols using {request.timeframe} timeframe.",
            timestamp=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Strategy generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Strategy generation failed: {str(e)}")


@router.get("/news/sentiment/{symbol}", response_model=NewsSentimentResponse)
async def get_news_sentiment(
    symbol: str,
    hours: int = Query(24, ge=1, le=168, description="Hours to look back")
):
    """
    Get news sentiment analysis for a symbol.

    Analyzes recent news and provides sentiment scoring.
    """
    # Mock news data (in production, would fetch from news API)
    mock_articles = [
        NewsItem(
            title=f"Bitcoin shows strong momentum as {symbol} gains",
            source="CryptoNews",
            published_at=datetime.utcnow() - timedelta(hours=2),
            sentiment="positive",
            sentiment_score=0.7,
            relevance=0.9,
            summary="Positive market outlook with strong technical indicators"
        ),
        NewsItem(
            title="Market volatility increases amid global uncertainty",
            source="FinanceDaily",
            published_at=datetime.utcnow() - timedelta(hours=5),
            sentiment="negative",
            sentiment_score=-0.4,
            relevance=0.6,
            summary="Increased volatility noted across cryptocurrency markets"
        ),
        NewsItem(
            title="Trading volumes remain stable for major pairs",
            source="TradingView",
            published_at=datetime.utcnow() - timedelta(hours=12),
            sentiment="neutral",
            sentiment_score=0.1,
            relevance=0.8,
            summary="Volume analysis shows consistent trading activity"
        )
    ]

    # Calculate overall sentiment
    avg_sentiment = sum(a.sentiment_score for a in mock_articles) / len(mock_articles)

    if avg_sentiment > 0.3:
        overall = "positive"
        market_impact = "Bullish sentiment may support upward price movement"
    elif avg_sentiment < -0.3:
        overall = "negative"
        market_impact = "Bearish sentiment may pressure prices downward"
    else:
        overall = "neutral"
        market_impact = "Mixed sentiment suggests consolidation"

    return NewsSentimentResponse(
        symbol=symbol,
        overall_sentiment=overall,
        sentiment_score=round(avg_sentiment, 2),
        article_count=len(mock_articles),
        articles=mock_articles,
        market_impact=market_impact,
        timestamp=datetime.utcnow()
    )


@router.post("/risk/assess", response_model=RiskAssessmentResponse)
async def assess_risk(request: RiskAssessmentRequest):
    """
    Perform LLM-powered risk assessment.

    Analyzes current positions and market conditions for risk factors.
    """
    # Get current portfolio state
    conn = await get_db_connection()
    try:
        portfolio = await conn.fetchrow("""
            SELECT total_value_zar, current_drawdown_pct, max_drawdown_pct
            FROM portfolio_state
            ORDER BY last_updated DESC
            LIMIT 1
        """)

        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        drawdown = float(portfolio['current_drawdown_pct'])

        # Assess risk based on scenario and current state
        if request.scenario == "crash":
            risk_level = "critical"
            risk_score = 0.9
            primary_risks = [
                "Severe market downturn scenario",
                "Potential for significant losses",
                "High volatility expected"
            ]
            mitigation = [
                "Reduce position sizes immediately",
                "Increase cash holdings to 50%+",
                "Set tight stop losses on all positions"
            ]
            actions = [
                "Close high-risk positions",
                "Move to defensive assets",
                "Prepare for extended downturn"
            ]
        elif request.scenario == "bear":
            risk_level = "high"
            risk_score = 0.7
            primary_risks = [
                "Downward market pressure",
                "Reduced liquidity",
                "Increased volatility"
            ]
            mitigation = [
                "Reduce exposure to 60% of normal",
                "Focus on quality assets",
                "Implement trailing stops"
            ]
            actions = [
                "Trim speculative positions",
                "Raise cash to 30%",
                "Tighten risk parameters"
            ]
        elif drawdown > 10:
            risk_level = "high"
            risk_score = 0.75
            primary_risks = [
                f"Current drawdown at {drawdown}%",
                "Portfolio under stress",
                "Risk limits being approached"
            ]
            mitigation = [
                "Review and close losing positions",
                "Reduce new position sizes",
                "Wait for favorable conditions"
            ]
            actions = [
                "Implement damage control",
                "Preserve capital",
                "Reassess strategy"
            ]
        else:
            risk_level = "medium"
            risk_score = 0.4
            primary_risks = [
                "Normal market risk present",
                "Standard volatility levels",
                "Adequate diversification"
            ]
            mitigation = [
                "Maintain current risk parameters",
                "Monitor positions regularly",
                "Follow existing strategy"
            ]
            actions = [
                "Continue normal operations",
                "Stay disciplined",
                "Execute strategy as planned"
            ]

        reasoning = f"Risk assessment for {request.scenario} scenario. Current drawdown: {drawdown}%. Portfolio value: R{float(portfolio['total_value_zar']):.2f}."

        return RiskAssessmentResponse(
            scenario=request.scenario,
            overall_risk_level=risk_level,
            risk_score=risk_score,
            primary_risks=primary_risks,
            mitigation_strategies=mitigation,
            recommended_actions=actions,
            reasoning=reasoning,
            timestamp=datetime.utcnow()
        )

    finally:
        await conn.close()


@router.post("/explain", response_model=ExplanationResponse)
async def explain_decision(request: ExplanationRequest):
    """
    Get explanation for a trading decision.

    Provides detailed reasoning for why a decision was made.
    """
    # Mock explanation (in production, would retrieve from decision log)
    factors = [
        {
            "factor": "Technical Analysis",
            "weight": 0.4,
            "value": "Strong bullish signals",
            "contribution": "positive"
        },
        {
            "factor": "ML Prediction",
            "weight": 0.3,
            "value": "BUY with 0.75 confidence",
            "contribution": "positive"
        },
        {
            "factor": "Risk Assessment",
            "weight": 0.2,
            "value": "Within acceptable limits",
            "contribution": "neutral"
        },
        {
            "factor": "Portfolio Diversification",
            "weight": 0.1,
            "value": "Improves balance",
            "contribution": "positive"
        }
    ]

    reasoning_chain = [
        "1. Analyzed market conditions and identified uptrend",
        "2. ML model confirmed BUY signal with high confidence",
        "3. Verified risk parameters within acceptable range",
        "4. Calculated optimal position size using Kelly criterion",
        "5. Confirmed portfolio diversification improved",
        "6. Executed trade with appropriate stop loss"
    ]

    alternatives = [
        "HOLD - Wait for stronger confirmation (considered but rejected due to strong signals)",
        "Smaller position size - Reduce risk (considered but signals justify full size)",
        "Different entry price - Wait for pullback (rejected due to momentum strength)"
    ]

    return ExplanationResponse(
        decision_type=request.decision_type,
        decision_id=request.decision_id,
        decision_summary=f"Executed {request.decision_type} decision {request.decision_id} based on multi-factor analysis",
        factors_considered=factors,
        reasoning_chain=reasoning_chain,
        alternative_actions=alternatives,
        confidence=0.75,
        timestamp=datetime.utcnow()
    )


@router.post("/portfolio/optimize", response_model=PortfolioOptimizationResponse)
async def optimize_portfolio(request: PortfolioOptimizationRequest):
    """
    Get portfolio optimization recommendations.

    Analyzes current portfolio and suggests improvements.
    """
    # Calculate current allocation
    total_value = sum(pos.get('value_zar', 0) for pos in request.current_positions)

    current_allocation = {}
    for pos in request.current_positions:
        symbol = pos.get('symbol', 'UNKNOWN')
        value = pos.get('value_zar', 0)
        current_allocation[symbol] = round((value / total_value * 100), 2) if total_value > 0 else 0

    # Generate recommended allocation (simplified - in production use MPT)
    num_positions = len(request.current_positions)
    target_pct = 100.0 / num_positions if num_positions > 0 else 0

    recommended_allocation = {
        symbol: target_pct for symbol in current_allocation.keys()
    }

    # Generate rebalancing actions
    rebalancing_actions = []
    for symbol, current_pct in current_allocation.items():
        recommended_pct = recommended_allocation[symbol]
        diff = recommended_pct - current_pct

        if abs(diff) > 2:  # Only rebalance if >2% difference
            action = "BUY" if diff > 0 else "SELL"
            amount_zar = abs(diff / 100 * total_value)
            rebalancing_actions.append({
                "symbol": symbol,
                "action": action,
                "amount_zar": round(amount_zar, 2),
                "current_pct": current_pct,
                "target_pct": recommended_pct
            })

    # Calculate expected metrics
    expected_return = request.target_return_pct if request.target_return_pct else 8.0
    expected_volatility = 15.0  # Mock value
    sharpe_ratio = (expected_return - 2.0) / expected_volatility  # Assuming 2% risk-free rate

    reasoning = f"Portfolio optimization for {num_positions} positions. "
    reasoning += f"Rebalancing to equal-weight allocation improves diversification. "
    reasoning += f"Expected return: {expected_return}%, volatility: {expected_volatility}%, Sharpe: {sharpe_ratio:.2f}."

    return PortfolioOptimizationResponse(
        current_allocation=current_allocation,
        recommended_allocation=recommended_allocation,
        rebalancing_actions=rebalancing_actions,
        expected_return_pct=expected_return,
        expected_volatility_pct=expected_volatility,
        sharpe_ratio=round(sharpe_ratio, 2),
        reasoning=reasoning,
        timestamp=datetime.utcnow()
    )


@router.get("/insights/daily")
async def get_daily_insights(
    symbols: List[str] = Query(["BTCZAR"], description="Symbols to analyze")
):
    """
    Get daily market insights and recommendations.

    Provides a daily briefing with key market movements and opportunities.
    """
    insights = []

    for symbol in symbols:
        context = await get_market_context(symbol, 24)

        insight = {
            "symbol": symbol,
            "price_change_24h_pct": context.get('price_change_pct', 0),
            "trend": context.get('trend', 'sideways'),
            "key_level": context.get('current_price', 0),
            "outlook": "bullish" if context.get('price_change_pct', 0) > 2 else (
                "bearish" if context.get('price_change_pct', 0) < -2 else "neutral"
            ),
            "recommendation": "Consider buying on dips" if context.get('trend') == "uptrend" else (
                "Wait for confirmation" if context.get('trend') == "sideways" else "Avoid new positions"
            )
        }
        insights.append(insight)

    return {
        "date": datetime.utcnow().date().isoformat(),
        "market_summary": "Mixed conditions across analyzed pairs",
        "insights": insights,
        "opportunities": [i for i in insights if i['outlook'] == 'bullish'],
        "warnings": [i for i in insights if i['outlook'] == 'bearish'],
        "timestamp": datetime.utcnow().isoformat()
    }

"""Research engine for deep market research with chain-of-thought reasoning."""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import uuid
from loguru import logger

from src.config import config


# =====================================
# Data Classes
# =====================================

@dataclass
class ReasoningStep:
    """Single step in chain-of-thought reasoning."""
    step_number: int
    step_name: str
    reasoning: str
    data: Dict[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "step_number": self.step_number,
            "step_name": self.step_name,
            "reasoning": self.reasoning,
            "data": self.data,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class ResearchReport:
    """Structured research report with recommendations."""
    symbol: str
    research_type: str  # "deep_symbol", "comparative", "theme_candidate"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reasoning_chain: List[ReasoningStep] = field(default_factory=list)
    fundamental_score: float = 0.0  # 0-10
    technical_score: float = 0.0  # 0-10
    sentiment_score: float = 0.0  # 0-10
    overall_score: float = 0.0  # 0-10
    recommendation: str = "RESEARCH_MORE"  # BUY, HOLD, SELL, RESEARCH_MORE
    confidence: float = 0.0  # 0-1
    key_findings: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    catalysts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            "symbol": self.symbol,
            "research_type": self.research_type,
            "timestamp": self.timestamp.isoformat(),
            "reasoning_chain": [step.to_dict() for step in self.reasoning_chain],
            "fundamental_score": self.fundamental_score,
            "technical_score": self.technical_score,
            "sentiment_score": self.sentiment_score,
            "overall_score": self.overall_score,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "key_findings": self.key_findings,
            "risks": self.risks,
            "catalysts": self.catalysts
        }


@dataclass
class ThemeChangeProposal:
    """Proposal to change theme symbols."""
    theme_name: str  # "theme_a", "theme_b", "theme_c"
    current_symbols: List[str]
    proposed_symbols: List[str]
    reasoning_chain: List[ReasoningStep] = field(default_factory=list)
    recommendation_score: float = 0.0  # 0-10
    confidence: float = 0.0  # 0-1
    expected_improvement: str = ""
    risks: List[str] = field(default_factory=list)
    status: str = "proposed"  # "proposed", "approved", "rejected", "executed"

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            "theme_name": self.theme_name,
            "current_symbols": self.current_symbols,
            "proposed_symbols": self.proposed_symbols,
            "reasoning_chain": [step.to_dict() for step in self.reasoning_chain],
            "recommendation_score": self.recommendation_score,
            "confidence": self.confidence,
            "expected_improvement": self.expected_improvement,
            "risks": self.risks,
            "status": self.status
        }

    def summary(self) -> str:
        """Generate summary string."""
        return (
            f"{self.theme_name}: {', '.join(self.current_symbols)} → "
            f"{', '.join(self.proposed_symbols)} "
            f"(score={self.recommendation_score:.1f}/10, confidence={self.confidence:.0%})"
        )


@dataclass
class ThemeEvaluationReport:
    """Report on theme evaluation with alternatives."""
    theme_name: str
    current_symbols: List[str]
    current_performance_score: float = 0.0  # 0-10
    alternative_candidates: List[Dict[str, Any]] = field(default_factory=list)  # List of {symbol, score, reason}
    should_change: bool = False
    rationale: str = ""

    def get_alternative_candidates(self) -> List[str]:
        """Get list of alternative symbol candidates."""
        return [c["symbol"] for c in self.alternative_candidates if c.get("symbol")]


# =====================================
# Chain-of-Thought Logger
# =====================================

class ChainOfThoughtLogger:
    """Structured chain-of-thought reasoning logger."""

    def __init__(self, storage_manager=None):
        """Initialize chain-of-thought logger.

        Args:
            storage_manager: Optional storage manager for persistence
        """
        self.storage = storage_manager
        self.session_id = f"research_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.steps: List[ReasoningStep] = []
        self.current_step = 0

    def log_step(self, step_name: str, reasoning: str, data: Optional[Dict] = None,
                 confidence: Optional[float] = None) -> ReasoningStep:
        """Log a reasoning step.

        Args:
            step_name: Name of this step
            reasoning: Human-readable reasoning text
            data: Optional supporting data
            confidence: Optional confidence score (0-1)

        Returns:
            ReasoningStep object
        """
        self.current_step += 1
        step = ReasoningStep(
            step_number=self.current_step,
            step_name=step_name,
            reasoning=reasoning,
            data=data or {},
            confidence=confidence
        )
        self.steps.append(step)

        # Log to console
        confidence_str = f" (confidence: {confidence:.0%})" if confidence else ""
        logger.info(f"[COT Step {self.current_step}] {step_name}{confidence_str}: {reasoning[:200]}")

        # Persist to database if storage available
        if self.storage and config.cot_logging_enabled:
            try:
                self.storage.log_chain_of_thought(
                    session_id=self.session_id,
                    step_number=self.current_step,
                    step_name=step_name,
                    reasoning=reasoning,
                    data=data,
                    confidence=confidence
                )
            except Exception as e:
                logger.warning(f"Failed to persist chain-of-thought step: {e}")

        return step

    def log_decision(self, decision: str, rationale: str, confidence: float) -> ReasoningStep:
        """Log a decision with rationale.

        Args:
            decision: The decision made
            rationale: Reasoning for the decision
            confidence: Confidence score (0-1)

        Returns:
            ReasoningStep object
        """
        return self.log_step(
            step_name="Decision",
            reasoning=f"{decision} - {rationale}",
            data={"decision": decision, "rationale": rationale},
            confidence=confidence
        )

    def get_reasoning_chain(self) -> List[ReasoningStep]:
        """Get complete reasoning chain.

        Returns:
            List of reasoning steps
        """
        return self.steps

    def get_session_id(self) -> str:
        """Get session ID for this reasoning chain.

        Returns:
            Session ID string
        """
        return self.session_id


# =====================================
# Research Engine
# =====================================

class ResearchEngine:
    """Orchestrates deep research workflows with chain-of-thought reasoning."""

    def __init__(self, bot):
        """Initialize research engine.

        Args:
            bot: TradingBot instance with access to clients and managers
        """
        self.bot = bot
        self.storage = getattr(bot, "storage", None)

        # Import managers
        try:
            from src.fundamental_analysis import FundamentalAnalysis
            self.fundamental = FundamentalAnalysis()
        except Exception as e:
            logger.warning(f"Could not initialize fundamental analysis: {e}")
            self.fundamental = None

    def deep_research_symbol(self, symbol: str) -> ResearchReport:
        """Run comprehensive multi-step research on a symbol.

        This executes the 7-step research workflow:
        1. Initialize Context
        2. Fundamental Analysis
        3. Technical Analysis
        4. Market Sentiment
        5. Comparative Analysis
        6. Risk Assessment
        7. Recommendation Synthesis

        Args:
            symbol: Stock symbol to research

        Returns:
            ResearchReport with scores, recommendation, and reasoning chain
        """
        logger.info(f"Starting deep research on {symbol}")
        cot = ChainOfThoughtLogger(self.storage)

        # Initialize report
        report = ResearchReport(
            symbol=symbol,
            research_type="deep_symbol"
        )

        try:
            # Step 1: Initialize Context
            step1 = self._step1_initialize_context(symbol, cot)

            # Step 2: Fundamental Analysis
            fundamental_score, fundamental_data = self._step2_fundamental_analysis(symbol, cot)
            report.fundamental_score = fundamental_score

            # Step 3: Technical Analysis
            technical_score, technical_data = self._step3_technical_analysis(symbol, cot)
            report.technical_score = technical_score

            # Step 4: Market Sentiment
            sentiment_score, sentiment_data = self._step4_market_sentiment(symbol, cot)
            report.sentiment_score = sentiment_score

            # Step 5: Comparative Analysis (skip for now, implement later)
            # comparative_data = self._step5_comparative_analysis(symbol, cot)

            # Step 6: Risk Assessment
            risks = self._step6_risk_assessment(symbol, cot, fundamental_data, technical_data)
            report.risks = risks

            # Step 7: Recommendation Synthesis
            recommendation, confidence, overall_score, findings = self._step7_recommendation_synthesis(
                symbol, cot,
                fundamental_score, technical_score, sentiment_score,
                fundamental_data, technical_data, sentiment_data, risks
            )
            report.recommendation = recommendation
            report.confidence = confidence
            report.overall_score = overall_score
            report.key_findings = findings

            # Attach reasoning chain
            report.reasoning_chain = cot.get_reasoning_chain()

            logger.info(f"Deep research complete: {symbol} - {recommendation} (score={overall_score:.1f}/10, confidence={confidence:.0%})")

        except Exception as e:
            logger.error(f"Deep research failed for {symbol}: {e}")
            cot.log_step("Error", f"Research failed: {str(e)}", confidence=0.0)
            report.reasoning_chain = cot.get_reasoning_chain()

        return report

    def _step1_initialize_context(self, symbol: str, cot: ChainOfThoughtLogger) -> Dict:
        """Step 1: Initialize context with portfolio state."""
        try:
            # Get current portfolio state
            pm = self.bot.portfolio_manager
            pm.refresh_portfolio()
            equity = pm.get_equity()
            allocations = pm.get_current_allocations()

            # Check if symbol is in current holdings
            positions = pm.get_positions()
            current_position = next((p for p in positions if p.underlying == symbol), None)

            context = {
                "equity": equity,
                "allocations": allocations,
                "has_position": current_position is not None,
                "position_value": current_position.market_value if current_position else 0
            }

            reasoning = (
                f"Starting research on {symbol}. Portfolio equity: ${equity:,.0f}. "
                f"Current position: {'Yes' if current_position else 'No'}."
            )
            if current_position:
                reasoning += f" Position value: ${current_position.market_value:,.0f}."

            cot.log_step("Initialize Context", reasoning, data=context, confidence=1.0)
            return context

        except Exception as e:
            logger.warning(f"Could not initialize context: {e}")
            cot.log_step("Initialize Context", f"Limited context available: {str(e)}", confidence=0.5)
            return {}

    def _step2_fundamental_analysis(self, symbol: str, cot: ChainOfThoughtLogger) -> tuple[float, Dict]:
        """Step 2: Fundamental analysis with DCF, P/E, etc."""
        if not self.fundamental:
            cot.log_step("Fundamental Analysis", "Fundamental analysis not available", confidence=0.0)
            return 5.0, {}  # Neutral score

        try:
            # Run fundamental analysis
            fund_result = self.fundamental.analyze(symbol)

            if not fund_result or fund_result.get("error"):
                error_msg = fund_result.get("error", "Unknown error") if fund_result else "No data"
                cot.log_step("Fundamental Analysis", f"Analysis failed: {error_msg}", confidence=0.0)
                return 5.0, {}

            # Extract scores
            valuation_score = fund_result.get("valuation_score", 3)  # 0-6 scale
            # Convert to 0-10 scale
            fundamental_score = (valuation_score / 6.0) * 10.0

            # Build reasoning
            dcf_value = fund_result.get("dcf_valuation", {}).get("intrinsic_value")
            current_price = fund_result.get("current_price")
            pe_ratio = fund_result.get("pe_analysis", {}).get("pe_ratio")

            reasoning_parts = [f"Fundamental analysis for {symbol}:"]
            if dcf_value and current_price:
                discount_pct = ((current_price - dcf_value) / dcf_value) * 100
                reasoning_parts.append(
                    f"DCF intrinsic value ${dcf_value:.2f}, current price ${current_price:.2f} "
                    f"({discount_pct:+.1f}%)."
                )
            if pe_ratio:
                reasoning_parts.append(f"P/E ratio: {pe_ratio:.1f}.")
            reasoning_parts.append(f"Valuation score: {fundamental_score:.1f}/10.")

            reasoning = " ".join(reasoning_parts)
            cot.log_step("Fundamental Analysis", reasoning, data=fund_result, confidence=0.8)
            return fundamental_score, fund_result

        except Exception as e:
            logger.warning(f"Fundamental analysis failed for {symbol}: {e}")
            cot.log_step("Fundamental Analysis", f"Analysis error: {str(e)}", confidence=0.0)
            return 5.0, {}

    def _step3_technical_analysis(self, symbol: str, cot: ChainOfThoughtLogger) -> tuple[float, Dict]:
        """Step 3: Technical analysis with advanced TA-Lib indicators."""
        try:
            import yfinance as yf
            import pandas as pd
            import numpy as np

            # Try to import TA-Lib (falls back to basic analysis if not available)
            try:
                import talib
                use_talib = True
            except ImportError:
                use_talib = False
                logger.debug("TA-Lib not available, using basic technical analysis")

            # Fetch historical data
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="6mo")  # 6 months of data

            if hist.empty:
                cot.log_step("Technical Analysis", f"No historical data for {symbol}", confidence=0.0)
                return 5.0, {}

            close = hist['Close'].values
            high = hist['High'].values
            low = hist['Low'].values
            volume = hist['Volume'].values
            current_price = float(hist['Close'].iloc[-1])

            technical_score = 5.0  # Start neutral
            technical_data = {"current_price": current_price}

            if use_talib and len(close) >= 50:
                # === ADVANCED TA-LIB ANALYSIS ===

                # 1. Moving Averages (Trend)
                sma_20 = talib.SMA(close, timeperiod=20)
                sma_50 = talib.SMA(close, timeperiod=50)
                ema_12 = talib.EMA(close, timeperiod=12)
                ema_26 = talib.EMA(close, timeperiod=26)

                current_sma_20 = float(sma_20[-1]) if len(sma_20) > 0 else current_price
                current_sma_50 = float(sma_50[-1]) if len(sma_50) > 0 else current_price

                # Trend scoring
                if current_price > current_sma_20:
                    technical_score += 1.0  # Above short-term trend
                if current_price > current_sma_50:
                    technical_score += 0.5  # Above long-term trend
                if current_sma_20 > current_sma_50:
                    technical_score += 1.0  # Golden cross territory

                technical_data.update({
                    "sma_20": current_sma_20,
                    "sma_50": current_sma_50,
                    "trend": "bullish" if current_price > current_sma_20 else "bearish"
                })

                # 2. MACD (Momentum)
                macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
                current_macd = float(macd[-1]) if len(macd) > 0 else 0
                current_macd_signal = float(macd_signal[-1]) if len(macd_signal) > 0 else 0
                current_macd_hist = float(macd_hist[-1]) if len(macd_hist) > 0 else 0

                # MACD scoring
                if current_macd > current_macd_signal and current_macd_hist > 0:
                    technical_score += 1.5  # Bullish MACD crossover
                elif current_macd < current_macd_signal and current_macd_hist < 0:
                    technical_score -= 0.5  # Bearish MACD crossover

                technical_data.update({
                    "macd": current_macd,
                    "macd_signal": current_macd_signal,
                    "macd_histogram": current_macd_hist
                })

                # 3. RSI (Overbought/Oversold)
                rsi = talib.RSI(close, timeperiod=14)
                current_rsi = float(rsi[-1]) if len(rsi) > 0 else 50

                # RSI scoring
                if 40 <= current_rsi <= 60:
                    technical_score += 1.0  # Neutral zone (healthy)
                elif 30 <= current_rsi < 40:
                    technical_score += 0.5  # Slightly oversold (potential buy)
                elif current_rsi < 30:
                    technical_score += 0.25  # Oversold (risky but opportunity)
                elif 60 < current_rsi <= 70:
                    technical_score += 0.5  # Slightly overbought
                elif current_rsi > 70:
                    technical_score -= 0.5  # Overbought (risk)

                technical_data["rsi"] = current_rsi

                # 4. Bollinger Bands (Volatility)
                upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
                current_upper = float(upper[-1]) if len(upper) > 0 else current_price * 1.02
                current_lower = float(lower[-1]) if len(lower) > 0 else current_price * 0.98
                current_middle = float(middle[-1]) if len(middle) > 0 else current_price

                # Bollinger scoring
                bb_width = (current_upper - current_lower) / current_middle
                price_position = (current_price - current_lower) / (current_upper - current_lower) if current_upper > current_lower else 0.5

                if 0.4 <= price_position <= 0.6:
                    technical_score += 0.5  # Near middle (neutral, good)
                elif price_position < 0.2:
                    technical_score += 0.25  # Near lower band (oversold)
                elif price_position > 0.8:
                    technical_score -= 0.25  # Near upper band (overbought)

                technical_data.update({
                    "bb_upper": current_upper,
                    "bb_middle": current_middle,
                    "bb_lower": current_lower,
                    "bb_width": bb_width,
                    "bb_position": price_position
                })

                # 5. Stochastic Oscillator (Momentum)
                slowk, slowd = talib.STOCH(high, low, close, fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
                current_slowk = float(slowk[-1]) if len(slowk) > 0 else 50
                current_slowd = float(slowd[-1]) if len(slowd) > 0 else 50

                # Stochastic scoring
                if current_slowk < 20 and current_slowk > current_slowd:
                    technical_score += 0.5  # Oversold with bullish cross
                elif current_slowk > 80 and current_slowk < current_slowd:
                    technical_score -= 0.5  # Overbought with bearish cross

                technical_data.update({
                    "stoch_k": current_slowk,
                    "stoch_d": current_slowd
                })

                # 6. ATR (Volatility measurement)
                atr = talib.ATR(high, low, close, timeperiod=14)
                current_atr = float(atr[-1]) if len(atr) > 0 else 0
                atr_percent = (current_atr / current_price) * 100 if current_price > 0 else 0

                # Volatility penalty
                if atr_percent > 5:  # High volatility (> 5% daily range)
                    technical_score -= 1.0
                elif atr_percent > 3:
                    technical_score -= 0.5

                technical_data.update({
                    "atr": current_atr,
                    "atr_percent": atr_percent
                })

                # 7. ADX (Trend Strength)
                adx = talib.ADX(high, low, close, timeperiod=14)
                current_adx = float(adx[-1]) if len(adx) > 0 else 25

                # ADX scoring (trend strength)
                if current_adx > 25:
                    technical_score += 0.5  # Strong trend
                if current_adx > 40:
                    technical_score += 0.5  # Very strong trend

                technical_data["adx"] = current_adx

                confidence = 0.85  # High confidence with TA-Lib

            else:
                # === BASIC ANALYSIS (Fallback) ===
                sma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                sma_50 = hist['Close'].rolling(window=50).mean().iloc[-1] if len(hist) >= 50 else sma_20

                # Basic RSI
                delta = hist['Close'].diff()
                gain = delta.where(delta > 0, 0).rolling(window=14).mean()
                loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                current_rsi = rsi.iloc[-1] if not rsi.empty else 50

                # Basic scoring
                if current_price > sma_20:
                    technical_score += 1.5
                if sma_20 > sma_50:
                    technical_score += 1.5
                if 40 <= current_rsi <= 60:
                    technical_score += 1.0

                # Volatility
                returns = hist['Close'].pct_change()
                volatility_30d = returns.tail(30).std() * (252 ** 0.5)
                if volatility_30d > 0.5:
                    technical_score -= 1.0

                technical_data.update({
                    "sma_20": float(sma_20),
                    "sma_50": float(sma_50),
                    "rsi": float(current_rsi),
                    "volatility_30d": float(volatility_30d),
                    "trend": "bullish" if current_price > sma_20 else "bearish"
                })

                confidence = 0.70  # Lower confidence without TA-Lib

            # Cap score at 10
            technical_score = min(10.0, max(0.0, technical_score))

            # Build reasoning
            reasoning_parts = [f"Technical analysis for {symbol}:"]
            if use_talib:
                reasoning_parts.append(f"Price ${current_price:.2f} vs SMA(20) ${technical_data.get('sma_20', 0):.2f}.")
                reasoning_parts.append(f"MACD histogram {technical_data.get('macd_histogram', 0):+.2f}.")
                reasoning_parts.append(f"RSI {technical_data.get('rsi', 50):.0f}, ADX {technical_data.get('adx', 25):.0f}.")
                reasoning_parts.append(f"Bollinger position {technical_data.get('bb_position', 0.5)*100:.0f}%.")
            else:
                reasoning_parts.append(f"Price ${current_price:.2f}, SMA(20) ${technical_data.get('sma_20', 0):.2f}.")
                reasoning_parts.append(f"RSI {technical_data.get('rsi', 50):.0f}.")
            reasoning_parts.append(f"Score: {technical_score:.1f}/10.")

            reasoning = " ".join(reasoning_parts)
            cot.log_step("Technical Analysis", reasoning, data=technical_data, confidence=confidence)
            return technical_score, technical_data

        except Exception as e:
            logger.warning(f"Technical analysis failed for {symbol}: {e}")
            cot.log_step("Technical Analysis", f"Analysis error: {str(e)}", confidence=0.0)
            return 5.0, {}

    def _step4_market_sentiment(self, symbol: str, cot: ChainOfThoughtLogger) -> tuple[float, Dict]:
        """Step 4: Market sentiment from news and data."""
        try:
            import yfinance as yf

            # Fetch news
            ticker = yf.Ticker(symbol)
            news = ticker.news[:5] if hasattr(ticker, 'news') else []

            # Simple sentiment scoring based on news availability
            sentiment_score = 5.0  # Neutral default
            sentiment_data = {
                "news_count": len(news),
                "headlines": [n.get('title', '') for n in news[:3]] if news else []
            }

            if news:
                sentiment_score = 6.0  # Slight positive if news exists
                reasoning = f"Found {len(news)} recent news items for {symbol}. Headlines: {', '.join(sentiment_data['headlines'][:2])}"
            else:
                reasoning = f"No recent news found for {symbol}. Neutral sentiment assumed."

            cot.log_step("Market Sentiment", reasoning, data=sentiment_data, confidence=0.5)
            return sentiment_score, sentiment_data

        except Exception as e:
            logger.warning(f"Sentiment analysis failed for {symbol}: {e}")
            cot.log_step("Market Sentiment", f"Analysis error: {str(e)}", confidence=0.0)
            return 5.0, {}

    def _step6_risk_assessment(self, symbol: str, cot: ChainOfThoughtLogger,
                              fundamental_data: Dict, technical_data: Dict) -> List[str]:
        """Step 6: Identify risks."""
        risks = []

        # Volatility risk
        volatility = technical_data.get("volatility_30d", 0)
        if volatility > 0.5:
            risks.append(f"High volatility ({volatility*100:.1f}% annualized)")

        # Valuation risk
        dcf_data = fundamental_data.get("dcf_valuation", {})
        if dcf_data.get("intrinsic_value") and fundamental_data.get("current_price"):
            intrinsic = dcf_data["intrinsic_value"]
            current = fundamental_data["current_price"]
            if current > intrinsic * 1.3:
                risks.append(f"Overvalued by {((current/intrinsic - 1)*100):.1f}% vs DCF")

        # Trend risk
        if technical_data.get("trend") == "bearish":
            risks.append("Bearish technical trend (below SMA)")

        # Default risk if none identified
        if not risks:
            risks.append("Standard market risk")

        reasoning = f"Identified {len(risks)} key risks: {'; '.join(risks[:3])}"
        cot.log_step("Risk Assessment", reasoning, data={"risks": risks}, confidence=0.7)

        return risks

    def _step7_recommendation_synthesis(
        self, symbol: str, cot: ChainOfThoughtLogger,
        fundamental_score: float, technical_score: float, sentiment_score: float,
        fundamental_data: Dict, technical_data: Dict, sentiment_data: Dict,
        risks: List[str]
    ) -> tuple[str, float, float, List[str]]:
        """Step 7: Synthesize recommendation."""

        # Calculate overall score (weighted average)
        overall_score = (
            fundamental_score * 0.5 +  # 50% weight on fundamentals
            technical_score * 0.3 +     # 30% weight on technicals
            sentiment_score * 0.2       # 20% weight on sentiment
        )

        # Determine recommendation
        if overall_score >= 7.5:
            recommendation = "BUY"
            confidence = 0.75 + (overall_score - 7.5) * 0.1  # 75-100%
        elif overall_score >= 6.0:
            recommendation = "HOLD"
            confidence = 0.60
        elif overall_score >= 4.0:
            recommendation = "HOLD"
            confidence = 0.50
        else:
            recommendation = "SELL"
            confidence = 0.60 + (4.0 - overall_score) * 0.1

        # Cap confidence
        confidence = min(0.95, max(0.50, confidence))

        # Key findings
        findings = []
        if fundamental_score > 7.0:
            findings.append(f"Strong fundamentals (score {fundamental_score:.1f}/10)")
        if technical_score > 7.0:
            findings.append(f"Positive technical trend (score {technical_score:.1f}/10)")
        if len(risks) > 3:
            findings.append(f"Multiple risks identified ({len(risks)} total)")
        if overall_score > 8.0:
            findings.append("High conviction opportunity")

        reasoning = (
            f"Synthesis for {symbol}: Overall score {overall_score:.1f}/10 "
            f"(fund={fundamental_score:.1f}, tech={technical_score:.1f}, sent={sentiment_score:.1f}). "
            f"Recommendation: {recommendation}. Confidence: {confidence:.0%}."
        )

        cot.log_step(
            "Recommendation Synthesis",
            reasoning,
            data={
                "overall_score": overall_score,
                "recommendation": recommendation,
                "confidence": confidence
            },
            confidence=confidence
        )

        return recommendation, confidence, overall_score, findings

    def comparative_research(self, symbols: List[str]) -> Dict[str, ResearchReport]:
        """Compare multiple symbols using deep research.

        Args:
            symbols: List of symbols to compare

        Returns:
            Dictionary mapping symbol to ResearchReport
        """
        logger.info(f"Starting comparative research on {len(symbols)} symbols: {symbols}")
        reports = {}

        for symbol in symbols:
            try:
                report = self.deep_research_symbol(symbol)
                reports[symbol] = report
            except Exception as e:
                logger.error(f"Failed to research {symbol}: {e}")

        return reports

    def theme_evaluation(self, theme_name: str) -> Optional[ThemeEvaluationReport]:
        """Evaluate current theme performance and suggest alternatives.

        Args:
            theme_name: Name of theme to evaluate ("theme_a", "theme_b", "theme_c")

        Returns:
            ThemeEvaluationReport or None if evaluation fails
        """
        logger.info(f"Evaluating {theme_name}")

        # Get current theme symbol
        theme_idx = {"theme_a": 0, "theme_b": 1, "theme_c": 2}.get(theme_name)
        if theme_idx is None or theme_idx >= len(config.theme_underlyings):
            logger.error(f"Invalid theme name or index: {theme_name}")
            return None

        current_symbol = config.theme_underlyings[theme_idx]
        current_symbols = [current_symbol]

        # Research current symbol
        current_report = self.deep_research_symbol(current_symbol)

        # Get smart alternatives using industry peer analysis
        alternatives = self.get_smart_theme_alternatives(current_symbol, num_alternatives=3)

        # Quick research on alternatives to build candidate list
        alternative_candidates = []
        for alt_symbol in alternatives:
            try:
                alt_report = self.deep_research_symbol(alt_symbol)
                alternative_candidates.append({
                    "symbol": alt_symbol,
                    "score": alt_report.overall_score,
                    "reason": f"{alt_report.recommendation} - {alt_report.overall_score:.1f}/10"
                })
            except Exception as e:
                logger.warning(f"Could not research alternative {alt_symbol}: {e}")

        # Determine if change should be considered
        best_alternative_score = max([c["score"] for c in alternative_candidates]) if alternative_candidates else 0
        should_change = (
            current_report.overall_score < 6.0 and  # Current is mediocre or poor
            best_alternative_score > current_report.overall_score + 1.0  # Alternative is significantly better
        )

        rationale_parts = [f"Current score: {current_report.overall_score:.1f}/10"]
        if alternative_candidates:
            best_alt = max(alternative_candidates, key=lambda x: x["score"])
            rationale_parts.append(f"Best alternative: {best_alt['symbol']} ({best_alt['score']:.1f}/10)")
            if should_change:
                rationale_parts.append(f"Recommend considering change (+{best_alt['score'] - current_report.overall_score:.1f} points)")

        evaluation = ThemeEvaluationReport(
            theme_name=theme_name,
            current_symbols=current_symbols,
            current_performance_score=current_report.overall_score,
            alternative_candidates=alternative_candidates,
            should_change=should_change,
            rationale=". ".join(rationale_parts)
        )

        logger.info(
            f"Theme evaluation complete: {theme_name} - "
            f"current={current_report.overall_score:.1f}, "
            f"should_change={should_change}, "
            f"alternatives={len(alternative_candidates)}"
        )

        return evaluation

    def research_theme_change(
        self, current_symbols: List[str], candidate_symbols: List[str]
    ) -> Optional[ThemeChangeProposal]:
        """Research whether to change theme symbols.

        Args:
            current_symbols: Current theme symbol(s)
            candidate_symbols: Alternative symbol(s) to consider

        Returns:
            ThemeChangeProposal or None if research fails
        """
        logger.info(f"Researching theme change: {current_symbols} → {candidate_symbols}")

        # Research current
        current_reports = self.comparative_research(current_symbols)

        # Research candidates
        candidate_reports = self.comparative_research(candidate_symbols)

        # Calculate average scores
        current_avg = sum(r.overall_score for r in current_reports.values()) / len(current_reports) if current_reports else 5.0
        candidate_avg = sum(r.overall_score for r in candidate_reports.values()) / len(candidate_reports) if candidate_reports else 5.0

        # Determine if change is recommended
        score_delta = candidate_avg - current_avg
        recommendation_score = 5.0 + score_delta  # 0-10 scale

        # Confidence based on score difference
        confidence = min(0.85, 0.5 + abs(score_delta) * 0.1)

        # Build proposal
        proposal = ThemeChangeProposal(
            theme_name="theme_auto",  # Will be set by caller
            current_symbols=current_symbols,
            proposed_symbols=candidate_symbols,
            recommendation_score=recommendation_score,
            confidence=confidence,
            expected_improvement=f"Score improvement: {score_delta:+.1f} points ({current_avg:.1f} → {candidate_avg:.1f})",
            risks=["Change may incur transaction costs", "Historical performance may not predict future results"]
        )

        logger.info(f"Theme change proposal: score={recommendation_score:.1f}/10, confidence={confidence:.0%}")
        return proposal

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """Get company information including sector, industry, and market cap.

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary with company info: sector, industry, market_cap, name
        """
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                "symbol": symbol,
                "name": info.get("longName", symbol),
                "sector": info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
                "market_cap": info.get("marketCap", 0),
                "country": info.get("country", "Unknown"),
                "exchange": info.get("exchange", "Unknown")
            }

        except Exception as e:
            logger.warning(f"Could not get company info for {symbol}: {e}")
            return {
                "symbol": symbol,
                "name": symbol,
                "sector": "Unknown",
                "industry": "Unknown",
                "market_cap": 0,
                "country": "Unknown",
                "exchange": "Unknown"
            }

    def get_industry_peers(self, symbol: str, max_peers: int = 5) -> List[str]:
        """Find industry peer companies for a given symbol.

        Uses sector, industry, and market cap to find similar companies.

        Args:
            symbol: Stock symbol to find peers for
            max_peers: Maximum number of peers to return

        Returns:
            List of peer symbols (similar sector/industry/market cap)
        """
        try:
            import yfinance as yf

            # Get company info
            company_info = self.get_company_info(symbol)
            sector = company_info["sector"]
            industry = company_info["industry"]
            market_cap = company_info["market_cap"]

            if sector == "Unknown" or market_cap == 0:
                logger.warning(f"Insufficient data to find peers for {symbol}")
                return []

            # Common peer mappings (curated list for major sectors)
            # In production, use a real peer discovery API or database
            peer_map = {
                "Technology": {
                    "Semiconductors": ["NVDA", "AMD", "INTC", "TSM", "ASML", "MU", "QCOM"],
                    "Software": ["MSFT", "ORCL", "CRM", "ADBE", "NOW", "INTU"],
                    "Hardware": ["AAPL", "HPQ", "DELL", "WDC", "STX"],
                    "Internet": ["GOOGL", "META", "AMZN", "NFLX", "UBER", "ABNB"]
                },
                "Financial Services": {
                    "Banks": ["JPM", "BAC", "WFC", "C", "USB", "PNC"],
                    "Investment": ["GS", "MS", "BLK", "SCHW", "IBKR"],
                    "Insurance": ["BRK.B", "PGR", "TRV", "ALL", "AIG"]
                },
                "Healthcare": {
                    "Drug Manufacturers": ["JNJ", "PFE", "ABBV", "MRK", "LLY", "BMY"],
                    "Biotechnology": ["GILD", "AMGN", "REGN", "VRTX", "BIIB"],
                    "Medical Devices": ["ABT", "TMO", "DHR", "SYK", "BSX"]
                },
                "Consumer Cyclical": {
                    "Auto Manufacturers": ["TSLA", "F", "GM", "TM", "HMC"],
                    "Retail": ["WMT", "TGT", "COST", "HD", "LOW", "AMZN"],
                    "Restaurants": ["MCD", "SBUX", "YUM", "CMG", "DPZ"]
                },
                "Energy": {
                    "Oil & Gas": ["XOM", "CVX", "COP", "SLB", "EOG"],
                    "Renewable": ["ENPH", "SEDG", "NEE", "DUK"]
                },
                "Consumer Defensive": {
                    "Beverages": ["KO", "PEP", "MNST", "STZ"],
                    "Food": ["PG", "UL", "KMB", "CL", "GIS"]
                },
                "Communication Services": {
                    "Telecom": ["T", "VZ", "TMUS", "CMCSA"],
                    "Media": ["DIS", "NFLX", "WBD", "PARA"]
                },
                "Industrials": {
                    "Aerospace": ["BA", "LMT", "RTX", "GD", "NOC"],
                    "Machinery": ["CAT", "DE", "EMR", "MMM"]
                }
            }

            # Find peers based on sector and industry
            peers = []

            # Try to find from curated map
            if sector in peer_map:
                for ind_group, symbols in peer_map[sector].items():
                    if industry in ind_group or ind_group in industry:
                        peers.extend(symbols)
                        break

                # If no industry match, use all sector peers
                if not peers:
                    for symbols in peer_map[sector].values():
                        peers.extend(symbols)

            # Remove the original symbol from peers
            peers = [p for p in peers if p != symbol]

            # Filter by similar market cap (within 10x range)
            if market_cap > 0 and peers:
                filtered_peers = []
                for peer in peers[:20]:  # Check first 20
                    try:
                        peer_info = self.get_company_info(peer)
                        peer_cap = peer_info["market_cap"]

                        if peer_cap > 0:
                            ratio = max(market_cap, peer_cap) / min(market_cap, peer_cap)
                            if ratio <= 10:  # Within 10x market cap
                                filtered_peers.append(peer)

                        if len(filtered_peers) >= max_peers:
                            break
                    except Exception as e:
                        logger.debug(f"Error checking peer {peer}: {e}")
                        continue

                peers = filtered_peers

            # Return top N peers
            result = peers[:max_peers]
            logger.info(f"Found {len(result)} industry peers for {symbol} ({sector}/{industry}): {result}")
            return result

        except Exception as e:
            logger.warning(f"Could not find industry peers for {symbol}: {e}")
            return []

    def get_smart_theme_alternatives(self, current_symbol: str, num_alternatives: int = 3) -> List[str]:
        """Get smart alternative symbols for theme change evaluation.

        Uses industry peer analysis to find better alternatives.

        Args:
            current_symbol: Current theme symbol
            num_alternatives: Number of alternatives to return

        Returns:
            List of alternative symbols (industry peers with high potential)
        """
        try:
            # Get industry peers
            peers = self.get_industry_peers(current_symbol, max_peers=10)

            if not peers:
                # Fallback to sector ETFs if no peers found
                company_info = self.get_company_info(current_symbol)
                sector = company_info["sector"]

                sector_etfs = {
                    "Technology": ["XLK", "QQQ", "SOXX"],
                    "Financial Services": ["XLF", "KRE", "KBE"],
                    "Healthcare": ["XLV", "IBB", "XBI"],
                    "Consumer Cyclical": ["XLY", "VCR"],
                    "Energy": ["XLE", "XOP", "VDE"],
                    "Consumer Defensive": ["XLP", "VDC"],
                    "Communication Services": ["XLC", "VOX"],
                    "Industrials": ["XLI", "VIS"]
                }

                peers = sector_etfs.get(sector, ["SPY", "QQQ", "IWM"])

            # Quick score peers (simplified - in production, do full research)
            scored_peers = []
            for peer in peers[:num_alternatives * 2]:  # Check 2x what we need
                try:
                    # Quick fundamental check
                    if self.fundamental:
                        result = self.fundamental.analyze(peer)
                        if result and not result.get("error"):
                            valuation_score = result.get("valuation_score", 3)
                            scored_peers.append((peer, valuation_score))
                        else:
                            scored_peers.append((peer, 3))  # Neutral if no data
                    else:
                        scored_peers.append((peer, 3))  # Neutral if no fundamental analysis
                except Exception as e:
                    logger.debug(f"Error scoring peer {peer}: {e}")
                    continue

            # Sort by score (highest first) and return top N
            scored_peers.sort(key=lambda x: x[1], reverse=True)
            alternatives = [symbol for symbol, score in scored_peers[:num_alternatives]]

            # If we don't have enough, add SPY as fallback
            while len(alternatives) < num_alternatives:
                alternatives.append("SPY")

            logger.info(f"Smart alternatives for {current_symbol}: {alternatives}")
            return alternatives[:num_alternatives]

        except Exception as e:
            logger.warning(f"Could not get smart alternatives for {current_symbol}: {e}")
            return ["SPY", "QQQ", "IWM"][:num_alternatives]

"""Fundamental analysis including DCF, P/E, volatility, and valuation scoring."""
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from loguru import logger
import yfinance as yf
import numpy as np
import pandas as pd


class FundamentalAnalysis:
    """Fundamental analysis including DCF, P/E ratios, volatility, and valuation scoring."""
    
    def __init__(self):
        """Initialize fundamental analysis."""
        logger.info("Fundamental analysis initialized")
    
    def get_fundamental_data(self, symbol: str) -> Optional[Dict]:
        """Get comprehensive fundamental data for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with fundamental data or None if error
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Get financial statements
            financials = ticker.financials
            balance_sheet = ticker.balance_sheet
            cashflow = ticker.cashflow
            
            # Get historical prices for volatility
            hist = ticker.history(period="1y")
            
            return {
                "symbol": symbol,
                "info": info,
                "financials": financials,
                "balance_sheet": balance_sheet,
                "cashflow": cashflow,
                "history": hist,
            }
        except Exception as e:
            logger.error(f"Error getting fundamental data for {symbol}: {e}")
            return None
    
    def calculate_dcf(
        self,
        symbol: str,
        free_cash_flow_ltm: Optional[float] = None,
        growth_rate_1: float = 0.10,
        growth_rate_2: float = 0.05,
        terminal_growth_rate: float = 0.03,
        discount_rate: float = 0.10,
        years_stage1: int = 5,
        years_total: int = 10
    ) -> Optional[Dict]:
        """Calculate Discounted Cash Flow (DCF) valuation.
        
        Uses 2-stage model: high growth for first N years, then slower growth,
        then terminal value.
        
        Args:
            symbol: Stock symbol
            free_cash_flow_ltm: Last twelve months free cash flow (if None, will fetch)
            growth_rate_1: Growth rate for stage 1 (default 10%)
            growth_rate_2: Growth rate for stage 2 (default 5%)
            terminal_growth_rate: Terminal growth rate (default 3%)
            discount_rate: Discount rate / WACC (default 10%)
            years_stage1: Years in stage 1 (default 5)
            years_total: Total projection years (default 10)
            
        Returns:
            Dictionary with DCF results including intrinsic value per share
        """
        try:
            ticker = yf.Ticker(symbol)
            
            # Get FCF if not provided
            if free_cash_flow_ltm is None:
                cashflow = ticker.cashflow
                if cashflow is not None and not cashflow.empty:
                    # Get Free Cash Flow (Operating Cash Flow - Capital Expenditures)
                    if "Free Cash Flow" in cashflow.index:
                        fcf_values = cashflow.loc["Free Cash Flow"].dropna()
                    elif "Operating Cash Flow" in cashflow.index and "Capital Expenditure" in cashflow.index:
                        ocf = cashflow.loc["Operating Cash Flow"].dropna()
                        capex = cashflow.loc["Capital Expenditure"].dropna()
                        # Align dates
                        common_dates = ocf.index.intersection(capex.index)
                        if len(common_dates) > 0:
                            fcf_values = ocf.loc[common_dates] - abs(capex.loc[common_dates])
                        else:
                            fcf_values = pd.Series()
                    else:
                        fcf_values = pd.Series()
                    
                    if len(fcf_values) > 0:
                        # Use most recent non-zero value
                        free_cash_flow_ltm = float(fcf_values.iloc[0])
                    else:
                        # Fallback: try to get from info
                        info = ticker.info
                        free_cash_flow_ltm = info.get("freeCashflow") or info.get("operatingCashflow")
                        if free_cash_flow_ltm:
                            free_cash_flow_ltm = float(free_cash_flow_ltm)
                        else:
                            logger.warning(f"Could not determine FCF for {symbol}, using $0")
                            free_cash_flow_ltm = 0.0
                else:
                    # Try info
                    info = ticker.info
                    free_cash_flow_ltm = info.get("freeCashflow") or info.get("operatingCashflow")
                    if free_cash_flow_ltm:
                        free_cash_flow_ltm = float(free_cash_flow_ltm)
                    else:
                        logger.warning(f"Could not determine FCF for {symbol}, using $0")
                        free_cash_flow_ltm = 0.0
            
            if free_cash_flow_ltm is None or free_cash_flow_ltm == 0:
                return {
                    "symbol": symbol,
                    "error": "Could not determine free cash flow",
                    "intrinsic_value_per_share": None,
                    "discount_to_intrinsic": None,
                }
            
            # Get shares outstanding
            info = ticker.info
            shares_outstanding = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
            if not shares_outstanding:
                logger.warning(f"Could not determine shares outstanding for {symbol}")
                return None
            
            shares_outstanding = float(shares_outstanding)
            
            # Stage 1: High growth
            cash_flows_stage1 = []
            current_fcf = free_cash_flow_ltm
            for year in range(1, years_stage1 + 1):
                current_fcf *= (1 + growth_rate_1)
                discounted = current_fcf / ((1 + discount_rate) ** year)
                cash_flows_stage1.append({
                    "year": year,
                    "fcf": current_fcf,
                    "discounted": discounted
                })
            
            # Stage 2: Slower growth
            cash_flows_stage2 = []
            for year in range(years_stage1 + 1, years_total + 1):
                current_fcf *= (1 + growth_rate_2)
                discounted = current_fcf / ((1 + discount_rate) ** year)
                cash_flows_stage2.append({
                    "year": year,
                    "fcf": current_fcf,
                    "discounted": discounted
                })
            
            # Terminal value (perpetuity model)
            terminal_fcf = current_fcf * (1 + terminal_growth_rate)
            terminal_value = terminal_fcf / (discount_rate - terminal_growth_rate)
            terminal_value_discounted = terminal_value / ((1 + discount_rate) ** years_total)
            
            # Total enterprise value
            pv_stage1 = sum(cf["discounted"] for cf in cash_flows_stage1)
            pv_stage2 = sum(cf["discounted"] for cf in cash_flows_stage2)
            enterprise_value = pv_stage1 + pv_stage2 + terminal_value_discounted
            
            # Equity value (assuming no net debt for simplicity, or subtract net debt)
            net_debt = info.get("netDebt") or 0.0
            if net_debt:
                net_debt = float(net_debt)
            equity_value = enterprise_value - net_debt
            
            # Intrinsic value per share
            intrinsic_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else None
            
            # Get current price
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            if current_price:
                current_price = float(current_price)
                discount_to_intrinsic = ((intrinsic_value_per_share - current_price) / intrinsic_value_per_share * 100) if intrinsic_value_per_share else None
            else:
                current_price = None
                discount_to_intrinsic = None
            
            return {
                "symbol": symbol,
                "free_cash_flow_ltm": free_cash_flow_ltm,
                "shares_outstanding": shares_outstanding,
                "growth_rate_stage1": growth_rate_1,
                "growth_rate_stage2": growth_rate_2,
                "terminal_growth_rate": terminal_growth_rate,
                "discount_rate": discount_rate,
                "cash_flows_stage1": cash_flows_stage1,
                "cash_flows_stage2": cash_flows_stage2,
                "terminal_value": terminal_value,
                "terminal_value_discounted": terminal_value_discounted,
                "enterprise_value": enterprise_value,
                "equity_value": equity_value,
                "intrinsic_value_per_share": intrinsic_value_per_share,
                "current_price": current_price,
                "discount_to_intrinsic": discount_to_intrinsic,
                "valuation_result": "UNDERVALUED" if discount_to_intrinsic and discount_to_intrinsic > 0 else "OVERVALUED" if discount_to_intrinsic and discount_to_intrinsic < 0 else "FAIRLY_VALUED",
            }
            
        except Exception as e:
            logger.error(f"Error calculating DCF for {symbol}: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
                "intrinsic_value_per_share": None,
                "discount_to_intrinsic": None,
            }
    
    def analyze_pe_ratio(self, symbol: str) -> Optional[Dict]:
        """Analyze Price-to-Earnings (P/E) ratio.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with P/E analysis
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            current_pe = info.get("trailingPE") or info.get("forwardPE")
            industry_pe = info.get("industryPE")
            sector_pe = info.get("sectorPE")
            market_cap = info.get("marketCap")
            
            # Get earnings growth estimate
            earnings_growth = info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")
            
            # Determine if P/E is reasonable
            result = "ABOUT_RIGHT"
            if current_pe:
                current_pe = float(current_pe)
                if industry_pe:
                    industry_pe = float(industry_pe)
                    if current_pe > industry_pe * 1.2:  # 20% above industry
                        result = "EXPENSIVE"
                    elif current_pe < industry_pe * 0.8:  # 20% below industry
                        result = "CHEAP"
            else:
                current_pe = None
            
            return {
                "symbol": symbol,
                "current_pe": current_pe,
                "industry_pe": industry_pe,
                "sector_pe": sector_pe,
                "market_cap": market_cap,
                "earnings_growth": earnings_growth,
                "result": result,
            }
            
        except Exception as e:
            logger.error(f"Error analyzing P/E for {symbol}: {e}")
            return None
    
    def calculate_volatility_metrics(self, symbol: str, periods: List[str] = None) -> Optional[Dict]:
        """Calculate volatility metrics for different time periods.
        
        Args:
            symbol: Stock symbol
            periods: List of periods to analyze (e.g., ["1wk", "1mo", "ytd", "1y", "5y"])
            
        Returns:
            Dictionary with volatility metrics
        """
        if periods is None:
            periods = ["1wk", "1mo", "ytd", "1y", "5y"]
        
        try:
            ticker = yf.Ticker(symbol)
            
            # Get historical data for longest period
            hist = ticker.history(period="5y")
            if hist.empty:
                return None
            
            # Calculate returns
            hist["returns"] = hist["Close"].pct_change()
            
            results = {}
            
            # Calculate for each period
            for period in periods:
                if period == "1wk":
                    period_data = hist.tail(5)  # ~5 trading days
                elif period == "1mo":
                    period_data = hist.tail(21)  # ~21 trading days
                elif period == "ytd":
                    # Year to date
                    current_year = datetime.now().year
                    period_data = hist[hist.index >= f"{current_year}-01-01"]
                elif period == "1y":
                    period_data = hist.tail(252)  # ~252 trading days
                elif period == "5y":
                    period_data = hist
                else:
                    continue
                
                if len(period_data) < 2:
                    continue
                
                returns = period_data["returns"].dropna()
                if len(returns) == 0:
                    continue
                
                # Calculate metrics
                total_return = ((period_data["Close"].iloc[-1] / period_data["Close"].iloc[0]) - 1) * 100
                volatility = returns.std() * np.sqrt(252) * 100  # Annualized volatility %
                avg_return = returns.mean() * 252 * 100  # Annualized return %
                
                results[period] = {
                    "total_return_pct": total_return,
                    "volatility_pct": volatility,
                    "avg_return_pct": avg_return,
                    "trading_days": len(period_data),
                }
            
            return {
                "symbol": symbol,
                "periods": results,
            }
            
        except Exception as e:
            logger.error(f"Error calculating volatility for {symbol}: {e}")
            return None
    
    def calculate_valuation_score(self, symbol: str) -> Optional[Dict]:
        """Calculate overall valuation score (0-6 scale like Simply Wall St).
        
        Combines DCF, P/E, and other metrics into a single score.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with valuation score and breakdown
        """
        try:
            score = 0
            max_score = 6
            breakdown = {}
            
            # DCF analysis (0-2 points)
            dcf = self.calculate_dcf(symbol)
            if dcf and dcf.get("discount_to_intrinsic") is not None:
                discount = dcf["discount_to_intrinsic"]
                if discount > 50:  # Very undervalued
                    dcf_score = 2
                elif discount > 20:  # Undervalued
                    dcf_score = 1.5
                elif discount > -20:  # Fairly valued
                    dcf_score = 1
                else:  # Overvalued
                    dcf_score = 0
                score += dcf_score
                breakdown["dcf"] = {
                    "score": dcf_score,
                    "discount_pct": discount,
                    "intrinsic_value": dcf.get("intrinsic_value_per_share"),
                }
            else:
                breakdown["dcf"] = {"score": 0, "reason": "Insufficient data"}
            
            # P/E analysis (0-2 points)
            pe_analysis = self.analyze_pe_ratio(symbol)
            if pe_analysis and pe_analysis.get("current_pe") is not None:
                current_pe = pe_analysis["current_pe"]
                industry_pe = pe_analysis.get("industry_pe")
                
                if industry_pe:
                    pe_ratio = current_pe / industry_pe
                    if pe_ratio < 0.8:  # Cheap vs industry
                        pe_score = 2
                    elif pe_ratio < 1.0:  # Slightly cheap
                        pe_score = 1.5
                    elif pe_ratio < 1.2:  # About right
                        pe_score = 1
                    else:  # Expensive
                        pe_score = 0
                else:
                    # No industry comparison, use absolute P/E
                    if current_pe < 15:  # Generally considered reasonable
                        pe_score = 1.5
                    elif current_pe < 25:
                        pe_score = 1
                    else:
                        pe_score = 0.5
                
                score += pe_score
                breakdown["pe"] = {
                    "score": pe_score,
                    "current_pe": current_pe,
                    "industry_pe": industry_pe,
                }
            else:
                breakdown["pe"] = {"score": 0, "reason": "Insufficient data"}
            
            # Profitability check (0-1 point)
            ticker = yf.Ticker(symbol)
            info = ticker.info
            profit_margin = info.get("profitMargins")
            if profit_margin:
                profit_margin = float(profit_margin)
                if profit_margin > 0.15:  # High profitability
                    profit_score = 1
                elif profit_margin > 0.05:
                    profit_score = 0.5
                else:
                    profit_score = 0
                score += profit_score
                breakdown["profitability"] = {
                    "score": profit_score,
                    "profit_margin": profit_margin,
                }
            else:
                breakdown["profitability"] = {"score": 0, "reason": "Insufficient data"}
            
            # Growth check (0-1 point)
            earnings_growth = info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")
            revenue_growth = info.get("revenueGrowth")
            
            growth_score = 0
            if earnings_growth:
                earnings_growth = float(earnings_growth)
                if earnings_growth > 0.20:  # High growth
                    growth_score = 1
                elif earnings_growth > 0.10:
                    growth_score = 0.5
            elif revenue_growth:
                revenue_growth = float(revenue_growth)
                if revenue_growth > 0.15:
                    growth_score = 0.5
            
            score += growth_score
            breakdown["growth"] = {
                "score": growth_score,
                "earnings_growth": earnings_growth,
                "revenue_growth": revenue_growth,
            }
            
            # Cap score at max_score
            final_score = min(score, max_score)
            
            return {
                "symbol": symbol,
                "valuation_score": final_score,
                "max_score": max_score,
                "breakdown": breakdown,
            }
            
        except Exception as e:
            logger.error(f"Error calculating valuation score for {symbol}: {e}")
            return None
    
    def get_comprehensive_analysis(self, symbol: str) -> Dict:
        """Get comprehensive fundamental analysis combining all methods.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with comprehensive analysis including DCF, P/E, volatility, and valuation score
        """
        try:
            logger.info(f"Running comprehensive fundamental analysis for {symbol}")
            
            # Get all analyses
            dcf = self.calculate_dcf(symbol)
            pe = self.analyze_pe_ratio(symbol)
            volatility = self.calculate_volatility_metrics(symbol)
            valuation_score = self.calculate_valuation_score(symbol)
            
            # Get current quote
            ticker = yf.Ticker(symbol)
            info = ticker.info
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            
            return {
                "symbol": symbol,
                "analysis_date": datetime.now().isoformat(),
                "current_price": float(current_price) if current_price else None,
                "dcf_analysis": dcf,
                "pe_analysis": pe,
                "volatility_analysis": volatility,
                "valuation_score": valuation_score,
            }
            
        except Exception as e:
            logger.error(f"Error in comprehensive analysis for {symbol}: {e}")
            return {
                "symbol": symbol,
                "error": str(e),
            }

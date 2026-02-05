"""Tests for fundamental analysis (DCF, P/E, volatility, valuation score)."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np

from src.fundamental_analysis import FundamentalAnalysis


@pytest.fixture
def analyzer():
    """FundamentalAnalysis instance."""
    return FundamentalAnalysis()


# --- DCF (production-like: explicit FCF and shares, no yfinance for math) ---


def test_calculate_dcf_with_explicit_fcf_no_yfinance(analyzer):
    """DCF with explicit FCF and shares uses only math (no yfinance for valuation)."""
    # We need to avoid ticker.info for shares/price when we pass explicit FCF;
    # production code still fetches ticker for shares_outstanding and current_price.
    with patch("src.fundamental_analysis.yf") as mock_yf:
        ticker = Mock()
        ticker.info = {
            "sharesOutstanding": 100_000_000,
            "currentPrice": 20.0,
            "netDebt": 0,
        }
        mock_yf.Ticker.return_value = ticker

        result = analyzer.calculate_dcf(
            "TEST",
            free_cash_flow_ltm=50_000_000,
            growth_rate_1=0.10,
            growth_rate_2=0.05,
            terminal_growth_rate=0.03,
            discount_rate=0.10,
            years_stage1=5,
            years_total=10,
        )

    assert result is not None
    assert result["symbol"] == "TEST"
    assert result["free_cash_flow_ltm"] == 50_000_000
    assert result["shares_outstanding"] == 100_000_000
    assert result["intrinsic_value_per_share"] is not None
    assert result["intrinsic_value_per_share"] > 0
    assert result["current_price"] == 20.0
    assert result["discount_to_intrinsic"] is not None
    # Intrinsic > price => positive discount => UNDERVALUED
    if result["intrinsic_value_per_share"] > 20:
        assert result["valuation_result"] == "UNDERVALUED"
    assert "cash_flows_stage1" in result
    assert "cash_flows_stage2" in result
    assert "terminal_value" in result


def test_calculate_dcf_zero_fcf_returns_error_dict(analyzer):
    """DCF with zero FCF returns dict with error and no intrinsic value."""
    with patch("src.fundamental_analysis.yf") as mock_yf:
        ticker = Mock()
        ticker.info = {"sharesOutstanding": 100_000_000}
        mock_yf.Ticker.return_value = ticker

        result = analyzer.calculate_dcf("TEST", free_cash_flow_ltm=0)

    assert result["symbol"] == "TEST"
    assert result.get("error") or result.get("intrinsic_value_per_share") is None
    assert result.get("intrinsic_value_per_share") is None


def test_calculate_dcf_exception_returns_error_dict(analyzer):
    """DCF on exception returns dict with error key."""
    with patch("src.fundamental_analysis.yf") as mock_yf:
        mock_yf.Ticker.side_effect = Exception("API error")

        result = analyzer.calculate_dcf(
            "FAIL",
            free_cash_flow_ltm=10_000_000,
        )

    assert result["symbol"] == "FAIL"
    assert "error" in result
    assert result.get("intrinsic_value_per_share") is None


# --- P/E ---


def test_analyze_pe_ratio_production_shape(analyzer):
    """P/E analysis returns production shape (symbol, current_pe, industry_pe, result)."""
    with patch("src.fundamental_analysis.yf") as mock_yf:
        ticker = Mock()
        ticker.info = {
            "trailingPE": 27.45,
            "industryPE": 20.37,
            "sectorPE": 21.0,
            "marketCap": 10_000_000_000,
            "earningsGrowth": 0.05,
        }
        mock_yf.Ticker.return_value = ticker

        result = analyzer.analyze_pe_ratio("GME")

    assert result is not None
    assert result["symbol"] == "GME"
    assert result["current_pe"] == 27.45
    assert result["industry_pe"] == 20.37
    assert result["sector_pe"] == 21.0
    assert result["result"] in ("ABOUT_RIGHT", "EXPENSIVE", "CHEAP")
    # 27.45 > 20.37 * 1.2 => EXPENSIVE
    assert result["result"] == "EXPENSIVE"


def test_analyze_pe_ratio_no_pe_returns_about_right(analyzer):
    """When no P/E in info, result is ABOUT_RIGHT and current_pe is None."""
    with patch("src.fundamental_analysis.yf") as mock_yf:
        ticker = Mock()
        ticker.info = {}
        mock_yf.Ticker.return_value = ticker

        result = analyzer.analyze_pe_ratio("NOPE")

    assert result["symbol"] == "NOPE"
    assert result["current_pe"] is None
    assert result["result"] == "ABOUT_RIGHT"


def test_analyze_pe_ratio_exception_returns_none(analyzer):
    """P/E on exception returns None."""
    with patch("src.fundamental_analysis.yf") as mock_yf:
        mock_yf.Ticker.side_effect = Exception("fail")

        result = analyzer.analyze_pe_ratio("FAIL")

    assert result is None


# --- Volatility ---


def test_calculate_volatility_metrics_production_shape(analyzer):
    """Volatility returns symbol and periods dict with total_return_pct, volatility_pct."""
    with patch("src.fundamental_analysis.yf") as mock_yf:
        # 252 days of history
        idx = pd.date_range(end=pd.Timestamp.now(), periods=252, freq="B")
        np.random.seed(42)
        close = 100 * np.exp(np.cumsum(np.random.randn(252) * 0.01))
        hist = pd.DataFrame({"Close": close}, index=idx)
        ticker = Mock()
        ticker.history.return_value = hist
        mock_yf.Ticker.return_value = ticker

        result = analyzer.calculate_volatility_metrics("TEST", periods=["1y"])

    assert result is not None
    assert result["symbol"] == "TEST"
    assert "periods" in result
    assert "1y" in result["periods"]
    p = result["periods"]["1y"]
    assert "total_return_pct" in p
    assert "volatility_pct" in p
    assert "trading_days" in p
    assert p["trading_days"] == 252


def test_calculate_volatility_metrics_empty_history_returns_none(analyzer):
    """Empty history returns None."""
    with patch("src.fundamental_analysis.yf") as mock_yf:
        ticker = Mock()
        ticker.history.return_value = pd.DataFrame()
        mock_yf.Ticker.return_value = ticker

        result = analyzer.calculate_volatility_metrics("EMPTY")

    assert result is None


# --- Valuation score ---


def test_calculate_valuation_score_production_shape(analyzer):
    """Valuation score returns symbol, valuation_score, max_score, breakdown."""
    with patch.object(analyzer, "calculate_dcf") as mock_dcf:
        with patch.object(analyzer, "analyze_pe_ratio") as mock_pe:
            with patch("src.fundamental_analysis.yf") as mock_yf:
                mock_dcf.return_value = {
                    "discount_to_intrinsic": 30.0,
                    "intrinsic_value_per_share": 50.0,
                }
                mock_pe.return_value = {"current_pe": 15.0, "industry_pe": 20.0}
                ticker = Mock()
                ticker.info = {"profitMargins": 0.08, "earningsGrowth": 0.12}
                mock_yf.Ticker.return_value = ticker

                result = analyzer.calculate_valuation_score("TEST")

    assert result is not None
    assert result["symbol"] == "TEST"
    assert result["max_score"] == 6
    assert 0 <= result["valuation_score"] <= 6
    assert "breakdown" in result
    assert "dcf" in result["breakdown"]
    assert "pe" in result["breakdown"]
    assert "profitability" in result["breakdown"]
    assert "growth" in result["breakdown"]


# --- Comprehensive analysis ---


def test_get_comprehensive_analysis_production_shape(analyzer):
    """Comprehensive analysis returns symbol, analysis_date, dcf_analysis, pe_analysis, etc."""
    with patch.object(analyzer, "calculate_dcf") as mock_dcf:
        with patch.object(analyzer, "analyze_pe_ratio") as mock_pe:
            with patch.object(analyzer, "calculate_volatility_metrics") as mock_vol:
                with patch.object(analyzer, "calculate_valuation_score") as mock_score:
                    with patch("src.fundamental_analysis.yf") as mock_yf:
                        mock_dcf.return_value = {"intrinsic_value_per_share": 100.0, "discount_to_intrinsic": 25.0}
                        mock_pe.return_value = {"current_pe": 18.0}
                        mock_vol.return_value = {"symbol": "GME", "periods": {"1y": {"total_return_pct": 10.0}}}
                        mock_score.return_value = {"valuation_score": 3.0, "max_score": 6, "breakdown": {}}
                        ticker = Mock()
                        ticker.info = {"currentPrice": 75.0}
                        mock_yf.Ticker.return_value = ticker

                        result = analyzer.get_comprehensive_analysis("GME")

    assert result["symbol"] == "GME"
    assert "analysis_date" in result
    assert result["current_price"] == 75.0
    assert result["dcf_analysis"] is not None
    assert result["pe_analysis"] is not None
    assert result["volatility_analysis"] is not None
    assert result["valuation_score"] is not None


def test_get_comprehensive_analysis_exception_returns_error_dict(analyzer):
    """On exception, comprehensive analysis returns dict with error."""
    with patch.object(analyzer, "calculate_dcf", side_effect=Exception("fail")):
        result = analyzer.get_comprehensive_analysis("FAIL")

    assert result["symbol"] == "FAIL"
    assert "error" in result

"""Comprehensive SDK data serializer for AI consumption.

This module ensures ALL fields from public_api_sdk response objects are properly
extracted and formatted for AI comprehension. It recursively serializes SDK objects
to dictionaries, handling all data types including Decimals, datetimes, enums, etc.
"""
import json
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from enum import Enum
from loguru import logger


def serialize_sdk_object(obj: Any, max_depth: int = 10, current_depth: int = 0) -> Any:
    """Recursively serialize SDK objects to JSON-serializable Python types.
    
    This function extracts ALL attributes from SDK response objects, ensuring
    no data is lost when passing to AI. It handles:
    - Nested objects
    - Lists/arrays
    - Decimals -> float
    - Datetimes/dates -> ISO strings
    - Enums -> their values
    - None values
    - Primitive types
    
    Args:
        obj: The SDK object to serialize
        max_depth: Maximum recursion depth to prevent infinite loops
        current_depth: Current recursion depth
        
    Returns:
        JSON-serializable Python object (dict, list, str, int, float, bool, None)
    """
    if current_depth >= max_depth:
        # Expected for deeply nested SDK responses (option chains, portfolio); avoid flooding logs
        logger.debug(f"Max depth {max_depth} reached during SDK serialization")
        return str(obj)
    
    # Handle None
    if obj is None:
        return None
    
    # Handle primitive types
    if isinstance(obj, (str, int, float, bool)):
        return obj
    
    # Handle Decimal -> float
    if isinstance(obj, Decimal):
        return float(obj)
    
    # Handle datetime/date -> ISO string
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    
    # Handle Enum -> value
    if isinstance(obj, Enum):
        return obj.value if hasattr(obj, 'value') else str(obj)
    
    # Handle lists/tuples
    if isinstance(obj, (list, tuple)):
        return [serialize_sdk_object(item, max_depth, current_depth + 1) for item in obj]
    
    # Handle dictionaries
    if isinstance(obj, dict):
        return {
            str(k): serialize_sdk_object(v, max_depth, current_depth + 1)
            for k, v in obj.items()
        }
    
    # Handle SDK objects (objects with attributes)
    if hasattr(obj, '__dict__') or hasattr(obj, '__slots__'):
        result = {}
        
        # Get all attributes
        attrs = {}
        if hasattr(obj, '__dict__'):
            attrs.update(obj.__dict__)
        
        # Also check for properties and methods that might be data fields
        for attr_name in dir(obj):
            # Skip private/magic methods
            if attr_name.startswith('_'):
                continue
            
            # Skip methods
            if callable(getattr(obj, attr_name, None)):
                continue
            
            # Get attribute value
            try:
                attr_value = getattr(obj, attr_name, None)
                # Only include if not already in __dict__ and it's not a method
                if attr_name not in attrs and not callable(attr_value):
                    attrs[attr_name] = attr_value
            except Exception:
                continue
        
        # Serialize all attributes
        for key, value in attrs.items():
            try:
                serialized = serialize_sdk_object(value, max_depth, current_depth + 1)
                result[key] = serialized
            except Exception as e:
                logger.debug(f"Failed to serialize attribute {key}: {e}")
                result[key] = str(value)
        
        return result
    
    # Fallback: convert to string
    return str(obj)


def extract_quote_data(quote_obj: Any) -> Dict[str, Any]:
    """Extract comprehensive data from a Quote object.
    
    Args:
        quote_obj: Quote object from SDK
        
    Returns:
        Dictionary with all quote fields
    """
    data = serialize_sdk_object(quote_obj)
    
    # Ensure standard fields are present with fallbacks
    result = {
        "symbol": data.get("symbol") or (data.get("instrument", {}).get("symbol") if isinstance(data.get("instrument"), dict) else None),
        "instrument_type": data.get("instrument_type") or (data.get("instrument", {}).get("type") if isinstance(data.get("instrument"), dict) else None),
        "last": _safe_float(data.get("last")),
        "bid": _safe_float(data.get("bid")),
        "ask": _safe_float(data.get("ask")),
        "volume": _safe_int(data.get("volume")),
        "high": _safe_float(data.get("high")),
        "low": _safe_float(data.get("low")),
        "open": _safe_float(data.get("open")),
        "close": _safe_float(data.get("close")),
        "change": _safe_float(data.get("change")),
        "change_percent": _safe_float(data.get("change_percent")),
        "timestamp": data.get("timestamp") or data.get("time") or data.get("updated_at"),
    }
    
    # Add all other fields that might exist
    for key, value in data.items():
        if key not in result:
            result[key] = value
    
    # Calculate mid if bid/ask available
    if result["bid"] is not None and result["ask"] is not None:
        result["mid"] = (result["bid"] + result["ask"]) / 2.0
    elif result["last"] is not None:
        result["mid"] = result["last"]
    
    # Calculate spread
    if result["bid"] is not None and result["ask"] is not None:
        result["spread"] = result["ask"] - result["bid"]
        if result["mid"]:
            result["spread_percent"] = (result["spread"] / result["mid"]) * 100 if result["mid"] > 0 else None
    
    return result


def extract_option_contract_data(contract_obj: Any) -> Dict[str, Any]:
    """Extract comprehensive data from an option contract object.
    
    Args:
        contract_obj: Option contract object from SDK (call or put)
        
    Returns:
        Dictionary with all option contract fields
    """
    data = serialize_sdk_object(contract_obj)
    
    # Extract symbol from nested instrument if needed
    symbol = data.get("symbol")
    if not symbol and isinstance(data.get("instrument"), dict):
        symbol = data.get("instrument", {}).get("symbol")
    elif not symbol and hasattr(contract_obj, 'instrument'):
        try:
            symbol = getattr(contract_obj.instrument, 'symbol', None)
        except (AttributeError, TypeError) as e:
            logger.debug(f"Could not extract symbol from instrument: {e}")
    
    result = {
        "symbol": symbol,
        "strike": _safe_float(data.get("strike")),
        "expiration": data.get("expiration") or data.get("expiration_date"),
        "option_type": data.get("option_type") or data.get("type") or ("CALL" if "C" in str(symbol or "") else "PUT"),
        "bid": _safe_float(data.get("bid")),
        "ask": _safe_float(data.get("ask")),
        "last": _safe_float(data.get("last")),
        "volume": _safe_int(data.get("volume")),
        "open_interest": _safe_int(data.get("open_interest")),
        "implied_volatility": _safe_float(data.get("implied_volatility") or data.get("iv")),
        "delta": _safe_float(data.get("delta")),
        "gamma": _safe_float(data.get("gamma")),
        "theta": _safe_float(data.get("theta")),
        "vega": _safe_float(data.get("vega")),
        "intrinsic_value": _safe_float(data.get("intrinsic_value")),
        "extrinsic_value": _safe_float(data.get("extrinsic_value")),
        "time_value": _safe_float(data.get("time_value")),
    }
    
    # Add all other fields
    for key, value in data.items():
        if key not in result:
            result[key] = value
    
    # Calculate mid
    if result["bid"] is not None and result["ask"] is not None:
        result["mid"] = (result["bid"] + result["ask"]) / 2.0
    elif result["last"] is not None:
        result["mid"] = result["last"]
    
    # Calculate spread
    if result["bid"] is not None and result["ask"] is not None:
        result["spread"] = result["ask"] - result["bid"]
        if result["mid"]:
            result["spread_percent"] = (result["spread"] / result["mid"]) * 100 if result["mid"] > 0 else None
    
    return result


def extract_option_chain_data(chain_obj: Any) -> Dict[str, Any]:
    """Extract comprehensive data from an OptionChainResponse object.
    
    Args:
        chain_obj: OptionChainResponse object from SDK
        
    Returns:
        Dictionary with all chain data including calls and puts
    """
    data = serialize_sdk_object(chain_obj)
    
    # Extract calls and puts
    calls_raw = data.get("calls") or []
    puts_raw = data.get("puts") or []
    
    # If calls/puts are objects, serialize them
    calls = []
    if calls_raw:
        if isinstance(calls_raw, list):
            calls = [extract_option_contract_data(c) for c in calls_raw]
        else:
            calls = [extract_option_contract_data(calls_raw)]
    
    puts = []
    if puts_raw:
        if isinstance(puts_raw, list):
            puts = [extract_option_contract_data(p) for p in puts_raw]
        else:
            puts = [extract_option_contract_data(puts_raw)]
    
    result = {
        "underlying": data.get("underlying") or data.get("instrument", {}).get("symbol") if isinstance(data.get("instrument"), dict) else None,
        "expiration": data.get("expiration") or data.get("expiration_date"),
        "spot_price": _safe_float(data.get("spot_price") or data.get("underlying_price") or data.get("spot")),
        "calls": calls,
        "puts": puts,
        "call_count": len(calls),
        "put_count": len(puts),
    }
    
    # Add all other fields
    for key, value in data.items():
        if key not in result and key not in ("calls", "puts"):
            result[key] = value
    
    return result


def extract_portfolio_position_data(pos_obj: Any) -> Dict[str, Any]:
    """Extract comprehensive data from a PortfolioPosition object.
    
    Args:
        pos_obj: PortfolioPosition object from SDK
        
    Returns:
        Dictionary with all position fields
    """
    data = serialize_sdk_object(pos_obj)
    
    # Extract nested instrument data
    instrument_data = data.get("instrument", {})
    if not isinstance(instrument_data, dict):
        instrument_data = serialize_sdk_object(instrument_data) if instrument_data else {}
    
    # Extract cost basis data
    cost_basis_data = data.get("cost_basis", {})
    if not isinstance(cost_basis_data, dict):
        cost_basis_data = serialize_sdk_object(cost_basis_data) if cost_basis_data else {}
    
    result = {
        "symbol": instrument_data.get("symbol") or data.get("symbol"),
        "instrument_type": instrument_data.get("type") or data.get("instrument_type"),
        "quantity": _safe_int(data.get("quantity")),
        "unit_cost": _safe_float(cost_basis_data.get("unit_cost")),
        "total_cost": _safe_float(cost_basis_data.get("total_cost")),
        "average_cost": _safe_float(cost_basis_data.get("average_cost") or cost_basis_data.get("unit_cost")),
        "market_value": _safe_float(data.get("market_value")),
        "unrealized_pnl": _safe_float(data.get("unrealized_pnl") or data.get("unrealized_gain_loss")),
        "unrealized_pnl_percent": _safe_float(data.get("unrealized_pnl_percent")),
    }
    
    # Add all other fields
    for key, value in data.items():
        if key not in result:
            result[key] = value
    
    # Add instrument fields
    for key, value in instrument_data.items():
        if key not in result:
            result[f"instrument_{key}"] = value
    
    # Add cost basis fields
    for key, value in cost_basis_data.items():
        if key not in result:
            result[f"cost_basis_{key}"] = value
    
    return result


def extract_greeks_data(greeks_obj: Any) -> Dict[str, Any]:
    """Extract comprehensive Greeks data.
    
    Args:
        greeks_obj: Greeks object from SDK
        
    Returns:
        Dictionary with all Greeks fields
    """
    data = serialize_sdk_object(greeks_obj)
    
    result = {
        "delta": _safe_float(data.get("delta")),
        "gamma": _safe_float(data.get("gamma")),
        "theta": _safe_float(data.get("theta")),
        "vega": _safe_float(data.get("vega")),
        "rho": _safe_float(data.get("rho")),
    }
    
    # Add all other fields
    for key, value in data.items():
        if key not in result:
            result[key] = value
    
    return result


def extract_portfolio_data(portfolio_obj: Any) -> Dict[str, Any]:
    """Extract comprehensive portfolio data.
    
    Args:
        portfolio_obj: Portfolio object from SDK
        
    Returns:
        Dictionary with all portfolio fields
    """
    data = serialize_sdk_object(portfolio_obj)
    
    # Extract positions
    positions_raw = data.get("positions") or []
    positions = []
    if positions_raw:
        if isinstance(positions_raw, list):
            positions = [extract_portfolio_position_data(p) for p in positions_raw]
        else:
            positions = [extract_portfolio_position_data(positions_raw)]
    
    # Extract equity (handle list format)
    equity_raw = data.get("equity")
    equity = 0.0
    if isinstance(equity_raw, list):
        equity = sum(_safe_float(x.get("value") if isinstance(x, dict) else x) or 0.0 for x in equity_raw)
    else:
        equity = _safe_float(equity_raw) or 0.0
    
    # Extract buying power (handle object format)
    buying_power_raw = data.get("buying_power")
    buying_power = 0.0
    if isinstance(buying_power_raw, dict):
        buying_power = _safe_float(buying_power_raw.get("buying_power") or buying_power_raw.get("cash_only_buying_power")) or 0.0
    elif isinstance(buying_power_raw, list):
        buying_power = sum(_safe_float(x.get("buying_power") if isinstance(x, dict) else x) or 0.0 for x in buying_power_raw)
    else:
        buying_power = _safe_float(buying_power_raw) or 0.0
    
    result = {
        "equity": equity,
        "buying_power": buying_power,
        "cash": _safe_float(data.get("cash")),
        "positions": positions,
        "position_count": len(positions),
    }
    
    # Add all other fields
    for key, value in data.items():
        if key not in result and key not in ("positions", "equity", "buying_power"):
            result[key] = value
    
    return result


def _safe_float(value: Any) -> Optional[float]:
    """Safely convert value to float."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, str):
            return float(value.strip())
        if hasattr(value, '__float__'):
            return float(value)
        return None
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    """Safely convert value to int."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            return int(value.strip())
        if hasattr(value, '__int__'):
            return int(value)
        return None
    except (TypeError, ValueError):
        return None

"""Configuration for high-convexity portfolio trading bot."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, computed_field
from typing import List


class HighConvexityConfig(BaseSettings):
    """Configuration for high-convexity portfolio strategy."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix=""
    )
    
    # API Configuration
    api_secret_key: str = Field(..., validation_alias="PUBLIC_SECRET_KEY")
    
    # Strategy Universe (env: comma-separated "UMC,TE,AMPX")
    theme_underlyings_csv: str = Field(
        default="UMC,TE,AMPX",
        env="THEME_UNDERLYINGS",
    )

    @computed_field
    @property
    def theme_underlyings(self) -> List[str]:
        s = getattr(self, "theme_underlyings_csv", "UMC,TE,AMPX") or "UMC,TE,AMPX"
        return [x.strip() for x in s.split(",") if x.strip()] or ["UMC", "TE", "AMPX"]

    moonshot_symbol: str = Field(default="GME.WS", env="MOONSHOT_SYMBOL")
    
    # Target Allocations (as percentages of equity)
    theme_a_target: float = Field(0.35, env="THEME_A_TARGET")  # UMC: 35%
    theme_b_target: float = Field(0.35, env="THEME_B_TARGET")  # TE: 35%
    theme_c_target: float = Field(0.15, env="THEME_C_TARGET")  # AMPX: 15% (optional)
    moonshot_target: float = Field(0.20, env="MOONSHOT_TARGET")  # 20%
    moonshot_max: float = Field(0.30, env="MOONSHOT_MAX")  # Hard cap: 30%
    cash_minimum: float = Field(0.20, env="CASH_MINIMUM")  # Minimum: 20%
    
    # Option Selection Rules
    option_dte_min: int = Field(60, env="OPTION_DTE_MIN")
    option_dte_max: int = Field(120, env="OPTION_DTE_MAX")
    option_dte_fallback_min: int = Field(45, env="OPTION_DTE_FALLBACK_MIN")
    option_dte_fallback_max: int = Field(150, env="OPTION_DTE_FALLBACK_MAX")
    strike_range_min: float = Field(1.00, env="STRIKE_RANGE_MIN")  # ATM
    strike_range_max: float = Field(1.10, env="STRIKE_RANGE_MAX")  # 10% OTM
    max_bid_ask_spread_pct: float = Field(0.12, env="MAX_BID_ASK_SPREAD_PCT")  # 12%
    min_open_interest: int = Field(50, env="MIN_OPEN_INTEREST")
    min_volume: int = Field(10, env="MIN_VOLUME")
    
    # Roll Rules
    roll_trigger_dte: int = Field(60, env="ROLL_TRIGGER_DTE")
    roll_target_dte: int = Field(90, env="ROLL_TARGET_DTE")
    max_roll_debit_pct: float = Field(0.35, env="MAX_ROLL_DEBIT_PCT")  # 35% of current value
    max_roll_debit_absolute: float = Field(100.0, env="MAX_ROLL_DEBIT_ABSOLUTE")  # $100
    
    # Profit/Loss Rules
    take_profit_100_pct: float = Field(1.00, env="TAKE_PROFIT_100_PCT")  # +100%
    take_profit_200_pct: float = Field(2.00, env="TAKE_PROFIT_200_PCT")  # +200%
    take_profit_100_close_pct: float = Field(0.50, env="TAKE_PROFIT_100_CLOSE_PCT")  # Close 50%
    stop_loss_drawdown_pct: float = Field(-0.40, env="STOP_LOSS_DRAWDOWN_PCT")  # -40%
    stop_loss_underlying_pct: float = Field(-0.05, env="STOP_LOSS_UNDERLYING_PCT")  # 5% below strike
    close_if_dte_lt: int = Field(30, env="CLOSE_IF_DTE_LT")
    close_if_otm_dte_lt: int = Field(30, env="CLOSE_IF_OTM_DTE_LT")
    
    # Execution
    max_trades_per_day: int = Field(5, env="MAX_TRADES_PER_DAY")
    order_price_offset_pct: float = Field(0.0, env="ORDER_PRICE_OFFSET_PCT")  # Mid price offset
    order_poll_timeout_seconds: int = Field(300, env="ORDER_POLL_TIMEOUT_SECONDS")  # 5 minutes
    order_poll_interval_seconds: int = Field(5, env="ORDER_POLL_INTERVAL_SECONDS")
    
    # Signals
    use_sma_filter: bool = Field(True, env="USE_SMA_FILTER")
    sma_period: int = Field(20, env="SMA_PERIOD")
    manual_mode_only: bool = Field(False, env="MANUAL_MODE_ONLY")
    
    # Trading Hours
    trade_during_extended_hours: bool = Field(False, env="TRADE_EXTENDED_HOURS")
    
    # Rebalancing
    rebalance_time_hour: int = Field(9, env="REBALANCE_TIME_HOUR")  # 9 AM ET
    rebalance_time_minute: int = Field(30, env="REBALANCE_TIME_MINUTE")  # 9:30 AM ET
    rebalance_timezone: str = Field("America/New_York", env="REBALANCE_TIMEZONE")
    
    # Guardrails
    kill_switch_drawdown_pct: float = Field(0.25, env="KILL_SWITCH_DRAWDOWN_PCT")  # 25%
    kill_switch_lookback_days: int = Field(30, env="KILL_SWITCH_LOOKBACK_DAYS")
    kill_switch_cooldown_days: int = Field(5, env="KILL_SWITCH_COOLDOWN_DAYS")
    
    # Database
    db_path: str = Field("data/trading_bot.db", env="DB_PATH")
    
    # Logging
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_file: str = Field("logs/high_convexity_bot.log", env="LOG_FILE")
    
    # Dry Run Mode
    dry_run: bool = Field(False, env="DRY_RUN")

    # Telegram + AI (optional; required when running Telegram bot)
    telegram_bot_token: str = Field("", env="TELEGRAM_BOT_TOKEN")
    openai_api_key: str = Field("", env="OPENAI_API_KEY")
    allowed_telegram_user_ids: str = Field(
        "",
        env="ALLOWED_TELEGRAM_USER_IDS",
        description="Comma-separated Telegram user IDs allowed to trade / change config (empty = allow all for read-only)",
    )

    @computed_field
    @property
    def allowed_telegram_user_id_list(self) -> List[int]:
        s = getattr(self, "allowed_telegram_user_ids", "") or ""
        if not s.strip():
            return []
        return [int(x.strip()) for x in s.split(",") if x.strip()]


# Global config instance
config = HighConvexityConfig()

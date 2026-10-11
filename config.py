from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    binance_mode: str = "testnet"
    allow_mainnet: bool = False
    binance_testnet_api_key: str = ""
    binance_testnet_api_secret: str = ""
    binance_mainnet_api_key: str = ""
    binance_mainnet_api_secret: str = ""
    database_url: str = "sqlite+aiosqlite:///./scalper.db"
    cors_origins: str = "http://localhost:3000"
    dashboard_token: str = ""
    bot_enabled: bool = False
    target_margin_usdt: float = 10.0
    leverage: int = 5
    risk_per_trade_pct: float = 1.0
    daily_loss_limit_pct: float = 3.0
    max_open_positions: int = 1
    breakout_lookback: int = 20
    stop_atr_multiplier: float = 1.5
    take_profit_r_multiple: float = 1.2
    max_symbols: int = 0

    @property
    def base_url(self):
        return "https://demo-fapi.binance.com" if self.binance_mode.lower() == "testnet" else "https://fapi.binance.com"
    @property
    def ws_url(self):
        return "wss://demo-fstream.binance.com/stream?streams=" if self.binance_mode.lower() == "testnet" else "wss://fstream.binance.com/stream?streams="
    @property
    def api_key(self):
        return self.binance_testnet_api_key if self.binance_mode.lower() == "testnet" else self.binance_mainnet_api_key
    @property
    def api_secret(self):
        return self.binance_testnet_api_secret if self.binance_mode.lower() == "testnet" else self.binance_mainnet_api_secret

settings = Settings()

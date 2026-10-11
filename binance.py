import hashlib, hmac, time
from urllib.parse import urlencode
import httpx
from .config import settings

class BinanceError(RuntimeError): pass
class BinanceClient:
    def __init__(self):
        self.base = settings.base_url
        self.key = settings.api_key
        self.secret = settings.api_secret
        self.http = httpx.AsyncClient(timeout=12.0, headers={"X-MBX-APIKEY": self.key} if self.key else {})
    def ready(self):
        return bool(self.key and self.secret)
    async def request(self, method, path, params=None, signed=False):
        params = dict(params or {})
        if signed:
            if not self.ready(): raise BinanceError("API credentials are not configured for the selected mode")
            params["timestamp"] = int(time.time() * 1000)
            params.setdefault("recvWindow", 5000)
            query = urlencode(params, doseq=True)
            params["signature"] = hmac.new(self.secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        r = await self.http.request(method, self.base + path, params=params)
        try: data = r.json()
        except Exception: data = {"msg": r.text}
        if r.is_error: raise BinanceError(f"Binance HTTP {r.status_code}: {data}")
        if isinstance(data, dict) and "code" in data and data.get("code", 0) < 0:
            raise BinanceError(f"Binance error: {data}")
        return data
    async def close(self): await self.http.aclose()
    async def exchange_info(self): return await self.request("GET", "/fapi/v1/exchangeInfo")
    async def ticker_24h(self): return await self.request("GET", "/fapi/v1/ticker/24hr")
    async def klines(self, symbol, interval="1m", limit=100): return await self.request("GET", "/fapi/v1/klines", {"symbol":symbol,"interval":interval,"limit":limit})
    async def account(self): return await self.request("GET", "/fapi/v2/account", signed=True)
    async def positions(self): return await self.request("GET", "/fapi/v2/positionRisk", signed=True)
    async def open_orders(self): return await self.request("GET", "/fapi/v1/openOrders", signed=True)
    async def set_leverage(self, symbol, leverage): return await self.request("POST", "/fapi/v1/leverage", {"symbol":symbol,"leverage":leverage}, signed=True)
    async def order(self, **params): return await self.request("POST", "/fapi/v1/order", params, signed=True)
    async def cancel_all(self, symbol): return await self.request("DELETE", "/fapi/v1/allOpenOrders", {"symbol":symbol}, signed=True)

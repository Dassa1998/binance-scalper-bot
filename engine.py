import asyncio, json, time, uuid
import websockets
from .config import settings
from .binance import BinanceClient, BinanceError
from .strategy import breakout_signal
from .db import log_event

class TradingEngine:
    def __init__(self):
        self.client=BinanceClient(); self.running=False; self.task=None
        self.symbols=[]; self.tickers={}; self.exchange_filters={}; self.last_signal={}; self.last_error=""
        self.started_at=None; self.daily_start_balance=None; self.daily_key=None; self.lock=asyncio.Lock()
    async def initialize_symbols(self):
        info=await self.client.exchange_info()
        eligible=[]
        for item in info.get("symbols",[]):
            if item.get("status") != "TRADING" or item.get("quoteAsset") != "USDT" or item.get("contractType") != "PERPETUAL": continue
            filters={f.get("filterType"):f for f in item.get("filters",[])}
            lot=filters.get("LOT_SIZE",{}); price=filters.get("PRICE_FILTER",{}); notional=filters.get("MIN_NOTIONAL",filters.get("NOTIONAL",{}))
            self.exchange_filters[item["symbol"]]={"stepSize":float(lot.get("stepSize",0.001)),"minQty":float(lot.get("minQty",0)),"tickSize":float(price.get("tickSize",0.01)),"minNotional":float(notional.get("notional",notional.get("minNotional",5)) or 5)}
            eligible.append(item["symbol"])
        self.symbols=eligible[:settings.max_symbols] if settings.max_symbols and settings.max_symbols>0 else eligible
        return self.symbols
    async def ticker_loop(self):
        # Binance combined-stream connections support up to 200 streams each; scan all loaded pairs in chunks.
        while self.running:
            try:
                if not self.symbols: await self.initialize_symbols()
                chunks=[self.symbols[i:i+200] for i in range(0,len(self.symbols),200)]
                await asyncio.gather(*(self._stream_chunk(chunk) for chunk in chunks))
            except Exception as e:
                self.last_error=f"Market stream reconnecting: {str(e)[:180]}"
                await log_event("websocket_reconnect",self.last_error,"warning")
                await asyncio.sleep(3)
    async def _stream_chunk(self, symbols):
        while self.running:
            try:
                streams="/".join(f"{s.lower()}@markPrice@1s" for s in symbols)
                async with websockets.connect(settings.ws_url+streams, ping_interval=20, ping_timeout=20, close_timeout=5, max_size=2**22) as ws:
                    async for msg in ws:
                        if not self.running: break
                        packet=json.loads(msg); d=packet.get("data",packet)
                        if d.get("s") and d.get("p"):
                            self.tickers[d["s"]]={"price":float(d["p"]),"time":int(d.get("E",time.time()*1000)),"fundingRate":d.get("r")}
            except Exception as e:
                if self.running:
                    self.last_error=f"Market stream reconnecting: {str(e)[:180]}"
                    await log_event("websocket_reconnect",self.last_error,"warning")
                    await asyncio.sleep(3)
    async def _snapshot(self):
        if not self.client.ready(): return {"connected":False,"message":"Set server-side API credentials for the selected mode."}
        account=await self.client.account(); positions=await self.client.positions(); orders=await self.client.open_orders()
        assets=account.get("assets",[]); usdt=next((a for a in assets if a.get("asset")=="USDT"),{})
        open_positions=[]
        for p in positions:
            amt=float(p.get("positionAmt",0) or 0)
            if amt:
                open_positions.append({"symbol":p["symbol"],"side":"LONG" if amt>0 else "SHORT","quantity":abs(amt),"entryPrice":float(p.get("entryPrice",0) or 0),"markPrice":float(p.get("markPrice",0) or 0),"unrealizedPnl":float(p.get("unRealizedProfit",0) or 0),"leverage":int(p.get("leverage",settings.leverage) or settings.leverage),"liquidationPrice":float(p.get("liquidationPrice",0) or 0),"marginType":p.get("marginType")})
        return {"connected":True,"mode":settings.binance_mode,"walletBalance":float(account.get("totalWalletBalance",0) or 0),"equityBalance":float(account.get("totalMarginBalance",account.get("totalWalletBalance",0)) or 0),"availableBalance":float(account.get("availableBalance",0) or 0),"totalUnrealizedPnl":float(account.get("totalUnrealizedProfit",0) or 0),"usdtBalance":float(usdt.get("walletBalance",0) or 0),"positions":open_positions,"openOrdersCount":len(orders),"assets":assets,"updateTime":int(time.time()*1000)}
    async def snapshot(self):
        try:
            acc=await self._snapshot()
            if not acc.get("connected"): return {**acc,"mode":settings.binance_mode,"running":self.running,"symbolsCount":len(self.symbols),"tickers":self.tickers,"lastError":self.last_error}
            return {**acc,"running":self.running,"symbolsCount":len(self.symbols),"tickers":self.tickers,"lastError":self.last_error,"settings":{"targetMarginUsdt":settings.target_margin_usdt,"leverage":settings.leverage,"riskPct":settings.risk_per_trade_pct,"dailyLossLimitPct":settings.daily_loss_limit_pct}}
        except Exception as e:
            self.last_error=str(e)[:400]
            return {"connected":False,"mode":settings.binance_mode,"running":self.running,"symbolsCount":len(self.symbols),"tickers":self.tickers,"lastError":self.last_error}
    async def start(self):
        if settings.binance_mode.lower() not in ("testnet","mainnet"): raise ValueError("BINANCE_MODE must be testnet or mainnet")
        if settings.binance_mode.lower()=="mainnet" and not settings.allow_mainnet: raise ValueError("Mainnet blocked: set ALLOW_MAINNET=true deliberately after Testnet validation")
        if not self.client.ready(): raise ValueError("Missing API credentials for selected mode")
        if self.running: return
        await self.initialize_symbols()
        self.running=True; self.started_at=time.time(); self.task=asyncio.create_task(self.run_loop())
        asyncio.create_task(self.ticker_loop())
        await log_event("bot_started",f"Bot started in {settings.binance_mode}; {len(self.symbols)} USDT perpetual symbols")
    async def stop(self):
        self.running=False
        if self.task:
            self.task.cancel(); self.task=None
        await log_event("bot_stopped","Bot stopped. Existing exchange positions/orders are NOT automatically closed.","warning")
    async def run_loop(self):
        while self.running:
            try:
                snap=await self._snapshot()
                if not snap.get("connected"): raise RuntimeError("Account snapshot unavailable")
                today=time.strftime("%Y-%m-%d",time.gmtime())
                if self.daily_key!=today:
                    self.daily_key=today; self.daily_start_balance=snap.get("equityBalance",snap["walletBalance"])
                if self.daily_start_balance and (self.daily_start_balance-snap.get("equityBalance",snap["walletBalance"]))/self.daily_start_balance*100 >= settings.daily_loss_limit_pct:
                    await log_event("risk_halt","Daily loss limit reached; bot paused. Existing positions are not auto-closed.","error")
                    self.running=False; break
                if len(snap["positions"]) >= settings.max_open_positions:
                    await asyncio.sleep(4); continue
                # Sequentially scan symbols; keep request rate conservative.
                for symbol in self.symbols:
                    if not self.running: break
                    # Only trade symbols with a recent mark-price update.
                    tick=self.tickers.get(symbol)
                    if not tick or time.time()*1000-tick["time"]>15000: continue
                    # Avoid duplicate position/order per symbol; global max position also checked above.
                    pos=await self.client.request("GET","/fapi/v2/positionRisk",{"symbol":symbol},signed=True)
                    if any(abs(float(p.get("positionAmt",0) or 0))>0 for p in pos): continue
                    orders=await self.client.request("GET","/fapi/v1/openOrders",{"symbol":symbol},signed=True)
                    if orders: continue
                    raw=await self.client.klines(symbol,"1m",max(100,settings.breakout_lookback+30))
                    signal=breakout_signal(raw,settings.breakout_lookback,settings.stop_atr_multiplier)
                    if not signal: continue
                    bar=signal["bar_time"]
                    if self.last_signal.get(symbol)==bar: continue
                    self.last_signal[symbol]=bar
                    await self.execute_signal(symbol,signal,snap["walletBalance"],snap["availableBalance"])
                    break
                    await asyncio.sleep(0.08)
                await asyncio.sleep(1.5)
            except asyncio.CancelledError: raise
            except Exception as e:
                self.last_error=str(e)[:400]; await log_event("engine_error",self.last_error,"error"); await asyncio.sleep(4)
    async def execute_signal(self,symbol,signal,wallet,available):
        async with self.lock:
            filters=self.exchange_filters.get(symbol,{})
            await self.client.set_leverage(symbol,settings.leverage)
            entry=float(signal["entry"]); stop=float(signal["stop"]); take=float(signal["take"])
            distance=abs(entry-stop)
            if distance<=0: return
            risk_cash=max(0.0,wallet*settings.risk_per_trade_pct/100)
            qty_by_risk=risk_cash/distance
            qty_by_margin=settings.target_margin_usdt*settings.leverage/entry
            qty=min(qty_by_risk,qty_by_margin,(available*settings.leverage*0.95)/entry)
            step=filters.get("stepSize",0.001); qty=(qty//step)*step if step>0 else qty
            min_qty=filters.get("minQty",0.0); min_notional=filters.get("minNotional",5.0)
            if qty<min_qty or qty*entry<min_notional:
                await log_event("signal_skipped",f"Sizing below exchange minimum: qty={qty:.8f}, notional={qty*entry:.4f}","warning",symbol); return
            side=signal["side"]; exit_side="SELL" if side=="BUY" else "BUY"
            client_id="scalp_"+uuid.uuid4().hex[:24]
            try:
                # Client order id makes retries/audit easier; we do not blindly retry uncertain entry submissions.
                result=await self.client.order(symbol=symbol,side=side,type="MARKET",quantity=f"{qty:.8f}",newClientOrderId=client_id,newOrderRespType="RESULT")
                filled=float(result.get("executedQty",qty) or qty)
                avg=float(result.get("avgPrice",entry) or entry)
                # Re-anchor protection to actual average fill. Binance conditional orders use STOP_MARKET / TAKE_PROFIT_MARKET.
                tick=filters.get("tickSize",0.01) or 0.01
                stop = avg - distance if side == "BUY" else avg + distance
                take = avg + distance*settings.take_profit_r_multiple if side == "BUY" else avg - distance*settings.take_profit_r_multiple
                stop_price=round(round(stop/tick)*tick,8); take_price=round(round(take/tick)*tick,8)
                await self.client.order(symbol=symbol,side=exit_side,type="STOP_MARKET",stopPrice=f"{stop_price:.8f}",closePosition="true",workingType="MARK_PRICE",priceProtect="TRUE")
                await self.client.order(symbol=symbol,side=exit_side,type="TAKE_PROFIT_MARKET",stopPrice=f"{take_price:.8f}",closePosition="true",workingType="MARK_PRICE",priceProtect="TRUE")
                await log_event("entry_filled",f"Entry order accepted; orderId={result.get('orderId')}; qty={filled}; avgPrice={avg}; stop={stop_price}; take={take_price}","info",symbol)
            except Exception as e:
                await log_event("order_protection_error",f"Protection/entry error: {str(e)[:500]}. Attempting reduce-only flatten; verify position on exchange.","error",symbol)
                try:
                    p=await self.client.request("GET","/fapi/v2/positionRisk",{"symbol":symbol},signed=True)
                    amt=sum(float(x.get("positionAmt",0) or 0) for x in p)
                    if abs(amt)>0:
                        await self.client.order(symbol=symbol,side="SELL" if amt>0 else "BUY",type="MARKET",quantity=f"{abs(amt):.8f}",reduceOnly="true",newClientOrderId="scalp_flat_"+uuid.uuid4().hex[:20])
                except Exception as flatten_error:
                    await log_event("flatten_failed",f"URGENT: automatic flatten failed: {flatten_error}","error",symbol)
                self.running=False
engine=TradingEngine()

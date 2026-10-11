from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, desc
from .config import settings
from .db import init_db, Session, Event
from .engine import engine
from .binance import BinanceError

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await engine.stop()
    await engine.client.close()
app=FastAPI(title="Binance Futures Scalper API",version="0.1.0",lifespan=lifespan)
async def require_dashboard_token(authorization: str | None = Header(default=None)):
    # Reads are also protected when a token is configured. Without one, bot controls are blocked.
    expected = settings.dashboard_token
    if not expected:
        raise HTTPException(503, "DASHBOARD_TOKEN is not configured; set a strong token in server environment")
    if authorization != f"Bearer {expected}":
        raise HTTPException(401, "Dashboard token missing or invalid")
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()],allow_credentials=False,allow_methods=["GET","POST"],allow_headers=["*"])
@app.get("/health")
def health(): return {"ok":True,"mode":settings.binance_mode,"mainnetAllowed":settings.allow_mainnet,"warning":"Unauthenticated starter API; do not expose publicly before adding authentication."}
@app.get("/api/status", dependencies=[Depends(require_dashboard_token)])
async def status(): return await engine.snapshot()
@app.get("/api/markets", dependencies=[Depends(require_dashboard_token)])
async def markets():
    try:
        if not engine.symbols: await engine.initialize_symbols()
        # Return live stream tickers only, not fabricated prices.
        return {"count":len(engine.symbols),"symbols":[{"symbol":s,"price":engine.tickers.get(s,{}).get("price"),"time":engine.tickers.get(s,{}).get("time")} for s in engine.symbols]}
    except Exception as e: raise HTTPException(502,str(e))
@app.get("/api/events", dependencies=[Depends(require_dashboard_token)])
async def events(limit: int=50):
    async with Session() as s:
        rows=(await s.execute(select(Event).order_by(desc(Event.id)).limit(max(1,min(limit,200))))).scalars().all()
        return [{"id":r.id,"createdAt":r.created_at.isoformat() if r.created_at else None,"level":r.level,"kind":r.kind,"symbol":r.symbol,"message":r.message,"pnl":r.pnl} for r in rows]
@app.post("/api/bot/start", dependencies=[Depends(require_dashboard_token)])
async def start():
    try: await engine.start(); return {"ok":True,"running":True,"mode":settings.binance_mode}
    except (ValueError,BinanceError) as e: raise HTTPException(400,str(e))
    except Exception as e: raise HTTPException(502,str(e))
@app.post("/api/bot/stop", dependencies=[Depends(require_dashboard_token)])
async def stop(): await engine.stop(); return {"ok":True,"running":False,"note":"Stops new entries only. Existing positions and orders remain on Binance; manage them in the exchange if needed."}
@app.post("/api/account/reconcile", dependencies=[Depends(require_dashboard_token)])
async def reconcile():
    try: return await engine.snapshot()
    except Exception as e: raise HTTPException(502,str(e))

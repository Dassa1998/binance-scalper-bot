from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, DateTime, Text, func
from .config import settings

url = settings.database_url
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
engine = create_async_engine(url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    level: Mapped[str] = mapped_column(String(16), default="info")
    kind: Mapped[str] = mapped_column(String(48))
    symbol: Mapped[str] = mapped_column(String(24), default="")
    message: Mapped[str] = mapped_column(Text)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
async def log_event(kind: str, message: str, level="info", symbol="", pnl=0.0):
    try:
        async with Session() as session:
            session.add(Event(kind=kind, message=message[:2000], level=level, symbol=symbol, pnl=float(pnl or 0)))
            await session.commit()
    except Exception:
        pass

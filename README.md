# Binance USDⓈ-M Futures Scalper (Testnet-first)

A starter project for a real exchange-connected bot. It uses live Binance market data, signed Futures REST requests for account/order actions, FastAPI, PostgreSQL, and a responsive Next.js dashboard. **It is not a profit guarantee and has not been live-money validated.** Start on Testnet and inspect every order before enabling real funds.

## Safety defaults
- `BINANCE_MODE=testnet`; the backend refuses mainnet trading unless `ALLOW_MAINNET=true` and the mode is explicitly `mainnet`.
- API secrets are server-side environment variables only. Never put keys in frontend variables, source control, screenshots, or chat. Create a key with Futures permissions only and withdrawals disabled; use IP restrictions when possible.
- Bot starts stopped. Start it from the dashboard only after setting credentials and verifying testnet.
- Default sizing is **10 USDT margin x 5 leverage** (about 50 USDT notional before filters), but exchange quantity/notional filters may reject some symbols. Planned risk cap is 1% of wallet balance; the bot uses the tighter of risk sizing and target-margin sizing.
- Stop-loss and take-profit are sent as exchange conditional orders after entry. There is a small execution window between entry and protective orders; use Testnet first. If protective orders fail, the bot attempts to flatten the position and halts.
- One position at a time globally; one-way mode assumed. Do not use hedge mode without adapting the code.

## Architecture
- `backend`: FastAPI REST API, signed Binance Futures client, WebSocket market stream, breakout strategy, risk checks, SQLAlchemy event persistence.
- `frontend`: Next.js mobile-friendly dashboard that polls actual backend snapshots; no fake account data.
- `docker-compose.yml`: local backend + frontend + PostgreSQL.
- Railway: deploy backend and frontend as separate services from this repository; provision PostgreSQL and set variables below.

## Local setup
1. Install Docker Desktop or Docker Engine + Compose.
2. Copy `.env.example` to `.env` and add **Testnet** API credentials from the Binance Futures Demo/Testnet environment. Never use mainnet keys for Testnet.
3. Run `docker compose up --build`.
4. Open `http://localhost:3000`. Backend health/docs: `http://localhost:8000/health` and `/docs`.
5. Confirm mode is `testnet`, balance is returned by Binance (or marked unavailable if no valid credentials), and symbols are loaded from Binance `exchangeInfo`.
6. Start the bot in the dashboard. Test entries, exits, reconnects, stop button, and database persistence on Testnet before considering live trading.

## Environment variables
See `.env.example`. For mainnet, set `BINANCE_MODE=mainnet`, `ALLOW_MAINNET=true`, and provide a separate mainnet API key/secret. Keep `BOT_ENABLED=false` until you intentionally start it. Never expose secrets as `NEXT_PUBLIC_*`.

## Railway deployment
1. Push this folder to a private GitHub repository.
2. Create a Railway project and add a PostgreSQL service. Railway docs: https://docs.railway.com/databases/postgresql
3. Add a backend service rooted at `backend`, deploy with its Dockerfile, and set `DATABASE_URL` to Railway's Postgres reference variable. Set `CORS_ORIGINS` to the frontend's public URL.
4. Add a frontend service rooted at `frontend`, set `NEXT_PUBLIC_API_URL` to the backend public URL (no trailing slash), and expose port 3000.
5. Set backend secrets through Railway Variables only. Check logs, `/health`, exchange connectivity and Testnet behavior before starting the bot.
6. Keep the backend as a continuously running service. Configure alerts/monitoring and confirm reconnect/reconciliation behavior after redeploys.

Railway's free/usage-based availability and quotas can change; do not assume an always-on production trading worker is free. A hosting outage can interrupt strategy decisions, though exchange-side protective orders remain at Binance if accepted.

## Important limitations / next hardening steps
This is an auditable starter, not a turnkey guaranteed-profit system. It does not claim any win rate. Before live trading, add independent code review, comprehensive tests, authentication on the dashboard/API, HTTPS-only deployment, API rate-limit monitoring, alerting, and a staged mainnet canary with tiny risk. The API requires a strong `DASHBOARD_TOKEN` for all `/api/*` routes; enter it in the dashboard. `/health` remains public and reveals only service mode/status. Use HTTPS, keep the token private, and restrict public access where possible.

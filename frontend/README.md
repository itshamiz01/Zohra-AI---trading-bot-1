# Zohra AI — Trading Bot Frontend

The standalone web frontend for the Zohra AI trading bot: the "ZOHRA AI OS // COMMAND CENTER" dashboard (`index.html`, copied from `zohra/api/dashboard.html` in the backend package).

It is deployed as its own Vercel project (static hosting) and talks to the FastAPI backend through the rewrites in `vercel.json`:

- `/api/*` → proxied to the backend project (`zohra-ai-trading-bot` on Vercel)
- `/static/*` → dashboard scripts/assets served by the backend
- The trading engine itself (MetaTrader 5) runs on the owner's Windows machine; this frontend is the always-on public face of the tool.

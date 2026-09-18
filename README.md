# Smart Money Flows Tracker

Three lenses on where Nansen-labeled smart money is moving — built for the Nansen Meridian Buildathon.

**The core idea:** a signal is strongest when *independent* wallets agree. One whale aping into a token is noise; five smart-money wallets from different Nansen cohorts that never trade together suddenly buying the same token is a pattern.

## The three lenses

1. **Consensus Radar** — tokens where multiple independent smart-money wallets are accumulating. Score = buyer breadth × label diversity × buy time-dispersion × conviction. Wallets that never agree suddenly agreeing is the signal.
2. **Exit Whisperer** — tokens smart money is quietly distributing. Score = seller breadth × sell value × outflow acceleration (24h pace vs 7d pace), with a day-by-day smart-holdings chart showing the bleed.
3. **Rotation Map** — where smart capital is migrating: 7d netflows aggregated by chain and by sector, from the same seed data (zero extra API calls).

## Pipeline

`scanner.py` (pure stdlib, ~20 Nansen API calls per scan):

1. `smart_traders_and_funds_netflow` — tokens with the largest 7d smart-money inflows and outflows
2. `smart_traders_and_funds_dex_trades` — per-token smart buys/sells; independence scored from buyer count, distinct Nansen label cohorts, and first-buy time dispersion
3. `smart_traders_and_funds_historical_token_balances` — smart-holdings history for top exits

The dashboard at `web/` is a static Next.js export reading `web/public/data/latest.json`. A GitHub Actions workflow (`.github/workflows/scan.yml`) rescans every 12 hours and commits fresh data.

## Run locally

```bash
export NANSEN_API_KEY=...   # or run where the Nansen credential helper exists
python scanner.py --out web/public/data/latest.json
cd web && npm install && npm run dev
```

Analytical signals, not financial advice.

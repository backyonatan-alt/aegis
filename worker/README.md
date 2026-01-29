# Aegis Data Worker

Cloudflare Worker (Python) that powers the data pipeline for [usstrikeradar.com](https://usstrikeradar.com).

Replaces the old GitHub Actions + `update_data.py` approach. A single Worker handles both serving `data.json` to the frontend and running the scheduled data pipeline.

## Architecture

```
  Cron (every 30 min)          User browser
        |                           |
        v                           v
  CF Worker (Python)          CF Worker (Python)
  on_scheduled() handler      on_fetch() handler
        |                           |
        v                           v
   Fetch 6 APIs              Read from R2
        |                           |
        v                           v
   Write to R2              Return JSON + cache headers
   "data.json"              (CDN caches for 5 min)
```

- `on_fetch()` — intercepts `usstrikeradar.com/data.json`, reads from R2, returns with `Cache-Control: public, max-age=60, s-maxage=300`
- `on_scheduled()` — runs every 30 minutes via cron trigger, fetches all APIs, calculates risk scores, writes updated JSON to R2
- All other paths pass through to the origin (current hosting)

## Prerequisites

- [Node.js](https://nodejs.org/) (v18+)
- A Cloudflare account with the domain `usstrikeradar.com` proxied (orange cloud DNS)
- An [OpenWeatherMap API key](https://openweathermap.org/api)

## Setup

```bash
# Install wrangler globally (or use npx)
npm install -g wrangler

# Authenticate with Cloudflare
wrangler login

# Create the R2 bucket
wrangler r2 bucket create aegis-data
```

## Local Development

1. Create `worker/.dev.vars` with your secrets:

   ```
   OPENWEATHER_API_KEY=your_key_here
   ```

2. Start the dev server:

   ```bash
   cd worker
   npx wrangler dev --test-scheduled
   ```

3. In a separate terminal, trigger the scheduled handler to populate data:

   ```bash
   curl http://localhost:8787/__scheduled?cron=*%2F30+*+*+*+*
   ```

4. Fetch the result:

   ```bash
   curl http://localhost:8787/data.json
   ```

Logs print directly to your terminal during local dev — you'll see each API fetch, risk calculation, and final totals.

## Viewing Logs

**Local dev** — logs stream to stdout in your terminal when running `wrangler dev`.

**Production** — use `wrangler tail` to stream live logs:

```bash
cd worker
npx wrangler tail
```

Or view historical logs in the Cloudflare Dashboard under **Workers & Pages > aegis-data-worker > Logs**.

## Deployment

```bash
cd worker
npx wrangler deploy
```

After deploying, set the secret:

```bash
npx wrangler secret put OPENWEATHER_API_KEY
# Paste your key when prompted
```

Seed the R2 bucket with existing data (optional, the next cron run will populate it):

```bash
npx wrangler r2 object put aegis-data/data.json --file ../frontend/data.json
```

## Verify

```bash
# Check the live endpoint
curl https://usstrikeradar.com/data.json

# Stream live logs
cd worker && npx wrangler tail
```

## Project Structure

```
worker/
├── wrangler.toml          # Worker configuration (name, R2 binding, cron, route)
├── pyproject.toml          # Python dependencies (httpx)
├── .dev.vars               # Local dev secrets (gitignored)
├── README.md               # This file
└── src/
    ├── __init__.py
    ├── entry.py            # Worker entrypoint (on_fetch + on_scheduled)
    ├── fetchers.py         # Async API fetchers (Polymarket, News, Aviation, etc.)
    ├── risk.py             # Risk calculation + history management
    └── constants.py        # Shared constants (keywords, ICAO ranges, etc.)
```

## Configuration

All configuration lives in `wrangler.toml`:

| Setting | Value | Purpose |
|---|---|---|
| `name` | `aegis-data-worker` | Worker name in Cloudflare dashboard |
| `main` | `src/entry.py` | Python entrypoint |
| `compatibility_flags` | `["python_workers"]` | Enable Python runtime |
| `crons` | `["*/30 * * * *"]` | Run every 30 minutes |
| `r2_buckets` | `DATA_BUCKET` -> `aegis-data` | R2 storage binding |
| `routes` | `usstrikeradar.com/data.json` | Intercept only this path |

## Secrets

| Name | Where to set | Purpose |
|---|---|---|
| `OPENWEATHER_API_KEY` | `wrangler secret put` (prod) / `.dev.vars` (local) | Tehran weather data |

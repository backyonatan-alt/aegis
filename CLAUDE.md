# Aegis Strike Radar - Development Notes

## Architecture Overview

### Frontend
- Static site served from `frontend/`
- Fetches data from `https://api.usstrikeradar.com/api/data`
- Key files:
  - `frontend/js/data.js` - API endpoints and data fetching
  - `frontend/js/chart.js` - "72 Hour Risk Trends" chart using `total_risk.history`
  - `frontend/js/display.js` - Dashboard rendering
  - `frontend/data.json` - Fallback/seed data with historical risk points

### Backend (Go)
- Location: `backend/`
- Deployed to GCP instance: `aegis-worker` (zone: `us-central1-a`)
- Service: systemd unit `aegis.service`
- Binary: `/usr/local/bin/aegis`
- Config: `/etc/aegis/env` (contains DATABASE_URL and API keys)
- Repo on server: `/home/hanan/aegis`

### Data Pipeline
- `backend/internal/pipeline/pipeline.go` - Orchestrates fetch → calculate → store
- `backend/internal/risk/history.go` - Manages signal histories and total risk history
- `backend/internal/risk/calculator.go` - Risk score calculations
- Pipeline runs periodically, fetching from external APIs and storing snapshots

### Database
- PostgreSQL
- Main table: `snapshots` (stores JSON response with history)
- History is accumulated over time from previous snapshots

## Common Issues & Solutions

### "72 Hour Risk Trends" chart empty or showing single point
**Cause:** Database has insufficient history data (e.g., after fresh deployment)
**Solution:** Seed the database with `frontend/data.json`:
```bash
gcloud compute ssh aegis-worker --zone=us-central1-a --command="cd /home/hanan/aegis && sudo bash -c 'source /etc/aegis/env && cat frontend/data.json | jq -c . | psql \"\$DATABASE_URL\" -c \"INSERT INTO snapshots (response) VALUES (\\\$\\\$\$(cat)\\\$\\\$)\"'"
```
Then restart the service to clear cache:
```bash
gcloud compute ssh aegis-worker --zone=us-central1-a --command="sudo systemctl restart aegis"
```

### Backend not reflecting DB changes
**Cause:** In-memory cache serves stale data
**Solution:** Restart the service: `sudo systemctl restart aegis`

## Useful Commands

```bash
# SSH to server
gcloud compute ssh aegis-worker --zone=us-central1-a

# Check service status
gcloud compute ssh aegis-worker --zone=us-central1-a --command="sudo systemctl status aegis"

# View service logs
gcloud compute ssh aegis-worker --zone=us-central1-a --command="sudo journalctl -u aegis -f"

# Check API response
curl -s https://api.usstrikeradar.com/api/data | jq '.total_risk'

# Restart service
gcloud compute ssh aegis-worker --zone=us-central1-a --command="sudo systemctl restart aegis"
```

## Data Flow

1. `pipeline.Run()` loads previous snapshot from DB for history continuity
2. Fetches data from external APIs (news, aviation, weather, polymarket, etc.)
3. `risk.Calculate()` computes risk scores
4. `risk.UpdateHistory()` appends new points to history arrays
5. Snapshot saved to DB and cached in memory
6. Frontend fetches from `/api/data` endpoint
7. Chart renders `total_risk.history` array (needs multiple points for 72h view)

## Signal History
- Each signal (news, flight, tanker, etc.) maintains a rolling history of 20 points
- `total_risk.history` stores timestamped points, pinned every 12 hours
- History is essential for the "72 Hour Risk Trends" visualization

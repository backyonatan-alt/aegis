"""Cloudflare Worker entrypoint for the Aegis data pipeline.

Two handlers:
- fetch(): Serves data.json from R2 with cache headers.
- scheduled(): Runs the full data pipeline and writes to R2.
"""

import asyncio
import json
import logging

from workers import WorkerEntrypoint, Response

from constants import R2_KEY
from fetchers import (
    fetch_aviation_data,
    fetch_news_intel,
    fetch_pentagon_data,
    fetch_polymarket_odds,
    fetch_tanker_activity,
    fetch_weather_data,
)
from risk import calculate_risk_scores, update_history

# Configure logging — Cloudflare captures stdout/stderr and shows it in
# Workers Logs / `wrangler tail`.  In local dev (`wrangler dev`) it prints
# straight to your terminal.
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("aegis")


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        """Serve data.json from R2 with cache headers."""
        log.info("Serving data.json from R2")
        obj = await self.env.DATA_BUCKET.get(R2_KEY)

        if obj is None:
            log.warning("data.json not found in R2")
            return Response(
                json.dumps({"error": "data not found"}),
                status=404,
                headers={"Content-Type": "application/json"},
            )

        body = await obj.text()
        log.info("Served %d bytes", len(body))
        return Response(
            body,
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "public, max-age=60, s-maxage=300",
                "Access-Control-Allow-Origin": "*",
            },
        )

    async def scheduled(self, controller):
        """Run the full data pipeline: fetch APIs, calculate risks, write to R2."""
        log.info("=" * 50)
        log.info("SCHEDULED RUN STARTING")
        log.info("=" * 50)

        # 1. Read existing data from R2 (preserve history)
        current_data = {}
        try:
            obj = await self.env.DATA_BUCKET.get(R2_KEY)
            if obj is not None:
                text = await obj.text()
                current_data = json.loads(text)
                log.info("Loaded existing data from R2 (%d bytes)", len(text))
            else:
                log.info("No existing data in R2, starting fresh")
        except Exception as e:
            log.warning("Failed to read existing data from R2: %s", e)
            current_data = {}

        # 2. Compute Pentagon data (no API call)
        pentagon_data = fetch_pentagon_data()

        # 3. Fetch 4 independent APIs in parallel
        api_key = getattr(self.env, "OPENWEATHER_API_KEY", "")

        polymarket_result, news_result, aviation_result, weather_result = (
            await asyncio.gather(
                fetch_polymarket_odds(),
                fetch_news_intel(),
                fetch_aviation_data(),
                fetch_weather_data(api_key),
                return_exceptions=True,
            )
        )

        # Convert exceptions to None and log them
        for name, result in [
            ("Polymarket", polymarket_result),
            ("News", news_result),
            ("Aviation", aviation_result),
            ("Weather", weather_result),
        ]:
            if isinstance(result, Exception):
                log.error("%s fetch raised exception: %s", name, result)

        if isinstance(polymarket_result, Exception):
            polymarket_result = None
        if isinstance(news_result, Exception):
            news_result = None
        if isinstance(aviation_result, Exception):
            aviation_result = None
        if isinstance(weather_result, Exception):
            weather_result = None

        # 4. Sleep for OpenSky rate limit, then fetch tanker data
        log.info("Waiting 2s for OpenSky rate limit...")
        await asyncio.sleep(2)
        tanker_result = await fetch_tanker_activity()

        # Use previous data as fallback for any failed fetches
        polymarket_data = polymarket_result or current_data.get("polymarket", {}).get("raw_data", {})
        news_data = news_result or current_data.get("news", {}).get("raw_data", {})
        aviation_data = aviation_result or current_data.get("flight", {}).get("raw_data", {})
        weather_data = weather_result or current_data.get("weather", {}).get("raw_data", {})
        tanker_data = tanker_result or current_data.get("tanker", {}).get("raw_data", {})

        fallback_used = []
        if polymarket_result is None:
            fallback_used.append("polymarket")
        if news_result is None:
            fallback_used.append("news")
        if aviation_result is None:
            fallback_used.append("aviation")
        if weather_result is None:
            fallback_used.append("weather")
        if tanker_result is None:
            fallback_used.append("tanker")
        if fallback_used:
            log.warning("Using previous data as fallback for: %s", ", ".join(fallback_used))

        # 5. Calculate all risk scores
        scores = calculate_risk_scores(
            news_intel=news_data,
            aviation=aviation_data,
            tanker=tanker_data,
            weather=weather_data,
            polymarket=polymarket_data,
            pentagon_data=pentagon_data,
        )

        # 6. Update history and build final JSON
        raw = {
            "news": news_data,
            "flight": aviation_data,
            "tanker": tanker_data,
            "weather": weather_data,
            "polymarket": polymarket_data,
            "pentagon": pentagon_data,
        }
        final_data = update_history(current_data, scores, raw)

        # 7. Write to R2
        payload = json.dumps(final_data, indent=2)
        await self.env.DATA_BUCKET.put(R2_KEY, payload)

        log.info("=" * 50)
        log.info("DATA COLLECTION COMPLETE")
        log.info("=" * 50)
        log.info("Total Risk: %d%%", scores["total_risk"])
        log.info("Written %d bytes to R2", len(payload))

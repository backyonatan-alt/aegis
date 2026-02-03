"""Cloudflare Worker entrypoint for the Aegis data pipeline.

Two handlers:
- on_fetch(): Serves data.json from R2 with cache headers.
- on_scheduled(): Runs the full data pipeline and writes to R2.

Uses function-based handlers (on_fetch / on_scheduled) with js.Response,
which is the stable Python Workers API.
"""

import asyncio
import json
import logging

from js import Response, Headers, Object

from constants import R2_KEY
from fetchers import (
    fetch_aviation_data,
    fetch_cloudflare_connectivity,
    fetch_news_intel,
    fetch_pentagon_data,
    fetch_polymarket_odds,
    fetch_tanker_activity,
    fetch_weather_data,
)
from risk import calculate_risk_scores, update_history

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("aegis")


def _make_response(body, status=200, headers_dict=None):
    """Build a JS Response with proper headers via the FFI."""
    headers = Headers.new()
    if headers_dict:
        for k, v in headers_dict.items():
            headers.set(k, v)
    init = Object.new()
    init.status = status
    init.headers = headers
    return Response.new(body, init)


ALLOWED_ORIGINS = [
    "https://usstrikeradar.com",
    "http://localhost",
]


def _get_cors_origin(request):
    """Return the Origin header if it matches an allowed origin, else None."""
    try:
        origin = request.headers.get("Origin") or ""
    except Exception:
        return "https://usstrikeradar.com"
    if origin in ALLOWED_ORIGINS or ".pages.dev" in origin:
        return origin
    return "https://usstrikeradar.com"


async def on_fetch(request, env):
    """Serve data.json from R2 with cache headers."""
    log.info("on_fetch: serving data.json from R2")

    cors_origin = _get_cors_origin(request)

    try:
        obj = await env.DATA_BUCKET.get(R2_KEY)
    except Exception as e:
        log.error("R2 get failed: %s", e)
        return _make_response(
            json.dumps({"error": "r2 read failed"}),
            status=500,
            headers_dict={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": cors_origin,
            },
        )

    if obj is None:
        log.warning("data.json not found in R2")
        return _make_response(
            json.dumps({"error": "data not found"}),
            status=404,
            headers_dict={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": cors_origin,
            },
        )

    # Parse data.json and add mock connectivity fallback if missing
    try:
        text = await obj.text()
        data = json.loads(text)

        # Add mock connectivity data if missing (until scheduled task runs)
        if "connectivity" not in data:
            data["connectivity"] = {
                "risk": 0,
                "detail": "STABLE (+0.0%)",
                "history": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                "raw_data": {"status": "STABLE", "trend": 0.0}
            }

        response_body = json.dumps(data)
    except Exception as e:
        log.warning("Failed to parse data, returning raw: %s", e)
        response_body = text if 'text' in dir() else "{}"

    log.info("Returning data.json")
    return _make_response(
        response_body,
        headers_dict={
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=60, s-maxage=300",
            "Access-Control-Allow-Origin": cors_origin,
        },
    )


async def on_scheduled(controller, env, ctx):
    """Run the full data pipeline: fetch APIs, calculate risks, write to R2."""
    log.info("=" * 50)
    log.info("SCHEDULED RUN STARTING")
    log.info("=" * 50)

    # 1. Read existing data from R2 (preserve history)
    current_data = {}
    try:
        obj = await env.DATA_BUCKET.get(R2_KEY)
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

    # 3. Fetch 5 independent APIs in parallel
    api_key = getattr(env, "OPENWEATHER_API_KEY", "")
    cloudflare_token = getattr(env, "CLOUDFLARE_RADAR_TOKEN", "")

    polymarket_result, news_result, aviation_result, weather_result, connectivity_result = (
        await asyncio.gather(
            fetch_polymarket_odds(),
            fetch_news_intel(),
            fetch_aviation_data(),
            fetch_weather_data(api_key),
            fetch_cloudflare_connectivity(cloudflare_token),
            return_exceptions=True,
        )
    )

    # Convert exceptions to None and log them
    for name, result in [
        ("Polymarket", polymarket_result),
        ("News", news_result),
        ("Aviation", aviation_result),
        ("Weather", weather_result),
        ("Connectivity", connectivity_result),
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
    if isinstance(connectivity_result, Exception):
        connectivity_result = None

    # 4. Sleep for OpenSky rate limit, then fetch tanker data
    log.info("Waiting 2s for OpenSky rate limit...")
    await asyncio.sleep(2)
    tanker_result = await fetch_tanker_activity()

    # Use previous data as fallback for any failed fetches
    polymarket_data = polymarket_result or current_data.get("polymarket", {}).get("raw_data", {})
    news_data = news_result or current_data.get("news", {}).get("raw_data", {})
    connectivity_data = connectivity_result or current_data.get("connectivity", {}).get("raw_data", {})
    aviation_data = aviation_result or current_data.get("flight", {}).get("raw_data", {})
    weather_data = weather_result or current_data.get("weather", {}).get("raw_data", {})
    tanker_data = tanker_result or current_data.get("tanker", {}).get("raw_data", {})

    fallback_used = []
    if polymarket_result is None:
        fallback_used.append("polymarket")
    if news_result is None:
        fallback_used.append("news")
    if connectivity_result is None:
        fallback_used.append("connectivity")
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
        connectivity=connectivity_data,
        aviation=aviation_data,
        tanker=tanker_data,
        weather=weather_data,
        polymarket=polymarket_data,
        pentagon_data=pentagon_data,
    )

    # 6. Update history and build final JSON
    raw = {
        "news": news_data,
        "connectivity": connectivity_data,
        "flight": aviation_data,
        "tanker": tanker_data,
        "weather": weather_data,
        "polymarket": polymarket_data,
        "pentagon": pentagon_data,
    }
    final_data = update_history(current_data, scores, raw)

    # 7. Write to R2
    payload = json.dumps(final_data, indent=2)
    await env.DATA_BUCKET.put(R2_KEY, payload)

    log.info("=" * 50)
    log.info("DATA COLLECTION COMPLETE")
    log.info("=" * 50)
    log.info("Total Risk: %d%%", scores["total_risk"])
    log.info("Written %d bytes to R2", len(payload))

"""Global Anxiety Pulse - visitor tracking and analytics.

Tracks visitor activity by country to show:
- How many people are watching (last 10 minutes)
- Activity multiplier vs baseline
- Country-specific surge detection
"""

import json
import logging
from datetime import datetime, timezone

log = logging.getLogger("aegis.pulse")

# Pulse data stored in separate R2 key
PULSE_KEY = "pulse.json"

# How long to keep visits (10 minutes in ms)
VISIT_WINDOW_MS = 10 * 60 * 1000

# Country code to flag emoji mapping
COUNTRY_FLAGS = {
    "IL": "🇮🇱", "US": "🇺🇸", "DE": "🇩🇪", "GB": "🇬🇧", "IR": "🇮🇷",
    "FR": "🇫🇷", "NL": "🇳🇱", "AE": "🇦🇪", "SA": "🇸🇦", "JO": "🇯🇴",
    "EG": "🇪🇬", "TR": "🇹🇷", "IN": "🇮🇳", "PK": "🇵🇰", "CA": "🇨🇦",
    "AU": "🇦🇺", "BR": "🇧🇷", "RU": "🇷🇺", "CN": "🇨🇳", "JP": "🇯🇵",
    "KR": "🇰🇷", "IT": "🇮🇹", "ES": "🇪🇸", "PL": "🇵🇱", "UA": "🇺🇦",
    "SE": "🇸🇪", "NO": "🇳🇴", "FI": "🇫🇮", "DK": "🇩🇰", "CH": "🇨🇭",
    "AT": "🇦🇹", "BE": "🇧🇪", "GR": "🇬🇷", "PT": "🇵🇹", "CZ": "🇨🇿",
    "RO": "🇷🇴", "HU": "🇭🇺", "IE": "🇮🇪", "SG": "🇸🇬", "MY": "🇲🇾",
    "TH": "🇹🇭", "VN": "🇻🇳", "PH": "🇵🇭", "ID": "🇮🇩", "MX": "🇲🇽",
    "AR": "🇦🇷", "CL": "🇨🇱", "CO": "🇨🇴", "ZA": "🇿🇦", "NG": "🇳🇬",
    "KE": "🇰🇪", "IQ": "🇮🇶", "SY": "🇸🇾", "LB": "🇱🇧", "KW": "🇰🇼",
    "QA": "🇶🇦", "BH": "🇧🇭", "OM": "🇴🇲", "YE": "🇾🇪", "AF": "🇦🇫",
    "XX": "🌍",  # Unknown
}

# Default baselines (estimated hourly visitors by country)
DEFAULT_BASELINES = {
    "total_hourly": 100,  # Default expected visitors per 10 min
    "by_country": {
        "US": 35, "IL": 15, "DE": 10, "GB": 10, "IR": 8,
        "FR": 5, "NL": 4, "CA": 4, "AU": 3, "IN": 3,
    }
}


def get_flag(country_code: str) -> str:
    """Get flag emoji for country code."""
    return COUNTRY_FLAGS.get(country_code, "🌍")


async def load_pulse_data(env) -> dict:
    """Load pulse data from R2, return empty structure if not found."""
    try:
        obj = await env.DATA_BUCKET.get(PULSE_KEY)
        if obj is not None:
            text = await obj.text()
            return json.loads(text)
    except Exception as e:
        log.warning("Failed to load pulse data: %s", e)

    # Return empty structure
    return {
        "visits": [],
        "baselines": DEFAULT_BASELINES,
    }


async def save_pulse_data(env, pulse_data: dict):
    """Save pulse data to R2."""
    try:
        payload = json.dumps(pulse_data)
        await env.DATA_BUCKET.put(PULSE_KEY, payload)
    except Exception as e:
        log.error("Failed to save pulse data: %s", e)


def trim_old_visits(visits: list, now_ms: int) -> list:
    """Remove visits older than VISIT_WINDOW_MS."""
    cutoff = now_ms - VISIT_WINDOW_MS
    return [v for v in visits if v.get("ts", 0) > cutoff]


async def log_visit(env, country_code: str) -> dict:
    """Log a visit and return current pulse stats.

    Args:
        env: Cloudflare Worker environment with R2 binding
        country_code: 2-letter country code from cf-ipcountry header

    Returns:
        Calculated pulse stats dict
    """
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    # Load existing pulse data
    pulse_data = await load_pulse_data(env)

    # Trim old visits
    visits = trim_old_visits(pulse_data.get("visits", []), now_ms)

    # Add this visit
    visits.append({"ts": now_ms, "cc": country_code or "XX"})

    # Keep only last 15 minutes max (buffer beyond 10 min window)
    max_visits = 10000  # Safety limit
    if len(visits) > max_visits:
        visits = visits[-max_visits:]

    # Save updated visits
    pulse_data["visits"] = visits
    await save_pulse_data(env, pulse_data)

    # Calculate and return stats
    return calculate_pulse_stats(visits, pulse_data.get("baselines", DEFAULT_BASELINES), now_ms)


def calculate_pulse_stats(visits: list, baselines: dict, now_ms: int) -> dict:
    """Calculate pulse statistics from visits.

    Args:
        visits: List of visit records [{ts, cc}, ...]
        baselines: Baseline expectations
        now_ms: Current timestamp in milliseconds

    Returns:
        Pulse stats dict for frontend
    """
    # Filter to last 10 minutes
    cutoff = now_ms - VISIT_WINDOW_MS
    recent_visits = [v for v in visits if v.get("ts", 0) > cutoff]

    # Count total watching
    watching_now = len(recent_visits)

    # Count by country
    country_counts = {}
    for v in recent_visits:
        cc = v.get("cc", "XX")
        country_counts[cc] = country_counts.get(cc, 0) + 1

    # Calculate activity multiplier
    baseline_total = baselines.get("total_hourly", 100)
    if baseline_total > 0:
        activity_multiplier = round(watching_now / baseline_total, 1)
    else:
        activity_multiplier = 1.0

    # Determine activity level
    if activity_multiplier <= 1.2:
        activity_level = "normal"
    elif activity_multiplier <= 2.0:
        activity_level = "elevated"
    elif activity_multiplier <= 3.0:
        activity_level = "high"
    else:
        activity_level = "surging"

    # Calculate country surges
    country_baselines = baselines.get("by_country", {})
    countries = []

    for cc, count in sorted(country_counts.items(), key=lambda x: x[1], reverse=True):
        baseline = country_baselines.get(cc, 5)  # Default baseline of 5
        surge = round(count / baseline, 2) if baseline > 0 else 1.0

        countries.append({
            "cc": cc,
            "flag": get_flag(cc),
            "count": count,
            "surge": surge,
        })

    # Israel stats (always include even if 0)
    israel_data = next((c for c in countries if c["cc"] == "IL"), None)
    if israel_data:
        israel = {
            "count": israel_data["count"],
            "surge": israel_data["surge"],
        }
    else:
        israel = {"count": 0, "surge": 0}

    # Other countries (exclude Israel, filter to surge >= 1.5 or top 6)
    other_countries = [c for c in countries if c["cc"] != "IL"]

    # Show countries with surge >= 1.5, or top 6 if not enough
    surging_countries = [c for c in other_countries if c["surge"] >= 1.5]
    if len(surging_countries) < 4:
        surging_countries = other_countries[:6]
    else:
        surging_countries = surging_countries[:6]

    return {
        "watching_now": watching_now,
        "activity_multiplier": activity_multiplier,
        "activity_level": activity_level,
        "israel": israel,
        "countries": surging_countries,
        "total_countries": len(country_counts),
    }


async def get_pulse_stats_only(env) -> dict:
    """Get pulse stats without logging a new visit.

    Used by scheduled handler or when we just want to read stats.
    """
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    pulse_data = await load_pulse_data(env)
    visits = pulse_data.get("visits", [])
    baselines = pulse_data.get("baselines", DEFAULT_BASELINES)

    return calculate_pulse_stats(visits, baselines, now_ms)

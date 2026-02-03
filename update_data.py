"""Aegis Data Pipeline — standalone continuous fetcher.

Replaces the Cloudflare Worker cron.  Runs in an infinite loop, fetching
data every 30 minutes, writing frontend/data.json, and committing + pushing
via git.

Dependencies: aiohttp (pip install aiohttp)
Environment:  OPENWEATHER_API_KEY must be set.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import signal
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("aegis")

# ---------------------------------------------------------------------------
# Constants (inlined from worker/src/constants.py)
# ---------------------------------------------------------------------------
DATA_JSON_PATH = Path("frontend/data.json")

PIZZA_PLACES = [
    {"name": "Domino's Pizza", "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4", "address": "Pentagon City"},
    {"name": "Papa John's", "place_id": "ChIJP3Sa8ziYEmsRUKgyFmh9AQM", "address": "Near Pentagon"},
    {"name": "Pizza Hut", "place_id": "ChIJrTLr-GyuEmsRBfy61i59si0", "address": "Pentagon Area"},
]

ALERT_KEYWORDS = ["strike", "attack", "military", "bomb", "missile", "war", "imminent", "troops", "forces"]
IRAN_KEYWORDS = ["iran", "tehran", "persian gulf", "strait of hormuz"]
STRIKE_KEYWORDS = ["strike", "attack", "bomb", "military action"]
NEGATIVE_KEYWORDS = [" not ", "won't", "will not", "doesn't", "does not"]

TANKER_PREFIXES = [
    # Original fuel/gas station themed
    "IRON", "SHELL", "TEXAN", "ETHYL", "PEARL", "ARCO",
    "ESSO", "MOBIL", "GULF", "TOPAZ", "PACK", "DOOM", "TREK", "REACH",
    # Additional fuel-themed callsigns
    "EXXON", "TEXACO", "OILER", "OPEC", "PETRO",
    # KC-10 unit callsigns
    "TOGA", "DUCE", "FORCE", "GUCCI", "XTNDR", "SPUR", "TEAM", "QUID",
    # KC-135 unit callsigns
    "BOLT", "BROKE", "BROOM", "BOBBY", "BOBBIE", "BODE", "CONIC",
    "MAINE", "BRIG", "ARTLY", "BANKER", "BRUSH",
    # KC-46 unit callsigns
    "ARRIS",
    # Coronet/trans-Atlantic mission callsigns
    "GOLD", "BLUE", "CLEAN", "VINYL",
]

USAF_HEX_START = int("AE0000", 16)
USAF_HEX_END = int("AE7FFF", 16)

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
]

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

# Cloudflare Radar API configuration
CLOUDFLARE_RADAR_BASE_URL = "https://api.cloudflare.com/client/v4/radar"
CLOUDFLARE_RADAR_LOCATION = "IR"  # Iran

CYCLE_INTERVAL = 30 * 60  # 30 minutes in seconds

# ---------------------------------------------------------------------------
# Fetchers (re-implemented with aiohttp)
# ---------------------------------------------------------------------------

async def fetch_polymarket_odds(session: aiohttp.ClientSession) -> dict | None:
    """Fetch Iran strike odds from Polymarket Gamma API."""
    try:
        log.info("=" * 50)
        log.info("POLYMARKET ODDS")
        log.info("=" * 50)

        async with session.get("https://gamma-api.polymarket.com/public-search?q=iran") as resp:
            if resp.status != 200:
                log.warning("Polymarket API error: %d", resp.status)
                return None
            data = await resp.json(content_type=None)

        if isinstance(data, dict) and data.get("events"):
            events = data["events"]
        elif isinstance(data, dict) and data.get("data"):
            events = data["data"]
        elif isinstance(data, list):
            events = data
        else:
            log.warning("Unexpected Polymarket response format: %s", type(data).__name__)
            return None

        events = [e for e in events if isinstance(e, dict)]
        highest_odds = 0
        market_title = ""

        log.info("Scanning %d events...", len(events))

        def get_market_odds(market):
            odds = 0
            prices = market.get("outcomePrices", [])
            if prices and len(prices) > 0:
                try:
                    yes_price = float(str(prices[0]) if prices[0] else "0")
                    if yes_price > 1:
                        odds = round(yes_price)
                    elif 0 < yes_price <= 1:
                        odds = round(yes_price * 100)
                    if odds >= 100 and len(prices) > 1:
                        no_price = float(str(prices[1])) if prices[1] else 0
                        if 0 < no_price < 1:
                            odds = round((1 - no_price) * 100)
                        elif no_price > 1:
                            odds = 100 - round(no_price)
                except (ValueError, TypeError):
                    pass
            if odds == 0 or odds >= 100:
                try:
                    best_ask = float(market.get("bestAsk", 0) or 0)
                    if best_ask > 1:
                        odds = round(best_ask)
                    elif 0 < best_ask <= 1:
                        odds = round(best_ask * 100)
                except (ValueError, TypeError):
                    pass
            if odds == 0 or odds >= 100:
                try:
                    last_price = float(market.get("lastTradePrice", 0) or 0)
                    if last_price > 1:
                        odds = round(last_price)
                    elif 0 < last_price <= 1:
                        odds = round(last_price * 100)
                except (ValueError, TypeError):
                    pass
            if odds >= 100:
                return 0
            return odds

        def is_near_term_market(title):
            title_lower = title.lower()
            now = datetime.now()
            week_ahead = now + timedelta(days=7)
            for i, month in enumerate(MONTHS, 1):
                if month in title_lower:
                    match = re.search(rf"{month}\s+(\d{{1,2}})", title_lower)
                    if match:
                        day = int(match.group(1))
                        try:
                            market_date = datetime(now.year, i, day)
                            if market_date < now:
                                market_date = datetime(now.year + 1, i, day)
                            if now <= market_date <= week_ahead:
                                log.info("    Market date %s is within 7 days", market_date.strftime("%Y-%m-%d"))
                                return True
                        except ValueError:
                            pass
            return False

        # First pass: specific strike markets
        for event in events:
            event_title = (event.get("title") or "").lower()
            if "will us or israel strike iran" in event_title or "us strikes iran by" in event_title:
                if not is_near_term_market(event.get("title", "")):
                    continue
                for market in event.get("markets", []):
                    odds = get_market_odds(market)
                    if odds > highest_odds:
                        highest_odds = odds
                        market_title = market.get("question") or event.get("title") or ""
            for market in event.get("markets", []):
                market_question = (market.get("question") or "").lower()
                if any(neg in market_question for neg in NEGATIVE_KEYWORDS):
                    continue
                if "iran" in market_question and any(kw in market_question for kw in STRIKE_KEYWORDS):
                    market_name = market.get("question") or ""
                    if not is_near_term_market(market_name):
                        continue
                    odds = get_market_odds(market)
                    if odds > 0 and odds > highest_odds:
                        highest_odds = odds
                        market_title = market_name

        # Second pass: any Iran-related market
        if highest_odds == 0:
            for event in events:
                event_title = (event.get("title") or "").lower()
                if any(neg in event_title for neg in NEGATIVE_KEYWORDS):
                    continue
                if "iran" in event_title:
                    if not is_near_term_market(event.get("title", "")):
                        continue
                    for market in event.get("markets", []):
                        market_question = (market.get("question") or "").lower()
                        if any(neg in market_question for neg in NEGATIVE_KEYWORDS):
                            continue
                        market_name = market.get("question") or event.get("title") or ""
                        if not is_near_term_market(market_name):
                            continue
                        odds = get_market_odds(market)
                        if odds > 0 and odds > highest_odds:
                            highest_odds = odds
                            market_title = market_name

        if highest_odds > 0:
            display = market_title[:70] + "..." if len(market_title) > 70 else market_title
            log.info("Market: %s", display)
        log.info("Result: Risk %d%%", highest_odds)

        return {
            "odds": highest_odds,
            "market": market_title,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        log.error("Polymarket fetch error: %s", e)
        log.debug(traceback.format_exc())
        return None


async def fetch_news_intel(session: aiohttp.ClientSession) -> dict | None:
    """Fetch Iran-related news from RSS feeds."""
    try:
        log.info("=" * 50)
        log.info("NEWS INTELLIGENCE")
        log.info("=" * 50)

        all_articles = []
        alert_count = 0

        for feed_url in RSS_FEEDS:
            try:
                log.info("  Fetching %s...", feed_url[:50])
                headers = {"User-Agent": "Mozilla/5.0 (compatible; StrikeRadar/1.0)"}
                async with session.get(feed_url, headers=headers) as resp:
                    if resp.status != 200:
                        log.warning("    Failed: %d", resp.status)
                        continue
                    content = await resp.text()

                root = ET.fromstring(content)
                items = root.findall(".//item")
                if not items:
                    items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

                for item in items:
                    title_elem = item.find("title")
                    desc_elem = item.find("description")
                    if title_elem is None:
                        title_elem = item.find("{http://www.w3.org/2005/Atom}title")
                    if desc_elem is None:
                        desc_elem = item.find("{http://www.w3.org/2005/Atom}summary")

                    title = title_elem.text if title_elem is not None else ""
                    desc = desc_elem.text if desc_elem is not None else ""
                    combined = (title + " " + desc).lower()

                    if any(kw in combined for kw in IRAN_KEYWORDS):
                        is_alert = any(kw in combined for kw in ALERT_KEYWORDS)
                        if is_alert:
                            alert_count += 1
                        all_articles.append({
                            "title": title[:100] if title else "",
                            "is_alert": is_alert,
                        })

            except Exception as e:
                log.warning("    Error: %s", e)
                continue

        # Deduplicate
        seen: set[str] = set()
        unique_articles = []
        for article in all_articles:
            key = article["title"][:40].lower()
            if key not in seen:
                seen.add(key)
                unique_articles.append(article)

        log.info("Found %d articles (%d critical)", len(unique_articles), alert_count)
        alert_ratio = alert_count / len(unique_articles) if len(unique_articles) > 0 else 0
        risk = max(3, round(pow(alert_ratio, 2) * 85))
        log.info("Result: Risk %d%%", risk)

        return {
            "articles": unique_articles,
            "total_count": len(unique_articles),
            "alert_count": alert_count,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        log.error("News Intel error: %s", e)
        log.debug(traceback.format_exc())
        return None


async def fetch_aviation_data(session: aiohttp.ClientSession) -> dict | None:
    """Fetch OpenSky Network data for aircraft over Iran."""
    try:
        log.info("=" * 50)
        log.info("AVIATION TRACKING")
        log.info("=" * 50)

        url = "https://opensky-network.org/api/states/all?lamin=25&lomin=44&lamax=40&lomax=64"
        async with session.get(url) as resp:
            if resp.status != 200:
                log.warning("OpenSky API error: %d", resp.status)
                return None
            data = await resp.json(content_type=None)

        civil_count = 0
        airlines: list[str] = []

        if data.get("states") and isinstance(data["states"], list):
            for aircraft in data["states"]:
                icao = aircraft[0]
                callsign = (aircraft[1] or "").strip()
                on_ground = aircraft[8]

                if on_ground:
                    continue

                try:
                    icao_num = int(icao, 16)
                    if USAF_HEX_START <= icao_num <= USAF_HEX_END:
                        continue
                except Exception:
                    pass

                civil_count += 1
                if callsign and len(callsign) >= 3:
                    airline_code = callsign[:3]
                    if airline_code not in airlines:
                        airlines.append(airline_code)

        log.info("Detected %d aircraft, %d airlines over Iran", civil_count, len(airlines))
        risk = max(3, 95 - round(civil_count * 0.8))
        log.info("Result: Risk %d%%", risk)

        return {
            "aircraft_count": civil_count,
            "airline_count": len(airlines),
            "airlines": airlines[:10],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        log.error("Aviation error: %s", e)
        return None


async def fetch_tanker_activity(session: aiohttp.ClientSession) -> dict | None:
    """Fetch US military tanker activity in Middle East."""
    try:
        log.info("=" * 50)
        log.info("TANKER ACTIVITY")
        log.info("=" * 50)

        url = "https://opensky-network.org/api/states/all?lamin=20&lomin=40&lamax=40&lomax=65"
        async with session.get(url) as resp:
            if resp.status != 200:
                log.warning("OpenSky API error: %d", resp.status)
                return None
            data = await resp.json(content_type=None)

        tanker_count = 0
        tanker_callsigns: list[str] = []

        if data.get("states") and isinstance(data["states"], list):
            for aircraft in data["states"]:
                icao = aircraft[0]
                callsign = (aircraft[1] or "").strip().upper()

                try:
                    icao_num = int(icao, 16)
                    is_us_military = USAF_HEX_START <= icao_num <= USAF_HEX_END
                except Exception:
                    is_us_military = False

                is_tanker_callsign = any(callsign.startswith(prefix) for prefix in TANKER_PREFIXES)
                has_kc_pattern = "KC" in callsign or "TANKER" in callsign

                if is_us_military and (is_tanker_callsign or has_kc_pattern):
                    tanker_count += 1
                    if callsign:
                        tanker_callsigns.append(callsign)

        log.info("Detected %d tankers in Middle East", tanker_count)
        if tanker_callsigns:
            log.info("  Callsigns: %s", ", ".join(tanker_callsigns[:5]))
        risk = round((tanker_count / 10) * 100)
        log.info("Result: Risk %d%%", risk)

        return {
            "tanker_count": tanker_count,
            "callsigns": tanker_callsigns[:5],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        log.error("Tanker error: %s", e)
        return None


async def fetch_weather_data(session: aiohttp.ClientSession, api_key: str) -> dict | None:
    """Fetch weather conditions for Tehran."""
    try:
        log.info("=" * 50)
        log.info("WEATHER CONDITIONS")
        log.info("=" * 50)

        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat=35.6892&lon=51.389&appid={api_key}&units=metric"
        )
        async with session.get(url) as resp:
            if resp.status != 200:
                log.warning("Weather API error: %d", resp.status)
                return None
            data = await resp.json(content_type=None)

        if not data.get("main"):
            log.warning("Weather: No main data in response")
            return None

        temp = round(data["main"]["temp"])
        visibility = data.get("visibility", 10000)
        clouds = data.get("clouds", {}).get("all", 0)
        description = data.get("weather", [{}])[0].get("description", "clear")

        if visibility >= 10000 and clouds < 30:
            condition = "Favorable"
        elif visibility >= 7000 and clouds < 60:
            condition = "Marginal"
        else:
            condition = "Poor"

        log.info("Conditions: %d°C, %s, clouds %d%%, %s", temp, condition, clouds, description)
        risk = max(0, min(100, 100 - (max(0, clouds - 6) * 10)))
        log.info("Result: Risk %d%%", risk)

        return {
            "temp": temp,
            "visibility": visibility,
            "clouds": clouds,
            "description": description,
            "condition": condition,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        log.error("Weather error: %s", e)
        return None


async def fetch_cloudflare_connectivity(session: aiohttp.ClientSession, api_token: str) -> dict | None:
    """Fetch Iran internet connectivity data from Cloudflare Radar API.

    Uses the HTTP timeseries endpoint to detect internet disruptions.
    A 4-hour moving average of percentage change values determines risk:
    - Stable (> -15%): 0% risk contribution
    - Anomalous (-15% to -25%): 10% risk contribution
    - Critical (-25% to -50%): 20% risk contribution
    - Blackout (<= -90%): 25% risk contribution
    """
    try:
        log.info("=" * 50)
        log.info("DIGITAL CONNECTIVITY")
        log.info("=" * 50)

        if not api_token:
            log.warning("Cloudflare Radar API token not configured")
            return None

        # Request 8 hours of data with 1-hour intervals
        url = (
            f"{CLOUDFLARE_RADAR_BASE_URL}/http/timeseries"
            f"?location={CLOUDFLARE_RADAR_LOCATION}"
            f"&botClass=LIKELY_HUMAN"
            f"&normalization=PERCENTAGE_CHANGE"
            f"&aggInterval=1h"
            f"&dateRange=8h"
        )

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                log.warning("Cloudflare Radar API error: %d", resp.status)
                # Return stale status indicator
                return {
                    "status": "STALE",
                    "risk": 0,
                    "trend": 0,
                    "values": [],
                    "timestamp": datetime.now().isoformat(),
                    "error": f"API returned {resp.status}",
                }

            data = await resp.json(content_type=None)

        # Extract timeseries values from the response
        result = data.get("result", {})
        series = result.get("serie_0", {}) if result else {}
        values = series.get("values", [])

        if not values:
            log.warning("No data points in Cloudflare response")
            return {
                "status": "STALE",
                "risk": 0,
                "trend": 0,
                "values": [],
                "timestamp": datetime.now().isoformat(),
                "error": "No data points returned",
            }

        # Parse values (they come as percentage change values, e.g., -0.15 = -15%)
        parsed_values = []
        for v in values:
            try:
                parsed_values.append(float(v))
            except (ValueError, TypeError):
                continue

        log.info("Received %d data points", len(parsed_values))

        # Calculate 4-hour moving average (last 4 data points)
        recent_values = parsed_values[-4:] if len(parsed_values) >= 4 else parsed_values
        if not recent_values:
            log.warning("No valid values to calculate trend")
            return {
                "status": "STALE",
                "risk": 0,
                "trend": 0,
                "values": parsed_values,
                "timestamp": datetime.now().isoformat(),
                "error": "No valid values",
            }

        trend = sum(recent_values) / len(recent_values)
        log.info("4-hour moving average: %.3f", trend)

        # Determine risk based on thresholds (PRD specification)
        if trend <= -0.90:
            risk = 25
            status = "BLACKOUT"
        elif trend <= -0.50:
            risk = 20
            status = "CRITICAL"
        elif trend <= -0.15:
            risk = 10
            status = "ANOMALOUS"
        else:
            risk = 0
            status = "STABLE"

        log.info("Status: %s, Risk contribution: %d%%", status, risk)

        return {
            "status": status,
            "risk": risk,
            "trend": round(trend * 100, 1),  # Convert to percentage for display
            "values": parsed_values,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        log.error("Cloudflare connectivity error: %s", e)
        log.debug(traceback.format_exc())
        return None


def fetch_pentagon_data() -> dict:
    """Compute Pentagon Pizza Meter data (no API call, time-based simulation)."""
    log.info("=" * 50)
    log.info("PENTAGON PIZZA METER")
    log.info("=" * 50)

    now = datetime.now()
    current_hour = now.hour
    current_day = now.weekday()

    busyness_data = []

    for place in PIZZA_PLACES:
        base_score = 30
        status = "normal"

        if 11 <= current_hour <= 14 and current_day < 5:
            base_score = 50
        elif 17 <= current_hour <= 20:
            base_score = 55
        elif current_hour >= 22 or current_hour < 6:
            day_hash = int(hashlib.md5(f"{now.date()}".encode()).hexdigest()[:8], 16)
            if day_hash % 10 < 2:
                base_score = 70
                status = "elevated_late"
            else:
                base_score = 20
        elif current_day >= 5:
            base_score = 25

        busyness_data.append({
            "name": place["name"],
            "status": status,
            "score": base_score,
        })
        log.info("  %s: Status=%s, Score=%d", place["name"], status, base_score)

    is_late_night = current_hour >= 22 or current_hour < 6
    is_weekend = current_day >= 5

    log.info("  Hour: %d, Late night: %s, Weekend: %s", current_hour, is_late_night, is_weekend)

    total_score = 0
    valid_readings = 0

    for place in busyness_data:
        if place.get("score") is not None:
            score = place["score"]
            valid_readings += 1
            if is_late_night and score > 60:
                weighted = score * 1.5
                log.info("    %s: %d x 1.5 (late night busy) = %.1f", place["name"], score, weighted)
                total_score += weighted
            elif is_weekend and score > 70:
                weighted = score * 1.3
                log.info("    %s: %d x 1.3 (weekend busy) = %.1f", place["name"], score, weighted)
                total_score += weighted
            else:
                log.info("    %s: %d (normal weighting)", place["name"], score)
                total_score += score

    if valid_readings == 0:
        log.info("  No valid readings, using default score of 30")
        activity_score = 30
    else:
        avg_score = total_score / valid_readings
        activity_score = round(min(100, max(0, avg_score)))
        log.info("  Total: %.1f, Readings: %d, Average: %.1f", total_score, valid_readings, avg_score)

    if activity_score >= 80:
        risk_contribution = 10
        pentagon_status = "High Activity"
    elif activity_score >= 60:
        risk_contribution = 7
        pentagon_status = "Elevated"
    elif activity_score >= 40:
        risk_contribution = 3
        pentagon_status = "Normal"
    else:
        risk_contribution = 1
        pentagon_status = "Low Activity"

    display_risk = round((risk_contribution / 10) * 100)
    log.info("Activity: %s - Score: %d/100", pentagon_status, activity_score)
    log.info("Result: Risk %d%%", display_risk)

    return {
        "score": activity_score,
        "risk_contribution": risk_contribution,
        "status": pentagon_status,
        "places": busyness_data,
        "timestamp": now.isoformat(),
        "is_late_night": is_late_night,
        "is_weekend": is_weekend,
    }


# ---------------------------------------------------------------------------
# Risk calculation (inlined from worker/src/risk.py)
# ---------------------------------------------------------------------------

def calculate_risk_scores(
    news_intel: dict,
    connectivity: dict,
    aviation: dict,
    tanker: dict,
    weather: dict,
    polymarket: dict,
    pentagon_data: dict,
) -> dict:
    """Calculate all risk scores and return the signal data dict."""
    log.info("=" * 50)
    log.info("RISK CALCULATION")
    log.info("=" * 50)

    # NEWS (20% weight)
    articles = news_intel.get("total_count", 0)
    alert_count = news_intel.get("alert_count", 0)
    alert_ratio = alert_count / articles if articles > 0 else 0
    news_display_risk = max(3, round(pow(alert_ratio, 2) * 85))
    news_detail = f"{articles} articles, {alert_count} critical"
    log.info("  News:       %d%% (%s)", news_display_risk, news_detail)

    # DIGITAL CONNECTIVITY (20% weight)
    connectivity_status = connectivity.get("status", "STABLE") if connectivity else "STABLE"
    connectivity_risk = connectivity.get("risk", 0) if connectivity else 0
    connectivity_trend = connectivity.get("trend", 0) if connectivity else 0
    # Display risk: Scale the 0-25 risk contribution to 0-100 for display
    connectivity_display_risk = min(100, connectivity_risk * 4)
    if connectivity_status == "STALE":
        connectivity_detail = "Data unavailable"
    else:
        connectivity_detail = f"{connectivity_status} ({connectivity_trend:+.1f}%)"
    log.info("  Connect:    %d%% (%s)", connectivity_display_risk, connectivity_detail)

    # FLIGHT (15% weight)
    aircraft_count = aviation.get("aircraft_count", 0)
    flight_risk = max(3, 95 - round(aircraft_count * 0.8))
    flight_detail = f"{round(aircraft_count)} aircraft over Iran"
    log.info("  Flight:     %d%% (%s)", flight_risk, flight_detail)

    # TANKER (15% weight)
    tanker_count = tanker.get("tanker_count", 0)
    tanker_risk = round((tanker_count / 10) * 100)
    tanker_display_count = round(tanker_count / 4)
    tanker_detail = f"{tanker_display_count} detected in region"
    log.info("  Tanker:     %d%% (%s)", tanker_risk, tanker_detail)

    # WEATHER (5% weight)
    clouds = weather.get("clouds", 0)
    weather_risk = max(0, min(100, 100 - (max(0, clouds - 6) * 10)))
    weather_detail = weather.get("description", "clear")
    log.info("  Weather:    %d%% (%s)", weather_risk, weather_detail)

    # POLYMARKET (15% weight)
    polymarket_odds = min(100, max(0, polymarket.get("odds", 0) if polymarket else 0))
    if polymarket_odds > 95:
        polymarket_odds = 0
    polymarket_display_risk = polymarket_odds if polymarket_odds > 0 else 10
    polymarket_detail = f"{polymarket_odds}% odds" if polymarket_odds > 0 else "Awaiting data..."
    log.info("  Polymarket: %d%% (%s)", polymarket_display_risk, polymarket_detail)

    # PENTAGON (10% weight)
    pentagon_contribution = pentagon_data.get("risk_contribution", 1)
    pentagon_display_risk = round((pentagon_contribution / 10) * 100)
    pentagon_status = pentagon_data.get("status", "Normal")
    is_late_night = pentagon_data.get("is_late_night", False)
    is_weekend = pentagon_data.get("is_weekend", False)
    pentagon_detail = (
        f"{pentagon_status}"
        f"{' (late night)' if is_late_night else ''}"
        f"{' (weekend)' if is_weekend else ''}"
    )
    log.info("  Pentagon:   %d%% (%s)", pentagon_display_risk, pentagon_detail)

    # Weighted contributions (v2.0 weights per PRD)
    # News: 20%, Connectivity: 20%, Aviation: 15%, Tanker: 15%,
    # Market: 15%, Pentagon: 10%, Weather: 5%
    news_weighted = news_display_risk * 0.20
    connectivity_weighted = connectivity_display_risk * 0.20
    flight_weighted = flight_risk * 0.15
    tanker_weighted = tanker_risk * 0.15
    polymarket_weighted = polymarket_display_risk * 0.15
    pentagon_weighted = pentagon_display_risk * 0.10
    weather_weighted = weather_risk * 0.05

    log.info(
        "  Weighted: news=%.1f conn=%.1f flight=%.1f tanker=%.1f poly=%.1f pent=%.1f weather=%.1f",
        news_weighted, connectivity_weighted, flight_weighted, tanker_weighted,
        polymarket_weighted, pentagon_weighted, weather_weighted,
    )

    total_risk = (
        news_weighted
        + connectivity_weighted
        + flight_weighted
        + tanker_weighted
        + polymarket_weighted
        + pentagon_weighted
        + weather_weighted
    )

    # Escalation multiplier
    elevated_count = sum([
        news_display_risk > 30,
        connectivity_risk >= 10,  # ANOMALOUS or higher
        flight_risk > 50,
        tanker_risk > 30,
        polymarket_display_risk > 30,
        pentagon_display_risk > 50,
        weather_risk > 70,
    ])

    if elevated_count >= 3:
        log.info("  Escalation: %d signals elevated, multiplying by 1.15", elevated_count)
        total_risk = min(100, total_risk * 1.15)

    total_risk = min(100, max(0, round(total_risk)))
    log.info("  TOTAL RISK: %d%% (elevated signals: %d)", total_risk, elevated_count)

    return {
        "news": {"risk": news_display_risk, "detail": news_detail},
        "connectivity": {"risk": connectivity_display_risk, "detail": connectivity_detail},
        "flight": {"risk": flight_risk, "detail": flight_detail},
        "tanker": {"risk": tanker_risk, "detail": tanker_detail},
        "weather": {"risk": weather_risk, "detail": weather_detail},
        "polymarket": {"risk": polymarket_display_risk, "detail": polymarket_detail},
        "pentagon": {"risk": pentagon_display_risk, "detail": pentagon_detail},
        "total_risk": total_risk,
        "elevated_count": elevated_count,
    }


def update_history(current_data: dict, scores: dict, raw: dict) -> dict:
    """Update signal histories and total risk history, return the final JSON structure."""
    # Extract existing histories
    if "total_risk" in current_data and "history" in current_data.get("total_risk", {}):
        history = current_data["total_risk"]["history"]
        signal_history = {
            sig: current_data.get(sig, {}).get("history", [])
            for sig in ["news", "connectivity", "flight", "tanker", "pentagon", "polymarket", "weather"]
        }
    else:
        history = current_data.get("history", [])
        signal_history = current_data.get("signalHistory", {
            "news": [], "connectivity": [], "flight": [], "tanker": [],
            "pentagon": [], "polymarket": [], "weather": [],
        })

    # Append current scores to signal histories
    for sig in ["news", "connectivity", "flight", "tanker", "pentagon", "polymarket", "weather"]:
        if sig not in signal_history:
            signal_history[sig] = []
        signal_history[sig].append(scores[sig]["risk"])
        if len(signal_history[sig]) > 20:
            signal_history[sig] = signal_history[sig][-20:]

    # Total risk history management
    now = datetime.now()
    current_timestamp = int(now.timestamp() * 1000)
    total_risk = scores["total_risk"]

    if now.hour >= 12:
        current_boundary = now.replace(hour=12, minute=0, second=0, microsecond=0)
    else:
        current_boundary = now.replace(hour=0, minute=0, second=0, microsecond=0)
    current_boundary_ts = int(current_boundary.timestamp() * 1000)

    if history:
        last_point = history[-1]
        last_point_ts = last_point.get("timestamp", 0)
        crossed_boundary = last_point_ts < current_boundary_ts

        if crossed_boundary:
            log.info("  History: crossed 12h boundary, pinning + adding new point")
            if len(history) > 0:
                history = history[1:]
            if len(history) > 0:
                history[-1] = {
                    "timestamp": current_boundary_ts,
                    "risk": last_point.get("risk", total_risk),
                    "pinned": True,
                }
            history.append({"timestamp": current_timestamp, "risk": total_risk})
        else:
            log.info("  History: updating last point in-place")
            history[-1] = {"timestamp": current_timestamp, "risk": total_risk}
    else:
        log.info("  History: starting fresh with single point")
        history = [{"timestamp": current_timestamp, "risk": total_risk}]

    log.info("  History points: %d", len(history))

    return {
        "news": {
            "risk": scores["news"]["risk"],
            "detail": scores["news"]["detail"],
            "history": signal_history["news"],
            "raw_data": raw.get("news", {}),
        },
        "connectivity": {
            "risk": scores["connectivity"]["risk"],
            "detail": scores["connectivity"]["detail"],
            "history": signal_history["connectivity"],
            "raw_data": raw.get("connectivity", {}),
        },
        "flight": {
            "risk": scores["flight"]["risk"],
            "detail": scores["flight"]["detail"],
            "history": signal_history["flight"],
            "raw_data": raw.get("flight", {}),
        },
        "tanker": {
            "risk": scores["tanker"]["risk"],
            "detail": scores["tanker"]["detail"],
            "history": signal_history["tanker"],
            "raw_data": raw.get("tanker", {}),
        },
        "weather": {
            "risk": scores["weather"]["risk"],
            "detail": scores["weather"]["detail"],
            "history": signal_history["weather"],
            "raw_data": raw.get("weather", {}),
        },
        "polymarket": {
            "risk": scores["polymarket"]["risk"],
            "detail": scores["polymarket"]["detail"],
            "history": signal_history["polymarket"],
            "raw_data": raw.get("polymarket", {}),
        },
        "pentagon": {
            "risk": scores["pentagon"]["risk"],
            "detail": scores["pentagon"]["detail"],
            "history": signal_history["pentagon"],
            "raw_data": raw.get("pentagon", {}),
        },
        "total_risk": {
            "risk": total_risk,
            "history": history,
            "elevated_count": scores["elevated_count"],
        },
        "last_updated": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------

def _run_git(*args: str) -> subprocess.CompletedProcess:
    """Run a git command, returning the CompletedProcess."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def git_pull() -> None:
    """Pull latest changes to avoid conflicts."""
    log.info("Running git pull --rebase...")
    result = _run_git("pull", "--rebase")
    if result.returncode != 0:
        log.warning("git pull failed: %s", result.stderr.strip())
    else:
        log.info("git pull: %s", result.stdout.strip() or "up to date")


def git_commit_and_push() -> None:
    """Stage data.json, commit, and push."""
    log.info("Committing and pushing data.json...")

    _run_git("add", str(DATA_JSON_PATH))

    # Check if there are staged changes
    diff_result = _run_git("diff", "--cached", "--quiet")
    if diff_result.returncode == 0:
        log.info("No changes to commit.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = f"data: update {timestamp}"
    commit_result = _run_git("commit", "-m", commit_msg)
    if commit_result.returncode != 0:
        log.warning("git commit failed: %s", commit_result.stderr.strip())
        return

    log.info("Committed: %s", commit_msg)

    push_result = _run_git("push")
    if push_result.returncode != 0:
        log.warning("git push failed: %s", push_result.stderr.strip())
    else:
        log.info("Pushed successfully.")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run_pipeline(weather_api_key: str, cloudflare_token: str) -> None:
    """Execute one full data-fetch-and-update cycle."""
    log.info("=" * 60)
    log.info("STARTING PIPELINE CYCLE")
    log.info("=" * 60)

    # 1. Pull latest
    git_pull()

    # 2. Read existing data
    current_data: dict = {}
    if DATA_JSON_PATH.exists():
        try:
            current_data = json.loads(DATA_JSON_PATH.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Could not read existing data.json: %s", e)

    # 3. Fetch APIs
    async with aiohttp.ClientSession() as session:
        # Fetch polymarket, news, aviation, weather, connectivity in parallel
        polymarket_task = asyncio.create_task(fetch_polymarket_odds(session))
        news_task = asyncio.create_task(fetch_news_intel(session))
        aviation_task = asyncio.create_task(fetch_aviation_data(session))
        weather_task = asyncio.create_task(fetch_weather_data(session, weather_api_key))
        connectivity_task = asyncio.create_task(fetch_cloudflare_connectivity(session, cloudflare_token))

        polymarket_result, news_result, aviation_result, weather_result, connectivity_result = await asyncio.gather(
            polymarket_task, news_task, aviation_task, weather_task, connectivity_task,
        )

        # 4. Sleep 2s then fetch tanker (OpenSky rate limit)
        log.info("Waiting 2s before tanker fetch (OpenSky rate limit)...")
        await asyncio.sleep(2)
        tanker_result = await fetch_tanker_activity(session)

    # 5. Pentagon (no API call)
    pentagon_result = fetch_pentagon_data()

    # Use fallback data from previous cycle where fetches failed
    news_data = news_result or current_data.get("news", {}).get("raw_data", {})
    connectivity_data = connectivity_result or current_data.get("connectivity", {}).get("raw_data", {})
    aviation_data = aviation_result or current_data.get("flight", {}).get("raw_data", {})
    tanker_data = tanker_result or current_data.get("tanker", {}).get("raw_data", {})
    weather_data = weather_result or current_data.get("weather", {}).get("raw_data", {})
    polymarket_data = polymarket_result or current_data.get("polymarket", {}).get("raw_data", {})

    # 6. Calculate risk scores
    scores = calculate_risk_scores(
        news_intel=news_data,
        connectivity=connectivity_data,
        aviation=aviation_data,
        tanker=tanker_data,
        weather=weather_data,
        polymarket=polymarket_data,
        pentagon_data=pentagon_result,
    )

    # 7. Update history and build final structure
    final_data = update_history(current_data, scores, raw={
        "news": news_data,
        "connectivity": connectivity_data,
        "flight": aviation_data,
        "tanker": tanker_data,
        "weather": weather_data,
        "polymarket": polymarket_data,
        "pentagon": pentagon_result,
    })

    # 8. Write data.json
    DATA_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_JSON_PATH.write_text(json.dumps(final_data, indent=2) + "\n")
    log.info("Wrote %s", DATA_JSON_PATH)

    # 9. Commit and push
    git_commit_and_push()

    log.info("Pipeline cycle complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    weather_api_key = os.environ.get("OPENWEATHER_API_KEY", "")
    cloudflare_token = os.environ.get("CLOUDFLARE_RADAR_TOKEN", "")
    if not weather_api_key:
        log.warning("OPENWEATHER_API_KEY not set — weather data will be unavailable.")
    if not cloudflare_token:
        log.warning("CLOUDFLARE_RADAR_TOKEN not set — connectivity data will be unavailable.")

    # Graceful shutdown on SIGINT / SIGTERM
    shutdown_event = asyncio.Event()

    def _handle_signal(sig, _frame):
        log.info("Received %s, shutting down after current cycle...", signal.Signals(sig).name)
        shutdown_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    async def _loop():
        while not shutdown_event.is_set():
            try:
                await run_pipeline(weather_api_key, cloudflare_token)
            except Exception:
                log.error("Unhandled error in pipeline cycle:\n%s", traceback.format_exc())

            log.info("Sleeping %d minutes until next cycle...", CYCLE_INTERVAL // 60)
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=CYCLE_INTERVAL)
            except asyncio.TimeoutError:
                pass  # Normal — timeout means it's time for the next cycle

        log.info("Shutdown complete.")

    asyncio.run(_loop())


if __name__ == "__main__":
    main()

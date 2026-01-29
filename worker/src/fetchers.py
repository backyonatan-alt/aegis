"""Async API fetchers for the Aegis data pipeline.

Uses the built-in js.fetch (Cloudflare Workers runtime) for HTTP requests
instead of httpx/requests, since Python Workers run on Pyodide (WASM).
"""

import hashlib
import json
import logging
import re
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from js import Headers, Request, fetch

from constants import (
    ALERT_KEYWORDS,
    IRAN_KEYWORDS,
    MONTHS,
    NEGATIVE_KEYWORDS,
    PIZZA_PLACES,
    STRIKE_KEYWORDS,
    TANKER_PREFIXES,
    USAF_HEX_END,
    USAF_HEX_START,
)

log = logging.getLogger("aegis.fetchers")


async def fetch_polymarket_odds() -> dict | None:
    """Fetch Iran strike odds from Polymarket Gamma API."""
    try:
        log.info("=" * 50)
        log.info("POLYMARKET ODDS")
        log.info("=" * 50)

        response = await fetch("https://gamma-api.polymarket.com/public-search?q=iran")

        if response.status != 200:
            log.warning("Polymarket API error: %d", response.status)
            return None

        data = json.loads(await response.text())

        if isinstance(data, dict) and data.get("events"):
            events = data["events"]
        elif isinstance(data, dict) and data.get("data"):
            events = data["data"]
        elif isinstance(data, list):
            events = data
        else:
            log.warning(
                "Unexpected Polymarket response format: %s, keys: %s",
                type(data).__name__,
                list(data.keys()) if isinstance(data, dict) else "N/A",
            )
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
                                log.info(
                                    "    Market date %s is within 7 days",
                                    market_date.strftime("%Y-%m-%d"),
                                )
                                return True
                            else:
                                log.debug(
                                    "    Market date %s is too far away (>7 days)",
                                    market_date.strftime("%Y-%m-%d"),
                                )
                        except ValueError:
                            pass
            return False

        # First pass: specific strike markets
        for event in events:
            event_title = (event.get("title") or "").lower()

            if (
                "will us or israel strike iran" in event_title
                or "us strikes iran by" in event_title
            ):
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
                if "iran" in market_question and any(
                    kw in market_question for kw in STRIKE_KEYWORDS
                ):
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


async def fetch_news_intel() -> dict | None:
    """Fetch Iran-related news from RSS feeds."""
    try:
        log.info("=" * 50)
        log.info("NEWS INTELLIGENCE")
        log.info("=" * 50)

        from constants import RSS_FEEDS

        all_articles = []
        alert_count = 0

        for feed_url in RSS_FEEDS:
            try:
                log.info("  Fetching %s...", feed_url[:50])
                headers = Headers.new(
                    {"User-Agent": "Mozilla/5.0 (compatible; StrikeRadar/1.0)"}.items()
                )
                req = Request.new(feed_url, headers=headers)
                response = await fetch(req)
                if not response.ok:
                    log.warning("    Failed: %d", response.status)
                    continue

                content = await response.text()
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
        seen = set()
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


async def fetch_aviation_data() -> dict | None:
    """Fetch OpenSky Network data for aircraft over Iran."""
    try:
        log.info("=" * 50)
        log.info("AVIATION TRACKING")
        log.info("=" * 50)

        url = "https://opensky-network.org/api/states/all?lamin=25&lomin=44&lamax=40&lomax=64"
        response = await fetch(url)
        if not response.ok:
            log.warning("OpenSky API error: %d", response.status)
            return None

        data = json.loads(await response.text())
        civil_count = 0
        airlines = []

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


async def fetch_tanker_activity() -> dict | None:
    """Fetch US military tanker activity in Middle East."""
    try:
        log.info("=" * 50)
        log.info("TANKER ACTIVITY")
        log.info("=" * 50)

        url = "https://opensky-network.org/api/states/all?lamin=20&lomin=40&lamax=40&lomax=65"
        response = await fetch(url)
        if not response.ok:
            log.warning("OpenSky API error: %d", response.status)
            return None

        data = json.loads(await response.text())
        tanker_count = 0
        tanker_callsigns = []

        if data.get("states") and isinstance(data["states"], list):
            for aircraft in data["states"]:
                icao = aircraft[0]
                callsign = (aircraft[1] or "").strip().upper()

                try:
                    icao_num = int(icao, 16)
                    is_us_military = USAF_HEX_START <= icao_num <= USAF_HEX_END
                except Exception:
                    is_us_military = False

                is_tanker_callsign = any(
                    callsign.startswith(prefix) for prefix in TANKER_PREFIXES
                )
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


async def fetch_weather_data(api_key: str) -> dict | None:
    """Fetch weather conditions for Tehran."""
    try:
        log.info("=" * 50)
        log.info("WEATHER CONDITIONS")
        log.info("=" * 50)

        url = f"https://api.openweathermap.org/data/2.5/weather?lat=35.6892&lon=51.389&appid={api_key}&units=metric"
        response = await fetch(url)
        if not response.ok:
            log.warning("Weather API error: %d", response.status)
            return None

        data = json.loads(await response.text())
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
            day_hash = int(
                hashlib.md5(f"{now.date()}".encode()).hexdigest()[:8], 16
            )
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

    # Calculate activity score
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

    # Determine risk contribution (max 10)
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

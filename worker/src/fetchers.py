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
    ALPHA_VANTAGE_BASE_URL,
    CLOUDFLARE_RADAR_BASE_URL,
    CLOUDFLARE_RADAR_LOCATION,
    ENERGY_CRITICAL_THRESHOLD,
    ENERGY_VOLATILE_THRESHOLD,
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


async def fetch_cloudflare_connectivity(api_token: str) -> dict | None:
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

        # Request 1 day of data (8h is not a valid dateRange)
        url = (
            f"{CLOUDFLARE_RADAR_BASE_URL}/http/timeseries"
            f"?location={CLOUDFLARE_RADAR_LOCATION}"
            f"&dateRange=1d"
        )

        headers = Headers.new(
            {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            }.items()
        )
        req = Request.new(url, headers=headers)
        response = await fetch(req)

        if response.status != 200:
            log.warning("Cloudflare Radar API error: %d", response.status)
            # Return stale status indicator
            return {
                "status": "STALE",
                "risk": 0,
                "trend": 0,
                "values": [],
                "timestamp": datetime.now().isoformat(),
                "error": f"API returned {response.status}",
            }

        data = json.loads(await response.text())

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

        # Parse values (0-1 normalized scale where 1 = max traffic)
        parsed_values = []
        for v in values:
            try:
                parsed_values.append(float(v))
            except (ValueError, TypeError):
                continue

        log.info("Received %d data points", len(parsed_values))

        if len(parsed_values) < 8:
            log.warning("Not enough data points")
            return {
                "status": "STALE",
                "risk": 0,
                "trend": 0,
                "values": parsed_values,
                "timestamp": datetime.now().isoformat(),
                "error": "Not enough data points",
            }

        # Calculate baseline (average of first 75% of data) vs recent (last 25%)
        split_point = int(len(parsed_values) * 0.75)
        baseline_values = parsed_values[:split_point]
        recent_values = parsed_values[split_point:]

        baseline_avg = sum(baseline_values) / len(baseline_values)
        recent_avg = sum(recent_values) / len(recent_values)

        # Calculate percentage change from baseline
        if baseline_avg > 0:
            trend = (recent_avg - baseline_avg) / baseline_avg
        else:
            trend = 0

        log.info("Baseline avg: %.3f, Recent avg: %.3f, Change: %.1f%%",
                 baseline_avg, recent_avg, trend * 100)

        # Determine risk based on traffic drop thresholds
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


async def fetch_energy_data(api_key: str, debug_price: float | None = None) -> dict | None:
    """Fetch Brent Crude oil price data from Alpha Vantage API.

    Calculates the Energy Volatility Index based on rate of change
    relative to the 24-hour moving average. Only tracks upside volatility
    (price drops result in 0% risk contribution).

    Args:
        api_key: Alpha Vantage API key.
        debug_price: Optional debug/simulation price to inject for testing.

    Returns:
        Dict with price, volatility index, and market status.
    """
    try:
        log.info("=" * 50)
        log.info("ENERGY MARKETS")
        log.info("=" * 50)

        now = datetime.now()

        # Check if oil markets are closed (weekends)
        # Oil markets trade Sunday 5pm EST to Friday 5pm EST
        # Simplified: consider Saturday and Sunday before 5pm as closed
        is_weekend = now.weekday() >= 5  # Saturday=5, Sunday=6

        # Debug mode: inject fake price for testing
        if debug_price is not None:
            log.info("DEBUG MODE: Using injected price $%.2f", debug_price)
            return _calculate_energy_metrics(
                current_price=debug_price,
                prices_history=[debug_price * 0.95] * 7,  # Simulate 5% below for testing
                is_market_closed=False,
                is_debug=True,
                now=now,
            )

        if not api_key:
            log.warning("Alpha Vantage API key not configured")
            return {
                "status": "STALE",
                "risk": 0,
                "price": 0,
                "change_pct": 0,
                "volatility_index": 0,
                "market_closed": is_weekend,
                "timestamp": now.isoformat(),
                "error": "API key not configured",
            }

        # Fetch Brent Crude daily prices (Alpha Vantage commodities API)
        # Note: Commodities only support daily/weekly/monthly, not intraday
        url = (
            f"{ALPHA_VANTAGE_BASE_URL}"
            f"?function=BRENT"
            f"&interval=daily"
            f"&apikey={api_key}"
        )

        log.info("Fetching Brent Crude from Alpha Vantage...")
        response = await fetch(url)

        if response.status != 200:
            log.warning("Alpha Vantage API error: %d", response.status)
            return {
                "status": "STALE",
                "risk": 0,
                "price": 0,
                "change_pct": 0,
                "volatility_index": 0,
                "market_closed": is_weekend,
                "timestamp": now.isoformat(),
                "error": f"API returned {response.status}",
            }

        data = json.loads(await response.text())

        # Check for API error messages
        if "Error Message" in data or "Note" in data or "Information" in data:
            error_msg = data.get("Error Message") or data.get("Note") or data.get("Information", "API limit reached")
            log.warning("Alpha Vantage API message: %s", error_msg[:100])
            return {
                "status": "STALE",
                "risk": 0,
                "price": 0,
                "change_pct": 0,
                "volatility_index": 0,
                "market_closed": is_weekend,
                "timestamp": now.isoformat(),
                "error": error_msg[:100],
            }

        # Parse BRENT commodity data (returns "data" array, not time series)
        price_data = data.get("data", [])
        if not price_data:
            log.warning("No price data in Alpha Vantage BRENT response")
            return {
                "status": "STALE",
                "risk": 0,
                "price": 0,
                "change_pct": 0,
                "volatility_index": 0,
                "market_closed": is_weekend,
                "timestamp": now.isoformat(),
                "error": "No price data",
            }

        # Extract prices (most recent first - data is already sorted desc)
        # Use last 7 days for moving average (daily data, not intraday)
        prices = []
        for item in price_data[:7]:  # Last 7 days
            try:
                value = item.get("value")
                if value and value != ".":
                    prices.append(float(value))
            except (KeyError, ValueError, TypeError):
                continue

        if len(prices) < 2:
            log.warning("Not enough price data points")
            return {
                "status": "STALE",
                "risk": 0,
                "price": 0,
                "change_pct": 0,
                "volatility_index": 0,
                "market_closed": is_weekend,
                "timestamp": now.isoformat(),
                "error": "Insufficient data points",
            }

        current_price = prices[0]
        return _calculate_energy_metrics(
            current_price=current_price,
            prices_history=prices,
            is_market_closed=is_weekend,
            is_debug=False,
            now=now,
        )

    except Exception as e:
        log.error("Energy data fetch error: %s", e)
        log.debug(traceback.format_exc())
        return None


def _calculate_energy_metrics(
    current_price: float,
    prices_history: list[float],
    is_market_closed: bool,
    is_debug: bool,
    now: datetime,
) -> dict:
    """Calculate energy volatility metrics from price data.

    Args:
        current_price: Most recent oil price.
        prices_history: List of recent prices (7 days for daily data).
        is_market_closed: Whether markets are closed (weekend).
        is_debug: Whether this is a debug/simulation run.
        now: Current datetime.

    Returns:
        Dict with calculated energy metrics.
    """
    # Calculate moving average from historical prices
    avg_price = sum(prices_history) / len(prices_history)

    # Calculate percentage change from moving average
    if avg_price > 0:
        change_pct = (current_price - avg_price) / avg_price
    else:
        change_pct = 0

    # Only track UPSIDE volatility (positive bias)
    # Price drops result in 0% risk contribution
    if change_pct < 0:
        change_pct = 0
        volatility_index = 0
    else:
        # Normalize: 5% jump = 1.0 (Critical)
        volatility_index = min(1.0, change_pct / ENERGY_CRITICAL_THRESHOLD)

    # Determine status based on thresholds
    if is_market_closed:
        status = "MARKET CLOSED"
    elif change_pct >= ENERGY_CRITICAL_THRESHOLD:
        status = "CRITICAL"
    elif change_pct >= ENERGY_VOLATILE_THRESHOLD:
        status = "VOLATILE"
    else:
        status = "STABLE"

    # Calculate risk contribution (0-100 scale)
    risk = round(volatility_index * 100)

    log.info("Price: $%.2f, Avg: $%.2f, Change: %.2f%%",
             current_price, avg_price, change_pct * 100)
    log.info("Status: %s, Volatility Index: %.2f, Risk: %d%%",
             status, volatility_index, risk)

    return {
        "status": status,
        "risk": risk,
        "price": round(current_price, 2),
        "avg_price": round(avg_price, 2),
        "change_pct": round(change_pct * 100, 2),
        "volatility_index": round(volatility_index, 3),
        "market_closed": is_market_closed,
        "is_debug": is_debug,
        "prices_history": [round(p, 2) for p in prices_history[:7]],
        "timestamp": now.isoformat(),
    }

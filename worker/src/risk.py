"""Risk calculation and history management. Pure computation, no I/O."""

import logging
from datetime import datetime

log = logging.getLogger("aegis.risk")


def calculate_risk_scores(
    news_intel: dict,
    connectivity: dict,
    aviation: dict,
    tanker: dict,
    weather: dict,
    polymarket: dict,
    pentagon_data: dict,
    energy: dict | None = None,
) -> dict:
    """Calculate all risk scores and return the signal data dict.

    Takes raw API results (not accumulated data) for each signal.
    Returns a dict with per-signal risk/detail and total_risk.
    """

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
    # Display risk: Scale the 0-25 risk contribution to 0-95 for display
    connectivity_display_risk = min(95, round(connectivity_risk * 3.8))
    if connectivity_status == "STALE":
        connectivity_detail = "Data unavailable"
    else:
        connectivity_detail = f"{connectivity_status} ({connectivity_trend:+.1f}%)"
    log.info("  Connect:    %d%% (%s)", connectivity_display_risk, connectivity_detail)

    # FLIGHT
    aircraft_count = aviation.get("aircraft_count", 0)
    flight_risk = max(3, 95 - round(aircraft_count * 0.8))
    flight_detail = f"{round(aircraft_count)} aircraft over Iran"
    log.info("  Flight:     %d%% (%s)", flight_risk, flight_detail)

    # TANKER
    tanker_count = tanker.get("tanker_count", 0)
    tanker_risk = round((tanker_count / 10) * 100)
    tanker_display_count = round(tanker_count / 4)
    tanker_detail = f"{tanker_display_count} detected in region"
    log.info("  Tanker:     %d%% (%s)", tanker_risk, tanker_detail)

    # WEATHER - use fresh API result directly, not accumulated data
    clouds = weather.get("clouds", 0)
    weather_risk = max(0, min(100, 100 - (max(0, clouds - 6) * 10)))
    weather_detail = weather.get("description", "clear")
    log.info("  Weather:    %d%% (%s)", weather_risk, weather_detail)

    # POLYMARKET
    polymarket_odds = min(100, max(0, polymarket.get("odds", 0) if polymarket else 0))
    if polymarket_odds > 95:
        polymarket_odds = 0
    polymarket_contribution = min(10, polymarket_odds * 0.1)
    polymarket_display_risk = polymarket_odds if polymarket_odds > 0 else 10
    polymarket_detail = (
        f"{polymarket_odds}% odds" if polymarket_odds > 0 else "Awaiting data..."
    )
    log.info("  Polymarket: %d%% (%s)", polymarket_display_risk, polymarket_detail)

    # PENTAGON
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

    # ENERGY MARKETS (15% weight)
    # When markets are closed or data is stale, risk = 0 to avoid affecting the gauge
    if energy:
        energy_status = energy.get("status", "STABLE")
        energy_price = energy.get("price", 0)
        energy_change = energy.get("change_pct", 0)
        energy_market_closed = energy.get("market_closed", False)

        if energy_status == "STALE":
            energy_display_risk = 0  # Don't affect gauge when data unavailable
            energy_detail = "Data unavailable"
        elif energy_market_closed:
            energy_display_risk = 0  # Don't affect gauge when markets closed
            energy_detail = f"${energy_price:.2f} (Market Closed)"
        else:
            energy_display_risk = energy.get("risk", 0)
            energy_detail = f"${energy_price:.2f} ({energy_change:+.1f}%)"
    else:
        energy_status = "STABLE"
        energy_display_risk = 0
        energy_detail = "Awaiting data..."
        energy_market_closed = False
    log.info("  Energy:     %d%% (%s)", energy_display_risk, energy_detail)

    # Weighted contributions (v3.0 weights per Black Gold PRD)
    # News: 17%, Connectivity: 17%, Energy: 15%, Aviation: 13%, Tanker: 13%,
    # Market: 13%, Pentagon: 8%, Weather: 4%
    news_weighted = news_display_risk * 0.17
    connectivity_weighted = connectivity_display_risk * 0.17
    energy_weighted = energy_display_risk * 0.15
    flight_weighted = flight_risk * 0.13
    tanker_weighted = tanker_risk * 0.13
    polymarket_weighted = polymarket_display_risk * 0.13
    pentagon_weighted = pentagon_display_risk * 0.08
    weather_weighted = weather_risk * 0.04

    log.info("  Weighted: news=%.1f conn=%.1f energy=%.1f flight=%.1f tanker=%.1f poly=%.1f pent=%.1f weather=%.1f",
             news_weighted, connectivity_weighted, energy_weighted, flight_weighted, tanker_weighted,
             polymarket_weighted, pentagon_weighted, weather_weighted)

    total_risk = (
        news_weighted
        + connectivity_weighted
        + energy_weighted
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
        energy_display_risk > 40,  # VOLATILE or higher
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
        "energy": {"risk": energy_display_risk, "detail": energy_detail},
        "flight": {"risk": flight_risk, "detail": flight_detail},
        "tanker": {"risk": tanker_risk, "detail": tanker_detail},
        "weather": {"risk": weather_risk, "detail": weather_detail},
        "polymarket": {"risk": polymarket_display_risk, "detail": polymarket_detail},
        "pentagon": {"risk": pentagon_display_risk, "detail": pentagon_detail},
        "total_risk": total_risk,
        "elevated_count": elevated_count,
    }


def update_history(current_data: dict, scores: dict, raw: dict) -> dict:
    """Update signal histories and total risk history, return the final JSON structure.

    Args:
        current_data: Existing data from R2 (for preserving history).
        scores: Output from calculate_risk_scores().
        raw: Dict of raw API results keyed by signal name.
    """

    # Extract existing histories
    if "total_risk" in current_data and "history" in current_data.get("total_risk", {}):
        history = current_data["total_risk"]["history"]
        signal_history = {
            sig: current_data.get(sig, {}).get("history", [])
            for sig in ["news", "connectivity", "energy", "flight", "tanker", "pentagon", "polymarket", "weather"]
        }
    else:
        history = current_data.get("history", [])
        signal_history = current_data.get("signalHistory", {
            "news": [], "connectivity": [], "energy": [], "flight": [], "tanker": [],
            "pentagon": [], "polymarket": [], "weather": [],
        })

    # Append current scores to signal histories
    for sig in ["news", "connectivity", "energy", "flight", "tanker", "pentagon", "polymarket", "weather"]:
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

    # Build final JSON structure
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
        "energy": {
            "risk": scores["energy"]["risk"],
            "detail": scores["energy"]["detail"],
            "history": signal_history["energy"],
            "raw_data": raw.get("energy", {}),
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

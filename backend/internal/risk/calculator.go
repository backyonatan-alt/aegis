package risk

import (
	"fmt"
	"log/slog"
	"math"

	"github.com/backyonatan-alt/aegis/backend/internal/model"
)

// Calculate computes risk scores for all signals and returns a RiskScores struct.
func Calculate(
	news model.NewsData,
	connectivity model.ConnectivityData,
	aviation model.AviationData,
	tanker model.TankerData,
	weather model.WeatherData,
	polymarket model.PolymarketData,
	pentagon model.PentagonData,
) model.RiskScores {
	slog.Info("calculating risk scores")

	// NEWS (20% weight)
	articles := news.TotalCount
	alertCount := news.AlertCount
	alertRatio := 0.0
	if articles > 0 {
		alertRatio = float64(alertCount) / float64(articles)
	}
	newsDisplayRisk := int(math.Max(3, math.Round(math.Pow(alertRatio, 2)*85)))
	newsDetail := fmt.Sprintf("%d articles, %d critical", articles, alertCount)
	slog.Info("risk: news", "risk", newsDisplayRisk, "detail", newsDetail)

	// DIGITAL CONNECTIVITY (20% weight)
	connStatus := connectivity.Status
	if connStatus == "" {
		connStatus = "STABLE"
	}
	connRisk := connectivity.Risk
	connTrend := connectivity.Trend
	connDisplayRisk := int(math.Min(95, math.Round(connRisk*3.8)))
	var connDetail string
	if connStatus == "STALE" {
		connDetail = "Data unavailable"
	} else {
		connDetail = fmt.Sprintf("%s (%+.1f%%)", connStatus, connTrend)
	}
	slog.Info("risk: connectivity", "risk", connDisplayRisk, "detail", connDetail)

	// FLIGHT (15% weight)
	aircraftCount := aviation.AircraftCount
	flightRisk := int(math.Max(3, 95-math.Round(float64(aircraftCount)*0.8)))
	flightDetail := fmt.Sprintf("%d aircraft over Iran", aircraftCount)
	slog.Info("risk: flight", "risk", flightRisk, "detail", flightDetail)

	// TANKER (15% weight)
	tankerCount := tanker.TankerCount
	tankerRisk := int(math.Round(float64(tankerCount) / 10 * 100))
	tankerDisplayCount := int(math.Round(float64(tankerCount) / 4))
	tankerDetail := fmt.Sprintf("%d detected in region", tankerDisplayCount)
	slog.Info("risk: tanker", "risk", tankerRisk, "detail", tankerDetail)

	// WEATHER (5% weight)
	clouds := weather.Clouds
	weatherRisk := int(math.Max(0, math.Min(100, float64(100-(int(math.Max(0, float64(clouds-6)))*10)))))
	weatherDetail := weather.Description
	if weatherDetail == "" {
		weatherDetail = "clear"
	}
	slog.Info("risk: weather", "risk", weatherRisk, "detail", weatherDetail)

	// POLYMARKET (15% weight)
	polyOdds := polymarket.Odds
	if polyOdds < 0 {
		polyOdds = 0
	}
	if polyOdds > 100 {
		polyOdds = 100
	}
	if polyOdds > 95 {
		polyOdds = 0
	}
	polyDisplayRisk := polyOdds
	if polyOdds == 0 {
		polyDisplayRisk = 10
	}
	var polyDetail string
	if polyOdds > 0 {
		polyDetail = fmt.Sprintf("%d%% odds", polyOdds)
	} else {
		polyDetail = "Awaiting data..."
	}
	slog.Info("risk: polymarket", "risk", polyDisplayRisk, "detail", polyDetail)

	// PENTAGON (10% weight)
	pentagonContrib := pentagon.RiskContribution
	pentagonDisplayRisk := int(math.Round(float64(pentagonContrib) / 10 * 100))
	pentagonStatus := pentagon.Status
	if pentagonStatus == "" {
		pentagonStatus = "Normal"
	}
	pentagonDetail := pentagonStatus
	if pentagon.IsLateNight {
		pentagonDetail += " (late night)"
	}
	if pentagon.IsWeekend {
		pentagonDetail += " (weekend)"
	}
	slog.Info("risk: pentagon", "risk", pentagonDisplayRisk, "detail", pentagonDetail)

	// Weighted contributions
	newsWeighted := float64(newsDisplayRisk) * 0.20
	connWeighted := float64(connDisplayRisk) * 0.20
	flightWeighted := float64(flightRisk) * 0.15
	tankerWeighted := float64(tankerRisk) * 0.15
	polyWeighted := float64(polyDisplayRisk) * 0.15
	pentagonWeighted := float64(pentagonDisplayRisk) * 0.10
	weatherWeighted := float64(weatherRisk) * 0.05

	totalRisk := newsWeighted + connWeighted + flightWeighted + tankerWeighted +
		polyWeighted + pentagonWeighted + weatherWeighted

	// Escalation multiplier
	elevatedCount := 0
	if newsDisplayRisk > 30 {
		elevatedCount++
	}
	if connRisk >= 10 {
		elevatedCount++
	}
	if flightRisk > 50 {
		elevatedCount++
	}
	if tankerRisk > 30 {
		elevatedCount++
	}
	if polyDisplayRisk > 30 {
		elevatedCount++
	}
	if pentagonDisplayRisk > 50 {
		elevatedCount++
	}
	if weatherRisk > 70 {
		elevatedCount++
	}

	if elevatedCount >= 3 {
		slog.Info("escalation triggered", "elevated_signals", elevatedCount)
		totalRisk = math.Min(100, totalRisk*1.15)
	}

	totalRiskInt := int(math.Min(100, math.Max(0, math.Round(totalRisk))))
	slog.Info("total risk", "risk", totalRiskInt, "elevated", elevatedCount)

	return model.RiskScores{
		News:         model.SignalScore{Risk: newsDisplayRisk, Detail: newsDetail},
		Connectivity: model.SignalScore{Risk: connDisplayRisk, Detail: connDetail},
		Flight:       model.SignalScore{Risk: flightRisk, Detail: flightDetail},
		Tanker:       model.SignalScore{Risk: tankerRisk, Detail: tankerDetail},
		Weather:      model.SignalScore{Risk: weatherRisk, Detail: weatherDetail},
		Polymarket:   model.SignalScore{Risk: polyDisplayRisk, Detail: polyDetail},
		Pentagon:     model.SignalScore{Risk: pentagonDisplayRisk, Detail: pentagonDetail},
		TotalRisk:    totalRiskInt,
		ElevatedCount: elevatedCount,
	}
}

package risk

import (
	"log/slog"
	"time"

	"github.com/backyonatan-alt/aegis/backend/internal/model"
)

// UpdateHistory takes existing snapshot data, new scores, and raw API data,
// and produces the final Snapshot with updated histories.
func UpdateHistory(current map[string]any, scores model.RiskScores, raw model.RawResults) model.Snapshot {
	now := time.Now()

	// Extract existing signal histories
	signalHistory := map[string][]int{
		"news": {}, "connectivity": {}, "flight": {}, "tanker": {},
		"pentagon": {}, "polymarket": {}, "weather": {},
	}

	// Extract existing total risk history
	var totalRiskHistory []model.TotalRiskPoint

	if current != nil {
		// Try new format: total_risk.history
		if tr, ok := current["total_risk"].(map[string]any); ok {
			if hist, ok := tr["history"].([]any); ok {
				for _, item := range hist {
					if mp, ok := item.(map[string]any); ok {
						point := model.TotalRiskPoint{
							Timestamp: int64(getFloat64(mp, "timestamp")),
							Risk:      getIntVal(mp, "risk"),
							Pinned:    getBoolVal(mp, "pinned"),
						}
						totalRiskHistory = append(totalRiskHistory, point)
					}
				}
			}
		}

		// Extract signal histories
		for sig := range signalHistory {
			if sigData, ok := current[sig].(map[string]any); ok {
				if hist, ok := sigData["history"].([]any); ok {
					for _, v := range hist {
						if n, ok := v.(float64); ok {
							signalHistory[sig] = append(signalHistory[sig], int(n))
						}
					}
				}
			}
		}

		// Fallback to old format
		if totalRiskHistory == nil {
			if hist, ok := current["history"].([]any); ok {
				for _, item := range hist {
					if mp, ok := item.(map[string]any); ok {
						point := model.TotalRiskPoint{
							Timestamp: int64(getFloat64(mp, "timestamp")),
							Risk:      getIntVal(mp, "risk"),
							Pinned:    getBoolVal(mp, "pinned"),
						}
						totalRiskHistory = append(totalRiskHistory, point)
					}
				}
			}
		}
	}

	// Append current scores to signal histories
	signalScores := map[string]int{
		"news":         scores.News.Risk,
		"connectivity": scores.Connectivity.Risk,
		"flight":       scores.Flight.Risk,
		"tanker":       scores.Tanker.Risk,
		"pentagon":     scores.Pentagon.Risk,
		"polymarket":   scores.Polymarket.Risk,
		"weather":      scores.Weather.Risk,
	}

	for sig, risk := range signalScores {
		signalHistory[sig] = append(signalHistory[sig], risk)
		if len(signalHistory[sig]) > 20 {
			signalHistory[sig] = signalHistory[sig][len(signalHistory[sig])-20:]
		}
	}

	// Total risk history management (12h pinning)
	currentTimestamp := now.UnixMilli()
	totalRisk := scores.TotalRisk

	var currentBoundary time.Time
	if now.Hour() >= 12 {
		currentBoundary = time.Date(now.Year(), now.Month(), now.Day(), 12, 0, 0, 0, now.Location())
	} else {
		currentBoundary = time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, now.Location())
	}
	currentBoundaryTS := currentBoundary.UnixMilli()

	if len(totalRiskHistory) > 0 {
		lastPoint := totalRiskHistory[len(totalRiskHistory)-1]
		crossedBoundary := lastPoint.Timestamp < currentBoundaryTS

		if crossedBoundary {
			slog.Info("history: crossed 12h boundary, pinning + adding new point")
			if len(totalRiskHistory) > 0 {
				totalRiskHistory = totalRiskHistory[1:]
			}
			if len(totalRiskHistory) > 0 {
				totalRiskHistory[len(totalRiskHistory)-1] = model.TotalRiskPoint{
					Timestamp: currentBoundaryTS,
					Risk:      lastPoint.Risk,
					Pinned:    true,
				}
			}
			totalRiskHistory = append(totalRiskHistory, model.TotalRiskPoint{
				Timestamp: currentTimestamp,
				Risk:      totalRisk,
			})
		} else {
			slog.Info("history: updating last point in-place")
			totalRiskHistory[len(totalRiskHistory)-1] = model.TotalRiskPoint{
				Timestamp: currentTimestamp,
				Risk:      totalRisk,
			}
		}
	} else {
		slog.Info("history: starting fresh with single point")
		totalRiskHistory = []model.TotalRiskPoint{
			{Timestamp: currentTimestamp, Risk: totalRisk},
		}
	}

	slog.Info("history points", "count", len(totalRiskHistory))

	// Build final snapshot
	return model.Snapshot{
		News: model.Signal{
			Risk:    scores.News.Risk,
			Detail:  scores.News.Detail,
			History: signalHistory["news"],
			RawData: ensureMap(raw.News),
		},
		Connectivity: model.Signal{
			Risk:    scores.Connectivity.Risk,
			Detail:  scores.Connectivity.Detail,
			History: signalHistory["connectivity"],
			RawData: ensureMap(raw.Connectivity),
		},
		Flight: model.Signal{
			Risk:    scores.Flight.Risk,
			Detail:  scores.Flight.Detail,
			History: signalHistory["flight"],
			RawData: ensureMap(raw.Flight),
		},
		Tanker: model.Signal{
			Risk:    scores.Tanker.Risk,
			Detail:  scores.Tanker.Detail,
			History: signalHistory["tanker"],
			RawData: ensureMap(raw.Tanker),
		},
		Weather: model.Signal{
			Risk:    scores.Weather.Risk,
			Detail:  scores.Weather.Detail,
			History: signalHistory["weather"],
			RawData: ensureMap(raw.Weather),
		},
		Polymarket: model.Signal{
			Risk:    scores.Polymarket.Risk,
			Detail:  scores.Polymarket.Detail,
			History: signalHistory["polymarket"],
			RawData: ensureMap(raw.Polymarket),
		},
		Pentagon: model.Signal{
			Risk:    scores.Pentagon.Risk,
			Detail:  scores.Pentagon.Detail,
			History: signalHistory["pentagon"],
			RawData: ensureMap(raw.Pentagon),
		},
		TotalRisk: model.TotalRisk{
			Risk:          totalRisk,
			History:       totalRiskHistory,
			ElevatedCount: scores.ElevatedCount,
		},
		LastUpdated: now.Format(time.RFC3339),
	}
}

func getFloat64(m map[string]any, key string) float64 {
	if v, ok := m[key]; ok {
		switch n := v.(type) {
		case float64:
			return n
		case int:
			return float64(n)
		}
	}
	return 0
}

func getIntVal(m map[string]any, key string) int {
	if v, ok := m[key]; ok {
		switch n := v.(type) {
		case float64:
			return int(n)
		case int:
			return n
		}
	}
	return 0
}

func getBoolVal(m map[string]any, key string) bool {
	if v, ok := m[key]; ok {
		if b, ok := v.(bool); ok {
			return b
		}
	}
	return false
}

func ensureMap(m map[string]any) map[string]any {
	if m == nil {
		return map[string]any{}
	}
	return m
}

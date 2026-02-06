package fetcher

import (
	"crypto/md5"
	"fmt"
	"log/slog"
	"math"
	"strconv"
	"time"

	"github.com/backyonatan-alt/aegis/backend/internal/model"
)

func (f *Fetcher) fetchPentagon() (model.PentagonData, map[string]any) {
	slog.Info("computing pentagon pizza meter")

	now := time.Now()
	currentHour := now.Hour()
	currentDay := now.Weekday() // Sunday=0, need Monday=0

	// Convert to Python weekday (Monday=0, Sunday=6)
	pyWeekday := int(currentDay+6) % 7

	var busynessData []map[string]any

	for _, place := range pizzaPlaces {
		baseScore := 30
		status := "normal"

		if currentHour >= 11 && currentHour <= 14 && pyWeekday < 5 {
			baseScore = 50
		} else if currentHour >= 17 && currentHour <= 20 {
			baseScore = 55
		} else if currentHour >= 22 || currentHour < 6 {
			dateStr := now.Format("2006-01-02")
			hash := md5.Sum([]byte(dateStr))
			hexStr := fmt.Sprintf("%x", hash[:4])
			dayHash, _ := strconv.ParseInt(hexStr, 16, 64)
			if dayHash%10 < 2 {
				baseScore = 70
				status = "elevated_late"
			} else {
				baseScore = 20
			}
		} else if pyWeekday >= 5 {
			baseScore = 25
		}

		busynessData = append(busynessData, map[string]any{
			"name":   place.Name,
			"status": status,
			"score":  baseScore,
		})
		slog.Info("pentagon place", "name", place.Name, "status", status, "score", baseScore)
	}

	isLateNight := currentHour >= 22 || currentHour < 6
	isWeekend := pyWeekday >= 5

	totalScore := 0.0
	validReadings := 0

	for _, place := range busynessData {
		score := place["score"].(int)
		validReadings++
		if isLateNight && score > 60 {
			totalScore += float64(score) * 1.5
		} else if isWeekend && score > 70 {
			totalScore += float64(score) * 1.3
		} else {
			totalScore += float64(score)
		}
	}

	activityScore := 30
	if validReadings > 0 {
		avg := totalScore / float64(validReadings)
		activityScore = int(math.Round(math.Min(100, math.Max(0, avg))))
	}

	var riskContribution int
	var pentagonStatus string
	if activityScore >= 80 {
		riskContribution = 10
		pentagonStatus = "High Activity"
	} else if activityScore >= 60 {
		riskContribution = 7
		pentagonStatus = "Elevated"
	} else if activityScore >= 40 {
		riskContribution = 3
		pentagonStatus = "Normal"
	} else {
		riskContribution = 1
		pentagonStatus = "Low Activity"
	}

	slog.Info("pentagon result", "status", pentagonStatus, "score", activityScore, "risk_contribution", riskContribution)

	result := model.PentagonData{
		Score:            activityScore,
		RiskContribution: riskContribution,
		Status:           pentagonStatus,
		Places:           busynessData,
		Timestamp:        now.Format(time.RFC3339),
		IsLateNight:      isLateNight,
		IsWeekend:        isWeekend,
	}
	rawMap := structToMap(result)
	return result, rawMap
}

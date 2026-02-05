package fetcher

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math"
	"net/http"
	"time"

	"github.com/backyonatan-alt/aegis/backend/internal/model"
)

func (f *Fetcher) fetchConnectivity() (model.ConnectivityData, map[string]any, error) {
	slog.Info("fetching digital connectivity")

	if f.cfg.CloudflareRadarToken == "" {
		return model.ConnectivityData{}, nil, fmt.Errorf("cloudflare radar token not configured")
	}

	url := fmt.Sprintf("%s/http/timeseries?location=%s&dateRange=1d",
		cloudflareRadarBaseURL, cloudflareRadarLocation)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return model.ConnectivityData{}, nil, fmt.Errorf("connectivity request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+f.cfg.CloudflareRadarToken)
	req.Header.Set("Content-Type", "application/json")

	resp, err := f.client.Do(req)
	if err != nil {
		return model.ConnectivityData{}, nil, fmt.Errorf("connectivity fetch: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		slog.Warn("cloudflare radar API error", "status", resp.StatusCode)
		stale := model.ConnectivityData{
			Status:    "STALE",
			Risk:      0,
			Trend:     0,
			Values:    nil,
			Timestamp: time.Now().Format(time.RFC3339),
			Error:     fmt.Sprintf("API returned %d", resp.StatusCode),
		}
		return stale, structToMap(stale), nil
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return model.ConnectivityData{}, nil, fmt.Errorf("connectivity read body: %w", err)
	}

	var data map[string]any
	if err := json.Unmarshal(body, &data); err != nil {
		return model.ConnectivityData{}, nil, fmt.Errorf("connectivity parse: %w", err)
	}

	// Extract timeseries values
	result, ok := data["result"].(map[string]any)
	if !ok {
		return model.ConnectivityData{Status: "STALE"}, nil, fmt.Errorf("no result in response")
	}

	series, ok := result["serie_0"].(map[string]any)
	if !ok {
		return model.ConnectivityData{Status: "STALE"}, nil, fmt.Errorf("no serie_0 in result")
	}

	rawValues, ok := series["values"].([]any)
	if !ok || len(rawValues) == 0 {
		stale := model.ConnectivityData{
			Status:    "STALE",
			Timestamp: time.Now().Format(time.RFC3339),
			Error:     "No data points returned",
		}
		return stale, structToMap(stale), nil
	}

	var parsedValues []float64
	for _, v := range rawValues {
		if f, err := toFloatSafe(v); err == nil {
			parsedValues = append(parsedValues, f)
		}
	}

	slog.Info("connectivity data points", "count", len(parsedValues))

	if len(parsedValues) < 8 {
		stale := model.ConnectivityData{
			Status:    "STALE",
			Values:    parsedValues,
			Timestamp: time.Now().Format(time.RFC3339),
			Error:     "Not enough data points",
		}
		return stale, structToMap(stale), nil
	}

	// Calculate baseline (first 75%) vs recent (last 25%)
	splitPoint := int(float64(len(parsedValues)) * 0.75)
	baselineValues := parsedValues[:splitPoint]
	recentValues := parsedValues[splitPoint:]

	baselineAvg := average(baselineValues)
	recentAvg := average(recentValues)

	var trend float64
	if baselineAvg > 0 {
		trend = (recentAvg - baselineAvg) / baselineAvg
	}

	slog.Info("connectivity analysis", "baseline", baselineAvg, "recent", recentAvg, "trend", trend*100)

	// Determine risk based on traffic drop thresholds
	var risk float64
	var status string
	if trend <= -0.90 {
		risk = 25
		status = "BLACKOUT"
	} else if trend <= -0.50 {
		risk = 20
		status = "CRITICAL"
	} else if trend <= -0.15 {
		risk = 10
		status = "ANOMALOUS"
	} else {
		risk = 0
		status = "STABLE"
	}

	slog.Info("connectivity result", "status", status, "risk", risk)

	now := time.Now()
	connData := model.ConnectivityData{
		Status:    status,
		Risk:      risk,
		Trend:     math.Round(trend*1000) / 10, // Convert to percentage with 1 decimal
		Values:    parsedValues,
		Timestamp: now.Format(time.RFC3339),
	}
	rawMap := structToMap(connData)
	return connData, rawMap, nil
}

func toFloatSafe(v any) (float64, error) {
	switch n := v.(type) {
	case float64:
		return n, nil
	case string:
		var f float64
		_, err := fmt.Sscanf(n, "%f", &f)
		return f, err
	case json.Number:
		return n.Float64()
	}
	return 0, fmt.Errorf("cannot convert %T to float64", v)
}

func average(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	sum := 0.0
	for _, v := range values {
		sum += v
	}
	return sum / float64(len(values))
}

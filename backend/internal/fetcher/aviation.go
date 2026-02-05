package fetcher

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math"
	"strconv"
	"strings"
	"time"

	"github.com/backyonatan-alt/aegis/backend/internal/model"
)

func (f *Fetcher) fetchAviation() (model.AviationData, map[string]any, error) {
	slog.Info("fetching aviation data")

	resp, err := f.client.Get("https://opensky-network.org/api/states/all?lamin=25&lomin=44&lamax=40&lomax=64")
	if err != nil {
		return model.AviationData{}, nil, fmt.Errorf("opensky request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return model.AviationData{}, nil, fmt.Errorf("opensky API error: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return model.AviationData{}, nil, fmt.Errorf("opensky read body: %w", err)
	}

	var data map[string]any
	if err := json.Unmarshal(body, &data); err != nil {
		return model.AviationData{}, nil, fmt.Errorf("opensky parse: %w", err)
	}

	civilCount := 0
	var airlines []string

	if states, ok := data["states"].([]any); ok {
		for _, s := range states {
			aircraft, ok := s.([]any)
			if !ok || len(aircraft) < 9 {
				continue
			}

			icao, _ := aircraft[0].(string)
			callsign := ""
			if cs, ok := aircraft[1].(string); ok {
				callsign = strings.TrimSpace(cs)
			}
			onGround := false
			if og, ok := aircraft[8].(bool); ok {
				onGround = og
			}

			if onGround {
				continue
			}

			// Skip USAF aircraft
			icaoNum, err := strconv.ParseInt(icao, 16, 64)
			if err == nil && icaoNum >= usafHexStart && icaoNum <= usafHexEnd {
				continue
			}

			civilCount++
			if len(callsign) >= 3 {
				code := callsign[:3]
				if !sliceContains(airlines, code) {
					airlines = append(airlines, code)
				}
			}
		}
	}

	risk := int(math.Max(3, 95-math.Round(float64(civilCount)*0.8)))
	slog.Info("aviation result", "aircraft", civilCount, "airlines", len(airlines), "risk", risk)

	if len(airlines) > 10 {
		airlines = airlines[:10]
	}

	now := time.Now()
	result := model.AviationData{
		AircraftCount: civilCount,
		AirlineCount:  len(airlines),
		Airlines:      airlines,
		Timestamp:     now.Format(time.RFC3339),
	}
	rawMap := structToMap(result)
	return result, rawMap, nil
}

func sliceContains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}

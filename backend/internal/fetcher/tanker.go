package fetcher

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"strconv"
	"strings"
	"time"

	"github.com/backyonatan-alt/aegis/backend/internal/model"
)

func (f *Fetcher) fetchTanker() (model.TankerData, map[string]any, error) {
	slog.Info("fetching tanker activity")

	resp, err := f.client.Get("https://opensky-network.org/api/states/all?lamin=20&lomin=40&lamax=40&lomax=65")
	if err != nil {
		return model.TankerData{}, nil, fmt.Errorf("opensky tanker request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return model.TankerData{}, nil, fmt.Errorf("opensky tanker API error: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return model.TankerData{}, nil, fmt.Errorf("opensky tanker read body: %w", err)
	}

	var data map[string]any
	if err := json.Unmarshal(body, &data); err != nil {
		return model.TankerData{}, nil, fmt.Errorf("opensky tanker parse: %w", err)
	}

	tankerCount := 0
	var tankerCallsigns []string

	if states, ok := data["states"].([]any); ok {
		for _, s := range states {
			aircraft, ok := s.([]any)
			if !ok || len(aircraft) < 2 {
				continue
			}

			icao, _ := aircraft[0].(string)
			callsign := ""
			if cs, ok := aircraft[1].(string); ok {
				callsign = strings.TrimSpace(strings.ToUpper(cs))
			}

			// Check if USAF
			icaoNum, err := strconv.ParseInt(icao, 16, 64)
			if err != nil {
				continue
			}
			isUSMilitary := icaoNum >= usafHexStart && icaoNum <= usafHexEnd
			if !isUSMilitary {
				continue
			}

			// Check if tanker callsign
			isTankerCallsign := false
			for _, prefix := range tankerPrefixes {
				if strings.HasPrefix(callsign, prefix) {
					isTankerCallsign = true
					break
				}
			}
			hasKCPattern := strings.Contains(callsign, "KC") || strings.Contains(callsign, "TANKER")

			if isTankerCallsign || hasKCPattern {
				tankerCount++
				if callsign != "" {
					tankerCallsigns = append(tankerCallsigns, callsign)
				}
			}
		}
	}

	slog.Info("tanker result", "count", tankerCount, "callsigns", tankerCallsigns)

	if len(tankerCallsigns) > 5 {
		tankerCallsigns = tankerCallsigns[:5]
	}

	now := time.Now()
	result := model.TankerData{
		TankerCount: tankerCount,
		Callsigns:   tankerCallsigns,
		Timestamp:   now.Format(time.RFC3339),
	}
	rawMap := structToMap(result)
	return result, rawMap, nil
}

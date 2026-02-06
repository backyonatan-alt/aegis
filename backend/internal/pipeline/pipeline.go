package pipeline

import (
	"context"
	"encoding/json"
	"log/slog"
	"time"

	"golang.org/x/sync/errgroup"

	"github.com/backyonatan-alt/aegis/backend/internal/cache"
	"github.com/backyonatan-alt/aegis/backend/internal/fetcher"
	"github.com/backyonatan-alt/aegis/backend/internal/model"
	"github.com/backyonatan-alt/aegis/backend/internal/risk"
	"github.com/backyonatan-alt/aegis/backend/internal/store"
)

// Pipeline orchestrates: fetch -> calculate -> store.
type Pipeline struct {
	store   store.Store
	cache   *cache.Cache
	fetcher *fetcher.Fetcher
}

func New(store store.Store, cache *cache.Cache, fetcher *fetcher.Fetcher) *Pipeline {
	return &Pipeline{store: store, cache: cache, fetcher: fetcher}
}

func (p *Pipeline) Run(ctx context.Context) error {
	slog.Info("pipeline run starting")

	// 1. Load previous snapshot from DB (for history continuity)
	var currentData map[string]any
	prevBytes, err := p.store.LatestSnapshot(ctx)
	if err != nil {
		slog.Warn("failed to load previous snapshot", "error", err)
	} else if prevBytes != nil {
		if err := json.Unmarshal(prevBytes, &currentData); err != nil {
			slog.Warn("failed to parse previous snapshot", "error", err)
		} else {
			slog.Info("loaded previous snapshot", "bytes", len(prevBytes))
		}
	}

	// 2. Fetch 5 APIs concurrently
	var (
		polyData     model.PolymarketData
		polyRaw      map[string]any
		polyErr      error
		newsData     model.NewsData
		newsRaw      map[string]any
		newsErr      error
		aviationData model.AviationData
		aviationRaw  map[string]any
		aviationErr  error
		weatherData  model.WeatherData
		weatherRaw   map[string]any
		weatherErr   error
		connData     model.ConnectivityData
		connRaw      map[string]any
		connErr      error
	)

	g, _ := errgroup.WithContext(ctx)

	g.Go(func() error {
		polyData, polyRaw, polyErr = p.fetcher.FetchPolymarket()
		return nil // don't fail the group
	})
	g.Go(func() error {
		newsData, newsRaw, newsErr = p.fetcher.FetchNews()
		return nil
	})
	g.Go(func() error {
		aviationData, aviationRaw, aviationErr = p.fetcher.FetchAviation()
		return nil
	})
	g.Go(func() error {
		weatherData, weatherRaw, weatherErr = p.fetcher.FetchWeather()
		return nil
	})
	g.Go(func() error {
		connData, connRaw, connErr = p.fetcher.FetchConnectivity()
		return nil
	})

	_ = g.Wait()

	// Log errors
	for name, err := range map[string]error{
		"polymarket": polyErr, "news": newsErr, "aviation": aviationErr,
		"weather": weatherErr, "connectivity": connErr,
	} {
		if err != nil {
			slog.Error("fetch failed", "signal", name, "error", err)
		}
	}

	// 3. Wait 2 seconds for OpenSky rate limit, then fetch tanker
	slog.Info("waiting 2s for OpenSky rate limit")
	time.Sleep(2 * time.Second)

	tankerData, tankerRaw, tankerErr := p.fetcher.FetchTanker()
	if tankerErr != nil {
		slog.Error("fetch failed", "signal", "tanker", "error", tankerErr)
	}

	// 4. Compute pentagon (no API)
	pentagonData, pentagonRaw := p.fetcher.FetchPentagon()

	// 5. Fallback: use previous snapshot raw_data for failed fetches
	if polyErr != nil && currentData != nil {
		if sig, ok := currentData["polymarket"].(map[string]any); ok {
			if rd, ok := sig["raw_data"].(map[string]any); ok {
				polyRaw = rd
				polyData = extractPolymarket(rd)
			}
		}
	}
	if newsErr != nil && currentData != nil {
		if sig, ok := currentData["news"].(map[string]any); ok {
			if rd, ok := sig["raw_data"].(map[string]any); ok {
				newsRaw = rd
				newsData = extractNews(rd)
			}
		}
	}
	if aviationErr != nil && currentData != nil {
		if sig, ok := currentData["flight"].(map[string]any); ok {
			if rd, ok := sig["raw_data"].(map[string]any); ok {
				aviationRaw = rd
				aviationData = extractAviation(rd)
			}
		}
	}
	if weatherErr != nil && currentData != nil {
		if sig, ok := currentData["weather"].(map[string]any); ok {
			if rd, ok := sig["raw_data"].(map[string]any); ok {
				weatherRaw = rd
				weatherData = extractWeather(rd)
			}
		}
	}
	if connErr != nil && currentData != nil {
		if sig, ok := currentData["connectivity"].(map[string]any); ok {
			if rd, ok := sig["raw_data"].(map[string]any); ok {
				connRaw = rd
				connData = extractConnectivity(rd)
			}
		}
	}
	if tankerErr != nil && currentData != nil {
		if sig, ok := currentData["tanker"].(map[string]any); ok {
			if rd, ok := sig["raw_data"].(map[string]any); ok {
				tankerRaw = rd
				tankerData = extractTanker(rd)
			}
		}
	}

	// 6. Calculate risk scores
	scores := risk.Calculate(newsData, connData, aviationData, tankerData, weatherData, polyData, pentagonData)

	// 7. Update signal histories and build final snapshot
	rawResults := model.RawResults{
		News:         newsRaw,
		Connectivity: connRaw,
		Flight:       aviationRaw,
		Tanker:       tankerRaw,
		Weather:      weatherRaw,
		Polymarket:   polyRaw,
		Pentagon:     pentagonRaw,
	}
	snapshot := risk.UpdateHistory(currentData, scores, rawResults)

	// 8. Serialize
	data, err := json.Marshal(snapshot)
	if err != nil {
		slog.Error("failed to serialize snapshot", "error", err)
		return err
	}

	// 9. Write to DB
	if err := p.store.SaveSnapshot(ctx, data); err != nil {
		slog.Error("failed to save snapshot to DB", "error", err)
		return err
	}

	// 10. Update in-memory cache
	p.cache.Set(data)

	slog.Info("pipeline run complete", "total_risk", scores.TotalRisk, "bytes", len(data))
	return nil
}

// Extraction helpers: convert raw_data maps back to typed structs for risk calculation fallbacks.

func extractPolymarket(m map[string]any) model.PolymarketData {
	return model.PolymarketData{
		Odds:      intFromAny(m["odds"]),
		Market:    strFromAny(m["market"]),
		Timestamp: strFromAny(m["timestamp"]),
	}
}

func extractNews(m map[string]any) model.NewsData {
	return model.NewsData{
		TotalCount: intFromAny(m["total_count"]),
		AlertCount: intFromAny(m["alert_count"]),
		Timestamp:  strFromAny(m["timestamp"]),
	}
}

func extractAviation(m map[string]any) model.AviationData {
	return model.AviationData{
		AircraftCount: intFromAny(m["aircraft_count"]),
		AirlineCount:  intFromAny(m["airline_count"]),
		Timestamp:     strFromAny(m["timestamp"]),
	}
}

func extractWeather(m map[string]any) model.WeatherData {
	return model.WeatherData{
		Temp:        intFromAny(m["temp"]),
		Visibility:  intFromAny(m["visibility"]),
		Clouds:      intFromAny(m["clouds"]),
		Description: strFromAny(m["description"]),
		Condition:   strFromAny(m["condition"]),
		Timestamp:   strFromAny(m["timestamp"]),
	}
}

func extractConnectivity(m map[string]any) model.ConnectivityData {
	return model.ConnectivityData{
		Status:    strFromAny(m["status"]),
		Risk:      floatFromAny(m["risk"]),
		Trend:     floatFromAny(m["trend"]),
		Timestamp: strFromAny(m["timestamp"]),
	}
}

func extractTanker(m map[string]any) model.TankerData {
	return model.TankerData{
		TankerCount: intFromAny(m["tanker_count"]),
		Timestamp:   strFromAny(m["timestamp"]),
	}
}

func intFromAny(v any) int {
	switch n := v.(type) {
	case float64:
		return int(n)
	case int:
		return n
	}
	return 0
}

func strFromAny(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func floatFromAny(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case int:
		return float64(n)
	}
	return 0
}

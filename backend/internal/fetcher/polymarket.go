package fetcher

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math"
	"regexp"
	"strings"
	"time"

	"github.com/backyonatan-alt/aegis/backend/internal/model"
)

func (f *Fetcher) fetchPolymarket() (model.PolymarketData, map[string]any, error) {
	slog.Info("fetching polymarket odds")

	resp, err := f.client.Get("https://gamma-api.polymarket.com/public-search?q=iran")
	if err != nil {
		return model.PolymarketData{}, nil, fmt.Errorf("polymarket request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return model.PolymarketData{}, nil, fmt.Errorf("polymarket API error: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return model.PolymarketData{}, nil, fmt.Errorf("polymarket read body: %w", err)
	}

	// Parse response - could be list or object with events/data key
	var events []map[string]any
	var raw any
	if err := json.Unmarshal(body, &raw); err != nil {
		return model.PolymarketData{}, nil, fmt.Errorf("polymarket parse: %w", err)
	}

	switch v := raw.(type) {
	case []any:
		for _, item := range v {
			if m, ok := item.(map[string]any); ok {
				events = append(events, m)
			}
		}
	case map[string]any:
		if evts, ok := v["events"]; ok {
			if arr, ok := evts.([]any); ok {
				for _, item := range arr {
					if m, ok := item.(map[string]any); ok {
						events = append(events, m)
					}
				}
			}
		} else if data, ok := v["data"]; ok {
			if arr, ok := data.([]any); ok {
				for _, item := range arr {
					if m, ok := item.(map[string]any); ok {
						events = append(events, m)
					}
				}
			}
		}
	}

	if events == nil {
		return model.PolymarketData{}, nil, fmt.Errorf("unexpected polymarket response format")
	}

	slog.Info("polymarket scanning events", "count", len(events))

	highestOdds := 0
	marketTitle := ""
	now := time.Now()

	// First pass: specific strike markets
	for _, event := range events {
		eventTitle := strings.ToLower(getString(event, "title"))

		if strings.Contains(eventTitle, "will us or israel strike iran") ||
			strings.Contains(eventTitle, "us strikes iran by") {
			if !isNearTermMarket(getString(event, "title"), now) {
				continue
			}
			if markets, ok := event["markets"].([]any); ok {
				for _, m := range markets {
					if market, ok := m.(map[string]any); ok {
						odds := getMarketOdds(market)
						if odds > highestOdds {
							highestOdds = odds
							marketTitle = getStringOr(market, "question", getString(event, "title"))
						}
					}
				}
			}
		}

		if markets, ok := event["markets"].([]any); ok {
			for _, m := range markets {
				if market, ok := m.(map[string]any); ok {
					question := strings.ToLower(getString(market, "question"))
					if containsAny(question, negativeKeywords) {
						continue
					}
					if strings.Contains(question, "iran") && containsAny(question, strikeKeywords) {
						name := getString(market, "question")
						if !isNearTermMarket(name, now) {
							continue
						}
						odds := getMarketOdds(market)
						if odds > 0 && odds > highestOdds {
							highestOdds = odds
							marketTitle = name
						}
					}
				}
			}
		}
	}

	// Second pass: any Iran-related market
	if highestOdds == 0 {
		for _, event := range events {
			eventTitle := strings.ToLower(getString(event, "title"))
			if containsAny(eventTitle, negativeKeywords) {
				continue
			}
			if !strings.Contains(eventTitle, "iran") {
				continue
			}
			if !isNearTermMarket(getString(event, "title"), now) {
				continue
			}
			if markets, ok := event["markets"].([]any); ok {
				for _, m := range markets {
					if market, ok := m.(map[string]any); ok {
						question := strings.ToLower(getString(market, "question"))
						if containsAny(question, negativeKeywords) {
							continue
						}
						name := getStringOr(market, "question", getString(event, "title"))
						if !isNearTermMarket(name, now) {
							continue
						}
						odds := getMarketOdds(market)
						if odds > 0 && odds > highestOdds {
							highestOdds = odds
							marketTitle = name
						}
					}
				}
			}
		}
	}

	slog.Info("polymarket result", "odds", highestOdds, "market", truncate(marketTitle, 70))

	result := model.PolymarketData{
		Odds:      highestOdds,
		Market:    marketTitle,
		Timestamp: now.Format(time.RFC3339),
	}
	rawMap := structToMap(result)
	return result, rawMap, nil
}

func getMarketOdds(market map[string]any) int {
	odds := 0

	// Try outcomePrices
	if prices, ok := market["outcomePrices"]; ok {
		if arr, ok := prices.([]any); ok && len(arr) > 0 {
			yesPrice := toFloat(arr[0])
			if yesPrice > 1 {
				odds = int(math.Round(yesPrice))
			} else if yesPrice > 0 && yesPrice <= 1 {
				odds = int(math.Round(yesPrice * 100))
			}
			if odds >= 100 && len(arr) > 1 {
				noPrice := toFloat(arr[1])
				if noPrice > 0 && noPrice < 1 {
					odds = int(math.Round((1 - noPrice) * 100))
				} else if noPrice > 1 {
					odds = 100 - int(math.Round(noPrice))
				}
			}
		}
	}

	// Try bestAsk
	if odds == 0 || odds >= 100 {
		bestAsk := toFloat(market["bestAsk"])
		if bestAsk > 1 {
			odds = int(math.Round(bestAsk))
		} else if bestAsk > 0 && bestAsk <= 1 {
			odds = int(math.Round(bestAsk * 100))
		}
	}

	// Try lastTradePrice
	if odds == 0 || odds >= 100 {
		lastPrice := toFloat(market["lastTradePrice"])
		if lastPrice > 1 {
			odds = int(math.Round(lastPrice))
		} else if lastPrice > 0 && lastPrice <= 1 {
			odds = int(math.Round(lastPrice * 100))
		}
	}

	if odds >= 100 {
		return 0
	}
	return odds
}

func isNearTermMarket(title string, now time.Time) bool {
	titleLower := strings.ToLower(title)
	weekAhead := now.AddDate(0, 0, 7)

	for i, month := range months {
		if !strings.Contains(titleLower, month) {
			continue
		}
		re := regexp.MustCompile(month + `\s+(\d{1,2})`)
		matches := re.FindStringSubmatch(titleLower)
		if len(matches) < 2 {
			continue
		}
		day := 0
		fmt.Sscanf(matches[1], "%d", &day)
		if day == 0 {
			continue
		}
		marketDate := time.Date(now.Year(), time.Month(i+1), day, 0, 0, 0, 0, time.UTC)
		if marketDate.Before(now) {
			marketDate = time.Date(now.Year()+1, time.Month(i+1), day, 0, 0, 0, 0, time.UTC)
		}
		if !marketDate.Before(now) && !marketDate.After(weekAhead) {
			return true
		}
	}
	return false
}

func getString(m map[string]any, key string) string {
	if v, ok := m[key]; ok {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return ""
}

func getStringOr(m map[string]any, key, fallback string) string {
	s := getString(m, key)
	if s != "" {
		return s
	}
	return fallback
}

func toFloat(v any) float64 {
	if v == nil {
		return 0
	}
	switch n := v.(type) {
	case float64:
		return n
	case string:
		var f float64
		fmt.Sscanf(n, "%f", &f)
		return f
	case json.Number:
		f, _ := n.Float64()
		return f
	}
	return 0
}

func containsAny(s string, keywords []string) bool {
	for _, kw := range keywords {
		if strings.Contains(s, kw) {
			return true
		}
	}
	return false
}

func truncate(s string, maxLen int) string {
	if len(s) > maxLen {
		return s[:maxLen] + "..."
	}
	return s
}

func structToMap(v any) map[string]any {
	data, _ := json.Marshal(v)
	var m map[string]any
	json.Unmarshal(data, &m)
	return m
}

package fetcher

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math"
	"time"

	"github.com/backyonatan-alt/aegis/backend/internal/model"
)

func (f *Fetcher) fetchWeather() (model.WeatherData, map[string]any, error) {
	slog.Info("fetching weather data")

	url := fmt.Sprintf(
		"https://api.openweathermap.org/data/2.5/weather?lat=35.6892&lon=51.389&appid=%s&units=metric",
		f.cfg.OpenWeatherAPIKey,
	)

	resp, err := f.client.Get(url)
	if err != nil {
		return model.WeatherData{}, nil, fmt.Errorf("weather request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return model.WeatherData{}, nil, fmt.Errorf("weather API error: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return model.WeatherData{}, nil, fmt.Errorf("weather read body: %w", err)
	}

	var data map[string]any
	if err := json.Unmarshal(body, &data); err != nil {
		return model.WeatherData{}, nil, fmt.Errorf("weather parse: %w", err)
	}

	mainData, ok := data["main"].(map[string]any)
	if !ok {
		return model.WeatherData{}, nil, fmt.Errorf("weather: no main data")
	}

	temp := int(math.Round(toFloat(mainData["temp"])))
	visibility := 10000
	if v, ok := data["visibility"]; ok {
		visibility = int(toFloat(v))
	}

	clouds := 0
	if cloudsMap, ok := data["clouds"].(map[string]any); ok {
		clouds = int(toFloat(cloudsMap["all"]))
	}

	description := "clear"
	if weatherArr, ok := data["weather"].([]any); ok && len(weatherArr) > 0 {
		if w, ok := weatherArr[0].(map[string]any); ok {
			if d, ok := w["description"].(string); ok {
				description = d
			}
		}
	}

	condition := "Favorable"
	if visibility >= 10000 && clouds < 30 {
		condition = "Favorable"
	} else if visibility >= 7000 && clouds < 60 {
		condition = "Marginal"
	} else {
		condition = "Poor"
	}

	slog.Info("weather result", "temp", temp, "clouds", clouds, "condition", condition)

	now := time.Now()
	result := model.WeatherData{
		Temp:        temp,
		Visibility:  visibility,
		Clouds:      clouds,
		Description: description,
		Condition:   condition,
		Timestamp:   now.Format(time.RFC3339),
	}
	rawMap := structToMap(result)
	return result, rawMap, nil
}

package config

import (
	"fmt"
	"os"
	"strings"
)

type Config struct {
	DatabaseURL        string
	OpenWeatherAPIKey  string
	CloudflareRadarToken string
	Port               string
	AllowedOrigins     []string
}

func Load() (*Config, error) {
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}

	weatherKey := os.Getenv("OPENWEATHER_API_KEY")
	if weatherKey == "" {
		return nil, fmt.Errorf("OPENWEATHER_API_KEY is required")
	}

	cfToken := os.Getenv("CLOUDFLARE_RADAR_TOKEN")
	if cfToken == "" {
		return nil, fmt.Errorf("CLOUDFLARE_RADAR_TOKEN is required")
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	origins := os.Getenv("ALLOWED_ORIGINS")
	var allowedOrigins []string
	if origins != "" {
		allowedOrigins = strings.Split(origins, ",")
	} else {
		allowedOrigins = []string{"https://usstrikeradar.com"}
	}

	return &Config{
		DatabaseURL:        dbURL,
		OpenWeatherAPIKey:  weatherKey,
		CloudflareRadarToken: cfToken,
		Port:               port,
		AllowedOrigins:     allowedOrigins,
	}, nil
}

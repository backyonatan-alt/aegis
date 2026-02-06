package fetcher

import (
	"net/http"
	"time"

	"github.com/backyonatan-alt/aegis/backend/internal/config"
	"github.com/backyonatan-alt/aegis/backend/internal/model"
)

// Fetcher holds the shared HTTP client and config for all API fetchers.
type Fetcher struct {
	client *http.Client
	cfg    *config.Config
}

func New(cfg *config.Config) *Fetcher {
	return &Fetcher{
		client: &http.Client{Timeout: 30 * time.Second},
		cfg:    cfg,
	}
}

// FetchAll runs all fetchers and returns structured results plus raw data maps.
// Aviation and tanker must be called sequentially (OpenSky rate limit).
// The caller is responsible for the 2-second delay between aviation and tanker.
func (f *Fetcher) FetchPolymarket() (model.PolymarketData, map[string]any, error) {
	return f.fetchPolymarket()
}

func (f *Fetcher) FetchNews() (model.NewsData, map[string]any, error) {
	return f.fetchNews()
}

func (f *Fetcher) FetchAviation() (model.AviationData, map[string]any, error) {
	return f.fetchAviation()
}

func (f *Fetcher) FetchTanker() (model.TankerData, map[string]any, error) {
	return f.fetchTanker()
}

func (f *Fetcher) FetchWeather() (model.WeatherData, map[string]any, error) {
	return f.fetchWeather()
}

func (f *Fetcher) FetchConnectivity() (model.ConnectivityData, map[string]any, error) {
	return f.fetchConnectivity()
}

func (f *Fetcher) FetchPentagon() (model.PentagonData, map[string]any) {
	return f.fetchPentagon()
}

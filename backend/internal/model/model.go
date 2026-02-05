package model

// Signal represents a single risk signal with history and raw data.
type Signal struct {
	Risk    int            `json:"risk"`
	Detail  string         `json:"detail"`
	History []int          `json:"history"`
	RawData map[string]any `json:"raw_data"`
}

// TotalRiskPoint is a single point in the total risk history timeline.
type TotalRiskPoint struct {
	Timestamp int64 `json:"timestamp"`
	Risk      int   `json:"risk"`
	Pinned    bool  `json:"pinned,omitempty"`
}

// TotalRisk holds the aggregated risk and its history.
type TotalRisk struct {
	Risk          int              `json:"risk"`
	History       []TotalRiskPoint `json:"history"`
	ElevatedCount int             `json:"elevated_count"`
}

// Snapshot is the full API response served to the frontend.
type Snapshot struct {
	News         Signal    `json:"news"`
	Connectivity Signal    `json:"connectivity"`
	Flight       Signal    `json:"flight"`
	Tanker       Signal    `json:"tanker"`
	Weather      Signal    `json:"weather"`
	Polymarket   Signal    `json:"polymarket"`
	Pentagon     Signal    `json:"pentagon"`
	TotalRisk    TotalRisk `json:"total_risk"`
	LastUpdated  string    `json:"last_updated"`
}

// RiskScores holds the output of the risk calculator before history is applied.
type RiskScores struct {
	News         SignalScore
	Connectivity SignalScore
	Flight       SignalScore
	Tanker       SignalScore
	Weather      SignalScore
	Polymarket   SignalScore
	Pentagon     SignalScore
	TotalRisk    int
	ElevatedCount int
}

// SignalScore is a single signal's computed risk and detail string.
type SignalScore struct {
	Risk   int
	Detail string
}

// RawResults holds the raw API data keyed by signal name.
type RawResults struct {
	News         map[string]any
	Connectivity map[string]any
	Flight       map[string]any
	Tanker       map[string]any
	Weather      map[string]any
	Polymarket   map[string]any
	Pentagon     map[string]any
}

// FetchResults holds the structured data returned by fetchers, used for risk calculation.
type FetchResults struct {
	News         NewsData
	Connectivity ConnectivityData
	Aviation     AviationData
	Tanker       TankerData
	Weather      WeatherData
	Polymarket   PolymarketData
	Pentagon     PentagonData
}

type NewsData struct {
	Articles   []map[string]any `json:"articles"`
	TotalCount int              `json:"total_count"`
	AlertCount int              `json:"alert_count"`
	Timestamp  string           `json:"timestamp"`
}

type ConnectivityData struct {
	Status    string    `json:"status"`
	Risk      float64   `json:"risk"`
	Trend     float64   `json:"trend"`
	Values    []float64 `json:"values"`
	Timestamp string    `json:"timestamp"`
	Error     string    `json:"error,omitempty"`
}

type AviationData struct {
	AircraftCount int      `json:"aircraft_count"`
	AirlineCount  int      `json:"airline_count"`
	Airlines      []string `json:"airlines"`
	Timestamp     string   `json:"timestamp"`
}

type TankerData struct {
	TankerCount int      `json:"tanker_count"`
	Callsigns   []string `json:"callsigns"`
	Timestamp   string   `json:"timestamp"`
}

type WeatherData struct {
	Temp        int    `json:"temp"`
	Visibility  int    `json:"visibility"`
	Clouds      int    `json:"clouds"`
	Description string `json:"description"`
	Condition   string `json:"condition"`
	Timestamp   string `json:"timestamp"`
}

type PolymarketData struct {
	Odds      int    `json:"odds"`
	Market    string `json:"market"`
	Timestamp string `json:"timestamp"`
}

type PentagonData struct {
	Score            int              `json:"score"`
	RiskContribution int             `json:"risk_contribution"`
	Status           string          `json:"status"`
	Places           []map[string]any `json:"places"`
	Timestamp        string          `json:"timestamp"`
	IsLateNight      bool            `json:"is_late_night"`
	IsWeekend        bool            `json:"is_weekend"`
}

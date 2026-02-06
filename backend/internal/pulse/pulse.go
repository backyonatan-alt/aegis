package pulse

import (
	"sync"
	"time"
)

// Visit represents a single page visit.
type Visit struct {
	Timestamp   time.Time
	CountryCode string
}

// CountryStats holds statistics for a single country.
type CountryStats struct {
	CC    string `json:"cc"`
	Flag  string `json:"flag"`
	Count int    `json:"count"`
	Surge float64 `json:"surge"`
}

// IsraelStats holds Israel-specific statistics.
type IsraelStats struct {
	Count int     `json:"count"`
	Surge float64 `json:"surge"`
}

// Stats is the pulse data returned to the frontend.
type Stats struct {
	WatchingNow        int            `json:"watching_now"`
	ActivityMultiplier float64        `json:"activity_multiplier"`
	ActivityLevel      string         `json:"activity_level"`
	Israel             IsraelStats    `json:"israel"`
	Countries          []CountryStats `json:"countries"`
	TotalCountries     int            `json:"total_countries"`
}

// Tracker tracks visitor activity with a sliding time window.
type Tracker struct {
	mu         sync.RWMutex
	visits     []Visit
	window     time.Duration
	maxVisits  int
	baselines  map[string]int
	baseTotal  int
}

// Country code to flag emoji mapping.
var countryFlags = map[string]string{
	"IL": "🇮🇱", "US": "🇺🇸", "DE": "🇩🇪", "GB": "🇬🇧", "IR": "🇮🇷",
	"FR": "🇫🇷", "NL": "🇳🇱", "AE": "🇦🇪", "SA": "🇸🇦", "JO": "🇯🇴",
	"EG": "🇪🇬", "TR": "🇹🇷", "IN": "🇮🇳", "PK": "🇵🇰", "CA": "🇨🇦",
	"AU": "🇦🇺", "BR": "🇧🇷", "RU": "🇷🇺", "CN": "🇨🇳", "JP": "🇯🇵",
	"KR": "🇰🇷", "IT": "🇮🇹", "ES": "🇪🇸", "PL": "🇵🇱", "UA": "🇺🇦",
	"SE": "🇸🇪", "NO": "🇳🇴", "FI": "🇫🇮", "DK": "🇩🇰", "CH": "🇨🇭",
	"AT": "🇦🇹", "BE": "🇧🇪", "GR": "🇬🇷", "PT": "🇵🇹", "CZ": "🇨🇿",
	"RO": "🇷🇴", "HU": "🇭🇺", "IE": "🇮🇪", "SG": "🇸🇬", "MY": "🇲🇾",
	"TH": "🇹🇭", "VN": "🇻🇳", "PH": "🇵🇭", "ID": "🇮🇩", "MX": "🇲🇽",
	"AR": "🇦🇷", "CL": "🇨🇱", "CO": "🇨🇴", "ZA": "🇿🇦", "NG": "🇳🇬",
	"KE": "🇰🇪", "IQ": "🇮🇶", "SY": "🇸🇾", "LB": "🇱🇧", "KW": "🇰🇼",
	"QA": "🇶🇦", "BH": "🇧🇭", "OM": "🇴🇲", "YE": "🇾🇪", "AF": "🇦🇫",
}

// Default baselines (expected visitors per 10-minute window).
var defaultBaselines = map[string]int{
	"US": 35, "IL": 15, "DE": 10, "GB": 10, "IR": 8,
	"FR": 5, "NL": 4, "CA": 4, "AU": 3, "IN": 3,
}

const defaultBaseTotal = 100

// NewTracker creates a new pulse tracker.
func NewTracker() *Tracker {
	return &Tracker{
		visits:    make([]Visit, 0, 1000),
		window:    10 * time.Minute,
		maxVisits: 10000,
		baselines: defaultBaselines,
		baseTotal: defaultBaseTotal,
	}
}

// getFlag returns the flag emoji for a country code.
func getFlag(cc string) string {
	if flag, ok := countryFlags[cc]; ok {
		return flag
	}
	return "🌍"
}

// LogVisit records a visit and returns current stats.
func (t *Tracker) LogVisit(countryCode string) Stats {
	now := time.Now()

	if countryCode == "" {
		countryCode = "XX"
	}

	t.mu.Lock()
	// Trim old visits
	t.trimOldVisits(now)

	// Add new visit
	t.visits = append(t.visits, Visit{
		Timestamp:   now,
		CountryCode: countryCode,
	})

	// Enforce max visits limit
	if len(t.visits) > t.maxVisits {
		t.visits = t.visits[len(t.visits)-t.maxVisits:]
	}

	// Calculate stats while holding lock
	stats := t.calculateStats(now)
	t.mu.Unlock()

	return stats
}

// GetStats returns current stats without logging a visit.
func (t *Tracker) GetStats() Stats {
	now := time.Now()

	t.mu.Lock()
	t.trimOldVisits(now)
	stats := t.calculateStats(now)
	t.mu.Unlock()

	return stats
}

// trimOldVisits removes visits outside the time window.
// Must be called with lock held.
func (t *Tracker) trimOldVisits(now time.Time) {
	cutoff := now.Add(-t.window)
	idx := 0
	for i, v := range t.visits {
		if v.Timestamp.After(cutoff) {
			idx = i
			break
		}
		if i == len(t.visits)-1 {
			idx = len(t.visits)
		}
	}
	if idx > 0 {
		t.visits = t.visits[idx:]
	}
}

// calculateStats computes pulse statistics from current visits.
// Must be called with lock held.
func (t *Tracker) calculateStats(now time.Time) Stats {
	cutoff := now.Add(-t.window)

	// Count visits by country
	countryCounts := make(map[string]int)
	for _, v := range t.visits {
		if v.Timestamp.After(cutoff) {
			countryCounts[v.CountryCode]++
		}
	}

	watchingNow := 0
	for _, count := range countryCounts {
		watchingNow += count
	}

	// Calculate activity multiplier
	var activityMultiplier float64
	if t.baseTotal > 0 {
		activityMultiplier = float64(watchingNow) / float64(t.baseTotal)
		// Round to 1 decimal
		activityMultiplier = float64(int(activityMultiplier*10)) / 10
	} else {
		activityMultiplier = 1.0
	}

	// Determine activity level
	var activityLevel string
	switch {
	case activityMultiplier <= 1.2:
		activityLevel = "normal"
	case activityMultiplier <= 2.0:
		activityLevel = "elevated"
	case activityMultiplier <= 3.0:
		activityLevel = "high"
	default:
		activityLevel = "surging"
	}

	// Calculate country stats with surge
	type countryData struct {
		cc    string
		count int
		surge float64
	}
	var countries []countryData

	for cc, count := range countryCounts {
		baseline := t.baselines[cc]
		if baseline == 0 {
			baseline = 5 // Default baseline
		}
		surge := float64(count) / float64(baseline)
		// Round to 2 decimals
		surge = float64(int(surge*100)) / 100

		countries = append(countries, countryData{
			cc:    cc,
			count: count,
			surge: surge,
		})
	}

	// Sort by count descending
	for i := 0; i < len(countries); i++ {
		for j := i + 1; j < len(countries); j++ {
			if countries[j].count > countries[i].count {
				countries[i], countries[j] = countries[j], countries[i]
			}
		}
	}

	// Israel stats (always include)
	israel := IsraelStats{Count: 0, Surge: 0}
	for _, c := range countries {
		if c.cc == "IL" {
			israel.Count = c.count
			israel.Surge = c.surge
			break
		}
	}

	// Other countries (exclude Israel)
	var otherCountries []countryData
	for _, c := range countries {
		if c.cc != "IL" {
			otherCountries = append(otherCountries, c)
		}
	}

	// Filter to surging countries or top 6
	var displayCountries []CountryStats
	surgingCount := 0
	for _, c := range otherCountries {
		if c.surge >= 1.5 {
			surgingCount++
		}
	}

	if surgingCount >= 4 {
		// Show surging countries (up to 6)
		for _, c := range otherCountries {
			if c.surge >= 1.5 && len(displayCountries) < 6 {
				displayCountries = append(displayCountries, CountryStats{
					CC:    c.cc,
					Flag:  getFlag(c.cc),
					Count: c.count,
					Surge: c.surge,
				})
			}
		}
	} else {
		// Show top 6 by count
		for i, c := range otherCountries {
			if i >= 6 {
				break
			}
			displayCountries = append(displayCountries, CountryStats{
				CC:    c.cc,
				Flag:  getFlag(c.cc),
				Count: c.count,
				Surge: c.surge,
			})
		}
	}

	return Stats{
		WatchingNow:        watchingNow,
		ActivityMultiplier: activityMultiplier,
		ActivityLevel:      activityLevel,
		Israel:             israel,
		Countries:          displayCountries,
		TotalCountries:     len(countryCounts),
	}
}

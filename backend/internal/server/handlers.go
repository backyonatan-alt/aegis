package server

import (
	"encoding/json"
	"log/slog"
	"net/http"
)

func (s *Server) handleData(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}

	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Try in-memory cache first
	data := s.cache.Get()

	// Cold start: load from DB
	if data == nil {
		slog.Info("cache miss, loading from database")
		var err error
		data, err = s.store.LatestSnapshot(r.Context())
		if err != nil {
			slog.Error("failed to load snapshot from DB", "error", err)
			http.Error(w, `{"error":"internal server error"}`, http.StatusInternalServerError)
			return
		}
		if data == nil {
			http.Error(w, `{"error":"no data available"}`, http.StatusNotFound)
			return
		}
		// Populate cache for next request
		s.cache.Set(data)
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "public, max-age=60, s-maxage=300")
	w.Write(data)
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	updatedAt := s.cache.UpdatedAt()

	resp := map[string]any{
		"status": "ok",
	}
	if !updatedAt.IsZero() {
		resp["last_update"] = updatedAt.Format("2006-01-02T15:04:05Z07:00")
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func (s *Server) handlePulse(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}

	if r.Method != http.MethodPost && r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Extract country code from headers
	// Cloudflare: CF-IPCountry, other proxies may use X-Country
	countryCode := r.Header.Get("CF-IPCountry")
	if countryCode == "" {
		countryCode = r.Header.Get("X-Country")
	}
	if countryCode == "" {
		countryCode = "XX"
	}

	var stats interface{}
	if r.Method == http.MethodPost {
		// POST logs a visit and returns stats
		stats = s.pulse.LogVisit(countryCode)
		slog.Debug("pulse visit logged", "country", countryCode)
	} else {
		// GET just returns current stats without logging
		stats = s.pulse.GetStats()
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-cache, no-store, must-revalidate")
	json.NewEncoder(w).Encode(stats)
}

func (s *Server) handleRadarIdea(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}

	// POST only - no GET to retrieve ideas
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Parse request body
	var req struct {
		Idea string `json:"idea"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid request"}`, http.StatusBadRequest)
		return
	}

	// Validate: non-empty and reasonable length (max 1000 chars)
	idea := req.Idea
	if len(idea) == 0 {
		http.Error(w, `{"error":"idea is required"}`, http.StatusBadRequest)
		return
	}
	if len(idea) > 1000 {
		idea = idea[:1000]
	}

	// Extract country code from headers
	countryCode := r.Header.Get("CF-IPCountry")
	if countryCode == "" {
		countryCode = r.Header.Get("X-Country")
	}
	if countryCode == "" {
		countryCode = "XX"
	}

	// Save to database
	if err := s.store.SaveRadarIdea(r.Context(), idea, countryCode); err != nil {
		slog.Error("failed to save radar idea", "error", err)
		http.Error(w, `{"error":"internal server error"}`, http.StatusInternalServerError)
		return
	}

	slog.Info("radar idea saved", "country", countryCode, "length", len(idea))

	// Return minimal success response - no data exposure
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-cache, no-store, must-revalidate")
	w.Write([]byte(`{"success":true}`))
}

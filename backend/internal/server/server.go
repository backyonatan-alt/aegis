package server

import (
	"net/http"

	"github.com/backyonatan-alt/aegis/backend/internal/cache"
	"github.com/backyonatan-alt/aegis/backend/internal/config"
	"github.com/backyonatan-alt/aegis/backend/internal/store"
)

// Server holds dependencies for HTTP handlers.
type Server struct {
	cfg   *config.Config
	cache *cache.Cache
	store store.Store
}

func New(cfg *config.Config, cache *cache.Cache, store store.Store) *Server {
	return &Server{cfg: cfg, cache: cache, store: store}
}

// Router returns the HTTP handler with all routes registered.
func (s *Server) Router() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/data", s.handleData)
	mux.HandleFunc("/healthz", s.handleHealth)
	return s.corsMiddleware(mux)
}

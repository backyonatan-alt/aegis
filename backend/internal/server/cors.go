package server

import (
	"net/http"
	"strings"
)

func (s *Server) corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		allowedOrigin := s.getAllowedOrigin(origin)

		w.Header().Set("Access-Control-Allow-Origin", allowedOrigin)
		w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		w.Header().Set("Access-Control-Max-Age", "86400")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}

		next.ServeHTTP(w, r)
	})
}

func (s *Server) getAllowedOrigin(origin string) string {
	if origin == "" {
		return s.cfg.AllowedOrigins[0]
	}

	for _, allowed := range s.cfg.AllowedOrigins {
		if origin == allowed {
			return origin
		}
	}

	// Allow .pages.dev origins for Cloudflare Pages previews
	if strings.HasSuffix(origin, ".pages.dev") {
		return origin
	}

	// Allow localhost for development
	if strings.HasPrefix(origin, "http://localhost") {
		return origin
	}

	return s.cfg.AllowedOrigins[0]
}

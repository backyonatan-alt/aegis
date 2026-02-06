package main

import (
	"context"
	"database/sql"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	_ "github.com/lib/pq"

	"github.com/backyonatan-alt/aegis/backend/internal/cache"
	"github.com/backyonatan-alt/aegis/backend/internal/config"
	"github.com/backyonatan-alt/aegis/backend/internal/fetcher"
	"github.com/backyonatan-alt/aegis/backend/internal/pipeline"
	"github.com/backyonatan-alt/aegis/backend/internal/scheduler"
	"github.com/backyonatan-alt/aegis/backend/internal/server"
	"github.com/backyonatan-alt/aegis/backend/internal/store"
)

func main() {
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})))

	cfg, err := config.Load()
	if err != nil {
		slog.Error("failed to load config", "error", err)
		os.Exit(1)
	}

	db, err := sql.Open("postgres", cfg.DatabaseURL)
	if err != nil {
		slog.Error("failed to open database", "error", err)
		os.Exit(1)
	}
	defer db.Close()

	db.SetMaxOpenConns(5)
	db.SetMaxIdleConns(2)
	db.SetConnMaxLifetime(30 * time.Minute)

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	if err := db.PingContext(ctx); err != nil {
		slog.Error("failed to ping database", "error", err)
		os.Exit(1)
	}
	cancel()

	pgStore := store.NewPostgres(db)
	if err := pgStore.Migrate(context.Background()); err != nil {
		slog.Error("failed to run migrations", "error", err)
		os.Exit(1)
	}
	if err := pgStore.MigrateRadarIdeas(context.Background()); err != nil {
		slog.Error("failed to run radar ideas migration", "error", err)
		os.Exit(1)
	}

	c := cache.New()
	f := fetcher.New(cfg)
	p := pipeline.New(pgStore, c, f)

	// Run pipeline once immediately on startup
	slog.Info("running initial pipeline")
	if err := p.Run(context.Background()); err != nil {
		slog.Error("initial pipeline run failed", "error", err)
		// Non-fatal: try to serve from DB cache
	}

	// Start scheduler
	sched := scheduler.New(p, 30*time.Minute)
	go sched.Start(context.Background())

	srv := server.New(cfg, c, pgStore)
	httpServer := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      srv.Router(),
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Graceful shutdown
	done := make(chan os.Signal, 1)
	signal.Notify(done, os.Interrupt, syscall.SIGTERM)

	go func() {
		slog.Info("server starting", "port", cfg.Port)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("server error", "error", err)
			os.Exit(1)
		}
	}()

	<-done
	slog.Info("shutting down")

	sched.Stop()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		slog.Error("server shutdown error", "error", err)
	}

	slog.Info("shutdown complete")
}

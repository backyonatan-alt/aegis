package scheduler

import (
	"context"
	"log/slog"
	"time"

	"github.com/backyonatan-alt/aegis/backend/internal/pipeline"
)

// Scheduler runs the pipeline on a fixed interval.
type Scheduler struct {
	pipeline *pipeline.Pipeline
	interval time.Duration
	stop     chan struct{}
}

func New(p *pipeline.Pipeline, interval time.Duration) *Scheduler {
	return &Scheduler{
		pipeline: p,
		interval: interval,
		stop:     make(chan struct{}),
	}
}

// Start begins the periodic pipeline runs. Blocks until Stop is called.
func (s *Scheduler) Start(ctx context.Context) {
	ticker := time.NewTicker(s.interval)
	defer ticker.Stop()

	slog.Info("scheduler started", "interval", s.interval)

	for {
		select {
		case <-ticker.C:
			slog.Info("scheduler: triggering pipeline run")
			if err := s.pipeline.Run(ctx); err != nil {
				slog.Error("scheduler: pipeline run failed", "error", err)
			}
		case <-s.stop:
			slog.Info("scheduler stopped")
			return
		case <-ctx.Done():
			slog.Info("scheduler context cancelled")
			return
		}
	}
}

// Stop signals the scheduler to stop.
func (s *Scheduler) Stop() {
	close(s.stop)
}

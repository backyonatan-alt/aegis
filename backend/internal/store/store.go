package store

import "context"

// Store is the repository interface for snapshot persistence.
type Store interface {
	// SaveSnapshot stores a JSON response blob.
	SaveSnapshot(ctx context.Context, response []byte) error
	// LatestSnapshot returns the most recent JSON response blob.
	LatestSnapshot(ctx context.Context) ([]byte, error)
	// Migrate runs database migrations.
	Migrate(ctx context.Context) error
	// SaveRadarIdea stores a user-submitted radar idea.
	SaveRadarIdea(ctx context.Context, idea, countryCode string) error
	// MigrateRadarIdeas creates the radar_ideas table.
	MigrateRadarIdeas(ctx context.Context) error
}

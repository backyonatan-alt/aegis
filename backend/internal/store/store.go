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
}

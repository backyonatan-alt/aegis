package store

import (
	"context"
	"database/sql"
)

type Postgres struct {
	db *sql.DB
}

func NewPostgres(db *sql.DB) *Postgres {
	return &Postgres{db: db}
}

func (p *Postgres) Migrate(ctx context.Context) error {
	query := `
		CREATE TABLE IF NOT EXISTS snapshots (
			id          BIGSERIAL PRIMARY KEY,
			response    JSONB NOT NULL,
			created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
		);
		CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots (created_at DESC);
	`
	_, err := p.db.ExecContext(ctx, query)
	return err
}

func (p *Postgres) SaveSnapshot(ctx context.Context, response []byte) error {
	_, err := p.db.ExecContext(ctx,
		"INSERT INTO snapshots (response) VALUES ($1)",
		response,
	)
	return err
}

func (p *Postgres) LatestSnapshot(ctx context.Context) ([]byte, error) {
	var response []byte
	err := p.db.QueryRowContext(ctx,
		"SELECT response FROM snapshots ORDER BY created_at DESC LIMIT 1",
	).Scan(&response)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	return response, err
}

func (p *Postgres) SaveRadarIdea(ctx context.Context, idea, countryCode string) error {
	_, err := p.db.ExecContext(ctx,
		"INSERT INTO radar_ideas (idea, country_code) VALUES ($1, $2)",
		idea, countryCode,
	)
	return err
}

func (p *Postgres) MigrateRadarIdeas(ctx context.Context) error {
	query := `
		CREATE TABLE IF NOT EXISTS radar_ideas (
			id           BIGSERIAL PRIMARY KEY,
			idea         TEXT NOT NULL,
			country_code VARCHAR(10) NOT NULL DEFAULT 'XX',
			created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
		);
		CREATE INDEX IF NOT EXISTS idx_radar_ideas_created_at ON radar_ideas (created_at DESC);
	`
	_, err := p.db.ExecContext(ctx, query)
	return err
}

CREATE TABLE IF NOT EXISTS radar_ideas (
    id           BIGSERIAL PRIMARY KEY,
    idea         TEXT NOT NULL,
    country_code VARCHAR(10) NOT NULL DEFAULT 'XX',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_radar_ideas_created_at ON radar_ideas (created_at DESC);

CREATE TABLE IF NOT EXISTS snapshots (
    id          BIGSERIAL PRIMARY KEY,
    response    JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots (created_at DESC);

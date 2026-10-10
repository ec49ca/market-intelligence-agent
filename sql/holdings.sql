-- Apply on an already-initialized volume (schema.sql only runs on first boot).
--   psql ... -f sql/holdings.sql

CREATE TABLE IF NOT EXISTS holdings (
    ticker TEXT PRIMARY KEY REFERENCES watchlist (ticker) ON DELETE CASCADE,
    shares NUMERIC NOT NULL CHECK (shares >= 0),
    cost_per_share NUMERIC CHECK (cost_per_share IS NULL OR cost_per_share >= 0),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE holdings
    ADD COLUMN IF NOT EXISTS cost_per_share NUMERIC
    CHECK (cost_per_share IS NULL OR cost_per_share >= 0);

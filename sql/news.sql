-- Apply on an already-initialized volume (schema.sql only runs on first boot).
--   psql ... -f sql/news.sql

CREATE TABLE IF NOT EXISTS raw_news (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL REFERENCES companies (ticker),
    url TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT,
    source TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    sentiment NUMERIC,
    body TEXT,
    UNIQUE (ticker, url)
);

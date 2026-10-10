-- Apply on an already-initialized volume.
--   psql ... -f sql/attention_scores.sql

CREATE TABLE IF NOT EXISTS attention_scores (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL REFERENCES companies (ticker),
    score_date DATE NOT NULL,
    idio_return NUMERIC,
    idio_z NUMERIC,
    volume_ratio NUMERIC,
    anomaly_score NUMERIC,
    iforest_flag INTEGER,
    news_count INTEGER,
    avg_sentiment NUMERIC,
    tape_news TEXT NOT NULL,
    vol_regime TEXT NOT NULL,
    UNIQUE (ticker, score_date)
);

-- Apply on an already-initialized volume.
--   psql ... -f sql/model_scores.sql

CREATE TABLE IF NOT EXISTS model_scores (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL REFERENCES companies (ticker),
    score_date DATE NOT NULL,
    proba NUMERIC NOT NULL,
    predicted INTEGER NOT NULL,
    stance TEXT NOT NULL,
    actual_large_move INTEGER,
    next_5d_return NUMERIC,
    pred_rv_5d NUMERIC,
    actual_rv_5d NUMERIC,
    UNIQUE (ticker, score_date)
);

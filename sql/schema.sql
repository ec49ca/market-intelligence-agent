-- ============================================================
-- schema.sql — first three tables
-- ============================================================
--
-- You did the first move correctly: this file lives at sql/schema.sql.
-- Now write the three CREATE TABLE statements below, using these
-- comments as the spec. Do not copy finished SQL from chat — type it.
--
--
-- POSTGRES vs WEEK 8 SQLITE
-- -------------------------
-- Week 8 used sqlite3 and week8.db. This file is PostgreSQL.
--
--   SQLite              Postgres
--   ------              --------
--   INTEGER PRIMARY KEY SERIAL PRIMARY KEY
--                       (or INTEGER GENERATED ALWAYS AS IDENTITY)
--   TEXT                TEXT is still fine
--   REAL                NUMERIC  (prices — avoid float money)
--   INTEGER 0/1         BOOLEAN
--   TEXT dates          DATE or TIMESTAMPTZ
--
-- Other Postgres bits:
--   DEFAULT NOW()                  -- timestamps
--   DEFAULT TRUE                   -- booleans
--   DEFAULT CURRENT_DATE           -- dates, if you need it
--   UNIQUE (col1, col2)            -- table-level unique
--   REFERENCES other_table (col)   -- foreign key
--
--
-- CREATE TABLE SHAPE (same idea as Week 8 setup.sql)
-- --------------------------------------------------
--   CREATE TABLE table_name (
--       column_name  TYPE  CONSTRAINT,
--       column_name  TYPE  CONSTRAINT,
--       CONSTRAINT constraint_name UNIQUE (col1, col2)
--   );
--
-- End every statement with a semicolon.
-- Create companies FIRST. watchlist and raw_prices reference it.
--
--
-- CHECKLIST WHEN YOU FINISH
-- -------------------------
-- [ ] companies exists
-- [ ] watchlist exists
-- [ ] raw_prices exists
-- [ ] ticker is unique on watchlist
-- [ ] (ticker, date) is unique on raw_prices
-- [ ] FKs point at companies(ticker)
-- ============================================================


-- ------------------------------------------------------------
-- 1. companies
-- ------------------------------------------------------------
-- One row per stock you might ever track.
-- ticker is the natural key (NVDA, AMD, …) so use it as the PK.
--
-- Columns:
--   ticker         TEXT         PRIMARY KEY
--   company_name   TEXT         NOT NULL
--   created_at     TIMESTAMPTZ  DEFAULT NOW()
--
-- Write CREATE TABLE companies (...) here:

CREATE TABLE companies (
    ticker TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);



-- ------------------------------------------------------------
-- 2. watchlist
-- ------------------------------------------------------------
-- Stocks the user is currently tracking. One row per ticker.
-- A ticker should not appear twice → UNIQUE on ticker.
--
-- Columns:
--   id                   SERIAL       PRIMARY KEY
--   ticker               TEXT         NOT NULL
--                                     UNIQUE
--                                     REFERENCES companies (ticker)
--   company_name         TEXT         NOT NULL
--                                     (denormalized copy is ok for now)
--   added_at             TIMESTAMPTZ  DEFAULT NOW()
--   active               BOOLEAN      DEFAULT TRUE
--   backfill_start_date  DATE         nullable (no NOT NULL)
--
-- Write CREATE TABLE watchlist (...) here:

CREATE TABLE watchlist (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL UNIQUE REFERENCES companies (ticker),
    company_name TEXT NOT NULL,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    active BOOLEAN DEFAULT TRUE,
    backfill_start_date DATE
);

CREATE TABLE IF NOT EXISTS holdings (
    ticker TEXT PRIMARY KEY REFERENCES watchlist (ticker) ON DELETE CASCADE,
    shares NUMERIC NOT NULL CHECK (shares >= 0),
    cost_per_share NUMERIC CHECK (cost_per_share IS NULL OR cost_per_share >= 0),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);



-- ------------------------------------------------------------
-- 3. raw_prices
-- ------------------------------------------------------------
-- One row per ticker per trading day. This is RAW ingestion,
-- so keep it close to the API: OHLCV, no derived metrics yet.
--
-- Columns:
--   id       SERIAL    PRIMARY KEY
--   ticker   TEXT      NOT NULL
--                      REFERENCES companies (ticker)
--   date     DATE      NOT NULL     -- the trading day
--   open     NUMERIC   NOT NULL
--   high     NUMERIC   NOT NULL
--   low      NUMERIC   NOT NULL
--   close    NUMERIC   NOT NULL
--   volume   BIGINT    NOT NULL
--
-- Extra constraint (table-level, after the columns):
--   UNIQUE (ticker, date)
--   so a backfill cannot insert NVDA on 2025-08-25 twice
--
-- Write CREATE TABLE raw_prices (...) here:
CREATE TABLE raw_prices (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL REFERENCES companies (ticker),
    date DATE NOT NULL, -- the trading day
    open NUMERIC NOT NULL,
    high NUMERIC NOT NULL,
    low NUMERIC NOT NULL,
    close NUMERIC NOT NULL,
    volume BIGINT NOT NULL,
    UNIQUE (ticker, date)
);



-- ------------------------------------------------------------
-- 4. raw_fundamentals
-- ------------------------------------------------------------
-- Slow-moving company snapshot (EPS, shares, cash, debt, …).
-- Not daily OHLCV — one row per ticker per fetch day.
-- Daily P/E and market cap are close * these fields in dbt.

CREATE TABLE IF NOT EXISTS raw_fundamentals (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL REFERENCES companies (ticker),
    as_of DATE NOT NULL,
    shares_outstanding NUMERIC,
    trailing_eps NUMERIC,
    book_value NUMERIC,
    trailing_pe NUMERIC,
    market_cap NUMERIC,
    enterprise_value NUMERIC,
    total_cash NUMERIC,
    total_debt NUMERIC,
    total_revenue NUMERIC,
    ebitda NUMERIC,
    profit_margins NUMERIC,
    return_on_equity NUMERIC,
    earnings_growth NUMERIC,
    revenue_growth NUMERIC,
    beta NUMERIC,
    UNIQUE (ticker, as_of)
);



-- ------------------------------------------------------------
-- 5. raw_news
-- ------------------------------------------------------------
-- Yahoo headlines for watchlist tickers. Optional article body
-- only when the URL is Yahoo-hosted, at most one per ticker/day.

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



-- ------------------------------------------------------------
-- 6. model_scores
-- ------------------------------------------------------------
-- Unusual-move probability from the sklearn Pipeline (not a buy/sell).

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



-- ------------------------------------------------------------
-- 7. attention_scores
-- ------------------------------------------------------------
-- Today-facing anomaly: residual z, IsolationForest, price vs news, vol regime.

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




-- When all three are written, say so (or save and ask me to read
-- the file). I will review constraints, types, and FK order — not
-- rewrite the tables for you unless something is actually broken.

-- Apply on an already-initialized volume (schema.sql only runs on first boot).
--   psql ... -f sql/fundamentals.sql

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

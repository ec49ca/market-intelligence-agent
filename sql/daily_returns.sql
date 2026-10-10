-- RETIRED: product reads analytics.mart_stock_metrics (dbt).
-- sql/daily_returns.sql
-- Apply from repo root:
--   docker compose exec -T postgres psql -U market -d market_intel < sql/daily_returns.sql

CREATE OR REPLACE VIEW daily_returns AS
WITH base AS (
    SELECT
        ticker,
        date,
        close,
        LAG(close) OVER (
            PARTITION BY ticker
            ORDER BY date
        ) AS prev_close
    FROM raw_prices
)
SELECT
    ticker,
    date,
    close,
    prev_close,
    (close - prev_close) / prev_close AS daily_return
FROM base;

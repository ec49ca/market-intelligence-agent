-- RETIRED: product reads analytics.mart_stock_metrics (dbt).
CREATE OR REPLACE VIEW ma_30d AS
SELECT
    ticker,
    date,
    close,
    AVG(close) OVER (
        PARTITION BY ticker
        ORDER BY date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS ma_30d
FROM raw_prices;

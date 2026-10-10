with base as (
    select
        ticker,
        date,
        open,
        high,
        low,
        close,
        volume,
        lag(close) over (
            partition by ticker
            order by date
        ) as prev_close,
        lag(close, 5) over (
            partition by ticker
            order by date
        ) as close_5d,
        lag(close, 21) over (
            partition by ticker
            order by date
        ) as close_21d,
        lag(close, 252) over (
            partition by ticker
            order by date
        ) as close_252d,
        avg(close) over (
            partition by ticker
            order by date
            rows between 29 preceding and current row
        ) as ma_30d,
        avg(volume) over (
            partition by ticker
            order by date
            rows between 29 preceding and current row
        ) as avg_volume_30d,
        max(close) over (
            partition by ticker
            order by date
            rows between unbounded preceding and current row
        ) as peak_close,
        max(close) over (
            partition by ticker
            order by date
            rows between 251 preceding and current row
        ) as high_52w
    from {{ ref('stg_prices') }}
),
daily as (
    select
        ticker,
        date,
        open,
        high,
        low,
        close,
        volume,
        prev_close,
        (close - prev_close) / prev_close as daily_return,
        close / nullif(close_5d, 0) - 1 as return_7d,
        close / nullif(close_21d, 0) - 1 as return_30d,
        close_21d / nullif(close_252d, 0) - 1 as momentum_12_1,
        ma_30d,
        close / nullif(ma_30d, 0) - 1 as dist_to_ma,
        avg_volume_30d,
        volume / nullif(avg_volume_30d, 0) as volume_ratio,
        close / nullif(peak_close, 0) - 1 as drawdown,
        close / nullif(high_52w, 0) - 1 as dist_52w_high
    from base
)

select
    ticker,
    date,
    open,
    high,
    low,
    close,
    volume,
    prev_close,
    daily_return,
    return_7d,
    return_30d,
    momentum_12_1,
    ma_30d,
    dist_to_ma,
    avg_volume_30d,
    volume_ratio,
    stddev(daily_return) over (
        partition by ticker
        order by date
        rows between 29 preceding and current row
    ) as vol_30d,
    drawdown,
    dist_52w_high
from daily

with spy as (
    select
        date,
        daily_return as spy_return
    from {{ ref('int_daily_metrics') }}
    where ticker = 'SPY'
),
priced as (
    select
        m.*,
        s.spy_return,
        regr_slope(m.daily_return, s.spy_return) over (
            partition by m.ticker
            order by m.date
            rows between 59 preceding and current row
        ) as beta_60d
    from {{ ref('int_daily_metrics') }} m
    left join spy s on s.date = m.date
)

select
    p.ticker,
    p.date,
    p.open,
    p.high,
    p.low,
    p.close,
    p.volume,
    p.prev_close,
    p.daily_return,
    p.return_7d,
    p.return_30d,
    p.momentum_12_1,
    p.ma_30d,
    p.dist_to_ma,
    p.avg_volume_30d,
    p.volume_ratio,
    p.vol_30d,
    p.drawdown,
    p.dist_52w_high,
    p.beta_60d,
    f.as_of as fundamentals_as_of,
    f.shares_outstanding,
    f.trailing_eps,
    f.book_value,
    f.yahoo_market_cap,
    f.enterprise_value,
    f.total_cash,
    f.total_debt,
    f.total_revenue,
    f.ebitda,
    f.profit_margins,
    f.return_on_equity,
    f.earnings_growth,
    f.revenue_growth,
    f.yahoo_beta,
    p.close * f.shares_outstanding as market_cap,
    p.close / nullif(f.trailing_eps, 0) as pe,
    p.close / nullif(f.book_value, 0) as pb,
    f.total_debt / nullif(p.close * f.shares_outstanding, 0) as debt_to_cap,
    n.news_count,
    n.avg_sentiment,
    n.news_with_body
from priced p
left join lateral (
    select *
    from {{ ref('stg_fundamentals') }} sf
    where sf.ticker = p.ticker
      and sf.as_of <= p.date
    order by sf.as_of desc
    limit 1
) f on true
left join {{ ref('int_daily_news') }} n
    on n.ticker = p.ticker
   and n.date = p.date

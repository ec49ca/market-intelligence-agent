select
    ticker,
    as_of,
    shares_outstanding,
    trailing_eps,
    book_value,
    trailing_pe,
    market_cap as yahoo_market_cap,
    enterprise_value,
    total_cash,
    total_debt,
    total_revenue,
    ebitda,
    profit_margins,
    return_on_equity,
    earnings_growth,
    revenue_growth,
    beta as yahoo_beta
from {{ source('market', 'raw_fundamentals') }}

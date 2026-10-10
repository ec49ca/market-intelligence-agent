select
    ticker,
    date,
    open,
    high,
    low,
    close,
    volume
from {{ source('market', 'raw_prices') }}

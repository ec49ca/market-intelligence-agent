select
    ticker,
    url,
    headline,
    summary,
    source,
    published_at,
    sentiment,
    body
from {{ source('market', 'raw_news') }}

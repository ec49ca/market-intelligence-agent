select
    ticker,
    (published_at at time zone 'America/New_York')::date as date,
    count(*) as news_count,
    avg(sentiment) as avg_sentiment,
    count(body) as news_with_body
from {{ ref('stg_news') }}
group by 1, 2

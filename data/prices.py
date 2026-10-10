"""Fetch daily OHLCV from Yahoo and upsert into raw_prices."""

from datetime import date, datetime, timedelta, timezone
import os

import httpx
import psycopg

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

# Host uvicorn: localhost:5433. Airflow in Compose: postgres:5432.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "market")
DB_PASSWORD = os.getenv("DB_PASSWORD", "market")
DB_NAME = os.getenv("DB_NAME", "market_intel")

INDEX_TICKER = "SPY"
INDEX_LOOKBACK_DAYS = 365 * 3


def fetch_prices(ticker: str, start: date, end: date) -> list[dict]:
    """GET daily bars from Yahoo for [start, end]. Returns dicts, no SQL."""
    ticker = ticker.strip().upper()
    period1 = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    period2 = int(
        datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp()
    )

    response = httpx.get(
        YAHOO_CHART.format(ticker=ticker),
        params={"interval": "1d", "period1": period1, "period2": period2},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return []

    bar = result[0]
    timestamps = bar.get("timestamp") or []
    quote = ((bar.get("indicators") or {}).get("quote") or [{}])[0]

    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    rows = []
    for i, ts in enumerate(timestamps):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue
        rows.append(
            {
                "ticker": ticker,
                "date": datetime.fromtimestamp(ts, tz=timezone.utc).date(),
                "open": opens[i] if i < len(opens) else None,
                "high": highs[i] if i < len(highs) else None,
                "low": lows[i] if i < len(lows) else None,
                "close": close,
                "volume": volumes[i] if i < len(volumes) else None,
            }
        )
    return rows


def upsert_prices(rows: list[dict]) -> int:
    """Insert daily bars. ON CONFLICT (ticker, date) updates OHLCV. Ensures companies row exists."""
    complete = [
        row
        for row in rows
        if None not in (row["open"], row["high"], row["low"], row["close"], row["volume"])
    ]
    if not complete:
        return 0

    with psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    ) as conn:
        with conn.cursor() as cur:
            for ticker in {row["ticker"] for row in complete}:
                cur.execute(
                    """
                    INSERT INTO companies (ticker, company_name)
                    VALUES (%s, %s)
                    ON CONFLICT (ticker) DO NOTHING
                    """,
                    (ticker, ticker),
                )
            cur.executemany(
                """
                INSERT INTO raw_prices (ticker, date, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume
                """,
                [
                    (
                        row["ticker"],
                        row["date"],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                    )
                    for row in complete
                ],
            )
    return len(complete)


def load_watchlist() -> list[tuple[str, date]]:
    """Tickers the UI saved: active rows with a backfill_start_date."""
    with psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ticker, backfill_start_date
                FROM watchlist
                WHERE active = TRUE
                  AND backfill_start_date IS NOT NULL
                """
            )
            return list(cur.fetchall())


def _price_date_bound(ticker: str, which: str) -> date | None:
    """MIN or MAX trading day stored for this ticker, or None if empty."""
    sql = {
        "min": "SELECT MIN(date) FROM raw_prices WHERE ticker = %s",
        "max": "SELECT MAX(date) FROM raw_prices WHERE ticker = %s",
    }[which]
    with psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (ticker,))
            row = cur.fetchone()
    return row[0] if row else None


def latest_price_date(ticker: str) -> date | None:
    """Newest trading day already stored for this ticker, or None if empty."""
    return _price_date_bound(ticker, "max")


def earliest_price_date(ticker: str) -> date | None:
    """Oldest trading day already stored for this ticker, or None if empty."""
    return _price_date_bound(ticker, "min")


def backfill_ticker(ticker: str, backfill_start: date | None = None) -> int:
    """Fetch+upsert one ticker. Fills older than stored min and newer than stored max."""
    ticker = ticker.strip().upper()
    end = date.today()

    if backfill_start is None:
        tracked = dict(load_watchlist())
        backfill_start = tracked.get(ticker)
        if backfill_start is None:
            return 0

    earliest = earliest_price_date(ticker)
    latest = latest_price_date(ticker)
    windows: list[tuple[date, date]] = []

    if latest is None:
        windows.append((backfill_start, end))
    else:
        if earliest is not None and earliest > backfill_start:
            windows.append((backfill_start, earliest - timedelta(days=1)))
        if latest < end:
            windows.append((latest + timedelta(days=1), end))

    written = 0
    for fetch_start, fetch_end in windows:
        if fetch_start > fetch_end:
            continue
        written += upsert_prices(fetch_prices(ticker, fetch_start, fetch_end))
    return written


def list_prices(ticker: str) -> list[dict]:
    ticker = ticker.strip().upper()
    with psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT date, open, high, low, close, volume
                FROM raw_prices
                WHERE ticker = %s
                ORDER BY date
                """,
                (ticker,),
            )
            rows = cur.fetchall()
    return [
        {
            "date": row[0],
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
            "volume": row[5],
        }
        for row in rows
    ]


def backfill_index() -> int:
    """Keep SPY daily bars so beta can be stock return vs the market."""
    start = date.today() - timedelta(days=INDEX_LOOKBACK_DAYS)
    return backfill_ticker(INDEX_TICKER, start)


def backfill_watchlist() -> None:
    """CLI / Airflow: SPY first, then every active watchlist ticker."""
    spy_written = backfill_index()
    spy_latest = latest_price_date(INDEX_TICKER)
    if spy_written == 0:
        print(f"{INDEX_TICKER}: already up to date ({spy_latest})")
    else:
        print(f"{INDEX_TICKER}: upserted {spy_written} rows")

    tracked = load_watchlist()
    if not tracked:
        print("watchlist is empty — Add a stock on the page first, then rerun.")
        return

    for ticker, backfill_start in tracked:
        written = backfill_ticker(ticker, backfill_start)
        latest = latest_price_date(ticker)
        if written == 0:
            print(f"{ticker}: already up to date ({latest})")
        else:
            print(f"{ticker}: upserted {written} rows")


if __name__ == "__main__":
    backfill_watchlist()

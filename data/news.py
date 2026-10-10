"""Fetch Yahoo news headlines into raw_news, score them, optionally store one body.

Headlines come from yfinance (Yahoo news). Article text is fetched only when
the click-through URL is Yahoo-hosted, at most one story per ticker per day.
"""

from datetime import datetime, timezone
from urllib.parse import urlparse
import json
import os

import httpx
import psycopg
import yfinance as yf
from bs4 import BeautifulSoup
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from data.prices import load_watchlist

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "market")
DB_PASSWORD = os.getenv("DB_PASSWORD", "market")
DB_NAME = os.getenv("DB_NAME", "market_intel")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
}
_SKIP_PARAS = (
    "oops, something went wrong",
    "cookie",
    "not a broker",
    "sign in",
)
_analyzer = SentimentIntensityAnalyzer()
_MAX_BODY_CHARS = 8000


def _connect():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    )


def _url_from(value) -> str | None:
    if isinstance(value, dict):
        return value.get("url")
    if isinstance(value, str) and value:
        return value
    return None


def _is_yahoo_hosted(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith("yahoo.com")


def _score_text(*parts: str | None) -> float:
    text = " ".join(part for part in parts if part).strip()
    if not text:
        return 0.0
    return float(_analyzer.polarity_scores(text)["compound"])


def _parse_published(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def fetch_news(ticker: str) -> list[dict]:
    """Yahoo news items for one ticker. Recent headlines only, not a full archive."""
    ticker = ticker.strip().upper()
    rows = []
    for item in yf.Ticker(ticker).news or []:
        content = item.get("content") or item
        headline = (content.get("title") or item.get("title") or "").strip()
        if not headline:
            continue
        url = (
            _url_from(content.get("clickThroughUrl"))
            or _url_from(content.get("canonicalUrl"))
            or _url_from(item.get("link"))
            or f"yahoo://{content.get('id') or item.get('id')}"
        )
        summary = (content.get("summary") or content.get("description") or "").strip() or None
        provider = content.get("provider") or {}
        source = provider.get("displayName") if isinstance(provider, dict) else None
        rows.append(
            {
                "ticker": ticker,
                "url": url,
                "headline": headline,
                "summary": summary,
                "source": source,
                "published_at": _parse_published(
                    content.get("pubDate") or content.get("displayTime")
                ),
                "sentiment": _score_text(headline, summary),
            }
        )
    return rows


def upsert_news(rows: list[dict]) -> int:
    if not rows:
        return 0
    with _connect() as conn:
        with conn.cursor() as cur:
            for ticker in {row["ticker"] for row in rows}:
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
                INSERT INTO raw_news (
                    ticker, url, headline, summary, source, published_at, sentiment
                )
                VALUES (
                    %(ticker)s, %(url)s, %(headline)s, %(summary)s,
                    %(source)s, %(published_at)s, %(sentiment)s
                )
                ON CONFLICT (ticker, url) DO UPDATE SET
                    headline = EXCLUDED.headline,
                    summary = EXCLUDED.summary,
                    source = EXCLUDED.source,
                    published_at = EXCLUDED.published_at,
                    sentiment = EXCLUDED.sentiment
                """,
                rows,
            )
    return len(rows)


def extract_yahoo_body(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop()
            if not isinstance(obj, dict):
                continue
            body = obj.get("articleBody")
            if isinstance(body, str) and len(body.strip()) > 120:
                return body.strip()[:_MAX_BODY_CHARS]
            stack.extend(obj.get("@graph") or [])

    paras = []
    for node in soup.find_all("p"):
        text = node.get_text(" ", strip=True)
        if len(text) < 80:
            continue
        lower = text.lower()
        if any(skip in lower for skip in _SKIP_PARAS):
            continue
        paras.append(text)
    if paras:
        return "\n\n".join(paras)[:_MAX_BODY_CHARS]

    og = soup.find("meta", attrs={"property": "og:description"})
    if og and og.get("content"):
        return og["content"].strip()[:_MAX_BODY_CHARS]
    return None


def _fetch_body(url: str) -> str | None:
    response = httpx.get(url, headers=_HEADERS, timeout=30, follow_redirects=True)
    if response.status_code >= 400:
        return None
    return extract_yahoo_body(response.text)


def fill_one_yahoo_body(ticker: str) -> int:
    """Store article text for at most one Yahoo-hosted story per ticker per day."""
    ticker = ticker.strip().upper()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT (published_at AT TIME ZONE 'America/New_York')::date
                FROM raw_news
                WHERE ticker = %s
                ORDER BY published_at DESC
                LIMIT 1
                """,
                (ticker,),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                return 0
            as_of = row[0]
            cur.execute(
                """
                SELECT 1
                FROM raw_news
                WHERE ticker = %s
                  AND (published_at AT TIME ZONE 'America/New_York')::date = %s
                  AND body IS NOT NULL
                LIMIT 1
                """,
                (ticker, as_of),
            )
            if cur.fetchone():
                return 0
            cur.execute(
                """
                SELECT n.id, n.url, n.headline
                FROM raw_news n
                JOIN companies c ON c.ticker = n.ticker
                WHERE n.ticker = %s
                  AND n.body IS NULL
                  AND (n.published_at AT TIME ZONE 'America/New_York')::date = %s
                ORDER BY
                    (
                        n.headline ILIKE '%%' || n.ticker || '%%'
                        OR n.url ILIKE '%%' || n.ticker || '%%'
                        OR n.headline ILIKE '%%' || split_part(c.company_name, ' ', 1) || '%%'
                    ) DESC,
                    n.published_at DESC
                """,
                (ticker, as_of),
            )
            candidates = cur.fetchall()

    for news_id, url, _headline in candidates:
        if not _is_yahoo_hosted(url):
            continue
        body = _fetch_body(url)
        if not body:
            continue
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE raw_news SET body = %s WHERE id = %s AND body IS NULL",
                    (body, news_id),
                )
        return 1
    return 0


def ingest_ticker_news(ticker: str) -> dict:
    ticker = ticker.strip().upper()
    written = upsert_news(fetch_news(ticker))
    bodies = fill_one_yahoo_body(ticker)
    return {"headlines": written, "body": bodies}


def ingest_watchlist_news() -> None:
    tracked = load_watchlist()
    if not tracked:
        print("watchlist is empty — Add a stock on the page first, then rerun.")
        return
    for ticker, _start in tracked:
        try:
            result = ingest_ticker_news(ticker)
            print(
                f"{ticker}: news headlines={result['headlines']} body={result['body']}"
            )
        except Exception as exc:
            print(f"{ticker}: news failed ({exc})")


if __name__ == "__main__":
    ingest_watchlist_news()

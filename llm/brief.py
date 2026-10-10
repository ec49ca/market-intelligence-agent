"""Assemble an immutable snapshot JSON from Postgres (mart + attention + news)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import os

import psycopg

from llm.paths import RAW_DIR

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "market")
DB_PASSWORD = os.getenv("DB_PASSWORD", "market")
DB_NAME = os.getenv("DB_NAME", "market_intel")

_BODY_CHARS = 3500
_GENERIC_NAME_TOKENS = {
    "ADVANCED",
    "AMERICAN",
    "GLOBAL",
    "GROUP",
    "HOLDINGS",
    "INTERNATIONAL",
    "NATIONAL",
    "UNITED",
    "GENERAL",
    "SYSTEMS",
    "TECHNOLOGIES",
}
_NAME_SUFFIXES = (
    "INCORPORATED",
    "CORPORATION",
    "COMPANY",
    "INC.",
    "INC",
    "CORP.",
    "CORP",
    "LTD.",
    "LTD",
    "LLC",
    "PLC",
    "THE",
    "CO",
)
_TICKER_ALIASES = {
    "NVDA": ("NVIDIA", "NVIDIAS"),
    "AMD": ("ADVANCED MICRO",),
}


def _connect():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    )


def _jsonify(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _news_needles(ticker: str, company_name: str) -> list[str]:
    needles = [ticker.upper()]
    needles.extend(_TICKER_ALIASES.get(ticker.upper(), ()))
    cleaned = company_name.upper().replace(",", " ")
    for suffix in _NAME_SUFFIXES:
        cleaned = cleaned.replace(suffix, " ")
    parts = [part for part in cleaned.split() if len(part) >= 4]
    if parts:
        needles.append(" ".join(parts))
        if parts[0] not in _GENERIC_NAME_TOKENS:
            needles.append(parts[0])
    return needles


def news_is_relevant(ticker: str, company_name: str, headline: str, summary: str | None) -> bool:
    blob = f"{headline or ''} {summary or ''}".upper()
    return any(needle in blob for needle in _news_needles(ticker, company_name))


def load_brief(ticker: str) -> dict:
    ticker = ticker.strip().upper()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT company_name
                FROM watchlist
                WHERE ticker = %s
                """,
                (ticker,),
            )
            name_row = cur.fetchone()
            company_name = name_row[0] if name_row else ticker
            cur.execute(
                """
                SELECT date, close, daily_return, volume_ratio, vol_30d, drawdown,
                       pe, market_cap, momentum_12_1, beta_60d, ma_30d, dist_to_ma,
                       return_7d, return_30d, dist_52w_high, pb, debt_to_cap
                FROM analytics.mart_stock_metrics
                WHERE ticker = %s
                ORDER BY date DESC
                LIMIT 1
                """,
                (ticker,),
            )
            metrics = cur.fetchone()
            if not metrics:
                raise ValueError(f"No mart rows for {ticker}")
            cur.execute(
                """
                SELECT score_date, idio_return, idio_z, volume_ratio, anomaly_score,
                       iforest_flag, news_count, avg_sentiment, tape_news, vol_regime
                FROM attention_scores
                WHERE ticker = %s
                ORDER BY score_date DESC
                LIMIT 1
                """,
                (ticker,),
            )
            attention = cur.fetchone()
            cur.execute(
                """
                SELECT url, headline, summary, source, published_at, sentiment, body
                FROM raw_news
                WHERE ticker = %s
                ORDER BY published_at DESC
                LIMIT 20
                """,
                (ticker,),
            )
            news_rows = cur.fetchall()

    metric_cols = [
        "date",
        "close",
        "daily_return",
        "volume_ratio",
        "vol_30d",
        "drawdown",
        "pe",
        "market_cap",
        "momentum_12_1",
        "beta_60d",
        "ma_30d",
        "dist_to_ma",
        "return_7d",
        "return_30d",
        "dist_52w_high",
        "pb",
        "debt_to_cap",
    ]
    attention_cols = [
        "score_date",
        "idio_return",
        "idio_z",
        "volume_ratio",
        "anomaly_score",
        "iforest_flag",
        "news_count",
        "avg_sentiment",
        "tape_news",
        "vol_regime",
    ]
    headlines = []
    for row in news_rows:
        headline = row[1]
        summary = row[2]
        body = row[6]
        relevant = news_is_relevant(ticker, company_name, headline, summary)
        item = {
            "url": row[0],
            "headline": headline,
            "summary": summary,
            "source": row[3],
            "published_at": _jsonify(row[4]),
            "sentiment": _jsonify(row[5]),
            "relevant": relevant,
        }
        if body and relevant:
            item["body"] = body[:_BODY_CHARS]
        headlines.append(item)

    relevant_headlines = [item for item in headlines if item["relevant"]]
    relevant_sentiments = [
        item["sentiment"]
        for item in relevant_headlines
        if isinstance(item.get("sentiment"), (int, float))
    ]
    as_of = str(_jsonify(metrics[0]))[:10]
    caveats = []
    for item in headlines:
        published = str(item.get("published_at") or "")[:10]
        if published and published > as_of:
            caveats.append(
                f"Some headlines were published after the last price bar ({as_of})."
            )
            break
    if not relevant_headlines:
        caveats.append(
            "No ticker-relevant headlines in this dump; ignore firehose sentiment."
        )
    if not any(item.get("body") for item in headlines):
        caveats.append("No Yahoo article body stored for this ticker in the window.")

    brief = {
        "ticker": ticker,
        "company_name": company_name,
        "as_of": _jsonify(metrics[0]),
        "metrics": {k: _jsonify(v) for k, v in zip(metric_cols, metrics)},
        "attention": (
            {k: _jsonify(v) for k, v in zip(attention_cols, attention)}
            if attention
            else None
        ),
        "relevant_news_count": len(relevant_headlines),
        "avg_sentiment_relevant": (
            sum(relevant_sentiments) / len(relevant_sentiments)
            if relevant_sentiments
            else None
        ),
        "headlines": headlines,
        "caveats": caveats,
        "charts": [
            {
                "id": "close_vs_ma",
                "title": "Close vs 30-day moving average",
                "how_to_read": "Price above ma_30d is recent strength; below is weakness. Use dist_to_ma.",
            },
            {
                "id": "volume",
                "title": "Trading volume",
                "how_to_read": "volume_ratio near 1 is ordinary; ~2+ is a real volume spike.",
            },
            {
                "id": "returns",
                "title": "Daily return vs typical vol",
                "how_to_read": "Compare daily_return to vol_30d; idio_z is vs the market, not raw percent.",
            },
            {
                "id": "drawdown",
                "title": "Drawdown from peak",
                "how_to_read": "0 is at the window high; more negative is farther from the peak.",
            },
        ],
    }
    return brief


def latest_raw_path(ticker: str):
    folder = RAW_DIR / ticker.strip().upper()
    files = sorted(folder.glob("*.json"))
    return files[-1] if files else None


def dump_brief(ticker: str, *, overwrite: bool = False) -> tuple[dict, str]:
    """Write raw/{TICKER}/{as_of}.json. Existing files are left alone unless overwrite."""
    ticker = ticker.strip().upper()
    try:
        brief = load_brief(ticker)
    except Exception:
        path = latest_raw_path(ticker)
        if path is None:
            raise
        return json.loads(path.read_text()), str(path)
    as_of = str(brief["as_of"])[:10]
    folder = RAW_DIR / brief["ticker"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{as_of}.json"
    if path.exists() and not overwrite:
        return brief, str(path)
    path.write_text(json.dumps(brief, indent=2) + "\n")
    return brief, str(path)


if __name__ == "__main__":
    import sys

    ticker = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    brief, path = dump_brief(ticker, overwrite="--force" in sys.argv)
    print(f"wrote {path} as_of={brief['as_of']}")

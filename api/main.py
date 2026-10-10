from datetime import date, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import psycopg
import httpx

from analysis.stock_eda import generate_stock_eda
from data.fundamentals import snapshot_ticker_fundamentals
from data.holdings import attach_weights, upsert_holdings
from data.news import ingest_ticker_news
from data.prices import backfill_ticker
from llm.client import LLMConfigError
from llm.ingest import ingest_book, ingest_ticker
from llm.query import generate_book_report, generate_report, list_reports, read_report
from llm.paths import WIKI_DIR
from llm.wiki_graph import wiki_link_graph

app = FastAPI()

# Next.js will run on :3000; this API is on :8000.
# Browsers block that cross-origin call unless we allow it here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_HOST = "localhost"
DB_PORT = 5433
DB_USER = "market"
DB_PASSWORD = "market"
DB_NAME = "market_intel"

DEFAULT_BACKFILL_DAYS = 365 * 3

BACKFILL_DAYS = {
    "3m": 90,
    "1y": 365,
    "3y": DEFAULT_BACKFILL_DAYS,
}


class WatchlistCreate(BaseModel):
    ticker: str
    company_name: str
    backfill: str | None = None  # "3m" | "1y" | "3y"
    backfill_start_date: date | None = None


class WatchlistUpdate(BaseModel):
    backfill: str | None = None
    backfill_start_date: date | None = None


class HoldingsUpdate(BaseModel):
    shares: float = Field(ge=0)
    cost_per_share: float | None = Field(default=None, ge=0)


def resolve_backfill_start(
    backfill: str | None,
    backfill_start_date: date | None,
) -> date:
    if backfill_start_date is not None:
        return backfill_start_date
    if backfill in BACKFILL_DAYS:
        return date.today() - timedelta(days=BACKFILL_DAYS[backfill])
    return date.today() - timedelta(days=DEFAULT_BACKFILL_DAYS)

@app.get("/")
def root():
    return {"message": "API is running. Open /health"}


@app.get("/health")
def health():
    with psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
    return {"status": "ok"}


# ------------------------------------------------------------
# GET /stocks/search?q=nvidia
# External lookup. Do NOT insert into companies/watchlist here.
# ------------------------------------------------------------
# FastAPI: if the function arg is not in the path, it becomes a
# query parameter. So search_stocks(q: str) → ?q=nvidia
#
# You will:
#   1. pip install httpx   (HTTP client — like requests, Week 2 JSON)
#   2. import httpx at the top
#   3. GET Yahoo's search URL (no API key)
#   4. pull ticker + name out of the JSON
#   5. return a list of dicts
#
# URL:
#   https://query1.finance.yahoo.com/v1/finance/search?q=WHATEVER
#
# Send a User-Agent header or Yahoo may refuse the request:
#   headers = {"User-Agent": "Mozilla/5.0"}
#
# JSON shape (simplified):
#   data["quotes"] → list of matches
#   each quote has "symbol" and "shortname" or "longname"
#   skip rows with no symbol
#
# Return:
#   [{"ticker": "NVDA", "company_name": "NVIDIA Corporation"}, ...]
#
# Write the function below. Replace pass.

@app.get("/stocks/search")
def search_stocks(q: str):
    # q comes from the URL: /stocks/search?q=nvidia  →  q = "nvidia"
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    response = httpx.get(
        url,
        params={"q": q},
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    data = response.json()

    results = []
    for quote in data.get("quotes", []):
        ticker = quote.get("symbol")
        if not ticker:
            continue
        name = quote.get("shortname") or quote.get("longname") or ticker
        results.append({"ticker": ticker, "company_name": name})
    return results


@app.get("/stocks/{ticker}/prices")
def get_stock_prices(ticker: str):
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
                FROM analytics.mart_stock_metrics
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


@app.get("/stocks/{ticker}/returns")
def get_stock_returns(ticker: str):
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
                SELECT ticker, date, close, prev_close, daily_return
                FROM analytics.mart_stock_metrics
                WHERE ticker = %s
                ORDER BY date
                """,
                (ticker,),
            )
            rows = cur.fetchall()
    return [
        {
            "ticker": row[0],
            "date": row[1],
            "close": row[2],
            "prev_close": row[3],
            "daily_return": row[4],
        }
        for row in rows
    ]


@app.get("/stocks/{ticker}/ma")
def get_stock_ma(ticker: str):
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
                SELECT ticker, date, close, ma_30d
                FROM analytics.mart_stock_metrics
                WHERE ticker = %s
                ORDER BY date
                """,
                (ticker,),
            )
            rows = cur.fetchall()
    return [
        {
            "ticker": row[0],
            "date": row[1],
            "close": row[2],
            "ma_30d": row[3],
        }
        for row in rows
    ]


@app.get("/stocks/{ticker}/news")
def get_stock_news(ticker: str):
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
                SELECT url, headline, summary, source, published_at, sentiment, body
                FROM raw_news
                WHERE ticker = %s
                ORDER BY published_at DESC
                LIMIT 20
                """,
                (ticker,),
            )
            rows = cur.fetchall()
    return [
        {
            "url": row[0],
            "headline": row[1],
            "summary": row[2],
            "source": row[3],
            "published_at": row[4],
            "sentiment": row[5],
            "body": row[6],
        }
        for row in rows
    ]


@app.get("/stocks/{ticker}/chart")
def get_stock_chart(ticker: str):
    return _stock_chart_file(ticker, "price")


@app.get("/stocks/{ticker}/chart/volume")
def get_stock_chart_volume(ticker: str):
    return _stock_chart_file(ticker, "volume")


@app.get("/stocks/{ticker}/chart/returns")
def get_stock_chart_returns(ticker: str):
    return _stock_chart_file(ticker, "returns")


@app.get("/stocks/{ticker}/chart/drawdown")
def get_stock_chart_drawdown(ticker: str):
    return _stock_chart_file(ticker, "drawdown")


def _stock_chart_file(ticker: str, kind: str):
    ticker = ticker.strip().upper()
    try:
        paths = generate_stock_eda(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = paths[kind]
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"chart {kind} not found")
    return FileResponse(path, media_type="image/png")


@app.get("/stocks/{ticker}/wiki")
def get_stock_wiki(ticker: str):
    ticker = ticker.strip().upper()
    path = WIKI_DIR / "entities" / f"{ticker}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no wiki entity page yet — ingest first")
    return {"ticker": ticker, "markdown": path.read_text()}


@app.post("/stocks/{ticker}/wiki/ingest")
def post_wiki_ingest(ticker: str, force: bool = False):
    ticker = ticker.strip().upper()
    try:
        return ingest_ticker(ticker, overwrite_raw=force, force=force)
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/stocks/{ticker}/reports")
def get_stock_reports(ticker: str):
    return list_reports(ticker.strip().upper())


@app.get("/stocks/{ticker}/reports/{filename}")
def get_stock_report(ticker: str, filename: str):
    try:
        return {"ticker": ticker.strip().upper(), "filename": filename, "markdown": read_report(filename)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="report not found")


@app.post("/stocks/{ticker}/reports")
def post_stock_report(ticker: str):
    ticker = ticker.strip().upper()
    try:
        return generate_report(ticker, ingest_first=True)
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/book")
def get_book():
    from llm.book import load_book_snapshot

    return load_book_snapshot()


@app.get("/book/reports")
def get_book_reports():
    return list_reports("book")


@app.get("/book/reports/{filename}")
def get_book_report(filename: str):
    try:
        return {"ticker": "book", "filename": filename, "markdown": read_report(filename)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="report not found")


@app.post("/book/reports")
def post_book_report():
    try:
        return generate_book_report(ingest_first=True)
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/wiki/graph")
def get_wiki_graph():
    return wiki_link_graph()


@app.post("/book/wiki/ingest")
def post_book_wiki_ingest(force: bool = False):
    try:
        return ingest_book(overwrite_raw=force, force=force)
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/watchlist")
def get_watchlist():
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
                SELECT
                    w.ticker,
                    w.company_name,
                    w.added_at,
                    w.active,
                    w.backfill_start_date,
                    h.shares,
                    h.cost_per_share,
                    entry.close AS default_cost,
                    entry.date AS default_cost_as_of,
                    m.date,
                    m.close,
                    m.daily_return,
                    m.volume_ratio,
                    m.vol_30d,
                    m.return_30d,
                    m.drawdown,
                    m.pe,
                    m.market_cap,
                    m.momentum_12_1,
                    m.beta_60d,
                    m.return_on_equity,
                    m.debt_to_cap,
                    n.news_count,
                    n.avg_sentiment,
                    a.idio_z,
                    a.anomaly_score,
                    a.tape_news,
                    a.vol_regime
                FROM watchlist w
                LEFT JOIN holdings h ON h.ticker = w.ticker
                LEFT JOIN LATERAL (
                    SELECT close, date
                    FROM analytics.mart_stock_metrics
                    WHERE ticker = w.ticker
                      AND date <= w.added_at::date
                    ORDER BY date DESC
                    LIMIT 1
                ) entry ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        date,
                        close,
                        daily_return,
                        volume_ratio,
                        vol_30d,
                        return_30d,
                        drawdown,
                        pe,
                        market_cap,
                        momentum_12_1,
                        beta_60d,
                        return_on_equity,
                        debt_to_cap
                    FROM analytics.mart_stock_metrics
                    WHERE ticker = w.ticker
                    ORDER BY date DESC
                    LIMIT 1
                ) m ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*)::int AS news_count,
                        AVG(sentiment) AS avg_sentiment
                    FROM raw_news
                    WHERE ticker = w.ticker
                      AND published_at >= NOW() - INTERVAL '7 days'
                ) n ON TRUE
                LEFT JOIN LATERAL (
                    SELECT idio_z, anomaly_score, tape_news, vol_regime
                    FROM attention_scores
                    WHERE ticker = w.ticker
                    ORDER BY score_date DESC
                    LIMIT 1
                ) a ON TRUE
                ORDER BY w.added_at DESC
                """
            )
            rows = cur.fetchall()
    payload = [
        {
            "ticker": row[0],
            "company_name": row[1],
            "added_at": row[2],
            "active": row[3],
            "backfill_start_date": row[4],
            "shares": row[5],
            "cost_per_share": row[6],
            "default_cost": row[7],
            "default_cost_as_of": row[8],
            "as_of": row[9],
            "close": row[10],
            "daily_return": row[11],
            "volume_ratio": row[12],
            "vol_30d": row[13],
            "return_30d": row[14],
            "drawdown": row[15],
            "pe": row[16],
            "market_cap": row[17],
            "momentum_12_1": row[18],
            "beta_60d": row[19],
            "return_on_equity": row[20],
            "debt_to_cap": row[21],
            "news_count": row[22],
            "avg_sentiment": row[23],
            "idio_z": row[24],
            "anomaly_score": row[25],
            "tape_news": row[26],
            "vol_regime": row[27],
        }
        for row in rows
    ]
    return attach_weights(payload)


@app.post("/watchlist")
def add_to_watchlist(body: WatchlistCreate):
    ticker = body.ticker.strip().upper()
    company_name = body.company_name.strip()
    backfill_start = resolve_backfill_start(body.backfill, body.backfill_start_date)

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
                INSERT INTO companies (ticker, company_name)
                VALUES (%s, %s)
                ON CONFLICT (ticker) DO NOTHING
                """,
                (ticker, company_name),
            )
            cur.execute(
                """
                INSERT INTO watchlist (ticker, company_name, backfill_start_date)
                VALUES (%s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE SET
                    company_name = EXCLUDED.company_name,
                    active = TRUE,
                    backfill_start_date = EXCLUDED.backfill_start_date
                """,
                (ticker, company_name, backfill_start),
            )

    prices_upserted = backfill_ticker(ticker, backfill_start)
    fundamentals_upserted = 0
    news_ingested = {"headlines": 0, "body": 0}
    try:
        fundamentals_upserted = snapshot_ticker_fundamentals(ticker)
    except Exception:
        fundamentals_upserted = 0
    try:
        news_ingested = ingest_ticker_news(ticker)
    except Exception:
        news_ingested = {"headlines": 0, "body": 0}

    return {
        "ticker": ticker,
        "company_name": company_name,
        "backfill_start_date": backfill_start,
        "active": True,
        "prices_upserted": prices_upserted,
        "fundamentals_upserted": fundamentals_upserted,
        "news_headlines": news_ingested.get("headlines", 0),
        "news_body": news_ingested.get("body", 0),
    }


@app.patch("/watchlist/{ticker}")
def update_watchlist(ticker: str, body: WatchlistUpdate):
    ticker = ticker.strip().upper()
    backfill_start = resolve_backfill_start(body.backfill, body.backfill_start_date)

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
                UPDATE watchlist
                SET backfill_start_date = %s
                WHERE ticker = %s
                """,
                (backfill_start, ticker),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="ticker not on watchlist")

    prices_upserted = backfill_ticker(ticker, backfill_start)
    return {
        "ticker": ticker,
        "backfill_start_date": backfill_start,
        "prices_upserted": prices_upserted,
    }


@app.delete("/watchlist/{ticker}")
def delete_watchlist(ticker: str):
    ticker = ticker.strip().upper()

    with psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM watchlist WHERE ticker = %s", (ticker,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="ticker not on watchlist")

    return {"deleted": ticker}


@app.put("/holdings/{ticker}")
def put_holdings(ticker: str, body: HoldingsUpdate):
    ticker = ticker.strip().upper()
    try:
        saved = upsert_holdings(
            ticker, shares=body.shares, cost_per_share=body.cost_per_share
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="ticker not on watchlist") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return saved
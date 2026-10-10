"""Fetch Yahoo fundamentals snapshots into raw_fundamentals.

Uses yfinance (same unofficial Yahoo quoteSummary under the hood).
Accounting fields change on filings / buybacks, not every trading day.
Daily P/E and market cap are computed in dbt from close × this snapshot.
"""

from datetime import date
import os

import psycopg
import yfinance as yf

from data.prices import latest_price_date, load_watchlist

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "market")
DB_PASSWORD = os.getenv("DB_PASSWORD", "market")
DB_NAME = os.getenv("DB_NAME", "market_intel")


def fetch_fundamentals(ticker: str) -> dict:
    """One Yahoo snapshot. Keys match raw_fundamentals columns except ticker/as_of."""
    ticker = ticker.strip().upper()
    info = yf.Ticker(ticker).info or {}
    if not info.get("sharesOutstanding") and not info.get("trailingEps") and not info.get("marketCap"):
        raise RuntimeError(f"No Yahoo fundamentals for {ticker}")
    as_of = latest_price_date(ticker) or date.today()
    return {
        "ticker": ticker,
        "as_of": as_of,
        "shares_outstanding": info.get("sharesOutstanding"),
        "trailing_eps": info.get("trailingEps"),
        "book_value": info.get("bookValue"),
        "trailing_pe": info.get("trailingPE"),
        "market_cap": info.get("marketCap"),
        "enterprise_value": info.get("enterpriseValue"),
        "total_cash": info.get("totalCash"),
        "total_debt": info.get("totalDebt"),
        "total_revenue": info.get("totalRevenue"),
        "ebitda": info.get("ebitda"),
        "profit_margins": info.get("profitMargins"),
        "return_on_equity": info.get("returnOnEquity"),
        "earnings_growth": info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth"),
        "revenue_growth": info.get("revenueGrowth") or info.get("revenueQuarterlyGrowth"),
        "beta": info.get("beta"),
    }


def upsert_fundamentals(row: dict) -> int:
    """Insert today's snapshot. ON CONFLICT (ticker, as_of) updates fields."""
    ticker = row["ticker"]
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
                (ticker, ticker),
            )
            cur.execute(
                """
                INSERT INTO raw_fundamentals (
                    ticker, as_of, shares_outstanding, trailing_eps, book_value,
                    trailing_pe, market_cap, enterprise_value, total_cash, total_debt,
                    total_revenue, ebitda, profit_margins, return_on_equity,
                    earnings_growth, revenue_growth, beta
                )
                VALUES (
                    %(ticker)s, %(as_of)s, %(shares_outstanding)s, %(trailing_eps)s,
                    %(book_value)s, %(trailing_pe)s, %(market_cap)s, %(enterprise_value)s,
                    %(total_cash)s, %(total_debt)s, %(total_revenue)s, %(ebitda)s,
                    %(profit_margins)s, %(return_on_equity)s, %(earnings_growth)s,
                    %(revenue_growth)s, %(beta)s
                )
                ON CONFLICT (ticker, as_of) DO UPDATE SET
                    shares_outstanding = EXCLUDED.shares_outstanding,
                    trailing_eps = EXCLUDED.trailing_eps,
                    book_value = EXCLUDED.book_value,
                    trailing_pe = EXCLUDED.trailing_pe,
                    market_cap = EXCLUDED.market_cap,
                    enterprise_value = EXCLUDED.enterprise_value,
                    total_cash = EXCLUDED.total_cash,
                    total_debt = EXCLUDED.total_debt,
                    total_revenue = EXCLUDED.total_revenue,
                    ebitda = EXCLUDED.ebitda,
                    profit_margins = EXCLUDED.profit_margins,
                    return_on_equity = EXCLUDED.return_on_equity,
                    earnings_growth = EXCLUDED.earnings_growth,
                    revenue_growth = EXCLUDED.revenue_growth,
                    beta = EXCLUDED.beta
                """,
                row,
            )
    return 1


def snapshot_ticker_fundamentals(ticker: str) -> int:
    """Fetch + upsert one ticker. Returns 1 if a row was written."""
    return upsert_fundamentals(fetch_fundamentals(ticker))


def snapshot_watchlist_fundamentals() -> None:
    """CLI / Airflow: snapshot every active watchlist ticker."""
    tracked = load_watchlist()
    if not tracked:
        print("watchlist is empty — Add a stock on the page first, then rerun.")
        return
    for ticker, _start in tracked:
        try:
            snapshot_ticker_fundamentals(ticker)
            as_of = latest_price_date(ticker) or date.today()
            print(f"{ticker}: fundamentals snapshot {as_of}")
        except Exception as exc:
            print(f"{ticker}: fundamentals failed ({exc})")


if __name__ == "__main__":
    snapshot_watchlist_fundamentals()

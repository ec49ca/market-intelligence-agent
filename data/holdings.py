"""Your book: share counts and approx cost. Weights use last close."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import os

import psycopg

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "market")
DB_PASSWORD = os.getenv("DB_PASSWORD", "market")
DB_NAME = os.getenv("DB_NAME", "market_intel")


def _connect():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    )


def _num(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def lookup_entry_close(ticker: str, as_of: date) -> tuple[float, date] | None:
    """Close on or before the watchlist-add date (nearest prior session)."""
    ticker = ticker.strip().upper()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT close, date
                FROM analytics.mart_stock_metrics
                WHERE ticker = %s AND date <= %s
                ORDER BY date DESC
                LIMIT 1
                """,
                (ticker, as_of),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    """
                    SELECT close, date
                    FROM raw_prices
                    WHERE ticker = %s AND date <= %s
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    (ticker, as_of),
                )
                row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0]), _as_date(row[1]) or as_of


def upsert_holdings(
    ticker: str, *, shares: float, cost_per_share: float | None
) -> dict:
    ticker = ticker.strip().upper()
    if shares < 0:
        raise ValueError("shares must be >= 0")
    if cost_per_share is not None and cost_per_share < 0:
        raise ValueError("cost_per_share must be >= 0")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT added_at, h.shares, h.cost_per_share
                FROM watchlist w
                LEFT JOIN holdings h ON h.ticker = w.ticker
                WHERE w.ticker = %s
                """,
                (ticker,),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(ticker)
            added_at, _existing_shares, existing_cost = row
            cost = cost_per_share
            if cost is None:
                cost = _num(existing_cost)
            if cost is None:
                added = _as_date(added_at) or date.today()
                found = lookup_entry_close(ticker, added)
                if found:
                    cost = found[0]
            cur.execute(
                """
                INSERT INTO holdings (ticker, shares, cost_per_share, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (ticker) DO UPDATE
                SET shares = EXCLUDED.shares,
                    cost_per_share = EXCLUDED.cost_per_share,
                    updated_at = NOW()
                """,
                (
                    ticker,
                    Decimal(str(shares)),
                    None if cost is None else Decimal(str(cost)),
                ),
            )
    return {
        "ticker": ticker,
        "shares": shares,
        "cost_per_share": cost,
    }


def attach_weights(rows: list[dict]) -> list[dict]:
    """Add market_value, weight, and P/L from shares × last close vs cost."""
    valued = []
    total = 0.0
    for row in rows:
        shares = _num(row.get("shares"))
        close = _num(row.get("close"))
        stored_cost = _num(row.get("cost_per_share"))
        default_cost = _num(row.get("default_cost"))
        cost = stored_cost if stored_cost is not None else default_cost
        value = None
        if shares is not None and close is not None and shares > 0:
            value = shares * close
            total += value
        cost_basis = None
        unrealized = None
        unrealized_pct = None
        if shares is not None and cost is not None and shares > 0:
            cost_basis = shares * cost
            if value is not None:
                unrealized = value - cost_basis
                if cost_basis != 0:
                    unrealized_pct = unrealized / cost_basis
        valued.append(
            {
                **row,
                "display_cost": cost,
                "market_value": value,
                "cost_basis": cost_basis,
                "unrealized": unrealized,
                "unrealized_pct": unrealized_pct,
            }
        )
    out = []
    for row in valued:
        value = row["market_value"]
        weight = (value / total) if value is not None and total > 0 else None
        out.append({**row, "weight": weight})
    return out

"""Book-level risk from a constant-weight return series. Not an average of names."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import math
import os

import pandas as pd
import psycopg

from data.prices import INDEX_TICKER

CORR_WINDOW = 90
VOL_WINDOW = 30
BETA_WINDOW = 60
DRAWDOWN_WINDOW = 90
HIGH_CORR = 0.75
HIGH_CONCENTRATION = 0.5
EXTREME_CONCENTRATION = 0.75

SECTOR_BY_TICKER = {
    "AMD": "Semiconductors",
    "NVDA": "Semiconductors",
    "INTC": "Semiconductors",
    "AVGO": "Semiconductors",
    "TSM": "Semiconductors",
    "QCOM": "Semiconductors",
    "MU": "Semiconductors",
    "MSFT": "Software",
    "GOOGL": "Internet",
    "GOOG": "Internet",
    "AMZN": "Internet",
    "META": "Internet",
    "AAPL": "Technology Hardware",
    "TSLA": "Autos",
    INDEX_TICKER: "Index",
}


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        value = float(value)
    else:
        value = float(value)
    if not math.isfinite(value):
        return None
    return value


def sector_for(ticker: str) -> str:
    return SECTOR_BY_TICKER.get((ticker or "").upper(), "Unclassified")


def concentration_label(top_weight: float | None) -> str:
    if top_weight is None:
        return "—"
    if top_weight >= EXTREME_CONCENTRATION:
        return "High"
    if top_weight >= HIGH_CONCENTRATION:
        return "Elevated"
    return "Moderate"


def corr_label(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value >= HIGH_CORR:
        return "historically move together"
    if value >= 0.4:
        return "tend to move in the same direction"
    if value <= -0.4:
        return "historically often move opposite"
    return "little linear relationship"


def risk_from_returns(
    weights: dict[str, float],
    returns: pd.DataFrame,
    *,
    spy: str = INDEX_TICKER,
) -> dict:
    """Constant today's weights on overlapping daily returns.

    Volatility is 30-session std of book daily returns (same units as mart vol_30d).
    Beta is 60-session slope vs SPY. Drawdown is vs the 90-session peak of the
    constant-weight wealth path. Correlation is 90-session Pearson.
    """
    names = [ticker for ticker, weight in weights.items() if weight and weight > 0]
    names = [ticker for ticker in names if ticker in returns.columns]
    total = sum(weights[ticker] for ticker in names)
    lookback = (
        "Constant today's weights over the lookback. Not a daily-rebalanced book."
    )
    empty = {
        "lookback": lookback,
        "corr_window": CORR_WINDOW,
        "vol_window": VOL_WINDOW,
        "beta_window": BETA_WINDOW,
        "drawdown_window": DRAWDOWN_WINDOW,
        "concentration_label": None,
        "top_ticker": None,
        "top_weight": None,
        "name_count": len(names),
        "correlation": None,
        "correlation_pair": None,
        "correlation_label": "n/a",
        "pairs": [],
        "vol_30d": None,
        "beta_vs_spy": None,
        "drawdown_90d": None,
        "sector_mix": [],
        "sector_line": None,
        "assessment": "No holdings with weights; book risk is empty.",
    }
    if not names or total <= 0:
        return empty

    w = {ticker: weights[ticker] / total for ticker in names}
    top_ticker = max(names, key=lambda ticker: w[ticker])
    top_weight = w[top_ticker]
    aligned = returns[names].dropna()
    window = aligned.tail(CORR_WINDOW)
    port = None
    if len(window) >= 5:
        port = sum(window[ticker] * w[ticker] for ticker in names)

    pairs = []
    headline_corr = None
    headline_pair = None
    if len(names) >= 2 and len(window) >= 10:
        corr = window.corr()
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                value = corr.loc[left, right]
                if pd.isna(value):
                    continue
                value = _num(value)
                if value is None:
                    continue
                pairs.append(
                    {
                        "a": left,
                        "b": right,
                        "corr": value,
                        "high": value >= HIGH_CORR,
                    }
                )
        if pairs:
            pairs.sort(key=lambda item: -abs(item["corr"]))
            headline_corr = pairs[0]["corr"]
            headline_pair = f"{pairs[0]['a']}/{pairs[0]['b']}"

    vol = None
    if port is not None and len(port.dropna()) >= 10:
        vol = float(port.tail(VOL_WINDOW).std())

    beta = None
    if port is not None and spy in returns.columns:
        spy_ret = returns[spy].reindex(port.index)
        both = pd.concat({"book": port, "spy": spy_ret}, axis=1).dropna().tail(BETA_WINDOW)
        if len(both) >= 20 and float(both["spy"].var()) > 0:
            beta = float(both["book"].cov(both["spy"]) / both["spy"].var())

    drawdown = None
    if port is not None and len(port.dropna()) >= 5:
        wealth = (1 + port.tail(DRAWDOWN_WINDOW)).cumprod()
        dd = wealth / wealth.cummax() - 1
        drawdown = float(dd.min())

    sectors: dict[str, float] = {}
    for ticker in names:
        sectors[sector_for(ticker)] = sectors.get(sector_for(ticker), 0) + w[ticker]
    sector_mix = [
        {"sector": name, "weight": weight}
        for name, weight in sorted(sectors.items(), key=lambda item: -item[1])
    ]
    if len(sector_mix) == 1:
        sector_line = f"100% {sector_mix[0]['sector']}"
    else:
        sector_line = ", ".join(
            f"{item['sector']} {item['weight'] * 100:.0f}%" for item in sector_mix
        )

    risk = {
        "lookback": lookback,
        "corr_window": CORR_WINDOW,
        "vol_window": VOL_WINDOW,
        "beta_window": BETA_WINDOW,
        "drawdown_window": DRAWDOWN_WINDOW,
        "sessions_used": int(len(window)),
        "concentration_label": concentration_label(top_weight),
        "top_ticker": top_ticker,
        "top_weight": _num(top_weight),
        "name_count": len(names),
        "correlation": _num(headline_corr),
        "correlation_pair": headline_pair,
        "correlation_label": corr_label(headline_corr),
        "pairs": pairs,
        "vol_30d": _num(vol),
        "beta_vs_spy": _num(beta),
        "drawdown_90d": _num(drawdown),
        "sector_mix": [
            {"sector": item["sector"], "weight": _num(item["weight"])}
            for item in sector_mix
        ],
        "sector_line": sector_line,
        "weights_used": {ticker: _num(weight) for ticker, weight in w.items()},
    }
    risk["assessment"] = assessment_line(risk)
    return risk


def assessment_line(risk: dict) -> str:
    parts = []
    label = risk.get("concentration_label")
    top = risk.get("top_ticker")
    weight = _num(risk.get("top_weight"))
    if label and top and weight is not None:
        parts.append(f"{label} concentration: {top} is {weight * 100:.0f}% of the book.")
    corr = _num(risk.get("correlation"))
    if corr is not None:
        pair = risk.get("correlation_pair") or "Holdings"
        hint = risk.get("correlation_label") or ""
        parts.append(f"{pair} 90-session correlation is {corr:.2f} ({hint}).")
    beta = _num(risk.get("beta_vs_spy"))
    if beta is not None:
        vs = "more" if beta > 1 else "less or similarly"
        parts.append(f"Book beta vs SPY is {beta:.2f} ({vs} sensitive than the index).")
    vol = _num(risk.get("vol_30d"))
    if vol is not None:
        parts.append(f"Book 30-session vol is {vol * 100:.2f}% (session std, not annualized).")
    dd = _num(risk.get("drawdown_90d"))
    if dd is not None:
        parts.append(f"90-session drawdown from peak is {dd * 100:.1f}%.")
    if risk.get("sector_line"):
        parts.append(f"Sector mix: {risk['sector_line']}.")
    if risk.get("lookback"):
        parts.append(risk["lookback"])
    return " ".join(parts)


def load_daily_returns(tickers: list[str], *, calendar_days: int = 220) -> pd.DataFrame:
    """Pivot mart daily_return for holdings + SPY. Empty frame if the mart is missing."""
    wanted = sorted({ticker.upper() for ticker in tickers if ticker} | {INDEX_TICKER})
    start = date.today() - timedelta(days=calendar_days)
    try:
        conn = psycopg.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5433")),
            user=os.getenv("DB_USER", "market"),
            password=os.getenv("DB_PASSWORD", "market"),
            dbname=os.getenv("DB_NAME", "market_intel"),
        )
    except Exception:
        return pd.DataFrame()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ticker, date, daily_return
                FROM analytics.mart_stock_metrics
                WHERE ticker = ANY(%s)
                  AND date >= %s
                  AND daily_return IS NOT NULL
                ORDER BY date, ticker
                """,
                (wanted, start),
            )
            rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows, columns=["ticker", "date", "daily_return"])
    frame["date"] = pd.to_datetime(frame["date"])
    frame["daily_return"] = frame["daily_return"].astype(float)
    return frame.pivot(index="date", columns="ticker", values="daily_return").sort_index()


def book_risk_for_holdings(names: list[dict]) -> dict:
    weights = {}
    for row in names:
        ticker = row.get("ticker")
        weight = _num(row.get("weight"))
        if ticker and weight and weight > 0:
            weights[str(ticker).upper()] = weight
    returns = load_daily_returns(list(weights))
    return risk_from_returns(weights, returns)

"""Book snapshot: holdings mix + SPY macro receipt. Numbers only, no letter."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import os

import psycopg

from data.holdings import attach_weights
from data.prices import INDEX_TICKER
from llm.book_risk import book_risk_for_holdings
from llm.paths import RAW_DIR

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "market")
DB_PASSWORD = os.getenv("DB_PASSWORD", "market")
DB_NAME = os.getenv("DB_NAME", "market_intel")

MACRO_NEWS_NEEDLES = (
    "SPY",
    "S&P",
    "S & P",
    "DOW",
    "NASDAQ",
    "FED ",
    "FEDERAL RESERVE",
    "TREASURY",
    "INFLATION",
    "CPI",
    "WALL STREET",
    "STOCK MARKET",
    "RATES",
    "YIELD",
    "RECESSION",
    "TARIFF",
    "EXPORT CONTROL",
    "AI PAUSE",
    "AI SLOWDOWN",
    "CHIP STOCKS",
    "SEMICONDUCTOR",
    "OIL",
    "RATE HIKE",
    "RATE CUT",
)


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


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def day_dollar(value: float | None, daily_return: float | None) -> float | None:
    """Shares × (close − prev) from end-of-day value and that name's daily return."""
    if value is None or daily_return is None or daily_return <= -1:
        return None
    return (value * daily_return) / (1 + daily_return)


def summarize_book(rows: list[dict]) -> dict:
    """Roll holdings rows (after attach_weights) into book-level stats."""
    held = [row for row in rows if _num(row.get("market_value"))]
    book = sum(_num(row["market_value"]) or 0 for row in held)
    cost = sum(_num(row.get("cost_basis")) or 0 for row in held)
    pnl = sum(_num(row.get("unrealized")) or 0 for row in held)
    names = []
    day_total = 0.0
    day_ok = True
    weighted_30 = 0.0
    as_of_dates = []
    for row in held:
        value = _num(row["market_value"]) or 0.0
        ret = _num(row.get("daily_return"))
        move = day_dollar(value, ret)
        if move is None:
            day_ok = False
        else:
            day_total += move
        weight = _num(row.get("weight"))
        r30 = _num(row.get("return_30d"))
        if weight is not None and r30 is not None:
            weighted_30 += weight * r30
        as_of = str(row.get("as_of") or "")[:10]
        if as_of:
            as_of_dates.append(as_of)
        names.append(
            {
                "ticker": row["ticker"],
                "company_name": row.get("company_name"),
                "shares": _num(row.get("shares")),
                "close": _num(row.get("close")),
                "as_of": as_of or None,
                "daily_return": ret,
                "return_30d": r30,
                "vol_30d": _num(row.get("vol_30d")),
                "beta_60d": _num(row.get("beta_60d")),
                "tape_news": row.get("tape_news"),
                "vol_regime": row.get("vol_regime"),
                "market_value": value,
                "weight": weight,
                "cost_basis": _num(row.get("cost_basis")),
                "unrealized": _num(row.get("unrealized")),
                "unrealized_pct": _num(row.get("unrealized_pct")),
                "day_dollar": move,
            }
        )
    names.sort(key=lambda item: -(item["weight"] or 0))
    prior = book - day_total if day_ok else None
    top = names[0] if names else None
    return {
        "as_of": max(as_of_dates) if as_of_dates else None,
        "book_value": book if held else None,
        "cost_basis": cost if cost else None,
        "unrealized": pnl if held else None,
        "unrealized_pct": (pnl / cost) if cost else None,
        "day_dollar": day_total if held and day_ok else None,
        "day_pct": (day_total / prior) if prior else None,
        "return_30d_weighted": weighted_30 if held else None,
        "name_count": len(held),
        "top_ticker": top["ticker"] if top else None,
        "top_weight": top["weight"] if top else None,
        "names": names,
        "unheld": [
            {"ticker": row["ticker"], "company_name": row.get("company_name")}
            for row in rows
            if not _num(row.get("market_value"))
        ],
        "caveats": _book_caveats(held, names, top),
    }


def _book_caveats(held: list, names: list[dict], top: dict | None) -> list[str]:
    notes = []
    if not held:
        notes.append("No share counts yet; mix/P/L chips are empty.")
        return notes
    if top and (top.get("weight") or 0) >= 0.5:
        notes.append(
            f"{top['ticker']} is {100 * (top['weight'] or 0):.0f}% of the book "
            "(concentration, not a forecast)."
        )
    tickers = {row["ticker"] for row in names}
    if tickers <= {"AMD", "NVDA"} and len(tickers) >= 2:
        notes.append(
            "Both names are AI-infrastructure semiconductors; they are one theme, not a diversified book."
        )
    return notes


def load_watchlist_metric_rows() -> list[dict]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    w.ticker,
                    w.company_name,
                    h.shares,
                    h.cost_per_share,
                    entry.close AS default_cost,
                    m.date,
                    m.close,
                    m.daily_return,
                    m.vol_30d,
                    m.return_30d,
                    m.beta_60d,
                    a.tape_news,
                    a.vol_regime
                FROM watchlist w
                LEFT JOIN holdings h ON h.ticker = w.ticker
                LEFT JOIN LATERAL (
                    SELECT close
                    FROM analytics.mart_stock_metrics
                    WHERE ticker = w.ticker
                      AND date <= w.added_at::date
                    ORDER BY date DESC
                    LIMIT 1
                ) entry ON TRUE
                LEFT JOIN LATERAL (
                    SELECT date, close, daily_return, vol_30d, return_30d, beta_60d
                    FROM analytics.mart_stock_metrics
                    WHERE ticker = w.ticker
                    ORDER BY date DESC
                    LIMIT 1
                ) m ON TRUE
                LEFT JOIN LATERAL (
                    SELECT tape_news, vol_regime
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
            "shares": _jsonify(row[2]),
            "cost_per_share": _jsonify(row[3]),
            "default_cost": _jsonify(row[4]),
            "as_of": _jsonify(row[5]),
            "close": _jsonify(row[6]),
            "daily_return": _jsonify(row[7]),
            "vol_30d": _jsonify(row[8]),
            "return_30d": _jsonify(row[9]),
            "beta_60d": _jsonify(row[10]),
            "tape_news": row[11],
            "vol_regime": row[12],
        }
        for row in rows
    ]
    return attach_weights(payload)


def load_spy_metrics() -> dict | None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT date, close, daily_return, vol_30d, return_30d
                FROM analytics.mart_stock_metrics
                WHERE ticker = %s
                ORDER BY date DESC
                LIMIT 1
                """,
                (INDEX_TICKER,),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    """
                    SELECT date, close
                    FROM raw_prices
                    WHERE ticker = %s
                    ORDER BY date DESC
                    LIMIT 2
                    """,
                    (INDEX_TICKER,),
                )
                bars = cur.fetchall()
                if not bars:
                    return None
                last = bars[0]
                prev = bars[1] if len(bars) > 1 else None
                daily = None
                if prev and prev[1] and last[1]:
                    daily = float(last[1]) / float(prev[1]) - 1
                return {
                    "ticker": INDEX_TICKER,
                    "as_of": _jsonify(last[0]),
                    "close": _jsonify(last[1]),
                    "daily_return": daily,
                    "vol_30d": None,
                    "return_30d": None,
                }
    return {
        "ticker": INDEX_TICKER,
        "as_of": _jsonify(row[0]),
        "close": _jsonify(row[1]),
        "daily_return": _jsonify(row[2]),
        "vol_30d": _jsonify(row[3]),
        "return_30d": _jsonify(row[4]),
    }


def _macro_relevant(headline: str, summary: str | None) -> bool:
    blob = f"{headline or ''} {summary or ''}".upper()
    return any(needle in blob for needle in MACRO_NEWS_NEEDLES)


def _macro_item(row: dict, *, via: str) -> dict:
    headline = row.get("headline") or ""
    summary = row.get("summary")
    return {
        "headline": headline,
        "summary": summary,
        "source": row.get("source"),
        "published_at": _jsonify(row.get("published_at")),
        "sentiment": _jsonify(row.get("sentiment")),
        "relevant": _macro_relevant(headline, summary),
        "via": via,
    }


def _dedupe_headlines(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for item in items:
        key = (item.get("headline") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def load_macro_headlines(
    limit: int = 16, *, holding_tickers: list[str] | None = None
) -> list[dict]:
    """SPY Yahoo first; if that feed is empty, market stories already on the names."""
    out: list[dict] = []
    try:
        from data.news import fetch_news

        for row in fetch_news(INDEX_TICKER)[:limit]:
            out.append(_macro_item(row, via="spy"))
    except Exception:
        pass
    if len(out) < 4:
        try:
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT headline, summary, source, published_at, sentiment
                        FROM raw_news
                        WHERE ticker = %s
                        ORDER BY published_at DESC NULLS LAST
                        LIMIT %s
                        """,
                        (INDEX_TICKER, limit),
                    )
                    for headline, summary, source, published, sentiment in cur.fetchall():
                        out.append(
                            _macro_item(
                                {
                                    "headline": headline,
                                    "summary": summary,
                                    "source": source,
                                    "published_at": published,
                                    "sentiment": sentiment,
                                },
                                via="spy-db",
                            )
                        )
        except Exception:
            pass
    if len(out) < 6 and holding_tickers:
        try:
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT ticker, headline, summary, source, published_at, sentiment
                        FROM raw_news
                        WHERE ticker = ANY(%s)
                        ORDER BY published_at DESC NULLS LAST
                        LIMIT 40
                        """,
                        ([name.upper() for name in holding_tickers],),
                    )
                    for ticker, headline, summary, source, published, sentiment in cur.fetchall():
                        if not _macro_relevant(headline, summary):
                            continue
                        item = _macro_item(
                            {
                                "headline": headline,
                                "summary": summary,
                                "source": source,
                                "published_at": published,
                                "sentiment": sentiment,
                            },
                            via=f"via-{ticker}",
                        )
                        out.append(item)
        except Exception:
            pass
    return _dedupe_headlines(out)[:limit]


_TIGHT_MACRO = (
    "TREASURY",
    "FEDERAL RESERVE",
    "FED RATE",
    "RATE HIKE",
    "RATE CUT",
    "AI PAUSE",
    "AI SLOWDOWN",
    "AI-LINKED STOCKS",
    "AI WARNINGS",
    "CHIP STOCKS",
    "WALL STREET",
    "INFLATION",
    "CPI",
    "NASDAQ",
    "S&P 500",
    "S&P500",
)


def pick_macro_stories(headlines: list[dict], limit: int = 5) -> list[dict]:
    """Short list of market stories for the Book letter, not company recaps."""
    picked = []
    for item in headlines:
        blob = (item.get("headline") or "").upper()
        if not any(needle in blob for needle in _TIGHT_MACRO):
            continue
        picked.append(
            {
                "headline": item.get("headline"),
                "summary": item.get("summary"),
                "published_at": item.get("published_at"),
            }
        )
        if len(picked) >= limit:
            break
    return picked


def load_holding_news(tickers: list[str], as_of: str) -> list[dict]:
    """Relevant Yahoo headlines already dumped for each name. No new fetch."""
    rows = []
    day = str(as_of)[:10]
    for ticker in tickers:
        name = str(ticker).strip().upper()
        if not name:
            continue
        path = RAW_DIR / name / f"{day}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text())
        except Exception:
            continue
        relevant = []
        for item in payload.get("headlines") or []:
            if not item.get("relevant"):
                continue
            relevant.append(
                {
                    "headline": item.get("headline"),
                    "summary": item.get("summary"),
                    "published_at": item.get("published_at"),
                    "sentiment": item.get("sentiment"),
                }
            )
            if len(relevant) >= 3:
                break
        rows.append({"ticker": name, "relevant": relevant})
    return rows


def load_book_snapshot() -> dict:
    rows = load_watchlist_metric_rows()
    book = summarize_book(rows)
    spy = load_spy_metrics()
    headlines = load_macro_headlines(
        holding_tickers=[row["ticker"] for row in rows]
    )
    relevant = [item for item in headlines if item.get("relevant")]
    caveats = list(book.get("caveats") or [])
    if spy is None:
        caveats.append("No SPY bar in marts/raw_prices; macro tape is missing.")
    if not headlines:
        caveats.append("No SPY or market headlines in this dump.")
    as_of = book.get("as_of") or (str(spy["as_of"])[:10] if spy else None)
    risk = book_risk_for_holdings(book.get("names") or [])
    if risk.get("correlation") is not None and risk.get("correlation_label"):
        pair = risk.get("correlation_pair") or "holdings"
        caveats.append(
            f"{pair} 90-session correlation is {risk['correlation']:.2f} "
            f"({risk['correlation_label']}); constant today's weights."
        )
    if risk.get("beta_vs_spy") is not None:
        vs = "higher" if risk["beta_vs_spy"] > 1 else "lower or similar"
        caveats.append(
            f"Book beta vs SPY is {risk['beta_vs_spy']:.2f} ({vs} market sensitivity; "
            "60 sessions, constant weights)."
        )
    return {
        "kind": "book",
        "as_of": as_of,
        "book": book,
        "risk": risk,
        "macro": {
            "spy": spy,
            "headlines": headlines,
            "relevant_news_count": len(relevant),
        },
        "caveats": caveats,
        "watchlist_tickers": [row["ticker"] for row in rows],
        "holding_news": load_holding_news(
            [row["ticker"] for row in rows], as_of or date.today().isoformat()
        ),
    }


def dump_book(*, overwrite: bool = False) -> tuple[dict, str]:
    """Write raw/Book/{as_of}.json. Existing files stay unless overwrite."""
    snapshot = load_book_snapshot()
    as_of = str(snapshot.get("as_of") or date.today().isoformat())[:10]
    snapshot["as_of"] = as_of
    folder = RAW_DIR / "Book"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{as_of}.json"
    if path.exists() and not overwrite:
        existing = json.loads(path.read_text())
        if not (existing.get("risk") or {}).get("lookback"):
            existing["risk"] = snapshot.get("risk")
            caveats = list(existing.get("caveats") or [])
            for note in snapshot.get("caveats") or []:
                if note not in caveats and (
                    "correlation" in note.lower() or "beta" in note.lower()
                ):
                    caveats.append(note)
            existing["caveats"] = caveats
            path.write_text(json.dumps(existing, indent=2) + "\n")
        return existing, str(path)
    path.write_text(json.dumps(snapshot, indent=2) + "\n")
    return snapshot, str(path)


def dump_macro(*, as_of: str, snapshot: dict | None = None, overwrite: bool = False) -> tuple[dict, str]:
    """Write raw/macro/{as_of}.json (SPY bar + headlines)."""
    payload = snapshot or load_book_snapshot()
    macro = {
        "kind": "macro",
        "as_of": as_of,
        "spy": (payload.get("macro") or {}).get("spy"),
        "headlines": (payload.get("macro") or {}).get("headlines") or [],
        "relevant_news_count": (payload.get("macro") or {}).get("relevant_news_count"),
        "caveats": [
            note
            for note in (payload.get("caveats") or [])
            if "headline" in note.lower()
            or "macro tape" in note.lower()
            or note.startswith("No SPY")
        ],
    }
    folder = RAW_DIR / "macro"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{as_of}.json"
    if path.exists() and not overwrite:
        return json.loads(path.read_text()), str(path)
    path.write_text(json.dumps(macro, indent=2) + "\n")
    return macro, str(path)


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"


def _usd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _ratio(value, digits: int = 2) -> str:
    number = _num(value)
    if number is None:
        return "—"
    return f"{number:.{digits}f}"


def render_book_source(snapshot: dict) -> str:
    as_of = str(snapshot.get("as_of"))[:10]
    book = snapshot.get("book") or {}
    lines = [
        f"# Book snapshot {as_of}",
        "",
        "Receipt for this session. Numbers copied from `raw/Book/`. Do not edit other days.",
        "",
        f"- Book value: {_usd(book.get('book_value'))}",
        f"- Cost: {_usd(book.get('cost_basis'))}",
        f"- Unrealized P/L: {_usd(book.get('unrealized'))} ({_pct(book.get('unrealized_pct'))})",
        f"- Last session $: {_usd(book.get('day_dollar'))} ({_pct(book.get('day_pct'))})",
        f"- 30-day weighted: {_pct(book.get('return_30d_weighted'))}",
        f"- Names with shares: {book.get('name_count')}",
        f"- Top weight: {book.get('top_ticker') or '—'} {_pct(book.get('top_weight'))}",
        "",
        "## Risk (constant today's weights)",
        "",
    ]
    risk = snapshot.get("risk") or {}
    corr_pair = risk.get("correlation_pair") or "pair"
    lines.extend(
        [
            f"- Concentration: {risk.get('concentration_label') or '—'} "
            f"{risk.get('top_ticker') or ''} {_pct(risk.get('top_weight'))}".rstrip(),
            f"- Names: {risk.get('name_count') if risk.get('name_count') is not None else book.get('name_count')}",
            f"- Sector: {risk.get('sector_line') or '—'}",
            f"- Correlation ({risk.get('corr_window') or 90}d {corr_pair}): "
            f"{_ratio(risk.get('correlation'))} ({risk.get('correlation_label') or 'n/a'})",
            f"- Book vol ({risk.get('vol_window') or 30} session std, not annualized): "
            f"{_pct(_num(risk.get('vol_30d')))}",
            f"- Book beta vs SPY ({risk.get('beta_window') or 60} sessions): "
            f"{_ratio(risk.get('beta_vs_spy'))}",
            f"- Book drawdown ({risk.get('drawdown_window') or 90}d peak): "
            f"{_pct(_num(risk.get('drawdown_90d')))}",
            "- "
            + (
                risk.get("lookback")
                or "Constant today's weights over the lookback."
            ),
        ]
    )
    if risk.get("assessment"):
        lines.extend(["", risk["assessment"]])
    lines.extend(
        [
            "",
            "| Ticker | Shares | Close | Weight | Day $ | Unrealized |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in book.get("names") or []:
        lines.append(
            f"| {row['ticker']} | {row.get('shares') if row.get('shares') is not None else '—'} "
            f"| {_usd(row.get('close'))} | {_pct(row.get('weight'))} "
            f"| {_usd(row.get('day_dollar'))} | {_usd(row.get('unrealized'))} |"
        )
    unheld = book.get("unheld") or []
    if unheld:
        lines.append("")
        lines.append(
            "Tracked with no shares: "
            + ", ".join(item["ticker"] for item in unheld)
            + "."
        )
    lines.append("")
    lines.append("Caveats:")
    for note in snapshot.get("caveats") or ["(none)"]:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def render_macro_source(macro: dict) -> str:
    as_of = str(macro.get("as_of"))[:10]
    spy = macro.get("spy") or {}
    lines = [
        f"# Macro (SPY) {as_of}",
        "",
        "US large-cap tape proxy. Not a holding. Headlines are Yahoo SPY feed, filtered.",
        "",
        f"- SPY close: {_usd(_num(spy.get('close')))}",
        f"- SPY daily return: {_pct(_num(spy.get('daily_return')))}",
        f"- SPY 30d return: {_pct(_num(spy.get('return_30d')))}",
        f"- SPY 30d vol: {_pct(_num(spy.get('vol_30d')))}",
        "",
        "## Relevant headlines",
        "",
    ]
    relevant = [item for item in (macro.get("headlines") or []) if item.get("relevant")]
    if not relevant:
        lines.append("- (none in this dump)")
    for item in relevant[:8]:
        url = item.get("url") or ""
        headline = item.get("headline") or ""
        if url.startswith("http"):
            lines.append(f"- [{headline}]({url})")
        else:
            lines.append(f"- {headline}")
    ignored = [item for item in (macro.get("headlines") or []) if not item.get("relevant")]
    if ignored:
        lines.append("")
        lines.append("## Ignored")
        lines.append("")
        for item in ignored[:6]:
            lines.append(f"- {item.get('headline')}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    snap, path = dump_book(overwrite=True)
    as_of = str(snap["as_of"])[:10]
    macro_path = dump_macro(as_of=as_of, snapshot=snap, overwrite=True)[1]
    print(f"book {path}")
    print(f"macro {macro_path}")

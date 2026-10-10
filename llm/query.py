"""Query: read the wiki, write a new dated holder letter under outputs/."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from llm.brief import dump_brief
from llm.client import complete
from llm.paths import INDEX_PATH, LOG_PATH, OUTPUTS_DIR, ROOT, SCHEMA_PATH, WIKI_DIR
from llm.wiki_graph import format_linked_pages, linked_wiki_pages


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text()


def _without_urls(value):
    """Drop URL fields so the letter cannot paste a Yahoo link dump."""
    if isinstance(value, dict):
        return {
            key: _without_urls(item)
            for key, item in value.items()
            if key not in {"url", "link"}
        }
    if isinstance(value, list):
        return [_without_urls(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    return value


def _write_letter(*, slug: str, as_of: str, generated: str, markdown: str, ingest_meta: dict | None) -> dict:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{generated}-{slug.lower()}-daily.md"
    out_path = OUTPUTS_DIR / filename
    n = 2
    while out_path.exists():
        filename = f"{generated}-{slug.lower()}-daily-{n}.md"
        out_path = OUTPUTS_DIR / filename
        n += 1
    header = f"<!-- ticker={slug} as_of={as_of} generated={generated} -->\n"
    out_path.write_text(header + markdown)
    skipped = bool(ingest_meta and ingest_meta.get("skipped"))
    log_entry = (
        f"## [{generated}] query | {slug}\n"
        f"Wrote `{out_path.relative_to(ROOT)}` from wiki as_of {as_of}"
        f"{' (ingest skipped, source already existed)' if skipped else ''}.\n"
    )
    log = _read(LOG_PATH)
    LOG_PATH.write_text(log.rstrip() + "\n\n" + log_entry + "\n")
    query_dir = WIKI_DIR / "queries"
    query_dir.mkdir(parents=True, exist_ok=True)
    (query_dir / filename).write_text(
        f"Filed letter. Canonical copy: `outputs/{filename}`\n"
    )
    return {
        "ticker": slug,
        "as_of": as_of,
        "filename": filename,
        "path": str(out_path),
        "ingest_skipped": skipped,
    }


def generate_report(ticker: str, *, ingest_first: bool = True) -> dict:
    ticker = ticker.strip().upper()
    ingest_meta = None
    if ingest_first:
        from llm.ingest import ingest_ticker

        ingest_meta = ingest_ticker(ticker)
    brief, _raw = dump_brief(ticker)
    as_of = str(brief["as_of"])[:10]
    generated = datetime.now(timezone.utc).date().isoformat()
    entity_path = WIKI_DIR / "entities" / f"{ticker}.md"
    source_path = WIKI_DIR / "sources" / f"{ticker}-{as_of}.md"
    schema = _read(SCHEMA_PATH)
    linked = linked_wiki_pages([entity_path, source_path], limit=8)
    user = f"""Write a front-facing holder letter for {ticker} ({brief.get("company_name")}).
Follow the schema Query rules. This is NOT a wiki page and NOT a metrics dump.

Use only the wiki and this snapshot. as_of={as_of} is the last price bar.
Today's calendar date for the letter is {generated}.
Follow linked entity/concept pages — those are compiled memory (CoreWeave,
useful yield, AMD). Do not re-derive them from headlines if the wiki already
says it. Numbers and tonight's tape come from the JSON snapshot.

Caveats from the dump:
{json.dumps(brief.get("caveats") or [], indent=2)}

index.md:
---
{_read(INDEX_PATH)}
---
entity (rolling thesis — do not paste this back as the letter):
---
{_read(entity_path) or "(missing — ingest first)"}
---
latest source:
---
{_read(source_path) or "(missing)"}
---
linked wiki pages (fan-out nodes; cite their paths when you use them):
---
{format_linked_pages(linked)}
---
JSON snapshot:
{json.dumps(_without_urls(brief), indent=2)}

Return ONLY the letter markdown (no JSON). Four blocks in this order.
No lead paragraphs before the first heading. No URLs and no markdown
links anywhere in the letter.

# {ticker} — {generated}

## What's happening
Prose. The one biggest story for this stock (a second only if it is
clearly the same magnitude). Not a rundown of every headline. If nothing
relevant, say so. Do not invent a catalyst.

## How it's faring
Tonight's tape: close, day move, volume, vs 30d MA / 30d return.
Did the print match that story (tape vs news)?

## Evaluation
Derived stats in English: vol_30d, idio_z / vol regime, drawdown, beta,
valuation (P/E, cap). Teach; do not reprint a table.

## Stance
Exactly one of Hold, Add, Trim, Watch. Bold it on the first line
(**Stance: Hold**). Conditional on THIS snapshot — not a forecast.
Why, what would flip it, what is missing (holiday gap, no article body,
news after as_of, junk firehose).

Forbidden: restating the entity page section-for-section; inventing a
catalyst; treating unrelated Motley Fool headlines as this ticker's story;
Buy/Sell day-trade language; pasting URLs.
"""
    markdown = complete(schema, user).strip() + "\n"
    return _write_letter(
        slug=ticker,
        as_of=as_of,
        generated=generated,
        markdown=markdown,
        ingest_meta=ingest_meta,
    )


def _book_query_pages(snapshot: dict, as_of: str) -> list[Path]:
    """Book hub + watchlist entities/latest sources + Book's linked concepts. Cap 12."""
    paths: list[Path] = [WIKI_DIR / "entities" / "Book.md"]
    for ticker in snapshot.get("watchlist_tickers") or []:
        paths.append(WIKI_DIR / "entities" / f"{ticker}.md")
        paths.append(WIKI_DIR / "sources" / f"{ticker}-{as_of}.md")
    paths.append(WIKI_DIR / "sources" / f"Book-{as_of}.md")
    paths.append(WIKI_DIR / "sources" / f"macro-{as_of}.md")
    seeds = [WIKI_DIR / "entities" / "Book.md"] + [
        WIKI_DIR / "entities" / f"{ticker}.md"
        for ticker in snapshot.get("watchlist_tickers") or []
    ]
    extra = linked_wiki_pages(seeds, limit=8)
    seen = {path.resolve() for path in paths if path.exists()}
    for path in extra:
        if path.resolve() in seen:
            continue
        paths.append(path)
        seen.add(path.resolve())
        if len([item for item in paths if item.exists()]) >= 12:
            break
    return [path for path in paths if path.exists()]


def generate_book_report(*, ingest_first: bool = True) -> dict:
    ingest_meta = None
    if ingest_first:
        from llm.ingest import ingest_book

        ingest_meta = ingest_book()
    from llm.book import (
        dump_book,
        load_holding_news,
        load_macro_headlines,
        pick_macro_stories,
    )

    snapshot, _raw = dump_book(overwrite=False)
    as_of = str(snapshot.get("as_of"))[:10]
    tickers = snapshot.get("watchlist_tickers") or []
    snapshot["holding_news"] = load_holding_news(tickers, as_of)
    live_macro = load_macro_headlines(holding_tickers=tickers)
    if live_macro:
        snapshot.setdefault("macro", {})["headlines"] = live_macro
        snapshot["macro"]["relevant_news_count"] = len(live_macro)
        snapshot["caveats"] = [
            note
            for note in (snapshot.get("caveats") or [])
            if "headline" not in note.lower()
        ]
    snapshot["macro_stories"] = pick_macro_stories(
        (snapshot.get("macro") or {}).get("headlines") or []
    )
    generated = datetime.now(timezone.utc).date().isoformat()
    schema = _read(SCHEMA_PATH)
    pages = _book_query_pages(snapshot, as_of)
    user = f"""Write a front-facing BOOK letter (the whole portfolio).
Follow schema Book query rules. This is NOT a wiki page and NOT a stock-pick list.

Use only the wiki and this snapshot. as_of={as_of} is the last price bar.
Today's calendar date for the letter is {generated}.
Read Book.md as the hub, watchlist ticker pages as the names in the book,
linked concepts as compiled memory, macro source as SPY/US tape.
JSON `holding_news` is candidate company stories — pick at most ONE for
the book. JSON `macro_stories` is the market beat (SPY Yahoo is often
empty, so these are market items that landed on the names). If
`macro_stories` is non-empty you MUST use one of them as the Macro beat.
JSON `risk` is the combined book (constant today's weights). Use those
numbers in ## Evaluation.
Do not invent Fed/economy claims that are not in the macro dump.
Do not recommend tickers that are not already on the watchlist or already
wiki entities used as GAPS (e.g. you don't own Microsoft — not "buy MSFT").

Caveats:
{json.dumps(snapshot.get("caveats") or [], indent=2)}

index.md:
---
{_read(INDEX_PATH)}
---
wiki context:
---
{format_linked_pages(pages, max_chars=2200)}
---
JSON snapshot:
{json.dumps(_without_urls(snapshot), indent=2)}

Return ONLY the letter markdown (no JSON). Four blocks in this order.
No lead paragraphs before the first heading. No URLs and no markdown
links anywhere in the letter.

# Book — {generated}

## What's happening
Prose. Two short beats, not a headline list:
1. The single biggest story for this book (one event, not every name).
2. Macro: ALWAYS include this beat. If `macro_stories` has items, write
   1–3 sentences from those headlines (Treasury/yields, AI pause, chip
   selloff, Wall Street). Do not write "no macro news" and do not replace
   this beat with SPY's daily return. Only if `macro_stories` is empty
   may you say the dump had none. Do not invent.

## How the book is faring
Last session $ and %, who moved the dollars, weights, P/L vs cost, vs SPY.
Teach; do not reprint the mix table.

## Evaluation
Combined book `risk` (not an average of names): concentration, 90d
correlation (flag ≳ 0.75 as historically moving together), beta vs SPY,
30d book vol, 90d drawdown, sector. Quote the snapshot numbers. Constant
today's weights. Then per-name stats (vol, beta, valuation) where present.
Gaps as missing *roles* already on the wiki (customer, energy, index hedge),
not a shopping list.

## Stance
Exactly one of **Hold mix**, **Trim {{TICKER}}**, **Add {{TICKER}}** (already held),
**Watch**, **Note gap**. Bold it (**Stance: Hold mix**). Conditional on THIS snapshot.
Why, what would flip it, what is missing.

Forbidden: Buy/Sell; new ticker recommendations; inventing catalysts; pasting
entity pages section-for-section; Yahoo URL lists; treating celebrity/outlet
noise as the economy.
"""
    markdown = complete(schema, user, max_tokens=4000).strip() + "\n"
    return _write_letter(
        slug="book",
        as_of=as_of,
        generated=generated,
        markdown=markdown,
        ingest_meta=ingest_meta,
    )


def report_filename_needle(ticker: str) -> str:
    return f"-{ticker.strip().lower()}-daily"


def list_reports(ticker: str | None = None) -> list[dict]:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    needle = report_filename_needle(ticker) if ticker else None
    paths = [
        path
        for path in OUTPUTS_DIR.glob("*.md")
        if path.name != "README.md"
    ]
    for path in sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True):
        if needle and needle not in path.name.lower():
            continue
        text = path.read_text()[:400]
        rows.append(
            {
                "filename": path.name,
                "path": str(path),
                "preview": text.split("\n", 2)[-1][:180],
            }
        )
    return rows


def read_report(filename: str) -> str:
    path = OUTPUTS_DIR / Path(filename).name
    if not path.exists() or path.suffix != ".md":
        raise FileNotFoundError(filename)
    return path.read_text()


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    skip = "--no-ingest" in sys.argv
    if target.lower() == "book":
        print(json.dumps(generate_book_report(ingest_first=not skip), indent=2))
    else:
        print(json.dumps(generate_report(target, ingest_first=not skip), indent=2))


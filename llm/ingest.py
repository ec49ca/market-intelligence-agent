"""Ingest: dump Postgres → raw/ → source page + ticker patch + fan-out + log."""

from __future__ import annotations

import json
from pathlib import Path

from llm.brief import dump_brief
from llm.client import complete, parse_json_object
from llm.paths import INDEX_PATH, LOG_PATH, SCHEMA_PATH, WIKI_DIR
from llm.wiki_edit import (
    MAX_OPEN_QUESTIONS,
    append_see_also,
    apply_unique_replaces,
    cap_section_bullets,
    has_thesis_heading,
    index_has_needle,
    insert_after_section,
    mutate_bullets,
    replace_section,
    tidy_see_also,
    upsert_index_line,
)
from llm.wiki_graph import (
    MAX_FANOUT,
    apply_fanout_item,
    catalog_wiki,
    hint_fanout_targets,
    is_ticker_slug,
    neighbor_page_bodies,
    page_path,
    parse_fanout_items,
    sentence_about,
    stub_page,
    ticker_links_to_fanout,
)


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text()


def _apply_entity_patches(existing: str, payload: dict, *, ticker: str, as_of: str) -> tuple[str, dict]:
    notes = {"applied": [], "skipped": []}
    text = existing
    last_session = (payload.get("last_session") or "").strip()
    if last_session:
        text = replace_section(text, "Last session", last_session)
        notes["applied"].append("last_session")
    text, applied, skipped = apply_unique_replaces(text, payload.get("thesis_edits") or [])
    notes["applied"].extend(f"thesis:{item}" for item in applied)
    notes["skipped"].extend(f"thesis:{item}" for item in skipped)
    contradiction = (payload.get("contradiction") or "").strip()
    if contradiction:
        if not contradiction.startswith(">"):
            contradiction = f"> {as_of}: {contradiction}"
        text = insert_after_section(text, "Thesis", contradiction)
        notes["applied"].append("contradiction")
    before = text
    text = mutate_bullets(
        text,
        "Open questions",
        add=payload.get("open_questions_add") or [],
        remove=payload.get("open_questions_remove") or [],
    )
    if text != before:
        notes["applied"].append("open_questions")
    before = text
    text = append_see_also(
        text,
        (payload.get("see_also_add") or [])
        + [f"[{as_of}](../sources/{ticker}-{as_of}.md)"],
    )
    if text != before:
        notes["applied"].append("see_also")
    text = cap_section_bullets(text, "Open questions", MAX_OPEN_QUESTIONS)
    text = tidy_see_also(text)
    return text, notes


def _fanout_contract(*, ticker: str, as_of: str) -> str:
    return f"""Fan-out (required when the snapshot or thesis names durable others):
- Priority 1: names **already in this ticker's Thesis / Open questions**
  (CoreWeave, Microsoft, Firmus, OpenAI, AMD, useful yield, tape vs news).
  Those MUST occupy fanout slots before any new headline name.
- Priority 2: counterparties in **relevant** headlines that will recur.
- Skip personal-finance framing (ETFs, retirement, 'sell the shares').
- Skip a peer mentioned only as a one-line comparison (e.g. Marvell beat NVDA)
  unless they are a customer, holding, or deal partner.
- fanout: array, max 6 objects. Each:
  - kind: "entity" or "concept"
  - slug: entity TitleCase (CoreWeave, Microsoft) or concept kebab-case
    (useful-yield, tape-vs-news). Not {ticker}. Not publishers.
  - index_line: one bullet starting with "{{slug}}:"
  - create: FULL markdown only if that file does not already exist.
    Headings: Thesis, Last mention ({as_of}), See also. ≤25 lines.
    See also must link [{ticker}](relative) and this source page.
  - last_mention: REQUIRED for existing satellites: 1-2 sentences of what
    THIS ticker's snapshot said about the slug. Code stores a {ticker}: bullet
    and keeps other tickers' bullets. Never omit. Not for other watchlist
    tickers like AMD — those keep their own Last session.
  - thesis_edits / see_also_add / open_questions_add / open_questions_remove
    / contradiction: same surgical rules as the ticker page
Prefer patching an existing slug from the catalog over a new near-duplicate.
"""


def _merge_fanout(
    llm_items: list, *, ticker: str, as_of: str, thesis: str, corpus: str
) -> list[dict]:
    """Thesis names always get nodes. LLM copy wins when it targeted the same slug."""
    hints = hint_fanout_targets(thesis, ticker)
    extra = hint_fanout_targets(corpus, ticker)
    for item in extra:
        if item not in hints:
            hints.append(item)
    hints = hints[:MAX_FANOUT]
    hint_items: dict[tuple[str, str], dict] = {}
    for kind, slug in hints:
        needle = slug.replace("-", " ")
        blurb = sentence_about(thesis, needle) or sentence_about(
            corpus, needle
        ) or sentence_about(corpus, slug)
        index_line = f"{slug}: {blurb or f'Named in {ticker} thesis.'}"
        hint_items[(kind, slug)] = {
            "kind": kind,
            "slug": slug,
            "index_line": index_line,
            "last_mention": blurb or f"Named in {ticker} {as_of} coverage.",
            "create": stub_page(
                kind,
                slug,
                ticker=ticker,
                as_of=as_of,
                item={"index_line": index_line, "last_mention": blurb},
            ),
        }
    for item in llm_items:
        key = (item["kind"], item["slug"])
        if key in hint_items:
            merged = dict(hint_items[key])
            for field, value in item.items():
                if value not in (None, "", [], {}):
                    merged[field] = value
            hint_items[key] = merged
    ordered: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for kind, slug in hints:
        key = (kind, slug)
        ordered.append(hint_items[key])
        seen.add(key)
        if len(ordered) >= MAX_FANOUT:
            break
    if len(ordered) < MAX_FANOUT:
        for item in llm_items:
            key = (item["kind"], item["slug"])
            if key in seen:
                continue
            ordered.append(item)
            seen.add(key)
            if len(ordered) >= MAX_FANOUT:
                break
    for item in ordered:
        if (item.get("last_mention") or "").strip():
            continue
        needle = str(item.get("slug") or "").replace("-", " ")
        blurb = sentence_about(thesis, needle) or sentence_about(corpus, needle)
        item["last_mention"] = blurb or f"Named in {ticker} {as_of} coverage."
    return ordered


def ingest_ticker(
    ticker: str, *, overwrite_raw: bool = False, force: bool = False
) -> dict:
    ticker = ticker.strip().upper()
    brief, raw_path = dump_brief(ticker, overwrite=overwrite_raw or force)
    as_of = str(brief["as_of"])[:10]
    entity_path = WIKI_DIR / "entities" / f"{ticker}.md"
    source_path = WIKI_DIR / "sources" / f"{ticker}-{as_of}.md"
    entity_exists = entity_path.exists()
    if source_path.exists() and not force:
        return {
            "ticker": ticker,
            "as_of": as_of,
            "raw_path": raw_path,
            "entity_path": str(entity_path),
            "source_path": str(source_path),
            "skipped": True,
        }
    existing_entity = _read(entity_path)
    existing_index = _read(INDEX_PATH)
    schema = _read(SCHEMA_PATH)
    first = not entity_exists or not has_thesis_heading(existing_entity)
    neighbors = neighbor_page_bodies(skip_ticker=ticker)
    catalog = catalog_wiki()
    hint_corpus = existing_entity + json.dumps(brief.get("headlines") or [])
    required = hint_fanout_targets(hint_corpus, ticker)
    required_line = ""
    if required:
        slugs = ", ".join(f"{kind}:{slug}" for kind, slug in required)
        required_line = (
            f"Required fan-out slugs from the current thesis (include these in "
            f"fanout; code will mint stubs if you omit them): {slugs}\n"
        )
    if first:
        contract = f"""The ticker entity page does not exist yet. Return JSON with:
- source_markdown: wiki/sources/{ticker}-{as_of}.md (this date only; numbers table lives here)
- entity_create: FULL first markdown for wiki/entities/{ticker}.md
  Headings MUST be Thesis, Last session ({as_of}), Open questions, See also.
  Thesis is prose about the business. Forbidden headings: Snapshot,
  Attention and Sentiment, Recent News Highlights, metric dump tables.
  Last session ≤6 bullets + link to ../sources/{ticker}-{as_of}.md.
- index_entity_line: one bullet starting with "{ticker}:"
- index_source_line: one bullet starting with "{ticker}-{as_of}:"
- log_entry: one block starting with ## [{as_of}] ingest | {ticker}
  Name every fan-out slug in the log body.
{_fanout_contract(ticker=ticker, as_of=as_of)}
Never send a full rewrite of index.md or other tickers' Last session.
"""
    else:
        contract = f"""The ticker entity page already exists. Do NOT return a full entity or index file.
Return JSON with:
- source_markdown: wiki/sources/{ticker}-{as_of}.md (this date only; replace that day's receipt only)
- last_session: markdown for the Last session section only, starting with
  ## Last session ({as_of})
  ≤6 bullets + link to ../sources/{ticker}-{as_of}.md
- thesis_edits: array of {{"old": "exact substring copied from the current Thesis", "new": "..."}}
  Empty array if the thesis still holds. old MUST appear exactly once in the current page.
- contradiction: short callout if today contradicts the current thesis, else ""
- open_questions_add: new bullet strings (no leading dash). Empty if none.
- open_questions_remove: exact existing bullets that this snapshot resolved. Empty if none.
- see_also_add: extra markdown links to fan-out pages. The {as_of} source link is added in code.
- index_entity_line: replacement one-liner starting with "{ticker}:"
- index_source_line: one bullet starting with "{ticker}-{as_of}:"
- log_entry: one block starting with ## [{as_of}] ingest | {ticker}
Forbidden: entity_create, index_markdown, wiping Thesis or Open questions,
replacing another ticker's Last session.
{_fanout_contract(ticker=ticker, as_of=as_of)}
"""
    user = f"""Ingest this source. Follow the schema Ingest rules.
Surgical edits only. Fan out to shared entity/concept pages. Memory
maintenance, not a holder letter. No Hold/Add/Trim.
{required_line}
Raw path: {raw_path}
Existing ticker entity page:
---
{existing_entity or "(none yet)"}
---
{catalog}

Other entity/concept page bodies (for patches; do not rewrite unrelated claims):
---
{neighbors}
---
Current index.md (other lines must survive; you do not rewrite this file):
---
{existing_index}
---
JSON snapshot:
{json.dumps(brief, indent=2)}

{contract}
"""
    payload = parse_json_object(complete(schema, user, max_tokens=8000))
    source_markdown = payload.get("source_markdown")
    if not source_markdown:
        raise ValueError("ingest did not return source_markdown")
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(str(source_markdown).rstrip() + "\n")

    fanout_items = _merge_fanout(
        parse_fanout_items(payload, ticker=ticker),
        ticker=ticker,
        as_of=as_of,
        thesis=existing_entity,
        corpus="\n".join(
            [
                existing_entity,
                str(source_markdown),
                json.dumps(brief.get("headlines") or []),
            ]
        ),
    )
    auto_links = ticker_links_to_fanout(fanout_items)

    patch_notes = {"applied": [], "skipped": []}
    entity_path.parent.mkdir(parents=True, exist_ok=True)
    if first:
        created = payload.get("entity_create") or payload.get("entity_markdown")
        if not created:
            raise ValueError("first ingest did not return entity_create")
        text = append_see_also(
            str(created).rstrip() + "\n",
            auto_links + [f"[{as_of}](../sources/{ticker}-{as_of}.md)"],
        )
        if not has_thesis_heading(text):
            raise ValueError("entity_create must include a ## Thesis heading")
        text = cap_section_bullets(text, "Open questions", MAX_OPEN_QUESTIONS)
        text = tidy_see_also(text)
        entity_path.write_text(text)
        patch_notes["applied"].append("entity_create")
    else:
        merged = dict(payload)
        merged["see_also_add"] = list(payload.get("see_also_add") or []) + auto_links
        patched, patch_notes = _apply_entity_patches(
            existing_entity, merged, ticker=ticker, as_of=as_of
        )
        entity_path.write_text(patched)

    fanout_notes = []
    for item in fanout_items:
        kind = item["kind"]
        slug = item["slug"]
        path = page_path(kind, slug)
        existing = _read(path)
        text, notes = apply_fanout_item(
            existing, item, kind=kind, slug=slug, ticker=ticker, as_of=as_of
        )
        if not text.strip():
            fanout_notes.append({"slug": slug, "kind": kind, "skipped": notes["skipped"]})
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        fanout_notes.append(
            {
                "slug": slug,
                "kind": kind,
                "path": str(path),
                "created": not bool(existing.strip()),
                "patches": notes,
            }
        )

    index = existing_index or (
        "# Wiki index\n\nCatalog of LLM-maintained pages. Updated on ingest.\n\n"
        "## Entities\n\n## Sources\n\n## Concepts\n\n_(none yet)_\n"
    )
    entity_line = (payload.get("index_entity_line") or "").strip()
    source_line = (payload.get("index_source_line") or "").strip()
    if entity_line:
        index = upsert_index_line(index, "Entities", ticker, entity_line)
    if source_line:
        index = upsert_index_line(index, "Sources", f"{ticker}-{as_of}", source_line)
    for item in fanout_items:
        if item["kind"] == "entity" and is_ticker_slug(item["slug"]) and item["slug"] != ticker:
            continue
        line = (item.get("index_line") or "").strip()
        if not line:
            line = f"{item['slug']}: linked from {ticker} {as_of}"
        if len(line) > 220:
            line = line[:217].rstrip() + "..."
        section = "Entities" if item["kind"] == "entity" else "Concepts"
        created = any(
            note.get("created")
            and note.get("slug") == item["slug"]
            and note.get("kind") == item["kind"]
            for note in fanout_notes
        )
        if not created and index_has_needle(index, section, item["slug"]):
            continue
        index = upsert_index_line(index, section, item["slug"], line)
    INDEX_PATH.write_text(index)

    log_entry = (payload.get("log_entry") or "").rstrip()
    slugs = ", ".join(item["slug"] for item in fanout_items) or "none"
    if f"fanout: {slugs}" not in log_entry.lower() and fanout_items:
        log_entry = (log_entry + f"\nFan-out: {slugs}").strip()
    if log_entry.strip():
        existing_log = _read(LOG_PATH)
        block = log_entry.strip()
        if block not in existing_log:
            LOG_PATH.write_text(existing_log.rstrip() + "\n\n" + block + "\n")

    return {
        "ticker": ticker,
        "as_of": as_of,
        "raw_path": raw_path,
        "entity_path": str(entity_path),
        "source_path": str(source_path),
        "skipped": False,
        "first_entity": first,
        "patches": patch_notes,
        "fanout": fanout_notes,
    }


def ingest_book(*, overwrite_raw: bool = False, force: bool = False) -> dict:
    """Compile wiki/entities/Book.md from holdings mix + SPY. Does not patch ticker Last session."""
    from llm.book import (
        dump_book,
        dump_macro,
        render_book_source,
        render_macro_source,
    )

    snapshot, raw_path = dump_book(overwrite=overwrite_raw or force)
    as_of = str(snapshot.get("as_of"))[:10]
    dump_macro(as_of=as_of, snapshot=snapshot, overwrite=overwrite_raw or force)
    entity_path = WIKI_DIR / "entities" / "Book.md"
    source_path = WIKI_DIR / "sources" / f"Book-{as_of}.md"
    macro_path = WIKI_DIR / "sources" / f"macro-{as_of}.md"
    if source_path.exists() and not force:
        return {
            "ticker": "Book",
            "as_of": as_of,
            "raw_path": raw_path,
            "entity_path": str(entity_path),
            "source_path": str(source_path),
            "skipped": True,
        }

    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(render_book_source(snapshot).rstrip() + "\n")
    macro_path.write_text(
        render_macro_source(
            {
                "as_of": as_of,
                **(snapshot.get("macro") or {}),
            }
        ).rstrip()
        + "\n"
    )

    existing_entity = _read(entity_path)
    existing_index = _read(INDEX_PATH)
    schema = _read(SCHEMA_PATH)
    first = not entity_path.exists() or not existing_entity.strip()
    tickers = snapshot.get("watchlist_tickers") or []
    ticker_links = [f"[{name}]({name}.md)" for name in tickers]
    required_links = ticker_links + [
        f"[{as_of}](../sources/Book-{as_of}.md)",
        f"[macro {as_of}](../sources/macro-{as_of}.md)",
    ]
    catalog = catalog_wiki()
    if first:
        contract = f"""The Book entity page does not exist yet. Return JSON with:
- entity_create: FULL first markdown for wiki/entities/Book.md
  Headings: Thesis, Last session ({as_of}), Open questions, See also.
  Thesis: what this book IS (theme, concentration, what is missing). Not a metric dump.
  Last session ≤6 bullets: mix, who moved dollars, SPY vs the book, and the
  Risk block (concentration, 90d corr, beta vs SPY, 30d book vol, 90d
  drawdown, sector). Copy those numbers; do not invent. Link the Book source.
  Do not paste NVDA/AMD Last session blocks.
- index_entity_line: one bullet starting with "Book:"
- index_source_line: one bullet starting with "Book-{as_of}:"
- index_macro_line: one bullet starting with "macro-{as_of}:"
- log_entry: one block starting with ## [{as_of}] ingest | Book
Never send fanout. Never rewrite another ticker's Last session.
"""
    else:
        contract = f"""Book.md already exists. Do NOT return entity_create or a full rewrite.
Return JSON with:
- last_session: markdown for Last session only, starting with ## Last session ({as_of})
  ≤6 bullets + link to ../sources/Book-{as_of}.md. Mix, SPY, and the Risk
  numbers (corr/beta/vol/drawdown/sector). Book tape only.
- thesis_edits: array of {{"old": "...", "new": "..."}} or []
- contradiction: short callout if mix/theme changed, else ""
- open_questions_add / open_questions_remove: bullet strings
- see_also_add: extra links to EXISTING wiki entities/concepts only
- index_entity_line: "Book: ..."
- index_source_line: "Book-{as_of}: ..."
- index_macro_line: "macro-{as_of}: ..."
- log_entry: ## [{as_of}] ingest | Book
Forbidden: fanout, entity_create, touching NVDA.md/AMD.md Last session.
"""
    user = f"""Ingest the BOOK hub. Follow schema Book ingest rules.
This is compiled memory for the portfolio, not a holder letter and not a stock-pick list.
Watchlist tickers: {", ".join(tickers) or "(none)"}.
Share counts live in Postgres. If they look like seed placeholders, say so
in Last session; do not treat today's mix as a long-term target.
JSON `risk` and the source ## Risk section are the book-level metrics
(constant today's weights). Last session MUST mention them.
See also MUST include those ticker pages plus the Book and macro source pages
(code also appends them).

Existing Book.md:
---
{existing_entity or "(none yet)"}
---
{catalog}

Book source (already written; copy numbers, do not invent):
---
{_read(source_path)}
---
Macro source (already written):
---
{_read(macro_path)}
---
JSON snapshot:
{json.dumps(snapshot, indent=2)}

{contract}
"""
    payload = parse_json_object(complete(schema, user, max_tokens=4000))
    patch_notes = {"applied": [], "skipped": []}
    entity_path.parent.mkdir(parents=True, exist_ok=True)
    if first:
        created = payload.get("entity_create") or payload.get("entity_markdown")
        if not created:
            raise ValueError("first Book ingest did not return entity_create")
        text = tidy_see_also(
            append_see_also(str(created).rstrip() + "\n", required_links)
        )
        entity_path.write_text(text)
        patch_notes["applied"].append("entity_create")
    else:
        merged = dict(payload)
        merged["see_also_add"] = list(payload.get("see_also_add") or [])
        patched, patch_notes = _apply_entity_patches(
            existing_entity, merged, ticker="Book", as_of=as_of
        )
        patched = tidy_see_also(append_see_also(patched, required_links))
        entity_path.write_text(patched)

    index = existing_index or (
        "# Wiki index\n\nCatalog of LLM-maintained pages. Updated on ingest.\n\n"
        "## Entities\n\n## Sources\n\n## Concepts\n\n_(none yet)_\n"
    )
    entity_line = (payload.get("index_entity_line") or "").strip()
    source_line = (payload.get("index_source_line") or "").strip()
    macro_line = (payload.get("index_macro_line") or "").strip()
    if entity_line:
        index = upsert_index_line(index, "Entities", "Book", entity_line)
    if source_line:
        index = upsert_index_line(index, "Sources", f"Book-{as_of}", source_line)
    if macro_line:
        index = upsert_index_line(index, "Sources", f"macro-{as_of}", macro_line)
    else:
        index = upsert_index_line(
            index,
            "Sources",
            f"macro-{as_of}",
            f"macro-{as_of}: SPY tape and US-market headlines for {as_of}.",
        )
    INDEX_PATH.write_text(index)

    log_entry = (payload.get("log_entry") or "").rstrip()
    if log_entry.strip():
        existing_log = _read(LOG_PATH)
        block = log_entry.strip()
        if block not in existing_log:
            LOG_PATH.write_text(existing_log.rstrip() + "\n\n" + block + "\n")

    return {
        "ticker": "Book",
        "as_of": as_of,
        "raw_path": raw_path,
        "entity_path": str(entity_path),
        "source_path": str(source_path),
        "macro_path": str(macro_path),
        "skipped": False,
        "first_entity": first,
        "patches": patch_notes,
    }


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    force = "--force" in sys.argv
    if target.lower() == "book":
        result = ingest_book(overwrite_raw=force, force=force)
    else:
        result = ingest_ticker(target, overwrite_raw=force, force=force)
    print(json.dumps(result, indent=2))


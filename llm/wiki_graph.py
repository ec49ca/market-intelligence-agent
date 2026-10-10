"""Fan-out helpers: slugs, apply satellite pages, follow wiki links."""

from __future__ import annotations

import re
from pathlib import Path

from llm.paths import WIKI_DIR
from llm.wiki_edit import (
    append_see_also,
    apply_unique_replaces,
    insert_after_section,
    mutate_bullets,
    tidy_see_also,
    upsert_last_mention,
)

MAX_FANOUT = 6
ENTITY_SLUG = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")
CONCEPT_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
MD_HREF = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
TICKER_SLUG = re.compile(r"^[A-Z]{1,5}$")

JUNK_CONCEPT = re.compile(
    r"(etf|retirement|diversif|portfolio|tax-planning|headline|motley)"
)
PUBLISHER_SLUGS = {
    "yahoo",
    "yahoofinance",
    "motleyfool",
    "thestreet",
    "gurufocus",
    "cnbc",
    "reuters",
    "bloomberg",
    "techcrunch",
    "investopedia",
    "seekingalpha",
    "wikipedia",
    "investors",
    "investorsbusinessdaily",
    "247wallst",
    "marketwatch",
    "barrons",
    "wsj",
    "forbes",
    "businessinsider",
}


def is_ticker_slug(slug: str) -> bool:
    return bool(TICKER_SLUG.fullmatch(slug or ""))


def normalize_kind(kind: str) -> str | None:
    value = (kind or "").strip().lower()
    if value in {"entity", "entities"}:
        return "entity"
    if value in {"concept", "concepts"}:
        return "concept"
    return None


def sanitize_slug(kind: str, slug: str) -> str | None:
    """Return a safe filename stem, or None if the model should not mint this node."""
    kind = normalize_kind(kind) or ""
    raw = str(slug or "").strip().replace("\\", "/")
    if not raw or "/" in raw or ".." in raw:
        return None
    raw = Path(raw).name
    raw = raw.removesuffix(".md")
    if kind == "entity":
        if not ENTITY_SLUG.fullmatch(raw):
            return None
        compact = re.sub(r"[^a-z0-9]", "", raw.lower())
        if compact in PUBLISHER_SLUGS:
            return None
        return raw
    if kind == "concept":
        if not CONCEPT_SLUG.fullmatch(raw):
            return None
        if raw in PUBLISHER_SLUGS or JUNK_CONCEPT.search(raw):
            return None
        return raw
    return None


def page_path(kind: str, slug: str) -> Path:
    folder = "entities" if kind == "entity" else "concepts"
    return WIKI_DIR / folder / f"{slug}.md"


KNOWN_FANOUT = (
    ("coreweave", "entity", "CoreWeave"),
    ("microsoft", "entity", "Microsoft"),
    ("firmus", "entity", "Firmus"),
    ("openai", "entity", "OpenAI"),
    ("anthropic", "entity", "Anthropic"),
    ("meta", "entity", "Meta"),
    ("useful yield", "concept", "useful-yield"),
    ("useful-yield", "concept", "useful-yield"),
    ("tape vs news", "concept", "tape-vs-news"),
    ("tape-vs-news", "concept", "tape-vs-news"),
    ("rack-scale", "concept", "rack-scale-ai"),
)


def hint_fanout_targets(text: str, ticker: str) -> list[tuple[str, str]]:
    """Durable names already in the thesis or dump — must become wiki nodes."""
    cut = re.search(r"^##[ \t]+See also\b", text or "", re.M)
    blob = ((text or "")[: cut.start()] if cut else (text or "")).lower()
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for needle, kind, slug in KNOWN_FANOUT:
        if needle == "meta":
            if not re.search(r"\bmeta\b", blob):
                continue
        elif needle not in blob:
            continue
        if slug.upper() == ticker.upper():
            continue
        key = f"{kind}:{slug.lower()}"
        if key in seen:
            continue
        seen.add(key)
        found.append((kind, slug))
    # Other watchlist tickers named in the text.
    for path in sorted((WIKI_DIR / "entities").glob("*.md")):
        other = path.stem
        if not is_ticker_slug(other) or other == ticker:
            continue
        if other.lower() in blob and f"entity:{other.lower()}" not in seen:
            seen.add(f"entity:{other.lower()}")
            found.append(("entity", other))
    return found[:MAX_FANOUT]


def sentence_about(text: str, needle: str) -> str:
    """One short line mentioning needle. Skip heading soup and giant first-page dumps."""
    needle_l = (needle or "").lower()
    if not needle_l:
        return ""
    for line in (text or "").splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if not stripped or stripped.startswith("#"):
            continue
        if needle_l not in stripped.lower():
            continue
        compact = re.sub(r"\s+", " ", stripped)
        if 24 <= len(compact) <= 280:
            return compact
    for part in re.split(r"(?<=[.!?])\s+", text or ""):
        compact = re.sub(r"\s+", " ", part).strip()
        if needle_l in compact.lower() and 24 <= len(compact) <= 280:
            return compact
    return ""


def catalog_wiki() -> str:
    """Short inventory so ingest can link existing slugs instead of duplicating."""
    lines = ["Existing wiki pages (patch these slugs; do not mint near-duplicates):"]
    for folder, label in (("entities", "entity"), ("concepts", "concept")):
        paths = sorted((WIKI_DIR / folder).glob("*.md"))
        if not paths:
            lines.append(f"- {label}: (none)")
            continue
        for path in paths:
            lines.append(f"- {label} {path.stem}: {path.relative_to(WIKI_DIR)}")
    return "\n".join(lines)


def neighbor_page_bodies(*, skip_ticker: str, max_pages: int = 12, max_chars: int = 3500) -> str:
    """Bodies of other entity/concept pages, truncated, for surgical fan-out edits."""
    skip = skip_ticker.strip().upper()
    chunks: list[str] = []
    paths = sorted((WIKI_DIR / "entities").glob("*.md")) + sorted(
        (WIKI_DIR / "concepts").glob("*.md")
    )
    for path in paths:
        if path.parent.name == "entities" and path.stem.upper() == skip:
            continue
        if len(chunks) >= max_pages:
            break
        text = path.read_text()
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "\n…(truncated)\n"
        rel = path.relative_to(WIKI_DIR)
        chunks.append(f"### {rel}\n{text}")
    if not chunks:
        return "(no other entity or concept pages yet)"
    return "\n\n".join(chunks)


def _see_also_for(kind: str, *, ticker: str, as_of: str) -> list[str]:
    if kind == "entity":
        ticker_link = f"[{ticker}]({ticker}.md)"
        source_link = f"[{ticker} {as_of}](../sources/{ticker}-{as_of}.md)"
    else:
        ticker_link = f"[{ticker}](../entities/{ticker}.md)"
        source_link = f"[{ticker} {as_of}](../sources/{ticker}-{as_of}.md)"
    return [ticker_link, source_link]


def stub_page(kind: str, slug: str, *, ticker: str, as_of: str, item: dict) -> str:
    """Minimal satellite page when the model named a node but omitted create."""
    title = slug if kind == "entity" else slug.replace("-", " ")
    blurb = (item.get("index_line") or "").split(":", 1)[-1].strip()
    if not blurb:
        blurb = f"Named in {ticker} coverage as of {as_of}."
    mention = (item.get("last_mention") or "").strip()
    if mention and not mention.lstrip().startswith("##"):
        mention = f"## Last mention ({as_of})\n\n{mention}"
    if not mention:
        mention = f"## Last mention ({as_of})\n\n- Cited from {ticker} {as_of}."
    return (
        f"# {title}\n\n## Thesis\n\n{blurb}\n\n{mention.rstrip()}\n\n## See also\n"
    )


def ticker_links_to_fanout(items: list[dict]) -> list[str]:
    links = []
    for item in items:
        kind = item.get("kind")
        slug = item.get("slug")
        if kind == "entity":
            links.append(f"[{slug}]({slug}.md)")
        elif kind == "concept":
            label = str(slug).replace("-", " ")
            links.append(f"[{label}](../concepts/{slug}.md)")
    return links


def apply_fanout_item(
    existing: str,
    item: dict,
    *,
    kind: str,
    slug: str,
    ticker: str,
    as_of: str,
) -> tuple[str, dict]:
    """Create or patch one satellite page. Never overwrites another ticker's Last session."""
    notes = {"applied": [], "skipped": []}
    other_ticker = kind == "entity" and is_ticker_slug(slug) and slug != ticker
    text = existing
    created = not bool(existing.strip())
    if created:
        created_md = (item.get("create") or item.get("markdown") or "").strip()
        if not created_md:
            created_md = stub_page(kind, slug, ticker=ticker, as_of=as_of, item=item)
            notes["applied"].append("stub_create")
        else:
            notes["applied"].append("create")
        if not created_md:
            notes["skipped"].append("missing_create")
            return "", notes
        text = created_md.rstrip() + "\n"
        text = upsert_last_mention(
            text,
            ticker=ticker,
            as_of=as_of,
            blurb=(item.get("last_mention") or "").strip(),
        )
    else:
        if not other_ticker:
            last_mention = (item.get("last_mention") or "").strip()
            text = upsert_last_mention(
                text, ticker=ticker, as_of=as_of, blurb=last_mention
            )
            notes["applied"].append("last_mention")
        elif item.get("last_mention") or item.get("last_session"):
            notes["skipped"].append("last_session_other_ticker")
        text, applied, skipped = apply_unique_replaces(text, item.get("thesis_edits") or [])
        notes["applied"].extend(f"thesis:{part}" for part in applied)
        notes["skipped"].extend(f"thesis:{part}" for part in skipped)
        contradiction = (item.get("contradiction") or "").strip()
        if contradiction:
            if not contradiction.startswith(">"):
                contradiction = f"> {as_of}: {contradiction}"
            text = insert_after_section(text, "Thesis", contradiction)
            notes["applied"].append("contradiction")
        before = text
        text = mutate_bullets(
            text,
            "Open questions",
            add=item.get("open_questions_add") or [],
            remove=item.get("open_questions_remove") or [],
        )
        if text != before:
            notes["applied"].append("open_questions")
    before = text
    extras = list(item.get("see_also_add") or []) + _see_also_for(
        kind, ticker=ticker, as_of=as_of
    )
    text = append_see_also(text, extras)
    if text != before:
        notes["applied"].append("see_also")
    text = tidy_see_also(text)
    return text, notes


def parse_fanout_items(payload: dict, *, ticker: str) -> list[dict]:
    raw = payload.get("fanout") or payload.get("new_files") or []
    if not isinstance(raw, list):
        return []
    seen: set[tuple[str, str]] = set()
    items: list[dict] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        kind = normalize_kind(str(row.get("kind") or row.get("type") or ""))
        if not kind:
            filename = str(row.get("filename") or row.get("path") or "")
            if "concept" in filename.replace("\\", "/"):
                kind = "concept"
            elif row.get("markdown") and filename.endswith(".md"):
                kind = "concept"
            else:
                continue
        slug_raw = row.get("slug") or row.get("filename") or row.get("path") or ""
        slug = sanitize_slug(kind, str(slug_raw))
        if not slug or slug.upper() == ticker.upper():
            continue
        key = (kind, slug.lower())
        if key in seen:
            continue
        seen.add(key)
        items.append({**row, "kind": kind, "slug": slug})
        if len(items) >= MAX_FANOUT:
            break
    return items


def resolve_wiki_href(href: str, from_file: Path) -> Path | None:
    target_href = (href or "").strip().split()[0].split("#")[0].split("?")[0]
    if not target_href or target_href.startswith(("http://", "https://", "mailto:")):
        return None
    if not target_href.endswith(".md"):
        return None
    try:
        resolved = (from_file.parent / target_href).resolve()
        resolved.relative_to(WIKI_DIR.resolve())
    except (ValueError, OSError):
        return None
    try:
        rel = resolved.relative_to(WIKI_DIR.resolve())
    except ValueError:
        return None
    if rel.parts[0] not in {"entities", "concepts"}:
        return None
    if resolved.exists() and resolved.suffix == ".md":
        return resolved
    return None


def linked_wiki_pages(seed_paths: list[Path], *, limit: int = 8) -> list[Path]:
    """Depth-1 links from seed pages into entities/ and concepts/."""
    found: list[Path] = []
    seen: set[Path] = set()
    seeds = [path.resolve() for path in seed_paths if path.exists()]
    seed_set = set(seeds)
    for seed in seeds:
        text = seed.read_text()
        for match in MD_HREF.finditer(text):
            target = resolve_wiki_href(match.group(1), seed)
            if target is None or target in seen or target in seed_set:
                continue
            seen.add(target)
            found.append(target)
            if len(found) >= limit:
                return found
    return found


def wiki_page_id(path: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(WIKI_DIR.resolve())
    except ValueError:
        return None
    if rel.parts[0] not in {"entities", "concepts"}:
        return None
    return f"{rel.parts[0]}/{path.stem}"


def wiki_node_role(path: Path) -> str:
    folder = path.parent.name
    slug = path.stem
    if folder == "concepts":
        return "concept"
    if slug.lower() == "book":
        return "book"
    if is_ticker_slug(slug):
        return "ticker"
    return "entity"


def wiki_link_graph() -> dict:
    """Entities + concepts as nodes; markdown links as undirected edges. No sources."""
    pages = sorted((WIKI_DIR / "entities").glob("*.md")) + sorted(
        (WIKI_DIR / "concepts").glob("*.md")
    )
    nodes = []
    id_of: dict[Path, str] = {}
    for path in pages:
        nid = wiki_page_id(path)
        if not nid:
            continue
        role = wiki_node_role(path)
        slug = path.stem
        label = slug.replace("-", " ") if role == "concept" else slug
        nodes.append(
            {
                "id": nid,
                "slug": slug,
                "label": label,
                "role": role,
                "path": str(path.relative_to(WIKI_DIR)),
            }
        )
        id_of[path.resolve()] = nid
    edges = []
    seen: set[tuple[str, str]] = set()
    for path in pages:
        src = id_of.get(path.resolve())
        if not src:
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        for match in MD_HREF.finditer(text):
            target = resolve_wiki_href(match.group(1), path)
            if target is None:
                continue
            dst = id_of.get(target.resolve())
            if not dst or dst == src:
                continue
            key = tuple(sorted((src, dst)))
            if key in seen:
                continue
            seen.add(key)
            edges.append({"source": src, "target": dst})
    return {"nodes": nodes, "edges": edges}


def format_linked_pages(paths: list[Path], *, max_chars: int = 2500) -> str:
    if not paths:
        return "(no linked entity/concept pages)"
    chunks = []
    for path in paths:
        text = path.read_text()
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "\n…(truncated)\n"
        chunks.append(f"### {path.relative_to(WIKI_DIR)}\n{text}")
    return "\n\n".join(chunks)

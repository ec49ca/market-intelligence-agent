"""Surgical wiki edits. Never replace a living page from a full model dump."""

from __future__ import annotations

import re
from pathlib import Path

MAX_OPEN_QUESTIONS = 8
MD_HREF = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SOURCE_HREF = re.compile(
    r"\((?:\.\./)?sources/([A-Za-z][A-Za-z0-9]*)-(\d{4}-\d{2}-\d{2})\.md\)"
)
TICKER_PREFIX = re.compile(r"^[A-Z]{1,5}:")


def _normalize_nl(text: str) -> str:
    return text.replace("\r\n", "\n")


def _section_pattern(heading: str) -> re.Pattern[str]:
    return re.compile(
        rf"(^##[ \t]+{re.escape(heading)}\b[^\n]*\n)(.*?)(?=^##[ \t]+|\Z)",
        re.M | re.S,
    )


def replace_section(text: str, heading: str, new_section: str) -> str:
    """Replace the ## heading block. Matches 'Last session' and 'Last session (date)'."""
    text = _normalize_nl(text)
    new_section = new_section.strip()
    if not new_section.startswith("##"):
        new_section = f"## {heading}\n\n{new_section}"
    new_section = new_section.rstrip() + "\n"
    pattern = _section_pattern(heading)
    if pattern.search(text):
        updated = pattern.sub(new_section + "\n", text, count=1)
        return re.sub(r"\n{3,}", "\n\n", updated).rstrip() + "\n"
    return text.rstrip() + "\n\n" + new_section + "\n"


def apply_unique_replaces(text: str, edits: list) -> tuple[str, list[str], list[str]]:
    """Replace exact substrings. Skip if missing or not unique — never guess."""
    applied: list[str] = []
    skipped: list[str] = []
    for edit in edits or []:
        if not isinstance(edit, dict):
            continue
        old = str(edit.get("old") or "")
        new = edit.get("new")
        if new is None:
            new = ""
        else:
            new = str(new)
        if not old.strip():
            continue
        count = text.count(old)
        if count != 1:
            skipped.append(old[:120])
            continue
        text = text.replace(old, new, 1)
        applied.append(old[:120])
    return text, applied, skipped


def _bullets_in(body: str) -> list[str]:
    items = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def mutate_bullets(
    text: str, heading: str, *, add: list | None = None, remove: list | None = None
) -> str:
    text = _normalize_nl(text)
    pattern = _section_pattern(heading)
    match = pattern.search(text)
    add = [str(item).strip().lstrip("- ").strip() for item in (add or []) if str(item).strip()]
    remove = [str(item).strip().lstrip("- ").strip() for item in (remove or []) if str(item).strip()]
    if not match:
        if not add:
            return text
        block = f"## {heading}\n\n" + "\n".join(f"- {item}" for item in add) + "\n"
        return text.rstrip() + "\n\n" + block + "\n"
    heading_line, body = match.group(1), match.group(2)
    bullets = _bullets_in(body)
    kept = []
    for bullet in bullets:
        drop = any(
            needle.lower() in bullet.lower() or bullet.lower() in needle.lower()
            for needle in remove
        )
        if not drop:
            kept.append(bullet)
    for item in add:
        if not any(item.lower() in existing.lower() or existing.lower() in item.lower() for existing in kept):
            kept.append(item)
    rest = "\n".join(line for line in body.splitlines() if not line.strip().startswith("- ")).strip()
    new_body = "\n".join(f"- {item}" for item in kept)
    if rest:
        new_body = new_body + "\n\n" + rest
    replacement = heading_line + new_body.rstrip() + "\n"
    updated = text[: match.start()] + replacement + text[match.end() :]
    return re.sub(r"\n{3,}", "\n\n", updated).rstrip() + "\n"


def insert_after_section(text: str, heading: str, block: str) -> str:
    block = (block or "").strip()
    if not block:
        return text
    text = _normalize_nl(text)
    if block in text:
        return text
    pattern = _section_pattern(heading)
    match = pattern.search(text)
    snippet = block.rstrip() + "\n\n"
    if not match:
        return text.rstrip() + "\n\n" + snippet
    at = match.end()
    return (text[:at].rstrip() + "\n\n" + snippet + text[at:].lstrip()).rstrip() + "\n"


def _bullet_key(stripped: str) -> str:
    if not stripped.startswith("- "):
        return ""
    return stripped[2:].split(":", 1)[0].strip()


def upsert_index_line(index: str, section: str, needle: str, line: str) -> str:
    """Replace or insert one bullet under ## section. Other bullets stay."""
    index = _normalize_nl(index)
    line = line.strip()
    if not line.startswith("- "):
        line = "- " + line
    pattern = _section_pattern(section)
    match = pattern.search(index)
    if not match:
        block = f"## {section}\n\n{line}\n"
        return index.rstrip() + "\n\n" + block + "\n"
    heading_line, body = match.group(1), match.group(2)
    lines = body.splitlines()
    found = False
    new_lines = []
    for raw in lines:
        stripped = raw.strip()
        if _bullet_key(stripped) == needle:
            new_lines.append(line)
            found = True
        else:
            new_lines.append(raw)
    if not found:
        for i, raw in enumerate(new_lines):
            if raw.strip() == "_(none yet)_":
                new_lines[i] = line
                found = True
                break
        if not found:
            insert_at = len(new_lines)
            while insert_at > 0 and not new_lines[insert_at - 1].strip():
                insert_at -= 1
            new_lines.insert(insert_at, line)
    new_body = "\n".join(new_lines).rstrip() + "\n"
    updated = index[: match.start()] + heading_line + new_body + index[match.end() :]
    return re.sub(r"\n{3,}", "\n\n", updated).rstrip() + "\n"


def append_see_also(text: str, links: list) -> str:
    text = _normalize_nl(text)
    match = _section_pattern("See also").search(text)
    existing_body = match.group(2) if match else ""
    additions = []
    for item in links or []:
        line = str(item).strip()
        if not line:
            continue
        if not line.startswith("- "):
            line = "- " + line
        target = line[2:].strip()
        if target in existing_body or target in additions:
            continue
        additions.append(target)
    return mutate_bullets(text, "See also", add=additions)


def _href_key(bullet: str) -> str:
    hrefs = MD_HREF.findall(bullet)
    if hrefs:
        return hrefs[0].strip().split()[0].split("#")[0].lower()
    return bullet.strip().lower()


def tidy_see_also(text: str) -> str:
    """Drop Yahoo URLs, duplicate targets, and old source receipts (keep latest per ticker)."""
    text = _normalize_nl(text)
    pattern = _section_pattern("See also")
    match = pattern.search(text)
    if not match:
        return text
    heading_line, body = match.group(1), match.group(2)
    latest_source: dict[str, tuple[str, str]] = {}
    others: list[str] = []
    seen: set[str] = set()
    for bullet in _bullets_in(body):
        if re.search(r"https?://", bullet):
            continue
        source = SOURCE_HREF.search(bullet)
        if source:
            prefix, date = source.group(1).lower(), source.group(2)
            prev = latest_source.get(prefix)
            if prev is None or date > prev[0]:
                latest_source[prefix] = (date, bullet)
            continue
        key = _href_key(bullet)
        if not key or key in seen:
            continue
        seen.add(key)
        others.append(bullet)
    source_bullets = [pair[1] for _, pair in sorted(latest_source.items())]
    kept = others + source_bullets
    new_body = "\n".join(f"- {item}" for item in kept)
    replacement = heading_line + (new_body + "\n" if new_body else "\n")
    updated = text[: match.start()] + replacement + text[match.end() :]
    return re.sub(r"\n{3,}", "\n\n", updated).rstrip() + "\n"


def cap_section_bullets(text: str, heading: str, max_n: int) -> str:
    text = _normalize_nl(text)
    pattern = _section_pattern(heading)
    match = pattern.search(text)
    if not match or max_n < 1:
        return text
    heading_line, body = match.group(1), match.group(2)
    bullets = _bullets_in(body)
    if len(bullets) <= max_n:
        return text
    rest = "\n".join(
        line for line in body.splitlines() if not line.strip().startswith("- ")
    ).strip()
    new_body = "\n".join(f"- {item}" for item in bullets[:max_n])
    if rest:
        new_body = new_body + "\n\n" + rest
    replacement = heading_line + new_body.rstrip() + "\n"
    updated = text[: match.start()] + replacement + text[match.end() :]
    return re.sub(r"\n{3,}", "\n\n", updated).rstrip() + "\n"


def upsert_last_mention(
    text: str, *, ticker: str, as_of: str, blurb: str
) -> str:
    """One Last mention bullet per watchlist ticker; bump the heading date."""
    text = _normalize_nl(text)
    blurb = re.sub(r"\s+", " ", (blurb or "").strip())
    if blurb.lstrip().startswith("##"):
        blurb = " ".join(
            line.lstrip("- ").strip()
            for line in blurb.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    if blurb.lower().startswith(ticker.lower() + ":"):
        blurb = blurb.split(":", 1)[1].strip()
    blurb = blurb.lstrip("- ").strip()
    if not blurb:
        blurb = f"Named in {ticker} {as_of} coverage."
    bullet = f"{ticker}: {blurb}"
    pattern = _section_pattern("Last mention")
    match = pattern.search(text)
    heading = f"## Last mention ({as_of})\n"
    kept: list[str] = []
    if match:
        for item in _bullets_in(match.group(2)):
            if item.lower().startswith(ticker.lower() + ":"):
                continue
            if TICKER_PREFIX.match(item):
                kept.append(item)
    kept.insert(0, bullet)
    kept = kept[:6]
    replacement = heading + "\n" + "\n".join(f"- {item}" for item in kept) + "\n"
    if not match:
        return text.rstrip() + "\n\n" + replacement + "\n"
    updated = text[: match.start()] + replacement + text[match.end() :]
    return re.sub(r"\n{3,}", "\n\n", updated).rstrip() + "\n"


def has_thesis_heading(text: str) -> bool:
    return bool(re.search(r"^##[ \t]+Thesis\b", text or "", re.M))


def index_has_needle(index: str, section: str, needle: str) -> bool:
    match = _section_pattern(section).search(_normalize_nl(index or ""))
    if not match:
        return False
    return any(_bullet_key(raw.strip()) == needle for raw in match.group(2).splitlines())


def write_if_missing(path: Path, markdown: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown.rstrip() + "\n")
    return True

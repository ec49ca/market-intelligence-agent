"""Fan-out must mint shared nodes without wiping another ticker's tape."""

from llm.paths import WIKI_DIR
from llm.wiki_graph import (
    apply_fanout_item,
    is_ticker_slug,
    parse_fanout_items,
    resolve_wiki_href,
    sanitize_slug,
    ticker_links_to_fanout,
    wiki_link_graph,
)

AMD = """# AMD

## Thesis

AMD competes in AI GPUs.

## Last session (2026-09-11)

- Closed at $516.13.

## See also

- [2026-09-11](../sources/AMD-2026-09-11.md)
"""


def test_sanitize_rejects_publishers_and_paths():
    assert sanitize_slug("entity", "CoreWeave") == "CoreWeave"
    assert sanitize_slug("concept", "useful-yield") == "useful-yield"
    assert sanitize_slug("entity", "Yahoo") is None
    assert sanitize_slug("concept", "etf-diversification-strategy") is None
    assert sanitize_slug("entity", "../etc") is None
    assert sanitize_slug("concept", "UsefulYield") is None
    assert is_ticker_slug("AMD")
    assert not is_ticker_slug("CoreWeave")


def test_parse_fanout_skips_self_and_caps():
    payload = {
        "fanout": [
            {"kind": "entity", "slug": "NVDA", "create": "# no"},
            {"kind": "entity", "slug": "CoreWeave", "create": "# cw"},
            {"kind": "entity", "slug": "Yahoo", "create": "# no"},
            {"kind": "concept", "slug": "useful-yield", "create": "# y"},
        ]
    }
    items = parse_fanout_items(payload, ticker="NVDA")
    assert [item["slug"] for item in items] == ["CoreWeave", "useful-yield"]


def test_omitted_last_mention_still_updates_satellite():
    existing = """# OpenAI

## Thesis

AI lab.

## Last mention (2026-09-11)

- Nvidia CEO highlighted OpenAI as a partner.

## See also

- [NVDA](NVDA.md)
- [2026-09-11](../sources/NVDA-2026-09-11.md)
"""
    text, notes = apply_fanout_item(
        existing,
        {},
        kind="entity",
        slug="OpenAI",
        ticker="NVDA",
        as_of="2026-10-08",
    )
    assert "Last mention (2026-10-08)" in text
    assert "NVDA:" in text
    assert "last_mention" in notes["applied"]
    assert "NVDA-2026-10-08.md" in text
    assert "NVDA-2026-09-11.md" not in text


def test_last_mention_keeps_other_ticker_bullet():
    existing = """# Anthropic

## Thesis

AI lab.

## Last mention (2026-10-08)

- NVDA: $10B IPO talks.

## See also

- [NVDA](NVDA.md)
"""
    text, _notes = apply_fanout_item(
        existing,
        {"last_mention": "Still named as an AMD data-center customer."},
        kind="entity",
        slug="Anthropic",
        ticker="AMD",
        as_of="2026-10-08",
    )
    assert "NVDA: $10B IPO talks." in text
    assert "AMD: Still named as an AMD data-center customer." in text


def test_other_ticker_keeps_last_session():
    text, notes = apply_fanout_item(
        AMD,
        {
            "last_mention": "## Last mention (2026-09-11)\n\n- NVDA dump cited AMD as demand proof.\n",
            "last_session": "## Last session (1999-01-01)\n\n- HACKED\n",
            "see_also_add": ["[NVDA](NVDA.md)"],
        },
        kind="entity",
        slug="AMD",
        ticker="NVDA",
        as_of="2026-09-11",
    )
    assert "Closed at $516.13." in text
    assert "HACKED" not in text
    assert "[NVDA](NVDA.md)" in text
    assert "[NVDA 2026-09-11](../sources/NVDA-2026-09-11.md)" in text
    assert "last_session_other_ticker" in notes["skipped"]


def test_stub_create_when_markdown_missing():
    text, notes = apply_fanout_item(
        "",
        {"index_line": "Microsoft: NVDA customer asking about useful yield."},
        kind="entity",
        slug="Microsoft",
        ticker="NVDA",
        as_of="2026-09-11",
    )
    assert "# Microsoft" in text
    assert "useful yield" in text
    assert "stub_create" in notes["applied"]
    assert "[NVDA](NVDA.md)" in text


def test_creates_satellite_with_backlinks():
    text, notes = apply_fanout_item(
        "",
        {
            "create": (
                "# CoreWeave\n\n## Thesis\n\nGPU cloud; NVDA owns 11.5%.\n\n"
                "## Last mention (2026-09-04)\n\n- Raised 2026 guide.\n\n## See also\n"
            )
        },
        kind="entity",
        slug="CoreWeave",
        ticker="NVDA",
        as_of="2026-09-04",
    )
    assert "GPU cloud" in text
    assert "[NVDA](NVDA.md)" in text
    assert "NVDA-2026-09-04.md" in text
    assert "create" in notes["applied"]


def test_hint_targets_from_nvda_thesis():
    from llm.wiki_graph import hint_fanout_targets

    thesis = (
        "Nvidia stake in CoreWeave (11.5%). Microsoft useful yield. "
        "Firmus OpenAI deal. AMD competes."
    )
    found = hint_fanout_targets(thesis, "NVDA")
    slugs = {slug for _kind, slug in found}
    assert "CoreWeave" in slugs
    assert "Microsoft" in slugs
    assert "useful-yield" in slugs
    assert "AMD" in slugs


def test_sentence_about_skips_heading_soup():
    from llm.wiki_graph import sentence_about

    blob = (
        "## Snapshot as of 2026-09-04 - Close Price: $477.57 "
        "Tape vs News: Classified as noise on a giant line that goes on "
        + ("x" * 500)
    )
    assert sentence_about(blob, "tape vs news") == ""
    assert (
        sentence_about(
            "- Tape vs News: Classified as noise indicating price moves are not news-driven.\n",
            "tape vs news",
        )
        == "Tape vs News: Classified as noise indicating price moves are not news-driven."
    )


def test_ticker_auto_links():
    links = ticker_links_to_fanout(
        [
            {"kind": "entity", "slug": "CoreWeave"},
            {"kind": "concept", "slug": "useful-yield"},
        ]
    )
    assert "[CoreWeave](CoreWeave.md)" in links
    assert "[useful yield](../concepts/useful-yield.md)" in links


def test_wiki_link_graph_skips_sources_and_joins_openai():
    graph = wiki_link_graph()
    ids = {node["id"] for node in graph["nodes"]}
    assert "entities/NVDA" in ids
    assert "entities/AMD" in ids
    assert "entities/Book" in ids
    assert "entities/OpenAI" in ids
    assert "concepts/useful-yield" in ids
    assert not any("sources/" in node["id"] for node in graph["nodes"])
    pairs = {tuple(sorted((edge["source"], edge["target"]))) for edge in graph["edges"]}
    assert ("entities/AMD", "entities/OpenAI") in pairs
    assert ("entities/NVDA", "entities/OpenAI") in pairs
    book = next(node for node in graph["nodes"] if node["role"] == "book")
    assert book["slug"] == "Book"


def test_resolve_hrefs_stay_in_wiki():
    nvda = WIKI_DIR / "entities" / "NVDA.md"
    amd = resolve_wiki_href("AMD.md", nvda)
    assert amd == (WIKI_DIR / "entities" / "AMD.md").resolve()
    assert resolve_wiki_href("https://finance.yahoo.com/x", nvda) is None
    assert resolve_wiki_href("../sources/NVDA-2026-09-04.md", nvda) is None
    assert resolve_wiki_href("../../.env", nvda) is None


if __name__ == "__main__":
    for test in [
        test_sanitize_rejects_publishers_and_paths,
        test_parse_fanout_skips_self_and_caps,
        test_omitted_last_mention_still_updates_satellite,
        test_last_mention_keeps_other_ticker_bullet,
        test_other_ticker_keeps_last_session,
        test_creates_satellite_with_backlinks,
        test_stub_create_when_markdown_missing,
        test_hint_targets_from_nvda_thesis,
        test_sentence_about_skips_heading_soup,
        test_ticker_auto_links,
        test_wiki_link_graph_skips_sources_and_joins_openai,
        test_resolve_hrefs_stay_in_wiki,
    ]:
        test()
        print("ok", test.__name__)
    print("all passed")

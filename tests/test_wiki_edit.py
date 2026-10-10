"""Surgical wiki edits must not wipe sibling sections or other tickers."""

from llm.wiki_edit import (
    apply_unique_replaces,
    cap_section_bullets,
    insert_after_section,
    mutate_bullets,
    replace_section,
    tidy_see_also,
    upsert_index_line,
    upsert_last_mention,
)

ENTITY = """# NVIDIA Corporation (NVDA)

## Thesis

NVIDIA is the premier AI GPU vendor. Microsoft useful yield is an open issue.

## Last session (2026-09-04)

- Closed at $230.36.
- Tape was noise.

For details see [2026-09-04](../sources/NVDA-2026-09-04.md).

## Open questions

- What is the realized useful yield?
- How will AMD compete?

## See also

- [AMD](AMD.md)
"""

INDEX = """# Wiki index

## Entities

- NVDA: old NVDA line
- AMD: old AMD line

## Sources

- NVDA-2026-09-04: old nvda source
- AMD-2026-09-04: old amd source

## Concepts

_(none yet)_
"""


def test_replace_last_session_keeps_thesis_and_questions():
    updated = replace_section(
        ENTITY,
        "Last session",
        "## Last session (2026-09-11)\n\n- Closed at $240.\n",
    )
    assert "premier AI GPU vendor" in updated
    assert "What is the realized useful yield?" in updated
    assert "Closed at $230.36" not in updated
    assert "Closed at $240." in updated
    assert "[AMD](AMD.md)" in updated


def test_thesis_edit_skips_if_not_exact():
    text, applied, skipped = apply_unique_replaces(
        ENTITY,
        [{"old": "this string is not on the page", "new": "nope"}],
    )
    assert text == ENTITY
    assert applied == []
    assert skipped


def test_thesis_edit_unique_replace():
    text, applied, skipped = apply_unique_replaces(
        ENTITY,
        [{"old": "Microsoft useful yield is an open issue.", "new": "Microsoft yield is still unanswered as of 2026-09-11."}],
    )
    assert "still unanswered" in text
    assert "Open questions" in text
    assert applied and not skipped


def test_open_questions_add_without_dropping():
    updated = mutate_bullets(
        ENTITY,
        "Open questions",
        add=["Did tape confirm on 2026-09-11?"],
        remove=[],
    )
    assert "useful yield" in updated
    assert "Did tape confirm on 2026-09-11?" in updated
    assert "How will AMD compete?" in updated


def test_index_upsert_does_not_drop_amd():
    updated = upsert_index_line(
        INDEX, "Entities", "NVDA", "NVDA: new NVDA line"
    )
    updated = upsert_index_line(
        updated, "Sources", "NVDA-2026-09-11", "NVDA-2026-09-11: thursday receipt"
    )
    assert "AMD: old AMD line" in updated
    assert "AMD-2026-09-04: old amd source" in updated
    assert "NVDA: new NVDA line" in updated
    assert "NVDA-2026-09-04: old nvda source" in updated
    assert "NVDA-2026-09-11: thursday receipt" in updated


def test_tidy_see_also_drops_urls_and_old_sources():
    messy = """# X

## See also

- [OpenAI](OpenAI.md)
- [OpenAI again](OpenAI.md)
- [story](https://finance.yahoo.com/x)
- [2026-09-11](../sources/NVDA-2026-09-11.md)
- [2026-10-08](../sources/NVDA-2026-10-08.md)
- [2026-10-07](../sources/AMD-2026-10-07.md)
"""
    cleaned = tidy_see_also(messy)
    assert "yahoo" not in cleaned
    assert "NVDA-2026-09-11" not in cleaned
    assert "NVDA-2026-10-08.md" in cleaned
    assert "AMD-2026-10-07.md" in cleaned
    assert cleaned.count("OpenAI.md") == 1


def test_upsert_last_mention_per_ticker():
    page = """# OpenAI

## Last mention (2026-09-11)

- Nvidia CEO highlighted OpenAI.
"""
    updated = upsert_last_mention(
        page, ticker="NVDA", as_of="2026-10-08", blurb="Still in the thesis via Firmus."
    )
    updated = upsert_last_mention(
        updated, ticker="AMD", as_of="2026-10-08", blurb="Named as an AMD customer."
    )
    assert "Last mention (2026-10-08)" in updated
    assert "NVDA: Still in the thesis via Firmus." in updated
    assert "AMD: Named as an AMD customer." in updated
    assert "Nvidia CEO highlighted" not in updated


def test_append_see_also_if_source_already_in_last_session():
    from llm.wiki_edit import append_see_also

    page = """# AMD

## Last session (2026-10-09)

See [2026-10-09](../sources/AMD-2026-10-09.md).

## See also

- [NVDA](NVDA.md)
- [2026-10-08](../sources/AMD-2026-10-08.md)
"""
    updated = tidy_see_also(
        append_see_also(page, ["[2026-10-09](../sources/AMD-2026-10-09.md)"])
    )
    assert "AMD-2026-10-09.md" in updated.split("## See also")[1]
    assert "AMD-2026-10-08.md" not in updated.split("## See also")[1]


def test_cap_open_questions():
    page = ENTITY
    for i in range(12):
        page = mutate_bullets(page, "Open questions", add=[f"Question {i} unique enough?"])
    capped = cap_section_bullets(page, "Open questions", 8)
    questions = capped.split("## Open questions")[1].split("## See also")[0]
    assert questions.count("\n- ") == 8


def test_contradiction_lands_after_thesis():
    updated = insert_after_section(
        ENTITY, "Thesis", "> 2026-09-11: tape confirmed; wiki had said noise-only."
    )
    thesis_at = updated.index("## Thesis")
    flag_at = updated.index("tape confirmed")
    last_at = updated.index("## Last session")
    assert thesis_at < flag_at < last_at


if __name__ == "__main__":
    tests = [
        test_replace_last_session_keeps_thesis_and_questions,
        test_thesis_edit_skips_if_not_exact,
        test_thesis_edit_unique_replace,
        test_open_questions_add_without_dropping,
        test_index_upsert_does_not_drop_amd,
        test_tidy_see_also_drops_urls_and_old_sources,
        test_append_see_also_if_source_already_in_last_session,
        test_upsert_last_mention_per_ticker,
        test_cap_open_questions,
        test_contradiction_lands_after_thesis,
    ]
    for test in tests:
        test()
        print("ok", test.__name__)
    print("all passed")

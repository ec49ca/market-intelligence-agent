"""Book mix rollup and report filename filter."""

from data.holdings import attach_weights
from llm.book import day_dollar, render_book_source, summarize_book
from llm.query import report_filename_needle


def test_summarize_book_weights_and_day():
    rows = attach_weights(
        [
            {
                "ticker": "NVDA",
                "company_name": "NVIDIA",
                "shares": 10,
                "close": 200,
                "daily_return": 0.0,
                "return_30d": -0.02,
                "as_of": "2026-09-11",
                "cost_per_share": 100,
            },
            {
                "ticker": "AMD",
                "company_name": "AMD",
                "shares": 20,
                "close": 50,
                "daily_return": 0.25,
                "return_30d": 0.10,
                "as_of": "2026-09-11",
                "cost_per_share": 40,
            },
        ]
    )
    book = summarize_book(rows)
    assert book["book_value"] == 3000
    assert book["top_ticker"] == "NVDA"
    assert abs(book["top_weight"] - 2000 / 3000) < 1e-9
    amd = next(row for row in book["names"] if row["ticker"] == "AMD")
    assert abs(amd["day_dollar"] - 200) < 1e-9
    assert abs(book["day_dollar"] - 200) < 1e-9
    assert "AI-infrastructure" in " ".join(book["caveats"])


def test_day_dollar_from_return():
    assert abs(day_dollar(103, 0.03) - 3) < 1e-9
    assert day_dollar(100, None) is None


def test_render_book_source_copies_tickers():
    snapshot = {
        "as_of": "2026-09-11",
        "book": summarize_book(
            attach_weights(
                [
                    {
                        "ticker": "NVDA",
                        "shares": 10,
                        "close": 200,
                        "daily_return": 0,
                        "as_of": "2026-09-11",
                        "cost_per_share": 200,
                    }
                ]
            )
        ),
        "caveats": ["test caveat"],
    }
    markdown = render_book_source(snapshot)
    assert "# Book snapshot 2026-09-11" in markdown
    assert "NVDA" in markdown
    assert "test caveat" in markdown


def test_report_needle_does_not_confuse_book_and_nvda():
    assert report_filename_needle("NVDA") == "-nvda-daily"
    assert report_filename_needle("book") == "-book-daily"
    assert "-nvda-daily" not in "2026-09-12-book-daily.md"
    assert "-book-daily" in "2026-09-12-book-daily.md"
    assert "-nvda-daily" in "2026-09-12-nvda-daily.md"


if __name__ == "__main__":
    test_summarize_book_weights_and_day()
    test_day_dollar_from_return()
    test_render_book_source_copies_tickers()
    test_report_needle_does_not_confuse_book_and_nvda()
    print("ok")

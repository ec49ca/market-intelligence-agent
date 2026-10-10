"""Constant-weight book risk from injected daily returns."""

import pandas as pd

from llm.book_risk import risk_from_returns
from llm.book import render_book_source


def _frame(rows: dict[str, list[float]]) -> pd.DataFrame:
    idx = pd.bdate_range("2026-01-02", periods=len(next(iter(rows.values()))))
    return pd.DataFrame(rows, index=idx)


def test_perfect_corr_equal_weights():
    r = [0.01 if i % 2 == 0 else -0.004 for i in range(80)]
    spy = [value / 2 for value in r]
    risk = risk_from_returns(
        {"NVDA": 0.6, "AMD": 0.4},
        _frame({"NVDA": r, "AMD": r, "SPY": spy}),
    )
    assert abs(risk["correlation"] - 1.0) < 1e-9
    assert risk["correlation_pair"] == "NVDA/AMD"
    assert risk["correlation_label"] == "historically move together"
    assert risk["pairs"][0]["high"] is True
    assert risk["vol_30d"] is not None and risk["vol_30d"] > 0
    assert abs(risk["beta_vs_spy"] - 2.0) < 1e-6
    assert risk["drawdown_90d"] is not None and risk["drawdown_90d"] <= 0
    assert risk["top_ticker"] == "NVDA"
    assert abs(risk["top_weight"] - 0.6) < 1e-9
    assert risk["concentration_label"] == "Elevated"
    assert risk["sector_line"] == "100% Semiconductors"
    assert "Constant today's weights" in risk["lookback"]
    assert "NVDA/AMD" in risk["assessment"]


def test_drawdown_from_peak():
    up = [0.01] * 40
    crash = [-0.2]
    flat = [0.0] * 40
    series = up + crash + flat
    risk = risk_from_returns(
        {"NVDA": 1.0},
        _frame({"NVDA": series, "SPY": series}),
    )
    assert risk["correlation"] is None
    assert risk["name_count"] == 1
    assert abs(risk["drawdown_90d"] - (-0.2)) < 1e-9


def test_render_book_source_includes_risk():
    markdown = render_book_source(
        {
            "as_of": "2026-09-11",
            "book": {
                "book_value": 3000,
                "name_count": 2,
                "top_ticker": "NVDA",
                "top_weight": 0.67,
                "names": [{"ticker": "NVDA", "shares": 10, "close": 200, "weight": 0.67}],
            },
            "risk": {
                "concentration_label": "Elevated",
                "top_ticker": "NVDA",
                "top_weight": 0.67,
                "name_count": 2,
                "sector_line": "100% Semiconductors",
                "corr_window": 90,
                "correlation_pair": "NVDA/AMD",
                "correlation": 0.81,
                "correlation_label": "historically move together",
                "vol_window": 30,
                "vol_30d": 0.02,
                "beta_window": 60,
                "beta_vs_spy": 1.4,
                "drawdown_window": 90,
                "drawdown_90d": -0.08,
                "lookback": "Constant today's weights over the lookback.",
                "assessment": "Elevated concentration: NVDA is 67% of the book.",
            },
            "caveats": [],
        }
    )
    assert "## Risk (constant today's weights)" in markdown
    assert "NVDA/AMD" in markdown
    assert "0.81" in markdown
    assert "1.40" in markdown
    assert "100% Semiconductors" in markdown
    assert "Elevated concentration" in markdown


if __name__ == "__main__":
    test_perfect_corr_equal_weights()
    test_drawdown_from_peak()
    test_render_book_source_includes_risk()
    print("ok")

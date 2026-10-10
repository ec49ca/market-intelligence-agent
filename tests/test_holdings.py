"""Book weights are shares × last close; P/L uses approx cost."""

from data.holdings import attach_weights


def test_weights_use_close_and_shares():
    rows = attach_weights(
        [
            {"ticker": "NVDA", "shares": 10, "close": 200},
            {"ticker": "AMD", "shares": 20, "close": 50},
            {"ticker": "MU", "shares": 0, "close": 100},
            {"ticker": "GOOGL", "shares": None, "close": 150},
        ]
    )
    by_ticker = {row["ticker"]: row for row in rows}
    assert by_ticker["NVDA"]["market_value"] == 2000
    assert by_ticker["AMD"]["market_value"] == 1000
    assert by_ticker["NVDA"]["weight"] == 2000 / 3000
    assert by_ticker["AMD"]["weight"] == 1000 / 3000
    assert by_ticker["MU"]["weight"] is None
    assert by_ticker["GOOGL"]["weight"] is None


def test_pnl_uses_stored_cost_else_default():
    rows = attach_weights(
        [
            {
                "ticker": "NVDA",
                "shares": 10,
                "close": 200,
                "cost_per_share": 100,
                "default_cost": 80,
            },
            {
                "ticker": "AMD",
                "shares": 5,
                "close": 50,
                "cost_per_share": None,
                "default_cost": 40,
            },
        ]
    )
    by_ticker = {row["ticker"]: row for row in rows}
    assert by_ticker["NVDA"]["display_cost"] == 100
    assert by_ticker["NVDA"]["cost_basis"] == 1000
    assert by_ticker["NVDA"]["unrealized"] == 1000
    assert by_ticker["NVDA"]["unrealized_pct"] == 1.0
    assert by_ticker["AMD"]["display_cost"] == 40
    assert by_ticker["AMD"]["cost_basis"] == 200
    assert by_ticker["AMD"]["unrealized"] == 50


if __name__ == "__main__":
    test_weights_use_close_and_shares()
    test_pnl_uses_stored_cost_else_default()
    print("ok")

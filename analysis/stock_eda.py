from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import psycopg

DB_HOST = "localhost"
DB_PORT = 5433
DB_USER = "market"
DB_PASSWORD = "market"
DB_NAME = "market_intel"

FIGURES = Path(__file__).resolve().parent / "figures"


def load_mart_frame(ticker: str) -> pd.DataFrame:
    ticker = ticker.strip().upper()
    with psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT date, close, ma_30d, volume, daily_return
                FROM analytics.mart_stock_metrics
                WHERE ticker = %s
                ORDER BY date
                """,
                (ticker,),
            )
            rows = cur.fetchall()

    df = pd.DataFrame(
        rows,
        columns=["date", "close", "ma_30d", "volume", "daily_return"],
    )
    if df.empty:
        raise ValueError(f"No mart_stock_metrics rows for {ticker}")
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"])
    df["ma_30d"] = pd.to_numeric(df["ma_30d"])
    df["volume"] = pd.to_numeric(df["volume"])
    df["daily_return"] = pd.to_numeric(df["daily_return"])
    return df


def plot_price_ma(df: pd.DataFrame, ticker: str, out_path: Path) -> None:
    plt.figure(figsize=(10, 5))
    plt.plot(df["date"], df["close"], label="Close")
    plt.plot(df["date"], df["ma_30d"], label="30D MA")
    plt.title(f"{ticker} close vs 30D MA")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def plot_volume(df: pd.DataFrame, ticker: str, out_path: Path) -> None:
    plt.figure(figsize=(10, 5))
    plt.bar(df["date"], df["volume"])
    plt.title(f"{ticker} volume")
    plt.xlabel("Date")
    plt.ylabel("Volume")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def plot_returns(df: pd.DataFrame, ticker: str, out_path: Path) -> None:
    plt.figure(figsize=(10, 5))
    plt.hist(df["daily_return"].dropna())
    plt.title(f"{ticker} daily returns")
    plt.xlabel("Daily return")
    plt.ylabel("Frequency")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def plot_drawdown(df: pd.DataFrame, ticker: str, out_path: Path) -> None:
    peak = df["close"].cummax()
    drawdown = df["close"] / peak - 1
    plt.figure(figsize=(10, 5))
    plt.plot(df["date"], drawdown)
    plt.title(f"{ticker} drawdown")
    plt.xlabel("Date")
    plt.ylabel("Drawdown")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def generate_stock_eda(ticker: str) -> dict[str, Path]:
    ticker = ticker.strip().upper()
    FIGURES.mkdir(exist_ok=True)
    df = load_mart_frame(ticker)
    paths = {
        "price": FIGURES / f"{ticker.lower()}_price_ma.png",
        "volume": FIGURES / f"{ticker.lower()}_volume.png",
        "returns": FIGURES / f"{ticker.lower()}_returns.png",
        "drawdown": FIGURES / f"{ticker.lower()}_drawdown.png",
    }
    plot_price_ma(df, ticker, paths["price"])
    plot_volume(df, ticker, paths["volume"])
    plot_returns(df, ticker, paths["returns"])
    plot_drawdown(df, ticker, paths["drawdown"])
    return paths


if __name__ == "__main__":
    generate_stock_eda("NVDA")

"""Today-facing attention scores: residual z, Isolation Forest, tape vs news, vol regime.

Not a forecast. Answers: was today weird for this name after the market,
did headlines show up with the move, and are we in a calm or storm vol state.
"""

from pathlib import Path
import os

import joblib
import numpy as np
import pandas as pd
import psycopg
from sklearn.ensemble import IsolationForest

from data.prices import INDEX_TICKER, load_watchlist

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "market")
DB_PASSWORD = os.getenv("DB_PASSWORD", "market")
DB_NAME = os.getenv("DB_NAME", "market_intel")

MODEL_PATH = Path(__file__).resolve().parent / "attention.joblib"
Z_WINDOW = 60
RV_WINDOW = 21
REGIME_LOOKBACK = 252
IFOREST_FEATURES = ["abs_ret", "abs_idio", "volume_ratio", "rv_21"]
TAPE_Z = 1.5
TAPE_RVOL = 2.0


def _connect():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    )


def load_price_frame() -> pd.DataFrame:
    sql = """
        SELECT ticker, date, close, daily_return, volume_ratio, beta_60d
        FROM analytics.mart_stock_metrics
        ORDER BY ticker, date
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [d.name for d in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    for col in ["close", "daily_return", "volume_ratio", "beta_60d"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_daily_news() -> pd.DataFrame:
    sql = """
        SELECT
            ticker,
            (published_at AT TIME ZONE 'America/New_York')::date AS date,
            COUNT(*)::int AS news_count,
            AVG(sentiment) AS avg_sentiment
        FROM raw_news
        GROUP BY 1, 2
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [d.name for d in cur.description]
    if not rows:
        return pd.DataFrame(columns=["ticker", "date", "news_count", "avg_sentiment"])
    news = pd.DataFrame(rows, columns=cols)
    news["date"] = pd.to_datetime(news["date"])
    news["news_count"] = pd.to_numeric(news["news_count"], errors="coerce")
    news["avg_sentiment"] = pd.to_numeric(news["avg_sentiment"], errors="coerce")
    return news


def load_news_7d() -> dict[str, tuple[int, float]]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ticker, COUNT(*)::int, AVG(sentiment)
                FROM raw_news
                WHERE published_at >= NOW() - INTERVAL '7 days'
                GROUP BY ticker
                """
            )
            return {
                row[0]: (int(row[1]), float(row[2]) if row[2] is not None else 0.0)
                for row in cur.fetchall()
            }


def _rolling_mad_z(series: pd.Series, window: int) -> pd.Series:
    """Modified z using only prior days, so today's spike does not inflate the baseline."""
    past = series.shift(1)
    med = past.rolling(window, min_periods=20).median()

    def _mad(values: np.ndarray) -> float:
        return float(np.median(np.abs(values - np.median(values))))

    mad = past.rolling(window, min_periods=20).apply(_mad, raw=True)
    return 0.6745 * (series - med) / mad.replace(0, np.nan)


def add_market_features(df: pd.DataFrame) -> pd.DataFrame:
    spy = df.loc[df["ticker"] == INDEX_TICKER, ["date", "daily_return"]].rename(
        columns={"daily_return": "spy_return"}
    )
    out = df.loc[df["ticker"] != INDEX_TICKER].copy()
    out = out.merge(spy, on="date", how="left").sort_values(["ticker", "date"])
    out["abs_ret"] = out["daily_return"].abs()
    out["idio"] = out["daily_return"] - out["beta_60d"] * out["spy_return"]
    out["abs_idio"] = out["idio"].abs()
    out["rv_21"] = out.groupby("ticker")["daily_return"].transform(
        lambda s: s.rolling(RV_WINDOW, min_periods=RV_WINDOW).std()
    )
    out["idio_z"] = out.groupby("ticker")["idio"].transform(
        lambda s: _rolling_mad_z(s, Z_WINDOW)
    )
    rv_med = out.groupby("ticker")["rv_21"].transform(
        lambda s: s.shift(1).rolling(REGIME_LOOKBACK, min_periods=60).median()
    )
    out["vol_regime"] = np.where(out["rv_21"] > 1.5 * rv_med, "storm", "calm")
    out.loc[rv_med.isna() | out["rv_21"].isna(), "vol_regime"] = "calm"
    return out


def attach_news(prices: pd.DataFrame, news: pd.DataFrame) -> pd.DataFrame:
    out = prices.merge(news, on=["ticker", "date"], how="left")
    out["news_count"] = out["news_count"].fillna(0).astype(int)
    out["avg_sentiment"] = out["avg_sentiment"].fillna(0.0)
    return out


def tape_label(idio_z, volume_ratio, news_count) -> str:
    z = abs(float(idio_z)) if pd.notna(idio_z) else 0.0
    rvol = float(volume_ratio) if pd.notna(volume_ratio) else 0.0
    n = int(news_count or 0)
    unusual = z >= TAPE_Z or rvol >= TAPE_RVOL
    has_news = n > 0
    if unusual and has_news:
        return "confirmed"
    if unusual and not has_news:
        return "silent"
    if has_news and not unusual:
        return "noise"
    return "quiet"


def fit_iforest(frame: pd.DataFrame) -> dict:
    models: dict[str, IsolationForest] = {}
    for ticker, grp in frame.groupby("ticker"):
        X = grp[IFOREST_FEATURES].fillna(0)
        if len(X) < 40:
            continue
        model = IsolationForest(
            n_estimators=200,
            contamination=0.08,
            random_state=42,
        )
        model.fit(X)
        models[ticker] = model
    joblib.dump({"kind": "attention_v1", "features": IFOREST_FEATURES, "models": models}, MODEL_PATH)
    return models


def apply_iforest(frame: pd.DataFrame, models: dict) -> pd.DataFrame:
    out = frame.copy()
    out["anomaly_score"] = np.nan
    out["iforest_flag"] = 0
    for ticker, grp in out.groupby("ticker"):
        model = models.get(ticker)
        if model is None:
            continue
        X = grp[IFOREST_FEATURES].fillna(0)
        raw = -model.score_samples(X)
        # 0–1 inside this name: higher = weirder vs that ticker's own history.
        ranks = pd.Series(raw, index=grp.index).rank(pct=True)
        flags = (model.predict(X) == -1).astype(int)
        out.loc[grp.index, "anomaly_score"] = ranks.to_numpy()
        out.loc[grp.index, "iforest_flag"] = flags
    return out


def overlay_latest_news(frame: pd.DataFrame) -> pd.DataFrame:
    news_7d = load_news_7d()
    if not news_7d:
        return frame
    out = frame.copy()
    out["news_count"] = pd.to_numeric(out["news_count"], errors="coerce").fillna(0)
    out["avg_sentiment"] = pd.to_numeric(out["avg_sentiment"], errors="coerce").fillna(0.0)
    latest_idx = out.sort_values("date").groupby("ticker").tail(1).index
    for idx in latest_idx:
        ticker = out.at[idx, "ticker"]
        if ticker in news_7d:
            out.loc[idx, "news_count"] = float(news_7d[ticker][0])
            out.loc[idx, "avg_sentiment"] = float(news_7d[ticker][1])
    return out


def build_scored_frame(*, overlay_news: bool = True) -> pd.DataFrame:
    featured = add_market_features(load_price_frame())
    featured = attach_news(featured, load_daily_news())
    if overlay_news:
        featured = overlay_latest_news(featured)
    models = fit_iforest(featured.dropna(subset=["rv_21"]))
    scored = apply_iforest(featured, models)
    scored["tape_news"] = [
        tape_label(z, rvol, n)
        for z, rvol, n in zip(
            scored["idio_z"], scored["volume_ratio"], scored["news_count"]
        )
    ]
    return scored


UPSERT_SQL = """
    INSERT INTO attention_scores (
        ticker, score_date, idio_return, idio_z, volume_ratio,
        anomaly_score, iforest_flag, news_count, avg_sentiment,
        tape_news, vol_regime
    )
    VALUES (
        %(ticker)s, %(score_date)s, %(idio_return)s, %(idio_z)s, %(volume_ratio)s,
        %(anomaly_score)s, %(iforest_flag)s, %(news_count)s, %(avg_sentiment)s,
        %(tape_news)s, %(vol_regime)s
    )
    ON CONFLICT (ticker, score_date) DO UPDATE SET
        idio_return = EXCLUDED.idio_return,
        idio_z = EXCLUDED.idio_z,
        volume_ratio = EXCLUDED.volume_ratio,
        anomaly_score = EXCLUDED.anomaly_score,
        iforest_flag = EXCLUDED.iforest_flag,
        news_count = EXCLUDED.news_count,
        avg_sentiment = EXCLUDED.avg_sentiment,
        tape_news = EXCLUDED.tape_news,
        vol_regime = EXCLUDED.vol_regime
"""


def score_attention(*, latest_only: bool = False) -> pd.DataFrame:
    scored = build_scored_frame(overlay_news=True)
    tracked = {ticker for ticker, _start in load_watchlist()}
    frame = scored[scored["ticker"].isin(tracked)].copy()
    if latest_only:
        frame = frame.sort_values("date").groupby("ticker", as_index=False).tail(1)
    rows = []
    for rec in frame.itertuples(index=False):
        if pd.isna(rec.idio_z) and pd.isna(rec.anomaly_score):
            continue
        rows.append(
            {
                "ticker": rec.ticker,
                "score_date": rec.date.date() if hasattr(rec.date, "date") else rec.date,
                "idio_return": None if pd.isna(rec.idio) else float(rec.idio),
                "idio_z": None if pd.isna(rec.idio_z) else float(rec.idio_z),
                "volume_ratio": None if pd.isna(rec.volume_ratio) else float(rec.volume_ratio),
                "anomaly_score": None if pd.isna(rec.anomaly_score) else float(rec.anomaly_score),
                "iforest_flag": int(rec.iforest_flag or 0),
                "news_count": int(rec.news_count or 0),
                "avg_sentiment": float(rec.avg_sentiment or 0),
                "tape_news": rec.tape_news,
                "vol_regime": rec.vol_regime,
            }
        )
    if rows:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(UPSERT_SQL, rows)
    return frame


def print_results(frame: pd.DataFrame) -> None:
    ready = frame.dropna(subset=["idio_z"]).copy()
    print("=== attention scores (nowcast, not a forecast) ===")
    print(f"rows with z={len(ready)}")
    print()
    print("Residual |z| flags (idio vs own 60d MAD, market subtracted)")
    print(f"  share |z|>=2: {(ready['idio_z'].abs() >= 2).mean():.1%}")
    print(f"  share |z|>=3: {(ready['idio_z'].abs() >= 3).mean():.1%}")
    print()
    hi = ready["idio_z"].abs() >= 2
    if hi.any() and (~hi).any():
        print("  mean |daily return| on |z|>=2:", f"{ready.loc[hi, 'abs_ret'].mean():.3%}")
        print("  mean |daily return| otherwise:", f"{ready.loc[~hi, 'abs_ret'].mean():.3%}")
        print("  mean volume ratio on |z|>=2:", f"{ready.loc[hi, 'volume_ratio'].mean():.2f}x")
        print("  mean volume ratio otherwise:", f"{ready.loc[~hi, 'volume_ratio'].mean():.2f}x")
    print()
    flagged = ready["iforest_flag"] == 1
    print("Isolation Forest (8% contamination, per ticker)")
    print(f"  flag rate: {flagged.mean():.1%}")
    if flagged.any() and (~flagged).any():
        print("  mean |idio| on IF flag:", f"{ready.loc[flagged, 'abs_idio'].mean():.3%}")
        print("  mean |idio| otherwise:", f"{ready.loc[~flagged, 'abs_idio'].mean():.3%}")
    print()
    print("Tape vs news")
    print(ready["tape_news"].value_counts().to_string())
    print()
    print("Vol regime")
    print(ready["vol_regime"].value_counts().to_string())
    print()
    latest = ready.sort_values("date").groupby("ticker", as_index=False).tail(1)
    print("Latest bar")
    cols = [
        "ticker",
        "date",
        "daily_return",
        "idio",
        "idio_z",
        "volume_ratio",
        "anomaly_score",
        "iforest_flag",
        "news_count",
        "avg_sentiment",
        "tape_news",
        "vol_regime",
    ]
    show = latest[cols].copy()
    show["date"] = pd.to_datetime(show["date"]).dt.date
    print(show.to_string(index=False))


if __name__ == "__main__":
    import sys

    latest_only = len(sys.argv) > 1 and sys.argv[1] == "latest"
    frame = score_attention(latest_only=latest_only)
    print_results(frame)
    print(f"wrote attention_scores ({'latest' if latest_only else 'history'})")
    print(f"saved {MODEL_PATH}")

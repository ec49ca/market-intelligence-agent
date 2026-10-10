"""Magnitude model: next-week jumpiness from lagged |returns| / realized vol.

Not a price forecast and not up/down. Unusual on the UI is
P(|next 5-day return| is in the top quintile), using a cutoff fit on train only.
"""

from pathlib import Path
import os

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from data.prices import INDEX_TICKER, load_watchlist

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "market")
DB_PASSWORD = os.getenv("DB_PASSWORD", "market")
DB_NAME = os.getenv("DB_NAME", "market_intel")

MODEL_PATH = Path(__file__).resolve().parent / "unusual_move.joblib"
FIG_DIR = Path(__file__).resolve().parent.parent / "analysis" / "figures"
COEF_PLOT = FIG_DIR / "unusual_move_coefs.png"
SCATTER_PLOT = FIG_DIR / "unusual_move_rv_scatter.png"
CMP_PLOT = FIG_DIR / "unusual_move_vs_baseline.png"
HORIZON = 5
JUMP_Q = 0.80

FEATURES = [
    "abs_ret",
    "rv_5",
    "rv_21",
    "rv_60",
    "volume_ratio",
    "abs_idio",
]


def _connect():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    )


def _num(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def load_mart_frame() -> pd.DataFrame:
    sql = """
        SELECT ticker, date, close, daily_return, volume_ratio, beta_60d,
               news_count, avg_sentiment
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
    return _num(
        df,
        ["close", "daily_return", "volume_ratio", "beta_60d", "news_count", "avg_sentiment"],
    )


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """HAR-style size features known at t. Residual vs SPY uses beta already in the mart."""
    spy = df.loc[df["ticker"] == INDEX_TICKER, ["date", "daily_return"]].rename(
        columns={"daily_return": "spy_return"}
    )
    out = df.loc[df["ticker"] != INDEX_TICKER].copy()
    out = out.merge(spy, on="date", how="left")
    out = out.sort_values(["ticker", "date"])
    out["abs_ret"] = out["daily_return"].abs()
    out["idio"] = out["daily_return"] - out["beta_60d"] * out["spy_return"]
    out["abs_idio"] = out["idio"].abs()
    grouped = out.groupby("ticker")["daily_return"]
    out["rv_5"] = grouped.transform(lambda s: s.rolling(5, min_periods=5).std())
    out["rv_21"] = grouped.transform(lambda s: s.rolling(21, min_periods=21).std())
    out["rv_60"] = grouped.transform(lambda s: s.rolling(60, min_periods=40).std())
    return out


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Future realized vol and |5d return|. Features stay at t (shifts are forward only)."""
    out = df.sort_values(["ticker", "date"]).copy()
    for k in range(1, HORIZON + 1):
        out[f"_fwd_{k}"] = out.groupby("ticker")["daily_return"].shift(-k)
    fwd = out[[f"_fwd_{k}" for k in range(1, HORIZON + 1)]]
    out["fut_rv_5"] = fwd.std(axis=1)
    out["close_fwd"] = out.groupby("ticker")["close"].shift(-HORIZON)
    out["next_5d_return"] = out["close_fwd"] / out["close"] - 1
    out["abs_5d"] = out["next_5d_return"].abs()
    out = out.drop(columns=[f"_fwd_{k}" for k in range(1, HORIZON + 1)])
    return out


def labeled_frame(df: pd.DataFrame | None = None) -> pd.DataFrame:
    raw = add_features(df if df is not None else load_mart_frame())
    labeled = add_targets(raw)
    return labeled.dropna(subset=FEATURES + ["fut_rv_5", "abs_5d", "close"])


def _pipe(estimator) -> Pipeline:
    return Pipeline(
        [
            (
                "impute",
                SimpleImputer(
                    strategy="constant",
                    fill_value=0,
                    keep_empty_features=True,
                ),
            ),
            ("scale", StandardScaler()),
            ("est", estimator),
        ]
    )


def make_rv_pipeline() -> Pipeline:
    return _pipe(Ridge(alpha=1.0))


def make_jump_pipeline() -> Pipeline:
    return _pipe(
        LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
        )
    )


def stance(
    proba: float,
    volume_ratio: float | None,
    momentum_12_1: float | None,
    sentiment: float | None,
) -> str:
    """Holder policy on top of the score. Default is hold; tails only."""
    if proba < 0.4:
        return "hold"
    if proba < 0.7:
        return "hold_watch"
    vr = float(volume_ratio or 0)
    mom = float(momentum_12_1 or 0)
    sent = float(sentiment or 0)
    if vr > 2 and mom > 0.5 and sent > 0.3:
        return "dont_chase"
    return "review"


def _ic(y_true, y_pred) -> float:
    a = pd.Series(np.asarray(y_true, dtype=float))
    b = pd.Series(np.asarray(y_pred, dtype=float))
    if a.nunique() < 2 or b.nunique() < 2:
        return float("nan")
    return float(a.corr(b, method="spearman"))


def _rmse(y_true, y_pred) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def _date_folds(dates: pd.Series, n_splits: int = 5):
    unique = np.sort(pd.to_datetime(dates).unique())
    splitter = TimeSeriesSplit(n_splits=n_splits)
    for train_idx, test_idx in splitter.split(unique):
        yield unique[train_idx], unique[test_idx]


def walk_forward(labeled: pd.DataFrame, n_splits: int = 5) -> dict:
    """OOS Ridge vs trailing-vol baseline, and logistic vs ranking by rv_5."""
    rv_rows = []
    jump_rows = []
    oos_actual = []
    oos_ridge = []
    oos_base = []
    for train_dates, test_dates in _date_folds(labeled["date"], n_splits=n_splits):
        train = labeled[labeled["date"].isin(train_dates)]
        test = labeled[labeled["date"].isin(test_dates)]
        if len(train) < 80 or len(test) < 20:
            continue
        q80 = float(train["abs_5d"].quantile(JUMP_Q))
        y_jump_tr = (train["abs_5d"] >= q80).astype(int)
        y_jump_te = (test["abs_5d"] >= q80).astype(int)
        if y_jump_tr.nunique() < 2 or y_jump_te.nunique() < 2:
            continue

        rv_pipe = make_rv_pipeline()
        rv_pipe.fit(train[FEATURES], train["fut_rv_5"])
        pred_rv = rv_pipe.predict(test[FEATURES])
        base_rv = test["rv_5"].fillna(0).to_numpy()

        jump_pipe = make_jump_pipeline()
        jump_pipe.fit(train[FEATURES], y_jump_tr)
        jump_p = jump_pipe.predict_proba(test[FEATURES])[:, 1]

        rv_rows.append(
            {
                "n_train": len(train),
                "n_test": len(test),
                "rmse_ridge": _rmse(test["fut_rv_5"], pred_rv),
                "rmse_base": _rmse(test["fut_rv_5"], base_rv),
                "mae_ridge": float(mean_absolute_error(test["fut_rv_5"], pred_rv)),
                "mae_base": float(mean_absolute_error(test["fut_rv_5"], base_rv)),
                "ic_ridge": _ic(test["fut_rv_5"], pred_rv),
                "ic_base": _ic(test["fut_rv_5"], base_rv),
                "ic_abs5_ridge": _ic(test["abs_5d"], pred_rv),
                "ic_abs5_base": _ic(test["abs_5d"], base_rv),
            }
        )
        jump_rows.append(
            {
                "auc_model": float(roc_auc_score(y_jump_te, jump_p)),
                "auc_base": float(roc_auc_score(y_jump_te, base_rv)),
                "jump_rate": float(y_jump_te.mean()),
            }
        )
        oos_actual.extend(test["fut_rv_5"].tolist())
        oos_ridge.extend(pred_rv.tolist())
        oos_base.extend(base_rv.tolist())

    return {
        "rv": pd.DataFrame(rv_rows),
        "jump": pd.DataFrame(jump_rows),
        "oos_actual": np.asarray(oos_actual),
        "oos_ridge": np.asarray(oos_ridge),
        "oos_base": np.asarray(oos_base),
    }


def _plot_ridge_coefs(pipe: Pipeline) -> None:
    coefs = pd.Series(pipe.named_steps["est"].coef_, index=FEATURES).sort_values()
    FIG_DIR.mkdir(exist_ok=True)
    plt.figure(figsize=(8, 4.5))
    plt.barh(coefs.index, coefs.values)
    plt.title("Ridge weights for next-5d realized vol (scaled HAR features)")
    plt.tight_layout()
    plt.savefig(COEF_PLOT)
    plt.close()


def _plot_scatter(actual, pred, base) -> None:
    FIG_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(9, 4), sharex=True, sharey=True)
    for ax, yhat, title in (
        (axes[0], pred, "Ridge OOS"),
        (axes[1], base, "Baseline rv_5 OOS"),
    ):
        ax.scatter(actual, yhat, s=8, alpha=0.35)
        lo = np.nanmin(actual)
        hi = np.nanmax(actual)
        ax.plot([lo, hi], [lo, hi], color="black", linewidth=1)
        ax.set_title(title)
        ax.set_xlabel("actual next-5d realized vol")
        ax.set_ylabel("predicted")
    fig.tight_layout()
    fig.savefig(SCATTER_PLOT)
    plt.close(fig)


def _plot_comparison(rv: pd.DataFrame, jump: pd.DataFrame) -> None:
    FIG_DIR.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    axes[0].bar(
        ["Ridge", "Baseline rv_5"],
        [rv["rmse_ridge"].mean(), rv["rmse_base"].mean()],
    )
    axes[0].set_title("Walk-forward RMSE (next-5d RV)")
    axes[1].bar(
        ["Logistic", "Baseline rv_5"],
        [jump["auc_model"].mean(), jump["auc_base"].mean()],
    )
    axes[1].set_title("Walk-forward AUC (top-quintile |5d|)")
    axes[1].set_ylim(0.45, 0.75)
    fig.tight_layout()
    fig.savefig(CMP_PLOT)
    plt.close(fig)


def _print_report(wf: dict, q80: float, n_labeled: int) -> None:
    rv = wf["rv"]
    jump = wf["jump"]
    print("=== magnitude v2 (HAR features, walk-forward) ===")
    print(f"labeled rows={n_labeled}  top-quintile |5d| cutoff (final fit)={q80:.4f}")
    print()
    print("Next-5d realized vol  (mean across folds)")
    print(
        f"  RMSE  ridge={rv['rmse_ridge'].mean():.5f}  "
        f"baseline rv_5={rv['rmse_base'].mean():.5f}"
    )
    print(
        f"  MAE   ridge={rv['mae_ridge'].mean():.5f}  "
        f"baseline rv_5={rv['mae_base'].mean():.5f}"
    )
    print(
        f"  IC vs fut RV   ridge={rv['ic_ridge'].mean():.3f}  "
        f"baseline={rv['ic_base'].mean():.3f}"
    )
    print(
        f"  IC vs |5d ret| ridge={rv['ic_abs5_ridge'].mean():.3f}  "
        f"baseline={rv['ic_abs5_base'].mean():.3f}"
    )
    print()
    print("Top-quintile |5-day return|  (cutoff from each fold's train only)")
    print(
        f"  AUC   logistic={jump['auc_model'].mean():.3f}  "
        f"baseline rv_5={jump['auc_base'].mean():.3f}  "
        f"test jump rate={jump['jump_rate'].mean():.2f}"
    )
    print()
    print(rv.to_string(index=False))
    print(jump.to_string(index=False))


def train_and_save() -> dict:
    labeled = labeled_frame()
    if labeled.empty:
        raise RuntimeError("No labeled mart rows — need prices and rolling vol")
    wf = walk_forward(labeled)
    if wf["rv"].empty:
        raise RuntimeError("Walk-forward produced no folds — need more history")

    q80 = float(labeled["abs_5d"].quantile(JUMP_Q))
    y_jump = (labeled["abs_5d"] >= q80).astype(int)
    rv_pipe = make_rv_pipeline()
    rv_pipe.fit(labeled[FEATURES], labeled["fut_rv_5"])
    jump_pipe = make_jump_pipeline()
    jump_pipe.fit(labeled[FEATURES], y_jump)

    artifact = {
        "kind": "magnitude_v2",
        "features": FEATURES,
        "rv_model": rv_pipe,
        "jump_model": jump_pipe,
        "q80": q80,
        "horizon": HORIZON,
    }
    joblib.dump(artifact, MODEL_PATH)
    _plot_ridge_coefs(rv_pipe)
    _plot_scatter(wf["oos_actual"], wf["oos_ridge"], wf["oos_base"])
    _plot_comparison(wf["rv"], wf["jump"])
    _print_report(wf, q80, len(labeled))
    print(f"saved {MODEL_PATH}")
    print(f"saved {COEF_PLOT}")
    print(f"saved {SCATTER_PLOT}")
    print(f"saved {CMP_PLOT}")
    return {
        "q80": q80,
        "rmse_ridge": float(wf["rv"]["rmse_ridge"].mean()),
        "rmse_base": float(wf["rv"]["rmse_base"].mean()),
        "auc_model": float(wf["jump"]["auc_model"].mean()),
        "auc_base": float(wf["jump"]["auc_base"].mean()),
    }


def _load_artifact() -> dict:
    if not MODEL_PATH.exists():
        raise RuntimeError(f"No model at {MODEL_PATH} — run train first")
    artifact = joblib.load(MODEL_PATH)
    if not isinstance(artifact, dict) or artifact.get("kind") != "magnitude_v2":
        raise RuntimeError("Saved model is the old classifier — retrain with python -m ml.unusual_move")
    return artifact


UPSERT_SQL = """
    INSERT INTO model_scores (
        ticker, score_date, proba, predicted, stance, pred_rv_5d
    )
    VALUES (
        %(ticker)s, %(score_date)s, %(proba)s, %(predicted)s, %(stance)s, %(pred_rv_5d)s
    )
    ON CONFLICT (ticker, score_date) DO UPDATE SET
        proba = EXCLUDED.proba,
        predicted = EXCLUDED.predicted,
        stance = EXCLUDED.stance,
        pred_rv_5d = EXCLUDED.pred_rv_5d
"""


def _overlay_recent_news(frame: pd.DataFrame) -> pd.DataFrame:
    """News often lands on non-trading days; attach 7d rollup to the latest bar."""
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
            news = {
                row[0]: (int(row[1]), float(row[2]) if row[2] is not None else 0.0)
                for row in cur.fetchall()
            }
    if not news:
        return frame
    out = frame.copy()
    latest_idx = out.sort_values("date").groupby("ticker").tail(1).index
    for idx in latest_idx:
        ticker = out.at[idx, "ticker"]
        if ticker in news:
            out.at[idx, "news_count"] = news[ticker][0]
            out.at[idx, "avg_sentiment"] = news[ticker][1]
    return out


def score_watchlist(*, latest_only: bool = True) -> int:
    artifact = _load_artifact()
    featured = add_features(load_mart_frame())
    if featured.empty:
        return 0
    tracked = {ticker for ticker, _start in load_watchlist()}
    frame = featured[featured["ticker"].isin(tracked)].copy()
    frame = frame.dropna(subset=["rv_5"])
    if latest_only:
        frame = frame.sort_values("date").groupby("ticker", as_index=False).tail(1)
    if frame.empty:
        return 0
    frame = _overlay_recent_news(frame)
    X = frame[FEATURES]
    proba = artifact["jump_model"].predict_proba(X)[:, 1]
    pred_rv = artifact["rv_model"].predict(X)
    predicted = (proba >= 0.5).astype(int)
    rows = []
    latest_print: dict[str, str] = {}
    for i, (_, row) in enumerate(frame.iterrows()):
        p = float(proba[i])
        label = stance(
            p,
            row.get("volume_ratio"),
            None,
            row.get("avg_sentiment"),
        )
        rows.append(
            {
                "ticker": row["ticker"],
                "score_date": row["date"].date(),
                "proba": p,
                "predicted": int(predicted[i]),
                "stance": label,
                "pred_rv_5d": float(pred_rv[i]),
            }
        )
        latest_print[row["ticker"]] = (
            f"{row['ticker']}: P(top-quintile |5d|)={p:.3f} "
            f"pred_rv={pred_rv[i]:.4f} stance={label}"
        )
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(UPSERT_SQL, rows)
    for line in latest_print.values():
        print(line)
    return len(rows)


def fill_actuals() -> int:
    """When 5 later closes exist, store realized vol, |5d| outcome vs train quintile."""
    artifact = _load_artifact()
    q80 = float(artifact["q80"])
    labeled = labeled_frame()
    labeled["score_date"] = labeled["date"].dt.date
    updated = 0
    with _connect() as conn:
        with conn.cursor() as cur:
            for rec in labeled.itertuples(index=False):
                cur.execute(
                    """
                    UPDATE model_scores
                    SET actual_large_move = %s,
                        next_5d_return = %s,
                        actual_rv_5d = %s
                    WHERE ticker = %s AND score_date = %s
                    """,
                    (
                        int(rec.abs_5d >= q80),
                        float(rec.next_5d_return),
                        float(rec.fut_rv_5),
                        rec.ticker,
                        rec.score_date,
                    ),
                )
                updated += cur.rowcount
    return updated


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "train"
    if cmd == "score":
        print(f"scored {score_watchlist()} rows")
    elif cmd == "history":
        print(f"scored {score_watchlist(latest_only=False)} rows")
        print(f"filled actuals on {fill_actuals()} rows")
    elif cmd == "actuals":
        print(f"filled actuals on {fill_actuals()} rows")
    else:
        train_and_save()
        print(f"scored {score_watchlist(latest_only=False)} rows")
        print(f"filled actuals on {fill_actuals()} rows")

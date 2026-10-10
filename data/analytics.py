"""Rebuild analytics marts (dbt). Same command locally and from Airflow."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = ROOT / "dbt"


def _dbt_bin() -> str:
    found = shutil.which("dbt")
    if found:
        return found
    candidates = [
        Path(sys.executable).parent / "dbt",
        ROOT / ".venv" / "bin" / "dbt",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    raise RuntimeError("dbt is not installed (need dbt-postgres on PATH)")


def refresh_analytics() -> None:
    env = os.environ.copy()
    env.setdefault("DB_HOST", "localhost")
    env.setdefault("DB_PORT", "5433")
    env.setdefault("DB_USER", "market")
    env.setdefault("DB_PASSWORD", "market")
    env.setdefault("DB_NAME", "market_intel")
    result = subprocess.run(
        [
            _dbt_bin(),
            "run",
            "--project-dir",
            str(DBT_DIR),
            "--profiles-dir",
            str(DBT_DIR),
        ],
        cwd=DBT_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "dbt run failed:\n"
            + (result.stdout or "")[-4000:]
            + "\n"
            + (result.stderr or "")[-2000:]
        )
    print(result.stdout[-2000:] if result.stdout else "dbt run ok")


if __name__ == "__main__":
    refresh_analytics()

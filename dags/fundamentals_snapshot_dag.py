from datetime import datetime, timedelta

# Airflow lives in the Docker image, not the local .venv.
from airflow import DAG  # pyright: ignore[reportMissingImports]
from airflow.operators.python import PythonOperator  # pyright: ignore[reportMissingImports]

from data.fundamentals import snapshot_watchlist_fundamentals

with DAG(
    dag_id="fundamentals_snapshot_dag",
    description="Weekly Yahoo quoteSummary → raw_fundamentals for the watchlist",
    start_date=datetime(2026, 8, 1),
    schedule="0 18 * * 0",
    catchup=False,
    is_paused_upon_creation=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["ingestion", "fundamentals"],
) as dag:
    PythonOperator(
        task_id="snapshot_watchlist_fundamentals",
        python_callable=snapshot_watchlist_fundamentals,
    )

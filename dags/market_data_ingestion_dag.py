from datetime import datetime, timedelta

# Airflow lives in the Docker image, not the local .venv.
from airflow import DAG  # pyright: ignore[reportMissingImports]
from airflow.operators.python import PythonOperator  # pyright: ignore[reportMissingImports]

from data.prices import backfill_watchlist

with DAG(
    dag_id="market_data_ingestion_dag",
    description="Daily incremental Yahoo → raw_prices for the watchlist",
    start_date=datetime(2026, 8, 1),
    schedule="0 18 * * 1-5",
    catchup=False,
    is_paused_upon_creation=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["ingestion", "prices"],
) as dag:
    PythonOperator(
        task_id="backfill_watchlist",
        python_callable=backfill_watchlist,
    )

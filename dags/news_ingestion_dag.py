from datetime import datetime, timedelta

# Airflow lives in the Docker image, not the local .venv.
from airflow import DAG  # pyright: ignore[reportMissingImports]
from airflow.operators.python import PythonOperator  # pyright: ignore[reportMissingImports]

from data.news import ingest_watchlist_news

with DAG(
    dag_id="news_ingestion_dag",
    description="Weekday Yahoo news → raw_news for the watchlist",
    start_date=datetime(2026, 8, 1),
    schedule="30 18 * * 1-5",
    catchup=False,
    is_paused_upon_creation=False,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["ingestion", "news"],
) as dag:
    PythonOperator(
        task_id="ingest_watchlist_news",
        python_callable=ingest_watchlist_news,
    )

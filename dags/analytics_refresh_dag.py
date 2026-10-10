from datetime import datetime, timedelta

# Airflow lives in the Docker image, not the local .venv.
from airflow import DAG  # pyright: ignore[reportMissingImports]
from airflow.operators.python import PythonOperator  # pyright: ignore[reportMissingImports]

from data.analytics import refresh_analytics

with DAG(
    dag_id="analytics_refresh_dag",
    description="dbt run: raw_prices/news/fundamentals → analytics.mart_stock_metrics",
    start_date=datetime(2026, 8, 1),
    schedule="15 18 * * 1-5",
    catchup=False,
    is_paused_upon_creation=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["analytics", "dbt"],
) as dag:
    PythonOperator(
        task_id="dbt_run",
        python_callable=refresh_analytics,
    )

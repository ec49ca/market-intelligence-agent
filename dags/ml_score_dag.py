from datetime import datetime, timedelta

# Airflow lives in the Docker image, not the local .venv.
from airflow import DAG  # pyright: ignore[reportMissingImports]
from airflow.operators.python import PythonOperator  # pyright: ignore[reportMissingImports]

from ml.attention import score_attention

with DAG(
    dag_id="ml_score_dag",
    description="Score watchlist attention (residual z, tape vs news, vol regime)",
    start_date=datetime(2026, 8, 1),
    schedule="45 18 * * 1-5",
    catchup=False,
    is_paused_upon_creation=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["ml"],
) as dag:
    PythonOperator(
        task_id="score_attention",
        python_callable=score_attention,
        op_kwargs={"latest_only": True},
    )

from datetime import datetime, timedelta

# Airflow lives in the Docker image, not the local .venv.
from airflow import DAG  # pyright: ignore[reportMissingImports]
from airflow.operators.python import PythonOperator  # pyright: ignore[reportMissingImports]

from data.prices import load_watchlist
from llm.ingest import ingest_book, ingest_ticker
from llm.query import generate_book_report, generate_report


def ingest_watchlist_wikis():
    """Every active watchlist ticker, then the Book hub and book letter."""
    tracked = load_watchlist()
    if not tracked:
        print("watchlist is empty")
        return
    for ticker, _start in tracked:
        try:
            result = ingest_ticker(ticker)
            print(
                f"{ticker}: wiki as_of={result.get('as_of')} "
                f"skipped={result.get('skipped')}"
            )
        except Exception as exc:
            print(f"{ticker}: wiki ingest failed ({exc})")
            continue
        try:
            report = generate_report(ticker, ingest_first=False)
            print(f"{ticker}: letter {report.get('filename')}")
        except Exception as extra:
            print(f"{ticker}: letter failed ({extra})")
    try:
        book = ingest_book()
        print(
            f"Book: wiki as_of={book.get('as_of')} skipped={book.get('skipped')}"
        )
    except Exception as exc:
        print(f"Book: wiki ingest failed ({exc})")
        return
    try:
        letter = generate_book_report(ingest_first=False)
        print(f"Book: letter {letter.get('filename')}")
    except Exception as extra:
        print(f"Book: letter failed ({extra})")


with DAG(
    dag_id="wiki_ingest_dag",
    description="Watchlist ticker wikis + letters, then Book hub and portfolio letter",
    start_date=datetime(2026, 8, 1),
    schedule="50 18 * * 1-5",
    catchup=False,
    is_paused_upon_creation=False,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["wiki", "llm"],
) as dag:
    PythonOperator(
        task_id="ingest_watchlist_wikis",
        python_callable=ingest_watchlist_wikis,
    )

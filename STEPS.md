# Build order

Build this as **thin vertical slices**, not “all backend, then all pipelines, then all frontend.” Each slice should go from user action → data → something you can see.

Airflow, ML, and the LLM wait until the thing they would orchestrate or talk to already works as a plain Python script.

Product spec lives in [README.md](README.md). This file is the sequence to actually build it.

---

## The sequence

### 1. Postgres + schema (nothing else)

Docker Compose with PostgreSQL. Tables: `companies`, `watchlist`, `raw_prices`. That’s enough to start. No warehouse layers yet.

### 2. Watchlist API, then a ugly Next.js page

`GET/POST/DELETE /watchlist` and `GET /stocks/search`. Then a page that can search, add NVDA, pick 3 months / 1 year / 3 years. You now have a real product loop: pick a stock → persist it. Don’t polish UI.

### 3. Ingestion as a Python script, not Airflow

One market-data provider. Functions: fetch range, clean, validate, upsert into `raw_prices` (idempotent on ticker+date). Trigger backfill from “add to watchlist.” Prove incremental load: if latest stored is Aug 23, only fetch Aug 24.

### 4. First analytics, then one chart

SQL: daily return + 30D MA on prices. One FastAPI metrics/prices endpoint. One Next.js chart on `/stocks/NVDA`. **This is Milestone 1 done.** You have search → watchlist → backfill → DB → a number → a chart.

### 5. Then wrap that job in Airflow

`market_data_ingestion_dag` calling the **same** Python you already run by hand. Schedule, retries, logging. `analytics_refresh_dag` after it. Airflow is orchestration of working code, not the place you invent ingestion.

### 6. Warehouse layers (still prices only)

`raw → stg → int → mart` for prices. CTEs, `LAG()`, rolling windows, indexes, uniqueness. Point the API at marts, not raw tables.

### 7. Python EDA module

`analysis/` with matplotlib: price+MA, volume, returns histogram. `generate_stock_eda("NVDA")` writing PNGs. Do this before more React charts so the DA work is real Python, not only frontend.

### 8. News/events (one source), then join to prices

Same pattern: Python job → table → Airflow DAG → staging/marts → events on the stock page.

### 9. Dashboard + compare

Watchlist table, date-range toggles, correlation, risk/return. `/compare` with checkboxes. Frontend state: selection, range, loading, errors.

### 10. ML last among the analytics

Features from marts you already trust. Logistic regression (unusual move), Pipeline, CV, `joblib`, `model_scores`. Matplotlib for confusion matrix / coefficients. Then show the score on the dashboard.

### 11. Compaction

Only after you actually have hot/warm history. `historical_compaction_dag`: roll up → validate → store → delete detail.

### 12. LLM reports last

Tools that **read** watchlist metrics, events, model scores. Persist `generated_reports`. No agent until those tools return real numbers.

---

## Keep on the side until the slice above exists

| Don’t start with | Why |
|---|---|
| Airflow | Orchestrates jobs you haven’t written |
| Full Next.js polish | You’ll redesign it once metrics exist |
| Plotly / fancy viz | matplotlib first, matching the syllabus |
| Second price API | One source until backfill + incremental are solid |
| Price prediction | Noisy; unusual-move / anomaly instead |
| Vector DB / agent | Wrapper without a data system |

---

## Folders, in the order you’d actually create them

If you sat down tomorrow:

1. `docker-compose` + SQL schema
2. `api/` watchlist + search
3. `frontend/` search/add page
4. `data/` price fetch/load script
5. SQL metrics + one chart
6. `airflow/` around that script
7. `sql/` staging/marts
8. `analysis/` matplotlib EDA
9. news → richer dashboard → `ml/` → compaction → agent

**Frontend appears early and thin** (step 2). **Airflow appears late for each pipeline** (after the script works).

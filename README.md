# Market Intelligence & Analytics Platform

A web application where a user tracks 5–20 stocks, backfills history, ingests new data on a schedule, models it in SQL, calculates financial analytics, runs Python EDA + visualizations, scores unusual movement with ML, views everything in Next.js, generates AI reports, and compresses old historical information.

AI is the **final layer**. The majority of the application is a genuine data / analytics system.

Build sequence: [STEPS.md](STEPS.md).

```
search / select stocks
        ↓
track them in a watchlist
        ↓
backfill historical data
        ↓
automatically ingest new data
        ↓
clean / model it in SQL
        ↓
calculate financial analytics
        ↓
run Python EDA + visualizations
        ↓
run ML / anomaly scoring
        ↓
view everything interactively in Next.js
        ↓
generate AI reports
        ↓
compress old historical information
```

## Design principle

Do **not** make the LLM the core data system.

```
real deterministic data pipeline
        ↓
clean database
        ↓
analytics / ML
        ↓
LLM agent reads those results
        ↓
human-readable report
```

The word that matters for historical ingestion: **backfill**. If you add NVDA today and request the previous 12 months, the system backfills historical data before starting normal scheduled collection.

---

## Full application architecture

```
                    USER
                      │
                      ▼
                  NEXT.JS
        ┌─────────────┼─────────────┐
        │             │             │
     Watchlist     Analytics     Reports
        │             │             │
        └─────────────┼─────────────┘
                      ▼
                   FASTAPI
        ┌─────────────┼─────────────┐
        │             │             │
    Watchlist      Analytics       Agent
     Service        Service       Service
        │             │             │
        └─────────────┼─────────────┘
                      ▼
                  POSTGRESQL
        ┌─────────────┼─────────────┐
        │             │             │
       Raw       Analytics Marts   ML Scores
        ▲
        │
                    AIRFLOW
        ┌─────────────┼───────────────┐
        │             │               │
     Ingestion     Analytics       Compaction
        │          Refresh             │
        ▼                              ▼
   External APIs                 Historical Data
```

Separately, analysis and ML sit on top of Postgres — they are required layers, not optional:

```
POSTGRESQL
    ↓
PYTHON ANALYSIS
    ↓
pandas / NumPy
    ↓
matplotlib
    ↓
EDA figures + analytical validation
```

```
POSTGRESQL
    ↓
SKLEARN
    ↓
scoring model
    ↓
model scores
    ↓
dashboard + AI
```

## Target repo layout

A hiring manager looking at the repo should be able to see a strong DA center, with DE, applied DS/ML, API/product, and AI built outward from it:

```
/data                    data engineering
/sql                     transformations, staging, marts
/airflow                 orchestration

/analysis
    exploratory_analysis.py
    stock_visualizations.py
    watchlist_visualizations.py
    correlation_analysis.py
    report_visualizations.py

/ml
    features.py
    train.py
    evaluate.py

/api                     FastAPI
/frontend                Next.js
```

Python visualization is a **required** project layer, not optional.

---

## Part 1 — Stock search & watchlist

### What the application does

```
Stock Tracker

Search:
[ Nvidia_______________ ] [ Search ]

NVDA — NVIDIA Corporation
[ + Add to Watchlist ]

Historical Data:
○ 3 months
○ 1 year
○ 3 years
```

Tracked stocks might include NVDA, AMD, MU, GOOGL, AMZN, META, MP. Keep it around **5–20 stocks**.

### Backend

Tables: `companies`, `watchlist`.

```
watchlist
------------------------
ticker
company_name
added_at
active
backfill_start_date
```

Example:

| ticker | company | added_at | active |
|---|---|---|---|
| NVDA | NVIDIA | 2026-08-25 | true |
| AMD | AMD | 2026-08-25 | true |
| MU | Micron | 2026-08-26 | true |

### FastAPI endpoints (this part)

```
GET    /stocks/search
GET    /watchlist
POST   /watchlist
DELETE /watchlist/{ticker}
```

### Skills repeated

Python, functions, dicts, JSON, SQL, schema design, FastAPI, Pydantic, HTTP methods, Next.js, forms, frontend API calls.

This is the easy opening milestone.

---

## Part 2 — Data ingestion, backfills & Airflow

When you add NVDA:

```
Add NVDA
     ↓
requested history = 1 year
     ↓
historical BACKFILL
     ↓
external market API
     ↓
raw data
     ↓
clean
     ↓
validate
     ↓
database
```

After that initial backfill, use **incremental ingestion**. Do not download the entire year every day.

```
latest date stored:  August 23
today:               August 24
                     ↓
only request August 24
```

Conceptually:

```
if latest_stored_date < today:
    fetch(latest_stored_date + 1, today)
```

### Data sources

Start with **one working source per category**. Do not start with five providers for each.

**1. Market prices**

- ticker
- timestamp / date
- open
- high
- low
- close
- volume

**2. Fundamentals** (depending on the chosen source)

- market_cap
- revenue
- EPS
- PE
- cash
- debt
- earnings_date

**3. News / events**

- ticker
- published_at
- headline
- source
- event_type
- URL
- sentiment

Pipeline:

```
                 STOCK
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
        price   fundamentals news
          │        │        │
          └────────┼────────┘
                   ▼
              normalization
                   ▼
              PostgreSQL
```

### Airflow

Create DAGs:

- `market_data_ingestion_dag`
- `news_ingestion_dag`
- `analytics_refresh_dag`
- `historical_compaction_dag` (Part 7)

Plus, when a new company is added:

```
backfill_stock_data(ticker, start_date, end_date)
```

Practice explicitly: tasks, dependencies, schedules, retries, failure handling, backfills, idempotency, logging.

This maps to Weeks 9–11: Python data pipelines, data/analytics engineering, Airflow + APIs.

---

## Part 3 — SQL data modeling / analytics engineering

This should be a **major component**. It shows DA / AE / DE ability.

Do **not** query raw APIs directly from the dashboard.

```
RAW
 ↓
STAGING
 ↓
INTERMEDIATE
 ↓
MARTS
```

Examples:

```
raw_prices
raw_news
raw_fundamentals

stg_prices
stg_news
stg_fundamentals

int_daily_stock_metrics
int_stock_events
int_market_comparisons

mart_stock_summary
mart_watchlist_summary
mart_stock_risk
```

Analytics mart shape:

| ticker | date | close | daily_return | return_30d | vol_30d | avg_volume_30d | volume_ratio |
|---|---|---|---|---|---|---|---|

### SQL analytics to use on purpose

CTEs, joins, `GROUP BY`, window functions, `LAG()`, rolling calculations, indexes, unique constraints, data quality tests.

**Daily return**

```
today_close - previous_close
────────────────────────────
previous_close
```

**Rolling averages** — 7-day, 30-day, 90-day.

**Rolling volatility** — calculated from historical returns.

**Relative volume**

```
today volume
──────────────
30D avg volume
```

Also: max drawdown, distance from 52-week high, NVDA return vs S&P 500 return, watchlist correlations.

This is the visible DA / analytics-engineering core.

### First schema (tables)

- `companies`
- `watchlist`
- `raw_prices`
- `raw_events`
- `raw_fundamentals`
- `stg_prices`
- `stg_events`
- `daily_stock_metrics`
- `stock_event_metrics`
- `stock_model_scores`
- `weekly_stock_rollups`
- `monthly_stock_rollups`
- `generated_reports`
- `pipeline_runs`

This is a data platform, not just a website.

---

## Part 4 — Python analytics + visualization

A separate analysis module, so visualization is actually written in Python rather than delegated entirely to React.

```
analysis/
├── exploratory_analysis.py
├── stock_visualizations.py
├── watchlist_visualizations.py
├── correlation_analysis.py
└── report_visualizations.py
```

Start with tools already practiced:

```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
```

Later, optionally:

```python
import plotly.express as px
import plotly.graph_objects as go
```

### Visualization 1 — Price history

Implement `plt.plot(...)`. Show price over time, then add 30-day and 90-day moving averages.

```
Price
│
│              ╭──╮
│         ╭────╯  ╰──
│    ╭────╯
│────╯
│
└──────────────────── Date

—— Closing Price
—— 30D MA
—— 90D MA
```

Reinforces: `pandas` `rolling()`, matplotlib, time-series analysis.

### Visualization 2 — Trading volume

Bar plot with `plt.bar(...)`. Highlight abnormal-volume periods. This ties directly into metrics later used by ML.

```
volume
│     █
│     █           █
│ █   █   █ █     █
│ █ █ █ █ █ █ █ █ █
└──────────────────── date
```

### Visualization 3 — Return distribution

Histogram with `plt.hist(...)`. Calculate mean, median, standard deviation, percentiles.

```
frequency
│
│       ███
│     ███████
│   █████████
│ ██         ██
└──────────────── return
       0%
```

### Visualization 4 — Rolling volatility

Calculate the metric with pandas / NumPy, then visualize it.

```
Volatility
│              ╭─╮
│          ╭───╯ ╰╮
│    ╭─────╯       ╰──
└────────────────────── Date
```

### Visualization 5 — Correlation matrix

For tracked stocks:

```
        NVDA   AMD    MU   GOOGL
NVDA    1.00   .78   .61   .42
AMD      .78  1.00   .69   .37
MU       .61   .69  1.00   .30
GOOGL    .42   .37   .30  1.00
```

Visualize as a heatmap with `plt.imshow(...)` (stay with syllabus tools rather than relying on Seaborn).

Analytical question: which of my tracked assets tend to move together?

### Visualization 6 — Risk vs return

One of the best charts for the portfolio / watchlist page. Each dot is a stock. X = volatility, Y = return.

```
RETURN
   ↑
   │            ● NVDA
   │
   │      ● GOOGL
   │                  ● AMD
   │
   │   ● MU
   └────────────────────────→
             VOLATILITY
```

### Visualization 7 — Drawdown

Decline from historical peaks. Answers: how bad have the losses actually gotten relative to peaks?

```
 0% ─────────────────
     ╲
-10%  ╲─────╮
             ╲
-20%          ╰──
```

### Visualization 8 — Watchlist comparison

Bar chart of 30-day returns. Dynamically rank best performers, worst performers, highest volatility, highest unusual activity.

```
30 DAY RETURNS

NVDA    ███████████ +12%
AMD     ███████      +7%
GOOGL   █████         +5%
MU      ██            +2%
MP      ███           -3%
```

### Python EDA report

```python
def generate_stock_eda(ticker):
    ...
```

Automatically produces several figures and summary metrics, e.g.:

```
reports/eda/NVDA/
    price_history.png
    volume_history.png
    return_distribution.png
    volatility.png
    drawdown.png
```

This demonstrates Python, pandas, NumPy, matplotlib, functions, file output, and analytical reasoning — not only JavaScript charts.

---

## Part 5 — Interactive Next.js analytics dashboard

Take the same analytical concepts and make interactive versions for the product.

Pages:

| Route | Purpose |
|---|---|
| `/dashboard` | Watchlist overview |
| `/stocks/[ticker]` | Individual stock analytics |
| `/compare` | Multi-stock charts |
| `/reports` | Generate / read reports |
| `/settings` | Tracked stocks and retention settings |

Do not spend three weeks making it beautiful. The frontend’s job is to make the data system visible.

### Main dashboard

```
MARKET INTELLIGENCE

Tracked     Avg 30D Return    Highest Risk
12               +5.8%            MU

──────────────────────────────────

Watchlist Performance

[1W] [1M] [3M] [1Y]

          [interactive chart]

──────────────────────────────────

Stock       Return    Volatility    Risk
NVDA       +12.8%       31.2%       63
AMD         +8.4%       37.7%       71
MU          -2.1%       42.0%       82
```

Watchlist-level analysis: performance, sector exposure, correlation matrix, best/worst performers, highest volatility, largest recent drawdown, unusual volume.

### Individual stock page

```
NVDA
NVIDIA Corporation

Price: $...
30D Return: ...
Volatility: ...
Risk Score: ...

[1M] [3M] [1Y]

PRICE CHART
──────────────

VOLUME CHART
──────────────

VOLATILITY
──────────────

RECENT EVENTS
──────────────
```

Per-stock metrics: 1D / 7D / 30D / 90D return, 30D rolling volatility, 30D / 90D moving average, volume vs rolling average, distance from 52-week high, maximum drawdown, correlation vs S&P 500 and vs other watched stocks.

### Compare page

Select stocks (checkboxes), then graph them together.

Frontend state to practice: selected stocks, date range, chart type, loading, errors, API results.

---

## Part 6 — ML / analytical scoring

Do **not** make “tomorrow NVDA will be $201.37” the centerpiece. That is noisy and can make a good project look naive.

### Unusual Movement Score

Question: based on recent behavior, is this stock entering an unusually high-activity period?

**Features**

- 7D return
- 30D return
- rolling volatility
- relative volume
- distance from MA
- market return
- news count
- sentiment

**Target**

```
large_move = 1 if abs(next_5_day_return) > threshold else 0
```

Then repeat Week 12 ML work:

```
pandas
↓
feature engineering
↓
X / y
↓
train / validation / test
↓
LogisticRegression
↓
Pipeline
↓
ColumnTransformer
↓
StandardScaler
↓
cross-validation
↓
accuracy / precision / recall / F1 / confusion matrix
↓
joblib.dump()
```

Then score the watchlist.

```
model_scores
------------------------
ticker
score_date
prediction
movement_probability
model_version
scored_at
```

### Alternative: anomaly score

Ask: is today’s behavior unusual relative to this company’s historical behavior? Variables: return, volume, volatility, news volume, sentiment. Rank the watchlist (e.g. MU 0.91, NVDA 0.84, AMD 0.63). This may fit the product even better.

### Visualize the ML too

**Confusion matrix** — generate with matplotlib.

**Probability distribution**

```
Number of samples
│       ███
│     █████
│    ███████
└────────────────→ Risk probability
0                  1
```

**Actual movement vs predicted score** — scatterplot.

**Feature importance / coefficient chart** (Logistic Regression)

```
relative volume       █████████
volatility            ███████
30d return            █████
news count            ███
```

Demonstrate: the classifier was trained **and** analyzed for why it behaves the way it does. That is particularly good DS practice.

---

## Part 7 — Historical compression + AI reporting

Detailed information has a lifecycle.

| Horizon | What to keep |
|---|---|
| Recent (0–30 days) | Detailed events. Hourly / intraday if available. |
| Older (31–365 days) | Daily summaries. Discard unnecessary high-frequency rows. |
| Historical (1+ year) | Weekly / monthly stock metrics, major events, aggregated sentiment, performance summaries |

Cold monthly rollup fields: month, opening_price, closing_price, high, low, avg_price, return, volatility, avg_volume, event_count, positive_news_count, negative_news_count.

```
possibly thousands of observations
           ↓
monthly rollup
           ↓
12 rows per year
```

Airflow DAG: `historical_compaction_dag`

```
old detailed data
       ↓
aggregate
       ↓
validate
       ↓
store historical summaries
       ↓
archive / delete unnecessary detail
```

The AI agent then queries the appropriate historical level:

- “What happened to NVIDIA yesterday?” → detailed data
- “What happened with NVIDIA during 2023?” → monthly / quarterly summaries

That is hierarchical historical memory. For old history the agent does not need 732 individual news items; it can retrieve January / February / March summaries. More interesting than indefinitely throwing everything into a vector DB.

### AI reporting layer

Only after the structured system exists.

```
user
↓
"Give me my weekly market report."
↓
agent
↓
get_watchlist_metrics()
get_top_movements()
get_unusual_activity()
get_recent_events()
get_model_scores()
↓
LLM
↓
grounded report
```

Agent tools (examples):

- `get_stock_metrics(ticker)`
- `get_price_history(ticker)`
- `get_recent_events(ticker)`
- `get_watchlist_summary()`
- `get_model_scores(ticker)`
- `compare_stocks(tickers)`
- `get_historical_report(ticker)`

The LLM does not randomly surf the internet. It asks the system for structured evidence, then writes the narrative.

Report shape:

```
WATCHLIST SUMMARY

Performance
───────────
...

Volatility
──────────
...

Unusual Activity
────────────────
...

Company Events
──────────────
...

Model Signals
─────────────
...

Things Worth Watching
─────────────────────
...
```

Report types:

- **Daily** — what moved today, what was unusual, major news/events, risk/anomaly scores
- **Weekly** — watchlist returns, major events, risk changes, correlations, winners/losers
- **Stock deep dive** — performance, volatility, volume, events, relative performance, ML score, historical context, AI narrative

Persist every report:

```
generated_reports
------------------------
report_id
report_type
ticker
created_at
model_version
report_text
```

The user generates reports from Next.js.

---

## FastAPI endpoints (full)

```
GET    /stocks/search?q=nvidia

GET    /watchlist
POST   /watchlist
DELETE /watchlist/{ticker}

GET    /stocks/{ticker}/prices
GET    /stocks/{ticker}/metrics
GET    /stocks/{ticker}/events

GET    /analytics/watchlist
GET    /analytics/correlations

POST   /reports/generate
GET    /reports/{id}

POST   /models/score/{ticker}

GET    /health
```

Pattern: route → service → data / model layer.

---

## Skills this reinforces

| What you studied | What you'll explicitly build |
|---|---|
| Python functions | ingestion / services / analytics |
| loops / collections | transformation utilities |
| JSON / CSV | financial data ingestion |
| pandas | cleaning / EDA / features |
| NumPy | financial calculations |
| SQL | database + analytics |
| joins | prices + events + fundamentals |
| CTEs | transformation queries |
| window functions | returns / MAs / rolling metrics |
| schemas | warehouse tables |
| indexes | stock / date lookup optimization |
| API requests | market / news ingestion |
| pipelines | extract → transform → load |
| incremental loads | daily market updates |
| idempotency | duplicate protection |
| logging | pipeline tracking |
| validation | data-quality checks |
| staging / marts | analytics warehouse |
| Airflow DAGs | scheduled pipelines |
| dependencies | ingestion → analytics |
| retries | provider / API failures |
| backfills | historical stock ingestion |
| pandas EDA | stock analysis |
| Matplotlib | price / volume / returns / volatility charts |
| Python visualization | EDA reports |
| metric design | financial KPIs |
| feature prep | model inputs |
| sklearn | movement classifier |
| CV | model evaluation |
| Pipeline | preprocess + classifier |
| joblib | save classifier |
| FastAPI | backend API |
| Pydantic | request validation |
| Next.js | dashboard |
| frontend HTTP | fetch analytics |
| loading / errors | dashboard states |
| debugging | trace complete application |

---

## Build order

The detailed slice-by-slice sequence is in [STEPS.md](STEPS.md). Do **not** start with the agent.

### Milestone 1

```
search stock
↓
add to watchlist
↓
backfill prices
↓
store in PostgreSQL
↓
calculate analytics
↓
show charts in Next.js
```

### Milestone 2

```
scheduled Airflow updates
↓
incremental ingestion
↓
data validation
↓
analytics marts
```

### Milestone 3

```
news / events ingestion
↓
join events with price behavior
↓
dashboard analysis
+ Python EDA visualizations
```

### Milestone 4

```
ML / anomaly scoring
↓
save trained Pipeline
↓
score tracked stocks
↓
ML evaluation charts
```

### Milestone 5

```
historical compaction
↓
weekly / monthly rollups
↓
retention policy
```

### Milestone 6

```
AI agent
↓
tools read your analytics
↓
generate grounded reports
```

That ordering matters because the impressive part is not “I made an AI stock agent.” There are thousands of those.

The impressive description becomes:

> Built an end-to-end market intelligence platform supporting configurable equity watchlists, historical backfills, incremental ingestion, Airflow orchestration, analytical marts, rolling financial metrics, Python EDA visualizations, anomaly scoring, tiered historical data retention, FastAPI services, and an interactive Next.js dashboard; added an LLM reporting layer grounded in structured system data.

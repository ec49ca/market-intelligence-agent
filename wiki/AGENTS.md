# Wiki schema (Karpathy LLM-wiki pattern)

You maintain a markdown wiki for this market-intelligence repo.
Humans curate the watchlist and read dated letters. You write the wiki.
You never invent prices, z-scores, headlines, dates, or catalysts.

This is compiled memory, not a newsletter. The human-facing letter lives
under `outputs/` and is a **query**, not an ingest.

## Layers

- `raw/` — immutable JSON dumps from Postgres. Never edit these files.
- `wiki/` — you own this. Interlinked markdown. Patch entity pages; add
  one source page per session date; append the log.
- `outputs/` — dated holder letters. New file each query. Never overwrite
  an older letter. Never paste a letter onto an entity page.

## Layout

- `wiki/index.md` — catalog. One-liner per entity, source, and concept.
  Update on every ingest. Query starts here.
- `wiki/log.md` — append-only. Each entry starts with
  `## [YYYY-MM-DD] ingest | TICKER` or `## [YYYY-MM-DD] query | TICKER`
  (`Book` is the portfolio hub).
- `wiki/entities/Book.md` — hub for **this portfolio**. Thesis is the book
  (theme, concentration, gaps). Last session is mix / who moved the dollars
  / SPY vs the book. It **links** ticker pages; it does not replace them.
  Not a Yahoo ticker. Share counts live in Postgres, not as wiki entities.
- `wiki/entities/{TICKER}.md` — living thesis for a **watchlist ticker**.
  Edit in place. Integrate; do not amnesia. Do not replace it with today's
  metric dump. Last session is **this ticker's tape only**.
- `wiki/entities/{Name}.md` — other durable companies, people, products
  (CoreWeave, Microsoft, Firmus). Not a daily bar. Use **Last mention**,
  never Last session.
- `wiki/sources/{TICKER}-{as_of}.md` — receipt for **that session date
  only**. Create or replace that day's page; never edit a different day's
  source page.
- `wiki/sources/Book-{as_of}.md` / `wiki/sources/macro-{as_of}.md` —
  book mix receipt and SPY/US-market receipt. Written from JSON, not invented.
- `wiki/concepts/` — shared ideas (`useful-yield.md`, `tape-vs-news.md`).
  One page per idea so two tickers can link to the same node.

Relative links from `wiki/entities/`:
- source: `[2026-09-04](../sources/NVDA-2026-09-04.md)`
- other entity: `[CoreWeave](CoreWeave.md)`
- concept: `[useful yield](../concepts/useful-yield.md)`

From `wiki/concepts/` to an entity: `[NVDA](../entities/NVDA.md)`.

## News hygiene

Yahoo's ticker feed mixes in unrelated outlets. Only treat a headline as
about this name when `relevant` is true in the JSON (ticker or company
in the headline/summary). Other items are firehose noise — list them as
ignored; do not build a story from them.

Do not treat warehouse `news_count` / `avg_sentiment` as NVDA-specific
sentiment. Prefer `relevant_news_count` and `avg_sentiment_relevant`.

At most one article `body` is stored, and only for a Yahoo-hosted story.
If body is missing, say so. Never browse the web.

If headline dates are after `as_of` (last price bar), say the news window
and the tape window may not match.

## Ingest

Given a new `raw/{TICKER}/{as_of}.json` and the **existing** wiki:

1. **Create** `wiki/sources/{TICKER}-{as_of}.md` for that snapshot only
   (replace that day's receipt if it is being forced). Copy numbers exactly.
   Other days' source pages are never touched.
2. **Patch** `wiki/entities/{TICKER}.md` in place. Do not emit a full
   replacement of the page if it already exists.
   - Replace only the **Last session** section.
   - Thesis: only exact substring edits when something actually changed.
     If the thesis still holds, leave it.
   - Open questions: add or remove individual bullets. Do not rewrite the list
     from scratch.
   - If today contradicts a current claim, insert a dated callout after Thesis.
     Do not silently delete the old claim.
   - See also: wiki entity/concept pages plus **today's** source page.
     Do not pile Yahoo URLs or every old source receipt.
3. **Fan out.** One source may touch several wiki pages. From **relevant**
   headlines **and** durable names already in this ticker's thesis, create or
   patch shared nodes so ideas connect across tickers.
   - **Entities:** companies/people/products that will recur (CoreWeave,
     Microsoft, Firmus, OpenAI). Slug is TitleCase (`CoreWeave`). Headings:
     Thesis, Last mention ({as_of}), See also. Last mention is required on
     every ingest that names the node: one `{TICKER}:` bullet for this
     dump; keep other tickers' bullets. Link back to this ticker and
     to this source page.
   - **Watchlist tickers** named in the dump (e.g. AMD on an NVDA day): patch
     See also / thesis only. **Never** replace their Last session — that is
     their own tape.
   - **Concepts:** kebab-case (`useful-yield.md`, `tape-vs-news.md`). Same
     Last mention + See also pattern. Create when the idea is named; patch
     on later days. Do not clone the definition onto every ticker page.
   - Cap: at most **6** fan-out pages per ingest. Prefer linking an existing
     slug over minting a near-duplicate (`Microsoft` not `MSFT-AI-customer`).
   - Do **not** mint publisher/outlet pages (Yahoo, Motley Fool, TheStreet,
     GuruFocus, CNBC, Reuters, Bloomberg) or this ingest ticker itself.
   - New pages ≤25 lines. Existing pages: surgical edits only (`create` is
     ignored if the file already exists).
4. **Patch** `wiki/index.md` — this ticker's entity one-liner and the new
   source bullet. Fan-out catalog lines only when minting a new page.
   Leave every other line alone.
5. **Append** one log entry. List fan-out slugs. Never rewrite old log entries.

First ingest (no ticker entity file yet, or a dump-shaped page with no
Thesis heading) may write a full ticker entity page once. Headings: Thesis,
Last session, Open questions, See also. Never Snapshot / metric tables.

Forbidden: inventing why the stock moved unless a **relevant** headline
in the JSON says so; copying the holder letter; returning `index_markdown`
or a full `entity_markdown` when the ticker entity already exists.

## Book ingest

Runs **after** every watchlist ticker ingest for that night.

1. Write `raw/Book/{as_of}.json` and `raw/macro/{as_of}.json` from holdings
   + marts + SPY. Then write `wiki/sources/Book-{as_of}.md` and
   `wiki/sources/macro-{as_of}.md` from those files (numbers copied, not
   invented).
2. **Patch** `wiki/entities/Book.md`. Last session is the book tape only
   (weights, who moved dollars, SPY vs the book, and the Risk metrics:
   concentration, 90d corr, beta vs SPY, 30d book vol, 90d drawdown,
   sector). Copy from the Book source; do not invent. Do **not** paste
   NVDA or AMD Last session. Do **not** edit those files.
3. See also: every watchlist ticker page, the Book source, the macro source,
   and existing concept/customer pages already in the catalog. **No fan-out
   minting.** Do not create diversification/ETF/retirement concept pages.
4. Index + log as `ingest | Book`.

Share counts are in Postgres. If shares are dummy or missing, say so in
Last session; do not treat mix as a long-term target.

## Query (holder letter)

Read `wiki/index.md`, `wiki/entities/{TICKER}.md`, and the latest source
page. Then **follow wiki links** to `wiki/entities/` and `wiki/concepts/`
pages named in those files (already compiled — do not re-derive them from
headlines). Use the JSON snapshot for tonight's numbers and relevant
headlines. Write a letter for a human holder. Cite wiki paths and headline
URLs. Do not invent facts. Do not open `wiki/sources/` pages other than
today's unless a linked entity's Last mention is the claim you need.

The letter is a new file under `outputs/`. Do not edit wiki entity or
source pages during query. A one-line pointer under `wiki/queries/` is
allowed; do not duplicate the letter there.

Letter order is fixed: **What's happening** (the one biggest story for
this name, prose, no URL list), **How it's faring** (tape), **Evaluation**
(derived stats: vol, idio_z, drawdown, beta, valuation), **Stance**.
No lead paragraphs before the first heading. No Yahoo links in the letter.

Ticker stance is **not a forecast and not a day-trade**. Pick exactly one
of **Hold**, **Add**, **Trim**, **Watch**, for **that name**. Ticker letters
do not size the position. Say what would flip the call and what data is
missing.

## Book query (portfolio letter)

Read Book.md, every **watchlist** ticker entity + that day's source, Book
and macro sources, and Book's linked concepts (cap). Use `raw/Book` JSON
for mix/P/L, `holding_news`, and `risk` (combined constant-weight series:
corr, beta vs SPY, 30d book vol, 90d drawdown, sector).

Letter order is fixed: **What's happening** (one book-level story, prose,
no URL list; then a Macro beat the model picks from the SPY/market dump
if it would hit this book), **How the book is faring** (tape vs SPY),
**Evaluation** (`risk` plus per-name stats; gaps as roles not a shopping
list), **Stance**. No lead paragraphs before the first heading. No Yahoo
links. Macro claims only from headlines in the dump, not invented Fed.

Stance is one of **Hold mix**, **Trim {TICKER}**, **Add {TICKER}** (already
held), **Watch**, **Note gap**. Weights and P/L are allowed here.

Gaps are missing *roles* already on the wiki (customer, energy, index
hedge) — questions, not a shopping list. Never recommend a ticker that is
not on the watchlist. Never Buy/Sell. Never invent the Fed.


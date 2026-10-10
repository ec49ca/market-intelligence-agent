"use client";

import {
  CSSProperties,
  FormEvent,
  ReactNode,
  useEffect,
  useState,
} from "react";
import BookIntel, { type BookSnapshot } from "./BookIntel";
import PortfolioCharts from "./PortfolioCharts";
import { SignedText, asNum } from "./signed";
import WikiGraphModal from "./WikiGraphModal";

const API = "http://127.0.0.1:8000";

type StockMatch = {
  ticker: string;
  company_name: string;
};

type PriceBar = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  prev_close?: number | null;
  daily_return?: number | null;
  ma_30d?: number | null;
};

type ReturnRow = {
  date: string;
  prev_close: number | null;
  daily_return: number | null;
};

type MaRow = {
  date: string;
  ma_30d: number | null;
};

function dateKey(value: string) {
  return String(value).slice(0, 10);
}

function formatPct(value: number | string | null | undefined) {
  if (value == null || value === "") return "—";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function SignedPct({
  value,
}: {
  value: number | string | null | undefined;
}) {
  if (value == null || value === "") return "—";
  return <SignedText value={value}>{formatPct(value)}</SignedText>;
}

function SignedUsd({
  value,
}: {
  value: number | string | null | undefined;
}) {
  const amount = asNum(value);
  if (amount == null) return "—";
  const body = formatUsd(Math.abs(amount));
  const text =
    amount > 0 ? `+${body}` : amount < 0 ? `−${body}` : body;
  return <SignedText value={amount}>{text}</SignedText>;
}

function formatMultiple(value: number | string | null | undefined) {
  if (value == null || value === "") return "—";
  return `${Number(value).toFixed(2)}×`;
}

function formatUsd(value: number | string | null | undefined) {
  if (value == null || value === "") return "—";
  const amount = Number(value);
  return amount.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: amount >= 1000 ? 0 : 2,
  });
}

function formatCap(value: number | string | null | undefined) {
  if (value == null || value === "") return "—";
  const amount = Number(value);
  if (amount >= 1e12) return `$${(amount / 1e12).toFixed(2)}T`;
  if (amount >= 1e9) return `$${(amount / 1e9).toFixed(2)}B`;
  if (amount >= 1e6) return `$${(amount / 1e6).toFixed(2)}M`;
  return `$${amount.toFixed(0)}`;
}

function formatNum(value: number | string | null | undefined, digits = 1) {
  if (value == null || value === "") return "—";
  return Number(value).toFixed(digits);
}

function formatSentiment(value: number | string | null | undefined) {
  if (value == null || value === "") return "—";
  const score = Number(value);
  const sign = score > 0 ? "+" : "";
  return `${sign}${score.toFixed(2)}`;
}

function SignedSentiment({
  value,
}: {
  value: number | string | null | undefined;
}) {
  if (value == null || value === "") return "—";
  return <SignedText value={value}>{formatSentiment(value)}</SignedText>;
}

function formatZ(value: number | string | null | undefined) {
  if (value == null || value === "") return "—";
  const z = Number(value);
  const sign = z > 0 ? "+" : "";
  return `${sign}${z.toFixed(2)}σ`;
}

function SignedZ({
  value,
}: {
  value: number | string | null | undefined;
}) {
  if (value == null || value === "") return "—";
  return <SignedText value={value}>{formatZ(value)}</SignedText>;
}

function formatInline(text: string) {
  const nodes: ReactNode[] = [];
  const pattern =
    /\*\*(.+?)\*\*|\[([^\]]+)\]\((https?:[^)\s]+|wiki\/[^)\s]+)\)/g;
  let last = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text))) {
    if (match.index > last) {
      nodes.push(text.slice(last, match.index));
    }
    if (match[1]) {
      nodes.push(<strong key={key}>{match[1]}</strong>);
    } else if (match[3]?.startsWith("http")) {
      nodes.push(
        <a key={key} href={match[3]} target="_blank" rel="noreferrer">
          {match[2]}
        </a>
      );
    } else {
      nodes.push(match[2] ?? match[0]);
    }
    key += 1;
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    nodes.push(text.slice(last));
  }
  return nodes;
}

function BriefingBody({ text }: { text: string }) {
  const cleaned = text.replace(/^<!--[\s\S]*?-->\s*/, "").trim();
  const normalized = cleaned
    .replace(/^(#{1,3}\s+.+)$/gm, "\n\n$1\n\n")
    .replace(/\n{3,}/g, "\n\n");
  const blocks = normalized.split(/\n{2,}/).filter((block) => {
    const start = block.trim();
    if (/^###\s+Ignored/i.test(start)) return false;
    if (/^-\s+wiki\//i.test(start) && !start.includes("http")) return false;
    return start.length > 0;
  });
  return (
    <div style={{ maxWidth: 680, lineHeight: 1.55 }}>
      {blocks.map((block, index) => {
        const trimmed = block.trim();
        if (trimmed.startsWith("# ")) {
          return <h3 key={index}>{formatInline(trimmed.slice(2))}</h3>;
        }
        if (trimmed.startsWith("### ")) {
          return (
            <h4 key={index} style={{ fontSize: 14, marginBottom: 0 }}>
              {formatInline(trimmed.slice(4))}
            </h4>
          );
        }
        if (trimmed.startsWith("## ")) {
          return <h4 key={index}>{formatInline(trimmed.slice(3))}</h4>;
        }
        const lines = trimmed.split("\n").filter((line) => line.trim());
        if (lines.every((line) => line.trim().startsWith("- "))) {
          const items = lines.filter(
            (line) => !/^\s*-\s+`?wiki\//i.test(line)
          );
          if (items.length === 0) return null;
          return (
            <ul key={index} style={{ paddingLeft: "1.2em" }}>
              {items.map((line) => (
                <li key={line}>{formatInline(line.replace(/^\s*-\s+/, ""))}</li>
              ))}
            </ul>
          );
        }
        return <p key={index}>{formatInline(trimmed.replace(/\n/g, " "))}</p>;
      })}
    </div>
  );
}

const STOCK_CHARTS = [
  {
    path: "",
    title: "Close vs 30-day moving average",
    blurb:
      "Daily closing price (blue) and the average close over the last ~30 sessions (orange). The MA is smoother; price above it is recent strength, below is weakness.",
  },
  {
    path: "/volume",
    title: "Trading volume",
    blurb:
      "Shares traded each day. Spikes often line up with big news or large moves. Later this feeds “unusual volume” in ML.",
  },
  {
    path: "/returns",
    title: "Daily return distribution",
    blurb:
      "How often each size of day-to-day percent change happens. The pile around 0 is a typical day; the tails are crashes and squeezes.",
  },
  {
    path: "/drawdown",
    title: "Drawdown from peak",
    blurb:
      "How far close sits below its running high. 0% is at an all-time high in this window; −20% means a 20% drop from the peak.",
  },
];

function PaneToggle({
  value,
  onChange,
}: {
  value: "overview" | "news";
  onChange: (pane: "overview" | "news") => void;
}) {
  const tab = (id: "overview" | "news", label: string) => (
    <button
      type="button"
      role="tab"
      aria-selected={value === id}
      onClick={() => onChange(id)}
      style={{
        border: "none",
        background: value === id ? "#111" : "#fff",
        color: value === id ? "#fff" : "#111",
        padding: "6px 14px",
        cursor: "pointer",
        font: "inherit",
        fontSize: 13,
      }}
    >
      {label}
    </button>
  );
  return (
    <div
      role="tablist"
      aria-label="Overview or news"
      style={{ display: "inline-flex", border: "1px solid #ccc" }}
    >
      {tab("overview", "Overview")}
      {tab("news", "News")}
    </div>
  );
}

const paneBox: CSSProperties = {
  flex: "0 0 50%",
  width: "50%",
  minWidth: 0,
  height: "100%",
  overflow: "auto",
  boxSizing: "border-box",
};

function SplitView({
  title,
  pane,
  onPane,
  overview,
  news,
}: {
  title: ReactNode;
  pane: "overview" | "news";
  onPane: (next: "overview" | "news") => void;
  overview: ReactNode;
  news: ReactNode;
}) {
  return (
    <>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          flexShrink: 0,
          marginBottom: 12,
        }}
      >
        {title}
        <PaneToggle value={pane} onChange={onPane} />
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
        <div
          style={{
            display: "flex",
            width: "200%",
            height: "100%",
            transform: pane === "news" ? "translateX(-50%)" : "translateX(0)",
            transition: "transform 0.28s ease",
          }}
        >
          <div style={{ ...paneBox, paddingRight: 8 }}>{overview}</div>
          <div role="tabpanel" style={{ ...paneBox, paddingLeft: 8 }}>
            {news}
          </div>
        </div>
      </div>
    </>
  );
}

const navBtn = (active: boolean): CSSProperties => ({
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 8,
  width: "100%",
  textAlign: "left",
  border: "none",
  background: active ? "#eee" : "transparent",
  color: "#111",
  padding: "8px 12px",
  cursor: "pointer",
  font: "inherit",
});

type TrackedStock = {
  ticker: string;
  company_name: string;
  added_at: string;
  active: boolean;
  backfill_start_date: string | null;
  as_of?: string | null;
  daily_return?: number | string | null;
  volume_ratio?: number | string | null;
  vol_30d?: number | string | null;
  return_30d?: number | string | null;
  drawdown?: number | string | null;
  pe?: number | string | null;
  market_cap?: number | string | null;
  momentum_12_1?: number | string | null;
  beta_60d?: number | string | null;
  return_on_equity?: number | string | null;
  debt_to_cap?: number | string | null;
  news_count?: number | null;
  avg_sentiment?: number | string | null;
  idio_z?: number | string | null;
  anomaly_score?: number | string | null;
  tape_news?: string | null;
  vol_regime?: string | null;
  shares?: number | string | null;
  close?: number | string | null;
  market_value?: number | string | null;
  weight?: number | string | null;
  cost_per_share?: number | string | null;
  default_cost?: number | string | null;
  default_cost_as_of?: string | null;
  display_cost?: number | string | null;
  cost_basis?: number | string | null;
  unrealized?: number | string | null;
  unrealized_pct?: number | string | null;
};

function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "#555" }}>{label}</div>
      <div>{value}</div>
    </div>
  );
}

export default function WatchlistPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<StockMatch[]>([]);
  const [customDate, setCustomDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [watchlist, setWatchlist] = useState<TrackedStock[]>([]);
  const [editingTicker, setEditingTicker] = useState<string | null>(null);
  const [editDate, setEditDate] = useState("");
  const [shareDrafts, setShareDrafts] = useState<Record<string, string>>({});
  const [costDrafts, setCostDrafts] = useState<Record<string, string>>({});
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);
  const [chartSlide, setChartSlide] = useState(0);
  const [bookPane, setBookPane] = useState<"overview" | "news">("overview");
  const [tickerPane, setTickerPane] = useState<"overview" | "news">("overview");
  const [bookSnapshot, setBookSnapshot] = useState<BookSnapshot | null>(null);
  const [prices, setPrices] = useState<PriceBar[]>([]);
  const [reports, setReports] = useState<{ filename: string; preview: string }[]>(
    []
  );
  const [reportText, setReportText] = useState<string | null>(null);
  const [activeReport, setActiveReport] = useState<string | null>(null);

  const trackedTickers = new Set(watchlist.map((stock) => stock.ticker));
  const selected = watchlist.find((stock) => stock.ticker === selectedTicker);

  async function loadWatchlist() {
    const response = await fetch(`${API}/watchlist`);
    if (!response.ok) {
      throw new Error(`Watchlist failed: ${response.status}`);
    }
    const data: TrackedStock[] = await response.json();
    setWatchlist(data);
    try {
      const bookResponse = await fetch(`${API}/book`);
      if (bookResponse.ok) {
        setBookSnapshot(await bookResponse.json());
      }
    } catch {
      setBookSnapshot(null);
    }
  }

  useEffect(() => {
    loadWatchlist().catch((err) => {
      setError(err instanceof Error ? err.message : "Unknown error");
    });
  }, []);

  async function loadBookLetter() {
    const listResponse = await fetch(`${API}/book/reports`);
    if (!listResponse.ok) {
      throw new Error(`Book letters failed: ${listResponse.status}`);
    }
    const reportList = await listResponse.json();
    setReports(reportList);
    if (reportList.length === 0) {
      setReportText(null);
      setActiveReport(null);
      return;
    }
    const latest = reportList[0].filename as string;
    const fileResponse = await fetch(
      `${API}/book/reports/${encodeURIComponent(latest)}`
    );
    if (fileResponse.ok) {
      const file = await fileResponse.json();
      setReportText(file.markdown);
      setActiveReport(latest);
    } else {
      setReportText(null);
      setActiveReport(null);
    }
  }

  useEffect(() => {
    if (selectedTicker != null) {
      return;
    }
    loadBookLetter().catch((err) => {
      setError(err instanceof Error ? err.message : "Unknown error");
    });
  }, [selectedTicker]);

  function clearTickerView() {
    setSelectedTicker(null);
    setPrices([]);
    setChartSlide(0);
    setReports([]);
    setReportText(null);
    setActiveReport(null);
    setEditingTicker(null);
    setTickerPane("overview");
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const response = await fetch(
        `${API}/stocks/search?q=${encodeURIComponent(query)}`
      );
      if (!response.ok) {
        throw new Error(`Search failed: ${response.status}`);
      }
      const data: StockMatch[] = await response.json();
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function handleAdd(stock: StockMatch) {
    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const response = await fetch(`${API}/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          customDate
            ? {
                ticker: stock.ticker,
                company_name: stock.company_name,
                backfill_start_date: customDate,
              }
            : {
                ticker: stock.ticker,
                company_name: stock.company_name,
              }
        ),
      });
      if (!response.ok) {
        throw new Error(`Add failed: ${response.status}`);
      }
      const added = await response.json();
      setMessage(
        `Added ${stock.ticker} (${added.prices_upserted ?? 0} price days)`
      );
      setQuery("");
      setResults([]);
      setCustomDate("");
      setAdding(false);
      await loadWatchlist();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function selectTicker(ticker: string) {
    if (selectedTicker === ticker) {
      return;
    }
    setAdding(false);
    setError(null);
    setTickerPane("overview");
    const encoded = encodeURIComponent(ticker);
    const [priceResponse, returnResponse, maResponse, reportsResponse] =
      await Promise.all([
        fetch(`${API}/stocks/${encoded}/prices`),
        fetch(`${API}/stocks/${encoded}/returns`),
        fetch(`${API}/stocks/${encoded}/ma`),
        fetch(`${API}/stocks/${encoded}/reports`),
      ]);
    if (!priceResponse.ok) {
      setError(`Prices failed: ${priceResponse.status}`);
      return;
    }
    if (!returnResponse.ok) {
      setError(`Returns failed: ${returnResponse.status}`);
      return;
    }
    if (!maResponse.ok) {
      setError(`MA failed: ${maResponse.status}`);
      return;
    }
    const priceData: PriceBar[] = await priceResponse.json();
    const returnData: ReturnRow[] = await returnResponse.json();
    const maData: MaRow[] = await maResponse.json();
    const reportList = reportsResponse.ok ? await reportsResponse.json() : [];
    setReports(reportList);
    if (reportList.length > 0) {
      const latest = reportList[0].filename as string;
      const fileResponse = await fetch(
        `${API}/stocks/${encoded}/reports/${encodeURIComponent(latest)}`
      );
      if (fileResponse.ok) {
        const file = await fileResponse.json();
        setReportText(file.markdown);
        setActiveReport(latest);
      } else {
        setReportText(null);
        setActiveReport(null);
      }
    } else {
      setReportText(null);
      setActiveReport(null);
    }
    const returnsByDate = new Map(
      returnData.map((row) => [dateKey(row.date), row])
    );
    const maByDate = new Map(maData.map((row) => [dateKey(row.date), row]));
    setPrices(
      priceData.map((bar) => {
        const metrics = returnsByDate.get(dateKey(bar.date));
        const ma = maByDate.get(dateKey(bar.date));
        return {
          ...bar,
          prev_close: metrics?.prev_close ?? null,
          daily_return: metrics?.daily_return ?? null,
          ma_30d: ma?.ma_30d ?? null,
        };
      })
    );
    setSelectedTicker(ticker);
    setChartSlide(0);
  }

  async function handleGenerateBookReport() {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${API}/book/reports`, { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || `Book letter failed: ${response.status}`);
      }
      setMessage("Updated today’s book letter");
      const listResponse = await fetch(`${API}/book/reports`);
      if (listResponse.ok) {
        setReports(await listResponse.json());
      }
      const fileResponse = await fetch(
        `${API}/book/reports/${encodeURIComponent(payload.filename)}`
      );
      if (fileResponse.ok) {
        const file = await fileResponse.json();
        setReportText(file.markdown);
        setActiveReport(payload.filename);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function handleOpenBookReport(filename: string) {
    setError(null);
    const response = await fetch(
      `${API}/book/reports/${encodeURIComponent(filename)}`
    );
    if (!response.ok) {
      setError(`Report failed: ${response.status}`);
      return;
    }
    const file = await response.json();
    setReportText(file.markdown);
    setActiveReport(filename);
  }

  async function handleGenerateReport(ticker: string) {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const encoded = encodeURIComponent(ticker);
      const response = await fetch(`${API}/stocks/${encoded}/reports`, {
        method: "POST",
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || `Report failed: ${response.status}`);
      }
      setMessage("Updated today’s briefing");
      const listResponse = await fetch(`${API}/stocks/${encoded}/reports`);
      if (listResponse.ok) {
        setReports(await listResponse.json());
      }
      const fileResponse = await fetch(
        `${API}/stocks/${encoded}/reports/${encodeURIComponent(payload.filename)}`
      );
      if (fileResponse.ok) {
        const file = await fileResponse.json();
        setReportText(file.markdown);
        setActiveReport(payload.filename);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function handleOpenReport(ticker: string, filename: string) {
    setError(null);
    const encoded = encodeURIComponent(ticker);
    const response = await fetch(
      `${API}/stocks/${encoded}/reports/${encodeURIComponent(filename)}`
    );
    if (!response.ok) {
      setError(`Report failed: ${response.status}`);
      return;
    }
    const file = await response.json();
    setReportText(file.markdown);
    setActiveReport(filename);
  }

  async function handleSaveHoldings(
    ticker: string,
    sharesRaw?: string,
    costRaw?: string
  ) {
    const stock = watchlist.find((row) => row.ticker === ticker);
    const sharesText = (sharesRaw ?? shareDrafts[ticker] ?? "").trim();
    const shares = sharesText === "" ? 0 : Number(sharesText);
    const costText = (costRaw ?? costDrafts[ticker] ?? "").trim();
    const cost =
      costText === ""
        ? stock?.display_cost == null
          ? null
          : Number(stock.display_cost)
        : Number(costText);
    if (Number.isNaN(shares) || shares < 0) {
      setError("Shares must be a number ≥ 0");
      return;
    }
    if (cost != null && (Number.isNaN(cost) || cost < 0)) {
      setError("Approx cost must be a number ≥ 0");
      return;
    }
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(
        `${API}/holdings/${encodeURIComponent(ticker)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            shares,
            cost_per_share: cost,
          }),
        }
      );
      if (!response.ok) {
        throw new Error(`Holdings failed: ${response.status}`);
      }
      setShareDrafts((prev) => {
        const next = { ...prev };
        delete next[ticker];
        return next;
      });
      setCostDrafts((prev) => {
        const next = { ...prev };
        delete next[ticker];
        return next;
      });
      await loadWatchlist();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(ticker: string) {
    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const response = await fetch(
        `${API}/watchlist/${encodeURIComponent(ticker)}`,
        { method: "DELETE" }
      );
      if (!response.ok) {
        throw new Error(`Delete failed: ${response.status}`);
      }
      setMessage(`Removed ${ticker}`);
      if (selectedTicker === ticker) {
        clearTickerView();
      }
      await loadWatchlist();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveEdit(ticker: string) {
    if (!editDate) {
      setError("Pick a start date to save");
      return;
    }

    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const response = await fetch(
        `${API}/watchlist/${encodeURIComponent(ticker)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ backfill_start_date: editDate }),
        }
      );
      if (!response.ok) {
        throw new Error(`Update failed: ${response.status}`);
      }
      const updated = await response.json();
      setMessage(
        `Updated ${ticker} (${updated.prices_upserted ?? 0} price days)`
      );
      setEditingTicker(null);
      await loadWatchlist();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  function holdingsForm(stock: TrackedStock) {
    return (
      <form
        style={{
          display: "flex",
          gap: 4,
          alignItems: "center",
          flexWrap: "nowrap",
        }}
        onSubmit={(event) => {
          event.preventDefault();
          const form = event.currentTarget;
          const sharesField = form.elements.namedItem("shares") as
            | HTMLInputElement
            | null;
          const costField = form.elements.namedItem("cost") as
            | HTMLInputElement
            | null;
          handleSaveHoldings(
            stock.ticker,
            sharesField?.value ?? "",
            costField?.value ?? ""
          );
        }}
      >
        <input
          name="shares"
          type="number"
          min={0}
          step="any"
          style={{ width: 72 }}
          aria-label={`${stock.ticker} shares`}
          value={
            shareDrafts[stock.ticker] ??
            (stock.shares == null || Number(stock.shares) === 0
              ? ""
              : String(stock.shares))
          }
          onChange={(event) =>
            setShareDrafts((prev) => ({
              ...prev,
              [stock.ticker]: event.target.value,
            }))
          }
        />
        <input
          name="cost"
          type="number"
          min={0}
          step="any"
          style={{ width: 88 }}
          aria-label={`${stock.ticker} approx cost`}
          title={
            stock.default_cost_as_of
              ? `Defaults to close on ${String(stock.default_cost_as_of).slice(0, 10)} (watchlist add)`
              : "Approx cost per share when bought"
          }
          placeholder={
            stock.display_cost == null
              ? "cost"
              : String(Number(stock.display_cost).toFixed(2))
          }
          value={
            costDrafts[stock.ticker] ??
            (stock.cost_per_share == null ? "" : String(stock.cost_per_share))
          }
          onChange={(event) =>
            setCostDrafts((prev) => ({
              ...prev,
              [stock.ticker]: event.target.value,
            }))
          }
        />
        <button type="submit" disabled={loading}>
          Save
        </button>
      </form>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        minHeight: 0,
      }}
    >
      <aside
        style={{
          width: 220,
          flexShrink: 0,
          borderRight: "1px solid #ddd",
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
            padding: "16px 12px 8px",
          }}
        >
          <strong>Market Intelligence</strong>
          <button
            type="button"
            aria-label={adding ? "Close add stock" : "Add stock"}
            title="Add a name"
            onClick={() => {
              setAdding((open) => !open);
              setResults([]);
              setQuery("");
            }}
            style={{
              width: 28,
              height: 28,
              padding: 0,
              border: "1px solid #ccc",
              background: adding ? "#eee" : "#fff",
              color: "#111",
              cursor: "pointer",
              font: "inherit",
              fontSize: 18,
              lineHeight: "26px",
            }}
          >
            +
          </button>
        </div>
        {adding ? (
          <div style={{ padding: "0 12px 12px", fontSize: 13 }}>
            <form onSubmit={handleSearch}>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search (e.g. nvidia)"
                style={{ width: "100%", boxSizing: "border-box" }}
              />
              <button type="submit" disabled={loading} style={{ marginTop: 6 }}>
                {loading ? "Working..." : "Search"}
              </button>
            </form>
            <p style={{ margin: "8px 0 4px", color: "#555" }}>
              Optional start date
            </p>
            <input
              type="date"
              value={customDate}
              onChange={(event) => setCustomDate(event.target.value)}
              style={{ width: "100%", boxSizing: "border-box" }}
            />
            <ul style={{ paddingLeft: 16, margin: "8px 0 0" }}>
              {results.map((stock) => (
                <li key={stock.ticker} style={{ marginBottom: 6 }}>
                  {stock.ticker}
                  <div style={{ color: "#555" }}>{stock.company_name}</div>
                  {trackedTickers.has(stock.ticker) ? (
                    <span>Already tracked</span>
                  ) : (
                    <button
                      type="button"
                      disabled={loading}
                      onClick={() => handleAdd(stock)}
                    >
                      Add
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <nav style={{ flex: 1, overflow: "auto" }}>
          <button
            type="button"
            style={navBtn(selectedTicker == null)}
            onClick={clearTickerView}
          >
            Book
          </button>
          <button
            type="button"
            style={navBtn(false)}
            onClick={() => setGraphOpen(true)}
          >
            Wiki graph
          </button>
          {watchlist.map((stock) => (
            <button
              key={stock.ticker}
              type="button"
              style={navBtn(selectedTicker === stock.ticker)}
              onClick={() => selectTicker(stock.ticker)}
            >
              <span>{stock.ticker}</span>
              {stock.daily_return != null ? (
                <span style={{ fontSize: 12 }}>
                  <SignedPct value={stock.daily_return} />
                </span>
              ) : stock.weight != null ? (
                <span style={{ color: "#555", fontSize: 12 }}>
                  {formatPct(stock.weight)}
                </span>
              ) : null}
            </button>
          ))}
        </nav>
      </aside>

      {graphOpen ? (
        <WikiGraphModal
          onClose={() => setGraphOpen(false)}
          onOpenTicker={(ticker) => {
            setGraphOpen(false);
            selectTicker(ticker);
          }}
        />
      ) : null}

      <main
        style={{
          flex: 1,
          minWidth: 0,
          minHeight: 0,
          overflow: "hidden",
          padding: "16px 24px 20px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {error && <p>Error: {error}</p>}
        {message && <p>{message}</p>}

        {selectedTicker == null || !selected ? (
          <SplitView
            pane={bookPane}
            onPane={setBookPane}
            title={<h1 style={{ margin: 0 }}>Book</h1>}
            overview={
              <>
                <PortfolioCharts rows={watchlist} />
                <BookIntel snapshot={bookSnapshot} />
                <div style={{ flexShrink: 0, marginTop: 12 }}>
                  <h2 style={{ margin: "0 0 6px", fontSize: 15 }}>
                    Positions
                  </h2>
                  <div style={{ overflow: "auto" }}>
                    <table
                      style={{
                        width: "100%",
                        fontSize: 13,
                        whiteSpace: "nowrap",
                      }}
                    >
                      <thead>
                        <tr>
                          <th>Ticker</th>
                          <th>Shares / cost</th>
                          <th>Value</th>
                          <th>Weight</th>
                          <th>P/L</th>
                        </tr>
                      </thead>
                      <tbody>
                        {watchlist.map((stock) => (
                          <tr key={stock.ticker}>
                            <td>
                              <button
                                type="button"
                                onClick={() => selectTicker(stock.ticker)}
                              >
                                {stock.ticker}
                              </button>
                            </td>
                            <td>{holdingsForm(stock)}</td>
                            <td>{formatUsd(stock.market_value)}</td>
                            <td>{formatPct(stock.weight)}</td>
                            <td>
                              {stock.unrealized == null ? (
                                "—"
                              ) : (
                                <>
                                  <SignedUsd value={stock.unrealized} /> (
                                  <SignedPct value={stock.unrealized_pct} />)
                                </>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            }
            news={
              <>
                <h2 style={{ marginTop: 0 }}>Today’s book letter</h2>
                {reportText ? (
                  <BriefingBody text={reportText} />
                ) : (
                  <p>
                    No book letter yet. Write one after the names have wiki
                    pages — mix, SPY, and gaps, not a stock-pick list.
                  </p>
                )}
                <p>
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => handleGenerateBookReport()}
                  >
                    {loading
                      ? "Working..."
                      : reportText
                        ? "Refresh book letter"
                        : "Write today’s book letter"}
                  </button>
                </p>
                {reports.length > 1 ? (
                  <details>
                    <summary>Earlier book letters</summary>
                    <ul>
                      {reports.map((item) => (
                        <li key={item.filename}>
                          <button
                            type="button"
                            onClick={() => handleOpenBookReport(item.filename)}
                          >
                            {item.filename}
                            {item.filename === activeReport ? " (open)" : ""}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </>
            }
          />
        ) : (
          <SplitView
            pane={tickerPane}
            onPane={setTickerPane}
            title={
              <h1 style={{ margin: 0 }}>
                {selected.ticker}{" "}
                <span style={{ fontWeight: 400, color: "#555" }}>
                  {selected.company_name}
                </span>
              </h1>
            }
            overview={
              <>
            <p>
              {formatUsd(selected.close)} last close{" "}
              <SignedPct value={selected.daily_return} />
              {selected.as_of
                ? ` · ${dateKey(String(selected.as_of))}`
                : ""}
              {selected.weight != null
                ? ` · ${formatPct(selected.weight)} of book`
                : ""}
            </p>
            <div style={{ marginBottom: 16 }}>{holdingsForm(selected)}</div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
                gap: 12,
                marginBottom: 24,
                maxWidth: 800,
              }}
            >
              <Metric label="Last return" value={<SignedPct value={selected.daily_return} />} />
              <Metric label="30d return" value={<SignedPct value={selected.return_30d} />} />
              <Metric label="30d vol" value={formatPct(selected.vol_30d)} />
              <Metric label="Drawdown" value={<SignedPct value={selected.drawdown} />} />
              <Metric label="Rel. volume" value={formatMultiple(selected.volume_ratio)} />
              <Metric label="P/E" value={formatNum(selected.pe, 1)} />
              <Metric label="Mkt cap" value={formatCap(selected.market_cap)} />
              <Metric label="Mom 12-1" value={<SignedPct value={selected.momentum_12_1} />} />
              <Metric label="Beta" value={formatNum(selected.beta_60d, 2)} />
              <Metric label="News 7d" value={selected.news_count ?? "—"} />
              <Metric label="Sent. 7d" value={<SignedSentiment value={selected.avg_sentiment} />} />
              <Metric label="Anomaly" value={<SignedZ value={selected.idio_z} />} />
              <Metric label="Tape" value={selected.tape_news ?? "—"} />
              <Metric label="Regime" value={selected.vol_regime ?? "—"} />
            </div>
            <h2>{STOCK_CHARTS[chartSlide].title}</h2>
            <p>{STOCK_CHARTS[chartSlide].blurb}</p>
            <p>
              {chartSlide + 1} of {STOCK_CHARTS.length}
            </p>
            <img
              src={`${API}/stocks/${encodeURIComponent(selected.ticker)}/chart${STOCK_CHARTS[chartSlide].path}`}
              alt={STOCK_CHARTS[chartSlide].title}
              style={{
                width: "100%",
                maxWidth: "640px",
                display: "block",
                marginBottom: "12px",
              }}
            />
            <p>
              <button
                type="button"
                disabled={chartSlide === 0}
                onClick={() => setChartSlide((i) => i - 1)}
              >
                Previous
              </button>{" "}
              <button
                type="button"
                disabled={chartSlide === STOCK_CHARTS.length - 1}
                onClick={() => setChartSlide((i) => i + 1)}
              >
                Next
              </button>
            </p>
            <p>{prices.length} daily rows stored (last 10 below)</p>
            <div style={{ maxHeight: 220, overflow: "auto" }}>
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Open</th>
                    <th>High</th>
                    <th>Low</th>
                    <th>Close</th>
                    <th>30D MA</th>
                    <th>Prev close</th>
                    <th>Daily return</th>
                    <th>Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {prices
                    .slice(-10)
                    .toReversed()
                    .map((bar) => (
                      <tr key={String(bar.date)}>
                        <td>{dateKey(bar.date)}</td>
                        <td>
                          {bar.open != null ? Number(bar.open).toFixed(2) : ""}
                        </td>
                        <td>
                          {bar.high != null ? Number(bar.high).toFixed(2) : ""}
                        </td>
                        <td>
                          {bar.low != null ? Number(bar.low).toFixed(2) : ""}
                        </td>
                        <td>
                          {bar.close != null ? Number(bar.close).toFixed(2) : ""}
                        </td>
                        <td>
                          {bar.ma_30d != null
                            ? Number(bar.ma_30d).toFixed(2)
                            : "—"}
                        </td>
                        <td>
                          {bar.prev_close != null
                            ? Number(bar.prev_close).toFixed(2)
                            : "—"}
                        </td>
                        <td>
                          <SignedPct value={bar.daily_return} />
                        </td>
                        <td>{bar.volume}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <p style={{ marginTop: 24 }}>
              {editingTicker === selected.ticker ? (
                <>
                  Backfill from{" "}
                  <input
                    type="date"
                    value={editDate}
                    onChange={(event) => setEditDate(event.target.value)}
                  />{" "}
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => handleSaveEdit(selected.ticker)}
                  >
                    Save
                  </button>
                  <button type="button" onClick={() => setEditingTicker(null)}>
                    Cancel
                  </button>
                </>
              ) : (
                <>
                  Backfill from {selected.backfill_start_date ?? "—"}{" "}
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => {
                      setEditingTicker(selected.ticker);
                      setEditDate(selected.backfill_start_date ?? "");
                    }}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => handleDelete(selected.ticker)}
                  >
                    Delete
                  </button>
                </>
              )}
            </p>
              </>
            }
            news={
              <>
                <h2 style={{ marginTop: 0 }}>Today’s briefing</h2>
                {reportText ? (
                  <BriefingBody text={reportText} />
                ) : (
                  <p>
                    No briefing yet. Write one when you want a read of this
                    session.
                  </p>
                )}
                <p>
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => handleGenerateReport(selected.ticker)}
                  >
                    {loading
                      ? "Working..."
                      : reportText
                        ? "Refresh briefing"
                        : "Write today’s briefing"}
                  </button>
                </p>
                {reports.length > 1 ? (
                  <details>
                    <summary>Earlier briefings</summary>
                    <ul>
                      {reports.map((item) => (
                        <li key={item.filename}>
                          <button
                            type="button"
                            onClick={() =>
                              handleOpenReport(selected.ticker, item.filename)
                            }
                          >
                            {item.filename}
                            {item.filename === activeReport ? " (open)" : ""}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </>
            }
          />
        )}
      </main>
    </div>
  );
}

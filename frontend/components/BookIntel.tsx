import { signedColor } from "./signed";

type BookRisk = {
  lookback?: string | null;
  concentration_label?: string | null;
  top_ticker?: string | null;
  top_weight?: number | null;
  name_count?: number | null;
  correlation?: number | null;
  correlation_pair?: string | null;
  correlation_label?: string | null;
  vol_30d?: number | null;
  beta_vs_spy?: number | null;
  drawdown_90d?: number | null;
  sector_line?: string | null;
  assessment?: string | null;
  corr_window?: number | null;
  vol_window?: number | null;
  beta_window?: number | null;
  drawdown_window?: number | null;
};

export type BookSnapshot = {
  as_of?: string | null;
  risk?: BookRisk | null;
};

function pct(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function ratio(value: number | null | undefined, digits = 2) {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function Chip({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: number | null;
}) {
  return (
    <div
      title={hint ? `${label}: ${value} · ${hint}` : `${label}: ${value}`}
      style={{
        border: "1px solid #ddd",
        padding: "6px 8px",
        background: "#fff",
        flex: "1 1 0",
        minWidth: 0,
      }}
    >
      <div
        style={{
          fontSize: 11,
          color: "#555",
          marginBottom: 2,
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 15,
          fontWeight: 600,
          whiteSpace: "nowrap",
          color: signedColor(tone),
        }}
      >
        {value}
      </div>
    </div>
  );
}

export default function BookIntel({ snapshot }: { snapshot: BookSnapshot | null }) {
  const risk = snapshot?.risk;
  if (!risk) {
    return (
      <p style={{ margin: "12px 0 0", color: "#555", fontSize: 13 }}>
        Book risk loads from live prices once the API is up.
      </p>
    );
  }

  const top =
    risk.top_ticker && risk.top_weight != null
      ? `${risk.top_ticker} ${pct(risk.top_weight, 0)}`
      : "—";
  const corrHint = [
    risk.correlation_pair,
    risk.correlation_label,
    `${risk.corr_window ?? 90} sessions`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div style={{ marginTop: 12, flexShrink: 0 }}>
      <h2 style={{ margin: "0 0 6px", fontSize: 15 }}>Book risk</h2>
      <p
        style={{
          margin: "0 0 8px",
          color: "#555",
          fontSize: 12,
          lineHeight: 1.4,
        }}
      >
        Combined book with today&apos;s weights held constant — not an average of
        the names, not annualized vol.
      </p>
      <div
        style={{
          display: "flex",
          gap: 8,
          overflowX: "auto",
        }}
      >
        <Chip
          label="Concentration"
          value={risk.concentration_label || "—"}
          hint={top}
        />
        <Chip
          label="90d corr"
          value={ratio(risk.correlation)}
          hint={corrHint}
        />
        <Chip
          label="Beta vs SPY"
          value={ratio(risk.beta_vs_spy)}
          hint={`${risk.beta_window ?? 60} sessions`}
        />
        <Chip
          label="30d vol"
          value={pct(risk.vol_30d, 2)}
          hint="Session std of the book, not annualized"
        />
        <Chip
          label="90d drawdown"
          value={pct(risk.drawdown_90d, 1)}
          hint="From the peak of the constant-weight wealth path"
          tone={risk.drawdown_90d}
        />
        <Chip
          label="Sector"
          value={(risk.sector_line || "—").replace(/^100% /, "")}
          hint={risk.sector_line || undefined}
        />
      </div>
      {risk.assessment ? (
        <p
          style={{
            margin: "8px 0 0",
            fontSize: 13,
            lineHeight: 1.45,
          }}
        >
          {risk.assessment}
        </p>
      ) : null}
    </div>
  );
}

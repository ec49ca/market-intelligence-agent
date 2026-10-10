import type { CSSProperties } from "react";
import { DOWN, UP, signedColor } from "./signed";

type BookRow = {
  ticker: string;
  as_of?: string | null;
  weight?: number | string | null;
  market_value?: number | string | null;
  cost_basis?: number | string | null;
  unrealized?: number | string | null;
  unrealized_pct?: number | string | null;
  daily_return?: number | string | null;
  vol_30d?: number | string | null;
  return_30d?: number | string | null;
};

const FILLS = ["#111", "#5a5a5a", "#8a8a8a", "#c4c4c4", "#333", "#777"];

const cell: CSSProperties = {
  minHeight: 0,
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

function num(value: number | string | null | undefined): number | null {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function usd(value: number, digits?: number) {
  const max =
    digits != null ? digits : Math.abs(value) >= 1000 ? 0 : 2;
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: max,
  });
}

function compactUsd(value: number) {
  const abs = Math.abs(value);
  const body =
    abs >= 1000
      ? `$${(abs / 1000).toFixed(abs >= 100000 ? 0 : 1)}k`
      : usd(abs);
  if (value > 0) return `+${body}`;
  if (value < 0) return `−${body}`;
  return body;
}

function pct(value: number, digits = 2) {
  return `${(value * 100).toFixed(digits)}%`;
}

function signedUsd(value: number) {
  const formatted = usd(Math.abs(value));
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `−${formatted}`;
  return formatted;
}

function signedPct(value: number, digits = 2) {
  const formatted = pct(Math.abs(value), digits);
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `−${formatted}`;
  return formatted;
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
  const color = signedColor(tone);
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
          color,
        }}
      >
        {value}
      </div>
    </div>
  );
}

function ChartHead({ title, caption }: { title: string; caption: string }) {
  return (
    <>
      <h3 style={{ margin: "0 0 2px", fontSize: 14 }}>{title}</h3>
      <p
        style={{
          margin: "0 0 8px",
          color: "#555",
          fontSize: 12,
          lineHeight: 1.35,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {caption}
      </p>
    </>
  );
}

function polar(cx: number, cy: number, r: number, angle: number) {
  return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)] as const;
}

function MixPie({
  items,
}: {
  items: { label: string; value: number }[];
}) {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  if (total <= 0) return null;
  const size = 124;
  const cx = size / 2;
  const cy = size / 2;
  const outer = 50;
  const inner = 28;
  const slices =
    items.length === 1
      ? [
          {
            label: items[0].label,
            value: items[0].value,
            fill: FILLS[0],
            d: [
              `M ${cx} ${cy - outer}`,
              `A ${outer} ${outer} 0 1 1 ${cx} ${cy + outer}`,
              `A ${outer} ${outer} 0 1 1 ${cx} ${cy - outer}`,
              `M ${cx} ${cy - inner}`,
              `A ${inner} ${inner} 0 1 0 ${cx} ${cy + inner}`,
              `A ${inner} ${inner} 0 1 0 ${cx} ${cy - inner}`,
            ].join(" "),
          },
        ]
      : (() => {
          let angle = -Math.PI / 2;
          return items.map((item, index) => {
            const sweep = (item.value / total) * 2 * Math.PI;
            const start = angle;
            const end = angle + sweep;
            angle = end;
            const large = sweep > Math.PI ? 1 : 0;
            const [x1, y1] = polar(cx, cy, outer, start);
            const [x2, y2] = polar(cx, cy, outer, end);
            const [ix1, iy1] = polar(cx, cy, inner, end);
            const [ix2, iy2] = polar(cx, cy, inner, start);
            return {
              ...item,
              fill: FILLS[index % FILLS.length],
              d: [
                `M ${x1} ${y1}`,
                `A ${outer} ${outer} 0 ${large} 1 ${x2} ${y2}`,
                `L ${ix1} ${iy1}`,
                `A ${inner} ${inner} 0 ${large} 0 ${ix2} ${iy2}`,
                "Z",
              ].join(" "),
            };
          });
        })();
  const top = items[0];
  return (
    <section style={cell}>
      <ChartHead
        title="Weight mix"
        caption="Percent of the book. Last close × shares, not what you paid."
      />
      <div
        style={{
          display: "flex",
          gap: 16,
          alignItems: "center",
          minHeight: 0,
          flex: 1,
        }}
      >
        <svg
          width={size}
          height={size}
          role="img"
          aria-label="Portfolio weight mix pie"
        >
          {slices.map((slice) => (
            <path key={slice.label} d={slice.d} fill={slice.fill} />
          ))}
          <text
            x={cx}
            y={cy - 6}
            textAnchor="middle"
            fontSize={13}
            fill="#111"
          >
            {top.label}
          </text>
          <text
            x={cx}
            y={cy + 12}
            textAnchor="middle"
            fontSize={12}
            fill="#555"
          >
            {pct(top.value / total, 1)}
          </text>
        </svg>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {slices.map((slice) => (
            <div
              key={slice.label}
              style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}
            >
              <span
                style={{
                  width: 10,
                  height: 10,
                  background: slice.fill,
                  display: "inline-block",
                }}
              />
              <span style={{ minWidth: 56 }}>{slice.label}</span>
              <span>{pct(slice.value / total, 1)}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function BarList({
  title,
  caption,
  items,
  format,
  signed,
}: {
  title: string;
  caption: string;
  items: { label: string; value: number }[];
  format: (value: number) => string;
  signed?: boolean;
}) {
  if (items.length === 0) {
    return null;
  }
  const max = Math.max(...items.map((item) => Math.abs(item.value)), 1e-9);
  return (
    <section style={cell}>
      <ChartHead title={title} caption={caption} />
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 8,
          flex: 1,
          minHeight: 0,
          justifyContent: "center",
        }}
      >
        {items.map((item) => {
          const width = `${Math.max(4, (Math.abs(item.value) / max) * 100)}%`;
          const negative = signed && item.value < 0;
          return (
            <div key={item.label}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: 13,
                  marginBottom: 2,
                }}
              >
                <span>{item.label}</span>
                <span
                  style={{
                    color: signed
                      ? item.value > 0
                        ? UP
                        : item.value < 0
                          ? DOWN
                          : undefined
                      : undefined,
                    fontWeight: signed && item.value !== 0 ? 600 : undefined,
                  }}
                >
                  {format(item.value)}
                </span>
              </div>
              <div style={{ background: "#eee", height: 10 }}>
                <div
                  style={{
                    width,
                    height: "100%",
                    background: negative ? DOWN : signed ? UP : "#111",
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function RiskReturn({ rows }: { rows: BookRow[] }) {
  const points = rows
    .map((row) => {
      const x = num(row.vol_30d);
      const y = num(row.return_30d);
      if (x == null || y == null) return null;
      return { ticker: row.ticker, x, y };
    })
    .filter((point): point is { ticker: string; x: number; y: number } => point != null);
  if (points.length === 0) {
    return null;
  }
  const width = 360;
  const height = 200;
  const pad = { top: 20, right: 52, bottom: 36, left: 48 };
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMin = Math.min(0, ...xs);
  const xMax = Math.max(...xs, 0.01);
  const yMin = Math.min(0, ...ys);
  const yMax = Math.max(...ys, 0.01);
  const xSpan = Math.max(xMax - xMin, 0.01);
  const ySpan = Math.max(yMax - yMin, 0.01);
  const x0 = xMin - xSpan * 0.08;
  const x1 = xMax + xSpan * 0.12;
  const y0 = yMin - ySpan * 0.12;
  const y1 = yMax + ySpan * 0.12;
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const sx = (x: number) => pad.left + ((x - x0) / (x1 - x0)) * innerW;
  const sy = (y: number) => pad.top + innerH - ((y - y0) / (y1 - y0)) * innerH;
  const originX = sx(0);
  const originY = sy(0);
  return (
    <section style={cell}>
      <ChartHead
        title="Risk vs 30-day return"
        caption="Each dot is a name. Right is jumpy (30d vol). Up is the last 30 session return."
      />
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Risk versus 30-day return scatter"
        style={{ flex: 1, minHeight: 0 }}
      >
        <line
          x1={pad.left}
          y1={originY}
          x2={width - pad.right}
          y2={originY}
          stroke="#bbb"
        />
        <line
          x1={originX}
          y1={pad.top}
          x2={originX}
          y2={height - pad.bottom}
          stroke="#bbb"
        />
        {points.map((point) => {
          const cx = sx(point.x);
          const cy = sy(point.y);
          const labelRight = cx < width - pad.right - 36;
          return (
            <g key={point.ticker}>
              <circle
                cx={cx}
                cy={cy}
                r={6}
                fill={point.y > 0 ? UP : point.y < 0 ? DOWN : "#111"}
              />
              <text
                x={labelRight ? cx + 8 : cx - 8}
                y={cy + 4}
                textAnchor={labelRight ? "start" : "end"}
                fontSize={11}
                fill="#111"
              >
                {point.ticker}
              </text>
            </g>
          );
        })}
        <text
          x={width / 2}
          y={height - 8}
          textAnchor="middle"
          fontSize={11}
          fill="#555"
        >
          30-day volatility
        </text>
        <text
          x={14}
          y={height / 2}
          textAnchor="middle"
          fontSize={11}
          fill="#555"
          transform={`rotate(-90 14 ${height / 2})`}
        >
          30-day return
        </text>
      </svg>
    </section>
  );
}

function dayDollar(row: BookRow): number | null {
  const value = num(row.market_value);
  const ret = num(row.daily_return);
  if (value == null || ret == null || ret <= -1) return null;
  return (value * ret) / (1 + ret);
}

export default function PortfolioCharts({ rows }: { rows: BookRow[] }) {
  const held = rows.filter((row) => (num(row.market_value) ?? 0) > 0);
  const book = held.reduce((sum, row) => sum + (num(row.market_value) ?? 0), 0);
  const cost = held.reduce((sum, row) => sum + (num(row.cost_basis) ?? 0), 0);
  const pnl = held.reduce((sum, row) => sum + (num(row.unrealized) ?? 0), 0);
  const dayMoves = held
    .map((row) => {
      const dollars = dayDollar(row);
      return dollars == null ? null : { ticker: row.ticker, dollars };
    })
    .filter((row): row is { ticker: string; dollars: number } => row != null);
  const dayDollars = dayMoves.reduce((sum, row) => sum + row.dollars, 0);
  const prior = book - dayDollars;
  const dayPct = prior > 0 ? dayDollars / prior : null;
  const pnlPct = cost > 0 ? pnl / cost : null;
  const weighted30 = held.reduce((sum, row) => {
    const weight = num(row.weight);
    const ret = num(row.return_30d);
    if (weight == null || ret == null) return sum;
    return sum + weight * ret;
  }, 0);
  const asOf = held
    .map((row) => (row.as_of ? String(row.as_of).slice(0, 10) : null))
    .filter((value): value is string => value != null)
    .sort()
    .at(-1);
  const weights = held
    .map((row) => ({ label: row.ticker, value: num(row.weight) ?? 0 }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value);
  const pnlBars = held
    .filter((row) => row.unrealized != null && row.unrealized !== "")
    .map((row) => ({ label: row.ticker, value: num(row.unrealized) ?? 0 }))
    .sort((a, b) => b.value - a.value);
  const todayBars = dayMoves
    .map((row) => ({ label: row.ticker, value: row.dollars }))
    .sort((a, b) => b.value - a.value);

  if (held.length === 0) {
    return (
      <p>
        Type shares and approx cost below. Cost defaults to the close on the day
        you added the name. Weight is last close × shares.
      </p>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        flexShrink: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          gap: 8,
          flexShrink: 0,
          overflowX: "auto",
        }}
      >
        <Chip
          label="Book"
          value={compactUsd(book).replace(/^\+/, "")}
          hint={usd(book)}
        />
        <Chip
          label="Today"
          value={dayPct == null ? compactUsd(dayDollars) : signedPct(dayPct, 1)}
          hint={signedUsd(dayDollars)}
          tone={dayPct ?? dayDollars}
        />
        <Chip
          label="P/L"
          value={pnlPct == null ? compactUsd(pnl) : signedPct(pnlPct, 1)}
          hint={signedUsd(pnl)}
          tone={pnlPct ?? pnl}
        />
        <Chip
          label="Cost"
          value={cost > 0 ? compactUsd(cost).replace(/^\+/, "") : "—"}
          hint={cost > 0 ? usd(cost) : undefined}
        />
        <Chip
          label="30-day"
          value={signedPct(weighted30, 1)}
          tone={weighted30}
        />
        <Chip
          label="Names"
          value={String(held.length)}
          hint={
            weights[0]
              ? `${weights[0].label} ${pct(weights[0].value, 1)}`
              : undefined
          }
        />
        {asOf ? (
          <Chip label="As of" value={asOf.slice(5).replace("-", "/")} />
        ) : (
          <Chip label="As of" value="—" />
        )}
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gridTemplateRows: "1fr 1fr",
          gap: 12,
          height: 340,
        }}
      >
        <MixPie items={weights} />
        <BarList
          title="Last session"
          caption="Dollar change from the prior close, shares × (close − prev)."
          items={todayBars}
          signed
          format={signedUsd}
        />
        <BarList
          title="Unrealized P/L"
          caption="(Last close − approx cost) × shares."
          items={pnlBars}
          signed
          format={(value) => signedUsd(value)}
        />
        <RiskReturn rows={held} />
      </div>
    </div>
  );
}

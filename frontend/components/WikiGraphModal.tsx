"use client";

import { useEffect, useMemo, useState } from "react";

const API = "http://127.0.0.1:8000";

type GraphNode = {
  id: string;
  slug: string;
  label: string;
  role: "book" | "ticker" | "entity" | "concept";
  path: string;
};

type GraphEdge = {
  source: string;
  target: string;
};

type Placed = GraphNode & { x: number; y: number; anchor?: "start" | "middle" | "end" };

const ROLE_FILL: Record<GraphNode["role"], string> = {
  book: "#111",
  ticker: "#111",
  entity: "#555",
  concept: "#888",
};

function neighborsOf(
  id: string,
  edges: GraphEdge[]
): Set<string> {
  const out = new Set<string>();
  for (const edge of edges) {
    if (edge.source === id) out.add(edge.target);
    if (edge.target === id) out.add(edge.source);
  }
  return out;
}

function tickerAnchors(
  tickers: GraphNode[],
  width: number,
  height: number
): Placed[] {
  const cx = width / 2;
  const cy = height * 0.52;
  const inset = 210;
  if (tickers.length === 0) return [];
  if (tickers.length === 1) {
    return [{ ...tickers[0], x: cx, y: cy, anchor: "middle" }];
  }
  if (tickers.length === 2) {
    return [
      { ...tickers[0], x: inset, y: cy, anchor: "middle" },
      { ...tickers[1], x: width - inset, y: cy, anchor: "middle" },
    ];
  }
  const r = Math.min(width, height) * 0.3;
  return tickers.map((node, index) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * index) / tickers.length;
    return {
      ...node,
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle) * 0.8,
      anchor: "middle",
    };
  });
}

function columnOutside(
  items: GraphNode[],
  hub: Placed,
  width: number
): Placed[] {
  if (items.length === 0) return [];
  const left = hub.x < width / 2;
  const x = left ? Math.max(72, hub.x - 118) : Math.min(width - 72, hub.x + 118);
  const gap = 56;
  const start = hub.y - ((items.length - 1) * gap) / 2;
  return items.map((node, index) => ({
    ...node,
    x,
    y: start + index * gap,
    anchor: "middle",
  }));
}

function packInside(
  items: { node: GraphNode; x: number }[],
  hubs: Placed[],
  height: number
): Placed[] {
  if (items.length === 0) return [];
  const cy = height * 0.5;
  const bands = new Map<number, { node: GraphNode; x: number }[]>();
  for (const item of items) {
    const key = Math.round(item.x / 80) * 80;
    const band = bands.get(key) || [];
    band.push(item);
    bands.set(key, band);
  }
  const out: Placed[] = [];
  const occupied = hubs.map((hub) => ({ x: hub.x, y: hub.y }));
  for (const [, band] of [...bands.entries()].sort((a, b) => a[0] - b[0])) {
    band.sort((a, b) => a.node.label.localeCompare(b.node.label));
    const cols = band.length > 3 ? 2 : 1;
    const colGap = 120;
    const rowGap = 78;
    const rows = Math.ceil(band.length / cols);
    const midX = band.reduce((sum, item) => sum + item.x, 0) / band.length;
    const startX = midX - ((cols - 1) * colGap) / 2;
    const startY = cy - ((rows - 1) * rowGap) / 2;
    band.forEach((item, index) => {
      const col = index % cols;
      const row = Math.floor(index / cols);
      let x = startX + col * colGap;
      let y = startY + row * rowGap;
      for (const other of occupied) {
        if (Math.hypot(other.x - x, other.y - y) < 56) {
          y += other.y >= y ? -64 : 64;
        }
      }
      y = Math.min(height - 40, Math.max(48, y));
      occupied.push({ x, y });
      out.push({ ...item.node, x, y, anchor: "middle" });
    });
  }
  return out;
}

function layout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  width: number,
  height: number
): Placed[] {
  const cx = width / 2;
  const graphNodes = nodes.filter((node) => node.role !== "book");
  const live = new Set(graphNodes.map((node) => node.id));
  const graphEdges = edges.filter(
    (edge) => live.has(edge.source) && live.has(edge.target)
  );
  const tickers = [...graphNodes.filter((node) => node.role === "ticker")].sort(
    (a, b) => a.slug.localeCompare(b.slug)
  );
  const hubs = tickerAnchors(tickers, width, height);
  const hubById = new Map(hubs.map((hub) => [hub.id, hub]));
  const tickerIds = new Set(tickers.map((node) => node.id));
  const exclusive = new Map<string, GraphNode[]>();
  for (const hub of hubs) exclusive.set(hub.id, []);
  const inside: { node: GraphNode; x: number }[] = [];

  for (const node of graphNodes) {
    if (node.role === "ticker") continue;
    const neigh = neighborsOf(node.id, graphEdges);
    const tickerNeigh = [...neigh].filter((id) => tickerIds.has(id));
    const otherNeigh = [...neigh].filter((id) => !tickerIds.has(id));
    if (tickerNeigh.length === 1 && otherNeigh.length === 0) {
      exclusive.get(tickerNeigh[0])!.push(node);
      continue;
    }
    const tickerXs = tickerNeigh
      .map((id) => hubById.get(id)?.x)
      .filter((x): x is number => x != null);
    let x = cx;
    if (tickerXs.length >= 2) {
      x = tickerXs.reduce((sum, value) => sum + value, 0) / tickerXs.length;
    } else if (tickerXs.length === 1) {
      x = tickerXs[0] * 0.58 + cx * 0.42;
    }
    inside.push({ node, x });
  }

  const placed: Placed[] = [...hubs];
  for (const hub of hubs) {
    const satellites = exclusive.get(hub.id) || [];
    satellites.sort((a, b) => a.label.localeCompare(b.label));
    placed.push(...columnOutside(satellites, hub, width));
  }
  placed.push(...packInside(inside, hubs, height));
  return placed;
}

export default function WikiGraphModal({
  onClose,
  onOpenTicker,
}: {
  onClose: () => void;
  onOpenTicker: (ticker: string) => void;
  onOpenBook?: () => void;
}) {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const width = 840;
  const height = 520;

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/wiki/graph`)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Graph failed: ${response.status}`);
        }
        return response.json();
      })
      .then((payload) => {
        if (cancelled) return;
        setNodes(payload.nodes || []);
        setEdges(payload.edges || []);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unknown error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const placed = useMemo(
    () => layout(nodes, edges, width, height),
    [nodes, edges, width, height]
  );
  const byId = useMemo(
    () => new Map(placed.map((node) => [node.id, node])),
    [placed]
  );

  function handleNode(node: Placed) {
    setActive(node.id);
    if (node.role === "ticker") {
      onOpenTicker(node.slug);
      onClose();
    }
  }

  return (
    <div
      role="dialog"
      aria-label="Wiki graph"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.35)",
        zIndex: 10000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        onClick={(event) => event.stopPropagation()}
        style={{
          background: "#fff",
          color: "#111",
          width: "min(920px, 96vw)",
          maxHeight: "92vh",
          overflow: "auto",
          padding: "16px 20px 20px",
          boxShadow: "0 8px 40px rgba(0,0,0,0.18)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            marginBottom: 8,
          }}
        >
          <h2 style={{ margin: 0 }}>Wiki graph</h2>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </div>
        <p style={{ marginTop: 0, color: "#555", fontSize: 13 }}>
          Pages in <code>wiki/entities</code> and <code>wiki/concepts</code>.
          Lines are markdown links. Source receipts are omitted. Book is the
          portfolio those names already live in, so it is not a node. Click a
          holding to open it.
        </p>
        <p style={{ fontSize: 12, color: "#555", marginTop: 0 }}>
          Holdings sit on opposite sides. A name that only belongs to one
          ticker fans outward. Anything that links across names sits between
          them.
        </p>
        {error ? <p>Error: {error}</p> : null}
        <svg
          width="100%"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="Wiki entity and concept links"
        >
          {edges.map((edge) => {
            const a = byId.get(edge.source);
            const b = byId.get(edge.target);
            if (!a || !b) return null;
            const lit =
              active != null && (a.id === active || b.id === active);
            return (
              <line
                key={`${edge.source}-${edge.target}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={lit ? "#111" : "#ccc"}
                strokeWidth={lit ? 2 : 1}
              />
            );
          })}
          {placed.map((node) => {
            const r = node.role === "ticker" ? 12 : 9;
            return (
              <g
                key={node.id}
                onClick={() => handleNode(node)}
                style={{
                  cursor: node.role === "ticker" ? "pointer" : "default",
                }}
              >
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={r}
                  fill={ROLE_FILL[node.role]}
                  opacity={active && active !== node.id ? 0.45 : 1}
                />
                <text
                  x={node.x}
                  y={node.y + r + 14}
                  textAnchor="middle"
                  fontSize={11}
                  fill="#111"
                >
                  {node.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { formatNum, formatPct, formatTwd, quadrantShort } from "@/lib/format";
import type { SectorRow } from "@/lib/types";

type Props = {
  rows: SectorRow[];
  selectedId: string | null;
  onSelect: (themeId: string) => void;
};

type Point = SectorRow & { size: number; x: number; y: number };

function domain(values: number[]): [number, number] {
  const peak = Math.max(...values.map((v) => Math.abs(v)), 1);
  return [-peak * 1.12, peak * 1.12];
}

function fillFor(row: SectorRow): string {
  switch (row.quadrant) {
    case "STRONG_INFLOW":
      return "#3dcf8e";
    case "SLOWING_INFLOW":
      return "#e0b34a";
    case "IMPROVING_OUTFLOW":
      return "#6ea8ff";
    case "ACCELERATING_OUTFLOW":
      return "#e07a7a";
    default:
      return "#8b93a7";
  }
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: Point }> }) {
  if (!active || !payload?.[0]) return null;
  const row = payload[0].payload;
  return (
    <div className="tooltip">
      <div className="tooltip-title">
        {row.theme_name} <span className="muted">{row.theme_id}</span>
      </div>
      <div>L{row.theme_level ?? "—"} · {quadrantShort(row.quadrant_label, row.quadrant)} · {row.lifecycle ?? "—"}</div>
      <div>Rotation {formatNum(row.rotation_score, 1)} · Emerging {formatNum(row.emerging_metric, 1)}</div>
      <div>flow_5d {formatTwd(row.flow_5d)} · accel {formatTwd(row.acceleration)}</div>
      <div>momentum {formatNum(row.price_momentum, 3)} · coverage {formatPct(row.coverage_ratio)}</div>
    </div>
  );
}

export default function BubbleChart({ rows, selectedId, onSelect }: Props) {
  const points: Point[] = useMemo(
    () =>
      rows
        .filter((r) => r.flow_5d != null && r.acceleration != null)
        .map((r) => ({
          ...r,
          x: r.flow_5d as number,
          y: r.acceleration as number,
          size: Math.max(r.trading_value_avg_20d ?? r.trading_value ?? 1, 1),
        })),
    [rows],
  );
  const xDomain = useMemo(() => domain(points.map((p) => p.x)), [points]);
  const yDomain = useMemo(() => domain(points.map((p) => p.y)), [points]);

  return (
    <div className="chart-wrap">
      <div className="quad-label tl">Improving Outflow / Watch</div>
      <div className="quad-label tr">Strong Inflow / Tide</div>
      <div className="quad-label bl">Accelerating Outflow / Exit</div>
      <div className="quad-label br">Slowing Inflow / Rotation</div>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 28, right: 16, bottom: 28, left: 8 }}>
          <CartesianGrid stroke="#243044" strokeDasharray="3 3" />
          <ReferenceArea x1={0} x2={xDomain[1]} y1={0} y2={yDomain[1]} fill="#1b3d2c" fillOpacity={0.22} />
          <ReferenceArea x1={0} x2={xDomain[1]} y1={yDomain[0]} y2={0} fill="#3a3118" fillOpacity={0.2} />
          <ReferenceArea x1={xDomain[0]} x2={0} y1={0} y2={yDomain[1]} fill="#1a2d4a" fillOpacity={0.2} />
          <ReferenceArea x1={xDomain[0]} x2={0} y1={yDomain[0]} y2={0} fill="#3a1f22" fillOpacity={0.22} />
          <ReferenceLine x={0} stroke="#6b778c" />
          <ReferenceLine y={0} stroke="#6b778c" />
          <XAxis
            type="number"
            dataKey="x"
            domain={xDomain}
            tick={{ fill: "#9aa4b5", fontSize: 11 }}
            tickFormatter={(v: number) => formatTwd(v)}
            name="flow_5d"
          />
          <YAxis
            type="number"
            dataKey="y"
            domain={yDomain}
            tick={{ fill: "#9aa4b5", fontSize: 11 }}
            tickFormatter={(v: number) => formatTwd(v)}
            name="acceleration"
            width={72}
          />
          <ZAxis type="number" dataKey="size" range={[40, 280]} />
          <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: "3 3" }} />
          <Scatter
            data={points}
            onClick={(state) => {
              const id = (state as { payload?: Point })?.payload?.theme_id;
              if (id) onSelect(id);
            }}
            shape={(props) => {
              const { cx = 0, cy = 0, payload } = props as {
                cx?: number;
                cy?: number;
                payload?: Point;
              };
              if (!payload) return <g />;
              const selected = payload.theme_id === selectedId;
              const r = selected ? 9 : 5;
              return (
                <circle
                  cx={cx}
                  cy={cy}
                  r={r}
                  fill={fillFor(payload)}
                  fillOpacity={selected ? 1 : 0.82}
                  stroke={selected ? "#f4efe4" : "rgba(255,255,255,0.25)"}
                  strokeWidth={selected ? 2.4 : 0.8}
                  style={{ cursor: "pointer" }}
                />
              );
            }}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

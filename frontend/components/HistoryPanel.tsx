"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatNum } from "@/lib/format";
import type { SectorRow } from "@/lib/types";

type Props = {
  sessions: SectorRow[];
  dates: string[];
  dateIndex: number;
  playing: boolean;
  onDateIndex: (index: number) => void;
  onTogglePlay: () => void;
};

export default function HistoryPanel({
  sessions,
  dates,
  dateIndex,
  playing,
  onDateIndex,
  onTogglePlay,
}: Props) {
  const [showFlow, setShowFlow] = useState(false);
  const [showAccel, setShowAccel] = useState(false);
  const [showMom, setShowMom] = useState(false);
  const data = useMemo(
    () =>
      sessions.map((s) => ({
        date: s.trade_date,
        rotation: s.rotation_score,
        emerging: s.emerging_metric,
        flow: s.flow_5d,
        accel: s.acceleration,
        mom: s.price_momentum,
      })),
    [sessions],
  );
  const current = dates[dateIndex] ?? "";

  return (
    <section className="history-panel">
      <header>
        <h2>20-session playback</h2>
        <div className="play-row">
          <button type="button" onClick={onTogglePlay}>
            {playing ? "Pause" : "Play"}
          </button>
          <label>
            {current}
            <input
              type="range"
              min={0}
              max={Math.max(dates.length - 1, 0)}
              value={dateIndex}
              onChange={(e) => onDateIndex(Number(e.target.value))}
            />
          </label>
        </div>
      </header>
      <div className="toggles">
        <label>
          <input type="checkbox" checked={showFlow} onChange={(e) => setShowFlow(e.target.checked)} />
          flow_5d
        </label>
        <label>
          <input type="checkbox" checked={showAccel} onChange={(e) => setShowAccel(e.target.checked)} />
          acceleration
        </label>
        <label>
          <input type="checkbox" checked={showMom} onChange={(e) => setShowMom(e.target.checked)} />
          price momentum
        </label>
      </div>
      <div className="hist-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#243044" strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fill: "#9aa4b5", fontSize: 10 }} minTickGap={24} />
            <YAxis yAxisId="score" tick={{ fill: "#9aa4b5", fontSize: 10 }} domain={[0, 100]} width={36} />
            {(showFlow || showAccel || showMom) && (
              <YAxis yAxisId="alt" orientation="right" tick={{ fill: "#9aa4b5", fontSize: 10 }} width={40} />
            )}
            <Tooltip
              formatter={(value) => formatNum(typeof value === "number" ? value : Number(value ?? 0), 2)}
            />
            <Legend />
            <Line yAxisId="score" type="monotone" dataKey="rotation" name="Rotation Score" stroke="#e0b34a" dot={false} strokeWidth={2} />
            <Line yAxisId="score" type="monotone" dataKey="emerging" name="Emerging" stroke="#6ea8ff" dot={false} strokeWidth={2} />
            {showFlow ? (
              <Line yAxisId="alt" type="monotone" dataKey="flow" name="flow_5d" stroke="#3dcf8e" dot={false} />
            ) : null}
            {showAccel ? (
              <Line yAxisId="alt" type="monotone" dataKey="accel" name="acceleration" stroke="#c48bff" dot={false} />
            ) : null}
            {showMom ? (
              <Line yAxisId="alt" type="monotone" dataKey="mom" name="momentum" stroke="#e07a7a" dot={false} />
            ) : null}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

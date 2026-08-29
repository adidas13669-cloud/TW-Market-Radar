"use client";

import { formatNum, quadrantShort } from "@/lib/format";
import type { SectorRow } from "@/lib/types";

type Props = {
  title: string;
  metric: "rotation_score" | "emerging_metric" | "acceleration";
  rows: SectorRow[];
  selectedId: string | null;
  onSelect: (themeId: string) => void;
};

function deltaMark(delta: number | null): string {
  if (delta == null) return "·";
  if (delta > 0.15) return "▲";
  if (delta < -0.15) return "▼";
  return "→";
}

export default function RankPanel({ title, metric, rows, selectedId, onSelect }: Props) {
  return (
    <section className="rank-panel">
      <header>{title}</header>
      <ol>
        {rows.slice(0, 20).map((row, idx) => (
          <li key={row.theme_id}>
            <button
              type="button"
              className={row.theme_id === selectedId ? "rank-row selected" : "rank-row"}
              onClick={() => onSelect(row.theme_id)}
            >
              <span className="rk">{idx + 1}</span>
              <span className="nm">
                <strong>{row.theme_name}</strong>
                <em>
                  {row.theme_id} · L{row.theme_level ?? "—"}
                </em>
              </span>
              <span className="sc">{formatNum(row[metric], 1)}</span>
              <span className="meta">
                {quadrantShort(row.quadrant_label, row.quadrant)} · {row.lifecycle ?? "—"} {deltaMark(row.score_delta)}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}

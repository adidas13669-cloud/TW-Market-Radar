"use client";

import { formatNum, formatPct, formatTwd, quadrantShort } from "@/lib/format";
import type { SectorDetail } from "@/lib/types";

type Props = {
  detail: SectorDetail | null;
};

const METRICS: Array<[string, (d: SectorDetail) => string]> = [
  ["flow_5d", (d) => formatTwd(d.sector.flow_5d)],
  ["avg_5d", (d) => formatTwd(d.sector.avg_5d)],
  ["avg_20d", (d) => formatTwd(d.sector.avg_20d)],
  ["acceleration", (d) => formatTwd(d.sector.acceleration)],
  ["normalized_flow", (d) => formatNum(d.sector.normalized_flow, 3)],
  ["price_momentum", (d) => formatNum(d.sector.price_momentum, 3)],
  ["volume_expansion", (d) => formatNum(d.sector.volume_expansion, 3)],
  ["continuity", (d) => formatNum(d.sector.continuity, 3)],
  ["margin_signal", (d) => formatNum(d.sector.margin_signal, 3)],
  ["rotation_score", (d) => formatNum(d.sector.rotation_score, 2)],
  ["emerging_metric", (d) => formatNum(d.sector.emerging_metric, 2)],
];

export default function ThemeDetail({ detail }: Props) {
  if (!detail) {
    return <section className="detail-panel muted">Select a theme to inspect metrics.</section>;
  }
  const s = detail.sector;
  const crumb = [...detail.parent_chain.map((t) => t.name), s.theme_name ?? s.theme_id].join(" / ");
  return (
    <section className="detail-panel">
      <header>
        <div>
          <h2>
            {s.theme_name} <span className="muted">{s.theme_id}</span>
          </h2>
          <p className="crumb">
            L{s.theme_level ?? "—"} · {crumb || "—"}
          </p>
        </div>
        <div className="badges">
          <span>{quadrantShort(s.quadrant_label, s.quadrant)}</span>
          <span>{s.lifecycle ?? "—"}</span>
          {s.divergence_flag ? <span className="warn">divergence</span> : null}
          {s.low_coverage ? <span className="warn">low coverage</span> : null}
        </div>
      </header>
      <div className="counts">
        members {s.member_count ?? "—"} · priced {s.priced_member_count ?? "—"} · flow {s.flow_member_count ?? "—"} ·
        coverage {formatPct(s.coverage_ratio)}
      </div>
      <dl className="metrics">
        {METRICS.map(([label, fn]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{fn(detail)}</dd>
          </div>
        ))}
      </dl>
      <h3>Top constituents</h3>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Ticker</th>
            <th>Name</th>
            <th>Score</th>
            <th>flow_5d</th>
          </tr>
        </thead>
        <tbody>
          {detail.constituents.slice(0, 12).map((c, i) => (
            <tr key={c.security_id}>
              <td>{i + 1}</td>
              <td>{c.security_id}</td>
              <td>{c.name ?? "—"}</td>
              <td>{formatNum(c.rotation_score, 1)}</td>
              <td>{formatTwd(c.flow_5d)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

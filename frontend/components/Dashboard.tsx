"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchDetail,
  fetchDivergence,
  fetchEmerging,
  fetchHealth,
  fetchHistory,
  fetchLatest,
  fetchMeta,
} from "@/lib/api";
import type { RadarMeta, SectorDetail, SectorHistory, SectorRow } from "@/lib/types";
import BubbleChart from "./BubbleChart";
import HistoryPanel from "./HistoryPanel";
import RankPanel from "./RankPanel";
import ThemeDetail from "./ThemeDetail";

type LevelMode = "eligible" | "1" | "2" | "3";
type Chip = "all" | "rotation" | "emerging" | "divergence";

export default function Dashboard() {
  const [meta, setMeta] = useState<RadarMeta | null>(null);
  const [connected, setConnected] = useState<"ok" | "down" | "loading">("loading");
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dates, setDates] = useState<string[]>([]);
  const [dateIndex, setDateIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [levelMode, setLevelMode] = useState<LevelMode>("eligible");
  const [parentId, setParentId] = useState("");
  const [search, setSearch] = useState("");
  const [chip, setChip] = useState<Chip>("all");
  const [rotation, setRotation] = useState<SectorRow[]>([]);
  const [emerging, setEmerging] = useState<SectorRow[]>([]);
  const [divergence, setDivergence] = useState<SectorRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>("AI_CPO");
  const [detail, setDetail] = useState<SectorDetail | null>(null);
  const [history, setHistory] = useState<SectorHistory | null>(null);

  const tradeDate = dates[dateIndex];
  const l1s = useMemo(() => (meta?.themes ?? []).filter((t) => t.theme_level === 1), [meta]);

  const loadUniverse = useCallback(async () => {
    if (!tradeDate) return;
    const query = {
      tradeDate,
      themeLevel: levelMode === "eligible" ? null : Number(levelMode),
      parentThemeId: parentId || undefined,
      rankEligible: levelMode === "eligible" || levelMode !== "1",
    };
    if (levelMode === "1") query.rankEligible = false;
    const [rot, emg, div] = await Promise.all([
      fetchLatest(query),
      fetchEmerging(query),
      fetchDivergence(query),
    ]);
    setRotation(rot);
    setEmerging(emg);
    setDivergence(div);
    setSelectedId((current) => {
      const ids = new Set(rot.map((r) => r.theme_id));
      if (current && ids.has(current)) return current;
      if (ids.has("AI_CPO")) return "AI_CPO";
      return rot[0]?.theme_id ?? null;
    });
  }, [tradeDate, levelMode, parentId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [health, radarMeta] = await Promise.all([fetchHealth(), fetchMeta()]);
        if (cancelled) return;
        setConnected(health.status === "ok" ? "ok" : "down");
        setMeta(radarMeta);
        setDates(radarMeta.session_dates);
        setDateIndex(Math.max(radarMeta.session_dates.length - 1, 0));
        setDemo(false);
      } catch (err) {
        if (cancelled) return;
        setConnected("down");
        setDemo(true);
        setError(err instanceof Error ? err.message : "backend unavailable");
        setMeta({
          asof: null,
          mapping_version: "v2-tax-2",
          production_ready: false,
          mapping_source: null,
          notes: "DEMO DATA",
          session_dates: [],
          themes: [],
          estimated_notional_caveat: "Backend unavailable.",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (demo) return;
    loadUniverse().catch((err: Error) => setError(err.message));
  }, [demo, loadUniverse]);

  useEffect(() => {
    if (!selectedId || !tradeDate || demo) return;
    let cancelled = false;
    Promise.all([fetchDetail(selectedId, tradeDate), fetchHistory(selectedId)])
      .then(([d, h]) => {
        if (!cancelled) {
          setDetail(d);
          setHistory(h);
        }
      })
      .catch((err: Error) => setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [selectedId, tradeDate, demo]);

  useEffect(() => {
    if (!playing || dates.length === 0) return;
    const timer = window.setInterval(() => {
      setDateIndex((idx) => (idx + 1) % dates.length);
    }, 700);
    return () => window.clearInterval(timer);
  }, [playing, dates.length]);

  const searched = useMemo(() => {
    const q = search.trim().toLowerCase();
    const match = (row: SectorRow) =>
      !q || row.theme_id.toLowerCase().includes(q) || (row.theme_name ?? "").toLowerCase().includes(q);
    return {
      rotation: rotation.filter(match),
      emerging: emerging.filter(match),
      divergence: divergence.filter(match),
    };
  }, [search, rotation, emerging, divergence]);

  const bubbles = useMemo(() => {
    const topRot = new Set(searched.rotation.slice(0, 20).map((r) => r.theme_id));
    const topEmg = new Set(searched.emerging.slice(0, 20).map((r) => r.theme_id));
    const div = new Set(searched.divergence.map((r) => r.theme_id));
    if (chip === "rotation") return searched.rotation.filter((r) => topRot.has(r.theme_id));
    if (chip === "emerging") return searched.rotation.filter((r) => topEmg.has(r.theme_id));
    if (chip === "divergence") return searched.rotation.filter((r) => div.has(r.theme_id));
    return searched.rotation;
  }, [chip, searched]);

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <h1>TW Market Radar</h1>
          <p className="sub">Stage 11 dashboard preview · not production UI</p>
        </div>
        <div className="status-row">
          <span className="pill">as-of {meta?.asof ?? tradeDate ?? "—"}</span>
          <span className="pill">{meta?.mapping_version ?? "v2-tax-2"}</span>
          <span className="pill warn">production_ready={String(meta?.production_ready ?? false)}</span>
          <span className={connected === "ok" ? "pill ok" : "pill warn"}>
            backend {connected === "loading" ? "…" : connected}
          </span>
          {demo ? <span className="pill warn">DEMO DATA</span> : null}
        </div>
        <div className="controls">
          <select value={levelMode} onChange={(e) => setLevelMode(e.target.value as LevelMode)}>
            <option value="eligible">All rank-eligible L2/L3</option>
            <option value="1">L1 only</option>
            <option value="2">L2 only</option>
            <option value="3">L3 only</option>
          </select>
          <select value={parentId} onChange={(e) => setParentId(e.target.value)}>
            <option value="">All L1 industries</option>
            {l1s.map((t) => (
              <option key={t.theme_id} value={t.theme_id}>
                {t.name} ({t.theme_id})
              </option>
            ))}
          </select>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search theme id / name"
          />
        </div>
      </header>

      {error ? <div className="banner warn-banner">{error}</div> : null}
      <div className="banner">
        Low-coverage themes are excluded from default ranks. {meta?.estimated_notional_caveat}
      </div>

      <div className="chips">
        {(["all", "rotation", "emerging", "divergence"] as Chip[]).map((id) => (
          <button key={id} type="button" className={chip === id ? "chip on" : "chip"} onClick={() => setChip(id)}>
            {id === "all" ? "Universe" : id === "rotation" ? "Top Rotation" : id === "emerging" ? "Top Emerging" : "Divergence"}
          </button>
        ))}
        <span className="muted">{bubbles.length} bubbles</span>
      </div>

      <div className="main-grid">
        <BubbleChart rows={bubbles} selectedId={selectedId} onSelect={setSelectedId} />
        <div className="ranks">
          <RankPanel title="Top Rotation Score" metric="rotation_score" rows={searched.rotation} selectedId={selectedId} onSelect={setSelectedId} />
          <RankPanel title="Top Emerging Rotation" metric="emerging_metric" rows={searched.emerging} selectedId={selectedId} onSelect={setSelectedId} />
          <RankPanel title="Divergence Candidates" metric="acceleration" rows={searched.divergence} selectedId={selectedId} onSelect={setSelectedId} />
        </div>
      </div>

      <div className="bottom-grid">
        <HistoryPanel
          sessions={history?.sessions ?? []}
          dates={dates}
          dateIndex={dateIndex}
          playing={playing}
          onDateIndex={(idx) => {
            setPlaying(false);
            setDateIndex(idx);
          }}
          onTogglePlay={() => setPlaying((p) => !p)}
        />
        <ThemeDetail detail={detail} />
      </div>
    </div>
  );
}

export type Quadrant =
  | "STRONG_INFLOW"
  | "SLOWING_INFLOW"
  | "IMPROVING_OUTFLOW"
  | "ACCELERATING_OUTFLOW";

export type Lifecycle = "EARLY" | "CONFIRMED" | "CROWDED" | "EXIT";

export type ThemeMeta = {
  theme_id: string;
  name: string;
  theme_level: number | null;
  parent_theme_id: string | null;
  theme_category: string | null;
  concentrated_ok: boolean;
};

export type RadarMeta = {
  asof: string | null;
  mapping_version: string | null;
  production_ready: boolean;
  mapping_source: string | null;
  notes: string | null;
  session_dates: string[];
  themes: ThemeMeta[];
  estimated_notional_caveat: string;
};

export type SectorRow = {
  theme_id: string;
  theme_name: string | null;
  trade_date: string;
  flow_5d: number | null;
  avg_5d: number | null;
  avg_20d: number | null;
  acceleration: number | null;
  trading_value: number | null;
  trading_value_avg_20d: number | null;
  normalized_flow: number | null;
  price_momentum: number | null;
  volume_expansion: number | null;
  continuity: number | null;
  margin_signal: number | null;
  quadrant: Quadrant | null;
  quadrant_label: string | null;
  lifecycle: Lifecycle | null;
  rotation_score: number | null;
  emerging_metric: number | null;
  divergence_flag: boolean;
  rank: number | null;
  member_count: number | null;
  priced_member_count: number | null;
  flow_member_count: number | null;
  coverage_ratio: number | null;
  low_coverage: boolean;
  thin_membership: boolean;
  rank_excluded: boolean;
  mapping_version: string | null;
  theme_level: number | null;
  parent_theme_id: string | null;
  theme_category: string | null;
  parent_chain: string[];
  score_delta: number | null;
};

export type Constituent = {
  security_id: string;
  name: string | null;
  rotation_score: number | null;
  flow_5d: number | null;
  acceleration: number | null;
  rank: number | null;
};

export type SectorDetail = {
  sector: SectorRow;
  constituents: Constituent[];
  parent_chain: ThemeMeta[];
};

export type SectorHistory = {
  theme_id: string;
  sessions: SectorRow[];
};

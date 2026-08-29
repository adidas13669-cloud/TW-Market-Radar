import type { RadarMeta, SectorDetail, SectorHistory, SectorRow } from "./types";

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new ApiError(`${path} ${response.status}`);
  }
  return (await response.json()) as T;
}

export type UniverseQuery = {
  tradeDate?: string;
  themeLevel?: number | null;
  parentThemeId?: string;
  rankEligible?: boolean;
};

function qs(query: UniverseQuery): string {
  const params = new URLSearchParams();
  if (query.tradeDate) params.set("trade_date", query.tradeDate);
  if (query.themeLevel != null) params.set("theme_level", String(query.themeLevel));
  if (query.parentThemeId) params.set("parent_theme_id", query.parentThemeId);
  if (query.rankEligible === false) params.set("rank_eligible", "false");
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

export function fetchMeta(): Promise<RadarMeta> {
  return getJson("/api/v1/radar/meta");
}

export function fetchHealth(): Promise<{ status: string }> {
  return getJson("/health");
}

export function fetchLatest(query: UniverseQuery): Promise<SectorRow[]> {
  return getJson(`/api/v1/radar/sectors/latest${qs(query)}`);
}

export function fetchEmerging(query: UniverseQuery): Promise<SectorRow[]> {
  return getJson(`/api/v1/radar/emerging${qs(query)}`);
}

export function fetchDivergence(query: UniverseQuery): Promise<SectorRow[]> {
  return getJson(`/api/v1/radar/divergence${qs(query)}`);
}

export function fetchDetail(themeId: string, tradeDate?: string): Promise<SectorDetail> {
  const suffix = tradeDate ? `?trade_date=${tradeDate}` : "";
  return getJson(`/api/v1/radar/sectors/${encodeURIComponent(themeId)}${suffix}`);
}

export function fetchHistory(themeId: string): Promise<SectorHistory> {
  return getJson(`/api/v1/radar/sectors/${encodeURIComponent(themeId)}/history?sessions=20`);
}

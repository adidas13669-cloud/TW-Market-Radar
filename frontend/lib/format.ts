export function formatTwd(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}億`;
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(1)}萬`;
  return `${sign}${abs.toFixed(0)}`;
}

export function formatNum(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function quadrantShort(label: string | null | undefined, quadrant: string | null | undefined): string {
  if (label) return label;
  if (!quadrant) return "—";
  return quadrant.replaceAll("_", " ");
}

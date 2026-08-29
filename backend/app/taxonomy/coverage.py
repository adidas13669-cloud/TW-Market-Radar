"""Industry-code and name-based coverage expansion.

Curated MEMBERS remain the investment-theme overlay (higher confidence).
Unmapped common stocks are attached using TW listed-code industry prefixes
and conservative Chinese name keywords. Prefix assignment is homogeneous
industries only; mixed electronics codes attach at L1 so they do not dilute
L2/L3 rotation ranks.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from app.core.securities import is_common_stock

LISTED_NAMES_PATH = Path("data/theme_mapping/v2/listed_names.csv")
COVERAGE_SOURCE = "v2-tax-2 coverage: TW listed-code prefix and name keywords"
PREFIX_CONFIDENCE = 0.55
KEYWORD_CONFIDENCE = 0.62

# Two-digit ticker prefix → theme_id. Electronics mega-codes map to L1 ELEC.
PREFIX_THEME: dict[str, str] = {
    "11": "CEMENT",
    "12": "FOOD",
    "13": "PLASTIC",
    "14": "TEXTILE",
    "15": "MACHINERY",
    "16": "CABLE",
    "17": "CHEM",
    "18": "GLASS",
    "19": "PAPER",
    "20": "STEEL",
    "21": "RUBBER",
    "22": "AUTO_PARTS",
    "23": "ELEC",
    "24": "ELEC",
    "25": "PROPERTY",
    "26": "SHIPPING",
    "27": "TOURISM",
    "28": "FINANCIAL",
    "29": "RETAIL",
    "30": "ELEC",
    "31": "ELEC",
    "32": "ELEC",
    "33": "ELEC",
    "34": "ELEC",
    "35": "ELEC",
    "36": "ELEC",
    "37": "ELEC",
    "41": "BIOPHARMA",
    "44": "TEXTILE",
    "45": "MACHINERY",
    "47": "BIOPHARMA",
    "49": "ELEC",
    "52": "ELEC",
    "53": "ELEC",
    "54": "ELEC",
    "55": "PROPERTY",
    "56": "LOGISTICS",
    "57": "TOURISM",
    "58": "FINANCIAL",
    "59": "RETAIL",
    "60": "SECURITIES",
    "61": "ELEC",
    "62": "ELEC",
    "64": "ELEC",
    "65": "ELEC",
    "66": "ELEC",
    "67": "ELEC",
    "68": "ELEC",
    "69": "ELEC",
    "77": "ELEC",
    "78": "ELEC",
    "80": "ELEC",
    "81": "ELEC",
    "82": "ELEC",
    "83": "ELEC",
    "89": "FOOD",
    "99": "CONSUMER",
}

# Longer keywords first. Avoid one-character matches (上銀 ≠ 銀行).
NAME_RULES: tuple[tuple[str, str], ...] = (
    ("金控", "FHOLDING"),
    ("商銀", "BANK"),
    ("企銀", "BANK"),
    ("銀行", "BANK"),
    ("人壽", "INSURANCE"),
    ("產險", "INSURANCE"),
    ("再保", "INSURANCE"),
    ("保險", "INSURANCE"),
    ("證券", "SECURITIES"),
    ("期貨", "SECURITIES"),
    ("租賃", "LEASING"),
    ("貨櫃", "CONTAINER"),
    ("散裝", "BULK"),
    ("航運", "SHIPPING"),
    ("海運", "SHIPPING"),
    ("航空", "AIRLINE"),
    ("水泥", "CEMENT"),
    ("鋼鐵", "STEEL"),
    ("不鏽鋼", "STEEL"),
    ("石化", "PETROCHEM"),
    ("塑膠", "PLASTIC"),
    ("橡膠", "RUBBER"),
    ("輪胎", "TIRE"),
    ("紡織", "TEXTILE"),
    ("食品", "FOOD"),
    ("超商", "RETAIL"),
    ("百貨", "RETAIL"),
    ("營造", "CONSTRUCTION"),
    ("營建", "CONSTRUCTION"),
    ("建設", "DEVELOPER"),
    ("觀光", "TOURISM"),
    ("飯店", "TOURISM"),
    ("太陽能", "SOLAR"),
    ("風力", "WIND"),
    ("風電", "WIND"),
    ("儲能", "STORAGE"),
    ("電池", "BATTERY"),
    ("充電", "CHARGING"),
    ("電動車", "EV"),
    ("半導體", "SEMI"),
    ("晶圓", "SEMI_WAFER"),
    ("封裝", "SEMI_PACKAGING"),
    ("連接器", "CONNECTOR"),
    ("被動", "PASSIVE"),
    ("伺服器", "AI_SERVER"),
    ("筆電", "NB"),
    ("主機板", "MOTHERBOARD"),
    ("工業電腦", "IPC"),
    ("生技", "BIOPHARMA"),
    ("製藥", "BIOPHARMA"),
    ("醫材", "DEVICE"),
    ("機器人", "ROBOTICS"),
    ("無人機", "DRONE"),
    ("國防", "DEFENSE"),
    ("衛星", "SATELLITE"),
    ("面板", "PANEL"),
    ("偏光", "POLARIZER"),
    ("機械", "MACHINERY"),
    ("自動化", "AUTOMATION"),
    ("電纜", "CABLE"),
    ("電線", "CABLE"),
)


def load_listed_names(path: Path | None = None) -> list[tuple[str, str]]:
    target = path or LISTED_NAMES_PATH
    if not target.exists():
        return []
    rows: list[tuple[str, str]] = []
    for line in target.read_text(encoding="utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        parts = line.split(",", 2)
        if len(parts) < 2:
            continue
        sid, name = parts[0].strip(), parts[1].strip()
        if is_common_stock(sid):
            rows.append((sid, name))
    return rows


def classify_coverage(
    security_id: str,
    name: str,
    *,
    already_mapped: bool,
) -> list[tuple[str, str, float]]:
    """Return (theme_id, rationale, confidence) extra assignments."""
    out: list[tuple[str, str, float]] = []
    seen: set[str] = set()
    if not already_mapped:
        theme = PREFIX_THEME.get(str(security_id)[:2])
        if theme:
            out.append((theme, f"TW listed-code prefix {security_id[:2]} → {theme}", PREFIX_CONFIDENCE))
            seen.add(theme)
    for keyword, theme in NAME_RULES:
        if keyword in name and theme not in seen:
            out.append((theme, f"name keyword {keyword} → {theme}", KEYWORD_CONFIDENCE))
            seen.add(theme)
    return out


def coverage_assignments(
    curated_ids: set[str],
    universe: list[tuple[str, str]] | None = None,
) -> dict[str, list[tuple[str, str, float]]]:
    """theme_id -> list of (security_id, rationale, confidence)."""
    names = universe if universe is not None else load_listed_names()
    extra: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    for sid, name in names:
        if not is_common_stock(sid):
            continue
        for theme, rationale, conf in classify_coverage(sid, name, already_mapped=sid in curated_ids):
            extra[theme].append((sid, rationale, conf))
    return extra

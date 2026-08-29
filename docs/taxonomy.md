# Theme taxonomy v2-tax-2

Hierarchical mapping: **L1 industry → L2 supply chain → L3 investment theme**.
Membership is many-to-many. Curated tickers attach at the most specific node and
roll up to parents. Remaining common stocks are covered by TW listed-code
industry prefixes and conservative name keywords (`backend/app/taxonomy/coverage.py`).

Electronics prefixes (23/24/30/61/…) attach at **L1 `ELEC`** so they count toward
market coverage without diluting L2/L3 rotation ranks. Homogeneous old-economy
prefixes attach at L2 (cement, steel, food, …).

Versioning:

- `mapping_version` on catalog, themes, membership links, and sector metrics
- Sector metric primary key is `(theme_id, trade_date, mapping_version)`
- Recompute replaces **only** the current `mapping_version` rows
- `effective_from` / `effective_to` on catalog and membership
- Changing today’s mapping (new version) does not delete prior version snapshots

Default ranking excludes:

- `coverage_ratio < 0.80`
- `member_count < MIN_THEME_MEMBERS` (default 3), unless `concentrated_ok`
- L1 industries (too coarse); default lists are L2 + L3

This catalog is **not** an official TWSE/TPEx industry file and is not claimed
production-complete. `production_ready` remains false until coverage and
reviewers say otherwise.

Source files: `backend/app/taxonomy/v2_catalog.py` (canonical curated tree),
`backend/app/taxonomy/coverage.py` (prefix/name expansion),
`data/theme_mapping/v2/listed_names.csv` (common-stock name snapshot used for
coverage), and `data/theme_mapping/v2/` (exported CSV + metadata).

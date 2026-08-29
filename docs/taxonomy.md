# Theme taxonomy v2-tax-1

Hierarchical mapping: **L1 industry → L2 supply chain → L3 investment theme**.
Membership is many-to-many. Tickers are attached at the most specific node and
rolled up to parents.

Versioning:

- `mapping_version` on catalog, themes, membership links, and sector metrics
- `effective_from` / `effective_to` on catalog and membership
- Recompute only replaces `sector_daily_metrics` rows for the **same**
  `mapping_version`. An older version’s snapshots stay unless that version is
  recomputed.

Default ranking excludes:

- `coverage_ratio < 0.80`
- `member_count < MIN_THEME_MEMBERS` (default 3), unless `concentrated_ok`
- L1 industries (too coarse); default lists are L2 + L3

This catalog is **not** an official TWSE/TPEx industry file and is not claimed
production-complete. `production_ready` remains false until coverage and
reviewers say otherwise.

Source files: `backend/app/taxonomy/v2_catalog.py` (canonical) and
`data/theme_mapping/v2/` (exported CSV + metadata).

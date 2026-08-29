# Cursor Task — Stage 11 Dashboard Preview

## Goal
Build a first interactive dashboard preview so the product owner can inspect layout, visual hierarchy, and behavior before production UI work.

This is a PREVIEW milestone, not final frontend architecture. Do not merge PR #1 and do not modify core Stage 1–10 scoring formulas or taxonomy semantics.

Base branch state: Stage 10 head `d930f311c12087b8faff7e8b1f9c28ce76538ab7`, taxonomy mapping version `v2-tax-2`.
Work only on branch `feat/v1-dashboard-preview`.

## Technical direction
Use Next.js + React + TypeScript unless the repository already contains an equivalent frontend convention. Prefer a lightweight chart library suitable for interactive scatter/bubble charts. Keep dependencies minimal.

Create `frontend/` as a separate app. It should consume the existing FastAPI backend. If the existing API lacks fields needed by the preview, add the smallest backward-compatible read-only API extensions on this branch only.

Do not fabricate market signals in the primary runtime path. Prefer real persisted Stage 10 data. A clearly marked demo fallback is acceptable only when the backend database is unavailable, and it must be visually labeled `DEMO DATA`.

## Primary screen
Create one dense dark-theme financial dashboard called `TW Market Radar`.

Top header:
- Product title
- data as-of date
- mapping version (`v2-tax-2`)
- `production_ready=false` badge
- backend connection status
- L1 / L2 / L3 filter controls
- search by theme id/name

### 1. Four-quadrant bubble chart
This is the hero view.

Axes:
- X = `flow_5d`
- Y = `acceleration`
- bubble size = 20D average trading value or closest currently stored 20D trading-value metric

Quadrants:
- upper-right: Strong Inflow / Tide
- lower-right: Slowing Inflow / Rotation
- upper-left: Improving Outflow / Watch
- lower-left: Accelerating Outflow / Exit

Behavior:
- default to L2 + L3 rank-eligible themes
- quadrant background should be subtle, not overpowering
- hover tooltip must show theme name/id, level, Rotation Score, Emerging Metric, flow_5d, acceleration, price momentum, lifecycle, coverage
- click bubble selects theme globally
- selected bubble is visually emphasized
- zoom/pan is optional; responsive scale is required
- provide `Top Rotation`, `Top Emerging`, and `Divergence` quick-filter chips

### 2. Ranking panels
Show three synchronized lists/cards:

A. Top Rotation Score
B. Top Emerging Rotation
C. Divergence Candidates

Each row should show:
- rank
- theme name
- theme level
- score / emerging metric as relevant
- quadrant
- lifecycle
- small direction indicator based on recent score path where available

Clicking any row selects the same theme in the bubble chart and detail panel.

### 3. Theme detail panel
For selected theme show:
- theme id + Chinese/name label
- L1/L2/L3 level
- parent chain / breadcrumb
- member count
- priced member count
- flow member count
- coverage ratio
- low-coverage warning
- flow_5d
- avg_5d
- avg_20d
- acceleration
- normalized_flow
- price_momentum
- volume_expansion
- continuity
- margin_signal
- rotation_score
- emerging_metric
- quadrant
- lifecycle
- divergence flag

Also show top constituent stocks if current API exposes them. If not, add a minimal read-only endpoint or use existing sector detail endpoint.

### 4. 20-session history / playback
Add a time-series panel for the selected theme with the latest 20 trading sessions.

At minimum plot:
- Rotation Score
- Emerging Metric

Optional secondary toggles:
- flow_5d
- acceleration
- price momentum

Add a date slider / playback control across available recent sessions. When the selected date changes:
- bubble chart updates to that historical session
- rankings update to that session
- selected theme detail updates to that session

A simple play/pause control is enough for preview.

### 5. Taxonomy navigation
Provide filters for:
- All rank-eligible L2/L3
- L1 only
- L2 only
- L3 only

Allow filtering by parent L1 industry.

Keep L1 roll-ups visible but do not let broad L1 categories crowd default L2/L3 ranking view.

### 6. Data quality UX
Display warnings clearly but compactly:
- `production_ready=false`
- mapping version
- low coverage themes
- estimated institutional notional (`shares × close`) caveat
- data timestamp/as-of session

Never present low-coverage themes in default top ranks.

## Visual direction
Dark professional trading dashboard, not flashy crypto styling.

Prefer:
- charcoal/near-black background
- compact cards
- high information density
- readable typography
- positive/negative semantics that remain understandable without relying only on color
- restrained motion
- desktop-first at 1440px, still usable around 1024px

The purpose is to inspect behavior, not pixel-perfect branding.

## API behavior
Inspect the existing FastAPI endpoints first.

Existing baseline endpoints include:
- `/health`
- `/api/v1/radar/sectors/latest`
- `/api/v1/radar/emerging`
- `/api/v1/radar/sectors/{theme_id}`
- `/api/v1/radar/sectors/{theme_id}/history`
- `/api/v1/radar/divergence`

If Stage 10 introduced mapping-version/level metadata elsewhere, reuse it.

If needed, add query parameters such as:
- `trade_date`
- `mapping_version`
- `theme_level`
- `parent_theme_id`
- `rank_eligible`

Do not break existing endpoints/tests.

## Preview acceptance behavior
The product owner should be able to:
1. Open the dashboard and immediately understand which themes are strong, emerging, slowing, or exiting.
2. Click `AI_CPO` (or any theme) in a leaderboard and see the corresponding bubble selected.
3. Click a bubble and see the complete metric detail.
4. Switch L2/L3 filters without a full page reload.
5. Move the historical date slider and watch bubbles/rankings change by session.
6. See low-coverage/data-quality warnings.
7. Inspect latest 20-session score behavior for a selected theme.

## Validation
Before reporting completion:
- run backend pytest and keep all existing tests green
- run frontend lint/typecheck/build
- start backend + frontend locally
- verify at least one real Stage 10 dataset view using `v2-tax-2`
- manually test bubble click -> detail sync
- manually test leaderboard click -> bubble/detail sync
- manually test date slider/playback
- manually test L1/L2/L3 filters

## Deliverable report
Return:
- changed files
- exact branch/commit
- frontend run commands
- backend run commands
- screenshot(s) or a concise description of actual rendered layout if screenshots cannot be attached
- API extensions made
- interactions verified
- frontend lint/typecheck/build result
- backend pytest result
- known preview limitations

Do not merge either PR/branch. This milestone is for visual and behavioral review only.
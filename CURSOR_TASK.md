# Cursor Development Task — TW-Market-Radar V1

## Objective
Build a production-oriented Taiwan stock sector rotation radar. Start with the backend calculation/data pipeline. Do not build a mock-only UI before formulas and ingestion are tested.

## Product logic
Daily stock institutional flow:

`institutional_flow = foreign_net_amount + investment_trust_net_amount + dealer_net_amount`

Aggregate stock flows by sector/theme. One stock may belong to multiple themes.

Core sector metrics:
- `flow_5d = sum(last 5 trading sessions sector institutional flow)`
- `avg_5d = flow_5d / 5`
- `avg_20d = sum(last 20 sessions flow) / 20`
- `acceleration = avg_5d - avg_20d`
- `normalized_flow = flow_5d / 20d_average_trading_value` (guard zero/missing denominator)
- price momentum
- volume expansion
- institutional buying continuity
- margin-financing signal

Four-quadrant state:
- flow_5d > 0 and acceleration > 0: STRONG_INFLOW / Tide
- flow_5d > 0 and acceleration <= 0: SLOWING_INFLOW / Rotation
- flow_5d <= 0 and acceleration > 0: IMPROVING_OUTFLOW / Watch
- flow_5d <= 0 and acceleration <= 0: ACCELERATING_OUTFLOW / Exit

Lifecycle classification:
- EARLY
- CONFIRMED
- CROWDED
- EXIT

Implement a configurable Rotation Score from 0–100. Initial default weights:
- institutional flow strength: 30%
- acceleration: 25%
- price momentum: 15%
- volume expansion: 15%
- continuity: 10%
- margin signal: 5%

Do not combine raw metrics with incompatible units directly. Normalize each factor robustly across the comparison universe/date before weighting. Keep scoring functions deterministic and configurable.

Add an Emerging Rotation metric that rewards positive score acceleration (e.g. sector score moving 50 -> 65 -> 78) rather than simply ranking the highest absolute score.

Add flow/price divergence detection to surface sectors/stocks where institutional flow accelerates while price has not materially moved.

## Architecture
Use:
- Python 3.12+
- FastAPI
- pandas or polars
- SQLAlchemy
- SQLite V1 with migration-ready schema for PostgreSQL
- pytest
- pydantic settings/models

Target structure:

```
backend/
  app/
    api/
    core/
    data_providers/
    db/
    models/
    schemas/
    services/
      institutional_flow.py
      rotation_engine.py
      scoring_engine.py
      ranking_engine.py
  tests/
data/
  theme_mapping/
docs/
```

## Data layer
Create an abstract market data provider so TWSE/TPEx implementations are replaceable. No HTTP calls inside scoring/calculation functions.

Represent at minimum:
- securities
- themes/sectors
- security_theme many-to-many mapping
- daily prices/volume/trading value
- daily institutional flows split into foreign / trust / dealer
- daily margin data
- calculated sector metrics/scores

TWSE/TPEx public endpoints may change. Isolate parsing and external schemas inside provider adapters. Add retries/timeouts and explicit errors. Do not silently fabricate missing values.

## V1 API
Design endpoints for:
- health
- latest sector radar
- emerging sectors
- sector detail + constituent rankings
- sector history (at least 20 sessions)
- divergence candidates

## Tests
Unit-test at minimum:
1. institutional flow sum
2. sector aggregation
3. Avg5/Avg20/acceleration
4. all four quadrants including zero boundaries
5. normalization and zero denominator handling
6. Rotation Score bounds 0–100
7. Emerging Rotation ordering
8. many-to-many theme mapping without accidental deduplication
9. missing-data behavior

Use deterministic fixtures; do not require live internet for unit tests.

## Frontend milestone (after backend passes tests)
Next.js/React dashboard:
- four-quadrant bubble chart
- X = 5D institutional net flow
- Y = acceleration
- bubble size = 20D trading value
- sector leaderboard
- Emerging Rotation leaderboard
- flow-in/price-not-moving leaderboard
- sector detail with top stocks
- 20-session playback

## Engineering rules
- Inspect existing repository before editing.
- Keep modules decoupled and typed.
- Prefer small commits by feature.
- Run tests after each major stage.
- Add `.env.example`, `.gitignore`, README setup instructions, and `docs/formula_spec.md`.
- Clearly document assumptions where the original Tide implementation is not public. Do not claim this implementation exactly reproduces proprietary formulas.
- Do not add credentials or paid/proprietary scraped data.

## First execution sequence
1. Scaffold backend/package configuration.
2. Define domain/database models and provider interfaces.
3. Implement pure calculation functions and tests.
4. Implement configurable scoring/ranking and tests.
5. Implement TWSE/TPEx provider adapters.
6. Add persistence and API endpoints.
7. Run full test suite and fix failures.
8. Only then scaffold frontend dashboard.

When finished with each stage, report changed files, test results, unresolved assumptions, and next recommended stage.

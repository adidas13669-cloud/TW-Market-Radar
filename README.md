# TW-Market-Radar

Taiwan stock sector rotation radar focused on institutional fund flows, acceleration, price/volume confirmation, and sector-to-stock ranking.

This V1 engine is an **independent implementation**. It does not claim to match any proprietary commercial formula. See [docs/formula_spec.md](docs/formula_spec.md) for definitions and assumptions.

## V1 goals

- TWSE / TPEx data provider abstraction
- Institutional flow = Foreign + Investment Trust + Dealer
- 5-day flow, Avg5, Avg20, and acceleration
- Normalized flow, price momentum, volume expansion, continuity, margin signal
- Rotation Score (0-100)
- Four-quadrant sector state and lifecycle state
- Emerging sector and top-stock rankings
- FastAPI backend, SQLite for V1
- React/Next.js dashboard in a later frontend milestone

Development starts with the data model and calculation engine before UI work.

## Setup

Requires Python 3.12+.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Run unit tests (no live internet):

```bash
pytest
```

Ingest one trading date (live HTTP; writes `data/raw_payloads/` and SQLite):

```bash
PYTHONPATH=backend python -m app.cli.ingest --date 2026-08-28
```

Backfill a range of weekdays:

```bash
PYTHONPATH=backend python -m app.cli.backfill --start 2026-07-28 --end 2026-08-28
```

Pipeline per date: fetch → validate → normalize to TWD notional → persist raw →
calculate metrics → score universe → persist radar snapshot. Holidays are skipped
without fabricating zeros. Incomplete 20-session history leaves `avg_20d` /
`acceleration` missing until warm-up.

Run the API:

```bash
PYTHONPATH=backend uvicorn app.main:app --reload
```

Health check: `GET /health`.

Radar endpoints (after data is ingested and `recompute` has run):

- `GET /api/v1/radar/sectors/latest`
- `GET /api/v1/radar/emerging`
- `GET /api/v1/radar/sectors/{theme_id}`
- `GET /api/v1/radar/sectors/{theme_id}/history`
- `GET /api/v1/radar/divergence`

Theme membership seed: `data/theme_mapping/seed_themes.csv`.

## Layout

```
backend/app/          FastAPI app, models, providers, engines, CLI ingest
backend/tests/        pytest (fixtures, including trimmed live JSON)
data/theme_mapping/  many-to-many security–theme CSV
data/raw_payloads/   captured exchange JSON (gitignored)
docs/formula_spec.md scoring, units, and verified field maps
```

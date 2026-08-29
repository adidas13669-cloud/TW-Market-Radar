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
backend/app/          FastAPI app, models, providers, engines
backend/tests/        pytest (fixtures, no live HTTP)
data/theme_mapping/  many-to-many security–theme CSV
docs/formula_spec.md scoring and metric definitions
```

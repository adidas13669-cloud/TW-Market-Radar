# TW-Market-Radar

Taiwan stock sector rotation radar focused on institutional fund flows, acceleration, price/volume confirmation, and sector-to-stock ranking.

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

# TW-Market-Radar formula specification (V1)

This document describes the **open V1 implementation**. It does not claim to
reproduce any proprietary “Tide” or commercial sector-rotation product. Where
the original product’s exact formula is unpublished, the rules below are
explicit engineering assumptions.

## Institutional flow

For each listed security and trading session, **after** conversion to TWD notional:

```
institutional_flow = foreign_net_amount
                   + investment_trust_net_amount
                   + dealer_net_amount
```

- If every **share** leg is missing, `institutional_flow` is missing (not zero).
- Published TWSE T86 / TPEx 三大法人 prints are **股數**, never copied into amount columns.
- Canonical TWD = `net_shares * close` with `amount_estimated=true` and `estimation_method=net_shares_times_close`.

## Sector aggregation

Themes are many-to-many. A security in N themes contributes its **full**
session flow, volume, and trading value to **each** of those N themes.
Aggregation never globally deduplicates a security before the theme join.

```
sector_flow[theme, date] = sum(institutional_flow of mapped members)
```

## Rolling flow metrics

Windows use **trading sessions**, not calendar days. Incomplete windows are
missing; they are not filled with partial averages.

| Metric | Definition | Min sessions |
| --- | --- | --- |
| `flow_5d` | sum of last 5 session `sector_flow` | 5 |
| `avg_5d` | `flow_5d / 5` | 5 |
| `avg_20d` | mean of last 20 session `sector_flow` | 20 |
| `acceleration` | `avg_5d - avg_20d` | 20 |

## Normalized flow

```
normalized_flow = flow_5d / trading_value_avg_20d
```

`trading_value_avg_20d` is the 20-session mean of sector trading value (sum of
member `trading_value`). If the denominator is missing or `0`,
`normalized_flow` is missing.

## Price momentum (assumption)

Stock: `close_t / close_{t-5} - 1`. Missing or zero lagged close → missing.

Sector: **equal-weight average** of member 5-session returns. Members without a
valid return that day are omitted, not imputed.

This is not a tradable index and ignores free-float / market cap.

## Volume expansion (assumption)

```
volume_expansion = mean(volume, 5) / mean(volume, 20)
```

Zero or missing 20-session mean volume → missing. Sector volume is the sum of
member volume (again, multi-theme stocks count in each theme).

## Institutional buying continuity (assumption)

Lookback = 10 sessions:

```
continuity = 0.6 * (positive_flow_days / 10)
           + 0.4 * min(consecutive_positive_streak, 10) / 10
```

Requires 10 sessions. Streak resets on a non-positive or missing flow day.

## Margin signal (verified units, 2026-08-28)

TWSE `MI_MARGN` and TPEx `margin_bal` publish **融資餘額 / 增減 in 張 (lots)**,
not TWD. 1 張 = 1,000 shares. Dividing lots by TWD trading value is invalid.

V1 conversion:

```
margin_share_change     = margin_buy_change_lots * 1000
margin_notional_change  = margin_share_change * close     # missing close → missing
margin_signal           = sum(margin_notional_change, 5) / trading_value_avg_20d
```

`margin_signal` is dimensionless (TWD / TWD). Raw lot columns stay on the
margin table and are never scored directly.

## Canonical scoring unit

The radar **only** scores **TWD notional**.

| Stream | Published unit (verified 2026-08-28) | Scoring unit |
| --- | --- | --- |
| Institutional 買賣超 | **股 (shares)** on both TWSE T86 and TPEx 3itrade | `net_shares * close` → TWD, `amount_estimated=true` |
| Price | TWD per share | unchanged |
| Volume `成交股數` | **shares** (not 張). TPEx `flagField=張數` applies to bid/ask size only | shares (ratio) |
| Trading value `成交金額` | **TWD (元)** | TWD |
| Margin 融資 | **張 (lots)** | lots → shares → TWD as above |

Mixing `shares`, `lots`, and `twd_notional` in sector aggregation raises
`UnitMismatchError`. Partial institutional legs stay missing (`None`); they are
never filled with 0 at parse time.

Estimation metadata persisted per row:

- `raw_net_shares`
- `estimated_net_amount`
- `amount_estimated`
- `estimation_method = net_shares_times_close`

## Sign convention (verified)

TWSE and TPEx both use **買賣超 = 買進 − 賣出**. Positive is net institutional
buy. Dealer on both venues is the **合計** print (proprietary + hedge), matching
TWSE field `自營商買賣超股數`.

## Verified live endpoints (2026-08-28)

| Venue | Dataset | URL | Key fields |
| --- | --- | --- | --- |
| TWSE | Quotes | `/rwd/zh/afterTrading/MI_INDEX?response=json&date=YYYYMMDD&type=ALLBUT0999` | table with `證券代號`,`成交股數`,`成交金額`,`收盤價` |
| TWSE | Flow | `/rwd/zh/fund/T86?response=json&date=YYYYMMDD&selectType=ALLBUT0999` | `外陸資買賣超股數(不含外資自營商)`, `投信買賣超股數`, `自營商買賣超股數` (all 股數) |
| TWSE | Margin | `/rwd/zh/marginTrading/MI_MARGN?response=json&date=YYYYMMDD&selectType=STOCK` | duplicated `前日餘額`/`今日餘額` blocks: 融資 then 融券, values in 張 |
| TPEx | Quotes | `/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php` `d=YYY/MM/DD` ROC | `成交股數`, `成交金額(元)`, `收盤` |
| TPEx | Flow | `/web/stock/3insti/daily_trade/3itrade_hedge_result.php` | 7 repeating 買/賣/超 groups; foreign net idx 4, trust 13, dealer total 22 |
| TPEx | Margin | `/web/stock/margin_trading/margin_balance/margin_bal_result.php` | `前資餘額(張)`, `資餘額`, `資買`/`資賣`/`現償` |

Holiday: TWSE `stat` is `很抱歉，沒有符合條件的資料!`. TPEx `stat=ok` with `totalCount=0`.

Remaining uncertainties:

- TPEx 3itrade group headers are positional (duplicate `買進股數` labels). Order is
  assumed to match TWSE T86 (foreign ex-dealer → … → dealer total). Not independently
  labeled in JSON.
- Warrant/ETF rows are ingested when present; theme radar uses `seed_themes.csv`.
- `shares * close` is VWAP-agnostic and slightly disagrees with true notional.

## Data provider contract

- No HTTP inside scoring/calculation modules.
- Transport failures raise `ProviderError` after bounded retries.
- Unexpected payloads raise `ProviderParseError`.
- Empty/`--` numeric cells become `None`, never silent zeros.
- Dated ingest captures raw JSON under `data/raw_payloads/YYYY-MM-DD/` for replay.

TWSE and TPEx public endpoints change without notice. Field maps live only in
`app/data_providers/twse.py` and `tpex.py`.


## Four-quadrant state

Zero is included on the “non-positive” side of each comparison:

| flow_5d | acceleration | Quadrant | Label |
| --- | --- | --- | --- |
| `> 0` | `> 0` | `STRONG_INFLOW` | Tide |
| `> 0` | `<= 0` | `SLOWING_INFLOW` | Rotation |
| `<= 0` | `> 0` | `IMPROVING_OUTFLOW` | Watch |
| `<= 0` | `<= 0` | `ACCELERATING_OUTFLOW` | Exit |

## Rotation Score (0–100)

Raw metrics are **not** mixed in native units. For each `trade_date`, each
factor is converted to an average-rank percentile in `(0, 1]` across the
comparison universe (all themes with a value that day).

Default weights (must sum to 1.0, overridable via env):

| Factor | Weight |
| --- | --- |
| `normalized_flow` | 30% |
| `acceleration` | 25% |
| `price_momentum` | 15% |
| `volume_expansion` | 15% |
| `continuity` | 10% |
| `margin_signal` | 5% |

Missing factors are **skipped** and remaining weights are re-normalized. If no
factor is present, the score is missing. The weighted sum is multiplied by 100
and clipped to `[0, 100]`.

## Emerging Rotation

High absolute score is not enough. V1 (path-only, kept for comparison):

```
change = score_t - score_{t-lag}          # default lag = 5 sessions
convexity = (score_t - score_{t-h}) - (score_{t-h} - score_{t-lag})
            where h = lag // 2
emerging_v1 = change + 0.5 * max(convexity, 0)
```

V1 correctly ranks a rising 50 → 65 → 78 path above a flat 80 → 80 → 80 path.
It also rewards convexity, which made a **one-day spike** with the same 5-session
change outrank a persistent grind (e.g. 40→40→40→40→40→65 vs 40→45→50→55→60→65).

V2 (default) multiplies the path term by how often daily score deltas were
positive over the lookback and subtracts a last-day spike residual versus the
median absolute daily change:

```
pos_share = share of positive daily score deltas in last max(lag, persist_lookback) sessions
spike     = max(last_delta - median(|daily delta|), 0)
emerging  = emerging_v1 * (0.35 + 0.65 * pos_share) - 0.25 * spike
```

On the grind-vs-spike pair above, V1 ranks the spike higher; V2 ranks the grind
higher. Tie-break for ranking is still current `rotation_score`.

## Coverage (data-quality confidence)

Each sector metric stores:

- `member_count` — mapped tickers
- `priced_member_count` — members with a close that session
- `flow_member_count` — members with usable institutional flow that session
- `coverage_ratio` — `min(priced/members, flow/members)`
- `low_coverage` — `coverage_ratio < min_coverage_ratio` (default **0.80**, env `MIN_COVERAGE_RATIO`)

Low-coverage rows are **kept** on the metric table but **excluded** from default
Top Rotation / Emerging / Divergence rankings (`include_low_coverage=true` to include).

## Theme mapping metadata

Seed mapping is **not** a production taxonomy. Catalog fields:

- `mapping_version`
- `mapping_source`
- `effective_from`
- `production_ready` (false for `seed-v1`)

## Lifecycle (assumption)

Deterministic rules, evaluated after the score exists:

1. `ACCELERATING_OUTFLOW` → `EXIT`
2. `SLOWING_INFLOW` and score ≥ 65 → `CROWDED`
3. `STRONG_INFLOW` and score ≥ 55 and price momentum > 2% → `CONFIRMED`
4. `STRONG_INFLOW` or `IMPROVING_OUTFLOW` otherwise → `EARLY`
5. remaining `SLOWING_INFLOW` with score ≥ 55 → `CONFIRMED`, else `EXIT`

The 2% “price has moved” threshold is an assumption for V1.

## Flow / price divergence (assumption)

A sector or stock is flagged when:

```
acceleration > 0 and flow_5d > 0 and abs(price_momentum) <= 0.02
```

Missing any input → not flagged (no invented confirmation).

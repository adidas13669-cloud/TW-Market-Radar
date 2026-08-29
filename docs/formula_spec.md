# TW-Market-Radar formula specification (V1)

This document describes the **open V1 implementation**. It does not claim to
reproduce any proprietary “Tide” or commercial sector-rotation product. Where
the original product’s exact formula is unpublished, the rules below are
explicit engineering assumptions.

## Institutional flow

For each listed security and trading session:

```
institutional_flow = foreign_net_amount
                   + investment_trust_net_amount
                   + dealer_net_amount
```

- If every leg is missing, `institutional_flow` is missing (not zero).
- If at least one leg is present, absent legs contribute `0` for that session.
- TWSE T86 / TPEx 三大法人 tables often publish **shares**, not notional.
  Adapters store shares as published. Amounts are left missing unless the
  source provides notional. Optional estimation (`shares * close`) is flagged
  `amount_estimated=true` and is never applied silently inside scoring.

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

## Margin signal (assumption)

TWSE/TPEx margin tables are used as a **retail-participation** proxy:

```
margin_signal = sum(margin_buy_change, 5) / trading_value_avg_20d
```

Missing/zero denominator → missing. Lifecycle crowding uses this together with
score and slowing inflow; the Rotation Score treats a higher value as a mild
positive factor (5% default weight). This is a documented choice, not a claim
that retail financing is “smart money”.

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

## Emerging Rotation (assumption)

High absolute score is not enough. For each theme’s score history:

```
change = score_t - score_{t-lag}          # default lag = 5 sessions
convexity = (score_t - score_{t-h}) - (score_{t-h} - score_{t-lag})
            where h = lag // 2
emerging_metric = change + 0.5 * max(convexity, 0)
```

Themes with a path such as 50 → 65 → 78 rank above a high but flat 80 → 80 → 80.
Tie-break: current `rotation_score`.

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

## Data provider contract

- No HTTP inside scoring/calculation modules.
- Transport failures raise `ProviderError` after bounded retries.
- Unexpected payloads raise `ProviderParseError`.
- Empty/`--` numeric cells become `None`, never silent zeros.

TWSE and TPEx public endpoints change without notice. Field maps live only in
`app/data_providers/twse.py` and `tpex.py`.

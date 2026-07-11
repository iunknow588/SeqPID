# Market PID Validation Report

## Scope

This report records the market breadth and relative market PID口径 used by the current batch.

## Market Breadth

- trade_date: `20260709`
- up_count: `0`
- down_count: `0`
- breadth_ratio: `0.000000`
- breadth_balance: `0.000000`
- market_regime: `震荡中性`

## PID Aggregates

- p_mean / p_median / p_std: `-0.000137` / `-0.000006` / `0.003599`
- i_mean / i_median / i_std: `0.000204` / `0.000045` / `0.001735`
- d_mean / d_median / d_std: `0.000974` / `0.000550` / `0.001549`

## Aggregation Contract

- preferred source: per-stock `c_p / c_i / c_d` from PID decomposition
- fallback source: heuristic summary only when PID components are unavailable
- rule-layer flows such as `Q_rule / R_seed` are not treated as market external-force outputs

## Relative Metrics Contract

- `p_rel_market = (p_value - p_median) / max(p_std, eps)`
- `i_rel_market = (i_value - i_median) / max(i_std, eps)`
- `d_rel_market = (d_value - d_median) / max(d_std, eps)`
- `trend_vs_market` is diagnostic only and does not change submission CSV columns.

## Diagnostics

```json
{
  "sample_count": 100,
  "pid_result_source_count": 100,
  "pid_component_source_count": 100,
  "heuristic_fallback_source_count": 0,
  "pattern_counts": {
    "日内套利": 99,
    "盘中诱多": 1
  },
  "capital_counts": {
    "量化": 90,
    "游资": 10
  },
  "intention_counts": {
    "卖出": 68,
    "买入": 32
  }
}
```

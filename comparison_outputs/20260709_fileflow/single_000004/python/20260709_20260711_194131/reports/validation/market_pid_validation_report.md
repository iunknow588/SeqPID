# Market PID Validation Report

## Scope

This report records the market breadth and relative market PID口径 used by the current batch.

## Market Breadth

- trade_date: `20260709`
- up_count: `1`
- down_count: `0`
- breadth_ratio: `1.000000`
- breadth_balance: `1.000000`
- market_regime: `震荡中性`

## PID Aggregates

- p_mean / p_median / p_std: `-0.000000` / `-0.000000` / `0.000000`
- i_mean / i_median / i_std: `0.000000` / `0.000000` / `0.000000`
- d_mean / d_median / d_std: `0.009072` / `0.009072` / `0.000000`

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
  "sample_count": 1,
  "pid_result_source_count": 1,
  "pid_component_source_count": 1,
  "heuristic_fallback_source_count": 0,
  "pattern_counts": {
    "分时脉冲": 1
  },
  "capital_counts": {
    "量化": 1
  },
  "intention_counts": {
    "卖出": 1
  }
}
```

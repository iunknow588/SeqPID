# Market PID Validation Report

## Scope

This report records the market breadth and relative market PID口径 used by the current batch.

## Market Breadth

- trade_date: `20260710`
- up_count: `59`
- down_count: `34`
- breadth_ratio: `1.735294`
- breadth_balance: `0.268817`
- market_regime: `震荡中性`

## PID Aggregates

- p_mean / p_median / p_std: `0.000063` / `-0.000493` / `0.005002`
- i_mean / i_median / i_std: `0.000035` / `-0.000005` / `0.001996`
- d_mean / d_median / d_std: `0.000715` / `0.000271` / `0.001399`

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
  "sample_count": 97,
  "pid_result_source_count": 97,
  "pid_component_source_count": 97,
  "heuristic_fallback_source_count": 0,
  "pattern_counts": {
    "对倒拉升": 35,
    "日内套利": 10,
    "盘中诱多": 18,
    "尾盘突袭": 16,
    "连续小单推升": 10,
    "分时脉冲": 1,
    "大单吸筹": 7
  },
  "capital_counts": {
    "量化": 68,
    "游资": 29
  },
  "intention_counts": {
    "买入": 45,
    "卖出": 52
  }
}
```

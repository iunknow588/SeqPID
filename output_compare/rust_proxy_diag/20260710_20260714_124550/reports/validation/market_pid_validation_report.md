# Market PID Validation Report

## Scope

This report records the market breadth and relative market PID contract used by the current batch.

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

## Diagnostics

```json
{
  "capital_counts": {
    "游资": 29,
    "量化": 68
  },
  "heuristic_fallback_source_count": 0,
  "intention_counts": {
    "买入": 45,
    "卖出": 52
  },
  "pattern_counts": {
    "分时脉冲": 1,
    "大单吸筹": 7,
    "对倒拉升": 35,
    "尾盘突袭": 16,
    "日内套利": 10,
    "盘中诱多": 18,
    "连续小单推升": 10
  },
  "pid_result_source_count": 97,
  "sample_count": 97
}
```

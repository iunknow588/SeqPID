# Market Regime Report

- trade_date: `20260709`
- market_regime: `震荡中性`
- up_count: `0`
- down_count: `0`
- breadth_ratio: `0.0000`
- breadth_balance: `0.0000`

## PID Summary

- P: mean `-0.0001`, median `-0.0000`, std `0.0036`
- I: mean `0.0002`, median `0.0000`, std `0.0017`
- D: mean `0.0010`, median `0.0006`, std `0.0015`

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

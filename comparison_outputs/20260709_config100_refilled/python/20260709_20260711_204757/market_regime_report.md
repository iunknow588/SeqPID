# Market Regime Report

- trade_date: `20260709`
- market_regime: `弱趋势上行`
- up_count: `61`
- down_count: `39`
- breadth_ratio: `1.5641`
- breadth_balance: `0.2200`

## PID Summary

- P: mean `0.0005`, median `0.0005`, std `0.0033`
- I: mean `0.0003`, median `0.0000`, std `0.0023`
- D: mean `0.0009`, median `0.0006`, std `0.0012`

## Diagnostics

```json
{
  "sample_count": 100,
  "pid_result_source_count": 100,
  "pid_component_source_count": 100,
  "heuristic_fallback_source_count": 0,
  "pattern_counts": {
    "对倒拉升": 29,
    "尾盘突袭": 7,
    "连续小单推升": 1,
    "日内套利": 42,
    "分时脉冲": 6,
    "大单吸筹": 11,
    "盘中诱多": 4
  },
  "capital_counts": {
    "量化": 71,
    "游资": 29
  },
  "intention_counts": {
    "卖出": 52,
    "买入": 48
  }
}
```

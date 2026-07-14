# Market Regime Report

- trade_date: `20260710`
- market_regime: `震荡中性`
- up_count: `59`
- down_count: `34`
- breadth_ratio: `1.7353`
- breadth_balance: `0.2688`

## PID Summary

- P: mean `0.0001`, median `-0.0005`, std `0.0050`
- I: mean `0.0000`, median `-0.0000`, std `0.0020`
- D: mean `0.0007`, median `0.0003`, std `0.0014`

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

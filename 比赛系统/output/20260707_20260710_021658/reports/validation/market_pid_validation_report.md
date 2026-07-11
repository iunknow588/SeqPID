# Market PID Validation Report

## Scope

This report records the market breadth and relative market PID口径 used by the current batch.

## Market Breadth

- trade_date: `20260707`
- up_count: `20`
- down_count: `78`
- breadth_ratio: `0.256410`
- breadth_balance: `-0.591837`
- market_regime: `弱趋势下跌`

## PID Aggregates

- p_mean / p_median / p_std: `0.227971` / `0.247370` / `0.059815`
- i_mean / i_median / i_std: `0.083517` / `0.072407` / `0.029253`
- d_mean / d_median / d_std: `0.722773` / `0.696199` / `0.052039`

## Relative Metrics Contract

- `p_rel_market = (p_value - p_median) / max(p_std, eps)`
- `i_rel_market = (i_value - i_median) / max(i_std, eps)`
- `d_rel_market = (d_value - d_median) / max(d_std, eps)`
- `trend_vs_market` is diagnostic only and does not change submission CSV columns.

## Diagnostics

```json
{
  "sample_count": 100,
  "pattern_counts": {
    "对倒拉升": 30,
    "尾盘突袭": 4,
    "盘中诱多": 45,
    "日内套利": 7,
    "压单吸货": 1,
    "分时脉冲": 7,
    "大单吸筹": 5,
    "连续小单推升": 1
  },
  "capital_counts": {
    "游资": 39,
    "散户": 26,
    "量化": 35
  },
  "intention_counts": {
    "买入": 54,
    "卖出": 46
  }
}
```

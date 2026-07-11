# Market PID Validation Report

## Scope

This report records the market breadth and relative market PID口径 used by the current batch.

## Market Breadth

- trade_date: `20260708`
- up_count: `26`
- down_count: `49`
- breadth_ratio: `0.530612`
- breadth_balance: `-0.306667`
- market_regime: `弱趋势下跌`

## PID Aggregates

- p_mean / p_median / p_std: `0.199535` / `0.224985` / `0.073780`
- i_mean / i_median / i_std: `0.085544` / `0.077218` / `0.023891`
- d_mean / d_median / d_std: `0.785305` / `0.698601` / `0.127799`

## Relative Metrics Contract

- `p_rel_market = (p_value - p_median) / max(p_std, eps)`
- `i_rel_market = (i_value - i_median) / max(i_std, eps)`
- `d_rel_market = (d_value - d_median) / max(d_std, eps)`
- `trend_vs_market` is diagnostic only and does not change submission CSV columns.

## Diagnostics

```json
{
  "sample_count": 75,
  "pattern_counts": {
    "对倒拉升": 27,
    "盘中诱多": 24,
    "日内套利": 10,
    "分时脉冲": 7,
    "压单吸货": 1,
    "尾盘突袭": 5,
    "大单吸筹": 1
  },
  "capital_counts": {
    "散户": 16,
    "游资": 26,
    "量化": 33
  },
  "intention_counts": {
    "卖出": 46,
    "买入": 29
  }
}
```

# Market PID Validation Report

## Scope

This report records the market breadth and relative market PID口径 used by the current batch.

## Market Breadth

- trade_date: `20260709`
- up_count: `61`
- down_count: `39`
- breadth_ratio: `1.564103`
- breadth_balance: `0.220000`
- market_regime: `弱趋势上行`

## PID Aggregates

- p_mean / p_median / p_std: `0.000479` / `0.000454` / `0.003340`
- i_mean / i_median / i_std: `0.000328` / `0.000029` / `0.002333`
- d_mean / d_median / d_std: `0.000932` / `0.000551` / `0.001152`

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
    "买入": 49,
    "卖出": 51
  }
}
```

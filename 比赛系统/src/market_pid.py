from __future__ import annotations

from statistics import mean, median, pstdev

from schemas import DailySample, MarketPidSnapshot, PatternResult, PredictResult


REGIME_STRONG_UP = "强趋势上行"
REGIME_WEAK_UP = "弱趋势上行"
REGIME_RISK_OFF = "风险偏好退潮"
REGIME_WEAK_DOWN = "弱趋势下跌"
REGIME_SIDEWAYS = "震荡中性"

TREND_STRONGER = "强于市场"
TREND_FOLLOW = "跟随市场"
TREND_WEAKER = "弱于市场"
TREND_COUNTER = "逆势强股"
TREND_RESILIENT = "抗跌"
TREND_NOISY = "高噪声扰动"


def _safe_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _safe_median(values: list[float]) -> float:
    return median(values) if values else 0.0


def _safe_std(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def _clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _regime_from_scores(breadth_balance: float, p_median: float, i_median: float, d_median: float) -> str:
    if breadth_balance > 0.30 and p_median > 0.10 and i_median > 0.20:
        return REGIME_STRONG_UP
    if breadth_balance > 0.10 and p_median >= 0.0:
        return REGIME_WEAK_UP
    if breadth_balance < -0.30 and p_median < -0.10:
        return REGIME_RISK_OFF
    if breadth_balance < -0.10:
        return REGIME_WEAK_DOWN
    if d_median > 0.45:
        return REGIME_SIDEWAYS
    return REGIME_SIDEWAYS


def estimate_market_pid(
    samples: list[DailySample],
    pattern_results: list[PatternResult],
    predict_results: list[PredictResult],
    config: dict,
) -> MarketPidSnapshot:
    del config
    p_values: list[float] = []
    i_values: list[float] = []
    d_values: list[float] = []
    up_count = 0
    down_count = 0

    pattern_counts: dict[str, int] = {}
    capital_counts: dict[str, int] = {}
    intention_counts: dict[str, int] = {}

    for result in pattern_results:
        pattern_counts[result.pattern_type] = pattern_counts.get(result.pattern_type, 0) + 1
    for result in predict_results:
        capital_counts[result.capital_type] = capital_counts.get(result.capital_type, 0) + 1
        intention_counts[result.capital_intention] = intention_counts.get(result.capital_intention, 0) + 1

    for sample in samples:
        summary = sample.feature_summary
        net_direction = float(summary.get("net_direction", 0.0))
        burst_ratio = float(summary.get("burst_ratio", 0.0))
        cancel_ratio = float(summary.get("cancel_ratio", 0.0))
        price_impact = float(summary.get("price_impact", 0.0))
        tail_ratio = float(summary.get("tail_ratio", 0.0))
        bid_support = float(summary.get("bid_support", 0.0))
        ask_pressure = float(summary.get("ask_pressure", 0.0))

        p_value = _clamp(net_direction * 0.6 + min(price_impact / 0.02, 1.0) * 0.25 + tail_ratio * 0.15)
        i_value = _clamp(burst_ratio * 0.55 + max(net_direction, 0.0) * 0.25 + tail_ratio * 0.20)
        d_value = _clamp(
            cancel_ratio * 0.50 + max(ask_pressure - bid_support, 0.0) * 0.30 + (1.0 - abs(net_direction)) * 0.20,
            0.0,
            1.0,
        )

        summary["p_value"] = p_value
        summary["i_value"] = i_value
        summary["d_value"] = d_value

        p_values.append(p_value)
        i_values.append(i_value)
        d_values.append(d_value)

        if net_direction > 0:
            up_count += 1
        elif net_direction < 0:
            down_count += 1

    market_up_candidates = [
        int(sample.feature_summary.get("up_count_market", 0))
        for sample in samples
        if sample.feature_summary.get("up_count_market", 0)
    ]
    market_down_candidates = [
        int(sample.feature_summary.get("down_count_market", 0))
        for sample in samples
        if sample.feature_summary.get("down_count_market", 0)
    ]
    if market_up_candidates and market_down_candidates:
        up_count = int(median(market_up_candidates))
        down_count = int(median(market_down_candidates))

    breadth_ratio = up_count / down_count if down_count > 0 else float(up_count) if up_count > 0 else 0.0
    breadth_balance = (up_count - down_count) / (up_count + down_count) if (up_count + down_count) > 0 else 0.0

    snapshot = MarketPidSnapshot(
        trade_date=samples[0].transaction_date if samples else "",
        up_count=up_count,
        down_count=down_count,
        breadth_ratio=breadth_ratio,
        breadth_balance=breadth_balance,
        p_mean=_safe_mean(p_values),
        p_median=_safe_median(p_values),
        p_std=_safe_std(p_values),
        i_mean=_safe_mean(i_values),
        i_median=_safe_median(i_values),
        i_std=_safe_std(i_values),
        d_mean=_safe_mean(d_values),
        d_median=_safe_median(d_values),
        d_std=_safe_std(d_values),
        market_regime=_regime_from_scores(
            breadth_balance,
            _safe_median(p_values),
            _safe_median(i_values),
            _safe_median(d_values),
        ),
        diagnostics={
            "sample_count": len(samples),
            "pattern_counts": pattern_counts,
            "capital_counts": capital_counts,
            "intention_counts": intention_counts,
        },
    )
    return snapshot


def attach_market_relative_metrics(
    samples: list[DailySample],
    predict_results: list[PredictResult],
    snapshot: MarketPidSnapshot,
) -> None:
    sample_map = {sample.stock_code: sample for sample in samples}
    p_std = snapshot.p_std if snapshot.p_std > 1e-8 else 1.0
    i_std = snapshot.i_std if snapshot.i_std > 1e-8 else 1.0
    d_std = snapshot.d_std if snapshot.d_std > 1e-8 else 1.0

    for result in predict_results:
        sample = sample_map.get(result.stock_code)
        if sample is None:
            continue
        summary = sample.feature_summary
        p_rel = (float(summary.get("p_value", 0.0)) - snapshot.p_median) / p_std
        i_rel = (float(summary.get("i_value", 0.0)) - snapshot.i_median) / i_std
        d_rel = (float(summary.get("d_value", 0.0)) - snapshot.d_median) / d_std
        trend_score = 0.45 * p_rel + 0.35 * i_rel - 0.20 * d_rel

        if snapshot.market_regime in {REGIME_STRONG_UP, REGIME_WEAK_UP}:
            trend_vs_market = TREND_STRONGER if trend_score > 0.8 else TREND_FOLLOW if trend_score > -0.3 else TREND_WEAKER
        elif snapshot.market_regime in {REGIME_WEAK_DOWN, REGIME_RISK_OFF}:
            trend_vs_market = TREND_COUNTER if trend_score > 0.8 else TREND_RESILIENT if trend_score > 0.0 else TREND_WEAKER
        else:
            trend_vs_market = TREND_STRONGER if trend_score > 0.8 else TREND_NOISY if d_rel > 1.0 else TREND_FOLLOW

        result.debug_info.update(
            {
                "p_rel_market": round(p_rel, 4),
                "i_rel_market": round(i_rel, 4),
                "d_rel_market": round(d_rel, 4),
                "trend_vs_market": trend_vs_market,
                "market_regime": snapshot.market_regime,
            }
        )

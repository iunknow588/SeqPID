from __future__ import annotations

from schemas import DailySample, PatternResult


def _to_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def predict_pattern(sample: DailySample, config: dict, label_dict: dict) -> PatternResult:
    del label_dict
    summary = sample.feature_summary

    deal_amount = _to_float(summary.get("deal_amount"))
    close_return = _to_float(summary.get("close_return"))
    open_return = _to_float(summary.get("open_return"))
    intraday_range = _to_float(summary.get("intraday_range"))
    close_strength = _to_float(summary.get("close_strength"))
    cancel_ratio = _to_float(summary.get("cancel_ratio"))
    burst_ratio = _to_float(summary.get("burst_ratio"))
    bid_support = _to_float(summary.get("bid_support"))
    ask_pressure = _to_float(summary.get("ask_pressure"))
    tail_ratio = _to_float(summary.get("tail_ratio"))
    last15_return = _to_float(summary.get("last15_return"))
    avg_trade_size = _to_float(summary.get("avg_trade_size"))
    order_buy_ratio = _to_float(summary.get("order_buy_ratio"), 0.5)
    directional_efficiency = _to_float(summary.get("directional_efficiency"))
    reversal_strength = _to_float(summary.get("reversal_strength"))

    forced_label = _detect_obvious_pattern(summary)
    if forced_label:
        return PatternResult(
            stock_code=sample.stock_code,
            transaction_date=sample.transaction_date,
            pattern_type=forced_label,
            pattern_explanation=render_pattern_explanation(forced_label, summary),
            pattern_score=0.86,
            prototype_id=f"rule::{forced_label}",
        )

    amount_score = _clip01(deal_amount / 1_000_000_000.0)
    range_score = _clip01(intraday_range / 0.08)
    up_score = _clip01(close_return / 0.05)
    down_score = _clip01(-close_return / 0.05)
    open_jump_score = _clip01(abs(open_return) / 0.03)
    close_top_score = _clip01((close_strength - 0.55) / 0.45)
    close_bottom_score = _clip01((0.45 - close_strength) / 0.45)
    buy_bias_score = _clip01((order_buy_ratio - 0.50) / 0.18)
    sell_bias_score = _clip01((0.50 - order_buy_ratio) / 0.18)
    small_order_score = _clip01((12_000.0 - avg_trade_size) / 10_000.0)
    large_order_score = _clip01((avg_trade_size - 8_000.0) / 12_000.0)
    tail_up_score = _clip01(last15_return / 0.006)
    tail_down_score = _clip01(-last15_return / 0.006)
    tail_flow_score = _clip01((tail_ratio - 0.08) / 0.10)
    mid_close_score = 1.0 - _clip01(abs(close_strength - 0.5) / 0.4)
    neutral_close_score = 1.0 - _clip01(abs(close_return) / 0.02)
    reversal_up_score = _clip01(reversal_strength / 0.03)
    reversal_down_score = _clip01(-reversal_strength / 0.03)

    candidate_scores = {
        "尾盘突袭": tail_up_score * 0.34 + tail_flow_score * 0.22 + close_top_score * 0.22 + up_score * 0.12 + amount_score * 0.10,
        "大单吸筹": up_score * 0.25 + buy_bias_score * 0.20 + close_top_score * 0.20 + large_order_score * 0.20 + amount_score * 0.15,
        "日内套利": range_score * 0.35 + neutral_close_score * 0.30 + mid_close_score * 0.20 + (1.0 - abs(order_buy_ratio - 0.5) / 0.2) * 0.15,
        "对倒拉升": range_score * 0.24 + amount_score * 0.18 + burst_ratio * 0.18 + up_score * 0.18 + cancel_ratio * 6.0 * 0.10 + close_top_score * 0.12,
        "压单吸货": close_top_score * 0.25 + up_score * 0.20 + _clip01((ask_pressure - bid_support + 0.1) / 0.3) * 0.20 + buy_bias_score * 0.15 + neutral_close_score * 0.10 + amount_score * 0.10,
        "集合竞价异动": open_jump_score * 0.42 + reversal_down_score * 0.18 + reversal_up_score * 0.18 + range_score * 0.12 + burst_ratio * 0.10,
        "分时脉冲": range_score * 0.34 + burst_ratio * 0.22 + mid_close_score * 0.18 + tail_down_score * 0.10 + tail_up_score * 0.10 + neutral_close_score * 0.06,
        "连续小单推升": up_score * 0.22 + close_top_score * 0.22 + small_order_score * 0.22 + buy_bias_score * 0.18 + directional_efficiency * 0.16,
        "盘中诱多": down_score * 0.26 + close_bottom_score * 0.24 + range_score * 0.18 + reversal_down_score * 0.18 + sell_bias_score * 0.14,
        "涨停板打开": up_score * 0.22 + range_score * 0.22 + close_top_score * 0.16 + amount_score * 0.16 + tail_down_score * 0.14 + burst_ratio * 0.10,
    }

    ranked = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)
    label, score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = score - second_score

    if score < float(config.get("pattern_low_conf_threshold", 0.15)) or margin < float(
        config.get("pattern_margin_threshold", 0.04)
    ):
        label = fallback_pattern_rule(summary)
        score = max(score, 0.18)

    return PatternResult(
        stock_code=sample.stock_code,
        transaction_date=sample.transaction_date,
        pattern_type=label,
        pattern_explanation=render_pattern_explanation(label, summary),
        pattern_score=round(score, 4),
        prototype_id=f"baseline::{label}",
    )


def _detect_obvious_pattern(summary: dict) -> str | None:
    deal_amount = _to_float(summary.get("deal_amount"))
    close_return = _to_float(summary.get("close_return"))
    open_return = _to_float(summary.get("open_return"))
    intraday_range = _to_float(summary.get("intraday_range"))
    close_strength = _to_float(summary.get("close_strength"))
    tail_ratio = _to_float(summary.get("tail_ratio"))
    last15_return = _to_float(summary.get("last15_return"))
    avg_trade_size = _to_float(summary.get("avg_trade_size"))
    order_buy_ratio = _to_float(summary.get("order_buy_ratio"), 0.5)

    if close_return >= 0.035 and close_strength >= 0.62 and deal_amount >= 300_000_000:
        return "大单吸筹"
    if close_return >= 0.012 and close_strength >= 0.58 and avg_trade_size <= 8_500 and order_buy_ratio >= 0.53:
        return "连续小单推升"
    if last15_return >= 0.0025 and tail_ratio >= 0.10 and close_strength >= 0.68:
        return "尾盘突袭"
    if open_return <= -0.008 and close_return >= 0.008 and close_strength >= 0.60:
        return "压单吸货"
    if open_return >= 0.008 and close_return <= -0.012 and close_strength <= 0.35:
        return "盘中诱多"
    if close_return <= -0.025 and close_strength <= 0.28:
        return "盘中诱多"
    if abs(close_return) <= 0.012 and intraday_range >= 0.035:
        return "日内套利"
    return None


def fallback_pattern_rule(summary: dict) -> str:
    close_return = _to_float(summary.get("close_return"))
    open_return = _to_float(summary.get("open_return"))
    intraday_range = _to_float(summary.get("intraday_range"))
    close_strength = _to_float(summary.get("close_strength"))
    order_buy_ratio = _to_float(summary.get("order_buy_ratio"), 0.5)
    avg_trade_size = _to_float(summary.get("avg_trade_size"))
    last15_return = _to_float(summary.get("last15_return"))

    if last15_return > 0.0025 and close_strength > 0.7:
        return "尾盘突袭"
    if close_return > 0.03 and close_strength > 0.85:
        return "大单吸筹"
    if close_return > 0.01 and avg_trade_size < 8_000 and order_buy_ratio > 0.52:
        return "连续小单推升"
    if abs(close_return) < 0.015 and intraday_range > 0.035:
        return "日内套利"
    if open_return < -0.01 and close_return > 0.008 and close_strength > 0.65:
        return "压单吸货"
    if open_return > 0.008 and close_return < -0.01 and close_strength < 0.35:
        return "盘中诱多"
    if close_return < -0.02 and close_strength < 0.35:
        return "盘中诱多"
    return "分时脉冲"


def render_pattern_explanation(label: str, summary: dict) -> str:
    if label == "尾盘突袭":
        return "尾盘最后一段成交明显放大，股价临近收盘快速抬升，带有集中做强收盘的意味。"
    if label == "大单吸筹":
        return "全天维持偏强上攻，成交额与单笔成交偏大，像是主导资金持续承接并主动推高。"
    if label == "日内套利":
        return "日内振幅较大但收盘偏离不深，更像在区间里反复高抛低吸做差价。"
    if label == "对倒拉升":
        return "成交活跃度与价格波动同步放大，盘口节奏偏快，存在制造活跃度并拉升股价的迹象。"
    if label == "压单吸货":
        return "盘口卖压存在但收盘仍维持相对高位，像是边压盘边在回落区间吸收筹码。"
    if label == "集合竞价异动":
        return "开盘阶段偏离前收较明显，随后出现修正，竞价阶段对全天预期的影响较强。"
    if label == "分时脉冲":
        return "盘中出现较快的拉升回落或试探动作，节奏短促，更多体现为脉冲型波动。"
    if label == "连续小单推升":
        return "单笔成交偏小但买入力度持续，股价重心缓慢上移，属于较隐蔽的推升形态。"
    if label == "盘中诱多":
        return "盘中一度尝试上攻，但收盘回落到偏弱位置，带有吸引跟风后转弱的特征。"
    if label == "涨停板打开":
        return "全天强势波动较大，情绪冲高后反复换手，呈现强势股开板博弈的节奏。"
    return "盘口与价格节奏存在明显异动，当前标签由日内成交结构与收盘位置共同决定。"

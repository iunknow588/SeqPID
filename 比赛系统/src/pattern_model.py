from __future__ import annotations

from typing import Any

from schemas import DailySample, PatternResult

PATTERN_LABELS = [
    "量化T0",
    "散户博弈",
    "尾盘突袭",
    "日内套利",
    "大单吸筹",
]

INTERNAL_TO_SUBMIT_LABEL = {
    "分时脉冲": "量化T0",
    "连续小单推升": "量化T0",
    "盘中诱多": "散户博弈",
    "对倒拉升": "大单吸筹",
    "压单吸货": "大单吸筹",
    "集合竞价异动": "日内套利",
    "涨停板打开": "尾盘突袭",
}

EXPLANATION_TEMPLATES = {
    ("量化T0", "vwap"): "量化模型围绕VWAP反复挂单，利用短周期偏离完成日内回转",
    ("量化T0", "default"): "程序化拆单后快速买入卖出，围绕盘口价差完成T0回转",
    ("散户博弈", "weak_support"): "盘口缺乏大单支撑，价格随散户情绪小幅波动",
    ("散户博弈", "default"): "成交以小单为主且方向混乱，呈现散户之间的博弈换手",
    ("尾盘突袭", "dump"): "收盘前集中砸盘，制造恐慌情绪并显著影响收盘价",
    ("尾盘突袭", "default"): "在下午2点半之后集中拉升，制造强势收盘和典型技术形态",
    ("日内套利", "vwap"): "资金围绕VWAP上下反复交易，赚取均值回复利润",
    ("日内套利", "default"): "资金在一定价格区间来回高抛低吸，获取日内价差收益",
    ("大单吸筹", "continuous"): "盘中持续出现大额买单，逐步抬高股价重心",
    ("大单吸筹", "default"): "资金大笔挂单买入，短时间内集中扫货并吸收筹码",
}


def _to_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _pattern_submit_labels(label_dict: dict) -> list[str]:
    labels = label_dict.get("pattern_labels_submit") if isinstance(label_dict, dict) else None
    if isinstance(labels, list) and labels:
        return [str(item) for item in labels]
    return PATTERN_LABELS


def _feature_scores(summary: dict) -> dict[str, float]:
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

    balance_score = 1.0 - _clip01(abs(order_buy_ratio - 0.50) / 0.18)
    small_order_score = _clip01((12_000.0 - avg_trade_size) / 10_000.0)
    large_order_score = _clip01((avg_trade_size - 7_000.0) / 13_000.0)
    amount_score = _clip01(deal_amount / 800_000_000.0)
    range_score = _clip01(intraday_range / 0.08)
    neutral_close_score = 1.0 - _clip01(abs(close_return) / 0.02)
    close_top_score = _clip01((close_strength - 0.56) / 0.44)
    close_mid_score = 1.0 - _clip01(abs(close_strength - 0.50) / 0.35)
    close_bottom_score = _clip01((0.45 - close_strength) / 0.45)
    buy_bias_score = _clip01((order_buy_ratio - 0.50) / 0.16)
    sell_bias_score = _clip01((0.50 - order_buy_ratio) / 0.16)
    tail_flow_score = _clip01((tail_ratio - 0.06) / 0.10)
    tail_return_score = _clip01((last15_return - 0.0015) / 0.01)
    tail_squeeze_score = _clip01((tail_ratio + max(last15_return, 0.0) * 40.0) / 0.22)
    burst_score = _clip01(burst_ratio / 0.22)
    direction_score = _clip01(directional_efficiency / 0.75)
    noise_score = 1.0 - _clip01(direction_score)
    reversal_score = _clip01(abs(reversal_strength) / 0.03)
    ask_pressure_score = _clip01((ask_pressure - bid_support + 0.12) / 0.30)
    open_jump_score = _clip01(abs(open_return) / 0.03)
    up_score = _clip01(close_return / 0.05)
    down_score = _clip01(-close_return / 0.05)

    return {
        "deal_amount": deal_amount,
        "close_return": close_return,
        "open_return": open_return,
        "intraday_range": intraday_range,
        "close_strength": close_strength,
        "cancel_ratio": cancel_ratio,
        "burst_ratio": burst_ratio,
        "bid_support": bid_support,
        "ask_pressure": ask_pressure,
        "tail_ratio": tail_ratio,
        "last15_return": last15_return,
        "avg_trade_size": avg_trade_size,
        "order_buy_ratio": order_buy_ratio,
        "directional_efficiency": directional_efficiency,
        "reversal_strength": reversal_strength,
        "balance_score": balance_score,
        "small_order_score": small_order_score,
        "large_order_score": large_order_score,
        "amount_score": amount_score,
        "range_score": range_score,
        "neutral_close_score": neutral_close_score,
        "close_top_score": close_top_score,
        "close_mid_score": close_mid_score,
        "close_bottom_score": close_bottom_score,
        "buy_bias_score": buy_bias_score,
        "sell_bias_score": sell_bias_score,
        "tail_flow_score": tail_flow_score,
        "tail_return_score": tail_return_score,
        "tail_squeeze_score": tail_squeeze_score,
        "burst_score": burst_score,
        "direction_score": direction_score,
        "noise_score": noise_score,
        "reversal_score": reversal_score,
        "ask_pressure_score": ask_pressure_score,
        "open_jump_score": open_jump_score,
        "up_score": up_score,
        "down_score": down_score,
    }


def _pattern_evidence(label: str, scores: dict[str, float]) -> list[str]:
    if label == "量化T0":
        return [
            f"小单占比={scores['small_order_score']:.2f}",
            f"买卖均衡={scores['balance_score']:.2f}",
            f"方向效率={scores['direction_score']:.2f}",
        ]
    if label == "散户博弈":
        return [
            f"单笔偏小={scores['small_order_score']:.2f}",
            f"噪声偏高={scores['noise_score']:.2f}",
            f"收盘中性={scores['neutral_close_score']:.2f}",
        ]
    if label == "尾盘突袭":
        return [
            f"尾盘占比={scores['tail_flow_score']:.2f}",
            f"尾段抬升={scores['tail_return_score']:.2f}",
            f"收盘强度={scores['close_top_score']:.2f}",
        ]
    if label == "日内套利":
        return [
            f"日内振幅={scores['range_score']:.2f}",
            f"收盘中性={scores['neutral_close_score']:.2f}",
            f"收盘居中={scores['close_mid_score']:.2f}",
        ]
    return [
        f"大单特征={scores['large_order_score']:.2f}",
        f"买盘偏强={scores['buy_bias_score']:.2f}",
        f"收盘强势={scores['close_top_score']:.2f}",
    ]


def _score_pattern_modes(scores: dict[str, float]) -> dict[str, tuple[float, list[str]]]:
    pattern_scores = {
        "量化T0": (
            scores["small_order_score"] * 0.28
            + scores["balance_score"] * 0.22
            + scores["direction_score"] * 0.20
            + scores["burst_score"] * 0.15
            + scores["neutral_close_score"] * 0.15,
            ["小单高频", "买卖均衡", "程序化回转"],
        ),
        "散户博弈": (
            scores["small_order_score"] * 0.22
            + scores["noise_score"] * 0.26
            + scores["neutral_close_score"] * 0.20
            + scores["close_mid_score"] * 0.18
            + (1.0 - scores["large_order_score"]) * 0.14,
            ["小单主导", "方向混乱", "缺少主导资金"],
        ),
        "尾盘突袭": (
            scores["tail_squeeze_score"] * 0.30
            + scores["tail_flow_score"] * 0.24
            + scores["close_top_score"] * 0.20
            + scores["amount_score"] * 0.14
            + scores["burst_score"] * 0.12,
            ["尾盘放量", "收盘强势", "尾段冲击"],
        ),
        "日内套利": (
            scores["range_score"] * 0.30
            + scores["neutral_close_score"] * 0.26
            + scores["close_mid_score"] * 0.18
            + scores["balance_score"] * 0.12
            + scores["burst_score"] * 0.14,
            ["区间波动", "收盘回中", "反复做差价"],
        ),
        "大单吸筹": (
            scores["large_order_score"] * 0.28
            + scores["buy_bias_score"] * 0.22
            + scores["close_top_score"] * 0.20
            + scores["amount_score"] * 0.18
            + scores["direction_score"] * 0.12,
            ["大单承接", "买盘占优", "重心抬升"],
        ),
    }
    return pattern_scores


def _detect_obvious_pattern(scores: dict[str, float]) -> str | None:
    if scores["tail_squeeze_score"] >= 0.72 and scores["close_top_score"] >= 0.45:
        return "尾盘突袭"
    if scores["large_order_score"] >= 0.70 and scores["buy_bias_score"] >= 0.45 and scores["close_top_score"] >= 0.35:
        return "大单吸筹"
    if scores["small_order_score"] >= 0.70 and scores["balance_score"] >= 0.70 and scores["neutral_close_score"] >= 0.50:
        return "量化T0"
    if scores["small_order_score"] >= 0.60 and scores["noise_score"] >= 0.55 and scores["close_mid_score"] >= 0.45:
        return "散户博弈"
    if scores["range_score"] >= 0.60 and scores["neutral_close_score"] >= 0.55:
        return "日内套利"
    return None


def _refine_pattern_with_pid(label: str, scores: dict[str, float], pid_result: Any | None) -> str:
    label = INTERNAL_TO_SUBMIT_LABEL.get(label, label)
    if pid_result is None:
        return label

    dominant_type = str(getattr(pid_result, "dominant_type", ""))
    dominant_intention = str(getattr(pid_result, "dominant_intention", ""))
    hot_money_ratio = _to_float(getattr(pid_result, "hot_money_ratio", 0.0))
    quant_ratio = _to_float(getattr(pid_result, "quant_ratio", 0.0))
    retail_ratio = _to_float(getattr(pid_result, "retail_ratio", 0.0))
    damping_mean = abs(_to_float(getattr(pid_result, "damping_mean", 0.0)))
    inertia_mean = abs(_to_float(getattr(pid_result, "inertia_mean", 0.0)))

    if dominant_type == "量化" and quant_ratio >= 0.38:
        if scores["small_order_score"] >= 0.50 or scores["balance_score"] >= 0.55:
            return "量化T0"
        if scores["range_score"] >= 0.55 and scores["neutral_close_score"] >= 0.45:
            return "日内套利"

    if dominant_type == "散户" and retail_ratio >= 0.34:
        if scores["noise_score"] >= 0.50 and scores["small_order_score"] >= 0.45:
            return "散户博弈"

    if dominant_type == "游资" and hot_money_ratio >= 0.34:
        if scores["tail_squeeze_score"] >= max(scores["large_order_score"], scores["range_score"]):
            return "尾盘突袭"
        if scores["large_order_score"] >= 0.50 and scores["buy_bias_score"] >= 0.40:
            return "大单吸筹"

    if dominant_intention in {"T0交易", "中性"} and scores["small_order_score"] >= 0.45:
        return "量化T0"
    if dominant_intention == "买入" and scores["buy_bias_score"] >= 0.40 and scores["close_top_score"] >= 0.40:
        return "大单吸筹"
    if dominant_intention == "卖出" and scores["close_mid_score"] < 0.40 and scores["noise_score"] >= 0.35:
        return "散户博弈"
    if inertia_mean >= 0.20 and damping_mean < 0.05 and scores["neutral_close_score"] >= 0.40:
        return "日内套利"
    return label


def refine_pattern_with_pid(label: str, summary: dict, pid_result: Any | None) -> str:
    """Backward-compatible public entry: old internal labels are evidence, not final labels."""

    return _refine_pattern_with_pid(label, _feature_scores(summary), pid_result)


def fallback_pattern_rule(scores: dict[str, float]) -> str:
    if scores["tail_squeeze_score"] >= 0.58:
        return "尾盘突袭"
    if scores["large_order_score"] >= 0.58:
        return "大单吸筹"
    if scores["small_order_score"] >= 0.58 and scores["balance_score"] >= 0.58:
        return "量化T0"
    if scores["range_score"] >= 0.48 and scores["neutral_close_score"] >= 0.42:
        return "日内套利"
    return "散户博弈"


def _dominant_capital_type(scores: dict[str, float], pid_result: Any | None = None) -> str:
    if pid_result is not None:
        dominant_type = str(getattr(pid_result, "dominant_type", "") or "")
        if dominant_type in {"游资", "量化", "散户"}:
            return dominant_type
    if scores["large_order_score"] >= 0.55 or scores["tail_squeeze_score"] >= 0.60:
        return "游资"
    if scores["small_order_score"] >= 0.55 and scores["balance_score"] >= 0.55:
        return "量化"
    return "散户"


def _dominant_intention(scores: dict[str, float], pid_result: Any | None = None) -> str:
    if pid_result is not None:
        dominant_intention = str(getattr(pid_result, "dominant_intention", "") or "")
        if dominant_intention in {"买入", "卖出", "中性", "T0交易"}:
            return dominant_intention
    if scores["sell_bias_score"] >= 0.35 or scores["down_score"] >= 0.25:
        return "卖出"
    if scores["buy_bias_score"] >= 0.35 or scores["up_score"] >= 0.25:
        return "买入"
    return "T0交易" if scores["balance_score"] >= 0.50 else "中性"


def _build_explanation_summary(label: str, scores: dict[str, float], pid_result: Any | None = None) -> dict[str, str]:
    time_bucket = "tail" if label == "尾盘突袭" or scores["tail_flow_score"] >= 0.50 else "intraday"
    if scores["open_jump_score"] >= 0.50 and time_bucket != "tail":
        time_bucket = "open"
    if scores["large_order_score"] >= 0.55:
        order_size_style = "large"
    elif scores["small_order_score"] >= 0.55:
        order_size_style = "small"
    else:
        order_size_style = "mixed"
    if label in {"量化T0", "日内套利"}:
        flow_style = "intermittent" if scores["balance_score"] >= 0.45 else "continuous"
        price_effect = "rotate"
    elif label == "尾盘突袭":
        flow_style = "one_shot" if scores["burst_score"] >= 0.45 else "continuous"
        price_effect = "dump" if scores["sell_bias_score"] >= 0.30 or scores["down_score"] >= 0.20 else "lift"
    elif label == "大单吸筹":
        flow_style = "continuous" if scores["direction_score"] >= 0.45 else "one_shot"
        price_effect = "absorb"
    else:
        flow_style = "intermittent"
        price_effect = "churn"

    if label == "量化T0":
        template_key = "vwap" if scores["range_score"] >= 0.45 and scores["neutral_close_score"] >= 0.45 else "default"
    elif label == "散户博弈":
        template_key = "weak_support" if scores["large_order_score"] <= 0.30 else "default"
    elif label == "尾盘突袭":
        template_key = "dump" if price_effect == "dump" else "default"
    elif label == "日内套利":
        template_key = "vwap" if scores["balance_score"] >= 0.50 else "default"
    elif label == "大单吸筹":
        template_key = "continuous" if flow_style == "continuous" else "default"
    else:
        template_key = "default"

    return {
        "pattern_type": label,
        "capital_type": _dominant_capital_type(scores, pid_result),
        "capital_intention": _dominant_intention(scores, pid_result),
        "time_bucket": time_bucket,
        "flow_style": flow_style,
        "order_size_style": order_size_style,
        "price_effect": price_effect,
        "template_key": template_key,
    }


def _render_explanation_summary(summary: dict[str, str]) -> str:
    label = summary.get("pattern_type", "")
    template_key = summary.get("template_key", "default")
    time_bucket = summary.get("time_bucket", "intraday")
    flow_style = summary.get("flow_style", "intermittent")
    order_size_style = summary.get("order_size_style", "mixed")
    price_effect = summary.get("price_effect", "")

    if label == PATTERN_LABELS[0]:
        if time_bucket == "open":
            return "早盘小单快速往返，买卖方向接近平衡，呈现程序化T0试盘回转"
        if order_size_style == "small" and flow_style == "intermittent":
            return "高频小单分批进出，围绕盘口价差反复回转，呈现量化T0特征"

    if label == PATTERN_LABELS[1]:
        if order_size_style == "small" and flow_style == "intermittent":
            return "成交以小单间歇换手为主，方向分散，呈现散户之间的博弈"

    if label == PATTERN_LABELS[2]:
        if time_bucket == "tail" and price_effect == "dump":
            return "收盘前集中砸盘，制造恐慌情绪并显著影响收盘价"
        if time_bucket == "tail" and flow_style == "one_shot":
            return "下午2点半后资金集中拉升，短时间突击并制造强势收盘形态"

    if label == PATTERN_LABELS[3]:
        if time_bucket == "open":
            return "早盘先拉开价差，盘中反复高抛低吸，最终回到区间中部"
        if flow_style == "intermittent":
            return "资金围绕VWAP上下反复交易，利用区间波动获取日内价差"

    if label == PATTERN_LABELS[4]:
        if time_bucket == "open" and order_size_style == "large":
            return "早盘大单快速扫货，主动承接筹码并抬高日内价格重心"
        if flow_style == "one_shot" and order_size_style == "large":
            return "短时间内大单集中买入，快速吸收筹码并推动股价上移"
    return EXPLANATION_TEMPLATES.get((label, template_key)) or EXPLANATION_TEMPLATES.get(
        (label, "default"),
        "盘中结构和资金行为出现明显异常，需结合盘口证据判断资金运行模式",
    )


def render_pattern_explanation(label: str, summary: dict, evidence: list[str] | None = None) -> str:
    scores = _feature_scores(summary)
    explanation_summary = _build_explanation_summary(label, scores)
    return _render_explanation_summary(explanation_summary)


def predict_pattern(sample: DailySample, config: dict, label_dict: dict, pid_result: Any | None = None) -> PatternResult:
    submit_labels = _pattern_submit_labels(label_dict)
    scores = _feature_scores(sample.feature_summary)
    candidate_scores = _score_pattern_modes(scores)
    ranked = sorted(candidate_scores.items(), key=lambda item: item[1][0], reverse=True)
    second_score = ranked[1][1][0] if len(ranked) > 1 else 0.0

    forced_label = _detect_obvious_pattern(scores)

    if forced_label is not None:
        label = forced_label
        score = max(candidate_scores[label][0], 0.86)
        evidence = _pattern_evidence(label, scores)
        refined_label = _refine_pattern_with_pid(label, scores, pid_result)
        pid_adjusted = refined_label != label
        if refined_label != label:
            score = max(score, 0.90)
            label = refined_label
            evidence = _pattern_evidence(label, scores)
        if label not in submit_labels:
            label = submit_labels[0]
        return PatternResult(
            stock_code=sample.stock_code,
            transaction_date=sample.transaction_date,
            pattern_type=label,
            pattern_explanation=_render_explanation_summary(_build_explanation_summary(label, scores, pid_result)),
            pattern_score=round(score, 4),
            prototype_id=f"rule::{label}",
            pattern_primary_score=round(score, 4),
            pattern_second_score=round(second_score, 4),
            pattern_margin=round(score - second_score, 4),
            pattern_source="rule_shortcut",
            pattern_pid_adjusted=pid_adjusted,
        )

    label, (score, evidence_tags) = ranked[0]
    margin = score - second_score

    low_conf = float(config.get("pattern_low_conf_threshold", 0.15))
    margin_thresh = float(config.get("pattern_margin_threshold", 0.04))
    if score < low_conf or margin < margin_thresh:
        label = fallback_pattern_rule(scores)
        score = max(score, 0.18)
        evidence_tags = candidate_scores[label][1]

    refined_label = _refine_pattern_with_pid(label, scores, pid_result)
    pid_adjusted = refined_label != label
    if refined_label != label:
        label = refined_label
        score = min(0.93, max(score, 0.62))
        evidence_tags = candidate_scores[label][1]

    if label not in submit_labels:
        label = submit_labels[0]

    return PatternResult(
        stock_code=sample.stock_code,
        transaction_date=sample.transaction_date,
        pattern_type=label,
        pattern_explanation=_render_explanation_summary(_build_explanation_summary(label, scores, pid_result)),
        pattern_score=round(score, 4),
        prototype_id=f"mode::{label}::{'|'.join(evidence_tags)}",
        pattern_primary_score=round(score, 4),
        pattern_second_score=round(second_score, 4),
        pattern_margin=round(score - second_score, 4),
        pattern_source="mode_detector",
        pattern_pid_adjusted=pid_adjusted,
    )

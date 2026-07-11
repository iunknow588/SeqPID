from __future__ import annotations

from schemas import DailySample, PatternResult, PredictResult
from pid_decomposer import DecompositionResult
from state_feature_builder import tail_state_feature


CAPITAL_TYPES = ("散户", "游资", "量化")
RULE_TO_LABEL = {
    "hot_money": "游资",
    "quant": "量化",
    "retail": "散户",
}


def _to_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _rule_flow_evidence(sample: DailySample) -> dict:
    totals = {"hot_money": 0.0, "quant": 0.0, "retail": 0.0}
    abs_totals = {"hot_money": 0.0, "quant": 0.0, "retail": 0.0}
    recovered = _to_float(sample.feature_summary.get("raw_order_age_recovered_count"))
    missing = _to_float(sample.feature_summary.get("raw_order_age_missing_count"))

    for row in sample.rows or []:
        values = {
            "hot_money": _to_float(row.get("CH_rule_t", row.get("signed_large_active_amount", 0.0))),
            "quant": _to_float(row.get("Q_rule_t", 0.0)),
            "retail": _to_float(row.get("R_seed_t", 0.0)),
        }
        if "Q_rule_t" not in row and "R_seed_t" not in row:
            values["quant"] = _to_float(row.get("signed_mix_qr_amount", 0.0))
            values["retail"] = 0.0
        for key, value in values.items():
            totals[key] += value
            abs_totals[key] += abs(value)

    total_abs = sum(abs_totals.values())
    if total_abs <= 0:
        return {
            "label": "",
            "signed_amount": 0.0,
            "ratio": 0.0,
            "recovery_ratio": 0.0,
            "confidence": 0.0,
            "totals": totals,
            "abs_totals": abs_totals,
        }

    dominant_key = max(abs_totals, key=abs_totals.get)
    recovery_total = recovered + missing
    recovery_ratio = recovered / recovery_total if recovery_total > 0 else 0.0
    quality = 1.0
    if dominant_key == "retail":
        quality = recovery_ratio
    elif dominant_key == "quant" and recovery_total > 0:
        quality = 0.85 + 0.15 * recovery_ratio

    ratio = abs_totals[dominant_key] / total_abs
    return {
        "label": RULE_TO_LABEL[dominant_key],
        "signed_amount": totals[dominant_key],
        "ratio": ratio,
        "recovery_ratio": recovery_ratio,
        "confidence": ratio * quality,
        "totals": totals,
        "abs_totals": abs_totals,
    }


def _select_capital_type(sample: DailySample, pid_result: DecompositionResult, config: dict) -> tuple[str, float, dict]:
    structural_label = pid_result.dominant_type
    structural_ratio = {
        "游资": pid_result.hot_money_ratio,
        "量化": pid_result.quant_ratio,
        "散户": pid_result.retail_ratio,
    }.get(structural_label, 0.0)
    rule = _rule_flow_evidence(sample)
    selected_label = structural_label
    selected_confidence = structural_ratio
    source = "capital_external_force"

    if bool(config.get("enable_rule_flow_capital_override", True)) and rule["label"]:
        label_thresholds = {
            "游资": float(config.get("capital_hot_money_rule_override_threshold", 0.46)),
            "散户": float(config.get("capital_retail_rule_override_threshold", 0.46)),
            "量化": float(config.get("capital_quant_rule_override_threshold", 0.68)),
        }
        threshold = label_thresholds.get(rule["label"], float(config.get("capital_rule_override_threshold", 0.46)))
        margin = float(config.get("capital_rule_override_margin", 0.04))
        if rule["label"] == "量化" and structural_label != "量化":
            margin = float(config.get("capital_quant_rule_override_margin", 0.18))
        anchor_error = float(getattr(pid_result, "capital_anchor_error", [0.0])[-1]) if len(pid_result.capital_anchor_error) else 0.0
        if anchor_error != anchor_error:
            anchor_error = 0.0
        structural_is_weak = structural_ratio < float(
            config.get("capital_external_force_strong_ratio", config.get("capital_structural_strong_ratio", 0.46))
        )
        anchor_is_weak = anchor_error > float(config.get("capital_anchor_override_error", 0.35))
        rule_is_stronger = rule["confidence"] >= structural_ratio + margin
        if rule["label"] == "量化" and structural_label != "量化":
            can_override = rule_is_stronger and (structural_is_weak or anchor_is_weak)
        else:
            can_override = rule_is_stronger or structural_is_weak or anchor_is_weak
        if rule["confidence"] >= threshold and can_override:
            selected_label = rule["label"]
            selected_confidence = rule["confidence"]
            source = "rule_flow_override"

    return selected_label, selected_confidence, {
        "capital_type_source": source,
        "external_force_capital_type": structural_label,
        "external_force_capital_ratio": round(structural_ratio, 4),
        "structural_capital_type": structural_label,
        "structural_capital_ratio": round(structural_ratio, 4),
        "rule_flow_capital_type": rule["label"] or None,
        "rule_flow_ratio": round(float(rule["ratio"]), 4),
        "rule_flow_confidence": round(float(rule["confidence"]), 4),
        "rule_flow_recovery_ratio": round(float(rule["recovery_ratio"]), 4),
        "rule_flow_signed_amount": round(float(rule["signed_amount"]), 4),
    }


def _map_pid_to_intention(pid_result: DecompositionResult, summary: dict, config: dict, label_dict: dict) -> tuple[str, float]:
    """
    基于PID贡献度映射资金意图
    返回: (intention, confidence)
    """
    dominant = pid_result.dominant_type
    if pid_result.dominant_intention in {"买入", "卖出", "中性"}:
        noise_penalty = float(getattr(pid_result, "noise_ratio", [0.0])[-1]) if len(pid_result.noise_ratio) else 0.0
        anchor_error = float(getattr(pid_result, "capital_anchor_error", [0.0])[-1]) if len(pid_result.capital_anchor_error) else 0.0
        if anchor_error != anchor_error:
            anchor_error = 0.0
        confidence = _clamp(0.72 - min(noise_penalty, 0.35) - min(anchor_error, 0.25))
        return pid_result.dominant_intention, confidence

    vwap_pct = _to_float(summary.get("close_strength"), 0.5)
    close_return = _to_float(summary.get("close_return"), 0.0)
    intraday_range = _to_float(summary.get("intraday_range"), 0.0)
    order_buy_ratio = _to_float(summary.get("order_buy_ratio"), 0.5)
    
    label_mode = str(config.get("label_mode", "compressed"))
    compressed_labels = set(label_dict.get("capital_intention_labels_submit", []))
    compressed_labels.update({"买入", "卖出", "中性", "T0交易"})
    
    if dominant == "游资":
        # 游资意图: 基于贡献度符号+VWAP位置
        delta_ch_end = pid_result.delta_ch[-1] if len(pid_result.delta_ch) > 0 else 0.0
        if delta_ch_end > 0 and vwap_pct < 0.8:
            fine, conf = "拉升", 0.75
        elif delta_ch_end < 0 and vwap_pct > 0.2:
            fine, conf = "出货", 0.72
        elif abs(delta_ch_end) < 1e-4:
            fine, conf = "试盘", 0.65
        else:
            fine, conf = "吸筹", 0.68
    elif dominant == "量化":
        # 量化意图: 基于波动+收益特征
        if abs(close_return) < 0.01 and intraday_range > 0.02:
            fine, conf = "T0交易", 0.70
        elif close_return < -0.015:
            fine, conf = "卖出", 0.67
        elif close_return > 0.015 and order_buy_ratio > 0.52:
            fine, conf = "买入", 0.62
        else:
            fine, conf = "中性", 0.57
    else:  # 散户
        if abs(close_return) < 0.008:
            fine, conf = "中性", 0.58
        elif close_return > 0:
            fine, conf = "买入", 0.60
        else:
            fine, conf = "卖出", 0.60
    
    # 标签压缩映射
    if label_mode == "compressed" and fine not in compressed_labels:
        if fine in {"吸筹", "拉升"}:
            return "买入", conf
        if fine in {"出货"}:
            return "卖出", conf
        if fine in {"试盘"}:
            return ("T0交易" if dominant == "散户" else "中性"), conf
        return "中性", conf
    return fine, conf


def predict_capitals(sample: DailySample, config: dict, label_dict: dict, 
                     pid_result: DecompositionResult) -> list[PredictResult]:
    """
    基于PID分解结果预测资金类型与意图
    pid_result: 必传参数，纯PID方案无降级
    """
    summary = sample.feature_summary
    
    dominant_type, selected_capital_ratio, capital_source_debug = _select_capital_type(sample, pid_result, config)
    
    intention, intention_confidence = _map_pid_to_intention(pid_result, summary, config, label_dict)
    if (
        capital_source_debug["capital_type_source"] == "rule_flow_override"
        and abs(float(capital_source_debug["rule_flow_signed_amount"])) > 0.0
    ):
        intention = "买入" if float(capital_source_debug["rule_flow_signed_amount"]) > 0 else "卖出"
        intention_confidence = max(intention_confidence, min(0.78, 0.52 + float(capital_source_debug["rule_flow_confidence"]) * 0.28))
    
    # 置信度: 基于主导占比+闭合误差
    dominant_ratio = selected_capital_ratio or {
        "游资": pid_result.hot_money_ratio,
        "量化": pid_result.quant_ratio,
        "散户": pid_result.retail_ratio,
    }.get(dominant_type, 0.33)
    capital_confidence = _clamp(0.50 + dominant_ratio * 0.4 - min(pid_result.closure_error * 1e5, 0.1))
    state_tail = tail_state_feature(sample, pid_result)
    state_debug = {}
    if state_tail is not None:
        state_debug = {
            "mode_name": state_tail.mode_name,
            "is_structural_output": state_tail.is_structural_output,
            "CH_rule_tail": round(state_tail.CH_rule_t, 4),
            "Q_rule_tail": round(state_tail.Q_rule_t, 4),
            "R_seed_tail": round(state_tail.R_seed_t, 4),
            "capital_ch_tail": round(state_tail.capital_ch, 4) if state_tail.capital_ch is not None else None,
            "capital_q_tail": round(state_tail.capital_q, 4) if state_tail.capital_q is not None else None,
            "capital_retail_tail": round(state_tail.capital_retail, 4) if state_tail.capital_retail is not None else None,
            "rule_error_q_tail": round(state_tail.rule_error_q, 4) if state_tail.rule_error_q is not None else None,
            "rule_error_retail_tail": round(state_tail.rule_error_retail, 4)
            if state_tail.rule_error_retail is not None
            else None,
        }
    
    return [
        PredictResult(
            stock_code=sample.stock_code,
            transaction_date=sample.transaction_date,
            capital_type=dominant_type,
            capital_intention=intention,
            capital_confidence=capital_confidence,
            intention_confidence=intention_confidence,
            debug_info={
                "hot_money_ratio": round(pid_result.hot_money_ratio, 4),
                "quant_ratio": round(pid_result.quant_ratio, 4),
                "retail_ratio": round(pid_result.retail_ratio, 4),
                "inertia_mean": round(pid_result.inertia_mean, 4),
                "damping_mean": round(pid_result.damping_mean, 4),
                "dominant_intention": pid_result.dominant_intention,
                "capital_anchor_error_tail": round(float(pid_result.capital_anchor_error[-1]), 4)
                if len(pid_result.capital_anchor_error) and pid_result.capital_anchor_error[-1] == pid_result.capital_anchor_error[-1]
                else None,
                "noise_ratio_tail": round(float(pid_result.noise_ratio[-1]), 4) if len(pid_result.noise_ratio) else None,
                "explain_ratio_tail": round(float(pid_result.explain_ratio[-1]), 4) if len(pid_result.explain_ratio) else None,
                "pid_closure_error": f"{pid_result.pid_closure_error:.2e}",
                "alloc_closure_error": f"{pid_result.alloc_closure_error:.2e}",
                "closure_error": f"{pid_result.closure_error:.2e}",
                "display_closure_error": f"{pid_result.display_closure_error:.2e}",
                "capital_identity_error": f"{pid_result.capital_identity_error:.2e}",
                "capital_cp_identity_error": f"{pid_result.capital_cp_identity_error:.2e}",
                "capital_ci_identity_error": f"{pid_result.capital_ci_identity_error:.2e}",
                "capital_cd_identity_error": f"{pid_result.capital_cd_identity_error:.2e}",
                "dominant_source": pid_result.dominant_source,
                "display_fields_used_for_dominant": pid_result.display_fields_used_for_dominant,
                "decompose_mode": pid_result.mode,
                "kf_converged": pid_result.kf_converged,
                "warnings": pid_result.warnings,
                **capital_source_debug,
                **state_debug,
            },
        )
    ]


def predict_capital(sample: DailySample, config: dict, label_dict: dict, 
                    pid_result: DecompositionResult) -> PredictResult:
    return predict_capitals(sample, config, label_dict, pid_result)[0]

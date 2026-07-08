from __future__ import annotations

from schemas import DailySample, PredictResult
from pid_decomposer import DecompositionResult


CAPITAL_TYPES = ("散户", "游资", "量化")


def _to_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


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
    
    # 主导类型直接取自PID结果
    dominant_type = pid_result.dominant_type
    
    # 意图映射
    intention, intention_confidence = _map_pid_to_intention(pid_result, summary, config, label_dict)
    
    # 置信度: 基于主导占比+闭合误差
    dominant_ratio = {"游资": pid_result.hot_money_ratio, "量化": pid_result.quant_ratio, "散户": pid_result.retail_ratio}.get(dominant_type, 0.33)
    capital_confidence = _clamp(0.50 + dominant_ratio * 0.4 - min(pid_result.closure_error * 1e5, 0.1))
    
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
                "decompose_mode": pid_result.mode,
                "kf_converged": pid_result.kf_converged,
                "warnings": pid_result.warnings,
            },
        )
    ]


def predict_capital(sample: DailySample, config: dict, label_dict: dict, 
                    pid_result: DecompositionResult) -> PredictResult:
    return predict_capitals(sample, config, label_dict, pid_result)[0]

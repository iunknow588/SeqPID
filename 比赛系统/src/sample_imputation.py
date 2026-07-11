from __future__ import annotations

from capital_model import predict_capitals
import data_loader
from pattern_model import predict_pattern
from pid_decomposer import PIDDecomposer
from schemas import DailySample, PatternResult, PredictResult


def build_imputed_results(
    missing_symbols: list[str],
    trade_date: str,
    samples: list[DailySample],
    config: dict,
    label_dict: dict,
    pid_decomposer: PIDDecomposer,
) -> tuple[list[PatternResult], list[PredictResult]]:
    if not missing_symbols or not samples:
        return [], []

    market_average_summary = data_loader.build_market_average_summary(samples)
    pattern_results: list[PatternResult] = []
    predict_results: list[PredictResult] = []

    for symbol in missing_symbols:
        default_sample = DailySample(
            stock_code=symbol,
            transaction_date=trade_date,
            rows=[],
            feature_summary=dict(market_average_summary),
            quality_flags={
                "has_reference_features": False,
                "window_count_ok": False,
                "imputed_from_market_average": True,
                "source_layout": "missing_raw_data",
            },
        )
        pid_result = pid_decomposer.decompose_sample(default_sample)
        pattern_result = predict_pattern(default_sample, config, label_dict, pid_result)
        pattern_result.pattern_explanation = (
            f"{pattern_result.pattern_explanation} 缺失原始数据，按当日市场中位水平补全判断。"
        )
        pattern_result.prototype_id = f"imputed::{pattern_result.prototype_id}"

        predict_batch = predict_capitals(default_sample, config, label_dict, pid_result)
        for predict_result in predict_batch:
            predict_result.debug_info.update(
                {
                    "imputed_from_market_average": True,
                    "imputed_reason": "missing_raw_data",
                }
            )

        pattern_results.append(pattern_result)
        predict_results.extend(predict_batch)

    return pattern_results, predict_results

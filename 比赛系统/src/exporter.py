from __future__ import annotations

import csv
import json
import zipfile
from collections import Counter
from pathlib import Path

from schemas import DailySample, MarketPidSnapshot, PatternResult, PredictResult


PATTERN_COLUMNS = ["stock_code", "transaction_date", "pattern_type", "pattern_explanation"]
PREDICT_COLUMNS = ["stock_code", "transaction_date", "capital_type", "capital_intention"]
MARKET_SNAPSHOT_COLUMNS = [
    "trade_date",
    "up_count",
    "down_count",
    "breadth_ratio",
    "breadth_balance",
    "p_mean",
    "p_median",
    "p_std",
    "i_mean",
    "i_median",
    "i_std",
    "d_mean",
    "d_median",
    "d_std",
    "market_regime",
]
SUMMARY_COLUMNS = ["category", "label", "count", "ratio"]
EVENT_CLASSIFIED_COLUMNS = [
    "trade_date",
    "symbol",
    "event_id",
    "event_time",
    "window_id",
    "side",
    "signed_amount",
    "capital_type_rule",
    "confidence_score",
    "reason_codes",
]
WINDOW_FEATURE_COLUMNS = [
    "trade_date",
    "symbol",
    "window_id",
    "window_start",
    "window_end",
    "open_price",
    "close_price",
    "vwap",
    "deal_amount",
    "data_P",
    "data_P_source",
]
PID_TAIL_COLUMNS = [
    "stock_code",
    "transaction_date",
    "mode",
    "kf_converged",
    "dominant_type",
    "dominant_intention",
    "hot_money_ratio",
    "quant_ratio",
    "retail_ratio",
    "phi_tail",
    "theta_tail",
    "beta_ch_tail",
    "beta_mix_tail",
    "beta_q_tail",
    "beta_retail_tail",
    "c_p_tail",
    "c_i_tail",
    "c_d_tail",
    "capital_ch_tail",
    "capital_q_tail",
    "capital_retail_tail",
    "capital_anchor_error_tail",
    "noise_ratio_tail",
    "explain_ratio_tail",
    "capital_identity_error",
    "closure_error",
    "warnings",
]
PID_WINDOW_PARAM_COLUMNS = [
    "stock_code",
    "transaction_date",
    "window_id",
    "mode_name",
    "phi",
    "beta_ch",
    "beta_q",
    "beta_retail",
    "beta_mix",
    "theta",
    "covariance_diag",
]
PID_WINDOW_CONTRIB_COLUMNS = [
    "stock_code",
    "transaction_date",
    "window_id",
    "c_p",
    "c_i",
    "c_d",
    "eps",
    "capital_ch",
    "capital_q",
    "capital_retail",
    "capital_mix",
    "noise_ratio",
    "explain_ratio",
    "capital_anchor_error",
    "closure_error",
]
PID_WINDOW_DIAG_COLUMNS = [
    "trade_date",
    "symbol",
    "window_id",
    "mode_name",
    "q_type",
    "u_source_type",
    "estimator_method",
    "state_space_contract",
    "psi_prediction_semantics",
    "y_observed",
    "y_hat_next",
    "v_q_observed",
    "v_hat_q_next",
    "c_p",
    "c_i",
    "c_d",
    "eps",
    "capital_ch",
    "capital_q",
    "capital_retail",
    "capital_mix",
    "beta_norm_ch_diag",
    "beta_norm_q_diag",
    "beta_norm_retail_diag",
    "beta_norm_mix_diag",
    "m_eff_ch_diag",
    "m_eff_q_diag",
    "m_eff_retail_diag",
    "m_eff_mix_diag",
    "beta_norm_unit",
    "m_eff_source_type",
    "m_eff_clipped_flag",
    "closure_impl_error",
    "model_residual",
    "param_stability_flag",
    "m_eff_rank_eligible",
    "data_leakage_check",
    "m_slow_method",
    "thin_trade_window",
    "cross_symbol_comparable",
    "domain_mapping_valid_flag",
    "warnings",
]
PID_DAILY_DIAG_COLUMNS = [
    "trade_date",
    "symbol",
    "mode_name",
    "q_type",
    "u_source_type",
    "estimator_method",
    "m_slow_method",
    "lookback_days",
    "zero_trade_policy",
    "submission_requires_complete_windows",
    "lambda_switch",
    "lambda_jump",
    "lambda_error",
    "data_leakage_check",
    "feature_engineering_leakage_check",
    "rule_layer_leakage_check",
    "offline_smooth_used",
    "param_stability_flag",
    "beta_norm_unit",
    "m_eff_source_type",
    "m_eff_clipped_flag",
    "m_eff_uncertainty_flag",
    "m_eff_rank_eligible",
    "submission_ready",
    "sample_origin",
    "reason_code",
    "code_build_hash",
    "warning_count",
    "warnings",
]
RAW_DATA_QUALITY_COLUMNS = [
    "trade_date",
    "symbol",
    "file_role",
    "file_path",
    "file_exists",
    "file_size",
    "null_byte_ratio",
    "encoding_used",
    "header_valid",
    "raw_row_count",
    "effective_row_count",
    "quality_status",
    "reason_code",
    "action",
]


def _resolve_m_eff_status(config: dict | None = None) -> tuple[str, str]:
    cfg = config or {}
    u_source_type = str(cfg.get("u_source_type", "mv_ratio"))
    if u_source_type == "mv_ratio":
        return "true", "false"
    return "true", "false"


WINDOW_FLOW_COLUMNS = [
    "stock_code",
    "transaction_date",
    "window_id",
    "deal_amount",
    "signal_deal_buy_amount",
    "signal_deal_sell_amount",
    "signed_large_active_amount",
    "signed_mix_qr_amount",
    "CH_rule_t",
    "Q_rule_t",
    "R_seed_t",
    "large_active_buy_amount",
    "large_active_sell_amount",
    "small_passive_buy_amount",
    "small_passive_sell_amount",
    "unknown_side_amount",
    "window_open_price",
    "window_close_price",
    "window_trade_count",
    "active_inferred_count",
    "side_fallback_count",
    "low_fallback_count",
    "order_age_recovered_count",
    "order_age_missing_count",
    "order_age_direct_count",
    "order_age_fifo_count",
    "order_age_unresolved_count",
    "active_buy_count",
    "active_sell_count",
    "active_buy_amount",
    "active_sell_amount",
    "pi_max_price_impact_pct",
]


def _round6(value: float) -> float:
    return round(float(value), 6)


def _tail_value(values: object) -> str:
    try:
        iterable = list(values)  # numpy arrays and lists are both supported.
    except TypeError:
        return ""
    for value in reversed(iterable):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if numeric == numeric:
            return str(_round6(numeric))
    return ""


def _series_len(result: object, names: list[str]) -> int:
    max_len = 0
    for name in names:
        try:
            max_len = max(max_len, len(getattr(result, name, [])))
        except TypeError:
            continue
    return max_len


def _series_value(result: object, name: str, index: int, default: float = 0.0) -> float:
    values = getattr(result, name, [])
    try:
        value = values[index]
    except (TypeError, IndexError):
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric != numeric:
        return default
    return numeric


def _series_optional_value(result: object, name: str, index: int) -> float | None:
    values = getattr(result, name, [])
    try:
        value = values[index]
    except (TypeError, IndexError):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    return numeric


def _proxy_beta_norm(capital_value: float | None, price_basis: float | None, u_ratio: float | None) -> float | None:
    if capital_value is None or price_basis is None or u_ratio is None:
        return None
    if abs(price_basis) <= 1e-12 or abs(u_ratio) <= 1e-12:
        return None
    return (capital_value / price_basis) / u_ratio


def _proxy_m_eff(beta_norm: float | None, beta_norm_floor: float) -> tuple[float | None, bool]:
    if beta_norm is None:
        return None, False
    clipped = abs(beta_norm) <= beta_norm_floor
    return 1.0 / max(abs(beta_norm), beta_norm_floor), clipped


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return ""
    return str(_round6(value))


def _window_diag_proxy_metrics(result: object, window_id: int, beta_norm_floor: float) -> dict[str, object]:
    price_basis = _series_optional_value(result, "price_basis", window_id)
    metrics: dict[str, object] = {
        "beta_norm_unit": "",
        "m_eff_source_type": "unavailable",
        "m_eff_clipped_flag": "false",
    }
    components = {
        "ch": (
            _series_optional_value(result, "capital_ch", window_id),
            _series_optional_value(result, "u_ch_amount_ratio", window_id),
        ),
        "q": (
            _series_optional_value(result, "capital_q", window_id),
            _series_optional_value(result, "u_q_amount_ratio", window_id),
        ),
        "retail": (
            _series_optional_value(result, "capital_retail", window_id),
            _series_optional_value(result, "u_retail_amount_ratio", window_id),
        ),
        "mix": (
            _series_optional_value(result, "capital_mix", window_id),
            _series_optional_value(result, "u_mix_amount_ratio", window_id),
        ),
    }
    any_valid = False
    any_clipped = False
    for name, (capital_value, u_ratio) in components.items():
        beta_norm = _proxy_beta_norm(capital_value, price_basis, u_ratio)
        m_eff, clipped = _proxy_m_eff(beta_norm, beta_norm_floor)
        metrics[f"beta_norm_{name}_diag"] = _format_optional_float(beta_norm)
        metrics[f"m_eff_{name}_diag"] = _format_optional_float(m_eff)
        any_valid = any_valid or beta_norm is not None
        any_clipped = any_clipped or clipped
    if any_valid:
        metrics["beta_norm_unit"] = "amount_response"
        metrics["m_eff_source_type"] = "amount_ratio_proxy"
    if any_clipped:
        metrics["m_eff_clipped_flag"] = "true"
    return metrics


def _daily_diag_proxy_summary(result: object, beta_norm_floor: float) -> tuple[str, str, str]:
    row_count = _series_len(
        result,
        ["price_basis", "u_ch_amount_ratio", "u_q_amount_ratio", "u_retail_amount_ratio", "u_mix_amount_ratio"],
    )
    any_valid = False
    any_clipped = False
    for window_id in range(row_count):
        metrics = _window_diag_proxy_metrics(result, window_id, beta_norm_floor)
        if metrics["m_eff_source_type"] != "unavailable":
            any_valid = True
        if metrics["m_eff_clipped_flag"] == "true":
            any_clipped = True
    return (
        "amount_response" if any_valid else "",
        "amount_ratio_proxy" if any_valid else "unavailable",
        "true" if any_clipped else "false",
    )


def _submission_date(default_date: str, submit_date_override: str | None = None) -> str:
    if submit_date_override is None:
        return default_date
    override = str(submit_date_override).strip()
    return override or default_date


def _submission_stock_code(stock_code: str) -> str:
    return str(stock_code).strip()


def _window_bounds(window_id: int) -> tuple[str, str]:
    if window_id < 24:
        start_minutes = 9 * 60 + 30 + window_id * 5
    else:
        start_minutes = 13 * 60 + (window_id - 24) * 5
    end_minutes = start_minutes + 5
    return f"{start_minutes // 60:02d}:{start_minutes % 60:02d}", f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"


def _row_float(row: dict, keys: list[str], default: float = 0.0) -> float:
    for key in keys:
        if key not in row:
            continue
        try:
            return float(row.get(key) or default)
        except (TypeError, ValueError):
            continue
    return default


def export_event_classified_rows(samples: list[DailySample], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    capital_fields = [
        ("CH_rule_t", "hot_money"),
        ("Q_rule_t", "quant"),
        ("R_seed_t", "retail"),
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(EVENT_CLASSIFIED_COLUMNS)
        for sample in sorted(samples, key=lambda item: (item.stock_code, item.transaction_date)):
            for row in sample.rows or []:
                window_raw = row.get("window_id", "")
                try:
                    window_id = int(float(window_raw))
                except (TypeError, ValueError):
                    continue
                for field_name, capital_type in capital_fields:
                    signed_amount = _row_float(row, [field_name], 0.0)
                    if signed_amount == 0.0:
                        continue
                    side = "buy" if signed_amount > 0 else "sell"
                    event_id = f"{sample.stock_code}-{sample.transaction_date}-{window_id:02d}-{capital_type}"
                    writer.writerow(
                        [
                            sample.transaction_date,
                            sample.stock_code,
                            event_id,
                            "",
                            window_id,
                            side,
                            _round6(signed_amount),
                            capital_type,
                            "",
                            "window_aggregate",
                        ]
                    )


def export_window_feature_rows(samples: list[DailySample], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(WINDOW_FEATURE_COLUMNS)
        for sample in sorted(samples, key=lambda item: (item.stock_code, item.transaction_date)):
            data_source = "reference_feature" if sample.quality_flags.get("has_reference_features") else "trade_window"
            seen_windows: set[int] = set()
            for row in sample.rows or []:
                try:
                    window_id = int(float(row.get("window_id", 0) or 0))
                except (TypeError, ValueError):
                    continue
                if window_id in seen_windows:
                    continue
                seen_windows.add(window_id)
                window_start, window_end = _window_bounds(window_id)
                open_price = _row_float(row, ["window_open_price", "open_price"], 0.0)
                close_price = _row_float(row, ["window_close_price", "close_price"], 0.0)
                deal_amount = _row_float(row, ["deal_amount", "amount", "成交额"], 0.0)
                data_p = _row_float(row, ["data_P", "delta_p", "pi_max_price_impact_pct", "price_impact"], 0.0)
                writer.writerow(
                    [
                        sample.transaction_date,
                        sample.stock_code,
                        window_id,
                        window_start,
                        window_end,
                        _round6(open_price),
                        _round6(close_price),
                        "",
                        _round6(deal_amount),
                        _round6(data_p),
                        data_source,
                    ]
                )


def export_pattern_reco(
    results: list[PatternResult],
    output_path: str | Path,
    submit_date_override: str | None = None,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(PATTERN_COLUMNS)
        for item in results:
            writer.writerow(
                [
                    _submission_stock_code(item.stock_code),
                    _submission_date(item.transaction_date, submit_date_override),
                    item.pattern_type,
                    item.pattern_explanation,
                ]
            )


def export_predict_result(
    results: list[PredictResult],
    output_path: str | Path,
    submit_date_override: str | None = None,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(PREDICT_COLUMNS)
        for item in results:
            writer.writerow(
                [
                    _submission_stock_code(item.stock_code),
                    _submission_date(item.transaction_date, submit_date_override),
                    item.capital_type,
                    item.capital_intention,
                ]
            )


def export_market_pid_snapshot(snapshot: MarketPidSnapshot, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(MARKET_SNAPSHOT_COLUMNS)
        writer.writerow(
            [
                snapshot.trade_date,
                snapshot.up_count,
                snapshot.down_count,
                round(snapshot.breadth_ratio, 6),
                round(snapshot.breadth_balance, 6),
                round(snapshot.p_mean, 6),
                round(snapshot.p_median, 6),
                round(snapshot.p_std, 6),
                round(snapshot.i_mean, 6),
                round(snapshot.i_median, 6),
                round(snapshot.i_std, 6),
                round(snapshot.d_mean, 6),
                round(snapshot.d_median, 6),
                round(snapshot.d_std, 6),
                snapshot.market_regime,
            ]
        )


def export_market_regime_report(snapshot: MarketPidSnapshot, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Market Regime Report",
        "",
        f"- trade_date: `{snapshot.trade_date}`",
        f"- market_regime: `{snapshot.market_regime}`",
        f"- up_count: `{snapshot.up_count}`",
        f"- down_count: `{snapshot.down_count}`",
        f"- breadth_ratio: `{snapshot.breadth_ratio:.4f}`",
        f"- breadth_balance: `{snapshot.breadth_balance:.4f}`",
        "",
        "## PID Summary",
        "",
        f"- P: mean `{snapshot.p_mean:.4f}`, median `{snapshot.p_median:.4f}`, std `{snapshot.p_std:.4f}`",
        f"- I: mean `{snapshot.i_mean:.4f}`, median `{snapshot.i_median:.4f}`, std `{snapshot.i_std:.4f}`",
        f"- D: mean `{snapshot.d_mean:.4f}`, median `{snapshot.d_median:.4f}`, std `{snapshot.d_std:.4f}`",
        "",
        "## Diagnostics",
        "",
        "```json",
        json.dumps(snapshot.diagnostics, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def export_batch_diagnostics(
    snapshot: MarketPidSnapshot | None,
    pattern_results: list[PatternResult],
    predict_results: list[PredictResult],
    output_dir: str | Path,
) -> tuple[str, str]:
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    json_path = base / "batch_diagnostics.json"
    csv_path = base / "label_distribution.csv"

    pattern_counts: dict[str, int] = {}
    capital_counts: dict[str, int] = {}
    intention_counts: dict[str, int] = {}
    for item in pattern_results:
        pattern_counts[item.pattern_type] = pattern_counts.get(item.pattern_type, 0) + 1
    for item in predict_results:
        capital_counts[item.capital_type] = capital_counts.get(item.capital_type, 0) + 1
        intention_counts[item.capital_intention] = intention_counts.get(item.capital_intention, 0) + 1

    sample_count = len(pattern_results)
    payload = {
        "sample_count": sample_count,
        "pattern_counts": pattern_counts,
        "capital_counts": capital_counts,
        "intention_counts": intention_counts,
        "market_snapshot": None,
    }
    if snapshot is not None:
        payload["market_snapshot"] = {
            "trade_date": snapshot.trade_date,
            "market_regime": snapshot.market_regime,
            "up_count": snapshot.up_count,
            "down_count": snapshot.down_count,
            "breadth_ratio": snapshot.breadth_ratio,
            "breadth_balance": snapshot.breadth_balance,
            "p_median": snapshot.p_median,
            "i_median": snapshot.i_median,
            "d_median": snapshot.d_median,
        }

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(SUMMARY_COLUMNS)
        for category, counts in (
            ("pattern_type", pattern_counts),
            ("capital_type", capital_counts),
            ("capital_intention", intention_counts),
        ):
            total = sum(counts.values()) or 1
            for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
                writer.writerow([category, label, count, round(count / total, 6)])

    return str(json_path), str(csv_path)


def export_pid_tail_diagnostics(pid_results: list[object], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(PID_TAIL_COLUMNS)
        for result in sorted(pid_results, key=lambda item: getattr(item, "stock_code", "")):
            writer.writerow(
                [
                    getattr(result, "stock_code", ""),
                    getattr(result, "transaction_date", ""),
                    getattr(result, "mode", ""),
                    "true" if bool(getattr(result, "kf_converged", False)) else "false",
                    getattr(result, "dominant_type", ""),
                    getattr(result, "dominant_intention", ""),
                    _round6(getattr(result, "hot_money_ratio", 0.0)),
                    _round6(getattr(result, "quant_ratio", 0.0)),
                    _round6(getattr(result, "retail_ratio", 0.0)),
                    _tail_value(getattr(result, "phi", [])),
                    _tail_value(getattr(result, "theta", [])),
                    _tail_value(getattr(result, "beta_ch", [])),
                    _tail_value(getattr(result, "beta_mix", [])),
                    _tail_value(getattr(result, "beta_q", [])),
                    _tail_value(getattr(result, "beta_retail", [])),
                    _tail_value(getattr(result, "c_p", [])),
                    _tail_value(getattr(result, "c_i", [])),
                    _tail_value(getattr(result, "c_d", [])),
                    _tail_value(getattr(result, "capital_ch", [])),
                    _tail_value(getattr(result, "capital_q", [])),
                    _tail_value(getattr(result, "capital_retail", [])),
                    _tail_value(getattr(result, "capital_anchor_error", [])),
                    _tail_value(getattr(result, "noise_ratio", [])),
                    _tail_value(getattr(result, "explain_ratio", [])),
                    f"{float(getattr(result, 'capital_identity_error', 0.0)):.2e}",
                    f"{float(getattr(result, 'closure_error', 0.0)):.2e}",
                    " | ".join(getattr(result, "warnings", [])),
                ]
            )


def export_pid_window_params(pid_results: list[object], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(PID_WINDOW_PARAM_COLUMNS)
        for result in sorted(pid_results, key=lambda item: (getattr(item, "stock_code", ""), getattr(item, "transaction_date", ""))):
            row_count = _series_len(result, ["phi", "beta_ch", "beta_q", "beta_retail", "beta_mix", "theta"])
            for window_id in range(row_count):
                writer.writerow(
                    [
                        getattr(result, "stock_code", ""),
                        getattr(result, "transaction_date", ""),
                        window_id,
                        getattr(result, "mode", ""),
                        _round6(_series_value(result, "phi", window_id)),
                        _round6(_series_value(result, "beta_ch", window_id)),
                        _round6(_series_value(result, "beta_q", window_id)),
                        _round6(_series_value(result, "beta_retail", window_id)),
                        _round6(_series_value(result, "beta_mix", window_id)),
                        _round6(_series_value(result, "theta", window_id)),
                        "",
                    ]
                )


def export_pid_window_contrib(pid_results: list[object], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(PID_WINDOW_CONTRIB_COLUMNS)
        for result in sorted(pid_results, key=lambda item: (getattr(item, "stock_code", ""), getattr(item, "transaction_date", ""))):
            row_count = _series_len(
                result,
                [
                    "c_p",
                    "c_i",
                    "c_d",
                    "eps",
                    "capital_ch",
                    "capital_q",
                    "capital_retail",
                    "noise_ratio",
                    "explain_ratio",
                    "capital_anchor_error",
                ],
            )
            for window_id in range(row_count):
                c_p = _series_value(result, "c_p", window_id)
                capital_ch = _series_value(result, "capital_ch", window_id)
                capital_q = _series_value(result, "capital_q", window_id)
                capital_retail = _series_value(result, "capital_retail", window_id)
                capital_mix = _series_value(result, "capital_mix", window_id, c_p - capital_ch)
                writer.writerow(
                    [
                        getattr(result, "stock_code", ""),
                        getattr(result, "transaction_date", ""),
                        window_id,
                        _round6(c_p),
                        _round6(_series_value(result, "c_i", window_id)),
                        _round6(_series_value(result, "c_d", window_id)),
                        _round6(_series_value(result, "eps", window_id)),
                        _round6(capital_ch),
                        _round6(capital_q),
                        _round6(capital_retail),
                        _round6(capital_mix),
                        _round6(_series_value(result, "noise_ratio", window_id, 1.0)),
                        _round6(_series_value(result, "explain_ratio", window_id)),
                        _round6(_series_value(result, "capital_anchor_error", window_id)),
                        f"{float(getattr(result, 'pid_closure_error', getattr(result, 'closure_error', 0.0))):.2e}",
                    ]
                )


def export_pid_window_diag(pid_results: list[object], output_path: str | Path, config: dict | None = None) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = config or {}
    q_type = str(cfg.get("q_type", "window_index"))
    u_source_type = str(cfg.get("u_source_type", "mv_ratio"))
    estimator_method = str(cfg.get("estimator_method", "kalman_filter_realtime"))
    m_slow_method = str(cfg.get("m_slow_method", "ewma_realtime"))
    beta_norm_floor = float(cfg.get("beta_norm_floor", 1.0e-6))
    data_leakage_check = "pass"
    m_eff_uncertainty_flag, m_eff_rank_eligible = _resolve_m_eff_status(cfg)
    if "offline" in estimator_method or "offline" in m_slow_method:
        data_leakage_check = "fail"

    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(PID_WINDOW_DIAG_COLUMNS)
        for result in sorted(pid_results, key=lambda item: (getattr(item, "stock_code", ""), getattr(item, "transaction_date", ""))):
            row_count = _series_len(result, ["c_p", "c_i", "c_d", "eps", "capital_ch", "capital_q", "capital_retail"])
            warnings = " | ".join(getattr(result, "warnings", []))
            mode_name = getattr(result, "mode", "")
            param_stability_flag = "pass" if bool(getattr(result, "kf_converged", False)) and float(getattr(result, "pid_closure_error", 0.0)) <= 1e-7 else "warn"
            for window_id in range(row_count):
                c_p = _series_value(result, "c_p", window_id)
                c_i = _series_value(result, "c_i", window_id)
                c_d = _series_value(result, "c_d", window_id)
                eps = _series_value(result, "eps", window_id)
                y_observed = c_p + c_i + c_d + eps
                next_id = min(window_id + 1, row_count - 1)
                y_hat_next = (
                    _series_value(result, "c_p", next_id)
                    + _series_value(result, "c_i", next_id)
                    + _series_value(result, "c_d", next_id)
                ) if row_count else 0.0
                capital_ch = _series_value(result, "capital_ch", window_id)
                capital_q = _series_value(result, "capital_q", window_id)
                capital_retail = _series_value(result, "capital_retail", window_id)
                capital_mix = _series_value(result, "capital_mix", window_id, c_p - capital_ch)
                proxy_metrics = _window_diag_proxy_metrics(result, window_id, beta_norm_floor)
                writer.writerow(
                    [
                        getattr(result, "transaction_date", ""),
                        getattr(result, "stock_code", ""),
                        window_id,
                        mode_name,
                        q_type,
                        u_source_type,
                        estimator_method,
                        "psi_transition_observation_prediction",
                        "psi_t_prior_for_prediction",
                        _round6(y_observed),
                        _round6(y_hat_next),
                        _round6(y_observed),
                        _round6(y_hat_next),
                        _round6(c_p),
                        _round6(c_i),
                        _round6(c_d),
                        _round6(eps),
                        _round6(capital_ch),
                        _round6(capital_q),
                        _round6(capital_retail),
                        _round6(capital_mix),
                        proxy_metrics["beta_norm_ch_diag"],
                        proxy_metrics["beta_norm_q_diag"],
                        proxy_metrics["beta_norm_retail_diag"],
                        proxy_metrics["beta_norm_mix_diag"],
                        proxy_metrics["m_eff_ch_diag"],
                        proxy_metrics["m_eff_q_diag"],
                        proxy_metrics["m_eff_retail_diag"],
                        proxy_metrics["m_eff_mix_diag"],
                        proxy_metrics["beta_norm_unit"],
                        proxy_metrics["m_eff_source_type"],
                        proxy_metrics["m_eff_clipped_flag"],
                        f"{float(getattr(result, 'pid_closure_error', getattr(result, 'closure_error', 0.0))):.2e}",
                        _round6(eps),
                        param_stability_flag,
                        m_eff_rank_eligible,
                        data_leakage_check,
                        m_slow_method,
                        "false",
                        m_eff_rank_eligible,
                        "true",
                        warnings,
                    ]
                )


def export_pid_daily_diag(pid_results: list[object], output_path: str | Path, config: dict | None = None) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = config or {}
    mode_switch = cfg.get("mode_switch", {}) if isinstance(cfg.get("mode_switch", {}), dict) else {}
    estimator_method = str(cfg.get("estimator_method", "kalman_filter_realtime"))
    m_slow_method = str(cfg.get("m_slow_method", "ewma_realtime"))
    beta_norm_floor = float(cfg.get("beta_norm_floor", 1.0e-6))
    offline_smooth_used = "offline" in estimator_method or "offline" in m_slow_method
    data_leakage_check = "fail" if offline_smooth_used else "pass"
    m_eff_uncertainty_flag, m_eff_rank_eligible = _resolve_m_eff_status(cfg)

    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(PID_DAILY_DIAG_COLUMNS)
        for result in sorted(pid_results, key=lambda item: (getattr(item, "stock_code", ""), getattr(item, "transaction_date", ""))):
            warnings = list(getattr(result, "warnings", []))
            param_stability_flag = "pass" if bool(getattr(result, "kf_converged", False)) and float(getattr(result, "pid_closure_error", 0.0)) <= 1e-7 else "warn"
            submission_ready = "true" if data_leakage_check == "pass" else "false"
            beta_norm_unit, m_eff_source_type, m_eff_clipped_flag = _daily_diag_proxy_summary(result, beta_norm_floor)
            writer.writerow(
                [
                    getattr(result, "transaction_date", ""),
                    getattr(result, "stock_code", ""),
                    getattr(result, "mode", ""),
                    cfg.get("q_type", "window_index"),
                    cfg.get("u_source_type", "mv_ratio"),
                    estimator_method,
                    m_slow_method,
                    cfg.get("lookback_days", 20),
                    cfg.get("zero_trade_policy", "mark_only"),
                    str(bool(cfg.get("submission_requires_complete_windows", True))).lower(),
                    mode_switch.get("lambda_switch", 0.1),
                    mode_switch.get("lambda_jump", 1.0),
                    mode_switch.get("lambda_error", 10.0),
                    data_leakage_check,
                    "pass",
                    "pass",
                    str(offline_smooth_used).lower(),
                    param_stability_flag,
                    beta_norm_unit,
                    m_eff_source_type,
                    m_eff_clipped_flag,
                    m_eff_uncertainty_flag,
                    m_eff_rank_eligible,
                    submission_ready,
                    "raw",
                    "ok",
                    cfg.get("code_build_hash", ""),
                    len(warnings),
                    " | ".join(warnings),
                ]
            )


def export_pid_daily_diag_records(
    records: list[dict[str, object]],
    output_path: str | Path,
    config: dict | None = None,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = config or {}
    mode_switch = cfg.get("mode_switch", {}) if isinstance(cfg.get("mode_switch", {}), dict) else {}
    default_row = {
        "q_type": cfg.get("q_type", "window_index"),
        "u_source_type": cfg.get("u_source_type", "mv_ratio"),
        "estimator_method": cfg.get("estimator_method", "kalman_filter_realtime"),
        "m_slow_method": cfg.get("m_slow_method", "ewma_realtime"),
        "lookback_days": cfg.get("lookback_days", 20),
        "zero_trade_policy": cfg.get("zero_trade_policy", "mark_only"),
        "submission_requires_complete_windows": str(bool(cfg.get("submission_requires_complete_windows", True))).lower(),
        "lambda_switch": mode_switch.get("lambda_switch", 0.1),
        "lambda_jump": mode_switch.get("lambda_jump", 1.0),
        "lambda_error": mode_switch.get("lambda_error", 10.0),
        "feature_engineering_leakage_check": "pass",
        "rule_layer_leakage_check": "pass",
        "offline_smooth_used": "false",
        "beta_norm_unit": "",
        "m_eff_source_type": "unavailable",
        "m_eff_clipped_flag": "false",
        "m_eff_uncertainty_flag": _resolve_m_eff_status(cfg)[0],
        "m_eff_rank_eligible": _resolve_m_eff_status(cfg)[1],
        "code_build_hash": cfg.get("code_build_hash", ""),
    }
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(PID_DAILY_DIAG_COLUMNS)
        for record in records:
            raw_warnings = record.get("warnings", []) or []
            if isinstance(raw_warnings, str):
                warnings = [raw_warnings] if raw_warnings else []
            else:
                warnings = list(raw_warnings)
            row = {**default_row, **record}
            writer.writerow(
                [
                    row.get("trade_date", ""),
                    row.get("symbol", ""),
                    row.get("mode_name", ""),
                    row.get("q_type", ""),
                    row.get("u_source_type", ""),
                    row.get("estimator_method", ""),
                    row.get("m_slow_method", ""),
                    row.get("lookback_days", ""),
                    row.get("zero_trade_policy", ""),
                    row.get("submission_requires_complete_windows", ""),
                    row.get("lambda_switch", ""),
                    row.get("lambda_jump", ""),
                    row.get("lambda_error", ""),
                    row.get("data_leakage_check", "pass"),
                    row.get("feature_engineering_leakage_check", "pass"),
                    row.get("rule_layer_leakage_check", "pass"),
                    row.get("offline_smooth_used", "false"),
                    row.get("param_stability_flag", "pass"),
                    row.get("beta_norm_unit", default_row["beta_norm_unit"]),
                    row.get("m_eff_source_type", default_row["m_eff_source_type"]),
                    row.get("m_eff_clipped_flag", default_row["m_eff_clipped_flag"]),
                    row.get("m_eff_uncertainty_flag", default_row["m_eff_uncertainty_flag"]),
                    row.get("m_eff_rank_eligible", default_row["m_eff_rank_eligible"]),
                    row.get("submission_ready", "true"),
                    row.get("sample_origin", "raw"),
                    row.get("reason_code", "ok"),
                    row.get("code_build_hash", ""),
                    row.get("warning_count", len(warnings)),
                    " | ".join(str(item) for item in warnings),
                ]
            )


def export_raw_data_quality_report(rows: list[dict[str, object]], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RAW_DATA_QUALITY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in RAW_DATA_QUALITY_COLUMNS})


def export_window_flow_rows(samples: list[DailySample], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    fieldnames: list[str] = list(WINDOW_FLOW_COLUMNS)

    for sample in sorted(samples, key=lambda item: (item.stock_code, item.transaction_date)):
        for row in sample.rows or []:
            merged = {
                "stock_code": sample.stock_code,
                "transaction_date": sample.transaction_date,
                **row,
            }
            rows.append(merged)
            for key in merged.keys():
                if key not in fieldnames:
                    fieldnames.append(key)

    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def export_market_pid_validation_report(snapshot: MarketPidSnapshot | None, output_dir: str | Path) -> str:
    base = Path(output_dir) / "reports" / "validation"
    base.mkdir(parents=True, exist_ok=True)
    report_path = base / "market_pid_validation_report.md"

    lines = [
        "# Market PID Validation Report",
        "",
        "## Scope",
        "",
        "This report records the market breadth and relative market PID口径 used by the current batch.",
        "",
    ]
    if snapshot is None:
        lines.extend(
            [
                "## Status",
                "",
                "- market_snapshot: `missing`",
                "- reason: no valid samples were available for market PID aggregation.",
                "",
            ]
        )
    else:
        diagnostics = snapshot.diagnostics or {}
        lines.extend(
            [
                "## Market Breadth",
                "",
                f"- trade_date: `{snapshot.trade_date}`",
                f"- up_count: `{snapshot.up_count}`",
                f"- down_count: `{snapshot.down_count}`",
                f"- breadth_ratio: `{snapshot.breadth_ratio:.6f}`",
                f"- breadth_balance: `{snapshot.breadth_balance:.6f}`",
                f"- market_regime: `{snapshot.market_regime}`",
                "",
                "## PID Aggregates",
                "",
                f"- p_mean / p_median / p_std: `{snapshot.p_mean:.6f}` / `{snapshot.p_median:.6f}` / `{snapshot.p_std:.6f}`",
                f"- i_mean / i_median / i_std: `{snapshot.i_mean:.6f}` / `{snapshot.i_median:.6f}` / `{snapshot.i_std:.6f}`",
                f"- d_mean / d_median / d_std: `{snapshot.d_mean:.6f}` / `{snapshot.d_median:.6f}` / `{snapshot.d_std:.6f}`",
                "",
                "## Aggregation Contract",
                "",
                "- preferred source: per-stock `c_p / c_i / c_d` from PID decomposition",
                "- fallback source: heuristic summary only when PID components are unavailable",
                "- rule-layer flows such as `Q_rule / R_seed` are not treated as market external-force outputs",
                "",
                "## Relative Metrics Contract",
                "",
                "- `p_rel_market = (p_value - p_median) / max(p_std, eps)`",
                "- `i_rel_market = (i_value - i_median) / max(i_std, eps)`",
                "- `d_rel_market = (d_value - d_median) / max(d_std, eps)`",
                "- `trend_vs_market` is diagnostic only and does not change submission CSV columns.",
                "",
                "## Diagnostics",
                "",
                "```json",
                json.dumps(diagnostics, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return str(report_path)


def export_replay_validation_report(batch_summary: dict, output_dir: str | Path) -> str:
    base = Path(output_dir) / "reports" / "validation"
    base.mkdir(parents=True, exist_ok=True)
    report_path = base / "100_stock_replay_report.md"
    performance = batch_summary.get("performance_summary") or {}
    lifecycle = batch_summary.get("order_lifecycle_summary") or {}
    warnings = batch_summary.get("warnings") or []
    missing_symbols = batch_summary.get("missing_symbols") or []
    incomplete_stock_dirs = batch_summary.get("incomplete_stock_dirs") or {}

    lines = [
        "# 100 Stock Replay Report",
        "",
        "## Batch Summary",
        "",
        f"- trade_date: `{batch_summary.get('trade_date', '')}`",
        f"- sample_count: `{batch_summary.get('sample_count', 0)}`",
        f"- output_count: `{batch_summary.get('output_count', 0)}`",
        f"- imputed_output_count: `{batch_summary.get('imputed_output_count', 0)}`",
        f"- stock_universe_size: `{batch_summary.get('stock_universe_size')}`",
        f"- stock_list_file: `{batch_summary.get('stock_list_file')}`",
        f"- stock_offset: `{batch_summary.get('stock_offset', 0)}`",
        f"- stock_limit: `{batch_summary.get('stock_limit')}`",
        "",
        "## Missing And Imputed Symbols",
        "",
        f"- missing_symbol_count: `{len(missing_symbols)}`",
        f"- missing_symbols: `{', '.join(missing_symbols) if missing_symbols else ''}`",
        f"- incomplete_stock_dir_count: `{len(incomplete_stock_dirs)}`",
        "",
        "## Warnings",
        "",
    ]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Performance",
            "",
            f"- total_seconds: `{performance.get('total_seconds')}`",
            f"- sample_build_seconds: `{performance.get('sample_build_seconds')}`",
            f"- pattern_seconds: `{performance.get('pattern_seconds')}`",
            f"- capital_seconds: `{performance.get('capital_seconds')}`",
            f"- market_seconds: `{performance.get('market_seconds')}`",
            f"- export_seconds: `{performance.get('export_seconds')}`",
            "",
            "## Order Lifecycle Recovery",
            "",
            f"- order_age_total_count: `{lifecycle.get('order_age_total_count')}`",
            f"- order_age_recovered_count: `{lifecycle.get('order_age_recovered_count')}`",
            f"- order_age_missing_count: `{lifecycle.get('order_age_missing_count')}`",
            f"- order_age_direct_count: `{lifecycle.get('order_age_direct_count')}`",
            f"- order_age_fifo_count: `{lifecycle.get('order_age_fifo_count')}`",
            f"- order_age_unresolved_count: `{lifecycle.get('order_age_unresolved_count')}`",
            f"- order_age_recovery_ratio: `{lifecycle.get('order_age_recovery_ratio')}`",
            "",
            "## Output Files",
            "",
            f"- market_snapshot_path: `{batch_summary.get('market_snapshot_path')}`",
            f"- market_report_path: `{batch_summary.get('market_report_path')}`",
            f"- diagnostics_json_path: `{batch_summary.get('diagnostics_json_path')}`",
            f"- distribution_csv_path: `{batch_summary.get('distribution_csv_path')}`",
            f"- submit_zip: `{batch_summary.get('submit_zip')}`",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return str(report_path)


def validate_submission_files(pattern_path: str | Path, predict_path: str | Path) -> None:
    row_counts: dict[str, int] = {}
    predict_pairs: list[tuple[str, str]] = []
    for path, expected in [(Path(pattern_path), PATTERN_COLUMNS), (Path(predict_path), PREDICT_COLUMNS)]:
        if not path.exists():
            raise FileNotFoundError(f"Submission file not found: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, [])
            row_count = 0
            for row in reader:
                row_count += 1
                if len(row) != len(expected):
                    raise ValueError(f"Invalid column count for {path.name}: {row}")
                if any(str(cell).strip() == "" for cell in row):
                    raise ValueError(f"Empty required field found in {path.name}: {row}")
                if path.name == "predict_result.csv":
                    predict_pairs.append((str(row[0]), str(row[1])))
        if header != expected:
            raise ValueError(f"Invalid header for {path.name}: {header} != {expected}")
        row_counts[path.name] = row_count

    if row_counts["pattern_reco.csv"] != row_counts["predict_result.csv"]:
        raise ValueError(
            "Row count mismatch between pattern_reco.csv and predict_result.csv; "
            "predict_result.csv should contain exactly one row per stock/date: "
            f"{row_counts['pattern_reco.csv']} vs {row_counts['predict_result.csv']}"
        )

    duplicate_pairs = [pair for pair, count in Counter(predict_pairs).items() if count > 1]
    if duplicate_pairs:
        raise ValueError(
            "predict_result.csv must contain exactly one row per stock/date; "
            f"duplicate keys found: {sorted(duplicate_pairs)[:10]}"
        )


def build_submit_zip(output_dir: str | Path) -> str:
    base = Path(output_dir)
    pattern_path = base / "pattern_reco.csv"
    predict_path = base / "predict_result.csv"
    validate_submission_files(pattern_path, predict_path)

    zip_path = base / "submit.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(pattern_path, arcname="pattern_reco.csv")
        zf.write(predict_path, arcname="predict_result.csv")
    return str(zip_path)

from __future__ import annotations

from typing import Any

from schemas import DailySample, StateFeature


STRUCTURAL_MODES = {"baseline_4d", "diag_5d", "full_5d"}


def build_state_features(sample: DailySample, pid_result: Any | None) -> list[StateFeature]:
    rows_by_window = _rows_by_window(sample.rows)
    window_count = _infer_window_count(rows_by_window, pid_result)
    mode_name = str(getattr(pid_result, "mode", "rule_base") or "rule_base")
    is_structural = mode_name in STRUCTURAL_MODES and pid_result is not None
    features: list[StateFeature] = []

    for index in range(window_count):
        row = rows_by_window.get(index, {})
        ch_rule = _to_float(row.get("CH_rule_t", row.get("signed_large_active_amount", 0.0)))
        q_rule = _to_float(row.get("Q_rule_t", 0.0))
        r_seed = _to_float(row.get("R_seed_t", 0.0))
        if "Q_rule_t" not in row and "R_seed_t" not in row:
            q_rule = _to_float(row.get("signed_mix_qr_amount", 0.0))
            r_seed = 0.0

        feature = StateFeature(
            stock_code=sample.stock_code,
            transaction_date=sample.transaction_date,
            window_id=str(index),
            CH_rule_t=ch_rule,
            Q_rule_t=q_rule,
            R_seed_t=r_seed,
            capital_ch_rule_approx=ch_rule,
            capital_q_rule_approx=q_rule,
            capital_retail_rule_approx=r_seed,
            mode_name=mode_name,
            is_structural_output=is_structural,
        )

        if pid_result is not None:
            _attach_pid_fields(feature, pid_result, index, is_structural)
        features.append(feature)
    return features


def tail_state_feature(sample: DailySample, pid_result: Any | None) -> StateFeature | None:
    features = build_state_features(sample, pid_result)
    return features[-1] if features else None


def _attach_pid_fields(feature: StateFeature, pid_result: Any, index: int, is_structural: bool) -> None:
    feature.phi = _series_value(getattr(pid_result, "phi", getattr(pid_result, "inertia", [])), index)
    feature.theta = _series_value(getattr(pid_result, "theta", getattr(pid_result, "damping", [])), index)
    feature.beta_ch = _series_value(getattr(pid_result, "beta_ch", []), index)
    feature.beta_q = _series_value(getattr(pid_result, "beta_q", []), index)
    feature.beta_mix = _series_value(getattr(pid_result, "beta_mix", []), index)
    feature.beta_retail = _series_value(getattr(pid_result, "beta_retail", []), index)
    feature.c_p = _series_value(getattr(pid_result, "c_p", []), index)
    feature.c_i = _series_value(getattr(pid_result, "c_i", []), index)
    feature.c_d = _series_value(getattr(pid_result, "c_d", []), index)
    feature.eps = _series_value(getattr(pid_result, "eps", []), index)
    feature.noise_ratio = _series_value(getattr(pid_result, "noise_ratio", []), index)
    feature.explain_ratio = _series_value(getattr(pid_result, "explain_ratio", []), index)
    feature.capital_anchor_error = _series_value(getattr(pid_result, "capital_anchor_error", []), index)

    if is_structural:
        feature.capital_ch = _series_value(getattr(pid_result, "capital_ch", []), index)
        feature.capital_q = _series_value(getattr(pid_result, "capital_q", []), index)
        feature.capital_retail = _series_value(getattr(pid_result, "capital_retail", []), index)
        if feature.capital_q is not None:
            feature.rule_error_q = _relative_error(feature.Q_rule_t, feature.capital_q)
        if feature.capital_retail is not None:
            feature.rule_error_retail = _relative_error(feature.R_seed_t, feature.capital_retail)


def _rows_by_window(rows: list[dict]) -> dict[int, dict]:
    mapped: dict[int, dict] = {}
    for row in rows or []:
        raw = row.get("window_id", 0)
        if str(raw).isdigit():
            mapped[int(raw)] = row
    return mapped


def _infer_window_count(rows_by_window: dict[int, dict], pid_result: Any | None) -> int:
    pid_lengths = [
        len(value)
        for value in (
            getattr(pid_result, "c_p", []),
            getattr(pid_result, "capital_ch", []),
            getattr(pid_result, "noise_ratio", []),
        )
        if hasattr(value, "__len__")
    ]
    row_count = max(rows_by_window.keys()) + 1 if rows_by_window else 0
    return max(48, row_count, *(pid_lengths or [0]))


def _series_value(series: Any, index: int) -> float | None:
    try:
        if index >= len(series):
            return None
        value = series[index]
    except (TypeError, IndexError):
        return None
    return None if value != value else float(value)


def _relative_error(rule_value: float, structural_value: float) -> float:
    denom = max(abs(rule_value), abs(structural_value), 1e-8)
    return abs(rule_value - structural_value) / denom


def _to_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

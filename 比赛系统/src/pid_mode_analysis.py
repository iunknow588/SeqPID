from __future__ import annotations

import csv
import math
from copy import deepcopy
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Iterable

from pid_decomposer import PIDDecomposer
from scheduler import _load_daily_samples


TAIL_METRICS = [
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
]


def _resolve_trade_input_dir(input_root: str | Path, trade_date: str) -> Path:
    base = Path(input_root)
    candidates = [base / trade_date / trade_date, base / trade_date, base]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return base


def _tail_float(values: object) -> float:
    try:
        iterable = list(values)
    except TypeError:
        return math.nan
    for value in reversed(iterable):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            return numeric
    return math.nan


def _round6(value: float) -> float | str:
    if not math.isfinite(value):
        return ""
    return round(float(value), 6)


def _safe_cv(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    abs_mean = mean(abs(value) for value in values)
    if abs_mean <= 1e-8:
        return pstdev(values)
    return pstdev(values) / abs_mean


def _stability_label(values: list[float]) -> str:
    if len(values) < 2:
        return "insufficient_history"
    non_zero_signs = [1 if value > 0 else -1 for value in values if abs(value) > 1e-8]
    sign_consistent = len(set(non_zero_signs)) <= 1 if non_zero_signs else True
    cv_value = _safe_cv(values)
    if sign_consistent and cv_value <= 0.35:
        return "stable"
    if sign_consistent and cv_value <= 0.75:
        return "mostly_stable"
    return "unstable"


def _result_tail_row(result: object) -> dict[str, object]:
    return {
        "stock_code": getattr(result, "stock_code", ""),
        "transaction_date": getattr(result, "transaction_date", ""),
        "mode": getattr(result, "mode", ""),
        "kf_converged": bool(getattr(result, "kf_converged", False)),
        "dominant_type": getattr(result, "dominant_type", ""),
        "dominant_intention": getattr(result, "dominant_intention", ""),
        "warnings": " | ".join(getattr(result, "warnings", [])),
        "phi_tail": _tail_float(getattr(result, "phi", [])),
        "theta_tail": _tail_float(getattr(result, "theta", [])),
        "beta_ch_tail": _tail_float(getattr(result, "beta_ch", [])),
        "beta_mix_tail": _tail_float(getattr(result, "beta_mix", [])),
        "beta_q_tail": _tail_float(getattr(result, "beta_q", [])),
        "beta_retail_tail": _tail_float(getattr(result, "beta_retail", [])),
        "c_p_tail": _tail_float(getattr(result, "c_p", [])),
        "c_i_tail": _tail_float(getattr(result, "c_i", [])),
        "c_d_tail": _tail_float(getattr(result, "c_d", [])),
        "capital_ch_tail": _tail_float(getattr(result, "capital_ch", [])),
        "capital_q_tail": _tail_float(getattr(result, "capital_q", [])),
        "capital_retail_tail": _tail_float(getattr(result, "capital_retail", [])),
        "capital_anchor_error_tail": _tail_float(getattr(result, "capital_anchor_error", [])),
        "noise_ratio_tail": _tail_float(getattr(result, "noise_ratio", [])),
        "explain_ratio_tail": _tail_float(getattr(result, "explain_ratio", [])),
    }


def compare_pid_modes(samples: list[object], config: dict, modes: tuple[str, str] = ("baseline_4d", "diag_5d")) -> list[dict[str, object]]:
    if len(modes) != 2:
        raise ValueError("compare_pid_modes currently expects exactly two modes")

    results_by_mode: dict[str, dict[str, dict[str, object]]] = {}
    for mode in modes:
        mode_config = deepcopy(config)
        mode_config.setdefault("pid_decomposer", {})
        mode_config["pid_decomposer"]["mode"] = mode
        decomposer = PIDDecomposer(mode_config)
        rows: dict[str, dict[str, object]] = {}
        for sample in samples:
            result = decomposer.decompose_sample(sample)
            rows[getattr(sample, "stock_code", "")] = _result_tail_row(result)
        results_by_mode[mode] = rows

    left_mode, right_mode = modes
    symbols = sorted(set(results_by_mode[left_mode]) | set(results_by_mode[right_mode]))
    comparison_rows: list[dict[str, object]] = []
    for symbol in symbols:
        left = results_by_mode[left_mode].get(symbol, {})
        right = results_by_mode[right_mode].get(symbol, {})
        row: dict[str, object] = {
            "stock_code": symbol,
            "transaction_date": left.get("transaction_date") or right.get("transaction_date") or "",
            "left_mode": left_mode,
            "right_mode": right_mode,
            "left_dominant_type": left.get("dominant_type", ""),
            "right_dominant_type": right.get("dominant_type", ""),
            "left_kf_converged": left.get("kf_converged", False),
            "right_kf_converged": right.get("kf_converged", False),
            "same_dominant_type": left.get("dominant_type", "") == right.get("dominant_type", ""),
            "beta_qr_gap_5d": (
                float(right.get("beta_q_tail", math.nan)) + float(right.get("beta_retail_tail", math.nan))
                if math.isfinite(float(right.get("beta_q_tail", math.nan))) and math.isfinite(float(right.get("beta_retail_tail", math.nan)))
                else math.nan
            ),
        }
        for metric in TAIL_METRICS:
            left_value = float(left.get(metric, math.nan))
            right_value = float(right.get(metric, math.nan))
            row[f"{metric}_{left_mode}"] = left_value
            row[f"{metric}_{right_mode}"] = right_value
            row[f"{metric}_delta"] = right_value - left_value if math.isfinite(left_value) and math.isfinite(right_value) else math.nan
        beta_mix_left = float(left.get("beta_mix_tail", math.nan))
        beta_mix_right = float(right.get("beta_q_tail", math.nan)) + float(right.get("beta_retail_tail", math.nan))
        row["beta_mix_consistency_gap"] = (
            beta_mix_right - beta_mix_left if math.isfinite(beta_mix_left) and math.isfinite(beta_mix_right) else math.nan
        )
        comparison_rows.append(row)
    return comparison_rows


def summarize_mode_stability(history_rows: list[dict[str, object]], metrics: Iterable[str] | None = None) -> list[dict[str, object]]:
    metrics = list(metrics or TAIL_METRICS)
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in history_rows:
        stock_code = str(row.get("stock_code", "")).strip()
        mode = str(row.get("mode", "")).strip()
        grouped.setdefault((stock_code, mode), []).append(row)

    summaries: list[dict[str, object]] = []
    for (stock_code, mode), rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda item: str(item.get("transaction_date", "")))
        dates = [str(row.get("transaction_date", "")) for row in rows]
        summary: dict[str, object] = {
            "stock_code": stock_code,
            "mode": mode,
            "history_count": len(rows),
            "trade_dates": ",".join(dates),
        }
        stable_votes = 0
        unstable_votes = 0
        for metric in metrics:
            values = [
                float(row.get(metric, math.nan))
                for row in rows
                if math.isfinite(float(row.get(metric, math.nan)))
            ]
            label = _stability_label(values)
            if label == "stable":
                stable_votes += 1
            elif label == "unstable":
                unstable_votes += 1
            summary[f"{metric}_mean"] = _round6(mean(values)) if values else ""
            summary[f"{metric}_median"] = _round6(median(values)) if values else ""
            summary[f"{metric}_std"] = _round6(pstdev(values)) if len(values) >= 2 else ""
            summary[f"{metric}_cv"] = _round6(_safe_cv(values)) if len(values) >= 2 else ""
            summary[f"{metric}_stability"] = label
        summary["overall_stability"] = "stable" if stable_votes >= unstable_votes else "unstable"
        summaries.append(summary)
    return summaries


def analyze_trade_dates(
    trade_dates: list[str],
    input_root: str | Path,
    config: dict,
    stock_codes: list[str] | None = None,
    compare_modes: tuple[str, str] = ("baseline_4d", "diag_5d"),
) -> dict[str, list[dict[str, object]]]:
    normalized_symbols = {symbol.upper() for symbol in (stock_codes or [])}
    history_rows: list[dict[str, object]] = []
    compare_rows: list[dict[str, object]] = []

    for trade_date in trade_dates:
        input_dir = _resolve_trade_input_dir(input_root, trade_date)
        samples = _load_daily_samples(
            input_dir=input_dir,
            trade_date=trade_date,
            config=config,
            stock_universe=normalized_symbols or None,
        )
        if normalized_symbols:
            samples = [sample for sample in samples if sample.stock_code.upper() in normalized_symbols]

        for mode in compare_modes:
            mode_config = deepcopy(config)
            mode_config.setdefault("pid_decomposer", {})
            mode_config["pid_decomposer"]["mode"] = mode
            decomposer = PIDDecomposer(mode_config)
            for sample in samples:
                history_rows.append(_result_tail_row(decomposer.decompose_sample(sample)))
        compare_rows.extend(compare_pid_modes(samples, config, modes=compare_modes))

    stability_rows = summarize_mode_stability(history_rows)
    return {
        "history_rows": history_rows,
        "compare_rows": compare_rows,
        "stability_rows": stability_rows,
    }


def write_csv(rows: list[dict[str, object]], output_path: str | Path) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    headers: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in headers:
                headers.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            formatted = {
                key: _round6(value) if isinstance(value, float) else value
                for key, value in row.items()
            }
            writer.writerow(formatted)
    return str(path)

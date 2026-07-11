from __future__ import annotations

from pathlib import Path

from schemas import MarketPidSnapshot, PatternResult, PredictResult


def build_batch_summary(
    trade_date: str,
    sample_count: int,
    output_count: int,
    warnings: list[str],
) -> dict:
    return {
        "trade_date": trade_date,
        "sample_count": sample_count,
        "output_count": output_count,
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def build_performance_summary(
    *,
    profile_enabled: bool,
    total_seconds: float,
    sample_build_seconds: float,
    pattern_seconds: float,
    capital_seconds: float,
    market_seconds: float,
    export_seconds: float,
    sample_timings: list[dict[str, float | str]],
    processed_samples: int,
    imputed_predict_count: int,
    skipped_incomplete_samples: int,
    round_seconds,
) -> dict | None:
    if not profile_enabled:
        return None

    top_slowest_samples = sorted(
        sample_timings,
        key=lambda item: float(item["sample_build_seconds"]),
        reverse=True,
    )[:20]
    return {
        "total_seconds": round_seconds(total_seconds),
        "sample_build_seconds": round_seconds(sample_build_seconds),
        "pattern_seconds": round_seconds(pattern_seconds),
        "capital_seconds": round_seconds(capital_seconds),
        "market_seconds": round_seconds(market_seconds),
        "export_seconds": round_seconds(export_seconds),
        "processed_samples": processed_samples,
        "imputed_missing_symbols": imputed_predict_count,
        "skipped_incomplete_samples": skipped_incomplete_samples,
        "top_slowest_samples": top_slowest_samples,
    }


def build_batch_result(
    *,
    trade_date: str,
    sample_count: int,
    pattern_results: list[PatternResult],
    predict_results: list[PredictResult],
    market_snapshot: MarketPidSnapshot | None,
    market_snapshot_path: Path | None,
    market_report_path: Path | None,
    market_validation_report_path: str,
    replay_validation_report_path: str,
    diagnostics_json_path: str,
    distribution_csv_path: str,
    submit_zip: str | None,
    warnings: list[str],
    imputed_output_count: int,
    stock_offset: int,
    stock_limit: int | None,
    stock_list_file: str | Path | None,
    stock_universe_size: int | None,
    missing_symbols: list[str],
    incomplete_stock_dirs: dict[str, list[str]],
    performance_summary: dict | None,
) -> dict:
    return {
        "trade_date": trade_date,
        "pattern_results": pattern_results,
        "predict_results": predict_results,
        "market_pid_snapshot": market_snapshot,
        "market_snapshot_path": str(market_snapshot_path) if market_snapshot_path else None,
        "market_report_path": str(market_report_path) if market_report_path else None,
        "market_validation_report_path": market_validation_report_path,
        "replay_validation_report_path": replay_validation_report_path,
        "diagnostics_json_path": diagnostics_json_path,
        "distribution_csv_path": distribution_csv_path,
        "submit_zip": submit_zip,
        "warnings": warnings,
        "sample_count": sample_count,
        "imputed_output_count": imputed_output_count,
        "output_count": len(pattern_results),
        "stock_offset": stock_offset,
        "stock_limit": stock_limit,
        "stock_list_file": str(stock_list_file) if stock_list_file else None,
        "stock_universe_size": stock_universe_size,
        "missing_symbols": missing_symbols,
        "incomplete_stock_dirs": incomplete_stock_dirs,
        "performance_summary": performance_summary,
    }

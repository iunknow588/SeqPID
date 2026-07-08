from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import load_label_dict, load_runtime_config
from exporter import build_submit_zip
from schema_probe import probe_input_schema, render_schema_probe_report
from scheduler import run_daily_batch

EXTERNAL_ROOT = Path(r"C:\level-2-ana")
DEFAULT_INPUT_DIR = EXTERNAL_ROOT / "data"
DEFAULT_OUTPUT_DIR = EXTERNAL_ROOT / "output"
DEFAULT_REPORT_DIR = DEFAULT_OUTPUT_DIR / "reports" / "diagnostics"
LogFn = Callable[[str], None]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Competition system entrypoint")
    parser.add_argument("--mode", choices=["probe", "batch"], default="probe")
    parser.add_argument("--date", required=True, help="Trade date, e.g. 20260710")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--config", default="./configs/dev.yaml")
    parser.add_argument("--label-config", default="./configs/label_dict.yaml")
    parser.add_argument("--stock-limit", type=int, default=0, help="Limit stock dirs for raw per-stock layout")
    parser.add_argument("--stock-offset", type=int, default=0, help="Skip N stock dirs before processing")
    parser.add_argument("--stock-list-file", default="", help="CSV file containing stock codes to process")
    parser.add_argument("--build-zip", action="store_true")
    parser.add_argument("--profile", action="store_true", help="Write performance profile report for batch mode")
    parser.add_argument("--submit-date", default="", help="Override transaction_date written into submission CSVs")
    return parser.parse_args()


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def _looks_like_supported_input_dir(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False

    for name in ("reference_features.csv", "features.csv"):
        if (path / name).exists():
            return True

    csv_files = list(path.glob("*.csv"))
    if len(csv_files) >= 3:
        return True

    for child in path.iterdir():
        if child.is_dir() and len(list(child.glob("*.csv"))) >= 3:
            return True
    return False


def _resolve_input_dir(path_str: str, trade_date: str) -> Path:
    base_path = _resolve_path(path_str)
    if _looks_like_supported_input_dir(base_path):
        return base_path

    candidates = [
        base_path / trade_date / trade_date,
        base_path / trade_date,
    ]
    for candidate in candidates:
        if _looks_like_supported_input_dir(candidate):
            return candidate
    return base_path


def _resolve_stock_list_file(
    stock_list_file: str | Path | None,
    resolved_input_dir: Path,
) -> Path | None:
    if stock_list_file:
        return _resolve_path(str(stock_list_file))

    candidates = [
        resolved_input_dir / "百只股票样本.csv",
        resolved_input_dir.parent / "百只股票样本.csv",
        EXTERNAL_ROOT / "data" / "百只股票样本.csv",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _infer_trade_date_from_path(path_str: str | Path) -> str:
    path = Path(path_str)
    for part in reversed(path.parts):
        if len(part) == 8 and part.isdigit():
            return part
    raise ValueError(f"Unable to infer trade date from path: {path}")


def _build_timestamped_output_dir(base_dir: Path, trade_date: str) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = base_dir / f"{trade_date}_{timestamp}"
    suffix = 1
    while candidate.exists():
        candidate = base_dir / f"{trade_date}_{timestamp}_{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _default_logger(message: str) -> None:
    print(message)


def _write_performance_report(output_dir: str | Path, performance_summary: dict) -> Path:
    report_path = Path(output_dir) / "performance_profile.json"
    report_path.write_text(json.dumps(performance_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def _log_performance_summary(log: LogFn, performance_summary: dict, report_path: Path) -> None:
    log(f"performance_profile: {report_path}")
    log(f"performance_total_seconds: {performance_summary['total_seconds']}")
    log(f"performance_sample_build_seconds: {performance_summary['sample_build_seconds']}")
    slowest = performance_summary.get("top_slowest_samples", [])
    if slowest:
        top = slowest[0]
        log(
            "slowest_sample: "
            f"{top['stock_code']} ({top['sample_build_seconds']}s)"
        )


def run_probe_job(
    trade_date: str,
    input_dir: str | Path,
    report_dir: str | Path,
    logger: LogFn | None = None,
) -> Path:
    log = logger or _default_logger
    resolved_input_dir = _resolve_input_dir(str(input_dir), trade_date)
    result = probe_input_schema(resolved_input_dir, trade_date)
    report = render_schema_probe_report(result)
    resolved_report_dir = _resolve_path(str(report_dir))
    resolved_report_dir.mkdir(parents=True, exist_ok=True)
    report_path = resolved_report_dir / "schema_probe_report.md"
    report_path.write_text(report, encoding="utf-8")
    log(f"Schema probe report written to: {report_path}")
    return report_path


def run_probe(args: argparse.Namespace) -> int:
    run_probe_job(args.date, args.input_dir, args.report_dir)
    return 0


def run_batch_job(
    trade_date: str,
    input_dir: str | Path,
    output_dir: str | Path,
    config_path: str | Path = "./configs/dev.yaml",
    label_config_path: str | Path = "./configs/label_dict.yaml",
    stock_limit: int | None = None,
    stock_offset: int = 0,
    stock_list_file: str | Path | None = None,
    build_zip: bool = False,
    profile_enabled: bool = False,
    submit_date: str | None = None,
    logger: LogFn | None = None,
) -> dict:
    log = logger or _default_logger
    config = load_runtime_config(ROOT / config_path)
    label_dict = load_label_dict(ROOT / label_config_path)
    resolved_input_dir = _resolve_input_dir(str(input_dir), trade_date)
    resolved_stock_list_file = _resolve_stock_list_file(stock_list_file, resolved_input_dir)
    output_base_dir = _resolve_path(str(output_dir))
    resolved_output_dir = _build_timestamped_output_dir(output_base_dir, trade_date)
    result = run_daily_batch(
        trade_date=trade_date,
        input_dir=resolved_input_dir,
        output_dir=resolved_output_dir,
        config=config,
        label_dict=label_dict,
        stock_limit=stock_limit if stock_limit and stock_limit > 0 else None,
        stock_offset=max(stock_offset, 0),
        stock_list_file=resolved_stock_list_file,
        enable_submit_zip=config.get("enable_submit_zip", False) or build_zip,
        profile_enabled=profile_enabled,
        submit_date_override=submit_date or None,
    )
    log(f"Batch finished for {trade_date}")
    log(f"Input directory: {resolved_input_dir}")
    log(f"Output directory: {resolved_output_dir}")
    log(f"Samples: {result['sample_count']}")
    if stock_offset or stock_limit:
        log(f"Slice: offset={result['stock_offset']}, limit={result['stock_limit']}")
    if result.get("stock_list_file"):
        log(f"Stock list: {result['stock_list_file']} ({result['stock_universe_size']} symbols)")
    log(f"Warnings: {result['warnings']}")
    if result.get("market_snapshot_path"):
        log(f"market_pid_snapshot: {result['market_snapshot_path']}")
    if result.get("market_report_path"):
        log(f"market_regime_report: {result['market_report_path']}")
    if result.get("diagnostics_json_path"):
        log(f"batch_diagnostics: {result['diagnostics_json_path']}")
    if result.get("distribution_csv_path"):
        log(f"label_distribution: {result['distribution_csv_path']}")
    if result["submit_zip"]:
        log(f"submit.zip: {result['submit_zip']}")
    if result.get("performance_summary"):
        profile_report_path = _write_performance_report(resolved_output_dir, result["performance_summary"])
        result["performance_report_path"] = str(profile_report_path)
        _log_performance_summary(log, result["performance_summary"], profile_report_path)
    result["output_dir"] = str(resolved_output_dir)
    result["resolved_input_dir"] = str(resolved_input_dir)
    return result


def run_batch(args: argparse.Namespace) -> int:
    run_batch_job(
        trade_date=args.date,
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        config_path=args.config,
        label_config_path=args.label_config,
        stock_limit=args.stock_limit if args.stock_limit > 0 else None,
        stock_offset=args.stock_offset,
        stock_list_file=args.stock_list_file or None,
        build_zip=args.build_zip,
        profile_enabled=args.profile,
        submit_date=args.submit_date or None,
    )
    return 0


def run_full_analysis(
    input_dir: str | Path,
    output_dir: str | Path,
    report_dir: str | Path | None = None,
    build_zip: bool = True,
    profile_enabled: bool = False,
    logger: LogFn | None = None,
) -> dict:
    trade_date = _infer_trade_date_from_path(input_dir)
    resolved_report_dir = report_dir or (Path(output_dir) / "reports" / "diagnostics")
    report_path = run_probe_job(trade_date, input_dir, resolved_report_dir, logger=logger)
    batch_result = run_batch_job(
        trade_date=trade_date,
        input_dir=input_dir,
        output_dir=output_dir,
        build_zip=build_zip,
        profile_enabled=profile_enabled,
        logger=logger,
    )
    batch_result["report_path"] = str(report_path)
    batch_result["trade_date"] = trade_date
    return batch_result


def main() -> int:
    args = parse_args()
    if args.mode == "probe":
        return run_probe(args)
    return run_batch(args)


if __name__ == "__main__":
    raise SystemExit(main())

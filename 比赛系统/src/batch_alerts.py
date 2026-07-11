from __future__ import annotations

from schemas import DailySample


def format_incomplete_stock_warning(incomplete_stock_dirs: dict[str, list[str]]) -> str:
    details = [
        f"{symbol}({','.join(missing_files)})"
        for symbol, missing_files in sorted(incomplete_stock_dirs.items())
    ]
    return "Skipped incomplete stock dirs: " + "; ".join(details)


def collect_missing_symbols(
    requested_symbols: list[str] | None,
    samples: list[DailySample],
) -> list[str]:
    if not requested_symbols:
        return []
    actual_symbols = {sample.stock_code.upper() for sample in samples}
    return [symbol for symbol in requested_symbols if symbol not in actual_symbols]


def build_batch_warnings(
    samples: list[DailySample],
    missing_symbols: list[str],
    incomplete_stock_dirs: dict[str, list[str]],
    imputed_symbols: list[str] | None = None,
) -> list[str]:
    warnings: list[str] = []
    if not samples:
        warnings.append("No reference feature rows found for the requested date; emitted header-only files.")
    if missing_symbols:
        warnings.append("Missing raw data for requested symbols: " + ", ".join(missing_symbols))
    if incomplete_stock_dirs:
        warnings.append(format_incomplete_stock_warning(incomplete_stock_dirs))
    if imputed_symbols:
        warnings.append("Imputed missing symbols with market-average defaults: " + ", ".join(imputed_symbols))
    return warnings

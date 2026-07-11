from __future__ import annotations

import csv
import sys
from pathlib import Path
from statistics import median


csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

REQUIRED_STOCK_FILES = {
    "trades": "逐笔成交.csv",
    "orders": "逐笔委托.csv",
    "snapshots": "行情.csv",
}

REFERENCE_FEATURE_FILENAMES = (
    "reference_features.csv",
    "features.csv",
    "参考特征.csv",
)


def iter_stock_dirs(input_dir: Path) -> list[Path]:
    return sorted([item for item in input_dir.iterdir() if item.is_dir()])


def looks_like_stock_symbol(value: str) -> bool:
    normalized = value.strip().upper()
    if not normalized:
        return False
    if normalized.endswith((".SZ", ".SH", ".BJ")):
        head = normalized.split(".", 1)[0]
        return head.isdigit()
    return normalized.isdigit()


def load_stock_universe(stock_list_file: str | Path | None) -> tuple[list[str] | None, set[str] | None]:
    if stock_list_file is None:
        return None, None
    path = Path(stock_list_file)
    if not path.exists():
        raise FileNotFoundError(f"Stock list file not found: {path}")

    ordered_symbols: list[str] = []
    symbols: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        for row_index, row in enumerate(reader):
            if not row:
                continue
            symbol = str(row[0]).strip()
            if not symbol:
                continue
            if row_index == 0 and not looks_like_stock_symbol(symbol):
                continue
            normalized = symbol.upper()
            if normalized not in symbols:
                ordered_symbols.append(normalized)
                symbols.add(normalized)
    return ordered_symbols, symbols


def slice_stock_dirs(stock_dirs: list[Path], stock_offset: int = 0, stock_limit: int | None = None) -> list[Path]:
    start = max(stock_offset, 0)
    if stock_limit is not None and stock_limit > 0:
        return stock_dirs[start : start + stock_limit]
    return stock_dirs[start:]


def sort_by_requested_order(items: list, requested_symbols: list[str] | None, key_name: str) -> list:
    if not requested_symbols:
        return items
    order_map = {symbol: index for index, symbol in enumerate(requested_symbols)}
    return sorted(
        items,
        key=lambda item: (
            order_map.get(str(getattr(item, key_name)).upper(), len(order_map)),
            str(getattr(item, key_name)).upper(),
        ),
    )


def build_market_average_summary(samples: list[object]) -> dict[str, float]:
    numeric_values: dict[str, list[float]] = {}
    for sample in samples:
        feature_summary = getattr(sample, "feature_summary", {}) or {}
        for key, value in feature_summary.items():
            if isinstance(value, (int, float)):
                numeric_values.setdefault(key, []).append(float(value))

    summary: dict[str, float] = {}
    for key, values in numeric_values.items():
        if values:
            summary[key] = float(median(values))

    summary.setdefault("order_buy_ratio", 0.5)
    summary.setdefault("bid_support", 0.5)
    summary.setdefault("ask_pressure", 0.5)
    summary.setdefault("window_count", 1.0)
    return summary


def is_stock_dir(input_dir: Path) -> bool:
    files = {item.name for item in input_dir.iterdir() if item.is_file()}
    return set(REQUIRED_STOCK_FILES.values()).issubset(files)


def find_reference_feature_file(input_dir: Path) -> Path | None:
    for name in REFERENCE_FEATURE_FILENAMES:
        candidate = input_dir / name
        if candidate.exists():
            return candidate
    return None


def filter_stock_dirs(stock_dirs: list[Path], stock_universe: set[str] | None) -> list[Path]:
    if not stock_universe:
        return stock_dirs
    return [stock_dir for stock_dir in stock_dirs if stock_dir.name.upper() in stock_universe]


def get_missing_required_files(stock_dir: Path) -> list[str]:
    missing: list[str] = []
    for logical_name, filename in REQUIRED_STOCK_FILES.items():
        if not (stock_dir / filename).exists():
            missing.append(logical_name)
    return missing


def open_csv_reader(path: Path) -> tuple[csv.DictReader, object]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            fh = path.open("r", encoding=encoding, newline="")
            return csv.DictReader(fh), fh
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Unable to open csv file: {path}")


def read_csv_rows(path: Path, trade_date: str) -> list[dict]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            with path.open("r", encoding=encoding, newline="") as fh:
                reader = csv.DictReader(fh)
                rows: list[dict] = []
                for row in reader:
                    row_date = str(row.get("自然日") or row.get("date") or row.get("trade_date") or "")
                    if row_date and row_date != trade_date:
                        continue
                    rows.append(row)
                return rows
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return []

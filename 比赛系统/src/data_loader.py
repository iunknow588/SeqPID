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

STOCK_BASICS_FILENAMES = (
    "stock_basics.csv",
    "stock_basic.csv",
    "symbol_meta.csv",
    "股票基础信息.csv",
)

CSV_QUALITY_HEADER_KEYS = {
    "自然日",
    "date",
    "trade_date",
    "时间",
    "time",
    "成交价格",
    "price",
}


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
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            with path.open("r", encoding=encoding, newline="") as fh:
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
        except UnicodeDecodeError as exc:
            ordered_symbols.clear()
            symbols.clear()
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
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


def find_stock_basics_file(input_dir: Path, config: dict | None = None) -> Path | None:
    cfg = config or {}
    configured = str(cfg.get("stock_basics_file", "") or "").strip()
    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return candidate if candidate.exists() else None
    for base in (input_dir, input_dir.parent):
        for name in STOCK_BASICS_FILENAMES:
            candidate = base / name
            if candidate.exists():
                return candidate
    return None


def load_stock_mv_metadata(path: Path | None) -> dict[str, dict[str, float]]:
    if path is None or not path.exists():
        return {}
    rows: dict[str, dict[str, float]] = {}
    reader, fh = open_csv_reader(path)
    try:
        for row in reader:
            symbol = str(
                row.get("symbol")
                or row.get("stock_code")
                or row.get("股票代码")
                or row.get("万得代码")
                or ""
            ).strip().upper()
            if not symbol:
                continue
            float_shares = _row_float(
                row,
                [
                    "float_shares",
                    "circulating_shares",
                    "free_float_shares",
                    "float_a_shares",
                    "流通股",
                    "流通股本",
                    "流通A股",
                    "自由流通股本",
                ],
            )
            if float_shares <= 0:
                continue
            rows[symbol] = {"float_shares": float_shares}
    finally:
        fh.close()
    return rows


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


def _row_float(row: dict[str, str], keys: list[str]) -> float:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def read_csv_rows_with_quality(path: Path, trade_date: str) -> tuple[list[dict], dict]:
    report = {
        "file_path": str(path),
        "file_exists": path.exists(),
        "file_size": 0,
        "null_byte_ratio": 0.0,
        "encoding_used": "",
        "header_valid": False,
        "raw_row_count": 0,
        "effective_row_count": 0,
        "quality_status": "missing",
        "reason_code": "missing_raw_file",
        "action": "impute",
    }
    if not path.exists():
        return [], report

    data = path.read_bytes()
    file_size = len(data)
    report["file_size"] = file_size
    if file_size == 0:
        report["quality_status"] = "empty"
        report["reason_code"] = "empty_raw_file"
        return [], report

    null_byte_count = data.count(b"\x00")
    report["null_byte_ratio"] = null_byte_count / file_size if file_size > 0 else 0.0
    if null_byte_count == file_size:
        report["quality_status"] = "null_filled"
        report["reason_code"] = "null_filled_raw_file"
        return [], report

    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            text = data.decode(encoding)
            reader = csv.DictReader(text.splitlines())
            fieldnames = [str(name or "").strip() for name in (reader.fieldnames or [])]
            header_valid = any(name in CSV_QUALITY_HEADER_KEYS for name in fieldnames) or any(fieldnames)
            report["encoding_used"] = encoding
            report["header_valid"] = header_valid
            if not header_valid:
                report["quality_status"] = "invalid_schema"
                report["reason_code"] = "invalid_raw_schema"
                return [], report

            rows: list[dict] = []
            raw_row_count = 0
            for row in reader:
                raw_row_count += 1
                row_date = str(row.get("自然日") or row.get("date") or row.get("trade_date") or "")
                if row_date and row_date != trade_date:
                    continue
                rows.append(row)
            report["raw_row_count"] = raw_row_count
            report["effective_row_count"] = len(rows)
            if not rows:
                report["quality_status"] = "no_effective_rows"
                report["reason_code"] = "no_effective_rows"
                return [], report

            report["quality_status"] = "ok"
            report["reason_code"] = "ok"
            report["action"] = "use_raw"
            return rows, report
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        report["quality_status"] = "invalid_schema"
        report["reason_code"] = "invalid_raw_schema"
        return [], report
    return [], report


def read_csv_rows(path: Path, trade_date: str) -> list[dict]:
    rows, _report = read_csv_rows_with_quality(path, trade_date)
    return rows

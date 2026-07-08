from __future__ import annotations

import csv
from pathlib import Path

from schemas import SchemaProbeFileResult, SchemaProbeResult


EXPECTED_FILES = {
    "trades": {
        "candidates": ["trades.csv", "trades.parquet", "逐笔成交.csv"],
        "required_fields": ["symbol", "timestamp_ms", "price", "volume", "amount"],
    },
    "orders": {
        "candidates": ["orders.csv", "orders.parquet", "逐笔委托.csv"],
        "required_fields": ["symbol", "timestamp_ms", "side", "price", "volume"],
    },
    "cancels": {
        "candidates": ["cancels.csv", "cancels.parquet", "逐笔撤单.csv"],
        "required_fields": ["symbol", "timestamp_ms", "side", "price", "volume"],
    },
    "snapshots": {
        "candidates": ["snapshots.csv", "snapshots.parquet", "十档盘口快照.csv", "行情.csv"],
        "required_fields": ["symbol", "timestamp_ms", "bid_px_1", "ask_px_1"],
    },
    "reference_features": {
        "candidates": ["reference_features.csv", "features.csv", "参考特征.csv"],
        "required_fields": ["date", "symbol", "window_start", "window_end"],
    },
}

FIELD_MAPPING_HINTS = {
    "trades": {
        "万得代码": "symbol",
        "自然日": "trade_date",
        "时间": "timestamp_ms",
        "成交价格": "price",
        "成交数量": "volume",
        "BS标志": "side",
    },
    "orders": {
        "万得代码": "symbol",
        "自然日": "trade_date",
        "时间": "timestamp_ms",
        "委托代码": "side",
        "委托价格": "price",
        "委托数量": "volume",
        "交易所委托号": "order_id",
    },
    "snapshots": {
        "万得代码": "symbol",
        "自然日": "trade_date",
        "时间": "timestamp_ms",
        "申买价1": "bid_px_1",
        "申卖价1": "ask_px_1",
        "申买量1": "bid_vol_1",
        "申卖量1": "ask_vol_1",
        "上涨品种数": "market_up_count",
        "下跌品种数": "market_down_count",
        "持平品种数": "market_flat_count",
    },
}


def _find_candidate_file(input_dir: Path, candidates: list[str]) -> Path | None:
    for name in candidates:
        path = input_dir / name
        if path.exists():
            return path
    return None


def _read_csv_header(path: Path) -> tuple[list[str], int | None]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            with path.open("r", encoding=encoding, newline="") as fh:
                reader = csv.reader(fh)
                header = next(reader, [])
                count = 0
                for _ in reader:
                    count += 1
                    if count >= 1000:
                        break
            return header, count
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return [], None


def _iter_stock_dirs(base: Path) -> list[Path]:
    return sorted([item for item in base.iterdir() if item.is_dir()])


def _find_stock_dir_file(base: Path, candidates: list[str]) -> tuple[Path | None, str | None]:
    for stock_dir in _iter_stock_dirs(base):
        for name in candidates:
            path = stock_dir / name
            if path.exists():
                return path, stock_dir.name
    return None, None


def probe_input_schema(input_dir: str | Path, trade_date: str) -> SchemaProbeResult:
    base = Path(input_dir)
    if not base.exists():
        raise FileNotFoundError(f"Input directory not found: {base}")

    files: dict[str, SchemaProbeFileResult] = {}
    summary = {
        "missing_file_keys": [],
        "order_lifetime_ms_detected": False,
        "reference_feature_file_detected": False,
        "layout": "flat_files",
        "sample_stock_dir": "",
        "field_mapping_hints": {},
    }

    stock_dirs = _iter_stock_dirs(base)
    if stock_dirs:
        summary["layout"] = "per_stock_dirs"

    for key, spec in EXPECTED_FILES.items():
        path = _find_candidate_file(base, spec["candidates"])
        sample_stock_dir = None
        if path is None and key != "reference_features":
            path, sample_stock_dir = _find_stock_dir_file(base, spec["candidates"])
            if sample_stock_dir:
                summary["sample_stock_dir"] = sample_stock_dir
        if path is None:
            files[key] = SchemaProbeFileResult(
                path=str(base / spec["candidates"][0]),
                exists=False,
                suffix="",
                size_bytes=0,
                missing_required_fields=list(spec["required_fields"]),
            )
            summary["missing_file_keys"].append(key)
            continue

        header: list[str] = []
        row_count_estimate: int | None = None
        if path.suffix.lower() == ".csv":
            header, row_count_estimate = _read_csv_header(path)

        required_present = [field for field in spec["required_fields"] if field in header]
        required_missing = [field for field in spec["required_fields"] if field not in header]

        if "order_lifetime_ms" in header:
            summary["order_lifetime_ms_detected"] = True
        if key == "reference_features":
            summary["reference_feature_file_detected"] = True
        if key == "trades" and "万得代码" in header:
            summary["encoding_hint"] = "gb18030"
        mapping_hints = FIELD_MAPPING_HINTS.get(key, {})
        matched_mapping = {src: dst for src, dst in mapping_hints.items() if src in header}
        if matched_mapping:
            summary["field_mapping_hints"][key] = matched_mapping

        files[key] = SchemaProbeFileResult(
            path=str(path),
            exists=True,
            suffix=path.suffix.lower(),
            size_bytes=path.stat().st_size,
            sample_header=header,
            row_count_estimate=row_count_estimate,
            required_fields_present=required_present,
            missing_required_fields=required_missing,
        )

    return SchemaProbeResult(
        trade_date=trade_date,
        input_dir=str(base),
        files=files,
        summary=summary,
    )


def render_schema_probe_report(result: SchemaProbeResult) -> str:
    lines: list[str] = []
    lines.append("# Schema Probe Report")
    lines.append("")
    lines.append(f"- trade_date: `{result.trade_date}`")
    lines.append(f"- input_dir: `{result.input_dir}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- missing_file_keys: `{', '.join(result.summary['missing_file_keys']) or 'none'}`")
    lines.append(f"- order_lifetime_ms_detected: `{result.summary['order_lifetime_ms_detected']}`")
    lines.append(f"- reference_feature_file_detected: `{result.summary['reference_feature_file_detected']}`")
    if result.summary.get("layout"):
        lines.append(f"- layout: `{result.summary['layout']}`")
    if result.summary.get("sample_stock_dir"):
        lines.append(f"- sample_stock_dir: `{result.summary['sample_stock_dir']}`")
    if result.summary.get("encoding_hint"):
        lines.append(f"- encoding_hint: `{result.summary['encoding_hint']}`")
    lines.append("")
    if result.summary.get("field_mapping_hints"):
        lines.append("## Field Mapping Hints")
        lines.append("")
        for key, mapping in result.summary["field_mapping_hints"].items():
            lines.append(f"### {key}")
            lines.append("")
            for src, dst in mapping.items():
                lines.append(f"- `{src}` -> `{dst}`")
            lines.append("")
    lines.append("## File Details")
    lines.append("")
    for key, item in result.files.items():
        lines.append(f"### {key}")
        lines.append("")
        lines.append(f"- path: `{item.path}`")
        lines.append(f"- exists: `{item.exists}`")
        lines.append(f"- suffix: `{item.suffix}`")
        lines.append(f"- size_bytes: `{item.size_bytes}`")
        if item.sample_header:
            lines.append(f"- sample_header: `{', '.join(item.sample_header[:20])}`")
        if item.row_count_estimate is not None:
            lines.append(f"- row_count_estimate(first1000): `{item.row_count_estimate}`")
        lines.append(f"- required_fields_present: `{', '.join(item.required_fields_present) or 'none'}`")
        lines.append(f"- missing_required_fields: `{', '.join(item.missing_required_fields) or 'none'}`")
        lines.append("")
    return "\n".join(lines).strip() + "\n"

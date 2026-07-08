from __future__ import annotations

import csv
import json
import zipfile
from collections import Counter
from pathlib import Path

from schemas import MarketPidSnapshot, PatternResult, PredictResult


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


def _submission_date(default_date: str, submit_date_override: str | None = None) -> str:
    if submit_date_override is None:
        return default_date
    override = str(submit_date_override).strip()
    return override or default_date


def _submission_stock_code(stock_code: str) -> str:
    return str(stock_code).strip()


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

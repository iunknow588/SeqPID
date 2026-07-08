from __future__ import annotations

import csv
from bisect import bisect_right
from pathlib import Path
from statistics import median
from time import perf_counter

from capital_model import predict_capitals
from exporter import (
    build_submit_zip,
    export_batch_diagnostics,
    export_market_pid_snapshot,
    export_market_regime_report,
    export_pattern_reco,
    export_predict_result,
)
from market_pid import attach_market_relative_metrics, estimate_market_pid
from pattern_model import predict_pattern
from pid_decomposer import PIDDecomposer
from schemas import DailySample, MarketPidSnapshot, PatternResult, PredictResult


def _iter_stock_dirs(input_dir: Path) -> list[Path]:
    return sorted([item for item in input_dir.iterdir() if item.is_dir()])


def _load_stock_universe(stock_list_file: str | Path | None) -> tuple[list[str] | None, set[str] | None]:
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
            if row_index == 0 and not _looks_like_stock_symbol(symbol):
                continue
            normalized = symbol.upper()
            if normalized not in symbols:
                ordered_symbols.append(normalized)
                symbols.add(normalized)
    return ordered_symbols, symbols


def _looks_like_stock_symbol(value: str) -> bool:
    normalized = value.strip().upper()
    if not normalized:
        return False
    if normalized.endswith((".SZ", ".SH", ".BJ")):
        head = normalized.split(".", 1)[0]
        return head.isdigit()
    return normalized.isdigit()


def _is_stock_dir(input_dir: Path) -> bool:
    required = {"逐笔成交.csv", "逐笔委托.csv", "行情.csv"}
    files = {item.name for item in input_dir.iterdir() if item.is_file()}
    return required.issubset(files)


def _find_reference_feature_file(input_dir: Path) -> Path | None:
    candidates = [
        input_dir / "reference_features.csv",
        input_dir / "features.csv",
        input_dir / "参考特征.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _filter_stock_dirs(stock_dirs: list[Path], stock_universe: set[str] | None) -> list[Path]:
    if not stock_universe:
        return stock_dirs
    return [stock_dir for stock_dir in stock_dirs if stock_dir.name.upper() in stock_universe]


def _get_missing_required_files(stock_dir: Path) -> list[str]:
    missing: list[str] = []
    if not (stock_dir / "逐笔成交.csv").exists():
        missing.append("trades")
    if not (stock_dir / "逐笔委托.csv").exists():
        missing.append("orders")
    if not (stock_dir / "行情.csv").exists():
        missing.append("snapshots")
    return missing


def _format_incomplete_stock_warning(incomplete_stock_dirs: dict[str, list[str]]) -> str:
    details = [
        f"{symbol}({','.join(missing_files)})"
        for symbol, missing_files in sorted(incomplete_stock_dirs.items())
    ]
    return "Skipped incomplete stock dirs: " + "; ".join(details)


def _round_seconds(value: float) -> float:
    return round(value, 6)


def _open_csv_reader(path: Path) -> csv.DictReader:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            fh = path.open("r", encoding=encoding, newline="")
            return csv.DictReader(fh)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Unable to open csv file: {path}")


def _to_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pick(row: dict, names: list[str], default: float = 0.0) -> float:
    for name in names:
        if name in row:
            return _to_float(row.get(name), default)
    return default


def _pick_text(row: dict, names: list[str], default: str = "") -> str:
    for name in names:
        if name in row and row.get(name) not in (None, ""):
            return str(row.get(name)).strip()
    return default


def _time_to_window_id(raw_time: object) -> int | None:
    value = int(_to_float(raw_time, 0.0))
    if value <= 0:
        return None
    hhmmss = value // 1000 if value > 235959 else value
    hh = hhmmss // 10000
    mm = (hhmmss % 10000) // 100
    total_minutes = hh * 60 + mm
    morning_start = 9 * 60 + 30
    morning_end = 11 * 60 + 30
    afternoon_start = 13 * 60
    afternoon_end = 15 * 60
    if morning_start <= total_minutes < morning_end:
        return min((total_minutes - morning_start) // 5, 23)
    if afternoon_start <= total_minutes < afternoon_end:
        return min(24 + (total_minutes - afternoon_start) // 5, 47)
    if total_minutes >= afternoon_end:
        return 47
    return None


def _trade_side_sign(row: dict) -> int:
    raw = _pick_text(row, ["BS标志", "side", "买卖方向", "成交方向", "委托代码"]).upper()
    if raw in {"B", "BUY", "买", "主动买", "1"}:
        return 1
    if raw in {"S", "SELL", "卖", "主动卖", "2"}:
        return -1
    return 0


def _row_time_value(row: dict) -> int:
    return int(_to_float(row.get("时间") or row.get("timestamp_ms") or row.get("time"), 0.0))


def _build_quote_series(quote_rows: list[dict]) -> tuple[list[int], list[dict]]:
    series: list[tuple[int, dict]] = []
    for row in quote_rows:
        timestamp = _row_time_value(row)
        if timestamp <= 0:
            continue
        bid_px_1 = _scaled_price(row.get("申买价1") or row.get("bid_px_1") or row.get("bid1"))
        ask_px_1 = _scaled_price(row.get("申卖价1") or row.get("ask_px_1") or row.get("ask1"))
        if bid_px_1 <= 0 and ask_px_1 <= 0:
            continue
        series.append((timestamp, {"bid_px_1": bid_px_1, "ask_px_1": ask_px_1}))
    series.sort(key=lambda item: item[0])
    return [item[0] for item in series], [item[1] for item in series]


def _lookup_quote_at_or_before(timestamp: int, quote_times: list[int], quote_values: list[dict]) -> dict:
    if not quote_times:
        return {}
    index = bisect_right(quote_times, timestamp) - 1
    if index < 0:
        return quote_values[0]
    return quote_values[index]


def _active_side_sign(row: dict, price: float, quote: dict, fallback_to_side: bool = True) -> int:
    bid_px_1 = float(quote.get("bid_px_1", 0.0) or 0.0)
    ask_px_1 = float(quote.get("ask_px_1", 0.0) or 0.0)
    has_quote = bid_px_1 > 0 or ask_px_1 > 0
    if price > 0 and ask_px_1 > 0 and price >= ask_px_1:
        return 1
    if price > 0 and bid_px_1 > 0 and price <= bid_px_1:
        return -1
    if has_quote:
        return 0
    if fallback_to_side:
        return _trade_side_sign(row)
    return 0


def _build_pid_rows_from_trades(trade_rows: list[dict], config: dict, quote_rows: list[dict] | None = None) -> list[dict]:
    species_rules = config.get("species_rules", {})
    large_threshold = float(species_rules.get("large_order_amount_threshold", 500_000.0))
    active_fallback_to_side = bool(species_rules.get("active_fallback_to_side", True))
    quote_times, quote_values = _build_quote_series(quote_rows or [])
    buckets = [
        {
            "window_id": str(index),
            "deal_amount": 0.0,
            "signal_deal_buy_amount": 0.0,
            "signal_deal_sell_amount": 0.0,
            "signed_large_active_amount": 0.0,
            "signed_mix_qr_amount": 0.0,
            "large_active_buy_amount": 0.0,
            "large_active_sell_amount": 0.0,
            "small_passive_buy_amount": 0.0,
            "small_passive_sell_amount": 0.0,
            "unknown_side_amount": 0.0,
            "window_open_price": 0.0,
            "window_close_price": 0.0,
            "window_trade_count": 0,
            "active_inferred_count": 0,
            "side_fallback_count": 0,
        }
        for index in range(48)
    ]

    for row in trade_rows:
        timestamp = _row_time_value(row)
        window_id = _time_to_window_id(timestamp)
        if window_id is None:
            continue
        price = _scaled_price(row.get("成交价格") or row.get("price"))
        volume = _to_float(row.get("成交数量") or row.get("volume"), 0.0)
        explicit_amount = _to_float(row.get("成交金额") or row.get("amount"), 0.0)
        amount = explicit_amount if explicit_amount > 0 else price * volume
        if amount <= 0:
            continue

        side_sign = _trade_side_sign(row)
        bucket = buckets[window_id]
        bucket["deal_amount"] += amount
        bucket["window_trade_count"] += 1
        if bucket["window_open_price"] <= 0 and price > 0:
            bucket["window_open_price"] = price
        if price > 0:
            bucket["window_close_price"] = price

        quote = _lookup_quote_at_or_before(timestamp, quote_times, quote_values)
        active_sign = _active_side_sign(row, price, quote, fallback_to_side=active_fallback_to_side)
        if active_sign != 0 and quote:
            bucket["active_inferred_count"] += 1
        elif active_sign != 0:
            bucket["side_fallback_count"] += 1

        signed_amount = side_sign * amount
        if side_sign > 0:
            bucket["signal_deal_buy_amount"] += amount
        elif side_sign < 0:
            bucket["signal_deal_sell_amount"] += amount

        is_active = active_sign != 0
        is_large_active = is_active and amount >= large_threshold
        if is_large_active:
            bucket["signed_large_active_amount"] += active_sign * amount
            if active_sign > 0:
                bucket["large_active_buy_amount"] += amount
            else:
                bucket["large_active_sell_amount"] += amount
        else:
            bucket["signed_mix_qr_amount"] += signed_amount
            if side_sign > 0:
                bucket["small_passive_buy_amount"] += amount
            elif side_sign < 0:
                bucket["small_passive_sell_amount"] += amount
            else:
                bucket["unknown_side_amount"] += amount

    previous_close = 0.0
    for bucket in buckets:
        open_price = float(bucket["window_open_price"])
        close_price = float(bucket["window_close_price"])
        if previous_close > 0 and close_price > 0:
            bucket["pi_max_price_impact_pct"] = (close_price - previous_close) / previous_close
        elif open_price > 0 and close_price > 0:
            bucket["pi_max_price_impact_pct"] = (close_price - open_price) / open_price
        else:
            bucket["pi_max_price_impact_pct"] = 0.0
        if close_price > 0:
            previous_close = close_price
    return buckets


def _build_daily_sample(symbol: str, trade_date: str, rows: list[dict]) -> DailySample:
    deal_amount = sum(_pick(row, ["deal_amount", "amount", "成交额"]) for row in rows)
    buy_amount = sum(_pick(row, ["signal_deal_buy_amount", "buy_amount", "主动买成交额"]) for row in rows)
    sell_amount = sum(_pick(row, ["signal_deal_sell_amount", "sell_amount", "主动卖成交额"]) for row in rows)
    cancel_ratio_values = [_pick(row, ["cb_cancel_order_ratio", "cancel_ratio", "撤单率"]) for row in rows]
    burst_values = [_pick(row, ["rs_burst_ratio", "burst_ratio", "爆发度"]) for row in rows]
    impact_values = [_pick(row, ["pi_max_price_impact_pct", "price_impact", "价格冲击"]) for row in rows]
    bid_support_values = [_pick(row, ["obp_at_best_bid_ratio", "best_bid_ratio", "买一挂单占比"]) for row in rows]
    ask_pressure_values = [_pick(row, ["obp_at_best_ask_ratio", "best_ask_ratio", "卖一挂单占比"]) for row in rows]

    tail_rows = [row for row in rows if str(row.get("window_id", "")).isdigit() and int(row["window_id"]) >= 42]
    tail_amount = sum(_pick(row, ["deal_amount", "amount", "成交额"]) for row in tail_rows)
    net_direction = (buy_amount - sell_amount) / deal_amount if deal_amount > 0 else 0.0

    summary = {
        "deal_amount": deal_amount,
        "buy_amount": buy_amount,
        "sell_amount": sell_amount,
        "net_direction": net_direction,
        "cancel_ratio": sum(cancel_ratio_values) / len(cancel_ratio_values) if cancel_ratio_values else 0.0,
        "burst_ratio": sum(burst_values) / len(burst_values) if burst_values else 0.0,
        "price_impact": max(impact_values) if impact_values else 0.0,
        "bid_support": sum(bid_support_values) / len(bid_support_values) if bid_support_values else 0.0,
        "ask_pressure": sum(ask_pressure_values) / len(ask_pressure_values) if ask_pressure_values else 0.0,
        "tail_ratio": tail_amount / deal_amount if deal_amount > 0 else 0.0,
        "window_count": len(rows),
    }
    quality_flags = {
        "has_reference_features": True,
        "window_count_ok": len(rows) > 0,
    }
    return DailySample(
        stock_code=symbol,
        transaction_date=trade_date,
        rows=rows,
        feature_summary=summary,
        quality_flags=quality_flags,
    )


def _scaled_price(value: object) -> float:
    raw = _to_float(value, 0.0)
    if raw > 1000:
        return raw / 10000.0
    return raw


def _load_rows_from_csv(path: Path, trade_date: str) -> list[dict]:
    rows: list[dict] = []
    reader = _open_csv_reader(path)
    fieldnames = reader.fieldnames or []
    try:
        for row in reader:
            row_date = str(row.get("自然日") or row.get("date") or row.get("trade_date") or "")
            if row_date and row_date != trade_date:
                continue
            rows.append(row)
    finally:
        if hasattr(reader, "reader") and hasattr(reader.reader, "line_num"):
            pass
        reader._fieldnames = fieldnames
        reader.reader = reader.reader
        reader_file = getattr(reader, "f", None)
    return rows


def _read_csv_rows(path: Path, trade_date: str) -> list[dict]:
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


def _build_daily_sample_from_stock_dir(stock_dir: Path, trade_date: str, config: dict | None = None) -> DailySample | None:
    config = config or {}
    trade_path = stock_dir / "逐笔成交.csv"
    order_path = stock_dir / "逐笔委托.csv"
    quote_path = stock_dir / "行情.csv"
    if not (trade_path.exists() and order_path.exists() and quote_path.exists()):
        return None

    trade_rows = _read_csv_rows(trade_path, trade_date)
    order_rows = _read_csv_rows(order_path, trade_date)
    quote_rows = _read_csv_rows(quote_path, trade_date)
    if not trade_rows and not quote_rows:
        return None

    symbol = stock_dir.name
    trade_amounts: list[float] = []
    trade_times: list[int] = []
    trade_prices: list[float] = []
    total_volume = 0.0
    for row in trade_rows:
        price = _scaled_price(row.get("成交价格"))
        volume = _to_float(row.get("成交数量"), 0.0)
        trade_amounts.append(price * volume)
        trade_prices.append(price)
        total_volume += volume
        trade_times.append(int(_to_float(row.get("时间"), 0.0)))

    total_trade_amount = sum(trade_amounts)
    tail_trade_amount = sum(amount for amount, t in zip(trade_amounts, trade_times) if t >= 143000000)
    avg_trade_size = total_trade_amount / len(trade_rows) if trade_rows else 0.0

    last_quote = quote_rows[-1] if quote_rows else {}
    prev_close = _scaled_price(last_quote.get("前收盘"))
    open_price = 0.0
    close_price = 0.0
    price_impact = 0.0
    up_count = int(_to_float(last_quote.get("上涨品种数"), 0.0))
    down_count = int(_to_float(last_quote.get("下跌品种数"), 0.0))
    flat_count = int(_to_float(last_quote.get("持平品种数"), 0.0))

    non_zero_closes = [_scaled_price(row.get("成交价")) for row in quote_rows if _scaled_price(row.get("成交价")) > 0]
    if non_zero_closes:
        close_price = non_zero_closes[-1]
    non_zero_opens = [_scaled_price(row.get("开盘价")) for row in quote_rows if _scaled_price(row.get("开盘价")) > 0]
    if non_zero_opens:
        open_price = non_zero_opens[0]
    non_zero_highs = [_scaled_price(row.get("最高价")) for row in quote_rows if _scaled_price(row.get("最高价")) > 0]
    non_zero_lows = [_scaled_price(row.get("最低价")) for row in quote_rows if _scaled_price(row.get("最低价")) > 0]
    high_price = max(non_zero_highs) if non_zero_highs else close_price
    low_price = min(non_zero_lows) if non_zero_lows else close_price
    if prev_close > 0 and close_price > 0:
        price_impact = abs(close_price - prev_close) / prev_close

    net_direction = 0.0
    close_return = 0.0
    open_return = 0.0
    intraday_range = 0.0
    close_strength = 0.0
    if prev_close > 0 and close_price > 0:
        reference_open = open_price if open_price > 0 else prev_close
        net_direction = (close_price - reference_open) / prev_close
        close_return = (close_price - prev_close) / prev_close
        open_return = (reference_open - prev_close) / prev_close
        intraday_range = (high_price - low_price) / prev_close if high_price > 0 and low_price > 0 else 0.0
    if high_price > low_price and close_price > 0:
        close_strength = (close_price - low_price) / (high_price - low_price)

    ask_vol = sum(_to_float(last_quote.get(f"申卖量{i}"), 0.0) for i in range(1, 11))
    bid_vol = sum(_to_float(last_quote.get(f"申买量{i}"), 0.0) for i in range(1, 11))
    bid_support = bid_vol / (bid_vol + ask_vol) if (bid_vol + ask_vol) > 0 else 0.0
    ask_pressure = ask_vol / (bid_vol + ask_vol) if (bid_vol + ask_vol) > 0 else 0.0

    bucket_counts: dict[int, int] = {}
    bucket_amounts: dict[int, float] = {}
    for row in trade_rows:
        t = int(_to_float(row.get("时间"), 0.0))
        hhmm = t // 100000
        bucket = (hhmm // 5) if hhmm > 0 else 0
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        bucket_amounts[bucket] = bucket_amounts.get(bucket, 0.0) + (
            _scaled_price(row.get("成交价格")) * _to_float(row.get("成交数量"), 0.0)
        )
    burst_ratio = 0.0
    if bucket_amounts:
        total_bucket_amount = sum(bucket_amounts.values())
        if total_bucket_amount > 0:
            burst_ratio = max(bucket_amounts.values()) / total_bucket_amount

    cancel_ratio = 0.0
    if order_rows:
        cancel_like = [row for row in order_rows if str(row.get("委托类型", "")).strip() not in {"", "0"}]
        cancel_ratio = len(cancel_like) / len(order_rows)
    buy_orders = sum(1 for row in order_rows if str(row.get("委托代码", "")).strip().upper() == "B")
    sell_orders = sum(1 for row in order_rows if str(row.get("委托代码", "")).strip().upper() == "S")
    order_buy_ratio = buy_orders / (buy_orders + sell_orders) if (buy_orders + sell_orders) > 0 else 0.5

    tail_quotes = [row for row in quote_rows if int(_to_float(row.get("时间"), 0.0)) >= 144500000]
    last15_prices = [_scaled_price(row.get("成交价")) for row in tail_quotes if _scaled_price(row.get("成交价")) > 0]
    last15_return = 0.0
    if last15_prices and prev_close > 0:
        last15_return = (last15_prices[-1] - last15_prices[0]) / prev_close

    directional_efficiency = 0.0
    reversal_strength = 0.0
    if intraday_range > 0:
        directional_efficiency = min(abs(close_return - open_return) / intraday_range, 1.0)
        reversal_strength = close_return - open_return

    pid_rows = _build_pid_rows_from_trades(trade_rows, config, quote_rows=quote_rows)
    active_pid_rows = [row for row in pid_rows if float(row.get("deal_amount", 0.0)) > 0]
    raw_hot_money_amount = sum(float(row["signed_large_active_amount"]) for row in pid_rows)
    raw_mix_qr_amount = sum(float(row["signed_mix_qr_amount"]) for row in pid_rows)
    raw_active_inferred_count = sum(int(row["active_inferred_count"]) for row in pid_rows)
    raw_side_fallback_count = sum(int(row["side_fallback_count"]) for row in pid_rows)
    raw_unknown_side_amount = sum(float(row["unknown_side_amount"]) for row in pid_rows)

    summary = {
        "deal_amount": total_trade_amount,
        "buy_amount": max(net_direction, 0.0) * total_trade_amount,
        "sell_amount": max(-net_direction, 0.0) * total_trade_amount,
        "raw_hot_money_amount": raw_hot_money_amount,
        "raw_mix_qr_amount": raw_mix_qr_amount,
        "raw_hot_money_ratio": abs(raw_hot_money_amount) / total_trade_amount if total_trade_amount > 0 else 0.0,
        "raw_active_inferred_count": raw_active_inferred_count,
        "raw_side_fallback_count": raw_side_fallback_count,
        "raw_unknown_side_amount": raw_unknown_side_amount,
        "net_direction": net_direction,
        "close_return": close_return,
        "open_return": open_return,
        "intraday_range": intraday_range,
        "close_strength": close_strength,
        "cancel_ratio": cancel_ratio,
        "burst_ratio": burst_ratio,
        "price_impact": price_impact,
        "bid_support": bid_support,
        "ask_pressure": ask_pressure,
        "tail_ratio": tail_trade_amount / total_trade_amount if total_trade_amount > 0 else 0.0,
        "last15_return": last15_return,
        "window_count": len(bucket_counts) if bucket_counts else 1,
        "total_volume": total_volume,
        "order_count": len(order_rows),
        "trade_count": len(trade_rows),
        "avg_trade_size": avg_trade_size,
        "order_buy_ratio": order_buy_ratio,
        "directional_efficiency": directional_efficiency,
        "reversal_strength": reversal_strength,
        "up_count_market": up_count,
        "down_count_market": down_count,
        "flat_count_market": flat_count,
    }
    quality_flags = {
        "has_reference_features": False,
        "window_count_ok": True,
        "source_layout": "per_stock_dirs",
    }
    return DailySample(
        stock_code=symbol,
        transaction_date=trade_date,
        rows=active_pid_rows,
        feature_summary=summary,
        quality_flags=quality_flags,
    )


def _load_daily_samples(
    input_dir: Path,
    trade_date: str,
    config: dict | None = None,
    stock_limit: int | None = None,
    stock_universe: set[str] | None = None,
) -> list[DailySample]:
    config = config or {}
    path = _find_reference_feature_file(input_dir)
    if path is None:
        if _is_stock_dir(input_dir):
            sample = _build_daily_sample_from_stock_dir(input_dir, trade_date, config=config)
            return [sample] if sample is not None else []
        samples: list[DailySample] = []
        stock_dirs = _filter_stock_dirs(_iter_stock_dirs(input_dir), stock_universe)
        if stock_limit is not None and stock_limit > 0:
            stock_dirs = stock_dirs[:stock_limit]
        for stock_dir in stock_dirs:
            sample = _build_daily_sample_from_stock_dir(stock_dir, trade_date, config=config)
            if sample is not None:
                samples.append(sample)
        return samples

    groups: dict[str, list[dict]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            row_date = str(row.get("date") or row.get("trade_date") or row.get("transaction_date") or "")
            if row_date != trade_date:
                continue
            symbol = str(row.get("symbol") or row.get("stock_code") or "").strip()
            if not symbol:
                continue
            if stock_universe and symbol.upper() not in stock_universe:
                continue
            groups.setdefault(symbol, []).append(row)

    return [_build_daily_sample(symbol, trade_date, rows) for symbol, rows in sorted(groups.items())]


def _slice_stock_dirs(stock_dirs: list[Path], stock_offset: int = 0, stock_limit: int | None = None) -> list[Path]:
    start = max(stock_offset, 0)
    if stock_limit is not None and stock_limit > 0:
        return stock_dirs[start : start + stock_limit]
    return stock_dirs[start:]


def _sort_by_requested_order(items: list, requested_symbols: list[str] | None, key_name: str) -> list:
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


def _build_market_average_summary(samples: list[DailySample]) -> dict[str, float]:
    numeric_values: dict[str, list[float]] = {}
    for sample in samples:
        for key, value in sample.feature_summary.items():
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


def _build_imputed_results(
    missing_symbols: list[str],
    trade_date: str,
    samples: list[DailySample],
    config: dict,
    label_dict: dict,
    pid_decomposer: PIDDecomposer,
) -> tuple[list[PatternResult], list[PredictResult]]:
    if not missing_symbols or not samples:
        return [], []

    market_average_summary = _build_market_average_summary(samples)
    pattern_results: list[PatternResult] = []
    predict_results: list[PredictResult] = []

    for symbol in missing_symbols:
        default_sample = DailySample(
            stock_code=symbol,
            transaction_date=trade_date,
            rows=[],
            feature_summary=dict(market_average_summary),
            quality_flags={
                "has_reference_features": False,
                "window_count_ok": False,
                "imputed_from_market_average": True,
                "source_layout": "missing_raw_data",
            },
        )
        pattern_result = predict_pattern(default_sample, config, label_dict)
        pattern_result.pattern_explanation = f"{pattern_result.pattern_explanation} 缺失原始数据，按当日市场中位水平补全判断。"
        pattern_result.prototype_id = f"imputed::{pattern_result.prototype_id}"

        pid_result = pid_decomposer.decompose_sample(default_sample)
        predict_batch = predict_capitals(default_sample, config, label_dict, pid_result)
        for predict_result in predict_batch:
            predict_result.debug_info.update(
                {
                    "imputed_from_market_average": True,
                    "imputed_reason": "missing_raw_data",
                }
            )

        pattern_results.append(pattern_result)
        predict_results.extend(predict_batch)

    return pattern_results, predict_results


def run_daily_batch(
    trade_date: str,
    input_dir: str | Path,
    output_dir: str | Path,
    config: dict,
    label_dict: dict,
    stock_limit: int | None = None,
    stock_offset: int = 0,
    stock_list_file: str | Path | None = None,
    enable_submit_zip: bool = True,
    profile_enabled: bool = False,
    submit_date_override: str | None = None,
) -> dict:
    batch_started_at = perf_counter()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dir = Path(input_dir)
    requested_symbols, stock_universe = _load_stock_universe(stock_list_file)
    sample_build_seconds = 0.0
    pattern_seconds = 0.0
    capital_seconds = 0.0
    market_seconds = 0.0
    export_seconds = 0.0
    sample_timings: list[dict[str, float | str]] = []

    warnings: list[str] = []
    incomplete_stock_dirs: dict[str, list[str]] = {}
    if _find_reference_feature_file(input_dir) is None and not _is_stock_dir(input_dir):
        stock_dirs = _slice_stock_dirs(
            _filter_stock_dirs(_iter_stock_dirs(input_dir), stock_universe),
            stock_offset=stock_offset,
            stock_limit=stock_limit,
        )
        samples: list[DailySample] = []
        for stock_dir in stock_dirs:
            missing_files = _get_missing_required_files(stock_dir)
            if missing_files:
                incomplete_stock_dirs[stock_dir.name] = missing_files
                continue
            started_at = perf_counter()
            sample = _build_daily_sample_from_stock_dir(stock_dir, trade_date, config=config)
            elapsed = perf_counter() - started_at
            sample_build_seconds += elapsed
            if sample is not None:
                samples.append(sample)
                if profile_enabled:
                    sample_timings.append(
                        {
                            "stock_code": stock_dir.name,
                            "sample_build_seconds": _round_seconds(elapsed),
                        }
                    )
    else:
        started_at = perf_counter()
        samples = _load_daily_samples(input_dir, trade_date, config=config, stock_limit=stock_limit, stock_universe=stock_universe)
        sample_build_seconds += perf_counter() - started_at
    if not samples:
        warnings.append("No reference feature rows found for the requested date; emitted header-only files.")

    started_at = perf_counter()
    pattern_results: list[PatternResult] = [predict_pattern(sample, config, label_dict) for sample in samples]
    pattern_seconds = perf_counter() - started_at

    started_at = perf_counter()
    pid_decomposer = PIDDecomposer(config)
    predict_results: list[PredictResult] = []
    for sample in samples:
        pid_result = pid_decomposer.decompose_sample(sample)
        predict_results.extend(predict_capitals(sample, config, label_dict, pid_result))
    capital_seconds = perf_counter() - started_at
    market_snapshot: MarketPidSnapshot | None = None

    if samples and config.get("enable_market_snapshot", True):
        started_at = perf_counter()
        market_snapshot = estimate_market_pid(samples, pattern_results, predict_results, config)
        attach_market_relative_metrics(samples, predict_results, market_snapshot)
        market_seconds = perf_counter() - started_at

    missing_symbols: list[str] = []
    if requested_symbols:
        actual_symbols = {sample.stock_code.upper() for sample in samples}
        missing_symbols = [symbol for symbol in requested_symbols if symbol not in actual_symbols]
        if missing_symbols:
            warnings.append("Missing raw data for requested symbols: " + ", ".join(missing_symbols))
    if incomplete_stock_dirs:
        warnings.append(_format_incomplete_stock_warning(incomplete_stock_dirs))

    imputed_pattern_results: list[PatternResult] = []
    imputed_predict_results: list[PredictResult] = []
    if missing_symbols and samples:
        started_at = perf_counter()
        imputed_pattern_results, imputed_predict_results = _build_imputed_results(
            missing_symbols,
            trade_date,
            samples,
            config,
            label_dict,
            pid_decomposer,
        )
        elapsed = perf_counter() - started_at
        pattern_seconds += elapsed / 2.0
        capital_seconds += elapsed / 2.0
        pattern_results.extend(imputed_pattern_results)
        predict_results.extend(imputed_predict_results)
        warnings.append("Imputed missing symbols with market-average defaults: " + ", ".join(missing_symbols))

    pattern_results = _sort_by_requested_order(pattern_results, requested_symbols, "stock_code")
    predict_results = _sort_by_requested_order(predict_results, requested_symbols, "stock_code")

    started_at = perf_counter()
    export_pattern_reco(
        pattern_results,
        output_dir / "pattern_reco.csv",
        submit_date_override=submit_date_override,
    )
    export_predict_result(
        predict_results,
        output_dir / "predict_result.csv",
        submit_date_override=submit_date_override,
    )
    diagnostics_json_path, distribution_csv_path = export_batch_diagnostics(
        market_snapshot,
        pattern_results,
        predict_results,
        output_dir,
    )
    market_snapshot_path = None
    market_report_path = None
    if market_snapshot is not None:
        market_snapshot_path = output_dir / "market_pid_snapshot.csv"
        market_report_path = output_dir / "market_regime_report.md"
        export_market_pid_snapshot(market_snapshot, market_snapshot_path)
        export_market_regime_report(market_snapshot, market_report_path)
    export_seconds = perf_counter() - started_at

    submit_zip = None
    if enable_submit_zip:
        started_at = perf_counter()
        submit_zip = build_submit_zip(output_dir)
        export_seconds += perf_counter() - started_at

    performance_summary = None
    if profile_enabled:
        total_seconds = perf_counter() - batch_started_at
        top_slowest_samples = sorted(
            sample_timings,
            key=lambda item: float(item["sample_build_seconds"]),
            reverse=True,
        )[:20]
        performance_summary = {
            "total_seconds": _round_seconds(total_seconds),
            "sample_build_seconds": _round_seconds(sample_build_seconds),
            "pattern_seconds": _round_seconds(pattern_seconds),
            "capital_seconds": _round_seconds(capital_seconds),
            "market_seconds": _round_seconds(market_seconds),
            "export_seconds": _round_seconds(export_seconds),
            "processed_samples": len(samples),
            "imputed_missing_symbols": len(imputed_predict_results),
            "skipped_incomplete_samples": len(incomplete_stock_dirs),
            "top_slowest_samples": top_slowest_samples,
        }

    return {
        "trade_date": trade_date,
        "pattern_results": pattern_results,
        "predict_results": predict_results,
        "market_pid_snapshot": market_snapshot,
        "market_snapshot_path": str(market_snapshot_path) if market_snapshot_path else None,
        "market_report_path": str(market_report_path) if market_report_path else None,
        "diagnostics_json_path": diagnostics_json_path,
        "distribution_csv_path": distribution_csv_path,
        "submit_zip": submit_zip,
        "warnings": warnings,
        "sample_count": len(samples),
        "imputed_output_count": len(imputed_predict_results),
        "output_count": len(pattern_results),
        "stock_offset": stock_offset,
        "stock_limit": stock_limit,
        "stock_list_file": str(stock_list_file) if stock_list_file else None,
        "stock_universe_size": len(stock_universe) if stock_universe is not None else None,
        "missing_symbols": missing_symbols,
        "incomplete_stock_dirs": incomplete_stock_dirs,
        "performance_summary": performance_summary,
    }

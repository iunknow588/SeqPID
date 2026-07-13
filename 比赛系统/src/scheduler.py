from __future__ import annotations

import csv
from bisect import bisect_right
from pathlib import Path
from time import perf_counter
from typing import Callable

from capital_model import predict_capitals
from batch_alerts import build_batch_warnings, collect_missing_symbols
from batch_reporting import build_batch_result, build_batch_summary, build_performance_summary
import data_loader
from exporter import (
    build_submit_zip,
    export_batch_diagnostics,
    export_event_classified_rows,
    export_market_pid_validation_report,
    export_market_pid_snapshot,
    export_market_regime_report,
    export_pattern_reco,
    export_pid_tail_diagnostics,
    export_pid_window_contrib,
    export_pid_window_params,
    export_window_feature_rows,
    export_window_flow_rows,
    export_predict_result,
    export_replay_validation_report,
)
from market_pid import attach_market_relative_metrics, estimate_market_pid
from order_lifecycle import OrderLifecycleResolver, is_cancel_trade, time_value_to_seconds
from pattern_model import predict_pattern
from pid_decomposer import PIDDecomposer
from sample_imputation import build_imputed_results
from schemas import DailySample, MarketPidSnapshot, PatternResult, PredictResult

ProgressFn = Callable[[str], None]


def _round_seconds(value: float) -> float:
    return round(value, 6)


def _emit_progress(progress_callback: ProgressFn | None, percent: float, message: str) -> None:
    if progress_callback is None:
        return
    progress_callback(f"Progress {percent:5.1f}% | {message}")


def _stage_percent(start: float, end: float, current: int, total: int) -> float:
    if total <= 0:
        return end
    return start + (end - start) * min(max(current, 0), total) / total


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
    raw = _pick_text(
        row,
        ["BS标志", "BS鏍囧織", "side", "买卖方向", "涔板崠鏂瑰悜", "成交方向", "鎴愪氦鏂瑰悜", "委托代码", "濮旀墭浠ｇ爜"],
    ).upper()
    if raw in {"B", "BUY", "1"}:
        return 1
    if raw in {"S", "SELL", "2"}:
        return -1
    return 0


def _row_time_value(row: dict) -> int:
    return int(
        _to_float(
            row.get("时间") or row.get("鏃堕棿") or row.get("timestamp_ms") or row.get("time") or row.get("閺冨爼妫?"),
            0.0,
        )
    )


def _order_id_candidates(row: dict, side_sign: int) -> list[str]:
    if side_sign > 0:
        keys = ["sell_order_id", "鍗栨柟濮旀墭搴忓彿", "ask_order_id", "order_id"]
    elif side_sign < 0:
        keys = ["buy_order_id", "涔版柟濮旀墭搴忓彿", "bid_order_id", "order_id"]
    else:
        keys = ["order_id", "濮旀墭搴忓彿", "涔版柟濮旀墭搴忓彿", "鍗栨柟濮旀墭搴忓彿"]
    ids: list[str] = []
    for key in keys:
        value = str(row.get(key, "") or "").strip()
        if value:
            ids.append(value)
    return ids


def _build_order_time_index(order_rows: list[dict]) -> dict[str, int]:
    index: dict[str, int] = {}
    id_keys = ["order_id", "濮旀墭搴忓彿", "涔版柟濮旀墭搴忓彿", "鍗栨柟濮旀墭搴忓彿"]
    for row in order_rows:
        timestamp = _row_time_value(row)
        if timestamp <= 0:
            continue
        for key in id_keys:
            order_id = str(row.get(key, "") or "").strip()
            if order_id:
                index.setdefault(order_id, timestamp)
    return index


def _infer_order_age_minutes(row: dict, trade_timestamp: int, order_time_by_id: dict[str, int]) -> float | None:
    direct_age = row.get("order_age_minutes")
    if direct_age not in (None, ""):
        try:
            return float(direct_age)
        except (TypeError, ValueError):
            pass

    side_sign = _trade_side_sign(row)
    for order_id in _order_id_candidates(row, side_sign):
        order_timestamp = order_time_by_id.get(order_id)
        if order_timestamp is not None and trade_timestamp >= order_timestamp:
            return (trade_timestamp - order_timestamp) / 100000.0
    return None


def _build_quote_series(quote_rows: list[dict]) -> tuple[list[int], list[dict]]:
    series: list[tuple[int, dict]] = []
    for row in quote_rows:
        timestamp = _row_time_value(row)
        if timestamp <= 0:
            continue
        bid_px_1 = _scaled_price(
            row.get("申买价1") or row.get("鐢充拱浠?") or row.get("bid_px_1") or row.get("bid1") or row.get("瀵偓閻╂ü鐜?")
        )
        bid_px_2 = _scaled_price(
            row.get("申买价2")
            or row.get("申买价1")
            or
            row.get("鐢充拱浠?")
            or row.get("bid_px_2")
            or row.get("bid2")
            or row.get("娑撳﹥瀹氶崫浣侯潚閺?")
        )
        ask_px_1 = _scaled_price(
            row.get("申卖价1")
            or row.get("鐢冲崠浠?")
            or row.get("ask_px_1")
            or row.get("ask1")
            or row.get("閹存劒姘︽禒?")
        )
        ask_px_2 = _scaled_price(
            row.get("申卖价2")
            or row.get("申卖价1")
            or row.get("鐢冲崠浠?")
            or row.get("ask_px_2")
            or row.get("ask2")
            or row.get("娑撳绌奸崫浣侯潚閺?")
        )
        if bid_px_1 <= 0 and ask_px_1 <= 0:
            continue
        series.append(
            (
                timestamp,
                {
                    "bid_px_1": bid_px_1,
                    "bid_px_2": bid_px_2,
                    "ask_px_1": ask_px_1,
                    "ask_px_2": ask_px_2,
                },
            )
        )
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


def _is_aggressive_price_shaping(price: float, quote: dict, active_sign: int) -> bool:
    if active_sign > 0:
        ask_px_1 = float(quote.get("ask_px_1", 0.0) or 0.0)
        ask_px_2 = float(quote.get("ask_px_2", 0.0) or 0.0)
        return (ask_px_2 > 0 and price >= ask_px_2) or (ask_px_2 <= 0 < ask_px_1 and price > ask_px_1)
    if active_sign < 0:
        bid_px_1 = float(quote.get("bid_px_1", 0.0) or 0.0)
        bid_px_2 = float(quote.get("bid_px_2", 0.0) or 0.0)
        return (bid_px_2 > 0 and price <= bid_px_2) or (bid_px_2 <= 0 < bid_px_1 and price < bid_px_1)
    return False


def _qualifies_hot_money(
    bucket: dict,
    active_sign: int,
    amount: float,
    large_threshold: float,
    active_fallback_hot_amount: float,
    is_price_shaping_active: bool,
    quote_known: bool,
) -> bool:
    if active_sign == 0:
        return False
    if not quote_known:
        return amount >= active_fallback_hot_amount
    if amount >= large_threshold:
        return True
    if not is_price_shaping_active:
        return False
    same_dir_count = bucket["active_buy_count"] if active_sign > 0 else bucket["active_sell_count"]
    same_dir_amount = bucket["active_buy_amount"] if active_sign > 0 else bucket["active_sell_amount"]
    moderate_support = amount >= active_fallback_hot_amount and (
        same_dir_count >= 1 or same_dir_amount >= active_fallback_hot_amount
    )
    strong_support = same_dir_count >= 2 and same_dir_amount >= active_fallback_hot_amount * 1.5
    return moderate_support or strong_support


def _build_pid_rows_from_trades(
    trade_rows: list[dict],
    config: dict,
    quote_rows: list[dict] | None = None,
    order_rows: list[dict] | None = None,
) -> list[dict]:
    species_rules = config.get("species_rules", {})
    large_threshold = float(species_rules.get("large_order_amount_threshold", 500_000.0))
    active_fallback_hot_amount = float(species_rules.get("active_fallback_hot_amount", 100_000.0))
    passive_survival_minutes = float(species_rules.get("passive_survival_minutes", 5.0))
    active_fallback_to_side = bool(species_rules.get("active_fallback_to_side", True))
    quote_times, quote_values = _build_quote_series(quote_rows or [])
    lifecycle_resolver = OrderLifecycleResolver(order_rows or [], trade_rows)
    buckets = [
        {
            "window_id": str(index),
            "deal_amount": 0.0,
            "signal_deal_buy_amount": 0.0,
            "signal_deal_sell_amount": 0.0,
            "signed_large_active_amount": 0.0,
            "signed_mix_qr_amount": 0.0,
            "CH_rule_t": 0.0,
            "Q_rule_t": 0.0,
            "R_seed_t": 0.0,
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
            "low_fallback_count": 0,
            "order_age_recovered_count": 0,
            "order_age_missing_count": 0,
            "order_age_direct_count": 0,
            "order_age_fifo_count": 0,
            "order_age_unresolved_count": 0,
            "active_buy_count": 0,
            "active_sell_count": 0,
            "active_buy_amount": 0.0,
            "active_sell_amount": 0.0,
        }
        for index in range(48)
    ]

    for row in trade_rows:
        if is_cancel_trade(row):
            continue
        timestamp = _row_time_value(row)
        window_id = _time_to_window_id(timestamp)
        if window_id is None:
            continue
        price = _scaled_price(
            row.get("成交价格") or row.get("鎴愪氦浠锋牸") or row.get("price") or row.get("閹存劒姘︽禒閿嬬壐")
        )
        volume = _to_float(
            row.get("成交数量") or row.get("鎴愪氦鏁伴噺") or row.get("volume") or row.get("閹存劒姘﹂弫浼村櫤"),
            0.0,
        )
        explicit_amount = _to_float(row.get("成交金额") or row.get("鎴愪氦閲戦") or row.get("amount"), 0.0)
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

        order_age = lifecycle_resolver.lookup_order_age_minutes(
            row,
            trade_time_seconds=time_value_to_seconds(timestamp),
            active_sign=active_sign,
            side_sign=side_sign,
            trade_price=price,
            trade_volume=volume,
        )
        if order_age.order_age_minutes is not None:
            bucket["order_age_recovered_count"] += 1
        else:
            bucket["order_age_missing_count"] += 1
        if order_age.recovery_method == "direct_order_id":
            bucket["order_age_direct_count"] += 1
        elif order_age.recovery_method == "fifo_price_queue":
            bucket["order_age_fifo_count"] += 1
        else:
            bucket["order_age_unresolved_count"] += 1

        is_active = active_sign != 0
        is_price_shaping_active = is_active and _is_aggressive_price_shaping(price, quote, active_sign)
        is_large_active = _qualifies_hot_money(
            bucket,
            active_sign,
            amount,
            large_threshold,
            active_fallback_hot_amount,
            is_price_shaping_active,
            bool(quote),
        )
        if is_active:
            if active_sign > 0:
                bucket["active_buy_count"] += 1
                bucket["active_buy_amount"] += amount
            else:
                bucket["active_sell_count"] += 1
                bucket["active_sell_amount"] += amount
        if is_large_active:
            bucket["signed_large_active_amount"] += active_sign * amount
            bucket["CH_rule_t"] += active_sign * amount
            if active_sign > 0:
                bucket["large_active_buy_amount"] += amount
            else:
                bucket["large_active_sell_amount"] += amount
        else:
            bucket["signed_mix_qr_amount"] += signed_amount
            rule_signed_amount = active_sign * amount if is_active else signed_amount
            if is_active:
                bucket["Q_rule_t"] += rule_signed_amount
            else:
                if order_age.order_age_minutes is not None and order_age.order_age_minutes > passive_survival_minutes:
                    bucket["R_seed_t"] += rule_signed_amount
                else:
                    bucket["Q_rule_t"] += rule_signed_amount
                    if order_age.order_age_minutes is None:
                        bucket["low_fallback_count"] += 1
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
    buy_amount = sum(_pick(row, ["signal_deal_buy_amount", "buy_amount", "主动买成交额", "涓诲姩涔版垚浜ら"]) for row in rows)
    sell_amount = sum(_pick(row, ["signal_deal_sell_amount", "sell_amount", "主动卖成交额", "涓诲姩鍗栨垚浜ら"]) for row in rows)
    cancel_ratio_values = [_pick(row, ["cb_cancel_order_ratio", "cancel_ratio", "撤单率"]) for row in rows]
    burst_values = [_pick(row, ["rs_burst_ratio", "burst_ratio", "爆发度"]) for row in rows]
    impact_values = [_pick(row, ["pi_max_price_impact_pct", "price_impact", "价格冲击", "浠锋牸鍐插嚮"]) for row in rows]
    bid_support_values = [_pick(row, ["obp_at_best_bid_ratio", "best_bid_ratio", "买一挂单占比", "涔颁竴鎸傚崟鍗犳瘮"]) for row in rows]
    ask_pressure_values = [_pick(row, ["obp_at_best_ask_ratio", "best_ask_ratio", "卖一挂单占比", "鍗栦竴鎸傚崟鍗犳瘮"]) for row in rows]

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
            row_date = str(row.get("date") or row.get("trade_date") or "")
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
                    row_date = str(row.get("date") or row.get("trade_date") or "")
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
    actual_trade_rows = [row for row in trade_rows if not is_cancel_trade(row)]
    trade_amounts: list[float] = []
    trade_times: list[int] = []
    total_volume = 0.0
    bucket_counts: dict[int, int] = {}
    bucket_amounts: dict[int, float] = {}
    for row in actual_trade_rows:
        price = _scaled_price(
            row.get("成交价格")
            or row.get("鎴愪氦浠锋牸")
            or row.get("price")
            or row.get("閹存劒姘︽禒閿嬬壐")
        )
        volume = _to_float(
            row.get("成交数量")
            or row.get("鎴愪氦鏁伴噺")
            or row.get("volume")
            or row.get("閹存劒姘﹂弫浼村櫤"),
            0.0,
        )
        amount = price * volume
        timestamp = _row_time_value(row)
        trade_amounts.append(amount)
        trade_times.append(timestamp)
        total_volume += volume
        hhmm = timestamp // 100000
        bucket = (hhmm // 5) if hhmm > 0 else 0
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        bucket_amounts[bucket] = bucket_amounts.get(bucket, 0.0) + amount

    total_trade_amount = sum(trade_amounts)
    tail_trade_amount = sum(amount for amount, t in zip(trade_amounts, trade_times) if t >= 143000000)
    avg_trade_size = total_trade_amount / len(actual_trade_rows) if actual_trade_rows else 0.0

    last_quote = quote_rows[-1] if quote_rows else {}
    prev_close = _scaled_price(
        last_quote.get("prev_close")
        or last_quote.get("pre_close")
        or last_quote.get("前收盘")
        or last_quote.get("瀵偓閻╂ü鐜?")
    )
    open_price = 0.0
    close_price = 0.0
    high_price = 0.0
    low_price = 0.0
    price_impact = 0.0
    up_count = int(_to_float(last_quote.get("up_count_market") or last_quote.get("上涨品种数") or last_quote.get("閹镐礁閽╅崫浣侯潚閺?"), 0.0))
    down_count = int(_to_float(last_quote.get("down_count_market") or last_quote.get("下跌品种数"), 0.0))
    flat_count = int(_to_float(last_quote.get("flat_count_market") or last_quote.get("持平品种数"), 0.0))
    last15_prices: list[float] = []

    for row in quote_rows:
        row_close = _scaled_price(
            row.get("close")
            or row.get("last_price")
            or row.get("price")
            or row.get("成交价")
            or row.get("閹存劒姘︽禒?")
        )
        if row_close > 0:
            close_price = row_close
        row_open = _scaled_price(row.get("开盘价") or row.get("寮€鐩樹环") or row.get("閺堚偓妤傛ü鐜?"))
        if open_price <= 0 and row_open > 0:
            open_price = row_open
        row_high = _scaled_price(row.get("最高价") or row.get("鏈€楂樹环") or row.get("閺堚偓娴ｅ簼鐜?"))
        if row_high > 0:
            high_price = max(high_price, row_high)
        row_low = _scaled_price(row.get("最低价") or row.get("鏈€浣庝环") or row.get("閸撳秵鏁归惄?"))
        if row_low > 0:
            low_price = row_low if low_price <= 0 else min(low_price, row_low)
        if int(_to_float(row.get("时间") or row.get("鏃堕棿"), 0.0)) >= 144500000 and row_close > 0:
            last15_prices.append(row_close)

    if high_price <= 0:
        high_price = close_price
    if low_price <= 0:
        low_price = close_price
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

    ask_vol = sum(
        _to_float(
            last_quote.get(f"ask_vol_{i}")
            or last_quote.get(f"ask_volume_{i}")
            or last_quote.get(f"申卖量{i}")
            or (last_quote.get("娑撳绌奸崫浣侯潚閺?") if i == 1 else None),
            0.0,
        )
        for i in range(1, 11)
    )
    bid_vol = sum(
        _to_float(
            last_quote.get(f"bid_vol_{i}")
            or last_quote.get(f"bid_volume_{i}")
            or last_quote.get(f"申买量{i}")
            or (last_quote.get("娑撳﹥瀹氶崫浣侯潚閺?") if i == 1 else None),
            0.0,
        )
        for i in range(1, 11)
    )
    bid_support = bid_vol / (bid_vol + ask_vol) if (bid_vol + ask_vol) > 0 else 0.0
    ask_pressure = ask_vol / (bid_vol + ask_vol) if (bid_vol + ask_vol) > 0 else 0.0

    burst_ratio = 0.0
    if bucket_amounts:
        total_bucket_amount = sum(bucket_amounts.values())
        if total_bucket_amount > 0:
            burst_ratio = max(bucket_amounts.values()) / total_bucket_amount

    cancel_ratio = 0.0
    if order_rows:
        cancel_like = [
            row
            for row in order_rows
            if str(row.get("委托类型") or row.get("濮旀墭绫诲瀷") or row.get("婵梹澧猾璇茬€?") or "").strip() not in {"", "0"}
        ]
        cancel_ratio = len(cancel_like) / len(order_rows)
    buy_orders = sum(
        1
        for row in order_rows
        if str(row.get("委托代码") or row.get("濮旀墭浠ｇ爜") or row.get("婵梹澧禒锝囩垳") or "").strip().upper() == "B"
    )
    sell_orders = sum(
        1
        for row in order_rows
        if str(row.get("委托代码") or row.get("濮旀墭浠ｇ爜") or row.get("婵梹澧禒锝囩垳") or "").strip().upper() == "S"
    )
    order_buy_ratio = buy_orders / (buy_orders + sell_orders) if (buy_orders + sell_orders) > 0 else 0.5

    last15_return = 0.0
    if last15_prices and prev_close > 0:
        last15_return = (last15_prices[-1] - last15_prices[0]) / prev_close

    directional_efficiency = 0.0
    reversal_strength = 0.0
    if intraday_range > 0:
        directional_efficiency = min(abs(close_return - open_return) / intraday_range, 1.0)
        reversal_strength = close_return - open_return

    pid_rows = _build_pid_rows_from_trades(trade_rows, config, quote_rows=quote_rows, order_rows=order_rows)
    active_pid_rows = [row for row in pid_rows if float(row.get("deal_amount", 0.0)) > 0]
    raw_hot_money_amount = sum(float(row["signed_large_active_amount"]) for row in pid_rows)
    raw_mix_qr_amount = sum(float(row["signed_mix_qr_amount"]) for row in pid_rows)
    raw_active_inferred_count = sum(int(row["active_inferred_count"]) for row in pid_rows)
    raw_side_fallback_count = sum(int(row["side_fallback_count"]) for row in pid_rows)
    raw_unknown_side_amount = sum(float(row["unknown_side_amount"]) for row in pid_rows)
    raw_order_age_recovered_count = sum(int(row["order_age_recovered_count"]) for row in pid_rows)
    raw_order_age_missing_count = sum(int(row["order_age_missing_count"]) for row in pid_rows)
    raw_order_age_direct_count = sum(int(row["order_age_direct_count"]) for row in pid_rows)
    raw_order_age_fifo_count = sum(int(row["order_age_fifo_count"]) for row in pid_rows)
    raw_order_age_unresolved_count = sum(int(row["order_age_unresolved_count"]) for row in pid_rows)
    raw_order_age_total_count = raw_order_age_recovered_count + raw_order_age_missing_count
    raw_order_age_recovery_ratio = (
        raw_order_age_recovered_count / raw_order_age_total_count if raw_order_age_total_count > 0 else 0.0
    )

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
        "raw_order_age_recovered_count": raw_order_age_recovered_count,
        "raw_order_age_missing_count": raw_order_age_missing_count,
        "raw_order_age_direct_count": raw_order_age_direct_count,
        "raw_order_age_fifo_count": raw_order_age_fifo_count,
        "raw_order_age_unresolved_count": raw_order_age_unresolved_count,
        "raw_order_age_recovery_ratio": raw_order_age_recovery_ratio,
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
        "trade_count": len(actual_trade_rows),
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
    path = data_loader.find_reference_feature_file(input_dir)
    if path is None:
        if data_loader.is_stock_dir(input_dir):
            sample = _build_daily_sample_from_stock_dir(input_dir, trade_date, config=config)
            return [sample] if sample is not None else []
        samples: list[DailySample] = []
        stock_dirs = data_loader.filter_stock_dirs(data_loader.iter_stock_dirs(input_dir), stock_universe)
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
    progress_callback: ProgressFn | None = None,
) -> dict:
    batch_started_at = perf_counter()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dir = Path(input_dir)
    _emit_progress(progress_callback, 0.0, "starting batch analysis")
    requested_symbols, stock_universe = data_loader.load_stock_universe(stock_list_file)
    sample_build_seconds = 0.0
    pattern_seconds = 0.0
    capital_seconds = 0.0
    market_seconds = 0.0
    export_seconds = 0.0
    sample_timings: list[dict[str, float | str]] = []

    incomplete_stock_dirs: dict[str, list[str]] = {}
    if data_loader.find_reference_feature_file(input_dir) is None and not data_loader.is_stock_dir(input_dir):
        stock_dirs = data_loader.slice_stock_dirs(
            data_loader.filter_stock_dirs(data_loader.iter_stock_dirs(input_dir), stock_universe),
            stock_offset=stock_offset,
            stock_limit=stock_limit,
        )
        total_stock_dirs = len(stock_dirs)
        _emit_progress(progress_callback, 1.0, f"building samples 0/{total_stock_dirs}")
        samples: list[DailySample] = []
        for index, stock_dir in enumerate(stock_dirs, start=1):
            missing_files = data_loader.get_missing_required_files(stock_dir)
            if missing_files:
                incomplete_stock_dirs[stock_dir.name] = missing_files
                percent = _stage_percent(0.0, 45.0, index, total_stock_dirs)
                _emit_progress(progress_callback, percent, f"skipped incomplete sample {index}/{total_stock_dirs} {stock_dir.name}")
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
            percent = _stage_percent(0.0, 45.0, index, total_stock_dirs)
            _emit_progress(progress_callback, percent, f"built sample {index}/{total_stock_dirs} {stock_dir.name}")
    else:
        _emit_progress(progress_callback, 1.0, "loading samples from flat input")
        started_at = perf_counter()
        samples = _load_daily_samples(input_dir, trade_date, config=config, stock_limit=stock_limit, stock_universe=stock_universe)
        sample_build_seconds += perf_counter() - started_at
        _emit_progress(progress_callback, 45.0, f"loaded samples {len(samples)}")
    started_at = perf_counter()
    pid_decomposer = PIDDecomposer(config)
    pid_results_by_symbol = {}
    total_samples = len(samples)
    for index, sample in enumerate(samples, start=1):
        pid_results_by_symbol[sample.stock_code] = pid_decomposer.decompose_sample(sample)
        percent = _stage_percent(45.0, 65.0, index, total_samples)
        _emit_progress(progress_callback, percent, f"PID {index}/{total_samples} {sample.stock_code}")
    pid_seconds = perf_counter() - started_at

    started_at = perf_counter()
    pattern_results: list[PatternResult] = []
    for index, sample in enumerate(samples, start=1):
        pattern_results.append(predict_pattern(sample, config, label_dict, pid_results_by_symbol.get(sample.stock_code)))
        percent = _stage_percent(65.0, 75.0, index, total_samples)
        _emit_progress(progress_callback, percent, f"pattern {index}/{total_samples} {sample.stock_code}")
    pattern_seconds = perf_counter() - started_at

    started_at = perf_counter()
    predict_results: list[PredictResult] = []
    for index, sample in enumerate(samples, start=1):
        pid_result = pid_results_by_symbol[sample.stock_code]
        predict_results.extend(predict_capitals(sample, config, label_dict, pid_result))
        percent = _stage_percent(75.0, 88.0, index, total_samples)
        _emit_progress(progress_callback, percent, f"capital {index}/{total_samples} {sample.stock_code}")
    capital_seconds = perf_counter() - started_at + pid_seconds
    market_snapshot: MarketPidSnapshot | None = None

    if samples and config.get("enable_market_snapshot", True):
        _emit_progress(progress_callback, 89.0, "estimating market snapshot")
        started_at = perf_counter()
        market_snapshot = estimate_market_pid(samples, pid_results_by_symbol, pattern_results, predict_results, config)
        attach_market_relative_metrics(samples, predict_results, market_snapshot)
        market_seconds = perf_counter() - started_at
    _emit_progress(progress_callback, 92.0, "building warnings and imputed outputs")

    missing_symbols = collect_missing_symbols(requested_symbols, samples)
    warnings = build_batch_warnings(samples, missing_symbols, incomplete_stock_dirs)

    imputed_pattern_results: list[PatternResult] = []
    imputed_predict_results: list[PredictResult] = []
    if missing_symbols and samples:
        started_at = perf_counter()
        imputed_pattern_results, imputed_predict_results = build_imputed_results(
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
        warnings = build_batch_warnings(samples, missing_symbols, incomplete_stock_dirs, imputed_symbols=missing_symbols)

    _emit_progress(progress_callback, 94.0, "exporting result files")
    pattern_results = data_loader.sort_by_requested_order(pattern_results, requested_symbols, "stock_code")
    predict_results = data_loader.sort_by_requested_order(predict_results, requested_symbols, "stock_code")

    started_at = perf_counter()
    export_event_classified_rows(samples, output_dir / "event_classified_rows.csv")
    export_window_feature_rows(samples, output_dir / "window_feature_rows.csv")
    export_window_flow_rows(samples, output_dir / "pid_window_flow_rows.csv")
    pid_results = list(pid_results_by_symbol.values())
    export_pid_window_params(pid_results, output_dir / "pid_window_params.csv")
    export_pid_window_contrib(pid_results, output_dir / "pid_window_contrib.csv")
    export_pid_tail_diagnostics(pid_results, output_dir / "pid_tail_diagnostics.csv")
    market_snapshot_path = None
    market_report_path = None
    if market_snapshot is not None:
        market_snapshot_path = output_dir / "market_pid_snapshot.csv"
        market_report_path = output_dir / "market_regime_report.md"
        export_market_pid_snapshot(market_snapshot, market_snapshot_path)
        export_market_regime_report(market_snapshot, market_report_path)
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
    batch_summary = build_batch_summary(
        trade_date=trade_date,
        sample_count=len(samples),
        output_count=len(pattern_results),
        warnings=warnings,
    )
    market_validation_report_path = export_market_pid_validation_report(market_snapshot, output_dir)
    replay_validation_report_path = export_replay_validation_report(batch_summary, output_dir)
    export_seconds = perf_counter() - started_at

    submit_zip = None
    if enable_submit_zip:
        _emit_progress(progress_callback, 98.0, "building submit.zip")
        started_at = perf_counter()
        submit_zip = build_submit_zip(output_dir)
        export_seconds += perf_counter() - started_at

    performance_summary = build_performance_summary(
        profile_enabled=profile_enabled,
        total_seconds=perf_counter() - batch_started_at,
        sample_build_seconds=sample_build_seconds,
        pattern_seconds=pattern_seconds,
        capital_seconds=capital_seconds,
        market_seconds=market_seconds,
        export_seconds=export_seconds,
        sample_timings=sample_timings,
        processed_samples=len(samples),
        imputed_predict_count=len(imputed_predict_results),
        skipped_incomplete_samples=len(incomplete_stock_dirs),
        round_seconds=_round_seconds,
    )

    result = build_batch_result(
        trade_date=trade_date,
        sample_count=len(samples),
        pattern_results=pattern_results,
        predict_results=predict_results,
        market_snapshot=market_snapshot,
        market_snapshot_path=market_snapshot_path,
        market_report_path=market_report_path,
        market_validation_report_path=market_validation_report_path,
        replay_validation_report_path=replay_validation_report_path,
        diagnostics_json_path=diagnostics_json_path,
        distribution_csv_path=distribution_csv_path,
        submit_zip=submit_zip,
        warnings=warnings,
        imputed_output_count=len(imputed_predict_results),
        stock_offset=stock_offset,
        stock_limit=stock_limit,
        stock_list_file=stock_list_file,
        stock_universe_size=len(stock_universe) if stock_universe is not None else None,
        missing_symbols=missing_symbols,
        incomplete_stock_dirs=incomplete_stock_dirs,
        performance_summary=performance_summary,
    )
    _emit_progress(progress_callback, 100.0, "batch analysis finished")
    return result

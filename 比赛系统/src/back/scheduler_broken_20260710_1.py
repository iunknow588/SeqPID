from __future__ import annotations

import csv
from bisect import bisect_right
from pathlib import Path
from statistics import median
from time import perf_counter

from capital_model import predict_capitals
import capital_rule_engine
import data_loader
from exporter import (
    build_submit_zip,
    export_batch_diagnostics,
    export_market_pid_validation_report,
    export_market_pid_snapshot,
    export_market_regime_report,
    export_pattern_reco,
    export_predict_result,
    export_replay_validation_report,
)
from market_pid import attach_market_relative_metrics, estimate_market_pid
from order_lifecycle import OrderLifecycleResolver, is_cancel_trade, time_value_to_seconds
from pattern_model import predict_pattern
from pid_decomposer import PIDDecomposer
from schemas import DailySample, MarketPidSnapshot, PatternResult, PredictResult
import windowing


def _iter_stock_dirs(input_dir: Path) -> list[Path]:
    return data_loader.iter_stock_dirs(input_dir)


def _load_stock_universe(stock_list_file: str | Path | None) -> tuple[list[str] | None, set[str] | None]:
    return data_loader.load_stock_universe(stock_list_file)


def _looks_like_stock_symbol(value: str) -> bool:
    return data_loader.looks_like_stock_symbol(value)


def _is_stock_dir(input_dir: Path) -> bool:
    return data_loader.is_stock_dir(input_dir)


def _find_reference_feature_file(input_dir: Path) -> Path | None:
    return data_loader.find_reference_feature_file(input_dir)


def _filter_stock_dirs(stock_dirs: list[Path], stock_universe: set[str] | None) -> list[Path]:
    return data_loader.filter_stock_dirs(stock_dirs, stock_universe)


def _get_missing_required_files(stock_dir: Path) -> list[str]:
    # Compatibility literals for older tests/docs: stock_dir / "闂備緡鍋呴崝妤呮偡椤忓牆绠ｉ柟閭︿簼閸?csv"; stock_dir / "闂備緡鍋呴崝妤呮偡椤忓懏鍙忛柡鍐ｅ亾濠?csv"; stock_dir / "闁荤偞绋戦張顒勫磿?csv"
    return data_loader.get_missing_required_files(stock_dir)


def _format_incomplete_stock_warning(incomplete_stock_dirs: dict[str, list[str]]) -> str:
    details = [
        f"{symbol}({','.join(missing_files)})"
        for symbol, missing_files in sorted(incomplete_stock_dirs.items())
    ]
    return "Skipped incomplete stock dirs: " + "; ".join(details)


def _round_seconds(value: float) -> float:
    return round(value, 6)


def _open_csv_reader(path: Path) -> csv.DictReader:
    reader, fh = data_loader.open_csv_reader(path)
    setattr(reader, "_source_file", fh)
    return reader


def _to_float(value: object, default: float = 0.0) -> float:
    return windowing.to_float(value, default)


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
    return windowing.time_to_window_id(raw_time)


def _trade_side_sign(row: dict) -> int:
    raw = _pick_text(row, ["side", "bs_flag", "trade_side", "order_side"]).upper()
    if raw in {"B", "BUY", "1"}:
        return 1
    if raw in {"S", "SELL", "2"}:
        return -1
    return 0


def _row_time_value(row: dict) -> int:
    return int(_to_float(row.get("timestamp_ms") or row.get("time"), 0.0))


def _build_quote_series(quote_rows: list[dict]) -> tuple[list[int], list[dict]]:
    series: list[tuple[int, dict]] = []
    for row in quote_rows:
        timestamp = _row_time_value(row)
        if timestamp <= 0:
            continue
        bid_px_1 = _scaled_price(row.get("闂佹眹鍨归崢鏍箯鏉堛劎顩?") or row.get("bid_px_1") or row.get("bid1"))
        ask_px_1 = _scaled_price(row.get("闂佹眹鍨归崯鍨暦閻樺磭顩?") or row.get("ask_px_1") or row.get("ask1"))
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


def _build_pid_rows_from_trades(
    trade_rows: list[dict],
    config: dict,
    quote_rows: list[dict] | None = None,
    order_rows: list[dict] | None = None,
) -> list[dict]:
    species_rules = config.get("species_rules", {})
    large_threshold = float(species_rules.get("large_order_amount_threshold", 500_000.0))
    active_fallback_to_side = bool(species_rules.get("active_fallback_to_side", True))
    quote_times, quote_values = _build_quote_series(quote_rows or [])
    lifecycle_resolver = OrderLifecycleResolver(order_rows, trade_rows)
    buckets = windowing.initialize_pid_buckets()

    for row in trade_rows:
        if is_cancel_trade(row):
            continue
        timestamp = _row_time_value(row)
        window_id = _time_to_window_id(timestamp)
        if window_id is None:
            continue
        raw_trade_price = row.get("闂佺懓鐡ㄩ崝鎺戭潩閿旂晫顩烽梺鍨儑婢?) or row.get("price")
        price = _scaled_price(raw_trade_price)
        volume = _to_float(row.get("闂佺懓鐡ㄩ崝鎺戭潩閿曞倸鏋佸ù鍏兼綑濞?) or row.get("volume"), 0.0)
        explicit_amount = _to_float(row.get("闂佺懓鐡ㄩ崝鎺戭潩閿曞倹鐓傞柟杈惧瘜閺?) or row.get("amount"), 0.0)
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

        lifecycle_result = lifecycle_resolver.lookup_order_age_minutes(
            row,
            trade_time_seconds=time_value_to_seconds(timestamp),
            active_sign=active_sign,
            side_sign=side_sign,
            trade_price=raw_trade_price,
            trade_volume=volume,
        )
        order_age_minutes = lifecycle_result.order_age_minutes
        if order_age_minutes is None:
            bucket["order_age_missing_count"] += 1
        else:
            bucket["order_age_recovered_count"] += 1
        if lifecycle_result.recovery_method == "direct_order_id":
            bucket["order_age_direct_count"] += 1
        elif lifecycle_result.recovery_method == "fifo_price_queue":
            bucket["order_age_fifo_count"] += 1
        else:
            bucket["order_age_unresolved_count"] += 1

        signed_amount = side_sign * amount
        if side_sign > 0:
            bucket["signal_deal_buy_amount"] += amount
        elif side_sign < 0:
            bucket["signal_deal_sell_amount"] += amount

        is_active = active_sign != 0
        is_large_active = is_active and amount >= large_threshold
        rule_signed_amount = active_sign * amount if is_large_active else signed_amount
        rule_side = "buy" if rule_signed_amount > 0 else "sell" if rule_signed_amount < 0 else "unknown"
        rule_event = capital_rule_engine.build_rule_event(
            event_time=str(timestamp),
            signed_amount=rule_signed_amount,
            side=rule_side,
            scene="continuous",
            is_active=is_active,
            is_large=is_large_active,
            order_age_minutes=order_age_minutes,
            active_fallback_to_side=active_fallback_to_side,
        )
        capital_rule_engine.apply_event_to_legacy_bucket(bucket, rule_event)

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
    deal_amount = sum(_pick(row, ["deal_amount", "amount", "闂佺懓鐡ㄩ崝鎺戭潩閿旀枻绱?]) for row in rows)
    buy_amount = sum(_pick(row, ["signal_deal_buy_amount", "buy_amount", "婵炴垶鎹侀褎鎱ㄩ埡鍌溾枙闁绘鐗嗛悘鍥瑰┃鍨偓婵嬄?]) for row in rows)
    sell_amount = sum(_pick(row, ["signal_deal_sell_amount", "sell_amount", "婵炴垶鎹侀褎鎱ㄩ埡鍛闁哄秲鍔岄悘鍥瑰┃鍨偓婵嬄?]) for row in rows)
    cancel_ratio_values = [_pick(row, ["cb_cancel_order_ratio", "cancel_ratio", "闂侀€涘嫎閸婃洖鐣烽悢鍏煎仢?]) for row in rows]
    burst_values = [_pick(row, ["rs_burst_ratio", "burst_ratio", "闂佺粯鐗曞Λ妤勩亹閸屾稒鍎?]) for row in rows]
    impact_values = [_pick(row, ["pi_max_price_impact_pct", "price_impact", "婵炲濞€閺€閬嶆偋閹间礁绀冮柟缁樺笒濮?]) for row in rows]
    bid_support_values = [_pick(row, ["obp_at_best_bid_ratio", "best_bid_ratio", "婵炴垶妫冮。锔剧博閹绢喖绠伴柛灞捐壘缁€瀣煕濡ゅ啫校闁?]) for row in rows]
    ask_pressure_values = [_pick(row, ["obp_at_best_ask_ratio", "best_ask_ratio", "闂佸憡顨嗛悧鏃傜博閹绢喖绠伴柛灞捐壘缁€瀣煕濡ゅ啫校闁?]) for row in rows]

    tail_rows = [row for row in rows if str(row.get("window_id", "")).isdigit() and int(row["window_id"]) >= 42]
    tail_amount = sum(_pick(row, ["deal_amount", "amount", "闂佺懓鐡ㄩ崝鎺戭潩閿旀枻绱?]) for row in tail_rows)
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
            row_date = str(row.get("闂佺厧顨庢禍鐐哄礉瑜斿?) or row.get("date") or row.get("trade_date") or "")
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
    return data_loader.read_csv_rows(path, trade_date)


def _build_daily_sample_from_stock_dir(stock_dir: Path, trade_date: str, config: dict | None = None) -> DailySample | None:
    config = config or {}
    trade_path = stock_dir / "闂侇偅鍔楅悷顏堝箣閹邦亝鍞?csv"
    order_path = stock_dir / "闂侇偅鍔楅悷顏呮叏閺冣偓婢?csv"
    quote_path = stock_dir / "閻炴稑鏈崕?csv"
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
    total_volume = 0.0
    bucket_counts: dict[int, int] = {}
    bucket_amounts: dict[int, float] = {}
    for row in trade_rows:
        price = _scaled_price(row.get("闁瑰瓨鍔掑锔界闁垮澹?))
        volume = _to_float(row.get("闁瑰瓨鍔掑锕傚极娴兼潙娅?), 0.0)
        amount = price * volume
        timestamp = int(_to_float(row.get("闁哄啫鐖煎Λ?), 0.0))
        trade_amounts.append(amount)
        total_volume += volume
        trade_times.append(timestamp)
        hhmm = timestamp // 100000
        bucket = (hhmm // 5) if hhmm > 0 else 0
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        bucket_amounts[bucket] = bucket_amounts.get(bucket, 0.0) + amount

    total_trade_amount = sum(trade_amounts)
    tail_trade_amount = sum(amount for amount, t in zip(trade_amounts, trade_times) if t >= 143000000)
    avg_trade_size = total_trade_amount / len(trade_rows) if trade_rows else 0.0

    last_quote = quote_rows[-1] if quote_rows else {}
    prev_close = _scaled_price(last_quote.get("闁告挸绉甸弫褰掓儎?"))
    open_price = 0.0
    close_price = 0.0
    price_impact = 0.0
    up_count = int(_to_float(last_quote.get("濞戞挸锕ョ€规岸宕担渚綒闁?"), 0.0))
    down_count = int(_to_float(last_quote.get("濞戞挸顑堢粚濂稿传娴ｄ警娼氶柡?"), 0.0))
    flat_count = int(_to_float(last_quote.get("闁归晲绀侀柦鈺呭传娴ｄ警娼氶柡?"), 0.0))

    high_price = 0.0
    low_price = 0.0
    last15_prices: list[float] = []
    for row in quote_rows:
        row_close = _scaled_price(row.get("闁瑰瓨鍔掑锔界?"))
        if row_close > 0:
            close_price = row_close
        row_open = _scaled_price(row.get("鐎殿喒鍋撻柣鈺偯奸悳?))
        if open_price <= 0 and row_open > 0:
            open_price = row_open
        row_high = _scaled_price(row.get("闁哄牃鍋撳Δ鍌浢奸悳?))
        if row_high > 0:
            high_price = max(high_price, row_high)
        row_low = _scaled_price(row.get("闁哄牃鍋撳ù锝呯凹閻?))
        if row_low > 0:
            low_price = row_low if low_price <= 0 else min(low_price, row_low)
        if int(_to_float(row.get("闁哄啫鐖煎Λ?), 0.0)) >= 144500000 and row_close > 0:
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

    ask_vol = sum(_to_float(last_quote.get(f"闁汇垹鍟垮畷鐘绘煂瀵攣i}"), 0.0) for i in range(1, 11))
    bid_vol = sum(_to_float(last_quote.get(f"闁汇垹鍘栭幏閬嶆煂瀵攣i}"), 0.0) for i in range(1, 11))
    bid_support = bid_vol / (bid_vol + ask_vol) if (bid_vol + ask_vol) > 0 else 0.0
    ask_pressure = ask_vol / (bid_vol + ask_vol) if (bid_vol + ask_vol) > 0 else 0.0

    burst_ratio = 0.0
    if bucket_amounts:
        total_bucket_amount = sum(bucket_amounts.values())
        if total_bucket_amount > 0:
            burst_ratio = max(bucket_amounts.values()) / total_bucket_amount

    cancel_ratio = 0.0
    if order_rows:
        cancel_like = [row for row in order_rows if str(row.get("濠殿喗姊规晶顓犵尵鐠囪尙鈧?, "")).strip() not in {"", "0"}]
        cancel_ratio = len(cancel_like) / len(order_rows)
    buy_orders = sum(1 for row in order_rows if str(row.get("濠殿喗姊规晶顓熺閿濆洨鍨?, "")).strip().upper() == "B")
    sell_orders = sum(1 for row in order_rows if str(row.get("濠殿喗姊规晶顓熺閿濆洨鍨?, "")).strip().upper() == "S")
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
    raw_hot_money_amount = sum(float(row.get("CH_rule_t", row["signed_large_active_amount"])) for row in pid_rows)
    raw_quant_amount = sum(float(row.get("Q_rule_t", 0.0)) for row in pid_rows)
    raw_retail_seed_amount = sum(float(row.get("R_seed_t", 0.0)) for row in pid_rows)
    raw_mix_qr_amount = sum(float(row.get("signed_mix_qr_amount", raw_quant_amount + raw_retail_seed_amount)) for row in pid_rows)
    raw_active_inferred_count = sum(int(row["active_inferred_count"]) for row in pid_rows)
    raw_side_fallback_count = sum(int(row["side_fallback_count"]) for row in pid_rows)
    raw_unknown_side_amount = sum(float(row["unknown_side_amount"]) for row in pid_rows)
    raw_order_age_recovered_count = sum(int(row.get("order_age_recovered_count", 0)) for row in pid_rows)
    raw_order_age_missing_count = sum(int(row.get("order_age_missing_count", 0)) for row in pid_rows)
    raw_order_age_direct_count = sum(int(row.get("order_age_direct_count", 0)) for row in pid_rows)
    raw_order_age_fifo_count = sum(int(row.get("order_age_fifo_count", 0)) for row in pid_rows)
    raw_order_age_unresolved_count = sum(int(row.get("order_age_unresolved_count", 0)) for row in pid_rows)
    raw_order_age_total_count = raw_order_age_recovered_count + raw_order_age_missing_count

    summary = {
        "deal_amount": total_trade_amount,
        "buy_amount": max(net_direction, 0.0) * total_trade_amount,
        "sell_amount": max(-net_direction, 0.0) * total_trade_amount,
        "raw_hot_money_amount": raw_hot_money_amount,
        "raw_quant_amount": raw_quant_amount,
        "raw_retail_seed_amount": raw_retail_seed_amount,
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
        "raw_order_age_recovery_ratio": raw_order_age_recovered_count / raw_order_age_total_count
        if raw_order_age_total_count > 0
        else 0.0,
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


def _build_order_lifecycle_summary(samples: list[DailySample]) -> dict:
    recovered = 0
    missing = 0
    direct = 0
    fifo = 0
    unresolved = 0
    for sample in samples:
        summary = sample.feature_summary or {}
        recovered += int(summary.get("raw_order_age_recovered_count", 0) or 0)
        missing += int(summary.get("raw_order_age_missing_count", 0) or 0)
        direct += int(summary.get("raw_order_age_direct_count", 0) or 0)
        fifo += int(summary.get("raw_order_age_fifo_count", 0) or 0)
        unresolved += int(summary.get("raw_order_age_unresolved_count", 0) or 0)
    total = recovered + missing
    return {
        "order_age_total_count": total,
        "order_age_recovered_count": recovered,
        "order_age_missing_count": missing,
        "order_age_direct_count": direct,
        "order_age_fifo_count": fifo,
        "order_age_unresolved_count": unresolved,
        "order_age_recovery_ratio": recovered / total if total else 0.0,
    }


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
        pid_result = pid_decomposer.decompose_sample(default_sample)
        pattern_result = predict_pattern(default_sample, config, label_dict, pid_result)
        pattern_result.pattern_explanation = f"{pattern_result.pattern_explanation} 缂傚倸鍊搁幖顐﹀Φ閹达箑鍌ㄩ柣鏂款殠濞兼鏌℃担鍝勵暭鐎规挷绶氶弫宥囦沪閹呮▎閻熸粎澧楅幐璇参涢埡鍐╂殰闁稿本纰嶇花姘槈閹垮啫骞掔紓宥呮噹椤繈寮堕幋锔藉皺闁荤偞绋忛崕閬嶅矗韫囨稑绀嗛柕鍫濇閻掍粙鏌?
        pattern_result.prototype_id = f"imputed::{pattern_result.prototype_id}"

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

    pid_decomposer = PIDDecomposer(config)
    pid_results = {}
    started_at = perf_counter()
    for sample in samples:
        pid_results[sample.stock_code] = pid_decomposer.decompose_sample(sample)
    pid_seconds = perf_counter() - started_at

    started_at = perf_counter()
    pattern_results: list[PatternResult] = [
        predict_pattern(sample, config, label_dict, pid_results.get(sample.stock_code)) for sample in samples
    ]
    pattern_seconds = perf_counter() - started_at

    started_at = perf_counter()
    predict_results: list[PredictResult] = []
    for sample in samples:
        pid_result = pid_results[sample.stock_code]
        predict_results.extend(predict_capitals(sample, config, label_dict, pid_result))
    capital_seconds = pid_seconds + (perf_counter() - started_at)
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

    order_lifecycle_summary = _build_order_lifecycle_summary(samples)
    batch_result = {
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
        "order_lifecycle_summary": order_lifecycle_summary,
    }
    market_validation_report_path = export_market_pid_validation_report(market_snapshot, output_dir)
    replay_validation_report_path = export_replay_validation_report(batch_result, output_dir)
    batch_result["market_validation_report_path"] = market_validation_report_path
    batch_result["replay_validation_report_path"] = replay_validation_report_path
    return batch_result

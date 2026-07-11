from __future__ import annotations


def to_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def time_to_window_id(raw_time: object) -> int | None:
    value = int(to_float(raw_time, 0.0))
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


def initialize_pid_buckets(window_count: int = 48) -> list[dict]:
    return [
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
            "CH_rule_t": 0.0,
            "Q_rule_t": 0.0,
            "R_seed_t": 0.0,
            "buy_ch_anchor_t": 0.0,
            "sell_ch_anchor_t": 0.0,
            "buy_q_anchor_t": 0.0,
            "sell_q_anchor_t": 0.0,
            "buy_retail_seed_t": 0.0,
            "sell_retail_seed_t": 0.0,
            "low_fallback_count": 0,
            "event_count": 0,
            "window_open_price": 0.0,
            "window_close_price": 0.0,
            "window_trade_count": 0,
            "active_inferred_count": 0,
            "side_fallback_count": 0,
            "order_age_recovered_count": 0,
            "order_age_missing_count": 0,
            "order_age_direct_count": 0,
            "order_age_fifo_count": 0,
            "order_age_unresolved_count": 0,
        }
        for index in range(window_count)
    ]

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque


@dataclass
class OrderState:
    order_id: str
    side: str
    price_key: str
    order_time_seconds: int
    remaining_volume: float


@dataclass
class OrderAgeResult:
    order_age_minutes: float | None
    lifecycle_recovered: bool
    recovery_method: str
    recovery_confidence: str


TIME_FIELDS = ("时间", "order_time", "time", "timestamp_ms")
ORDER_ID_FIELDS = ("交易所委托号", "order_id", "exchange_order_id")
ORDER_SIDE_FIELDS = ("委托代码", "side")
ORDER_PRICE_FIELDS = ("委托价格", "price")
ORDER_VOLUME_FIELDS = ("委托数量", "volume")
ORDER_TYPE_FIELDS = ("委托类型", "order_type")
TRADE_PRICE_FIELDS = ("成交价格", "price")
TRADE_VOLUME_FIELDS = ("成交数量", "volume")
TRADE_TYPE_FIELDS = ("成交代码", "trade_type", "exec_type")
SELL_ORDER_ID_FIELDS = ("叫卖序号", "ask_order_id", "sell_order_id")
BUY_ORDER_ID_FIELDS = ("叫买序号", "bid_order_id", "buy_order_id")


def to_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def time_value_to_seconds(raw_time: object) -> int | None:
    value = int(to_float(raw_time, 0.0))
    if value <= 0:
        return None
    hhmmss = value // 1000 if value > 235959 else value
    hh = hhmmss // 10000
    mm = (hhmmss % 10000) // 100
    ss = hhmmss % 100
    if hh > 23 or mm > 59 or ss > 59:
        return None
    return hh * 3600 + mm * 60 + ss


def price_key(value: object) -> str:
    numeric = to_float(value, 0.0)
    if numeric == 0.0:
        return ""
    if abs(numeric) > 1000:
        numeric /= 10000.0
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:.6f}".rstrip("0").rstrip(".")


def normalize_side(value: object) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"B", "BUY", "1"}:
        return "buy"
    if raw in {"S", "SELL", "2"}:
        return "sell"
    return ""


def normalize_order_type(value: object) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"D", "C", "CANCEL", "DELETE", "撤单"}:
        return "delete"
    if raw in {"A", "1", "2", "U", "ADD", ""}:
        return "add"
    return "add"


def pick_value(row: dict, names: tuple[str, ...]) -> object:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def pick_text(row: dict, names: tuple[str, ...]) -> str:
    for name in names:
        value = str(row.get(name, "")).strip()
        if value and value not in {"0", "0.0"}:
            return value
    return ""


def trade_passive_side(active_sign: int, side_sign: int) -> str:
    if active_sign > 0 or (active_sign == 0 and side_sign > 0):
        return "sell"
    if active_sign < 0 or (active_sign == 0 and side_sign < 0):
        return "buy"
    return ""


def trade_passive_order_id(row: dict, passive_side: str) -> str:
    if passive_side == "sell":
        return pick_text(row, SELL_ORDER_ID_FIELDS)
    if passive_side == "buy":
        return pick_text(row, BUY_ORDER_ID_FIELDS)
    return ""


def is_cancel_trade(row: dict) -> bool:
    return normalize_order_type(pick_value(row, TRADE_TYPE_FIELDS)) == "delete"


class OrderLifecycleResolver:
    def __init__(self, order_rows: list[dict] | None, trade_rows: list[dict] | None = None):
        events = self._build_order_events(order_rows or [])
        events.extend(self._build_trade_cancel_events(trade_rows or []))
        self.events = sorted(events, key=lambda item: (item["time_seconds"], item["event_order"]))
        self.event_index = 0
        self.orders_by_id: dict[str, OrderState] = {}
        self.queues: dict[tuple[str, str], Deque[OrderState]] = {}

    def lookup_order_age_minutes(
        self,
        trade_row: dict,
        *,
        trade_time_seconds: int | None,
        active_sign: int,
        side_sign: int,
        trade_price: object,
        trade_volume: float,
    ) -> OrderAgeResult:
        if trade_time_seconds is None:
            return OrderAgeResult(None, False, "missing_trade_time", "low")

        self._advance_to(trade_time_seconds)
        passive_side = trade_passive_side(active_sign, side_sign)
        if not passive_side:
            return OrderAgeResult(None, False, "passive_side_unresolved", "low")

        passive_order_id = trade_passive_order_id(trade_row, passive_side)
        order = self.orders_by_id.get(passive_order_id) if passive_order_id else None
        if order is not None:
            self._consume_order(order, trade_volume)
            return OrderAgeResult(
                (trade_time_seconds - order.order_time_seconds) / 60.0,
                True,
                "direct_order_id",
                "high",
            )

        order = self._consume_fifo(passive_side, price_key(trade_price), trade_volume)
        if order is not None:
            return OrderAgeResult(
                (trade_time_seconds - order.order_time_seconds) / 60.0,
                True,
                "fifo_price_queue",
                "medium",
            )

        return OrderAgeResult(None, False, "order_lifecycle_unresolved", "low")

    def _build_order_events(self, order_rows: list[dict]) -> list[dict]:
        events: list[dict] = []
        for row in order_rows:
            time_seconds = time_value_to_seconds(pick_value(row, TIME_FIELDS))
            if time_seconds is None:
                continue
            order_id = pick_text(row, ORDER_ID_FIELDS)
            side = normalize_side(pick_value(row, ORDER_SIDE_FIELDS))
            pkey = price_key(pick_value(row, ORDER_PRICE_FIELDS))
            volume = to_float(pick_value(row, ORDER_VOLUME_FIELDS), 0.0)
            event_type = normalize_order_type(pick_value(row, ORDER_TYPE_FIELDS))
            if volume <= 0:
                continue
            if event_type == "add" and (not side or not pkey):
                continue
            if event_type == "delete" and not (order_id or (side and pkey)):
                continue
            events.append(
                {
                    "time_seconds": time_seconds,
                    "event_order": 0,
                    "order_id": order_id,
                    "side": side,
                    "price_key": pkey,
                    "volume": volume,
                    "event_type": event_type,
                }
            )
        return events

    def _build_trade_cancel_events(self, trade_rows: list[dict]) -> list[dict]:
        events: list[dict] = []
        for row in trade_rows:
            if not is_cancel_trade(row):
                continue
            time_seconds = time_value_to_seconds(pick_value(row, TIME_FIELDS))
            if time_seconds is None:
                continue
            buy_order_id = pick_text(row, BUY_ORDER_ID_FIELDS)
            sell_order_id = pick_text(row, SELL_ORDER_ID_FIELDS)
            if buy_order_id:
                order_id = buy_order_id
                side = "buy"
            elif sell_order_id:
                order_id = sell_order_id
                side = "sell"
            else:
                order_id = ""
                side = normalize_side(pick_value(row, ORDER_SIDE_FIELDS))
            pkey = price_key(pick_value(row, TRADE_PRICE_FIELDS))
            volume = to_float(pick_value(row, TRADE_VOLUME_FIELDS), 0.0)
            if volume <= 0 or not (order_id or (side and pkey)):
                continue
            events.append(
                {
                    "time_seconds": time_seconds,
                    "event_order": 1,
                    "order_id": order_id,
                    "side": side,
                    "price_key": pkey,
                    "volume": volume,
                    "event_type": "delete",
                }
            )
        return events

    def _advance_to(self, trade_time_seconds: int) -> None:
        while self.event_index < len(self.events) and self.events[self.event_index]["time_seconds"] <= trade_time_seconds:
            event = self.events[self.event_index]
            self.event_index += 1
            if event["event_type"] == "delete":
                self._delete_event(event)
            else:
                self._add_event(event)

    def _add_event(self, event: dict) -> None:
        order = OrderState(
            order_id=event["order_id"],
            side=event["side"],
            price_key=event["price_key"],
            order_time_seconds=event["time_seconds"],
            remaining_volume=event["volume"],
        )
        if order.order_id:
            self.orders_by_id[order.order_id] = order
        self.queues.setdefault((order.side, order.price_key), deque()).append(order)

    def _delete_event(self, event: dict) -> None:
        order = self.orders_by_id.get(event["order_id"]) if event["order_id"] else None
        if order is not None:
            self._consume_order(order, event["volume"])
            return
        if event["side"] and event["price_key"]:
            self._consume_fifo(event["side"], event["price_key"], event["volume"])

    def _consume_order(self, order: OrderState, volume: float) -> None:
        order.remaining_volume -= max(volume, 0.0)
        if order.remaining_volume <= 0 and order.order_id:
            self.orders_by_id.pop(order.order_id, None)

    def _consume_fifo(self, side: str, pkey: str, volume: float) -> OrderState | None:
        queue = self.queues.get((side, pkey))
        if not queue:
            return None
        remaining = max(volume, 0.0)
        first_consumed: OrderState | None = None
        while queue and remaining > 0:
            order = queue[0]
            if order.remaining_volume <= 0:
                queue.popleft()
                continue
            if first_consumed is None:
                first_consumed = order
            used = min(order.remaining_volume, remaining)
            order.remaining_volume -= used
            remaining -= used
            if order.remaining_volume <= 0:
                queue.popleft()
                if order.order_id:
                    self.orders_by_id.pop(order.order_id, None)
        return first_consumed

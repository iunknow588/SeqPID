from __future__ import annotations

from schemas import CapitalBehaviorEvent, CapitalRuleWindowFeature


CAPITAL_HOT_MONEY = "hot_money"
CAPITAL_QUANT = "quant"
CAPITAL_RETAIL = "retail"


def confidence_level(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.60:
        return "medium"
    if score >= 0.40:
        return "low"
    return "low_fallback"


def build_rule_event(
    *,
    event_time: str,
    signed_amount: float,
    side: str,
    scene: str,
    is_active: bool,
    is_large: bool,
    order_age_minutes: float | None = None,
    active_fallback_to_side: bool = True,
) -> CapitalBehaviorEvent:
    amount = abs(float(signed_amount or 0.0))
    reason_codes: list[str] = []
    fallback_reason: str | None = None

    if is_active and is_large:
        capital_type = CAPITAL_HOT_MONEY
        score = 0.82
        reason_codes.append("active_large_price_shaping")
    elif not is_active and order_age_minutes is not None and order_age_minutes > 5.0:
        capital_type = CAPITAL_RETAIL
        score = 0.62
        reason_codes.append("passive_survival_gt_5m")
    elif is_active or active_fallback_to_side:
        capital_type = CAPITAL_QUANT
        score = 0.55 if order_age_minutes is None else 0.64
        reason_codes.append("quant_rule_or_low_conf_fallback")
        if order_age_minutes is None:
            fallback_reason = "order_age_missing"
    else:
        capital_type = CAPITAL_QUANT
        score = 0.35
        fallback_reason = "active_side_unresolved"
        reason_codes.append("weak_quant_fallback")

    return CapitalBehaviorEvent(
        event_time=str(event_time),
        order_time=None,
        side=side,
        scene=scene,
        signed_amount=float(signed_amount or 0.0),
        order_amount=amount,
        order_age_minutes=order_age_minutes,
        price_aggressive_score=1.0 if is_active else 0.0,
        direction_reliability=1.0 if side in {"buy", "sell"} else 0.4,
        capital_type_rule=capital_type,
        confidence_score=score,
        confidence_level=confidence_level(score),
        fallback_reason=fallback_reason,
        reason_codes=reason_codes,
    )


def initialize_rule_window_feature(window_id: str | int) -> CapitalRuleWindowFeature:
    return CapitalRuleWindowFeature(window_id=str(window_id))


def apply_event_to_window(feature: CapitalRuleWindowFeature, event: CapitalBehaviorEvent) -> None:
    amount = float(event.signed_amount or 0.0)
    is_buy = amount > 0
    if event.capital_type_rule == CAPITAL_HOT_MONEY:
        feature.CH_rule_t += amount
        if is_buy:
            feature.buy_ch_anchor_t += amount
        else:
            feature.sell_ch_anchor_t += amount
    elif event.capital_type_rule == CAPITAL_RETAIL:
        feature.R_seed_t += amount
        if is_buy:
            feature.buy_retail_seed_t += amount
        else:
            feature.sell_retail_seed_t += amount
    else:
        feature.Q_rule_t += amount
        if is_buy:
            feature.buy_q_anchor_t += amount
        else:
            feature.sell_q_anchor_t += amount

    feature.event_count += 1
    if event.confidence_level == "low_fallback":
        feature.low_fallback_count += 1


def apply_event_to_legacy_bucket(bucket: dict, event: CapitalBehaviorEvent) -> None:
    apply_event_to_window(_BucketFeatureAdapter(bucket), event)
    amount = abs(float(event.signed_amount or 0.0))
    if event.capital_type_rule == CAPITAL_HOT_MONEY:
        bucket["signed_large_active_amount"] += event.signed_amount
        if event.signed_amount > 0:
            bucket["large_active_buy_amount"] += amount
        else:
            bucket["large_active_sell_amount"] += amount
    elif event.capital_type_rule == CAPITAL_RETAIL:
        bucket["signed_mix_qr_amount"] += event.signed_amount
        if event.signed_amount > 0:
            bucket["small_passive_buy_amount"] += amount
        else:
            bucket["small_passive_sell_amount"] += amount
    else:
        bucket["signed_mix_qr_amount"] += event.signed_amount
        if event.signed_amount > 0:
            bucket["small_passive_buy_amount"] += amount
        elif event.signed_amount < 0:
            bucket["small_passive_sell_amount"] += amount
        else:
            bucket["unknown_side_amount"] += amount


class _BucketFeatureAdapter(CapitalRuleWindowFeature):
    def __init__(self, bucket: dict):
        self._bucket = bucket

    def __getattribute__(self, name: str):
        if name == "_bucket":
            return object.__getattribute__(self, name)
        bucket = object.__getattribute__(self, "_bucket")
        if name in bucket:
            return bucket[name]
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value):
        if name == "_bucket":
            object.__setattr__(self, name, value)
        else:
            self._bucket[name] = value

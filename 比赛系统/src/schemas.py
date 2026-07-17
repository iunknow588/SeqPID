from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SchemaProbeFileResult:
    path: str
    exists: bool
    suffix: str
    size_bytes: int
    sample_header: list[str] = field(default_factory=list)
    row_count_estimate: int | None = None
    required_fields_present: list[str] = field(default_factory=list)
    missing_required_fields: list[str] = field(default_factory=list)


@dataclass
class SchemaProbeResult:
    trade_date: str
    input_dir: str
    files: dict[str, SchemaProbeFileResult]
    summary: dict


@dataclass
class PatternResult:
    stock_code: str
    transaction_date: str
    pattern_type: str
    pattern_explanation: str
    pattern_score: float = 0.0
    prototype_id: str = ""
    pattern_primary_score: float = 0.0
    pattern_second_score: float = 0.0
    pattern_margin: float = 0.0
    pattern_source: str = ""
    pattern_pid_adjusted: bool = False


@dataclass
class PredictResult:
    stock_code: str
    transaction_date: str
    capital_type: str
    capital_intention: str
    capital_confidence: float = 0.0
    intention_confidence: float = 0.0
    debug_info: dict = field(default_factory=dict)


@dataclass
class DailySample:
    stock_code: str
    transaction_date: str
    rows: list[dict]
    feature_summary: dict
    quality_flags: dict = field(default_factory=dict)


@dataclass
class CapitalBehaviorEvent:
    event_time: str
    order_time: str | None
    side: str
    scene: str
    signed_amount: float
    order_amount: float
    order_age_minutes: float | None
    price_aggressive_score: float = 0.0
    sustain_score: float = 0.0
    follow_score: float = 0.0
    direction_reliability: float = 1.0
    capital_type_rule: str = "quant"
    confidence_score: float = 0.0
    confidence_level: str = "low_fallback"
    fallback_reason: str | None = None
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class CapitalRuleWindowFeature:
    window_id: str
    CH_rule_t: float = 0.0
    Q_rule_t: float = 0.0
    R_seed_t: float = 0.0
    buy_ch_anchor_t: float = 0.0
    sell_ch_anchor_t: float = 0.0
    buy_q_anchor_t: float = 0.0
    sell_q_anchor_t: float = 0.0
    buy_retail_seed_t: float = 0.0
    sell_retail_seed_t: float = 0.0
    low_fallback_count: int = 0
    event_count: int = 0


@dataclass
class StateFeature:
    stock_code: str
    transaction_date: str
    window_id: str
    CH_rule_t: float = 0.0
    Q_rule_t: float = 0.0
    R_seed_t: float = 0.0
    phi: float | None = None
    theta: float | None = None
    beta_ch: float | None = None
    beta_q: float | None = None
    beta_mix: float | None = None
    beta_retail: float | None = None
    c_p: float | None = None
    c_i: float | None = None
    c_d: float | None = None
    eps: float | None = None
    capital_ch: float | None = None
    capital_mix: float | None = None
    capital_q: float | None = None
    capital_retail: float | None = None
    capital_ch_rule_approx: float = 0.0
    capital_q_rule_approx: float = 0.0
    capital_retail_rule_approx: float = 0.0
    noise_ratio: float | None = None
    explain_ratio: float | None = None
    capital_anchor_error: float | None = None
    rule_error_q: float | None = None
    rule_error_retail: float | None = None
    mode_name: str = "rule_base"
    is_structural_output: bool = False


@dataclass
class MarketPidSnapshot:
    trade_date: str
    up_count: int
    down_count: int
    breadth_ratio: float
    breadth_balance: float
    p_mean: float
    p_median: float
    p_std: float
    i_mean: float
    i_median: float
    i_std: float
    d_mean: float
    d_median: float
    d_std: float
    market_regime: str
    diagnostics: dict = field(default_factory=dict)

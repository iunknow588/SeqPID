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

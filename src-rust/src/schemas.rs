use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Default)]
pub struct SchemaProbeFileResult {
    pub path: String,
    pub exists: bool,
    pub suffix: String,
    pub size_bytes: u64,
    pub sample_header: Vec<String>,
    pub row_count_estimate: Option<usize>,
    pub required_fields_present: Vec<String>,
    pub missing_required_fields: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct SchemaProbeResult {
    pub trade_date: String,
    pub input_dir: String,
    pub files: HashMap<String, SchemaProbeFileResult>,
    pub summary: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Default)]
#[allow(dead_code)]
pub struct PatternResult {
    pub stock_code: String,
    pub transaction_date: String,
    pub pattern_type: String,
    pub pattern_explanation: String,
    pub pattern_score: f64,
    pub prototype_id: String,
}

#[derive(Debug, Clone, Default)]
#[allow(dead_code)]
pub struct PredictResult {
    pub stock_code: String,
    pub transaction_date: String,
    pub capital_type: String,
    pub capital_intention: String,
    pub capital_confidence: f64,
    pub intention_confidence: f64,
    pub debug_info: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct DailySample {
    pub stock_code: String,
    pub transaction_date: String,
    pub rows: Vec<HashMap<String, String>>,
    pub feature_summary: HashMap<String, f64>,
    pub quality_flags: HashMap<String, bool>,
}

#[derive(Debug, Clone, Default)]
#[allow(dead_code)]
pub struct StateFeature {
    pub stock_code: String,
    pub transaction_date: String,
    pub window_id: String,
    pub ch_rule_t: f64,
    pub q_rule_t: f64,
    pub r_seed_t: f64,
    pub phi: Option<f64>,
    pub theta: Option<f64>,
    pub beta_ch: Option<f64>,
    pub beta_q: Option<f64>,
    pub beta_mix: Option<f64>,
    pub beta_retail: Option<f64>,
    pub c_p: Option<f64>,
    pub c_i: Option<f64>,
    pub c_d: Option<f64>,
    pub eps: Option<f64>,
    pub capital_ch: Option<f64>,
    pub capital_mix: Option<f64>,
    pub capital_q: Option<f64>,
    pub capital_retail: Option<f64>,
    pub capital_ch_rule_approx: f64,
    pub capital_q_rule_approx: f64,
    pub capital_retail_rule_approx: f64,
    pub noise_ratio: Option<f64>,
    pub explain_ratio: Option<f64>,
    pub capital_anchor_error: Option<f64>,
    pub rule_error_q: Option<f64>,
    pub rule_error_retail: Option<f64>,
    pub mode_name: String,
    pub is_structural_output: bool,
}

#[derive(Debug, Clone, Default)]
pub struct DecompositionResult {
    pub stock_code: String,
    pub transaction_date: String,
    pub phi: Vec<f64>,
    pub theta: Vec<f64>,
    pub inertia: Vec<f64>,
    pub beta_ch: Vec<f64>,
    pub beta_q: Vec<f64>,
    pub beta_retail: Vec<f64>,
    pub beta_mix: Vec<f64>,
    pub damping: Vec<f64>,
    pub c_p: Vec<f64>,
    pub c_i: Vec<f64>,
    pub c_d: Vec<f64>,
    pub eps: Vec<f64>,
    pub capital_ch: Vec<f64>,
    pub capital_mix: Vec<f64>,
    pub capital_q: Vec<f64>,
    pub capital_retail: Vec<f64>,
    pub price_basis: Vec<f64>,
    pub u_ch_amount_ratio: Vec<f64>,
    pub u_q_amount_ratio: Vec<f64>,
    pub u_retail_amount_ratio: Vec<f64>,
    pub u_mix_amount_ratio: Vec<f64>,
    pub capital_anchor_error: Vec<f64>,
    pub delta_ch: Vec<f64>,
    pub delta_q: Vec<f64>,
    pub delta_retail: Vec<f64>,
    pub delta_ch_alloc: Vec<f64>,
    pub delta_q_alloc: Vec<f64>,
    pub delta_retail_alloc: Vec<f64>,
    pub delta_ch_display: Vec<f64>,
    pub delta_q_display: Vec<f64>,
    pub delta_retail_display: Vec<f64>,
    pub noise_ratio: Vec<f64>,
    pub explain_ratio: Vec<f64>,
    pub inertia_mean: f64,
    pub damping_mean: f64,
    pub hot_money_ratio: f64,
    pub quant_ratio: f64,
    pub retail_ratio: f64,
    pub dominant_type: String,
    pub dominant_intention: String,
    pub closure_error: f64,
    pub pid_closure_error: f64,
    pub alloc_closure_error: f64,
    pub display_closure_error: f64,
    pub capital_cp_identity_error: f64,
    pub capital_ci_identity_error: f64,
    pub capital_cd_identity_error: f64,
    pub capital_identity_error: f64,
    pub dominant_source: String,
    pub display_fields_used_for_dominant: bool,
    pub kf_converged: bool,
    pub mode: String,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, Default)]
pub struct MarketPidSnapshot {
    pub trade_date: String,
    pub up_count: i64,
    pub down_count: i64,
    pub breadth_ratio: f64,
    pub breadth_balance: f64,
    pub p_mean: f64,
    pub p_median: f64,
    pub p_std: f64,
    pub i_mean: f64,
    pub i_median: f64,
    pub i_std: f64,
    pub d_mean: f64,
    pub d_median: f64,
    pub d_std: f64,
    pub market_regime: String,
    pub diagnostics: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[allow(dead_code)]
pub struct BatchResult {
    pub trade_date: String,
    pub sample_count: usize,
    pub output_count: usize,
    pub stock_offset: Option<usize>,
    pub stock_limit: Option<usize>,
    pub stock_list_file: Option<String>,
    pub stock_universe_size: Option<usize>,
    pub warnings: Vec<String>,
    pub submit_zip: Option<String>,
    pub market_snapshot_path: Option<String>,
    pub market_report_path: Option<String>,
    pub diagnostics_json_path: Option<String>,
    pub distribution_csv_path: Option<String>,
    pub performance_summary: Option<serde_json::Value>,
    pub output_dir: Option<String>,
    pub resolved_input_dir: Option<String>,
}

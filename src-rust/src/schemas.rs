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

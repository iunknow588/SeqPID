use crate::schemas::{MarketPidSnapshot, PatternResult, PredictResult};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::Path;

pub fn build_batch_summary(
    trade_date: &str,
    sample_count: usize,
    output_count: usize,
    warnings: &[String],
) -> serde_json::Map<String, Value> {
    let mut summary = serde_json::Map::new();
    summary.insert("trade_date".into(), Value::String(trade_date.to_string()));
    summary.insert("sample_count".into(), json!(sample_count));
    summary.insert("output_count".into(), json!(output_count));
    summary.insert("warning_count".into(), json!(warnings.len()));
    summary.insert(
        "warnings".into(),
        Value::Array(warnings.iter().cloned().map(Value::String).collect()),
    );
    summary
}

#[allow(clippy::too_many_arguments)]
pub fn build_performance_summary(
    profile_enabled: bool,
    total_seconds: f64,
    sample_build_seconds: f64,
    pattern_seconds: f64,
    capital_seconds: f64,
    market_seconds: f64,
    export_seconds: f64,
    sample_timings: &[HashMap<String, f64>],
    processed_samples: usize,
    imputed_predict_count: usize,
    skipped_incomplete_samples: usize,
    round_seconds: fn(f64) -> f64,
) -> Option<Value> {
    if !profile_enabled {
        return None;
    }
    let mut top_slowest_samples = sample_timings.to_vec();
    top_slowest_samples.sort_by(|left, right| {
        right
            .get("sample_build_seconds")
            .unwrap_or(&0.0)
            .partial_cmp(left.get("sample_build_seconds").unwrap_or(&0.0))
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    top_slowest_samples.truncate(20);
    let top_payload: Vec<Value> = top_slowest_samples
        .into_iter()
        .map(|item| {
            let mut payload = serde_json::Map::new();
            if let Some(value) = item.get("sample_build_seconds") {
                payload.insert("sample_build_seconds".into(), json!(round_seconds(*value)));
            }
            Value::Object(payload)
        })
        .collect();
    Some(json!({
        "total_seconds": round_seconds(total_seconds),
        "sample_build_seconds": round_seconds(sample_build_seconds),
        "pattern_seconds": round_seconds(pattern_seconds),
        "capital_seconds": round_seconds(capital_seconds),
        "market_seconds": round_seconds(market_seconds),
        "export_seconds": round_seconds(export_seconds),
        "processed_samples": processed_samples,
        "imputed_missing_symbols": imputed_predict_count,
        "skipped_incomplete_samples": skipped_incomplete_samples,
        "top_slowest_samples": top_payload,
    }))
}

#[allow(clippy::too_many_arguments)]
pub fn build_batch_result(
    trade_date: &str,
    sample_count: usize,
    pattern_results: &[PatternResult],
    predict_results: &[PredictResult],
    market_snapshot: Option<&MarketPidSnapshot>,
    market_snapshot_path: Option<&Path>,
    market_report_path: Option<&Path>,
    market_validation_report_path: &str,
    replay_validation_report_path: &str,
    diagnostics_json_path: &str,
    distribution_csv_path: &str,
    submit_zip: Option<&str>,
    warnings: &[String],
    imputed_output_count: usize,
    stock_offset: usize,
    stock_limit: Option<usize>,
    stock_list_file: Option<&Path>,
    stock_universe_size: Option<usize>,
    missing_symbols: &[String],
    incomplete_stock_dirs: Value,
    performance_summary: Option<Value>,
) -> HashMap<String, Value> {
    let mut result = HashMap::new();
    result.insert("trade_date".into(), Value::String(trade_date.to_string()));
    result.insert("sample_count".into(), json!(sample_count));
    result.insert("output_count".into(), json!(pattern_results.len()));
    result.insert("imputed_output_count".into(), json!(imputed_output_count));
    result.insert("stock_offset".into(), json!(stock_offset));
    result.insert(
        "stock_limit".into(),
        stock_limit.map(Value::from).unwrap_or(Value::Null),
    );
    result.insert(
        "stock_list_file".into(),
        stock_list_file
            .map(|path| Value::String(path.to_string_lossy().to_string()))
            .unwrap_or(Value::Null),
    );
    result.insert(
        "stock_universe_size".into(),
        stock_universe_size.map(Value::from).unwrap_or(Value::Null),
    );
    result.insert(
        "warnings".into(),
        Value::Array(warnings.iter().cloned().map(Value::String).collect()),
    );
    result.insert(
        "missing_symbols".into(),
        Value::Array(missing_symbols.iter().cloned().map(Value::String).collect()),
    );
    result.insert("incomplete_stock_dirs".into(), incomplete_stock_dirs);
    result.insert(
        "submit_zip".into(),
        submit_zip.map(|path| Value::String(path.to_string())).unwrap_or(Value::Null),
    );
    result.insert(
        "market_snapshot_path".into(),
        market_snapshot_path
            .map(|path| Value::String(path.to_string_lossy().to_string()))
            .unwrap_or(Value::Null),
    );
    result.insert(
        "market_report_path".into(),
        market_report_path
            .map(|path| Value::String(path.to_string_lossy().to_string()))
            .unwrap_or(Value::Null),
    );
    result.insert(
        "market_validation_report_path".into(),
        Value::String(market_validation_report_path.to_string()),
    );
    result.insert(
        "replay_validation_report_path".into(),
        Value::String(replay_validation_report_path.to_string()),
    );
    result.insert(
        "diagnostics_json_path".into(),
        Value::String(diagnostics_json_path.to_string()),
    );
    result.insert(
        "distribution_csv_path".into(),
        Value::String(distribution_csv_path.to_string()),
    );
    result.insert(
        "performance_summary".into(),
        performance_summary.unwrap_or(Value::Null),
    );
    result.insert(
        "market_pid_snapshot".into(),
        market_snapshot
            .map(|snapshot| json!({
                "trade_date": snapshot.trade_date,
                "market_regime": snapshot.market_regime,
                "up_count": snapshot.up_count,
                "down_count": snapshot.down_count,
            }))
            .unwrap_or(Value::Null),
    );
    result.insert("pattern_result_count".into(), json!(pattern_results.len()));
    result.insert("predict_result_count".into(), json!(predict_results.len()));
    result
}

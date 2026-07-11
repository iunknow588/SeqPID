use crate::schemas::DailySample;
use serde_json::Value;
use std::collections::HashMap;

pub fn format_incomplete_stock_warning(incomplete_stock_dirs: &HashMap<String, Vec<String>>) -> String {
    let mut details: Vec<String> = incomplete_stock_dirs
        .iter()
        .map(|(symbol, missing_files)| format!("{}({})", symbol, missing_files.join(",")))
        .collect();
    details.sort();
    format!("Skipped incomplete stock dirs: {}", details.join("; "))
}

pub fn collect_missing_symbols(
    requested_symbols: &Option<Vec<String>>,
    samples: &[DailySample],
) -> Vec<String> {
    let Some(requested_symbols) = requested_symbols else {
        return Vec::new();
    };
    let actual_symbols: std::collections::HashSet<String> = samples
        .iter()
        .map(|sample| sample.stock_code.to_uppercase())
        .collect();
    requested_symbols
        .iter()
        .filter(|symbol| !actual_symbols.contains(&symbol.to_uppercase()))
        .cloned()
        .collect()
}

pub fn build_batch_warnings(
    samples: &[DailySample],
    missing_symbols: &[String],
    incomplete_stock_dirs: &HashMap<String, Vec<String>>,
    imputed_symbols: Option<&[String]>,
) -> Vec<String> {
    let mut warnings = Vec::new();
    if samples.is_empty() {
        warnings.push("No reference feature rows found for the requested date; emitted header-only files.".to_string());
    }
    if !missing_symbols.is_empty() {
        warnings.push(format!(
            "Missing raw data for requested symbols: {}",
            missing_symbols.join(", ")
        ));
    }
    if !incomplete_stock_dirs.is_empty() {
        warnings.push(format_incomplete_stock_warning(incomplete_stock_dirs));
    }
    if let Some(imputed_symbols) = imputed_symbols {
        if !imputed_symbols.is_empty() {
            warnings.push(format!(
                "Imputed missing symbols with market-average defaults: {}",
                imputed_symbols.join(", ")
            ));
        }
    }
    warnings
}

pub fn incomplete_stock_dirs_to_json(
    incomplete_stock_dirs: &HashMap<String, Vec<String>>,
) -> Value {
    let mut payload = serde_json::Map::new();
    let mut items: Vec<_> = incomplete_stock_dirs.iter().collect();
    items.sort_by(|left, right| left.0.cmp(right.0));
    for (symbol, missing_files) in items {
        payload.insert(
            symbol.clone(),
            Value::Array(missing_files.iter().cloned().map(Value::String).collect()),
        );
    }
    Value::Object(payload)
}

use crate::schemas::{SchemaProbeFileResult, SchemaProbeResult};
use anyhow::Result;
use encoding_rs::{GB18030, UTF_8};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

struct FileSpec {
    candidates: Vec<&'static str>,
    required_fields: Vec<&'static str>,
}

fn expected_files() -> HashMap<&'static str, FileSpec> {
    let mut map = HashMap::new();
    map.insert("trades", FileSpec {
        candidates: vec!["trades.csv", "trades.parquet", "逐笔成交.csv"],
        required_fields: vec!["symbol", "timestamp_ms", "price", "volume", "amount"],
    });
    map.insert("orders", FileSpec {
        candidates: vec!["orders.csv", "orders.parquet", "逐笔委托.csv"],
        required_fields: vec!["symbol", "timestamp_ms", "side", "price", "volume"],
    });
    map.insert("cancels", FileSpec {
        candidates: vec!["cancels.csv", "cancels.parquet", "逐笔撤单.csv"],
        required_fields: vec!["symbol", "timestamp_ms", "side", "price", "volume"],
    });
    map.insert("snapshots", FileSpec {
        candidates: vec!["snapshots.csv", "snapshots.parquet", "十档盘口快照.csv", "行情.csv"],
        required_fields: vec!["symbol", "timestamp_ms", "bid_px_1", "ask_px_1"],
    });
    map.insert("reference_features", FileSpec {
        candidates: vec!["reference_features.csv", "features.csv", "参考特征.csv"],
        required_fields: vec!["date", "symbol", "window_start", "window_end"],
    });
    map
}

fn field_mapping_hints() -> HashMap<&'static str, HashMap<&'static str, &'static str>> {
    let mut map = HashMap::new();

    let mut trades = HashMap::new();
    trades.insert("万得代码", "symbol");
    trades.insert("自然日", "trade_date");
    trades.insert("时间", "timestamp_ms");
    trades.insert("成交价格", "price");
    trades.insert("成交数量", "volume");
    trades.insert("BS标志", "side");
    map.insert("trades", trades);

    let mut orders = HashMap::new();
    orders.insert("万得代码", "symbol");
    orders.insert("自然日", "trade_date");
    orders.insert("时间", "timestamp_ms");
    orders.insert("委托代码", "side");
    orders.insert("委托价格", "price");
    orders.insert("委托数量", "volume");
    orders.insert("交易所委托号", "order_id");
    map.insert("orders", orders);

    let mut snapshots = HashMap::new();
    snapshots.insert("万得代码", "symbol");
    snapshots.insert("自然日", "trade_date");
    snapshots.insert("时间", "timestamp_ms");
    snapshots.insert("申买价1", "bid_px_1");
    snapshots.insert("申卖价1", "ask_px_1");
    snapshots.insert("申买量1", "bid_vol_1");
    snapshots.insert("申卖量1", "ask_vol_1");
    snapshots.insert("上涨品种数", "market_up_count");
    snapshots.insert("下跌品种数", "market_down_count");
    snapshots.insert("持平品种数", "market_flat_count");
    map.insert("snapshots", snapshots);

    map
}

fn read_csv_header(path: &Path) -> Result<(Vec<String>, Option<usize>)> {
    let bytes = fs::read(path)?;
    let (encoding, _used, _had_errors) = if bytes.starts_with(&[0xEF, 0xBB, 0xBF]) {
        (UTF_8, true, false)
    } else {
        let (_, _, had_errors) = UTF_8.decode(&bytes);
        if had_errors {
            (GB18030, true, false)
        } else {
            (UTF_8, true, false)
        }
    };
    let (text, _, _) = encoding.decode(&bytes);
    let text = text.strip_prefix('\u{FEFF}').unwrap_or(&text);

    let mut reader = csv::ReaderBuilder::new()
        .has_headers(true)
        .from_reader(text.as_bytes());
    let headers: Vec<String> = reader
        .headers()?
        .iter()
        .map(|s| s.to_string())
        .collect();

    let mut count = 0;
    for result in reader.records() {
        if result.is_ok() {
            count += 1;
            if count >= 1000 {
                break;
            }
        }
    }

    Ok((headers, Some(count)))
}

fn find_candidate_file(base: &Path, candidates: &[&str]) -> Option<PathBuf> {
    for name in candidates {
        let path = base.join(name);
        if path.exists() {
            return Some(path);
        }
    }
    None
}

fn iter_stock_dirs(base: &Path) -> Vec<PathBuf> {
    let mut dirs: Vec<PathBuf> = fs::read_dir(base)
        .ok()
        .map(|entries| {
            entries
                .filter_map(|e| e.ok())
                .filter(|e| e.path().is_dir())
                .map(|e| e.path())
                .collect()
        })
        .unwrap_or_default();
    dirs.sort();
    dirs
}

fn find_stock_dir_file(base: &Path, candidates: &[&str]) -> (Option<PathBuf>, Option<String>) {
    for stock_dir in iter_stock_dirs(base) {
        for name in candidates {
            let path = stock_dir.join(name);
            if path.exists() {
                return (Some(path), Some(stock_dir.file_name().unwrap().to_string_lossy().to_string()));
            }
        }
    }
    (None, None)
}

pub fn probe_input_schema(input_dir: &Path, trade_date: &str) -> Result<SchemaProbeResult> {
    if !input_dir.exists() {
        anyhow::bail!("Input directory not found: {}", input_dir.display());
    }

    let specs = expected_files();
    let hints = field_mapping_hints();
    let mut files: HashMap<String, SchemaProbeFileResult> = HashMap::new();

    let mut missing_file_keys: Vec<String> = Vec::new();
    let mut order_lifetime_ms_detected = false;
    let mut reference_feature_file_detected = false;
    let mut layout = "flat_files".to_string();
    let mut sample_stock_dir = String::new();
    let mut field_mapping_hints_out: HashMap<String, HashMap<String, String>> = HashMap::new();
    let mut encoding_hint = String::new();

    let stock_dirs = iter_stock_dirs(input_dir);
    if !stock_dirs.is_empty() {
        layout = "per_stock_dirs".to_string();
    }

    for (key, spec) in &specs {
        let mut path = find_candidate_file(input_dir, &spec.candidates);
        let found_stock_dir: Option<String>;
        if path.is_none() && *key != "reference_features" {
            let (p, sd) = find_stock_dir_file(input_dir, &spec.candidates);
            path = p;
            found_stock_dir = sd;
            if let Some(ref sd) = found_stock_dir {
                sample_stock_dir = sd.clone();
            }
        }

        if path.is_none() {
            files.insert(
                key.to_string(),
                SchemaProbeFileResult {
                    path: input_dir.join(spec.candidates[0]).to_string_lossy().to_string(),
                    exists: false,
                    suffix: String::new(),
                    size_bytes: 0,
                    missing_required_fields: spec.required_fields.iter().map(|s| s.to_string()).collect(),
                    ..Default::default()
                },
            );
            missing_file_keys.push(key.to_string());
            continue;
        }

        let path = path.unwrap();
        let mut header: Vec<String> = Vec::new();
        let mut row_count: Option<usize> = None;

        if path.extension().and_then(|e| e.to_str()).unwrap_or("") == "csv" {
            if let Ok((h, rc)) = read_csv_header(&path) {
                header = h;
                row_count = rc;
            }
        }

        let required_present: Vec<String> = spec
            .required_fields
            .iter()
            .filter(|f| header.contains(&f.to_string()))
            .map(|f| f.to_string())
            .collect();
        let required_missing: Vec<String> = spec
            .required_fields
            .iter()
            .filter(|f| !header.contains(&f.to_string()))
            .map(|f| f.to_string())
            .collect();

        if header.contains(&"order_lifetime_ms".to_string()) {
            order_lifetime_ms_detected = true;
        }
        if *key == "reference_features" {
            reference_feature_file_detected = true;
        }
        if *key == "trades" && header.contains(&"万得代码".to_string()) {
            encoding_hint = "gb18030".to_string();
        }

        if let Some(key_hints) = hints.get(key) {
            let matched: HashMap<String, String> = key_hints
                .iter()
                .filter(|(src, _)| header.contains(&src.to_string()))
                .map(|(src, dst)| (src.to_string(), dst.to_string()))
                .collect();
            if !matched.is_empty() {
                field_mapping_hints_out.insert(key.to_string(), matched);
            }
        }

        files.insert(
            key.to_string(),
            SchemaProbeFileResult {
                path: path.to_string_lossy().to_string(),
                exists: true,
                suffix: path.extension().and_then(|e| e.to_str()).unwrap_or("").to_string(),
                size_bytes: fs::metadata(&path).map(|m| m.len()).unwrap_or(0),
                sample_header: header,
                row_count_estimate: row_count,
                required_fields_present: required_present,
                missing_required_fields: required_missing,
            },
        );
    }

    let mut summary: HashMap<String, serde_json::Value> = HashMap::new();
    summary.insert("missing_file_keys".into(), serde_json::Value::Array(missing_file_keys.iter().map(|s| serde_json::Value::String(s.clone())).collect()));
    summary.insert("order_lifetime_ms_detected".into(), serde_json::Value::Bool(order_lifetime_ms_detected));
    summary.insert("reference_feature_file_detected".into(), serde_json::Value::Bool(reference_feature_file_detected));
    summary.insert("layout".into(), serde_json::Value::String(layout));
    summary.insert("sample_stock_dir".into(), serde_json::Value::String(sample_stock_dir));
    if !encoding_hint.is_empty() {
        summary.insert("encoding_hint".into(), serde_json::Value::String(encoding_hint));
    }
    let hints_json: HashMap<String, serde_json::Value> = field_mapping_hints_out
        .into_iter()
        .map(|(k, v)| {
            let inner: HashMap<String, serde_json::Value> = v
                .into_iter()
                .map(|(sk, sv)| (sk, serde_json::Value::String(sv)))
                .collect();
            (k, serde_json::Value::Object(inner.into_iter().map(|(k, v)| (k, v)).collect()))
        })
        .collect();
    if !hints_json.is_empty() {
        summary.insert("field_mapping_hints".into(), serde_json::Value::Object(hints_json.into_iter().map(|(k, v)| (k, v)).collect()));
    }

    Ok(SchemaProbeResult {
        trade_date: trade_date.to_string(),
        input_dir: input_dir.to_string_lossy().to_string(),
        files,
        summary,
    })
}

pub fn render_schema_probe_report(result: &SchemaProbeResult) -> String {
    let mut lines: Vec<String> = Vec::new();
    lines.push("# Schema Probe Report".into());
    lines.push(String::new());
    lines.push(format!("- trade_date: {}", result.trade_date));
    lines.push(format!("- input_dir: {}", result.input_dir));
    lines.push(String::new());
    lines.push("## Summary".into());
    lines.push(String::new());

    let missing: Vec<String> = result
        .summary
        .get("missing_file_keys")
        .and_then(|v| match v {
            serde_json::Value::Array(arr) => Some(arr.iter().filter_map(|i| i.as_str().map(String::from)).collect()),
            _ => None,
        })
        .unwrap_or_default();
    lines.push(format!("- missing_file_keys: {}", if missing.is_empty() { "none".to_string() } else { missing.join(", ") }));

    if let Some(v) = result.summary.get("order_lifetime_ms_detected") {
        lines.push(format!("- order_lifetime_ms_detected: {}", v));
    }
    if let Some(v) = result.summary.get("reference_feature_file_detected") {
        lines.push(format!("- reference_feature_file_detected: {}", v));
    }
    if let Some(v) = result.summary.get("layout") {
        lines.push(format!("- layout: {}", v.as_str().unwrap_or("")));
    }
    if let Some(v) = result.summary.get("sample_stock_dir") {
        let s = v.as_str().unwrap_or("");
        if !s.is_empty() {
            lines.push(format!("- sample_stock_dir: {}", s));
        }
    }
    if let Some(v) = result.summary.get("encoding_hint") {
        lines.push(format!("- encoding_hint: {}", v.as_str().unwrap_or("")));
    }
    lines.push(String::new());

    if let Some(hints) = result.summary.get("field_mapping_hints") {
        if let Some(obj) = hints.as_object() {
            lines.push("## Field Mapping Hints".into());
            lines.push(String::new());
            for (key, mapping) in obj {
                lines.push(format!("### {}", key));
                lines.push(String::new());
                if let Some(map) = mapping.as_object() {
                    for (src, dst) in map {
                        lines.push(format!("- {} -> {}", src, dst.as_str().unwrap_or("")));
                    }
                }
                lines.push(String::new());
            }
        }
    }

    lines.push("## File Details".into());
    lines.push(String::new());

    let mut keys: Vec<&String> = result.files.keys().collect();
    keys.sort();
    for key in keys {
        let item = &result.files[key];
        lines.push(format!("### {}", key));
        lines.push(String::new());
        lines.push(format!("- path: {}", item.path));
        lines.push(format!("- exists: {}", item.exists));
        lines.push(format!("- suffix: {}", item.suffix));
        lines.push(format!("- size_bytes: {}", item.size_bytes));
        if !item.sample_header.is_empty() {
            let first20: Vec<&str> = item.sample_header.iter().take(20).map(|s| s.as_str()).collect();
            lines.push(format!("- sample_header: {}", first20.join(", ")));
        }
        if let Some(rc) = item.row_count_estimate {
            lines.push(format!("- row_count_estimate(first1000): {}", rc));
        }
        lines.push(format!("- required_fields_present: {}",
            if item.required_fields_present.is_empty() { "none".to_string() } else { item.required_fields_present.join(", ") }));
        lines.push(format!("- missing_required_fields: {}",
            if item.missing_required_fields.is_empty() { "none".to_string() } else { item.missing_required_fields.join(", ") }));
        lines.push(String::new());
    }

    lines.join("\n") + "\n"
}

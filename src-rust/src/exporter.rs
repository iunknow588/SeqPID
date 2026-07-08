use crate::schemas::{MarketPidSnapshot, PatternResult, PredictResult};
use anyhow::Result;
use csv::Writer;
use std::collections::HashMap;
use std::fs;
use std::io::Write;
use std::path::Path;

const PATTERN_COLUMNS: &[&str] = &["stock_code", "transaction_date", "pattern_type", "pattern_explanation"];
const PREDICT_COLUMNS: &[&str] = &["stock_code", "transaction_date", "capital_type", "capital_intention"];
const MARKET_SNAPSHOT_COLUMNS: &[&str] = &[
    "trade_date", "up_count", "down_count", "breadth_ratio", "breadth_balance",
    "p_mean", "p_median", "p_std", "i_mean", "i_median", "i_std",
    "d_mean", "d_median", "d_std", "market_regime",
];
const SUMMARY_COLUMNS: &[&str] = &["category", "label", "count", "ratio"];

fn round6(v: f64) -> f64 {
    (v * 1_000_000.0).round() / 1_000_000.0
}

pub fn export_pattern_reco(results: &[PatternResult], output_path: &Path) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(PATTERN_COLUMNS)?;
    for item in results {
        wtr.write_record(&[
            &item.stock_code,
            &item.transaction_date,
            &item.pattern_type,
            &item.pattern_explanation,
        ])?;
    }
    wtr.flush()?;
    Ok(())
}

pub fn export_predict_result(results: &[PredictResult], output_path: &Path) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(PREDICT_COLUMNS)?;
    for item in results {
        wtr.write_record(&[
            &item.stock_code,
            &item.transaction_date,
            &item.capital_type,
            &item.capital_intention,
        ])?;
    }
    wtr.flush()?;
    Ok(())
}

pub fn export_market_pid_snapshot(snapshot: &MarketPidSnapshot, output_path: &Path) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(MARKET_SNAPSHOT_COLUMNS)?;
    wtr.write_record(&[
        &snapshot.trade_date,
        &snapshot.up_count.to_string(),
        &snapshot.down_count.to_string(),
        &round6(snapshot.breadth_ratio).to_string(),
        &round6(snapshot.breadth_balance).to_string(),
        &round6(snapshot.p_mean).to_string(),
        &round6(snapshot.p_median).to_string(),
        &round6(snapshot.p_std).to_string(),
        &round6(snapshot.i_mean).to_string(),
        &round6(snapshot.i_median).to_string(),
        &round6(snapshot.i_std).to_string(),
        &round6(snapshot.d_mean).to_string(),
        &round6(snapshot.d_median).to_string(),
        &round6(snapshot.d_std).to_string(),
        &snapshot.market_regime,
    ])?;
    wtr.flush()?;
    Ok(())
}

pub fn export_market_regime_report(snapshot: &MarketPidSnapshot, output_path: &Path) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let diag_str = serde_json::to_string_pretty(&snapshot.diagnostics).unwrap_or_default();
    let content = format!(
        "# Market Regime Report\n\n\
         - trade_date: {}\n\
         - market_regime: {}\n\
         - up_count: {}\n\
         - down_count: {}\n\
         - breadth_ratio: {:.4}\n\
         - breadth_balance: {:.4}\n\n\
         ## PID Summary\n\n\
         - P: mean {:.4}, median {:.4}, std {:.4}\n\
         - I: mean {:.4}, median {:.4}, std {:.4}\n\
         - D: mean {:.4}, median {:.4}, std {:.4}\n\n\
         ## Diagnostics\n\n\
         `json\n{}\n`\n",
        snapshot.trade_date,
        snapshot.market_regime,
        snapshot.up_count,
        snapshot.down_count,
        snapshot.breadth_ratio,
        snapshot.breadth_balance,
        snapshot.p_mean,
        snapshot.p_median,
        snapshot.p_std,
        snapshot.i_mean,
        snapshot.i_median,
        snapshot.i_std,
        snapshot.d_mean,
        snapshot.d_median,
        snapshot.d_std,
        diag_str
    );
    fs::write(output_path, content)?;
    Ok(())
}

pub fn export_batch_diagnostics(
    snapshot: Option<&MarketPidSnapshot>,
    pattern_results: &[PatternResult],
    predict_results: &[PredictResult],
    output_dir: &Path,
) -> Result<(String, String)> {
    fs::create_dir_all(output_dir)?;
    let json_path = output_dir.join("batch_diagnostics.json");
    let csv_path = output_dir.join("label_distribution.csv");

    let mut pattern_counts: HashMap<String, i64> = HashMap::new();
    let mut capital_counts: HashMap<String, i64> = HashMap::new();
    let mut intention_counts: HashMap<String, i64> = HashMap::new();

    for item in pattern_results {
        *pattern_counts.entry(item.pattern_type.clone()).or_insert(0) += 1;
    }
    for item in predict_results {
        *capital_counts.entry(item.capital_type.clone()).or_insert(0) += 1;
        *intention_counts.entry(item.capital_intention.clone()).or_insert(0) += 1;
    }

    let sample_count = pattern_results.len();

    let mut payload = serde_json::Map::new();
    payload.insert("sample_count".into(), serde_json::Value::Number(sample_count.into()));

    let pc: serde_json::Map<String, serde_json::Value> = pattern_counts.iter()
        .map(|(k, v)| (k.clone(), serde_json::Value::Number((*v).into())))
        .collect();
    payload.insert("pattern_counts".into(), serde_json::Value::Object(pc));

    let cc: serde_json::Map<String, serde_json::Value> = capital_counts.iter()
        .map(|(k, v)| (k.clone(), serde_json::Value::Number((*v).into())))
        .collect();
    payload.insert("capital_counts".into(), serde_json::Value::Object(cc));

    let ic: serde_json::Map<String, serde_json::Value> = intention_counts.iter()
        .map(|(k, v)| (k.clone(), serde_json::Value::Number((*v).into())))
        .collect();
    payload.insert("intention_counts".into(), serde_json::Value::Object(ic));

    if let Some(snap) = snapshot {
        let mut ms = serde_json::Map::new();
        ms.insert("trade_date".into(), serde_json::Value::String(snap.trade_date.clone()));
        ms.insert("market_regime".into(), serde_json::Value::String(snap.market_regime.clone()));
        ms.insert("up_count".into(), serde_json::Value::Number(snap.up_count.into()));
        ms.insert("down_count".into(), serde_json::Value::Number(snap.down_count.into()));
        ms.insert("breadth_ratio".into(), serde_json::Value::Number(serde_json::Number::from_f64(snap.breadth_ratio).unwrap_or(0.into())));
        ms.insert("breadth_balance".into(), serde_json::Value::Number(serde_json::Number::from_f64(snap.breadth_balance).unwrap_or(0.into())));
        ms.insert("p_median".into(), serde_json::Value::Number(serde_json::Number::from_f64(snap.p_median).unwrap_or(0.into())));
        ms.insert("i_median".into(), serde_json::Value::Number(serde_json::Number::from_f64(snap.i_median).unwrap_or(0.into())));
        ms.insert("d_median".into(), serde_json::Value::Number(serde_json::Number::from_f64(snap.d_median).unwrap_or(0.into())));
        payload.insert("market_snapshot".into(), serde_json::Value::Object(ms));
    } else {
        payload.insert("market_snapshot".into(), serde_json::Value::Null);
    }

    fs::write(&json_path, serde_json::to_string_pretty(&serde_json::Value::Object(payload))?)?;

    // Write label_distribution.csv
    let mut wtr = Writer::from_path(&csv_path)?;
    wtr.write_record(SUMMARY_COLUMNS)?;

    let categories: &[(&str, &HashMap<String, i64>)] = &[
        ("pattern_type", &pattern_counts),
        ("capital_type", &capital_counts),
        ("capital_intention", &intention_counts),
    ];
    for (category, counts) in categories {
        let total: i64 = counts.values().sum::<i64>().max(1);
        let mut sorted: Vec<(&String, &i64)> = counts.iter().collect();
        sorted.sort_by(|a, b| b.1.cmp(a.1).then_with(|| a.0.cmp(b.0)));
        for (label, count) in sorted {
            let ratio = *count as f64 / total as f64;
            wtr.write_record(&[
                category,
                label.as_str(),
                &count.to_string(),
                &round6(ratio).to_string(),
            ])?;
        }
    }
    wtr.flush()?;

    Ok((json_path.to_string_lossy().to_string(), csv_path.to_string_lossy().to_string()))
}

pub fn validate_submission_files(pattern_path: &Path, predict_path: &Path) -> Result<()> {
    if !pattern_path.exists() {
        anyhow::bail!("Submission file not found: {}", pattern_path.display());
    }
    if !predict_path.exists() {
        anyhow::bail!("Submission file not found: {}", predict_path.display());
    }

    let expected: &[(&Path, &[&str])] = &[
        (pattern_path, PATTERN_COLUMNS),
        (predict_path, PREDICT_COLUMNS),
    ];

    let mut row_counts: HashMap<String, usize> = HashMap::new();

    for (path, cols) in expected {
        let mut rdr = csv::Reader::from_path(path)?;
        let header: Vec<String> = rdr.headers()?.iter().map(|s| s.to_string()).collect();
        let expected_header: Vec<String> = cols.iter().map(|s| s.to_string()).collect();
        if header != expected_header {
            anyhow::bail!(
                "Invalid header for {}: {:?} != {:?}",
                path.file_name().unwrap().to_string_lossy(),
                header,
                expected_header
            );
        }

        let mut row_count = 0usize;
        for result in rdr.records() {
            let record = result?;
            row_count += 1;
            if record.len() != cols.len() {
                anyhow::bail!(
                    "Invalid column count for {}: {:?}",
                    path.file_name().unwrap().to_string_lossy(),
                    record
                );
            }
            if record.iter().any(|cell| cell.trim().is_empty()) {
                anyhow::bail!(
                    "Empty required field found in {}: {:?}",
                    path.file_name().unwrap().to_string_lossy(),
                    record
                );
            }
        }
        row_counts.insert(
            path.file_name().unwrap().to_string_lossy().to_string(),
            row_count,
        );
    }

    let pattern_rows = row_counts.get("pattern_reco.csv").copied().unwrap_or(0);
    let predict_rows = row_counts.get("predict_result.csv").copied().unwrap_or(0);
    if pattern_rows != predict_rows {
        anyhow::bail!(
            "Row count mismatch between pattern_reco.csv and predict_result.csv: {} != {}",
            pattern_rows,
            predict_rows
        );
    }
    Ok(())
}

pub fn build_submit_zip(output_dir: &Path) -> Result<String> {
    let pattern_path = output_dir.join("pattern_reco.csv");
    let predict_path = output_dir.join("predict_result.csv");
    validate_submission_files(&pattern_path, &predict_path)?;

    let zip_path = output_dir.join("submit.zip");
    let file = fs::File::create(&zip_path)?;
    let mut zip = zip::ZipWriter::new(file);
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);

    zip.start_file("pattern_reco.csv", options)?;
    zip.write_all(&fs::read(&pattern_path)?)?;

    zip.start_file("predict_result.csv", options)?;
    zip.write_all(&fs::read(&predict_path)?)?;

    zip.finish()?;
    Ok(zip_path.to_string_lossy().to_string())
}

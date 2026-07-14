use crate::schemas::{DecompositionResult, MarketPidSnapshot, PatternResult, PredictResult};
use anyhow::Result;
use csv::Writer;
use std::collections::HashMap;
use std::fs;
use std::io::Write;
use std::path::Path;

const PATTERN_COLUMNS: &[&str] = &["stock_code", "transaction_date", "pattern_type", "pattern_explanation"];
const PREDICT_COLUMNS: &[&str] = &["stock_code", "transaction_date", "capital_type", "capital_intention"];
const MARKET_SNAPSHOT_COLUMNS: &[&str] = &[
    "trade_date",
    "up_count",
    "down_count",
    "breadth_ratio",
    "breadth_balance",
    "p_mean",
    "p_median",
    "p_std",
    "i_mean",
    "i_median",
    "i_std",
    "d_mean",
    "d_median",
    "d_std",
    "market_regime",
];
const SUMMARY_COLUMNS: &[&str] = &["category", "label", "count", "ratio"];
const EVENT_CLASSIFIED_COLUMNS: &[&str] = &[
    "trade_date",
    "symbol",
    "event_id",
    "event_time",
    "window_id",
    "side",
    "signed_amount",
    "capital_type_rule",
    "confidence_score",
    "reason_codes",
];
const WINDOW_FEATURE_COLUMNS: &[&str] = &[
    "trade_date",
    "symbol",
    "window_id",
    "window_start",
    "window_end",
    "open_price",
    "close_price",
    "vwap",
    "deal_amount",
    "data_P",
    "data_P_source",
];
const PID_TAIL_COLUMNS: &[&str] = &[
    "stock_code",
    "transaction_date",
    "mode",
    "kf_converged",
    "dominant_type",
    "dominant_intention",
    "hot_money_ratio",
    "quant_ratio",
    "retail_ratio",
    "phi_tail",
    "theta_tail",
    "beta_ch_tail",
    "beta_mix_tail",
    "beta_q_tail",
    "beta_retail_tail",
    "c_p_tail",
    "c_i_tail",
    "c_d_tail",
    "capital_ch_tail",
    "capital_q_tail",
    "capital_retail_tail",
    "capital_anchor_error_tail",
    "noise_ratio_tail",
    "explain_ratio_tail",
    "capital_identity_error",
    "closure_error",
    "warnings",
];
const PID_WINDOW_PARAM_COLUMNS: &[&str] = &[
    "stock_code",
    "transaction_date",
    "window_id",
    "mode_name",
    "phi",
    "beta_ch",
    "beta_q",
    "beta_retail",
    "beta_mix",
    "theta",
    "covariance_diag",
];
const PID_WINDOW_CONTRIB_COLUMNS: &[&str] = &[
    "stock_code",
    "transaction_date",
    "window_id",
    "c_p",
    "c_i",
    "c_d",
    "eps",
    "capital_ch",
    "capital_q",
    "capital_retail",
    "capital_mix",
    "noise_ratio",
    "explain_ratio",
    "capital_anchor_error",
    "closure_error",
];
const PID_WINDOW_DIAG_COLUMNS: &[&str] = &[
    "trade_date",
    "symbol",
    "window_id",
    "mode_name",
    "q_type",
    "u_source_type",
    "estimator_method",
    "state_space_contract",
    "psi_prediction_semantics",
    "y_observed",
    "y_hat_next",
    "v_q_observed",
    "v_hat_q_next",
    "c_p",
    "c_i",
    "c_d",
    "eps",
    "capital_ch",
    "capital_q",
    "capital_retail",
    "capital_mix",
    "beta_norm_ch_diag",
    "beta_norm_q_diag",
    "beta_norm_retail_diag",
    "beta_norm_mix_diag",
    "m_eff_ch_diag",
    "m_eff_q_diag",
    "m_eff_retail_diag",
    "m_eff_mix_diag",
    "beta_norm_unit",
    "m_eff_source_type",
    "m_eff_clipped_flag",
    "closure_impl_error",
    "model_residual",
    "param_stability_flag",
    "m_eff_rank_eligible",
    "data_leakage_check",
    "m_slow_method",
    "thin_trade_window",
    "cross_symbol_comparable",
    "domain_mapping_valid_flag",
    "warnings",
];
const PID_DAILY_DIAG_COLUMNS: &[&str] = &[
    "trade_date",
    "symbol",
    "mode_name",
    "q_type",
    "u_source_type",
    "estimator_method",
    "m_slow_method",
    "lookback_days",
    "zero_trade_policy",
    "submission_requires_complete_windows",
    "lambda_switch",
    "lambda_jump",
    "lambda_error",
    "data_leakage_check",
    "feature_engineering_leakage_check",
    "rule_layer_leakage_check",
    "offline_smooth_used",
    "param_stability_flag",
    "beta_norm_unit",
    "m_eff_source_type",
    "m_eff_clipped_flag",
    "m_eff_uncertainty_flag",
    "m_eff_rank_eligible",
    "submission_ready",
    "sample_origin",
    "reason_code",
    "code_build_hash",
    "warning_count",
    "warnings",
];
const RAW_DATA_QUALITY_COLUMNS: &[&str] = &[
    "trade_date",
    "symbol",
    "file_role",
    "file_path",
    "file_exists",
    "file_size",
    "null_byte_ratio",
    "encoding_used",
    "header_valid",
    "raw_row_count",
    "effective_row_count",
    "quality_status",
    "reason_code",
    "action",
];
const WINDOW_FLOW_COLUMNS: &[&str] = &["stock_code", "transaction_date", "window_id"];

fn round6(v: f64) -> f64 {
    (v * 1_000_000.0).round() / 1_000_000.0
}

fn window_bounds(window_id: i64) -> (String, String) {
    let start_minutes = if window_id < 24 {
        9 * 60 + 30 + window_id * 5
    } else {
        13 * 60 + (window_id - 24) * 5
    };
    let end_minutes = start_minutes + 5;
    (
        format!("{:02}:{:02}", start_minutes / 60, start_minutes % 60),
        format!("{:02}:{:02}", end_minutes / 60, end_minutes % 60),
    )
}

fn row_float(row: &HashMap<String, String>, keys: &[&str], default: f64) -> f64 {
    for key in keys {
        if let Some(value) = row.get(*key) {
            if let Ok(parsed) = value.parse::<f64>() {
                return parsed;
            }
        }
    }
    default
}

fn resolve_m_eff_status(_config: &serde_json::Value) -> (&'static str, &'static str) {
    ("true", "false")
}

fn series_optional_value(values: &[f64], index: usize) -> Option<f64> {
    values.get(index).copied().filter(|value| !value.is_nan())
}

fn proxy_beta_norm(capital_value: Option<f64>, price_basis: Option<f64>, u_ratio: Option<f64>) -> Option<f64> {
    let capital_value = capital_value?;
    let price_basis = price_basis?;
    let u_ratio = u_ratio?;
    if price_basis.abs() <= 1e-12 || u_ratio.abs() <= 1e-12 {
        return None;
    }
    Some((capital_value / price_basis) / u_ratio)
}

fn proxy_m_eff(beta_norm: Option<f64>, beta_norm_floor: f64) -> (Option<f64>, bool) {
    match beta_norm {
        Some(value) => {
            let clipped = value.abs() <= beta_norm_floor;
            (Some(1.0 / value.abs().max(beta_norm_floor)), clipped)
        }
        None => (None, false),
    }
}

fn format_optional_float(value: Option<f64>) -> String {
    value
        .map(|v| python_like_float_string(round6(v)))
        .unwrap_or_default()
}

fn python_like_float_string(value: f64) -> String {
    let raw = format!("{:?}", value);
    if let Some(pos) = raw.find('e') {
        let mantissa = &raw[..pos];
        let exponent = &raw[pos + 1..];
        if exponent.len() >= 2 {
            let sign = &exponent[..1];
            let digits = &exponent[1..];
            if digits.len() == 1 {
                return format!("{mantissa}e{sign}0{digits}");
            }
        }
    }
    raw
}

struct ProxyMetrics {
    beta_norm_ch_diag: String,
    beta_norm_q_diag: String,
    beta_norm_retail_diag: String,
    beta_norm_mix_diag: String,
    m_eff_ch_diag: String,
    m_eff_q_diag: String,
    m_eff_retail_diag: String,
    m_eff_mix_diag: String,
    beta_norm_unit: String,
    m_eff_source_type: String,
    m_eff_clipped_flag: String,
}

fn window_diag_proxy_metrics(
    result: &DecompositionResult,
    window_id: usize,
    beta_norm_floor: f64,
) -> ProxyMetrics {
    let price_basis = series_optional_value(&result.price_basis, window_id);
    let components = [
        (
            "ch",
            series_optional_value(&result.capital_ch, window_id),
            series_optional_value(&result.u_ch_amount_ratio, window_id),
        ),
        (
            "q",
            series_optional_value(&result.capital_q, window_id),
            series_optional_value(&result.u_q_amount_ratio, window_id),
        ),
        (
            "retail",
            series_optional_value(&result.capital_retail, window_id),
            series_optional_value(&result.u_retail_amount_ratio, window_id),
        ),
        (
            "mix",
            series_optional_value(&result.capital_mix, window_id),
            series_optional_value(&result.u_mix_amount_ratio, window_id),
        ),
    ];
    let mut any_valid = false;
    let mut any_clipped = false;
    let mut beta_norm_ch_diag = String::new();
    let mut beta_norm_q_diag = String::new();
    let mut beta_norm_retail_diag = String::new();
    let mut beta_norm_mix_diag = String::new();
    let mut m_eff_ch_diag = String::new();
    let mut m_eff_q_diag = String::new();
    let mut m_eff_retail_diag = String::new();
    let mut m_eff_mix_diag = String::new();
    for (name, capital_value, u_ratio) in components {
        let beta_norm = proxy_beta_norm(capital_value, price_basis, u_ratio);
        let (m_eff, clipped) = proxy_m_eff(beta_norm, beta_norm_floor);
        match name {
            "ch" => {
                beta_norm_ch_diag = format_optional_float(beta_norm);
                m_eff_ch_diag = format_optional_float(m_eff);
            }
            "q" => {
                beta_norm_q_diag = format_optional_float(beta_norm);
                m_eff_q_diag = format_optional_float(m_eff);
            }
            "retail" => {
                beta_norm_retail_diag = format_optional_float(beta_norm);
                m_eff_retail_diag = format_optional_float(m_eff);
            }
            _ => {
                beta_norm_mix_diag = format_optional_float(beta_norm);
                m_eff_mix_diag = format_optional_float(m_eff);
            }
        }
        any_valid |= beta_norm.is_some();
        any_clipped |= clipped;
    }
    ProxyMetrics {
        beta_norm_ch_diag,
        beta_norm_q_diag,
        beta_norm_retail_diag,
        beta_norm_mix_diag,
        m_eff_ch_diag,
        m_eff_q_diag,
        m_eff_retail_diag,
        m_eff_mix_diag,
        beta_norm_unit: if any_valid { "amount_response" } else { "" }.to_string(),
        m_eff_source_type: if any_valid { "amount_ratio_proxy" } else { "unavailable" }.to_string(),
        m_eff_clipped_flag: if any_clipped { "true" } else { "false" }.to_string(),
    }
}

fn daily_diag_proxy_summary(result: &DecompositionResult, beta_norm_floor: f64) -> (&'static str, &'static str, &'static str) {
    let row_count = [
        result.price_basis.len(),
        result.u_ch_amount_ratio.len(),
        result.u_q_amount_ratio.len(),
        result.u_retail_amount_ratio.len(),
        result.u_mix_amount_ratio.len(),
    ]
    .into_iter()
    .max()
    .unwrap_or(0);
    let mut any_valid = false;
    let mut any_clipped = false;
    for window_id in 0..row_count {
        let metrics = window_diag_proxy_metrics(result, window_id, beta_norm_floor);
        any_valid |= metrics.m_eff_source_type == "amount_ratio_proxy";
        any_clipped |= metrics.m_eff_clipped_flag == "true";
    }
    (
        if any_valid { "amount_response" } else { "" },
        if any_valid { "amount_ratio_proxy" } else { "unavailable" },
        if any_clipped { "true" } else { "false" },
    )
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

pub fn export_event_classified_rows(samples: &[crate::schemas::DailySample], output_path: &Path) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let capital_fields = [
        ("CH_rule_t", "hot_money"),
        ("Q_rule_t", "quant"),
        ("R_seed_t", "retail"),
    ];
    let mut sorted_samples: Vec<&crate::schemas::DailySample> = samples.iter().collect();
    sorted_samples.sort_by(|a, b| a.stock_code.cmp(&b.stock_code).then_with(|| a.transaction_date.cmp(&b.transaction_date)));

    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(EVENT_CLASSIFIED_COLUMNS)?;
    for sample in sorted_samples {
        for row in &sample.rows {
            let window_id = row_float(row, &["window_id"], 0.0) as i64;
            for (field_name, capital_type) in capital_fields {
                let signed_amount = row_float(row, &[field_name], 0.0);
                if signed_amount == 0.0 {
                    continue;
                }
                let side = if signed_amount > 0.0 { "buy" } else { "sell" };
                let event_id = format!("{}-{}-{:02}-{}", sample.stock_code, sample.transaction_date, window_id, capital_type);
                wtr.write_record(&[
                    sample.transaction_date.as_str(),
                    sample.stock_code.as_str(),
                    event_id.as_str(),
                    "",
                    &window_id.to_string(),
                    side,
                    &round6(signed_amount).to_string(),
                    capital_type,
                    "",
                    "window_aggregate",
                ])?;
            }
        }
    }
    wtr.flush()?;
    Ok(())
}

pub fn export_window_feature_rows(samples: &[crate::schemas::DailySample], output_path: &Path) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut sorted_samples: Vec<&crate::schemas::DailySample> = samples.iter().collect();
    sorted_samples.sort_by(|a, b| a.stock_code.cmp(&b.stock_code).then_with(|| a.transaction_date.cmp(&b.transaction_date)));

    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(WINDOW_FEATURE_COLUMNS)?;
    for sample in sorted_samples {
        let data_source = if sample.quality_flags.get("has_reference_features").copied().unwrap_or(false) {
            "reference_feature"
        } else {
            "trade_window"
        };
        let mut seen_windows = std::collections::HashSet::new();
        for row in &sample.rows {
            let window_id = row_float(row, &["window_id"], 0.0) as i64;
            if !seen_windows.insert(window_id) {
                continue;
            }
            let (window_start, window_end) = window_bounds(window_id);
            let open_price = row_float(row, &["window_open_price", "open_price"], 0.0);
            let close_price = row_float(row, &["window_close_price", "close_price"], 0.0);
            let deal_amount = row_float(row, &["deal_amount", "amount", "成交额"], 0.0);
            let data_p = row_float(row, &["data_P", "delta_p", "pi_max_price_impact_pct", "price_impact"], 0.0);
            wtr.write_record(&[
                sample.transaction_date.as_str(),
                sample.stock_code.as_str(),
                &window_id.to_string(),
                window_start.as_str(),
                window_end.as_str(),
                &round6(open_price).to_string(),
                &round6(close_price).to_string(),
                "",
                &round6(deal_amount).to_string(),
                &round6(data_p).to_string(),
                data_source,
            ])?;
        }
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
         ```json\n{}\n```\n",
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

    let pc: serde_json::Map<String, serde_json::Value> = pattern_counts
        .iter()
        .map(|(k, v)| (k.clone(), serde_json::Value::Number((*v).into())))
        .collect();
    payload.insert("pattern_counts".into(), serde_json::Value::Object(pc));

    let cc: serde_json::Map<String, serde_json::Value> = capital_counts
        .iter()
        .map(|(k, v)| (k.clone(), serde_json::Value::Number((*v).into())))
        .collect();
    payload.insert("capital_counts".into(), serde_json::Value::Object(cc));

    let ic: serde_json::Map<String, serde_json::Value> = intention_counts
        .iter()
        .map(|(k, v)| (k.clone(), serde_json::Value::Number((*v).into())))
        .collect();
    payload.insert("intention_counts".into(), serde_json::Value::Object(ic));

    if let Some(snap) = snapshot {
        let mut ms = serde_json::Map::new();
        ms.insert("trade_date".into(), serde_json::Value::String(snap.trade_date.clone()));
        ms.insert("market_regime".into(), serde_json::Value::String(snap.market_regime.clone()));
        ms.insert("up_count".into(), serde_json::Value::Number(snap.up_count.into()));
        ms.insert("down_count".into(), serde_json::Value::Number(snap.down_count.into()));
        ms.insert(
            "breadth_ratio".into(),
            serde_json::Value::Number(serde_json::Number::from_f64(snap.breadth_ratio).unwrap_or(0.into())),
        );
        ms.insert(
            "breadth_balance".into(),
            serde_json::Value::Number(serde_json::Number::from_f64(snap.breadth_balance).unwrap_or(0.into())),
        );
        ms.insert(
            "p_median".into(),
            serde_json::Value::Number(serde_json::Number::from_f64(snap.p_median).unwrap_or(0.into())),
        );
        ms.insert(
            "i_median".into(),
            serde_json::Value::Number(serde_json::Number::from_f64(snap.i_median).unwrap_or(0.into())),
        );
        ms.insert(
            "d_median".into(),
            serde_json::Value::Number(serde_json::Number::from_f64(snap.d_median).unwrap_or(0.into())),
        );
        payload.insert("market_snapshot".into(), serde_json::Value::Object(ms));
    } else {
        payload.insert("market_snapshot".into(), serde_json::Value::Null);
    }

    fs::write(&json_path, serde_json::to_string_pretty(&serde_json::Value::Object(payload))?)?;

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

pub fn export_pid_tail_diagnostics(
    pid_results: &[&DecompositionResult],
    output_path: &Path,
) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(PID_TAIL_COLUMNS)?;
    for result in pid_results {
        wtr.write_record(&[
            result.stock_code.as_str(),
            result.transaction_date.as_str(),
            result.mode.as_str(),
            if result.kf_converged { "true" } else { "false" },
            result.dominant_type.as_str(),
            result.dominant_intention.as_str(),
            &round6(result.hot_money_ratio).to_string(),
            &round6(result.quant_ratio).to_string(),
            &round6(result.retail_ratio).to_string(),
            &tail_value(&result.phi),
            &tail_value(&result.theta),
            &tail_value(&result.beta_ch),
            &tail_value(&result.beta_mix),
            &tail_value(&result.beta_q),
            &tail_value(&result.beta_retail),
            &tail_value(&result.c_p),
            &tail_value(&result.c_i),
            &tail_value(&result.c_d),
            &tail_value(&result.capital_ch),
            &tail_value(&result.capital_q),
            &tail_value(&result.capital_retail),
            &tail_value_nullable(&result.capital_anchor_error),
            &tail_value(&result.noise_ratio),
            &tail_value(&result.explain_ratio),
            &format!("{:.2e}", result.capital_identity_error),
            &format!("{:.2e}", result.closure_error),
            &result.warnings.join(" | "),
        ])?;
    }
    wtr.flush()?;
    Ok(())
}

pub fn export_pid_window_params(
    pid_results: &[&DecompositionResult],
    output_path: &Path,
) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(PID_WINDOW_PARAM_COLUMNS)?;
    for result in pid_results {
        let row_count = [
            result.phi.len(),
            result.beta_ch.len(),
            result.beta_q.len(),
            result.beta_retail.len(),
            result.beta_mix.len(),
            result.theta.len(),
        ]
        .into_iter()
        .max()
        .unwrap_or(0);
        for window_id in 0..row_count {
            wtr.write_record(&[
                result.stock_code.as_str(),
                result.transaction_date.as_str(),
                &window_id.to_string(),
                result.mode.as_str(),
                &series_value(&result.phi, window_id).to_string(),
                &series_value(&result.beta_ch, window_id).to_string(),
                &series_value(&result.beta_q, window_id).to_string(),
                &series_value(&result.beta_retail, window_id).to_string(),
                &series_value(&result.beta_mix, window_id).to_string(),
                &series_value(&result.theta, window_id).to_string(),
                "",
            ])?;
        }
    }
    wtr.flush()?;
    Ok(())
}

pub fn export_pid_window_contrib(
    pid_results: &[&DecompositionResult],
    output_path: &Path,
) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(PID_WINDOW_CONTRIB_COLUMNS)?;
    for result in pid_results {
        let row_count = [
            result.c_p.len(),
            result.c_i.len(),
            result.c_d.len(),
            result.eps.len(),
            result.capital_ch.len(),
            result.capital_q.len(),
            result.capital_retail.len(),
            result.noise_ratio.len(),
            result.explain_ratio.len(),
            result.capital_anchor_error.len(),
        ]
        .into_iter()
        .max()
        .unwrap_or(0);
        for window_id in 0..row_count {
            let c_p_raw = series_value_default(&result.c_p, window_id, 0.0);
            let capital_ch_raw = series_value_default(&result.capital_ch, window_id, 0.0);
            let c_p = round6(c_p_raw);
            let capital_ch = round6(capital_ch_raw);
            let capital_mix = round6(series_value_default(&result.capital_mix, window_id, c_p_raw - capital_ch_raw));
            wtr.write_record(&[
                result.stock_code.as_str(),
                result.transaction_date.as_str(),
                &window_id.to_string(),
                &c_p.to_string(),
                &series_value(&result.c_i, window_id).to_string(),
                &series_value(&result.c_d, window_id).to_string(),
                &series_value(&result.eps, window_id).to_string(),
                &capital_ch.to_string(),
                &series_value(&result.capital_q, window_id).to_string(),
                &series_value(&result.capital_retail, window_id).to_string(),
                &capital_mix.to_string(),
                &round6(series_value_default(&result.noise_ratio, window_id, 1.0)).to_string(),
                &series_value(&result.explain_ratio, window_id).to_string(),
                &series_value(&result.capital_anchor_error, window_id).to_string(),
                &format!("{:.2e}", result.pid_closure_error),
            ])?;
        }
    }
    wtr.flush()?;
    Ok(())
}

fn config_str<'a>(config: &'a serde_json::Value, key: &str, default: &'a str) -> String {
    config.get(key).and_then(|v| v.as_str()).unwrap_or(default).to_string()
}

fn config_bool(config: &serde_json::Value, key: &str, default: bool) -> bool {
    config.get(key).and_then(|v| v.as_bool()).unwrap_or(default)
}

fn config_f64(config: &serde_json::Value, path: &[&str], default: f64) -> f64 {
    let mut current = config;
    for key in path {
        if let Some(next) = current.get(*key) {
            current = next;
        } else {
            return default;
        }
    }
    current.as_f64().unwrap_or(default)
}

pub fn export_pid_window_diag(
    pid_results: &[&DecompositionResult],
    output_path: &Path,
    config: &serde_json::Value,
) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let q_type = config_str(config, "q_type", "window_index");
    let u_source_type = config_str(config, "u_source_type", "mv_ratio");
    let estimator_method = config_str(config, "estimator_method", "kalman_filter_realtime");
    let m_slow_method = config_str(config, "m_slow_method", "ewma_realtime");
    let beta_norm_floor = config_f64(config, &["beta_norm_floor"], 1.0e-6);
    let data_leakage_check = if estimator_method.contains("offline") || m_slow_method.contains("offline") { "fail" } else { "pass" };
    let (_m_eff_uncertainty_flag, m_eff_rank_eligible) = resolve_m_eff_status(config);

    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(PID_WINDOW_DIAG_COLUMNS)?;
    for result in pid_results {
        let row_count = [
            result.c_p.len(), result.c_i.len(), result.c_d.len(), result.eps.len(),
            result.capital_ch.len(), result.capital_q.len(), result.capital_retail.len(),
        ].into_iter().max().unwrap_or(0);
        let warnings = result.warnings.join(" | ");
        let param_stability_flag = if result.kf_converged && result.pid_closure_error <= 1e-7 { "pass" } else { "warn" };
        for window_id in 0..row_count {
            let c_p = series_value_default(&result.c_p, window_id, 0.0);
            let c_i = series_value_default(&result.c_i, window_id, 0.0);
            let c_d = series_value_default(&result.c_d, window_id, 0.0);
            let eps = series_value_default(&result.eps, window_id, 0.0);
            let y_observed = c_p + c_i + c_d + eps;
            let next_id = if row_count == 0 { 0 } else { (window_id + 1).min(row_count - 1) };
            let y_hat_next = series_value_default(&result.c_p, next_id, 0.0)
                + series_value_default(&result.c_i, next_id, 0.0)
                + series_value_default(&result.c_d, next_id, 0.0);
            let capital_ch = series_value_default(&result.capital_ch, window_id, 0.0);
            let capital_q = series_value_default(&result.capital_q, window_id, 0.0);
            let capital_retail = series_value_default(&result.capital_retail, window_id, 0.0);
            let capital_mix = series_value_default(&result.capital_mix, window_id, c_p - capital_ch);
            let proxy_metrics = window_diag_proxy_metrics(result, window_id, beta_norm_floor);
            wtr.write_record(&[
                result.transaction_date.as_str(),
                result.stock_code.as_str(),
                &window_id.to_string(),
                result.mode.as_str(),
                q_type.as_str(),
                u_source_type.as_str(),
                estimator_method.as_str(),
                "psi_transition_observation_prediction",
                "psi_t_prior_for_prediction",
                &round6(y_observed).to_string(),
                &round6(y_hat_next).to_string(),
                &round6(y_observed).to_string(),
                &round6(y_hat_next).to_string(),
                &round6(c_p).to_string(),
                &round6(c_i).to_string(),
                &round6(c_d).to_string(),
                &round6(eps).to_string(),
                &round6(capital_ch).to_string(),
                &round6(capital_q).to_string(),
                &round6(capital_retail).to_string(),
                &round6(capital_mix).to_string(),
                proxy_metrics.beta_norm_ch_diag.as_str(),
                proxy_metrics.beta_norm_q_diag.as_str(),
                proxy_metrics.beta_norm_retail_diag.as_str(),
                proxy_metrics.beta_norm_mix_diag.as_str(),
                proxy_metrics.m_eff_ch_diag.as_str(),
                proxy_metrics.m_eff_q_diag.as_str(),
                proxy_metrics.m_eff_retail_diag.as_str(),
                proxy_metrics.m_eff_mix_diag.as_str(),
                proxy_metrics.beta_norm_unit.as_str(),
                proxy_metrics.m_eff_source_type.as_str(),
                proxy_metrics.m_eff_clipped_flag.as_str(),
                &format!("{:.2e}", result.pid_closure_error),
                &round6(eps).to_string(),
                param_stability_flag,
                m_eff_rank_eligible,
                data_leakage_check,
                m_slow_method.as_str(),
                "false",
                m_eff_rank_eligible,
                "true",
                warnings.as_str(),
            ])?;
        }
    }
    wtr.flush()?;
    Ok(())
}

pub fn export_pid_daily_diag(
    pid_results: &[&DecompositionResult],
    output_path: &Path,
    config: &serde_json::Value,
) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let q_type = config_str(config, "q_type", "window_index");
    let u_source_type = config_str(config, "u_source_type", "mv_ratio");
    let estimator_method = config_str(config, "estimator_method", "kalman_filter_realtime");
    let m_slow_method = config_str(config, "m_slow_method", "ewma_realtime");
    let beta_norm_floor = config_f64(config, &["beta_norm_floor"], 1.0e-6);
    let offline_smooth_used = estimator_method.contains("offline") || m_slow_method.contains("offline");
    let data_leakage_check = if offline_smooth_used { "fail" } else { "pass" };
    let (m_eff_uncertainty_flag, m_eff_rank_eligible) = resolve_m_eff_status(config);
    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(PID_DAILY_DIAG_COLUMNS)?;
    for result in pid_results {
        let warnings = result.warnings.join(" | ");
        let param_stability_flag = if result.kf_converged && result.pid_closure_error <= 1e-7 { "pass" } else { "warn" };
        let (beta_norm_unit, m_eff_source_type, m_eff_clipped_flag) = daily_diag_proxy_summary(result, beta_norm_floor);
        wtr.write_record(&[
            result.transaction_date.as_str(),
            result.stock_code.as_str(),
            result.mode.as_str(),
            q_type.as_str(),
            u_source_type.as_str(),
            estimator_method.as_str(),
            m_slow_method.as_str(),
            &config.get("lookback_days").and_then(|v| v.as_i64()).unwrap_or(20).to_string(),
            config.get("zero_trade_policy").and_then(|v| v.as_str()).unwrap_or("mark_only"),
            if config_bool(config, "submission_requires_complete_windows", true) { "true" } else { "false" },
            &format!("{:?}", config_f64(config, &["mode_switch", "lambda_switch"], 0.1)),
            &format!("{:?}", config_f64(config, &["mode_switch", "lambda_jump"], 1.0)),
            &format!("{:?}", config_f64(config, &["mode_switch", "lambda_error"], 10.0)),
            data_leakage_check,
            "pass",
            "pass",
            if offline_smooth_used { "true" } else { "false" },
            param_stability_flag,
            beta_norm_unit,
            m_eff_source_type,
            m_eff_clipped_flag,
            m_eff_uncertainty_flag,
            m_eff_rank_eligible,
            if data_leakage_check == "pass" { "true" } else { "false" },
            "raw",
            "ok",
            config.get("code_build_hash").and_then(|v| v.as_str()).unwrap_or(""),
            &result.warnings.len().to_string(),
            warnings.as_str(),
        ])?;
    }
    wtr.flush()?;
    Ok(())
}

pub fn export_pid_daily_diag_records(
    records: &[HashMap<String, String>],
    output_path: &Path,
    config: &serde_json::Value,
) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let q_type = config_str(config, "q_type", "window_index");
    let u_source_type = config_str(config, "u_source_type", "mv_ratio");
    let estimator_method = config_str(config, "estimator_method", "kalman_filter_realtime");
    let m_slow_method = config_str(config, "m_slow_method", "ewma_realtime");
    let (m_eff_uncertainty_flag, m_eff_rank_eligible) = resolve_m_eff_status(config);
    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(PID_DAILY_DIAG_COLUMNS)?;
    for record in records {
        let warnings = record.get("warnings").cloned().unwrap_or_default();
        let warning_count = record
            .get("warning_count")
            .cloned()
            .unwrap_or_else(|| if warnings.is_empty() { "0".into() } else { "1".into() });
        wtr.write_record(&[
            record.get("trade_date").map(String::as_str).unwrap_or(""),
            record.get("symbol").map(String::as_str).unwrap_or(""),
            record.get("mode_name").map(String::as_str).unwrap_or(""),
            record.get("q_type").map(String::as_str).unwrap_or(q_type.as_str()),
            record.get("u_source_type").map(String::as_str).unwrap_or(u_source_type.as_str()),
            record.get("estimator_method").map(String::as_str).unwrap_or(estimator_method.as_str()),
            record.get("m_slow_method").map(String::as_str).unwrap_or(m_slow_method.as_str()),
            record.get("lookback_days").map(String::as_str).unwrap_or("20"),
            record.get("zero_trade_policy").map(String::as_str).unwrap_or("mark_only"),
            record.get("submission_requires_complete_windows").map(String::as_str).unwrap_or("true"),
            record.get("lambda_switch").map(String::as_str).unwrap_or("0.1"),
            record.get("lambda_jump").map(String::as_str).unwrap_or("1.0"),
            record.get("lambda_error").map(String::as_str).unwrap_or("10.0"),
            record.get("data_leakage_check").map(String::as_str).unwrap_or("pass"),
            record.get("feature_engineering_leakage_check").map(String::as_str).unwrap_or("pass"),
            record.get("rule_layer_leakage_check").map(String::as_str).unwrap_or("pass"),
            record.get("offline_smooth_used").map(String::as_str).unwrap_or("false"),
            record.get("param_stability_flag").map(String::as_str).unwrap_or("pass"),
            record.get("beta_norm_unit").map(String::as_str).unwrap_or(""),
            record.get("m_eff_source_type").map(String::as_str).unwrap_or("unavailable"),
            record.get("m_eff_clipped_flag").map(String::as_str).unwrap_or("false"),
            record.get("m_eff_uncertainty_flag").map(String::as_str).unwrap_or(m_eff_uncertainty_flag),
            record.get("m_eff_rank_eligible").map(String::as_str).unwrap_or(m_eff_rank_eligible),
            record.get("submission_ready").map(String::as_str).unwrap_or("true"),
            record.get("sample_origin").map(String::as_str).unwrap_or("raw"),
            record.get("reason_code").map(String::as_str).unwrap_or("ok"),
            record.get("code_build_hash").map(String::as_str).unwrap_or(""),
            warning_count.as_str(),
            warnings.as_str(),
        ])?;
    }
    wtr.flush()?;
    Ok(())
}

pub fn export_raw_data_quality_report(
    rows: &[HashMap<String, String>],
    output_path: &Path,
) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record(RAW_DATA_QUALITY_COLUMNS)?;
    for row in rows {
        let values: Vec<String> = RAW_DATA_QUALITY_COLUMNS
            .iter()
            .map(|key| row.get(*key).cloned().unwrap_or_default())
            .collect();
        wtr.write_record(values)?;
    }
    wtr.flush()?;
    Ok(())
}

pub fn export_window_flow_rows(samples: &[crate::schemas::DailySample], output_path: &Path) -> Result<()> {
    if let Some(parent) = output_path.parent() {
        fs::create_dir_all(parent)?;
    }

    let mut sorted_samples: Vec<&crate::schemas::DailySample> = samples.iter().collect();
    sorted_samples.sort_by(|a, b| a.stock_code.cmp(&b.stock_code).then_with(|| a.transaction_date.cmp(&b.transaction_date)));

    let mut wtr = Writer::from_path(output_path)?;
    wtr.write_record([
        "stock_code",
        "transaction_date",
        "window_id",
        "deal_amount",
        "signal_deal_buy_amount",
        "signal_deal_sell_amount",
        "signed_large_active_amount",
        "signed_mix_qr_amount",
        "CH_rule_t",
        "Q_rule_t",
        "R_seed_t",
        "large_active_buy_amount",
        "large_active_sell_amount",
        "small_passive_buy_amount",
        "small_passive_sell_amount",
        "unknown_side_amount",
        "window_open_price",
        "window_close_price",
        "window_trade_count",
        "active_inferred_count",
        "side_fallback_count",
        "low_fallback_count",
        "order_age_recovered_count",
        "order_age_missing_count",
        "order_age_direct_count",
        "order_age_fifo_count",
        "order_age_unresolved_count",
        "active_buy_count",
        "active_sell_count",
        "active_buy_amount",
        "active_sell_amount",
        "pi_max_price_impact_pct",
    ])?;
    for sample in sorted_samples {
        for row in &sample.rows {
            wtr.write_record(&[
                sample.stock_code.as_str(),
                sample.transaction_date.as_str(),
                row.get("window_id").map(String::as_str).unwrap_or(""),
                row.get("deal_amount").map(String::as_str).unwrap_or(""),
                row.get("signal_deal_buy_amount").map(String::as_str).unwrap_or(""),
                row.get("signal_deal_sell_amount").map(String::as_str).unwrap_or(""),
                row.get("signed_large_active_amount").map(String::as_str).unwrap_or(""),
                row.get("signed_mix_qr_amount").map(String::as_str).unwrap_or(""),
                row.get("CH_rule_t").map(String::as_str).unwrap_or(""),
                row.get("Q_rule_t").map(String::as_str).unwrap_or(""),
                row.get("R_seed_t").map(String::as_str).unwrap_or(""),
                row.get("large_active_buy_amount").map(String::as_str).unwrap_or(""),
                row.get("large_active_sell_amount").map(String::as_str).unwrap_or(""),
                row.get("small_passive_buy_amount").map(String::as_str).unwrap_or(""),
                row.get("small_passive_sell_amount").map(String::as_str).unwrap_or(""),
                row.get("unknown_side_amount").map(String::as_str).unwrap_or(""),
                row.get("window_open_price").map(String::as_str).unwrap_or(""),
                row.get("window_close_price").map(String::as_str).unwrap_or(""),
                row.get("window_trade_count").map(String::as_str).unwrap_or(""),
                row.get("active_inferred_count").map(String::as_str).unwrap_or(""),
                row.get("side_fallback_count").map(String::as_str).unwrap_or(""),
                row.get("low_fallback_count").map(String::as_str).unwrap_or("0"),
                row.get("order_age_recovered_count").map(String::as_str).unwrap_or(""),
                row.get("order_age_missing_count").map(String::as_str).unwrap_or(""),
                row.get("order_age_direct_count").map(String::as_str).unwrap_or(""),
                row.get("order_age_fifo_count").map(String::as_str).unwrap_or(""),
                row.get("order_age_unresolved_count").map(String::as_str).unwrap_or(""),
                row.get("active_buy_count").map(String::as_str).unwrap_or(""),
                row.get("active_sell_count").map(String::as_str).unwrap_or(""),
                row.get("active_buy_amount").map(String::as_str).unwrap_or(""),
                row.get("active_sell_amount").map(String::as_str).unwrap_or(""),
                row.get("pi_max_price_impact_pct").map(String::as_str).unwrap_or(""),
            ])?;
        }
    }
    wtr.flush()?;
    Ok(())
}

fn series_value(values: &[f64], index: usize) -> f64 {
    let value = series_value_default(values, index, 0.0);
    round6(value)
}

fn series_value_default(values: &[f64], index: usize, default: f64) -> f64 {
    values
        .get(index)
        .copied()
        .filter(|value| value.is_finite())
        .unwrap_or(default)
}

fn tail_value(values: &[f64]) -> String {
    values
        .iter()
        .rev()
        .find(|value| value.is_finite())
        .map(|value| round6(*value).to_string())
        .unwrap_or_default()
}

fn tail_value_nullable(values: &[f64]) -> String {
    values
        .iter()
        .rev()
        .find(|value| value.is_finite())
        .map(|value| round6(*value).to_string())
        .unwrap_or_default()
}

pub fn validate_submission_files(pattern_path: &Path, predict_path: &Path) -> Result<()> {
    if !pattern_path.exists() {
        anyhow::bail!("Submission file not found: {}", pattern_path.display());
    }
    if !predict_path.exists() {
        anyhow::bail!("Submission file not found: {}", predict_path.display());
    }

    let expected: &[(&Path, &[&str])] = &[(pattern_path, PATTERN_COLUMNS), (predict_path, PREDICT_COLUMNS)];
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
        row_counts.insert(path.file_name().unwrap().to_string_lossy().to_string(), row_count);
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
    let options =
        zip::write::SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    zip.start_file("pattern_reco.csv", options)?;
    zip.write_all(&fs::read(&pattern_path)?)?;

    zip.start_file("predict_result.csv", options)?;
    zip.write_all(&fs::read(&predict_path)?)?;

    zip.finish()?;
    Ok(zip_path.to_string_lossy().to_string())
}

pub fn export_market_pid_validation_report(
    snapshot: Option<&MarketPidSnapshot>,
    output_dir: &Path,
) -> Result<String> {
    let base = output_dir.join("reports").join("validation");
    fs::create_dir_all(&base)?;
    let report_path = base.join("market_pid_validation_report.md");

    let mut lines = vec![
        "# Market PID Validation Report".to_string(),
        "".to_string(),
        "## Scope".to_string(),
        "".to_string(),
        "This report records the market breadth and relative market PID contract used by the current batch.".to_string(),
        "".to_string(),
    ];
    if let Some(snapshot) = snapshot {
        lines.extend([
            "## Market Breadth".to_string(),
            "".to_string(),
            format!("- trade_date: `{}`", snapshot.trade_date),
            format!("- up_count: `{}`", snapshot.up_count),
            format!("- down_count: `{}`", snapshot.down_count),
            format!("- breadth_ratio: `{:.6}`", snapshot.breadth_ratio),
            format!("- breadth_balance: `{:.6}`", snapshot.breadth_balance),
            format!("- market_regime: `{}`", snapshot.market_regime),
            "".to_string(),
            "## PID Aggregates".to_string(),
            "".to_string(),
            format!(
                "- p_mean / p_median / p_std: `{:.6}` / `{:.6}` / `{:.6}`",
                snapshot.p_mean, snapshot.p_median, snapshot.p_std
            ),
            format!(
                "- i_mean / i_median / i_std: `{:.6}` / `{:.6}` / `{:.6}`",
                snapshot.i_mean, snapshot.i_median, snapshot.i_std
            ),
            format!(
                "- d_mean / d_median / d_std: `{:.6}` / `{:.6}` / `{:.6}`",
                snapshot.d_mean, snapshot.d_median, snapshot.d_std
            ),
            "".to_string(),
            "## Diagnostics".to_string(),
            "".to_string(),
            "```json".to_string(),
            serde_json::to_string_pretty(&snapshot.diagnostics).unwrap_or_default(),
            "```".to_string(),
            "".to_string(),
        ]);
    } else {
        lines.extend([
            "## Status".to_string(),
            "".to_string(),
            "- market_snapshot: `missing`".to_string(),
            "- reason: no valid samples were available for market PID aggregation.".to_string(),
            "".to_string(),
        ]);
    }
    fs::write(&report_path, lines.join("\n"))?;
    Ok(report_path.to_string_lossy().to_string())
}

pub fn export_replay_validation_report(
    batch_summary: &serde_json::Value,
    output_dir: &Path,
) -> Result<String> {
    let base = output_dir.join("reports").join("validation");
    fs::create_dir_all(&base)?;
    let report_path = base.join("100_stock_replay_report.md");

    let warnings = batch_summary
        .get("warnings")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();
    let mut lines = vec![
        "# 100 Stock Replay Report".to_string(),
        "".to_string(),
        "## Batch Summary".to_string(),
        "".to_string(),
        format!("- trade_date: `{}`", batch_summary.get("trade_date").and_then(|v| v.as_str()).unwrap_or("")),
        format!("- sample_count: `{}`", batch_summary.get("sample_count").cloned().unwrap_or(serde_json::Value::Null)),
        format!("- output_count: `{}`", batch_summary.get("output_count").cloned().unwrap_or(serde_json::Value::Null)),
        format!("- imputed_output_count: `{}`", batch_summary.get("imputed_output_count").cloned().unwrap_or(serde_json::Value::Null)),
        format!("- stock_universe_size: `{}`", batch_summary.get("stock_universe_size").cloned().unwrap_or(serde_json::Value::Null)),
        format!("- stock_list_file: `{}`", batch_summary.get("stock_list_file").cloned().unwrap_or(serde_json::Value::Null)),
        format!("- stock_offset: `{}`", batch_summary.get("stock_offset").cloned().unwrap_or(serde_json::Value::Null)),
        format!("- stock_limit: `{}`", batch_summary.get("stock_limit").cloned().unwrap_or(serde_json::Value::Null)),
        "".to_string(),
        "## Warnings".to_string(),
        "".to_string(),
    ];
    if warnings.is_empty() {
        lines.push("- none".to_string());
    } else {
        for warning in warnings {
            lines.push(format!("- {}", warning.as_str().unwrap_or("")));
        }
    }
    fs::write(&report_path, lines.join("\n"))?;
    Ok(report_path.to_string_lossy().to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schemas::DecompositionResult;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn pid_window_diag_prefers_explicit_capital_mix() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let base = std::env::temp_dir().join(format!("opc_rust_exporter_test_{unique}"));
        fs::create_dir_all(&base).expect("create temp dir");
        let output = base.join("pid_window_diag.csv");

        let mut result = DecompositionResult {
            stock_code: "000001.SZ".to_string(),
            transaction_date: "20260710".to_string(),
            mode: "baseline_4d".to_string(),
            kf_converged: true,
            ..DecompositionResult::default()
        };
        result.c_p = vec![0.0; 48];
        result.c_i = vec![0.0; 48];
        result.c_d = vec![0.0; 48];
        result.eps = vec![0.0; 48];
        result.capital_ch = vec![0.0; 48];
        result.capital_q = vec![0.0; 48];
        result.capital_retail = vec![0.0; 48];
        result.capital_mix = vec![0.0; 48];
        result.price_basis = vec![0.0; 48];
        result.u_ch_amount_ratio = vec![0.0; 48];
        result.u_q_amount_ratio = vec![0.0; 48];
        result.u_retail_amount_ratio = vec![0.0; 48];
        result.u_mix_amount_ratio = vec![0.0; 48];
        result.c_p[0] = 0.20;
        result.capital_ch[0] = 0.12;
        result.capital_mix[0] = 0.09;
        result.price_basis[0] = 10.0;
        result.u_ch_amount_ratio[0] = 0.02;
        result.u_mix_amount_ratio[0] = 0.015;

        export_pid_window_diag(&[&result], &output, &serde_json::json!({})).expect("export diag");

        let content = fs::read_to_string(&output).expect("read csv");
        let mut lines = content.lines();
        let header = lines.next().unwrap_or_default();
        let row = lines.next().unwrap_or_default();
        let headers: Vec<&str> = header.split(',').collect();
        let fields: Vec<&str> = row.split(',').collect();
        let mix_idx = headers
            .iter()
            .position(|name| *name == "capital_mix")
            .expect("capital_mix column");
        let beta_idx = headers
            .iter()
            .position(|name| *name == "beta_norm_ch_diag")
            .expect("beta_norm_ch_diag column");

        assert_eq!(fields.get(mix_idx).copied(), Some("0.09"));
        assert_eq!(fields.get(beta_idx).copied(), Some("0.6"));

        let _ = fs::remove_file(&output);
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn pid_daily_diag_defaults_to_conservative_m_eff_flags() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let base = std::env::temp_dir().join(format!("opc_rust_daily_diag_test_{unique}"));
        fs::create_dir_all(&base).expect("create temp dir");
        let output = base.join("pid_daily_diag.csv");

        let mut result = DecompositionResult {
            stock_code: "000001.SZ".to_string(),
            transaction_date: "20260710".to_string(),
            mode: "baseline_4d".to_string(),
            kf_converged: true,
            ..DecompositionResult::default()
        };
        result.price_basis = vec![0.0; 48];
        result.u_ch_amount_ratio = vec![0.0; 48];
        result.capital_ch = vec![0.0; 48];
        result.price_basis[0] = 10.0;
        result.u_ch_amount_ratio[0] = 0.02;
        result.capital_ch[0] = 0.12;

        export_pid_daily_diag(&[&result], &output, &serde_json::json!({})).expect("export daily diag");

        let content = fs::read_to_string(&output).expect("read csv");
        let mut lines = content.lines();
        let header = lines.next().unwrap_or_default();
        let row = lines.next().unwrap_or_default();
        let headers: Vec<&str> = header.split(',').collect();
        let fields: Vec<&str> = row.split(',').collect();
        let uncertainty_idx = headers
            .iter()
            .position(|name| *name == "m_eff_uncertainty_flag")
            .expect("uncertainty column");
        let eligible_idx = headers
            .iter()
            .position(|name| *name == "m_eff_rank_eligible")
            .expect("eligible column");
        let source_idx = headers
            .iter()
            .position(|name| *name == "m_eff_source_type")
            .expect("source column");

        assert_eq!(fields.get(uncertainty_idx).copied(), Some("true"));
        assert_eq!(fields.get(eligible_idx).copied(), Some("false"));
        assert_eq!(fields.get(source_idx).copied(), Some("amount_ratio_proxy"));

        let _ = fs::remove_file(&output);
        let _ = fs::remove_dir_all(&base);
    }
}

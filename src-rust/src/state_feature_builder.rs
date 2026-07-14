use crate::schemas::{DailySample, DecompositionResult, StateFeature};
use std::collections::HashMap;

const STRUCTURAL_MODES: &[&str] = &["baseline_4d", "diag_5d", "full_5d"];

pub fn build_state_features(sample: &DailySample, pid_result: Option<&DecompositionResult>) -> Vec<StateFeature> {
    let rows_by_window = rows_by_window(&sample.rows);
    let window_count = infer_window_count(&rows_by_window, pid_result);
    let mode_name = pid_result
        .map(|result| {
            if result.mode.trim().is_empty() {
                "rule_base".to_string()
            } else {
                result.mode.clone()
            }
        })
        .unwrap_or_else(|| "rule_base".to_string());
    let is_structural = pid_result.is_some() && STRUCTURAL_MODES.contains(&mode_name.as_str());
    let mut features = Vec::with_capacity(window_count);

    for index in 0..window_count {
        let row = rows_by_window.get(&index);
        let ch_rule = row
            .and_then(|row| row_f64(row, &["CH_rule_t", "signed_large_active_amount"]))
            .unwrap_or(0.0);
        let mut q_rule = row.and_then(|row| row_f64(row, &["Q_rule_t"])).unwrap_or(0.0);
        let mut r_seed = row.and_then(|row| row_f64(row, &["R_seed_t"])).unwrap_or(0.0);
        if let Some(row) = row {
            if !row.contains_key("Q_rule_t") && !row.contains_key("R_seed_t") {
                q_rule = row_f64(row, &["signed_mix_qr_amount"]).unwrap_or(0.0);
                r_seed = 0.0;
            }
        }

        let mut feature = StateFeature {
            stock_code: sample.stock_code.clone(),
            transaction_date: sample.transaction_date.clone(),
            window_id: index.to_string(),
            ch_rule_t: ch_rule,
            q_rule_t: q_rule,
            r_seed_t: r_seed,
            capital_ch_rule_approx: ch_rule,
            capital_q_rule_approx: q_rule,
            capital_retail_rule_approx: r_seed,
            mode_name: mode_name.clone(),
            is_structural_output: is_structural,
            ..StateFeature::default()
        };
        if let Some(result) = pid_result {
            attach_pid_fields(&mut feature, result, index, is_structural);
        }
        features.push(feature);
    }

    features
}

pub fn tail_state_feature(sample: &DailySample, pid_result: Option<&DecompositionResult>) -> Option<StateFeature> {
    build_state_features(sample, pid_result).into_iter().last()
}

fn attach_pid_fields(
    feature: &mut StateFeature,
    pid_result: &DecompositionResult,
    index: usize,
    is_structural: bool,
) {
    feature.phi = series_value(&pid_result.phi, index).or_else(|| series_value(&pid_result.inertia, index));
    feature.theta = series_value(&pid_result.theta, index).or_else(|| series_value(&pid_result.damping, index));
    feature.beta_ch = series_value(&pid_result.beta_ch, index);
    feature.beta_q = series_value(&pid_result.beta_q, index);
    feature.beta_mix = series_value(&pid_result.beta_mix, index);
    feature.beta_retail = series_value(&pid_result.beta_retail, index);
    feature.c_p = series_value(&pid_result.c_p, index);
    feature.c_i = series_value(&pid_result.c_i, index);
    feature.c_d = series_value(&pid_result.c_d, index);
    feature.eps = series_value(&pid_result.eps, index);
    feature.noise_ratio = series_value(&pid_result.noise_ratio, index);
    feature.explain_ratio = series_value(&pid_result.explain_ratio, index);
    feature.capital_anchor_error = series_value(&pid_result.capital_anchor_error, index);

    if is_structural {
        feature.capital_ch = series_value(&pid_result.capital_ch, index);
        feature.capital_mix = series_value(&pid_result.capital_mix, index);
        if pid_result.mode != "baseline_4d" {
            feature.capital_q = series_value(&pid_result.capital_q, index);
            feature.capital_retail = series_value(&pid_result.capital_retail, index);
            if let Some(capital_q) = feature.capital_q {
                feature.rule_error_q = Some(relative_error(feature.q_rule_t, capital_q));
            }
            if let Some(capital_retail) = feature.capital_retail {
                feature.rule_error_retail = Some(relative_error(feature.r_seed_t, capital_retail));
            }
        }
    }
}

fn rows_by_window(rows: &[HashMap<String, String>]) -> HashMap<usize, &HashMap<String, String>> {
    let mut mapped = HashMap::new();
    for row in rows {
        if let Some(window_id) = row.get("window_id").and_then(|value| value.parse::<usize>().ok()) {
            mapped.insert(window_id, row);
        }
    }
    mapped
}

fn infer_window_count(
    rows_by_window: &HashMap<usize, &HashMap<String, String>>,
    pid_result: Option<&DecompositionResult>,
) -> usize {
    let row_count = rows_by_window.keys().max().map(|value| value + 1).unwrap_or(0);
    let pid_lengths = pid_result
        .map(|result| {
            [
                result.c_p.len(),
                result.capital_ch.len(),
                result.noise_ratio.len(),
            ]
        })
        .unwrap_or([0, 0, 0]);
    48usize.max(row_count).max(*pid_lengths.iter().max().unwrap_or(&0))
}

fn row_f64(row: &HashMap<String, String>, names: &[&str]) -> Option<f64> {
    names
        .iter()
        .find_map(|name| row.get(*name))
        .and_then(|value| value.parse::<f64>().ok())
}

fn series_value(series: &[f64], index: usize) -> Option<f64> {
    series.get(index).copied().filter(|value| !value.is_nan())
}

fn relative_error(rule_value: f64, structural_value: f64) -> f64 {
    let denom = rule_value.abs().max(structural_value.abs()).max(1e-8);
    (rule_value - structural_value).abs() / denom
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rule_base_keeps_structural_capital_fields_empty() {
        let sample = DailySample {
            stock_code: "000001.SZ".to_string(),
            transaction_date: "20260710".to_string(),
            rows: vec![HashMap::from([
                ("window_id".to_string(), "0".to_string()),
                ("CH_rule_t".to_string(), "100".to_string()),
                ("Q_rule_t".to_string(), "50".to_string()),
                ("R_seed_t".to_string(), "-20".to_string()),
            ])],
            feature_summary: HashMap::new(),
            quality_flags: HashMap::new(),
        };
        let pid_result = DecompositionResult {
            stock_code: sample.stock_code.clone(),
            transaction_date: sample.transaction_date.clone(),
            mode: "rule_base".to_string(),
            ..DecompositionResult::default()
        };

        let feature = build_state_features(&sample, Some(&pid_result))
            .into_iter()
            .next()
            .unwrap_or_default();

        assert!(!feature.is_structural_output);
        assert_eq!(feature.capital_ch_rule_approx, 100.0);
        assert_eq!(feature.capital_q_rule_approx, 50.0);
        assert_eq!(feature.capital_retail_rule_approx, -20.0);
        assert_eq!(feature.capital_ch, None);
        assert_eq!(feature.capital_mix, None);
        assert_eq!(feature.capital_q, None);
        assert_eq!(feature.capital_retail, None);
    }

    #[test]
    fn baseline_4d_keeps_quant_retail_split_as_diagnostic_only() {
        let sample = DailySample {
            stock_code: "000001.SZ".to_string(),
            transaction_date: "20260710".to_string(),
            rows: vec![HashMap::from([
                ("window_id".to_string(), "0".to_string()),
                ("CH_rule_t".to_string(), "100".to_string()),
                ("Q_rule_t".to_string(), "50".to_string()),
                ("R_seed_t".to_string(), "20".to_string()),
            ])],
            feature_summary: HashMap::new(),
            quality_flags: HashMap::new(),
        };
        let pid_result = DecompositionResult {
            stock_code: sample.stock_code.clone(),
            transaction_date: sample.transaction_date.clone(),
            mode: "baseline_4d".to_string(),
            capital_ch: {
                let mut v = vec![0.0; 48];
                v[0] = 90.0;
                v
            },
            capital_mix: {
                let mut v = vec![0.0; 48];
                v[0] = 35.0;
                v
            },
            capital_q: {
                let mut v = vec![0.0; 48];
                v[0] = 25.0;
                v
            },
            capital_retail: {
                let mut v = vec![0.0; 48];
                v[0] = 10.0;
                v
            },
            ..DecompositionResult::default()
        };

        let feature = build_state_features(&sample, Some(&pid_result))
            .into_iter()
            .next()
            .unwrap_or_default();

        assert!(feature.is_structural_output);
        assert_eq!(feature.capital_ch, Some(90.0));
        assert_eq!(feature.capital_mix, Some(35.0));
        assert_eq!(feature.capital_q, None);
        assert_eq!(feature.capital_retail, None);
        assert_eq!(feature.rule_error_q, None);
        assert_eq!(feature.rule_error_retail, None);
    }

    #[test]
    fn diag_5d_exposes_rule_errors() {
        let sample = DailySample {
            stock_code: "000001.SZ".to_string(),
            transaction_date: "20260710".to_string(),
            rows: vec![HashMap::from([
                ("window_id".to_string(), "0".to_string()),
                ("CH_rule_t".to_string(), "100".to_string()),
                ("Q_rule_t".to_string(), "50".to_string()),
                ("R_seed_t".to_string(), "20".to_string()),
            ])],
            feature_summary: HashMap::new(),
            quality_flags: HashMap::new(),
        };
        let pid_result = DecompositionResult {
            stock_code: sample.stock_code.clone(),
            transaction_date: sample.transaction_date.clone(),
            mode: "diag_5d".to_string(),
            capital_ch: {
                let mut v = vec![0.0; 48];
                v[0] = 90.0;
                v
            },
            capital_mix: {
                let mut v = vec![0.0; 48];
                v[0] = 35.0;
                v
            },
            capital_q: {
                let mut v = vec![0.0; 48];
                v[0] = 25.0;
                v
            },
            capital_retail: {
                let mut v = vec![0.0; 48];
                v[0] = 10.0;
                v
            },
            ..DecompositionResult::default()
        };

        let feature = build_state_features(&sample, Some(&pid_result))
            .into_iter()
            .next()
            .unwrap_or_default();

        assert!(feature.is_structural_output);
        assert_eq!(feature.capital_q, Some(25.0));
        assert_eq!(feature.capital_retail, Some(10.0));
        assert_eq!(feature.rule_error_q, Some(0.5));
        assert_eq!(feature.rule_error_retail, Some(0.5));
    }
}

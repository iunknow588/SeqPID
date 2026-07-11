use crate::schemas::{DailySample, DecompositionResult, PredictResult};
use crate::state_feature_builder::tail_state_feature;
use std::collections::{HashMap, HashSet};

const RULE_TO_LABEL: &[(&str, &str)] = &[("hot_money", "游资"), ("quant", "量化"), ("retail", "散户")];

fn to_float(value: Option<&f64>, default: f64) -> f64 {
    value.copied().unwrap_or(default)
}

fn clamp01(value: f64) -> f64 {
    value.clamp(0.0, 1.0)
}

fn round4(value: f64) -> f64 {
    (value * 10000.0).round() / 10000.0
}

fn rule_flow_evidence(sample: &DailySample) -> RuleFlowEvidence {
    let mut totals: HashMap<&str, f64> = HashMap::from([("hot_money", 0.0), ("quant", 0.0), ("retail", 0.0)]);
    let mut abs_totals = totals.clone();
    let recovered = to_float(sample.feature_summary.get("raw_order_age_recovered_count"), 0.0);
    let missing = to_float(sample.feature_summary.get("raw_order_age_missing_count"), 0.0);

    for row in &sample.rows {
        let mut values = HashMap::from([
            ("hot_money", parse_row_f64(row, &["CH_rule_t", "signed_large_active_amount"]).unwrap_or(0.0)),
            ("quant", parse_row_f64(row, &["Q_rule_t"]).unwrap_or(0.0)),
            ("retail", parse_row_f64(row, &["R_seed_t"]).unwrap_or(0.0)),
        ]);
        if !row.contains_key("Q_rule_t") && !row.contains_key("R_seed_t") {
            values.insert("quant", parse_row_f64(row, &["signed_mix_qr_amount"]).unwrap_or(0.0));
            values.insert("retail", 0.0);
        }
        for (key, value) in values {
            *totals.entry(key).or_insert(0.0) += value;
            *abs_totals.entry(key).or_insert(0.0) += value.abs();
        }
    }

    let total_abs: f64 = abs_totals.values().sum();
    if total_abs <= 0.0 {
        return RuleFlowEvidence::default();
    }

    let (dominant_key, dominant_abs) = abs_totals
        .iter()
        .max_by(|a, b| a.1.partial_cmp(b.1).unwrap())
        .map(|(k, v)| (*k, *v))
        .unwrap_or(("retail", 0.0));
    let recovery_total = recovered + missing;
    let recovery_ratio = if recovery_total > 0.0 { recovered / recovery_total } else { 0.0 };
    let quality = if dominant_key == "retail" {
        recovery_ratio
    } else if dominant_key == "quant" && recovery_total > 0.0 {
        0.85 + 0.15 * recovery_ratio
    } else {
        1.0
    };

    RuleFlowEvidence {
        label: RULE_TO_LABEL
            .iter()
            .find(|(key, _)| *key == dominant_key)
            .map(|(_, label)| (*label).to_string())
            .unwrap_or_default(),
        signed_amount: *totals.get(dominant_key).unwrap_or(&0.0),
        ratio: dominant_abs / total_abs,
        recovery_ratio,
        confidence: (dominant_abs / total_abs) * quality,
    }
}

fn select_capital_type(
    sample: &DailySample,
    pid_result: &DecompositionResult,
    config: &HashMap<String, serde_yaml::Value>,
) -> (String, f64, HashMap<String, serde_json::Value>) {
    let structural_label = pid_result.dominant_type.clone();
    let structural_ratio = match structural_label.as_str() {
        "游资" => pid_result.hot_money_ratio,
        "量化" => pid_result.quant_ratio,
        "散户" => pid_result.retail_ratio,
        _ => 0.0,
    };
    let rule = rule_flow_evidence(sample);
    let mut selected_label = structural_label.clone();
    let mut selected_confidence = structural_ratio;
    let mut source = "capital_external_force".to_string();

    if config
        .get("enable_rule_flow_capital_override")
        .and_then(|v| v.as_bool())
        .unwrap_or(true)
        && !rule.label.is_empty()
    {
        let threshold = match rule.label.as_str() {
            "游资" => config.get("capital_hot_money_rule_override_threshold").and_then(|v| v.as_f64()).unwrap_or(0.46),
            "散户" => config.get("capital_retail_rule_override_threshold").and_then(|v| v.as_f64()).unwrap_or(0.46),
            "量化" => config.get("capital_quant_rule_override_threshold").and_then(|v| v.as_f64()).unwrap_or(0.68),
            _ => config.get("capital_rule_override_threshold").and_then(|v| v.as_f64()).unwrap_or(0.46),
        };
        let mut margin = config.get("capital_rule_override_margin").and_then(|v| v.as_f64()).unwrap_or(0.04);
        if rule.label == "量化" && structural_label != "量化" {
            margin = config
                .get("capital_quant_rule_override_margin")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.18);
        }
        let anchor_error = pid_result.capital_anchor_error.last().copied().unwrap_or(0.0);
        let anchor_error = if anchor_error.is_nan() { 0.0 } else { anchor_error };
        let structural_is_weak = structural_ratio
            < config
                .get("capital_external_force_strong_ratio")
                .or_else(|| config.get("capital_structural_strong_ratio"))
                .and_then(|v| v.as_f64())
                .unwrap_or(0.46);
        let anchor_is_weak = anchor_error
            > config
                .get("capital_anchor_override_error")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.35);
        let rule_is_stronger = rule.confidence >= structural_ratio + margin;
        let can_override = if rule.label == "量化" && structural_label != "量化" {
            rule_is_stronger && (structural_is_weak || anchor_is_weak)
        } else {
            rule_is_stronger || structural_is_weak || anchor_is_weak
        };
        if rule.confidence >= threshold && can_override {
            selected_label = rule.label.clone();
            selected_confidence = rule.confidence;
            source = "rule_flow_override".to_string();
        }
    }

    let mut debug = HashMap::new();
    debug.insert("capital_type_source".into(), serde_json::Value::String(source));
    debug.insert(
        "external_force_capital_type".into(),
        serde_json::Value::String(structural_label.clone()),
    );
    debug.insert(
        "external_force_capital_ratio".into(),
        serde_json::json!(round4(structural_ratio)),
    );
    debug.insert(
        "structural_capital_type".into(),
        serde_json::Value::String(structural_label),
    );
    debug.insert(
        "structural_capital_ratio".into(),
        serde_json::json!(round4(structural_ratio)),
    );
    debug.insert(
        "rule_flow_capital_type".into(),
        if rule.label.is_empty() {
            serde_json::Value::Null
        } else {
            serde_json::Value::String(rule.label.clone())
        },
    );
    debug.insert("rule_flow_ratio".into(), serde_json::json!(round4(rule.ratio)));
    debug.insert(
        "rule_flow_confidence".into(),
        serde_json::json!(round4(rule.confidence)),
    );
    debug.insert(
        "rule_flow_recovery_ratio".into(),
        serde_json::json!(round4(rule.recovery_ratio)),
    );
    debug.insert(
        "rule_flow_signed_amount".into(),
        serde_json::json!(round4(rule.signed_amount)),
    );
    (selected_label, selected_confidence, debug)
}

fn map_pid_to_intention(
    pid_result: &DecompositionResult,
    summary: &HashMap<String, f64>,
    config: &HashMap<String, serde_yaml::Value>,
    label_dict: &HashMap<String, serde_yaml::Value>,
) -> (String, f64) {
    let dominant = pid_result.dominant_type.as_str();
    if matches!(pid_result.dominant_intention.as_str(), "买入" | "卖出" | "中性") {
        let noise_penalty = pid_result.noise_ratio.last().copied().unwrap_or(0.0);
        let mut anchor_error = pid_result.capital_anchor_error.last().copied().unwrap_or(0.0);
        if anchor_error.is_nan() {
            anchor_error = 0.0;
        }
        let confidence = clamp01(0.72 - noise_penalty.min(0.35) - anchor_error.min(0.25));
        return (pid_result.dominant_intention.clone(), confidence);
    }

    let vwap_pct = to_float(summary.get("close_strength"), 0.5);
    let close_return = to_float(summary.get("close_return"), 0.0);
    let intraday_range = to_float(summary.get("intraday_range"), 0.0);
    let order_buy_ratio = to_float(summary.get("order_buy_ratio"), 0.5);
    let label_mode = config.get("label_mode").and_then(|v| v.as_str()).unwrap_or("compressed");
    let mut compressed_labels: HashSet<String> = label_dict
        .get("capital_intention_labels_submit")
        .and_then(|v| v.as_sequence())
        .map(|seq| seq.iter().filter_map(|item| item.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_default();
    for label in ["买入", "卖出", "中性", "T0交易"] {
        compressed_labels.insert(label.to_string());
    }

    let (fine, conf) = if dominant == "游资" {
        let delta_ch_end = pid_result.delta_ch.last().copied().unwrap_or(0.0);
        if delta_ch_end > 0.0 && vwap_pct < 0.8 {
            ("拉升", 0.75)
        } else if delta_ch_end < 0.0 && vwap_pct > 0.2 {
            ("出货", 0.72)
        } else if delta_ch_end.abs() < 1e-4 {
            ("试盘", 0.65)
        } else {
            ("吸筹", 0.68)
        }
    } else if dominant == "量化" {
        if close_return.abs() < 0.01 && intraday_range > 0.02 {
            ("T0交易", 0.70)
        } else if close_return < -0.015 {
            ("卖出", 0.67)
        } else if close_return > 0.015 && order_buy_ratio > 0.52 {
            ("买入", 0.62)
        } else {
            ("中性", 0.57)
        }
    } else if close_return.abs() < 0.008 {
        ("中性", 0.58)
    } else if close_return > 0.0 {
        ("买入", 0.60)
    } else {
        ("卖出", 0.60)
    };

    if label_mode == "compressed" && !compressed_labels.contains(fine) {
        return if matches!(fine, "吸筹" | "拉升") {
            ("买入".to_string(), conf)
        } else if fine == "出货" {
            ("卖出".to_string(), conf)
        } else if fine == "试盘" {
            (
                if dominant == "散户" { "T0交易" } else { "中性" }.to_string(),
                conf,
            )
        } else {
            ("中性".to_string(), conf)
        };
    }
    (fine.to_string(), conf)
}

pub fn predict_capitals(
    sample: &DailySample,
    config: &HashMap<String, serde_yaml::Value>,
    label_dict: &HashMap<String, serde_yaml::Value>,
    pid_result: &DecompositionResult,
) -> Vec<PredictResult> {
    let summary = &sample.feature_summary;
    let (dominant_type, selected_ratio, mut capital_debug) = select_capital_type(sample, pid_result, config);
    let (mut intention, mut intention_confidence) =
        map_pid_to_intention(pid_result, summary, config, label_dict);

    if capital_debug
        .get("capital_type_source")
        .and_then(|v| v.as_str())
        == Some("rule_flow_override")
    {
        let signed_amount = capital_debug
            .get("rule_flow_signed_amount")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0);
        let rule_flow_confidence = capital_debug
            .get("rule_flow_confidence")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0);
        if signed_amount.abs() > 0.0 {
            intention = if signed_amount > 0.0 { "买入" } else { "卖出" }.to_string();
            intention_confidence =
                intention_confidence.max((0.52 + rule_flow_confidence * 0.28).min(0.78));
        }
    }

    let dominant_ratio = if selected_ratio > 0.0 {
        selected_ratio
    } else {
        match dominant_type.as_str() {
            "游资" => pid_result.hot_money_ratio,
            "量化" => pid_result.quant_ratio,
            "散户" => pid_result.retail_ratio,
            _ => 0.33,
        }
    };
    let capital_confidence = clamp01(0.50 + dominant_ratio * 0.4 - (pid_result.closure_error * 1e5).min(0.1));
    let state_tail = tail_state_feature(sample, Some(pid_result));

    let mut debug_info = HashMap::new();
    debug_info.insert("hot_money_ratio".into(), serde_json::json!(round4(pid_result.hot_money_ratio)));
    debug_info.insert("quant_ratio".into(), serde_json::json!(round4(pid_result.quant_ratio)));
    debug_info.insert("retail_ratio".into(), serde_json::json!(round4(pid_result.retail_ratio)));
    debug_info.insert("inertia_mean".into(), serde_json::json!(round4(pid_result.inertia_mean)));
    debug_info.insert("damping_mean".into(), serde_json::json!(round4(pid_result.damping_mean)));
    debug_info.insert(
        "dominant_intention".into(),
        serde_json::Value::String(pid_result.dominant_intention.clone()),
    );
    debug_info.insert(
        "capital_anchor_error_tail".into(),
        match pid_result.capital_anchor_error.last().copied().filter(|v| v.is_finite()) {
            Some(value) => serde_json::json!(round4(value)),
            None => serde_json::Value::Null,
        },
    );
    debug_info.insert(
        "noise_ratio_tail".into(),
        pid_result
            .noise_ratio
            .last()
            .map(|value| serde_json::json!(round4(*value)))
            .unwrap_or(serde_json::Value::Null),
    );
    debug_info.insert(
        "explain_ratio_tail".into(),
        pid_result
            .explain_ratio
            .last()
            .map(|value| serde_json::json!(round4(*value)))
            .unwrap_or(serde_json::Value::Null),
    );
    debug_info.insert(
        "pid_closure_error".into(),
        serde_json::Value::String(format!("{:.2e}", pid_result.pid_closure_error)),
    );
    debug_info.insert(
        "alloc_closure_error".into(),
        serde_json::Value::String(format!("{:.2e}", pid_result.alloc_closure_error)),
    );
    debug_info.insert(
        "closure_error".into(),
        serde_json::Value::String(format!("{:.2e}", pid_result.closure_error)),
    );
    debug_info.insert(
        "display_closure_error".into(),
        serde_json::Value::String(format!("{:.2e}", pid_result.display_closure_error)),
    );
    debug_info.insert(
        "capital_identity_error".into(),
        serde_json::Value::String(format!("{:.2e}", pid_result.capital_identity_error)),
    );
    debug_info.insert(
        "capital_cp_identity_error".into(),
        serde_json::Value::String(format!("{:.2e}", pid_result.capital_cp_identity_error)),
    );
    debug_info.insert(
        "capital_ci_identity_error".into(),
        serde_json::Value::String(format!("{:.2e}", pid_result.capital_ci_identity_error)),
    );
    debug_info.insert(
        "capital_cd_identity_error".into(),
        serde_json::Value::String(format!("{:.2e}", pid_result.capital_cd_identity_error)),
    );
    debug_info.insert(
        "dominant_source".into(),
        serde_json::Value::String(pid_result.dominant_source.clone()),
    );
    debug_info.insert(
        "display_fields_used_for_dominant".into(),
        serde_json::Value::Bool(pid_result.display_fields_used_for_dominant),
    );
    debug_info.insert(
        "decompose_mode".into(),
        serde_json::Value::String(pid_result.mode.clone()),
    );
    debug_info.insert("kf_converged".into(), serde_json::Value::Bool(pid_result.kf_converged));
    debug_info.insert(
        "warnings".into(),
        serde_json::Value::Array(
            pid_result
                .warnings
                .iter()
                .cloned()
                .map(serde_json::Value::String)
                .collect(),
        ),
    );
    debug_info.extend(capital_debug.drain());
    if let Some(state_tail) = state_tail {
        debug_info.insert(
            "state_feature_mode".into(),
            serde_json::Value::String(state_tail.mode_name),
        );
        debug_info.insert(
            "state_feature_is_structural".into(),
            serde_json::Value::Bool(state_tail.is_structural_output),
        );
        debug_info.insert(
            "state_feature_window_id".into(),
            serde_json::Value::String(state_tail.window_id),
        );
        debug_info.insert(
            "state_feature_ch_rule_t".into(),
            serde_json::json!(round4(state_tail.ch_rule_t)),
        );
        debug_info.insert(
            "state_feature_q_rule_t".into(),
            serde_json::json!(round4(state_tail.q_rule_t)),
        );
        debug_info.insert(
            "state_feature_r_seed_t".into(),
            serde_json::json!(round4(state_tail.r_seed_t)),
        );
        debug_info.insert(
            "state_feature_capital_ch_rule_approx".into(),
            serde_json::json!(round4(state_tail.capital_ch_rule_approx)),
        );
        debug_info.insert(
            "state_feature_capital_q_rule_approx".into(),
            serde_json::json!(round4(state_tail.capital_q_rule_approx)),
        );
        debug_info.insert(
            "state_feature_capital_retail_rule_approx".into(),
            serde_json::json!(round4(state_tail.capital_retail_rule_approx)),
        );
        debug_info.insert(
            "state_feature_rule_error_q".into(),
            state_tail
                .rule_error_q
                .map(|value| serde_json::json!(round4(value)))
                .unwrap_or(serde_json::Value::Null),
        );
        debug_info.insert(
            "state_feature_rule_error_retail".into(),
            state_tail
                .rule_error_retail
                .map(|value| serde_json::json!(round4(value)))
                .unwrap_or(serde_json::Value::Null),
        );
    }

    vec![PredictResult {
        stock_code: sample.stock_code.clone(),
        transaction_date: sample.transaction_date.clone(),
        capital_type: dominant_type,
        capital_intention: intention,
        capital_confidence,
        intention_confidence,
        debug_info,
    }]
}

pub fn predict_capital(
    sample: &DailySample,
    config: &HashMap<String, serde_yaml::Value>,
    label_dict: &HashMap<String, serde_yaml::Value>,
    pid_result: &DecompositionResult,
) -> PredictResult {
    predict_capitals(sample, config, label_dict, pid_result)
        .into_iter()
        .next()
        .unwrap_or_default()
}

#[derive(Default)]
struct RuleFlowEvidence {
    label: String,
    signed_amount: f64,
    ratio: f64,
    recovery_ratio: f64,
    confidence: f64,
}

fn parse_row_f64(row: &HashMap<String, String>, names: &[&str]) -> Option<f64> {
    names.iter().find_map(|name| row.get(*name)).and_then(|value| value.parse::<f64>().ok())
}

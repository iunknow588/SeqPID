use crate::schemas::{DailySample, PredictResult};
use std::collections::HashMap;

fn to_float(value: Option<&f64>, default: f64) -> f64 {
    value.copied().unwrap_or(default)
}

fn clamp01(value: f64) -> f64 {
    value.clamp(0.0, 1.0)
}

fn predict_intention(
    capital_type: &str,
    close_return: f64,
    intraday_range: f64,
    close_strength: f64,
    _cancel_ratio: f64,
    bid_support: f64,
    ask_pressure: f64,
    order_buy_ratio: f64,
    last15_return: f64,
    config: &HashMap<String, serde_yaml::Value>,
    label_dict: &HashMap<String, serde_yaml::Value>,
) -> (String, f64) {
    let label_mode = config
        .get("label_mode")
        .and_then(|v| v.as_str())
        .unwrap_or("compressed");

    let compressed_labels: std::collections::HashSet<String> = label_dict
        .get("capital_intention_labels_submit")
        .and_then(|v| v.as_sequence())
        .map(|seq| {
            seq.iter()
                .filter_map(|item| item.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();

    let (fine, confidence) = if capital_type == "散户" {
        if close_return.abs() < 0.008 && intraday_range > 0.025 {
            ("T0交易", 0.72)
        } else if close_return > 0.012 && close_strength > 0.6 {
            ("买入", 0.64)
        } else if close_return < -0.012 && close_strength < 0.4 {
            ("卖出", 0.64)
        } else {
            ("中性", 0.58)
        }
    } else if capital_type == "量化" {
        if close_return.abs() < 0.01 && intraday_range > 0.02 {
            ("T0交易", 0.74)
        } else if close_return < -0.015 {
            ("卖出", 0.67)
        } else if close_return > 0.015 && order_buy_ratio > 0.52 {
            ("买入", 0.62)
        } else {
            ("中性", 0.57)
        }
    } else {
        if close_return > 0.02 && close_strength > 0.65 {
            ("拉升", 0.80)
        } else if order_buy_ratio > 0.56 && bid_support >= ask_pressure && close_return > 0.0 {
            ("吸筹", 0.73)
        } else if close_return < -0.018 && close_strength < 0.35 {
            ("出货", 0.79)
        } else if close_return.abs() < 0.008 && intraday_range > 0.03 {
            ("试盘", 0.68)
        } else if last15_return > 0.002 && close_return > 0.0 {
            ("买入", 0.64)
        } else if close_return > 0.008 {
            ("买入", 0.61)
        } else if close_return < -0.01 {
            ("卖出", 0.61)
        } else {
            ("中性", 0.56)
        }
    };

    if label_mode == "compressed" && !compressed_labels.contains(fine) {
        if fine == "吸筹" || fine == "拉升" {
            return ("买入".into(), confidence);
        }
        if fine == "出货" {
            return ("卖出".into(), confidence);
        }
        if fine == "试盘" {
            return (
                if capital_type == "散户" { "T0交易".into() } else { "中性".into() },
                confidence,
            );
        }
        return ("中性".into(), confidence);
    }
    (fine.into(), confidence)
}

pub fn predict_capital(
    sample: &DailySample,
    config: &HashMap<String, serde_yaml::Value>,
    label_dict: &HashMap<String, serde_yaml::Value>,
) -> PredictResult {
    let summary = &sample.feature_summary;

    let deal_amount = to_float(summary.get("deal_amount"), 0.0);
    let close_return = to_float(summary.get("close_return"), 0.0);
    let intraday_range = to_float(summary.get("intraday_range"), 0.0);
    let close_strength = to_float(summary.get("close_strength"), 0.0);
    let cancel_ratio = to_float(summary.get("cancel_ratio"), 0.0);
    let burst_ratio = to_float(summary.get("burst_ratio"), 0.0);
    let bid_support = to_float(summary.get("bid_support"), 0.0);
    let ask_pressure = to_float(summary.get("ask_pressure"), 0.0);
    let avg_trade_size = to_float(summary.get("avg_trade_size"), 0.0);
    let order_buy_ratio = to_float(summary.get("order_buy_ratio"), 0.5);
    let last15_return = to_float(summary.get("last15_return"), 0.0);
    let directional_efficiency = to_float(summary.get("directional_efficiency"), 0.0);

    let amount_score = clamp01(deal_amount / 1_000_000_000.0);
    let small_order_score = clamp01((12_000.0 - avg_trade_size) / 10_000.0);
    let large_order_score = clamp01((avg_trade_size - 8_000.0) / 12_000.0);
    let buy_bias_score = clamp01((order_buy_ratio - 0.50) / 0.18);
    let sell_bias_score = clamp01((0.50 - order_buy_ratio) / 0.18);
    let range_score = clamp01(intraday_range / 0.08);
    let up_score = clamp01(close_return / 0.05);
    let down_score = clamp01(-close_return / 0.05);

    let retail_score = small_order_score * 0.30
        + (1.0 - amount_score) * 0.15
        + (1.0 - (order_buy_ratio - 0.5).abs() / 0.18) * 0.20
        + range_score * 0.15
        + (1.0 - directional_efficiency) * 0.10
        + if cancel_ratio < 0.02 { 0.10 } else { 0.0 };

    let hot_money_score = amount_score * 0.25
        + large_order_score * 0.15
        + up_score.max(down_score) * 0.18
        + range_score * 0.15
        + directional_efficiency * 0.12
        + buy_bias_score.max(sell_bias_score) * 0.10
        + if last15_return.abs() > 0.002 { 0.05 } else { 0.0 }
        + if close_return.abs() > 0.03 { 0.10 } else { 0.0 }
        + if deal_amount > 300_000_000.0 && close_strength > 0.6 { 0.06 } else { 0.0 };

    let quant_score = (1.0 - close_return.abs() / 0.03) * 0.18
        + (1.0 - (order_buy_ratio - 0.5).abs() / 0.18) * 0.18
        + range_score * 0.10
        + burst_ratio * 0.12
        + if close_return.abs() < 0.008 { 0.12 } else { 0.0 }
        + if close_strength < 0.35 || close_strength > 0.65 { 0.10 } else { 0.0 }
        + if bid_support <= ask_pressure { 0.10 } else { 0.0 }
        + if cancel_ratio >= 0.01 { 0.10 } else { 0.0 };

    let (mut capital_type, mut capital_confidence) = if hot_money_score >= retail_score && hot_money_score >= quant_score {
        ("游资", clamp01(0.55 + (hot_money_score - retail_score.max(quant_score)) / 1.5))
    } else if quant_score >= retail_score {
        ("量化", clamp01(0.55 + (quant_score - retail_score) / 1.5))
    } else {
        ("散户", clamp01(0.55 + (retail_score - hot_money_score.max(quant_score)) / 1.5))
    };

    if capital_type == "散户" && close_return > 0.025 && close_strength > 0.65 {
        capital_type = "游资";
        capital_confidence = capital_confidence.max(0.66);
    }

    let (intention, intention_confidence) = predict_intention(
        capital_type,
        close_return,
        intraday_range,
        close_strength,
        cancel_ratio,
        bid_support,
        ask_pressure,
        order_buy_ratio,
        last15_return,
        config,
        label_dict,
    );

    let mut debug_info = HashMap::new();
    debug_info.insert("retail_score".into(), serde_json::Value::Number(serde_json::Number::from_f64((retail_score * 10000.0).round() / 10000.0).unwrap()));
    debug_info.insert("hot_money_score".into(), serde_json::Value::Number(serde_json::Number::from_f64((hot_money_score * 10000.0).round() / 10000.0).unwrap()));
    debug_info.insert("quant_score".into(), serde_json::Value::Number(serde_json::Number::from_f64((quant_score * 10000.0).round() / 10000.0).unwrap()));
    debug_info.insert("close_return".into(), serde_json::Value::Number(serde_json::Number::from_f64((close_return * 10000.0).round() / 10000.0).unwrap()));
    debug_info.insert("order_buy_ratio".into(), serde_json::Value::Number(serde_json::Number::from_f64((order_buy_ratio * 10000.0).round() / 10000.0).unwrap()));

    PredictResult {
        stock_code: sample.stock_code.clone(),
        transaction_date: sample.transaction_date.clone(),
        capital_type: capital_type.to_string(),
        capital_intention: intention,
        capital_confidence,
        intention_confidence,
        debug_info,
    }
}

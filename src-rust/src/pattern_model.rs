use crate::schemas::{DailySample, PatternResult};

fn to_float(value: Option<&f64>, default: f64) -> f64 {
    value.copied().unwrap_or(default)
}

fn clip01(value: f64) -> f64 {
    value.clamp(0.0, 1.0)
}

fn detect_obvious_pattern(summary: &std::collections::HashMap<String, f64>) -> Option<String> {
    let deal_amount = to_float(summary.get("deal_amount"), 0.0);
    let close_return = to_float(summary.get("close_return"), 0.0);
    let open_return = to_float(summary.get("open_return"), 0.0);
    let intraday_range = to_float(summary.get("intraday_range"), 0.0);
    let close_strength = to_float(summary.get("close_strength"), 0.0);
    let tail_ratio = to_float(summary.get("tail_ratio"), 0.0);
    let last15_return = to_float(summary.get("last15_return"), 0.0);
    let avg_trade_size = to_float(summary.get("avg_trade_size"), 0.0);
    let order_buy_ratio = to_float(summary.get("order_buy_ratio"), 0.5);

    if close_return >= 0.035 && close_strength >= 0.62 && deal_amount >= 300_000_000.0 {
        return Some("大单吸筹".into());
    }
    if close_return >= 0.012 && close_strength >= 0.58 && avg_trade_size <= 8500.0 && order_buy_ratio >= 0.53 {
        return Some("连续小单推升".into());
    }
    if last15_return >= 0.0025 && tail_ratio >= 0.10 && close_strength >= 0.68 {
        return Some("尾盘突袭".into());
    }
    if open_return <= -0.008 && close_return >= 0.008 && close_strength >= 0.60 {
        return Some("压单吸货".into());
    }
    if open_return >= 0.008 && close_return <= -0.012 && close_strength <= 0.35 {
        return Some("盘中诱多".into());
    }
    if close_return <= -0.025 && close_strength <= 0.28 {
        return Some("盘中诱多".into());
    }
    if close_return.abs() <= 0.012 && intraday_range >= 0.035 {
        return Some("日内套利".into());
    }
    None
}

fn render_pattern_explanation(label: &str) -> &'static str {
    match label {
        "尾盘突袭" => "尾盘最后一段成交明显放大，股价临近收盘快速抬升，带有集中做强收盘的意味。",
        "大单吸筹" => "全天维持偏强上攻，成交额与单笔成交偏大，像是主导资金持续承接并主动推高。",
        "日内套利" => "日内振幅较大但收盘偏离不深，更像在区间里反复高抛低吸做差价。",
        "对倒拉升" => "成交活跃度与价格波动同步放大，盘口节奏偏快，存在制造活跃度并拉升股价的迹象。",
        "压单吸货" => "盘口卖压存在但收盘仍维持相对高位，像是边压盘边在回落区间吸收筹码。",
        "集合竞价异动" => "开盘阶段偏离前收较明显，随后出现修正，竞价阶段对全天预期的影响较强。",
        "分时脉冲" => "盘中出现较快的拉升回落或试探动作，节奏短促，更多体现为脉冲型波动。",
        "连续小单推升" => "单笔成交偏小但买入力度持续，股价重心缓慢上移，属于较隐蔽的推升形态。",
        "盘中诱多" => "盘中一度尝试上攻，但收盘回落到偏弱位置，带有吸引跟风后转弱的特征。",
        "涨停板打开" => "全天强势波动较大，情绪冲高后反复换手，呈现强势股开板博弈的节奏。",
        _ => "盘口与价格节奏存在明显异动，当前标签由日内成交结构与收盘位置共同决定。",
    }
}

fn fallback_pattern_rule(summary: &std::collections::HashMap<String, f64>) -> String {
    let close_return = to_float(summary.get("close_return"), 0.0);
    let open_return = to_float(summary.get("open_return"), 0.0);
    let intraday_range = to_float(summary.get("intraday_range"), 0.0);
    let close_strength = to_float(summary.get("close_strength"), 0.0);
    let order_buy_ratio = to_float(summary.get("order_buy_ratio"), 0.5);
    let avg_trade_size = to_float(summary.get("avg_trade_size"), 0.0);
    let last15_return = to_float(summary.get("last15_return"), 0.0);

    if last15_return > 0.0025 && close_strength > 0.7 {
        return "尾盘突袭".into();
    }
    if close_return > 0.03 && close_strength > 0.85 {
        return "大单吸筹".into();
    }
    if close_return > 0.01 && avg_trade_size < 8000.0 && order_buy_ratio > 0.52 {
        return "连续小单推升".into();
    }
    if close_return.abs() < 0.015 && intraday_range > 0.035 {
        return "日内套利".into();
    }
    if open_return < -0.01 && close_return > 0.008 && close_strength > 0.65 {
        return "压单吸货".into();
    }
    if open_return > 0.008 && close_return < -0.01 && close_strength < 0.35 {
        return "盘中诱多".into();
    }
    if close_return < -0.02 && close_strength < 0.35 {
        return "盘中诱多".into();
    }
    "分时脉冲".into()
}

pub fn predict_pattern(
    sample: &DailySample,
    config: &std::collections::HashMap<String, serde_yaml::Value>,
    _label_dict: &std::collections::HashMap<String, serde_yaml::Value>,
) -> PatternResult {
    let summary = &sample.feature_summary;

    let deal_amount = to_float(summary.get("deal_amount"), 0.0);
    let close_return = to_float(summary.get("close_return"), 0.0);
    let open_return = to_float(summary.get("open_return"), 0.0);
    let intraday_range = to_float(summary.get("intraday_range"), 0.0);
    let close_strength = to_float(summary.get("close_strength"), 0.0);
    let cancel_ratio = to_float(summary.get("cancel_ratio"), 0.0);
    let burst_ratio = to_float(summary.get("burst_ratio"), 0.0);
    let bid_support = to_float(summary.get("bid_support"), 0.0);
    let ask_pressure = to_float(summary.get("ask_pressure"), 0.0);
    let tail_ratio = to_float(summary.get("tail_ratio"), 0.0);
    let last15_return = to_float(summary.get("last15_return"), 0.0);
    let avg_trade_size = to_float(summary.get("avg_trade_size"), 0.0);
    let order_buy_ratio = to_float(summary.get("order_buy_ratio"), 0.5);
    let directional_efficiency = to_float(summary.get("directional_efficiency"), 0.0);
    let reversal_strength = to_float(summary.get("reversal_strength"), 0.0);

    if let Some(forced) = detect_obvious_pattern(summary) {
        return PatternResult {
            stock_code: sample.stock_code.clone(),
            transaction_date: sample.transaction_date.clone(),
            pattern_type: forced.clone(),
            pattern_explanation: render_pattern_explanation(&forced).to_string(),
            pattern_score: 0.86,
            prototype_id: format!("rule::{}", forced),
        };
    }

    let amount_score = clip01(deal_amount / 1_000_000_000.0);
    let range_score = clip01(intraday_range / 0.08);
    let up_score = clip01(close_return / 0.05);
    let down_score = clip01(-close_return / 0.05);
    let open_jump_score = clip01(open_return.abs() / 0.03);
    let close_top_score = clip01((close_strength - 0.55) / 0.45);
    let close_bottom_score = clip01((0.45 - close_strength) / 0.45);
    let buy_bias_score = clip01((order_buy_ratio - 0.50) / 0.18);
    let sell_bias_score = clip01((0.50 - order_buy_ratio) / 0.18);
    let small_order_score = clip01((12_000.0 - avg_trade_size) / 10_000.0);
    let large_order_score = clip01((avg_trade_size - 8_000.0) / 12_000.0);
    let tail_up_score = clip01(last15_return / 0.006);
    let tail_down_score = clip01(-last15_return / 0.006);
    let tail_flow_score = clip01((tail_ratio - 0.08) / 0.10);
    let mid_close_score = 1.0 - clip01((close_strength - 0.5).abs() / 0.4);
    let neutral_close_score = 1.0 - clip01(close_return.abs() / 0.02);
    let reversal_up_score = clip01(reversal_strength / 0.03);
    let reversal_down_score = clip01(-reversal_strength / 0.03);

    let mut candidates: Vec<(&str, f64)> = vec![
        ("尾盘突袭", tail_up_score * 0.34 + tail_flow_score * 0.22 + close_top_score * 0.22 + up_score * 0.12 + amount_score * 0.10),
        ("大单吸筹", up_score * 0.25 + buy_bias_score * 0.20 + close_top_score * 0.20 + large_order_score * 0.20 + amount_score * 0.15),
        ("日内套利", range_score * 0.35 + neutral_close_score * 0.30 + mid_close_score * 0.20 + (1.0 - (order_buy_ratio - 0.5).abs() / 0.2) * 0.15),
        ("对倒拉升", range_score * 0.24 + amount_score * 0.18 + burst_ratio * 0.18 + up_score * 0.18 + cancel_ratio * 6.0 * 0.10 + close_top_score * 0.12),
        ("压单吸货", close_top_score * 0.25 + up_score * 0.20 + clip01((ask_pressure - bid_support + 0.1) / 0.3) * 0.20 + buy_bias_score * 0.15 + neutral_close_score * 0.10 + amount_score * 0.10),
        ("集合竞价异动", open_jump_score * 0.42 + reversal_down_score * 0.18 + reversal_up_score * 0.18 + range_score * 0.12 + burst_ratio * 0.10),
        ("分时脉冲", range_score * 0.34 + burst_ratio * 0.22 + mid_close_score * 0.18 + tail_down_score * 0.10 + tail_up_score * 0.10 + neutral_close_score * 0.06),
        ("连续小单推升", up_score * 0.22 + close_top_score * 0.22 + small_order_score * 0.22 + buy_bias_score * 0.18 + directional_efficiency * 0.16),
        ("盘中诱多", down_score * 0.26 + close_bottom_score * 0.24 + range_score * 0.18 + reversal_down_score * 0.18 + sell_bias_score * 0.14),
        ("涨停板打开", up_score * 0.22 + range_score * 0.22 + close_top_score * 0.16 + amount_score * 0.16 + tail_down_score * 0.14 + burst_ratio * 0.10),
    ];

    candidates.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
    let (label, score) = candidates[0];
    let second_score = if candidates.len() > 1 { candidates[1].1 } else { 0.0 };
    let margin = score - second_score;

    let low_conf = config.get("pattern_low_conf_threshold")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.15);
    let margin_thresh = config.get("pattern_margin_threshold")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.05);

    if score < low_conf || margin < margin_thresh {
        let fallback = fallback_pattern_rule(summary);
        return PatternResult {
            stock_code: sample.stock_code.clone(),
            transaction_date: sample.transaction_date.clone(),
            pattern_type: fallback.clone(),
            pattern_explanation: render_pattern_explanation(&fallback).to_string(),
            pattern_score: low_conf,
            prototype_id: format!("fallback::{}", fallback),
        };
    }

    PatternResult {
        stock_code: sample.stock_code.clone(),
        transaction_date: sample.transaction_date.clone(),
        pattern_type: label.to_string(),
        pattern_explanation: render_pattern_explanation(label).to_string(),
        pattern_score: (score * 10000.0).round() / 10000.0,
        prototype_id: format!("scorer::{}", label),
    }
}

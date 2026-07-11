use crate::schemas::{DailySample, DecompositionResult, PatternResult};
use std::collections::HashMap;

fn to_float(value: Option<&f64>, default: f64) -> f64 {
    value.copied().unwrap_or(default)
}

fn clip01(value: f64) -> f64 {
    value.clamp(0.0, 1.0)
}

fn detect_obvious_pattern(summary: &HashMap<String, f64>) -> Option<&'static str> {
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
        Some("大单吸筹")
    } else if close_return >= 0.012 && close_strength >= 0.58 && avg_trade_size <= 8500.0 && order_buy_ratio >= 0.53 {
        Some("连续小单推升")
    } else if last15_return >= 0.0025 && tail_ratio >= 0.10 && close_strength >= 0.68 {
        Some("尾盘突袭")
    } else if open_return <= -0.008 && close_return >= 0.008 && close_strength >= 0.60 {
        Some("压单吸货")
    } else if open_return >= 0.008 && close_return <= -0.012 && close_strength <= 0.35 {
        Some("盘中诱多")
    } else if close_return <= -0.025 && close_strength <= 0.28 {
        Some("盘中诱多")
    } else if close_return.abs() <= 0.012 && intraday_range >= 0.035 {
        Some("日内套利")
    } else {
        None
    }
}

fn fallback_pattern_rule(summary: &HashMap<String, f64>) -> &'static str {
    let close_return = to_float(summary.get("close_return"), 0.0);
    let open_return = to_float(summary.get("open_return"), 0.0);
    let intraday_range = to_float(summary.get("intraday_range"), 0.0);
    let close_strength = to_float(summary.get("close_strength"), 0.0);
    let order_buy_ratio = to_float(summary.get("order_buy_ratio"), 0.5);
    let avg_trade_size = to_float(summary.get("avg_trade_size"), 0.0);
    let last15_return = to_float(summary.get("last15_return"), 0.0);

    if last15_return > 0.0025 && close_strength > 0.7 {
        "尾盘突袭"
    } else if close_return > 0.03 && close_strength > 0.85 {
        "大单吸筹"
    } else if close_return > 0.01 && avg_trade_size < 8000.0 && order_buy_ratio > 0.52 {
        "连续小单推升"
    } else if close_return.abs() < 0.015 && intraday_range > 0.035 {
        "日内套利"
    } else if open_return < -0.01 && close_return > 0.008 && close_strength > 0.65 {
        "压单吸货"
    } else if open_return > 0.008 && close_return < -0.01 && close_strength < 0.35 {
        "盘中诱多"
    } else if close_return < -0.02 && close_strength < 0.35 {
        "盘中诱多"
    } else {
        "分时脉冲"
    }
}

fn refine_pattern_with_pid(label: &str, summary: &HashMap<String, f64>, pid_result: Option<&DecompositionResult>) -> String {
    let Some(pid_result) = pid_result else {
        return label.to_string();
    };
    let dominant_type = pid_result.dominant_type.as_str();
    let dominant_intention = pid_result.dominant_intention.as_str();
    let hot_money_ratio = pid_result.hot_money_ratio;
    let quant_ratio = pid_result.quant_ratio;
    let damping_mean = pid_result.damping_mean.abs();
    let inertia_mean = pid_result.inertia_mean.abs();
    let close_return = to_float(summary.get("close_return"), 0.0);
    let intraday_range = to_float(summary.get("intraday_range"), 0.0);
    let close_strength = to_float(summary.get("close_strength"), 0.0);
    let burst_ratio = to_float(summary.get("burst_ratio"), 0.0);
    let tail_ratio = to_float(summary.get("tail_ratio"), 0.0);

    if dominant_type == "游资" && dominant_intention == "买入" && hot_money_ratio >= 0.34 {
        if close_return >= 0.018 && close_strength >= 0.55 {
            return "大单吸筹".to_string();
        }
        if intraday_range >= 0.025 || burst_ratio >= 0.18 {
            return "对倒拉升".to_string();
        }
    }
    if dominant_type == "游资" && dominant_intention == "卖出" && close_strength <= 0.48 {
        return "盘中诱多".to_string();
    }
    if dominant_type == "量化" && quant_ratio >= 0.38 {
        if intraday_range >= 0.025 && close_return.abs() <= 0.015 {
            return "日内套利".to_string();
        }
        if damping_mean >= 0.05 && burst_ratio >= 0.12 {
            return "分时脉冲".to_string();
        }
    }
    if dominant_intention == "卖出" && close_return < -0.018 && close_strength <= 0.45 {
        return "盘中诱多".to_string();
    }
    if dominant_intention == "买入" && tail_ratio >= 0.10 && close_strength >= 0.65 {
        return "尾盘突袭".to_string();
    }
    if inertia_mean >= 0.20 && damping_mean < 0.03 && close_return > 0.01 {
        return "连续小单推升".to_string();
    }
    label.to_string()
}

pub fn render_pattern_explanation(label: &str) -> &'static str {
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

pub fn predict_pattern(
    sample: &DailySample,
    config: &HashMap<String, serde_yaml::Value>,
    _label_dict: &HashMap<String, serde_yaml::Value>,
    pid_result: Option<&DecompositionResult>,
) -> PatternResult {
    let summary = &sample.feature_summary;

    if let Some(forced_label) = detect_obvious_pattern(summary) {
        let refined = refine_pattern_with_pid(forced_label, summary, pid_result);
        return PatternResult {
            stock_code: sample.stock_code.clone(),
            transaction_date: sample.transaction_date.clone(),
            pattern_type: refined.clone(),
            pattern_explanation: render_pattern_explanation(&refined).to_string(),
            pattern_score: 0.86,
            prototype_id: if refined == forced_label {
                format!("rule::{}", refined)
            } else {
                format!("rule_pid::{}", refined)
            },
        };
    }

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

    let mut candidates = vec![
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
    let (mut label, mut score) = (candidates[0].0, candidates[0].1);
    let second_score = candidates.get(1).map(|item| item.1).unwrap_or(0.0);
    let margin = score - second_score;
    let low_conf = config
        .get("pattern_low_conf_threshold")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.15);
    let margin_thresh = config
        .get("pattern_margin_threshold")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.04);
    if score < low_conf || margin < margin_thresh {
        label = fallback_pattern_rule(summary);
        score = score.max(0.18);
    }

    let refined_label = refine_pattern_with_pid(label, summary, pid_result);
    if refined_label != label {
        score = score.max(0.62).min(0.93);
    }

    PatternResult {
        stock_code: sample.stock_code.clone(),
        transaction_date: sample.transaction_date.clone(),
        pattern_type: refined_label.clone(),
        pattern_explanation: render_pattern_explanation(&refined_label).to_string(),
        pattern_score: (score * 10000.0).round() / 10000.0,
        prototype_id: if refined_label == label {
            format!("baseline::{}", refined_label)
        } else {
            format!("baseline_pid::{}", refined_label)
        },
    }
}

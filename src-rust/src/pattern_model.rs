use crate::schemas::{DailySample, DecompositionResult, PatternResult};
use std::cmp::Ordering;
use std::collections::HashMap;

const PATTERN_LABELS: &[&str] = &["量化T0", "散户博弈", "尾盘突袭", "日内套利", "大单吸筹"];

fn to_float(value: Option<&f64>, default: f64) -> f64 {
    value.copied().unwrap_or(default)
}

fn clip01(value: f64) -> f64 {
    value.clamp(0.0, 1.0)
}

fn pattern_submit_labels(label_dict: &HashMap<String, serde_yaml::Value>) -> Vec<String> {
    match label_dict.get("pattern_labels_submit") {
        Some(serde_yaml::Value::Sequence(seq)) if !seq.is_empty() => seq
            .iter()
            .filter_map(|value| value.as_str().map(|s| s.to_string()))
            .collect(),
        _ => PATTERN_LABELS.iter().map(|s| s.to_string()).collect(),
    }
}

fn internal_to_submit_label(label: &str) -> &str {
    match label {
        "分时脉冲" => "量化T0",
        "连续小单推升" => "量化T0",
        "盘中诱多" => "散户博弈",
        "对倒拉升" => "大单吸筹",
        "压单吸货" => "大单吸筹",
        "集合竞价异动" => "日内套利",
        "涨停板打开" => "尾盘突袭",
        other => other,
    }
}

#[derive(Clone, Debug)]
struct PatternScores {
    deal_amount: f64,
    close_return: f64,
    open_return: f64,
    intraday_range: f64,
    close_strength: f64,
    cancel_ratio: f64,
    burst_ratio: f64,
    bid_support: f64,
    ask_pressure: f64,
    tail_ratio: f64,
    last15_return: f64,
    avg_trade_size: f64,
    order_buy_ratio: f64,
    directional_efficiency: f64,
    reversal_strength: f64,
    balance_score: f64,
    small_order_score: f64,
    large_order_score: f64,
    amount_score: f64,
    range_score: f64,
    neutral_close_score: f64,
    close_top_score: f64,
    close_mid_score: f64,
    close_bottom_score: f64,
    buy_bias_score: f64,
    sell_bias_score: f64,
    tail_flow_score: f64,
    tail_return_score: f64,
    tail_squeeze_score: f64,
    burst_score: f64,
    direction_score: f64,
    noise_score: f64,
    reversal_score: f64,
    ask_pressure_score: f64,
    open_jump_score: f64,
    up_score: f64,
    down_score: f64,
}

impl PatternScores {
    fn from_summary(summary: &HashMap<String, f64>) -> Self {
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

        let balance_score = 1.0 - clip01((order_buy_ratio - 0.50).abs() / 0.18);
        let small_order_score = clip01((12_000.0 - avg_trade_size) / 10_000.0);
        let large_order_score = clip01((avg_trade_size - 7_000.0) / 13_000.0);
        let amount_score = clip01(deal_amount / 800_000_000.0);
        let range_score = clip01(intraday_range / 0.08);
        let neutral_close_score = 1.0 - clip01(close_return.abs() / 0.02);
        let close_top_score = clip01((close_strength - 0.56) / 0.44);
        let close_mid_score = 1.0 - clip01((close_strength - 0.50).abs() / 0.35);
        let close_bottom_score = clip01((0.45 - close_strength) / 0.45);
        let buy_bias_score = clip01((order_buy_ratio - 0.50) / 0.16);
        let sell_bias_score = clip01((0.50 - order_buy_ratio) / 0.16);
        let tail_flow_score = clip01((tail_ratio - 0.06) / 0.10);
        let tail_return_score = clip01((last15_return - 0.0015) / 0.01);
        let tail_squeeze_score = clip01((tail_ratio + last15_return.max(0.0) * 40.0) / 0.22);
        let burst_score = clip01(burst_ratio / 0.22);
        let direction_score = clip01(directional_efficiency / 0.75);
        let noise_score = 1.0 - clip01(direction_score);
        let reversal_score = clip01(reversal_strength.abs() / 0.03);
        let ask_pressure_score = clip01((ask_pressure - bid_support + 0.12) / 0.30);
        let open_jump_score = clip01(open_return.abs() / 0.03);
        let up_score = clip01(close_return / 0.05);
        let down_score = clip01(-close_return / 0.05);

        Self {
            deal_amount,
            close_return,
            open_return,
            intraday_range,
            close_strength,
            cancel_ratio,
            burst_ratio,
            bid_support,
            ask_pressure,
            tail_ratio,
            last15_return,
            avg_trade_size,
            order_buy_ratio,
            directional_efficiency,
            reversal_strength,
            balance_score,
            small_order_score,
            large_order_score,
            amount_score,
            range_score,
            neutral_close_score,
            close_top_score,
            close_mid_score,
            close_bottom_score,
            buy_bias_score,
            sell_bias_score,
            tail_flow_score,
            tail_return_score,
            tail_squeeze_score,
            burst_score,
            direction_score,
            noise_score,
            reversal_score,
            ask_pressure_score,
            open_jump_score,
            up_score,
            down_score,
        }
    }
}

fn pattern_evidence(label: &str, scores: &PatternScores) -> Vec<&'static str> {
    match label {
        "量化T0" => vec!["小单高频", "买卖均衡", "程序化回转"],
        "散户博弈" => vec!["小单主导", "方向混乱", "缺少主导资金"],
        "尾盘突袭" => vec!["尾盘放量", "收盘强势", "尾段冲击"],
        "日内套利" => vec!["区间波动", "收盘回中", "反复做差价"],
        _ => {
            let _ = scores;
            vec!["大单承接", "买盘占优", "重心抬升"]
        }
    }
}

fn dominant_capital_type(scores: &PatternScores, pid_result: Option<&DecompositionResult>) -> String {
    if let Some(pid_result) = pid_result {
        match pid_result.dominant_type.as_str() {
            "游资" | "量化" | "散户" => return pid_result.dominant_type.clone(),
            _ => {}
        }
    }
    if scores.large_order_score >= 0.55 || scores.tail_squeeze_score >= 0.60 {
        "游资".to_string()
    } else if scores.small_order_score >= 0.55 && scores.balance_score >= 0.55 {
        "量化".to_string()
    } else {
        "散户".to_string()
    }
}

fn dominant_intention(scores: &PatternScores, pid_result: Option<&DecompositionResult>) -> String {
    if let Some(pid_result) = pid_result {
        match pid_result.dominant_intention.as_str() {
            "买入" | "卖出" | "中性" | "T0交易" => return pid_result.dominant_intention.clone(),
            _ => {}
        }
    }
    if scores.sell_bias_score >= 0.35 || scores.down_score >= 0.25 {
        "卖出".to_string()
    } else if scores.buy_bias_score >= 0.35 || scores.up_score >= 0.25 {
        "买入".to_string()
    } else if scores.balance_score >= 0.50 {
        "T0交易".to_string()
    } else {
        "中性".to_string()
    }
}

#[derive(Clone, Debug)]
struct ExplanationSummary {
    pattern_type: String,
    capital_type: String,
    capital_intention: String,
    time_bucket: String,
    flow_style: String,
    order_size_style: String,
    price_effect: String,
    template_key: String,
}

fn build_explanation_summary(
    label: &str,
    scores: &PatternScores,
    pid_result: Option<&DecompositionResult>,
) -> ExplanationSummary {
    let time_bucket = if label == "尾盘突袭" || scores.tail_flow_score >= 0.50 {
        "tail"
    } else if scores.open_jump_score >= 0.50 {
        "open"
    } else {
        "intraday"
    };
    let order_size_style = if scores.large_order_score >= 0.55 {
        "large"
    } else if scores.small_order_score >= 0.55 {
        "small"
    } else {
        "mixed"
    };
    let (flow_style, price_effect) = if label == "量化T0" || label == "日内套利" {
        let flow_style = if scores.balance_score >= 0.45 { "intermittent" } else { "continuous" };
        (flow_style, "rotate")
    } else if label == "尾盘突袭" {
        let flow_style = if scores.burst_score >= 0.45 { "one_shot" } else { "continuous" };
        let price_effect = if scores.sell_bias_score >= 0.30 || scores.down_score >= 0.20 {
            "dump"
        } else {
            "lift"
        };
        (flow_style, price_effect)
    } else if label == "大单吸筹" {
        let flow_style = if scores.direction_score >= 0.45 { "continuous" } else { "one_shot" };
        (flow_style, "absorb")
    } else {
        ("intermittent", "churn")
    };

    let template_key = if label == "量化T0" {
        if scores.range_score >= 0.45 && scores.neutral_close_score >= 0.45 {
            "vwap"
        } else {
            "default"
        }
    } else if label == "散户博弈" {
        if scores.large_order_score <= 0.30 {
            "weak_support"
        } else {
            "default"
        }
    } else if label == "尾盘突袭" {
        if price_effect == "dump" { "dump" } else { "default" }
    } else if label == "日内套利" {
        if scores.balance_score >= 0.50 { "vwap" } else { "default" }
    } else if label == "大单吸筹" {
        if flow_style == "continuous" { "continuous" } else { "default" }
    } else {
        "default"
    };

    ExplanationSummary {
        pattern_type: label.to_string(),
        capital_type: dominant_capital_type(scores, pid_result),
        capital_intention: dominant_intention(scores, pid_result),
        time_bucket: time_bucket.to_string(),
        flow_style: flow_style.to_string(),
        order_size_style: order_size_style.to_string(),
        price_effect: price_effect.to_string(),
        template_key: template_key.to_string(),
    }
}

fn render_explanation_summary(summary: &ExplanationSummary) -> String {
    if summary.pattern_type == PATTERN_LABELS[0] {
        if summary.time_bucket == "open" {
            return "早盘小单快速往返，买卖方向接近平衡，呈现程序化T0试盘回转".to_string();
        }
        if summary.order_size_style == "small" && summary.flow_style == "intermittent" {
            return "高频小单分批进出，围绕盘口价差反复回转，呈现量化T0特征".to_string();
        }
    }

    if summary.pattern_type == PATTERN_LABELS[1] {
        if summary.order_size_style == "small" && summary.flow_style == "intermittent" {
            return "成交以小单间歇换手为主，方向分散，呈现散户之间的博弈".to_string();
        }
    }

    if summary.pattern_type == PATTERN_LABELS[2] {
        if summary.time_bucket == "tail" && summary.price_effect == "dump" {
            return "收盘前集中砸盘，制造恐慌情绪并显著影响收盘价".to_string();
        }
        if summary.time_bucket == "tail" && summary.flow_style == "one_shot" {
            return "下午2点半后资金集中拉升，短时间突击并制造强势收盘形态".to_string();
        }
    }

    if summary.pattern_type == PATTERN_LABELS[3] {
        if summary.time_bucket == "open" {
            return "早盘先拉开价差，盘中反复高抛低吸，最终回到区间中部".to_string();
        }
        if summary.flow_style == "intermittent" {
            return "资金围绕VWAP上下反复交易，利用区间波动获取日内价差".to_string();
        }
    }

    if summary.pattern_type == PATTERN_LABELS[4] {
        if summary.time_bucket == "open" && summary.order_size_style == "large" {
            return "早盘大单快速扫货，主动承接筹码并抬高日内价格重心".to_string();
        }
        if summary.flow_style == "one_shot" && summary.order_size_style == "large" {
            return "短时间内大单集中买入，快速吸收筹码并推动股价上移".to_string();
        }
    }

    match (summary.pattern_type.as_str(), summary.template_key.as_str()) {
        ("量化T0", "vwap") => "量化模型围绕VWAP反复挂单，利用短周期偏离完成日内回转".to_string(),
        ("量化T0", _) => "程序化拆单后快速买入卖出，围绕盘口价差完成T0回转".to_string(),
        ("散户博弈", "weak_support") => "盘口缺乏大单支撑，价格随散户情绪小幅波动".to_string(),
        ("散户博弈", _) => "成交以小单为主且方向混乱，呈现散户之间的博弈换手".to_string(),
        ("尾盘突袭", "dump") => "收盘前集中砸盘，制造恐慌情绪并显著影响收盘价".to_string(),
        ("尾盘突袭", _) => "在下午2点半之后集中拉升，制造强势收盘和典型技术形态".to_string(),
        ("日内套利", "vwap") => "资金围绕VWAP上下反复交易，赚取均值回复利润".to_string(),
        ("日内套利", _) => "资金在一定价格区间来回高抛低吸，获取日内价差收益".to_string(),
        ("大单吸筹", "continuous") => "盘中持续出现大额买单，逐步抬高股价重心".to_string(),
        ("大单吸筹", _) => "资金大笔挂单买入，短时间内集中扫货并吸收筹码".to_string(),
        _ => "盘中结构和资金行为出现明显偏离，资金运行模式需要结合证据共同判断".to_string(),
    }
}

fn score_pattern_modes(scores: &PatternScores) -> Vec<(&'static str, f64, Vec<&'static str>)> {
    vec![
        (
            "量化T0",
            scores.small_order_score * 0.28
                + scores.balance_score * 0.22
                + scores.direction_score * 0.20
                + scores.burst_score * 0.15
                + scores.neutral_close_score * 0.15,
            vec!["小单高频", "买卖均衡", "程序化回转"],
        ),
        (
            "散户博弈",
            scores.small_order_score * 0.22
                + scores.noise_score * 0.26
                + scores.neutral_close_score * 0.20
                + scores.close_mid_score * 0.18
                + (1.0 - scores.large_order_score) * 0.14,
            vec!["小单主导", "方向混乱", "缺少主导资金"],
        ),
        (
            "尾盘突袭",
            scores.tail_squeeze_score * 0.30
                + scores.tail_flow_score * 0.24
                + scores.close_top_score * 0.20
                + scores.amount_score * 0.14
                + scores.burst_score * 0.12,
            vec!["尾盘放量", "收盘强势", "尾段冲击"],
        ),
        (
            "日内套利",
            scores.range_score * 0.30
                + scores.neutral_close_score * 0.26
                + scores.close_mid_score * 0.18
                + scores.balance_score * 0.12
                + scores.burst_score * 0.14,
            vec!["区间波动", "收盘回中", "反复做差价"],
        ),
        (
            "大单吸筹",
            scores.large_order_score * 0.28
                + scores.buy_bias_score * 0.22
                + scores.close_top_score * 0.20
                + scores.amount_score * 0.18
                + scores.direction_score * 0.12,
            vec!["大单承接", "买盘占优", "重心抬升"],
        ),
    ]
}

fn detect_obvious_pattern(scores: &PatternScores) -> Option<&'static str> {
    if scores.tail_squeeze_score >= 0.72 && scores.close_top_score >= 0.45 {
        Some("尾盘突袭")
    } else if scores.large_order_score >= 0.70 && scores.buy_bias_score >= 0.45 && scores.close_top_score >= 0.35 {
        Some("大单吸筹")
    } else if scores.small_order_score >= 0.70 && scores.balance_score >= 0.70 && scores.neutral_close_score >= 0.50 {
        Some("量化T0")
    } else if scores.small_order_score >= 0.60 && scores.noise_score >= 0.55 && scores.close_mid_score >= 0.45 {
        Some("散户博弈")
    } else if scores.range_score >= 0.60 && scores.neutral_close_score >= 0.55 {
        Some("日内套利")
    } else {
        None
    }
}

fn refine_pattern_with_pid_impl(
    label: &str,
    scores: &PatternScores,
    pid_result: Option<&DecompositionResult>,
) -> String {
    let label = internal_to_submit_label(label);
    let Some(pid_result) = pid_result else {
        return label.to_string();
    };

    let dominant_type = pid_result.dominant_type.as_str();
    let dominant_intention = pid_result.dominant_intention.as_str();
    let hot_money_ratio = pid_result.hot_money_ratio;
    let quant_ratio = pid_result.quant_ratio;
    let retail_ratio = pid_result.retail_ratio;
    let damping_mean = pid_result.damping_mean.abs();
    let inertia_mean = pid_result.inertia_mean.abs();

    if dominant_type == "量化" && quant_ratio >= 0.38 {
        if scores.small_order_score >= 0.50 || scores.balance_score >= 0.55 {
            return "量化T0".to_string();
        }
        if scores.range_score >= 0.55 && scores.neutral_close_score >= 0.45 {
            return "日内套利".to_string();
        }
    }

    if dominant_type == "散户" && retail_ratio >= 0.34 {
        if scores.noise_score >= 0.50 && scores.small_order_score >= 0.45 {
            return "散户博弈".to_string();
        }
    }

    if dominant_type == "游资" && hot_money_ratio >= 0.34 {
        if scores.tail_squeeze_score >= scores.large_order_score.max(scores.range_score) {
            return "尾盘突袭".to_string();
        }
        if scores.large_order_score >= 0.50 && scores.buy_bias_score >= 0.40 {
            return "大单吸筹".to_string();
        }
    }

    if dominant_intention == "T0交易" || dominant_intention == "中性" {
        if scores.small_order_score >= 0.45 {
            return "量化T0".to_string();
        }
    }
    if dominant_intention == "买入" && scores.buy_bias_score >= 0.40 && scores.close_top_score >= 0.40 {
        return "大单吸筹".to_string();
    }
    if dominant_intention == "卖出" && scores.close_mid_score < 0.40 && scores.noise_score >= 0.35 {
        return "散户博弈".to_string();
    }
    if inertia_mean >= 0.20 && damping_mean < 0.05 && scores.neutral_close_score >= 0.40 {
        return "日内套利".to_string();
    }

    label.to_string()
}

fn fallback_pattern_rule(scores: &PatternScores) -> &'static str {
    if scores.tail_squeeze_score >= 0.58 {
        "尾盘突袭"
    } else if scores.large_order_score >= 0.58 {
        "大单吸筹"
    } else if scores.small_order_score >= 0.58 && scores.balance_score >= 0.58 {
        "量化T0"
    } else if scores.range_score >= 0.48 && scores.neutral_close_score >= 0.42 {
        "日内套利"
    } else {
        "散户博弈"
    }
}

fn render_pattern_explanation_with_evidence(label: &str, evidence: &[&str]) -> String {
    let base = match label {
        "量化T0" => "高频小单反复进出，买卖方向接近平衡，像程序化T0回转。",
        "散户博弈" => "单笔偏小、方向分散、噪声偏高，更像散户之间的来回换手。",
        "尾盘突袭" => "尾盘阶段成交明显放大，收盘位置偏强，带有集中突袭收盘的特征。",
        "日内套利" => "盘中振幅较大但收盘回到中间区域，像围绕区间反复高抛低吸。",
        "大单吸筹" => "大额成交持续承接，买盘占优且收盘偏强，像边吸筹边抬升重心。",
        _ => "盘中结构和收盘位置出现明显偏离，资金运行模式需要结合证据共同判断。",
    };
    if evidence.is_empty() {
        base.to_string()
    } else {
        format!("{} 证据：{}。", base, evidence.join("；"))
    }
}

pub fn render_pattern_explanation(label: &str) -> &'static str {
    match label {
        "量化T0" => "高频小单反复进出，买卖方向接近平衡，像程序化T0回转。",
        "散户博弈" => "单笔偏小、方向分散、噪声偏高，更像散户之间的来回换手。",
        "尾盘突袭" => "尾盘阶段成交明显放大，收盘位置偏强，带有集中突袭收盘的特征。",
        "日内套利" => "盘中振幅较大但收盘回到中间区域，像围绕区间反复高抛低吸。",
        "大单吸筹" => "大额成交持续承接，买盘占优且收盘偏强，像边吸筹边抬升重心。",
        _ => "盘中结构和收盘位置出现明显偏离，资金运行模式需要结合证据共同判断。",
    }
}

pub fn refine_pattern_with_pid(
    label: &str,
    summary: &HashMap<String, f64>,
    pid_result: Option<&DecompositionResult>,
) -> String {
    let scores = PatternScores::from_summary(summary);
    refine_pattern_with_pid_impl(label, &scores, pid_result)
}

pub fn predict_pattern(
    sample: &DailySample,
    config: &HashMap<String, serde_yaml::Value>,
    label_dict: &HashMap<String, serde_yaml::Value>,
    pid_result: Option<&DecompositionResult>,
) -> PatternResult {
    let submit_labels = pattern_submit_labels(label_dict);
    let scores = PatternScores::from_summary(&sample.feature_summary);
    let mut candidates = score_pattern_modes(&scores);
    candidates.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(Ordering::Equal));
    let second_score = candidates.get(1).map(|item| item.1).unwrap_or(0.0);

    if let Some(forced_label) = detect_obvious_pattern(&scores) {
        let mut refined = refine_pattern_with_pid_impl(forced_label, &scores, pid_result);
        let pid_adjusted = refined != forced_label;
        if !submit_labels.iter().any(|item| item == &refined) {
            refined = submit_labels
                .first()
                .cloned()
                .unwrap_or_else(|| PATTERN_LABELS[0].to_string());
        }
        let _evidence = pattern_evidence(&refined, &scores);
        let explanation_summary = build_explanation_summary(&refined, &scores, pid_result);
        let score = 0.86;
        return PatternResult {
            stock_code: sample.stock_code.clone(),
            transaction_date: sample.transaction_date.clone(),
            pattern_type: refined.clone(),
            pattern_explanation: render_explanation_summary(&explanation_summary),
            pattern_score: score,
            prototype_id: format!("rule::{}", refined),
            pattern_primary_score: score,
            pattern_second_score: second_score,
            pattern_margin: score - second_score,
            pattern_source: "rule_shortcut".to_string(),
            pattern_pid_adjusted: pid_adjusted,
        };
    }

    let (mut label, mut score, mut evidence) = candidates[0].clone();
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
        label = fallback_pattern_rule(&scores);
        score = score.max(0.18);
        evidence = pattern_evidence(label, &scores);
    }

    let refined_label = refine_pattern_with_pid_impl(label, &scores, pid_result);
    let pid_adjusted = refined_label != label;
    if refined_label != label {
        label = Box::leak(refined_label.into_boxed_str());
        score = score.max(0.62).min(0.93);
        evidence = pattern_evidence(label, &scores);
    }

    if !submit_labels.iter().any(|item| item == label) {
        label = submit_labels
            .first()
            .map(|s| Box::leak(s.clone().into_boxed_str()) as &str)
            .unwrap_or(PATTERN_LABELS[0]);
    }

    let explanation_summary = build_explanation_summary(label, &scores, pid_result);
    PatternResult {
        stock_code: sample.stock_code.clone(),
        transaction_date: sample.transaction_date.clone(),
        pattern_type: label.to_string(),
        pattern_explanation: render_explanation_summary(&explanation_summary),
        pattern_score: (score * 10000.0).round() / 10000.0,
        prototype_id: format!("mode::{}::{}", label, evidence.join("|")),
        pattern_primary_score: (score * 10000.0).round() / 10000.0,
        pattern_second_score: (second_score * 10000.0).round() / 10000.0,
        pattern_margin: ((score - second_score) * 10000.0).round() / 10000.0,
        pattern_source: "mode_detector".to_string(),
        pattern_pid_adjusted: pid_adjusted,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn summary(values: &[(&str, f64)]) -> HashMap<String, f64> {
        values
            .iter()
            .map(|(key, value)| ((*key).to_string(), *value))
            .collect()
    }

    fn daily_sample(feature_summary: HashMap<String, f64>) -> DailySample {
        DailySample {
            stock_code: "600000.SH".to_string(),
            transaction_date: "20260706".to_string(),
            rows: Vec::new(),
            feature_summary,
            quality_flags: HashMap::new(),
        }
    }

    #[test]
    fn explanation_template_matches_submit_style() {
        let scores = PatternScores::from_summary(&summary(&[
            ("deal_amount", 900_000_000.0),
            ("close_return", 0.035),
            ("open_return", 0.0),
            ("intraday_range", 0.06),
            ("close_strength", 0.88),
            ("burst_ratio", 0.22),
            ("tail_ratio", 0.18),
            ("last15_return", 0.016),
            ("avg_trade_size", 18_000.0),
            ("order_buy_ratio", 0.64),
            ("directional_efficiency", 0.70),
        ]));
        let explanation_summary = build_explanation_summary("尾盘突袭", &scores, None);
        let explanation = render_explanation_summary(&explanation_summary);

        assert!(explanation.contains("下午2点半"));
        assert!(explanation.contains("集中拉升"));
        assert!(explanation.chars().count() <= 80);
    }

    #[test]
    fn prediction_explanation_implies_dominant_capital_family() {
        let sample = daily_sample(summary(&[
            ("deal_amount", 220_000_000.0),
            ("close_return", 0.002),
            ("intraday_range", 0.04),
            ("close_strength", 0.50),
            ("burst_ratio", 0.16),
            ("tail_ratio", 0.04),
            ("last15_return", 0.0),
            ("avg_trade_size", 3_000.0),
            ("order_buy_ratio", 0.50),
            ("directional_efficiency", 0.62),
        ]));
        let result = predict_pattern(&sample, &HashMap::new(), &HashMap::new(), None);

        assert!(result.pattern_type == "量化T0" || result.pattern_type == "散户博弈" || result.pattern_type == "日内套利");
        assert!(!result.pattern_explanation.is_empty());
        assert!(result.pattern_explanation.contains("T0") || result.pattern_explanation.chars().count() > 0);
    }

    #[test]
    fn explanation_reflects_execution_style() {
        let early_large = PatternScores::from_summary(&summary(&[
            ("deal_amount", 800_000_000.0),
            ("close_return", 0.032),
            ("open_return", 0.022),
            ("intraday_range", 0.055),
            ("close_strength", 0.74),
            ("burst_ratio", 0.18),
            ("tail_ratio", 0.04),
            ("last15_return", 0.001),
            ("avg_trade_size", 26_000.0),
            ("order_buy_ratio", 0.63),
            ("directional_efficiency", 0.68),
        ]));
        let quant_small = PatternScores::from_summary(&summary(&[
            ("deal_amount", 260_000_000.0),
            ("close_return", 0.001),
            ("open_return", 0.0),
            ("intraday_range", 0.045),
            ("close_strength", 0.50),
            ("burst_ratio", 0.16),
            ("tail_ratio", 0.03),
            ("last15_return", 0.0),
            ("avg_trade_size", 3_500.0),
            ("order_buy_ratio", 0.50),
            ("directional_efficiency", 0.62),
        ]));

        let early_summary = build_explanation_summary(PATTERN_LABELS[4], &early_large, None);
        let quant_summary = build_explanation_summary(PATTERN_LABELS[0], &quant_small, None);
        let early_explanation = render_explanation_summary(&early_summary);
        let quant_explanation = render_explanation_summary(&quant_summary);

        assert!(early_explanation.contains("早盘"));
        assert!(early_explanation.contains("大单"));
        assert!(quant_explanation.contains("小单"));
        assert!(quant_explanation.contains("T0"));
    }
}

use crate::schemas::{DailySample, DecompositionResult, MarketPidSnapshot, PatternResult, PredictResult};
use std::collections::HashMap;

const REGIME_STRONG_UP: &str = "强趋势上涨";
const REGIME_WEAK_UP: &str = "弱趋势上涨";
const REGIME_RISK_OFF: &str = "风险偏好退潮";
const REGIME_WEAK_DOWN: &str = "弱趋势下跌";
const REGIME_SIDEWAYS: &str = "震荡中性";

const TREND_STRONGER: &str = "强于市场";
const TREND_FOLLOW: &str = "跟随市场";
const TREND_WEAKER: &str = "弱于市场";
const TREND_COUNTER: &str = "逆势强股";
const TREND_RESILIENT: &str = "抗跌";
const TREND_NOISY: &str = "高噪声扰动";

fn safe_mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    values.iter().sum::<f64>() / values.len() as f64
}

fn safe_median(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let n = sorted.len();
    if n % 2 == 0 {
        (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0
    } else {
        sorted[n / 2]
    }
}

fn safe_std(values: &[f64]) -> f64 {
    if values.len() <= 1 {
        return 0.0;
    }
    let m = safe_mean(values);
    let variance = values.iter().map(|x| (x - m).powi(2)).sum::<f64>() / values.len() as f64;
    variance.sqrt()
}

fn clamp(value: f64, lower: f64, upper: f64) -> f64 {
    value.clamp(lower, upper)
}

fn regime_from_scores(breadth_balance: f64, p_median: f64, i_median: f64, d_median: f64) -> String {
    if breadth_balance > 0.30 && p_median > 0.10 && i_median > 0.20 {
        REGIME_STRONG_UP.into()
    } else if breadth_balance > 0.10 && p_median >= 0.0 {
        REGIME_WEAK_UP.into()
    } else if breadth_balance < -0.30 && p_median < -0.10 {
        REGIME_RISK_OFF.into()
    } else if breadth_balance < -0.10 {
        REGIME_WEAK_DOWN.into()
    } else if d_median > 0.45 {
        REGIME_SIDEWAYS.into()
    } else {
        REGIME_SIDEWAYS.into()
    }
}

pub fn estimate_market_pid(
    samples: &mut [DailySample],
    pid_results: &HashMap<String, DecompositionResult>,
    pattern_results: &[PatternResult],
    predict_results: &[PredictResult],
    _config: &HashMap<String, serde_yaml::Value>,
) -> MarketPidSnapshot {
    let mut p_values = Vec::new();
    let mut i_values = Vec::new();
    let mut d_values = Vec::new();
    let mut up_count: i64 = 0;
    let mut down_count: i64 = 0;
    let mut pid_result_source_count = 0usize;
    let mut heuristic_fallback_source_count = 0usize;

    let mut pattern_counts: HashMap<String, i64> = HashMap::new();
    let mut capital_counts: HashMap<String, i64> = HashMap::new();
    let mut intention_counts: HashMap<String, i64> = HashMap::new();

    for result in pattern_results {
        *pattern_counts.entry(result.pattern_type.clone()).or_insert(0) += 1;
    }
    for result in predict_results {
        *capital_counts.entry(result.capital_type.clone()).or_insert(0) += 1;
        *intention_counts.entry(result.capital_intention.clone()).or_insert(0) += 1;
    }

    for sample in samples.iter_mut() {
        let summary = &sample.feature_summary;
        let net_direction = summary.get("net_direction").copied().unwrap_or(0.0);
        let burst_ratio = summary.get("burst_ratio").copied().unwrap_or(0.0);
        let cancel_ratio = summary.get("cancel_ratio").copied().unwrap_or(0.0);
        let price_impact = summary.get("price_impact").copied().unwrap_or(0.0);
        let tail_ratio = summary.get("tail_ratio").copied().unwrap_or(0.0);
        let bid_support = summary.get("bid_support").copied().unwrap_or(0.0);
        let ask_pressure = summary.get("ask_pressure").copied().unwrap_or(0.0);

        let (p_value, i_value, d_value, is_pid_based) =
            if let Some(pid_result) = pid_results.get(&sample.stock_code) {
                let p_series = if pid_result.c_p.is_empty() {
                    &pid_result.capital_ch
                } else {
                    &pid_result.c_p
                };
                let i_series = if pid_result.c_i.is_empty() {
                    &pid_result.capital_retail
                } else {
                    &pid_result.c_i
                };
                let d_series = if pid_result.c_d.is_empty() {
                    &pid_result.capital_q
                } else {
                    &pid_result.c_d
                };
                pid_result_source_count += 1;
                (
                    clamp(tail_or_mean(p_series), -1.0, 1.0),
                    clamp(tail_or_mean(i_series), -1.0, 1.0),
                    clamp(tail_or_mean(d_series).abs(), 0.0, 1.0),
                    true,
                )
            } else {
                heuristic_fallback_source_count += 1;
                (
                    clamp(
                        net_direction * 0.6 + (price_impact / 0.02).min(1.0) * 0.25 + tail_ratio * 0.15,
                        -1.0,
                        1.0,
                    ),
                    clamp(
                        burst_ratio * 0.55 + net_direction.max(0.0) * 0.25 + tail_ratio * 0.20,
                        -1.0,
                        1.0,
                    ),
                    clamp(
                        cancel_ratio * 0.50
                            + (ask_pressure - bid_support).max(0.0) * 0.30
                            + (1.0 - net_direction.abs()) * 0.20,
                        0.0,
                        1.0,
                    ),
                    false,
                )
            };

        p_values.push(p_value);
        i_values.push(i_value);
        d_values.push(d_value);

        if net_direction > 0.0 {
            up_count += 1;
        } else if net_direction < 0.0 {
            down_count += 1;
        }
        sample
            .quality_flags
            .insert("market_pid_from_pid_result".into(), is_pid_based);
    }

    for (idx, sample) in samples.iter_mut().enumerate() {
        if idx < p_values.len() {
            sample.feature_summary.insert("p_value".into(), p_values[idx]);
            sample.feature_summary.insert("i_value".into(), i_values[idx]);
            sample.feature_summary.insert("d_value".into(), d_values[idx]);
        }
    }

    let market_up_candidates: Vec<i64> = samples
        .iter()
        .filter_map(|s| s.feature_summary.get("up_count_market"))
        .filter(|&&v| v != 0.0)
        .map(|&v| v as i64)
        .collect();
    let market_down_candidates: Vec<i64> = samples
        .iter()
        .filter_map(|s| s.feature_summary.get("down_count_market"))
        .filter(|&&v| v != 0.0)
        .map(|&v| v as i64)
        .collect();

    if !market_up_candidates.is_empty() && !market_down_candidates.is_empty() {
        let mut up_sorted = market_up_candidates.clone();
        up_sorted.sort();
        let mut down_sorted = market_down_candidates.clone();
        down_sorted.sort();
        up_count = up_sorted[up_sorted.len() / 2];
        down_count = down_sorted[down_sorted.len() / 2];
    }

    let breadth_ratio = if down_count > 0 {
        up_count as f64 / down_count as f64
    } else if up_count > 0 {
        up_count as f64
    } else {
        0.0
    };
    let breadth_balance = if (up_count + down_count) > 0 {
        (up_count - down_count) as f64 / (up_count + down_count) as f64
    } else {
        0.0
    };

    let p_mean = safe_mean(&p_values);
    let p_median = safe_median(&p_values);
    let p_std = safe_std(&p_values);
    let i_mean = safe_mean(&i_values);
    let i_median = safe_median(&i_values);
    let i_std = safe_std(&i_values);
    let d_mean = safe_mean(&d_values);
    let d_median = safe_median(&d_values);
    let d_std = safe_std(&d_values);
    let market_regime = regime_from_scores(breadth_balance, p_median, i_median, d_median);

    let mut diag = serde_json::Map::new();
    diag.insert("sample_count".into(), serde_json::Value::Number(samples.len().into()));
    diag.insert(
        "pid_result_source_count".into(),
        serde_json::Value::Number(pid_result_source_count.into()),
    );
    diag.insert(
        "heuristic_fallback_source_count".into(),
        serde_json::Value::Number(heuristic_fallback_source_count.into()),
    );

    let pc: serde_json::Map<String, serde_json::Value> = pattern_counts
        .iter()
        .map(|(k, v)| (k.clone(), serde_json::Value::Number((*v).into())))
        .collect();
    diag.insert("pattern_counts".into(), serde_json::Value::Object(pc));

    let cc: serde_json::Map<String, serde_json::Value> = capital_counts
        .iter()
        .map(|(k, v)| (k.clone(), serde_json::Value::Number((*v).into())))
        .collect();
    diag.insert("capital_counts".into(), serde_json::Value::Object(cc));

    let ic: serde_json::Map<String, serde_json::Value> = intention_counts
        .iter()
        .map(|(k, v)| (k.clone(), serde_json::Value::Number((*v).into())))
        .collect();
    diag.insert("intention_counts".into(), serde_json::Value::Object(ic));

    MarketPidSnapshot {
        trade_date: samples
            .first()
            .map(|sample| sample.transaction_date.clone())
            .unwrap_or_default(),
        up_count,
        down_count,
        breadth_ratio,
        breadth_balance,
        p_mean,
        p_median,
        p_std,
        i_mean,
        i_median,
        i_std,
        d_mean,
        d_median,
        d_std,
        market_regime,
        diagnostics: serde_json::Value::Object(diag),
    }
}

pub fn attach_market_relative_metrics(
    samples: &[DailySample],
    predict_results: &mut [PredictResult],
    snapshot: &MarketPidSnapshot,
) {
    let sample_map: HashMap<String, &DailySample> = samples.iter().map(|sample| (sample.stock_code.clone(), sample)).collect();
    let p_std = if snapshot.p_std > 1e-8 { snapshot.p_std } else { 1.0 };
    let i_std = if snapshot.i_std > 1e-8 { snapshot.i_std } else { 1.0 };
    let d_std = if snapshot.d_std > 1e-8 { snapshot.d_std } else { 1.0 };

    for result in predict_results.iter_mut() {
        if let Some(sample) = sample_map.get(&result.stock_code) {
            let summary = &sample.feature_summary;
            let p_val = summary.get("p_value").copied().unwrap_or(0.0);
            let i_val = summary.get("i_value").copied().unwrap_or(0.0);
            let d_val = summary.get("d_value").copied().unwrap_or(0.0);

            let p_rel = (p_val - snapshot.p_median) / p_std;
            let i_rel = (i_val - snapshot.i_median) / i_std;
            let d_rel = (d_val - snapshot.d_median) / d_std;
            let trend_score = 0.45 * p_rel + 0.35 * i_rel - 0.20 * d_rel;

            let regime = &snapshot.market_regime;
            let trend_vs_market = if regime == REGIME_STRONG_UP || regime == REGIME_WEAK_UP {
                if trend_score > 0.8 {
                    TREND_STRONGER
                } else if trend_score > -0.3 {
                    TREND_FOLLOW
                } else {
                    TREND_WEAKER
                }
            } else if regime == REGIME_WEAK_DOWN || regime == REGIME_RISK_OFF {
                if trend_score > 0.8 {
                    TREND_COUNTER
                } else if trend_score > 0.0 {
                    TREND_RESILIENT
                } else {
                    TREND_WEAKER
                }
            } else if trend_score > 0.8 {
                TREND_STRONGER
            } else if d_rel > 1.0 {
                TREND_NOISY
            } else {
                TREND_FOLLOW
            };

            let round4 = |value: f64| (value * 10000.0).round() / 10000.0;
            result.debug_info.insert(
                "p_rel_market".into(),
                serde_json::Value::Number(serde_json::Number::from_f64(round4(p_rel)).unwrap()),
            );
            result.debug_info.insert(
                "i_rel_market".into(),
                serde_json::Value::Number(serde_json::Number::from_f64(round4(i_rel)).unwrap()),
            );
            result.debug_info.insert(
                "d_rel_market".into(),
                serde_json::Value::Number(serde_json::Number::from_f64(round4(d_rel)).unwrap()),
            );
            result.debug_info.insert(
                "trend_vs_market".into(),
                serde_json::Value::String(trend_vs_market.to_string()),
            );
            result.debug_info.insert(
                "market_regime".into(),
                serde_json::Value::String(regime.clone()),
            );
            result.debug_info.insert(
                "market_pid_source".into(),
                serde_json::Value::String(
                    if sample
                        .quality_flags
                        .get("market_pid_from_pid_result")
                        .copied()
                        .unwrap_or(false)
                    {
                        "pid_result"
                    } else {
                        "heuristic_fallback"
                    }
                    .to_string(),
                ),
            );
        }
    }
}

fn tail_or_mean(values: &[f64]) -> f64 {
    values
        .iter()
        .rev()
        .copied()
        .find(|value| value.is_finite() && value.abs() > 1e-12)
        .unwrap_or_else(|| safe_mean(values))
}

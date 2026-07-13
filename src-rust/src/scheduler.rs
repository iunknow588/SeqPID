use crate::capital_model::predict_capitals;
use crate::config::{ConfigMap, get_bool};
use crate::exporter;
use crate::market_pid::{attach_market_relative_metrics, estimate_market_pid};
use crate::order_lifecycle::{time_value_to_seconds, OrderLifecycleResolver};
use crate::pattern_model::predict_pattern;
use crate::pid_decomposer::PIDDecomposer;
use crate::schemas::{DailySample, MarketPidSnapshot, PatternResult, PredictResult};
use anyhow::Result;
use csv::ReaderBuilder;
use encoding_rs::GB18030;
use std::collections::HashMap;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::Instant;

#[derive(Clone)]
struct QRow {
    time: f64,
    close: f64,
    open: f64,
    high: f64,
    low: f64,
    prev_close: f64,
    up: f64,
    down: f64,
    flat: f64,
    bid_px_1: f64,
    bid_px_2: f64,
    ask_px_1: f64,
    ask_px_2: f64,
    bid_vols: [f64; 10],
    ask_vols: [f64; 10],
}

fn iter_stock_dirs(d: &Path) -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = fs::read_dir(d).ok()
        .map(|e| e.filter_map(|e| e.ok()).filter(|e| e.path().is_dir()).map(|e| e.path()).collect())
        .unwrap_or_default();
    v.sort(); v
}
fn looks_like_stock(v: &str) -> bool {
    let n = v.trim().to_uppercase();
    if n.is_empty() { return false; }
    if n.ends_with(".SZ")||n.ends_with(".SH")||n.ends_with(".BJ") {
        return n.split('.').next().map(|h| h.chars().all(|c|c.is_ascii_digit())).unwrap_or(false);
    }
    n.chars().all(|c| c.is_ascii_digit())
}
fn load_universe(f: Option<&Path>) -> Result<(Option<Vec<String>>, Option<std::collections::HashSet<String>>)> {
    let p = match f { Some(p)=>p, None=>return Ok((None,None)) };
    if !p.exists() { anyhow::bail!("not found: {}",p.display()); }
    let c_raw = fs::read_to_string(p)?;
    let c = c_raw.strip_prefix('\u{FEFF}').unwrap_or(&c_raw);
    let mut ord = Vec::new(); let mut set = std::collections::HashSet::new();
    for (i,l) in c.lines().enumerate() {
        let s = l.split(',').next().unwrap_or("").trim().to_string();
        if s.is_empty() { continue; }
        if i==0 && !looks_like_stock(&s) { continue; }
        let n = s.to_uppercase();
        if set.insert(n.clone()) { ord.push(n); }
    }
    Ok((Some(ord), Some(set)))
}
fn find_ref(d: &Path) -> Option<PathBuf> {
    for n in &["reference_features.csv","features.csv"] { let p=d.join(n); if p.exists(){return Some(p);} }
    None
}
fn filt(d: Vec<PathBuf>, u: &Option<std::collections::HashSet<String>>) -> Vec<PathBuf> {
    match u { Some(u)=>d.into_iter().filter(|d|u.contains(&d.file_name().unwrap().to_string_lossy().to_uppercase())).collect(), None=>d }
}
fn miss(d: &Path) -> Vec<String> {
    let mut m=Vec::new();
    if !d.join("\u{9010}\u{7b14}\u{6210}\u{4ea4}.csv").exists(){m.push("trades".into());}
    if !d.join("\u{9010}\u{7b14}\u{59d4}\u{6258}.csv").exists(){m.push("orders".into());}
    if !d.join("\u{884c}\u{60c5}.csv").exists(){m.push("snapshots".into());}
    m
}
fn rsec(v:f64)->f64{(v*1e6).round()/1e6}

fn progress(percent: f64, message: &str) {
    println!("Progress {:5.1}% | {}", percent, message);
    let _ = io::stdout().flush();
}

fn stage_percent(start: f64, end: f64, current: usize, total: usize) -> f64 {
    if total == 0 {
        return end;
    }
    start + (end - start) * current.min(total) as f64 / total as f64
}
fn dec(b:&[u8])->String{ match std::str::from_utf8(b){Ok(t)=>t.to_string(),Err(_)=>GB18030.decode(b).0.to_string()} }

fn scaled_price(val: f64) -> f64 {
    if val > 1000.0 { val / 10000.0 } else { val }
}

fn time_to_window_id(value: i64) -> Option<usize> {
    if value <= 0 {
        return None;
    }
    let hhmmss = if value > 235959 { value / 1000 } else { value };
    let hh = hhmmss / 10000;
    let mm = (hhmmss % 10000) / 100;
    let total_minutes = hh * 60 + mm;
    let morning_start = 9 * 60 + 30;
    let morning_end = 11 * 60 + 30;
    let afternoon_start = 13 * 60;
    let afternoon_end = 15 * 60;
    if (morning_start..morning_end).contains(&total_minutes) {
        Some(((total_minutes - morning_start) / 5).min(23) as usize)
    } else if (afternoon_start..afternoon_end).contains(&total_minutes) {
        Some((24 + (total_minutes - afternoon_start) / 5).min(47) as usize)
    } else if total_minutes >= afternoon_end {
        Some(47)
    } else {
        None
    }
}

fn trade_side_sign(r: &csv::StringRecord, idx: &HashMap<&str, usize>) -> i32 {
    let raw = ["BS鏍囧織", "side", "涔板崠鏂瑰悜", "鎴愪氦鏂瑰悜", "濮旀墭浠ｇ爜"]
        .iter()
        .find_map(|name| idx.get(*name).and_then(|&i| r.get(i)))
        .unwrap_or("")
        .trim()
        .to_uppercase();
    if matches!(raw.as_str(), "B" | "BUY" | "1" | "买" | "主动买") {
        1
    } else if matches!(raw.as_str(), "S" | "SELL" | "2" | "卖" | "主动卖") {
        -1
    } else {
        0
    }
}

fn trade_side_sign_from_row(row: &HashMap<String, String>) -> i32 {
    let raw = [
        "BS\u{6807}\u{5fd7}",
        "side",
        "\u{4e70}\u{5356}\u{65b9}\u{5411}",
        "\u{6210}\u{4ea4}\u{65b9}\u{5411}",
        "\u{59d4}\u{6258}\u{4ee3}\u{7801}",
    ]
    .iter()
    .find_map(|name| row.get(*name))
    .map(|value| value.trim().to_uppercase())
    .unwrap_or_default();
    if matches!(raw.as_str(), "B" | "BUY" | "1" | "买" | "主动买") {
        1
    } else if matches!(raw.as_str(), "S" | "SELL" | "2" | "卖" | "主动卖") {
        -1
    } else {
        0
    }
}

fn is_aggressive_price_shaping(price: f64, quote: Option<&QRow>, active_sign: i32, amount: f64, fallback_hot_amount: f64) -> bool {
    let Some(quote) = quote else {
        return active_sign != 0 && amount >= fallback_hot_amount;
    };
    if active_sign > 0 {
        if quote.ask_px_2 > 0.0 && price >= quote.ask_px_2 {
            return true;
        }
        if quote.ask_px_2 <= 0.0 && quote.ask_px_1 > 0.0 && price > quote.ask_px_1 {
            return true;
        }
    } else if active_sign < 0 {
        if quote.bid_px_2 > 0.0 && price <= quote.bid_px_2 {
            return true;
        }
        if quote.bid_px_2 <= 0.0 && quote.bid_px_1 > 0.0 && price < quote.bid_px_1 {
            return true;
        }
    }
    false
}

fn qualifies_hot_money(
    bucket: &HashMap<String, String>,
    active_sign: i32,
    amount: f64,
    species_large_threshold: f64,
    active_fallback_hot_amount: f64,
    is_price_shaping_active: bool,
    quote_known: bool,
) -> bool {
    if active_sign == 0 {
        return false;
    }
    if !quote_known {
        return amount >= active_fallback_hot_amount;
    }
    if amount >= species_large_threshold {
        return true;
    }
    if !is_price_shaping_active {
        return false;
    }

    let same_dir_count = if active_sign > 0 {
        get_bucket_f64(bucket, "active_buy_count")
    } else {
        get_bucket_f64(bucket, "active_sell_count")
    };
    let same_dir_amount = if active_sign > 0 {
        get_bucket_f64(bucket, "active_buy_amount")
    } else {
        get_bucket_f64(bucket, "active_sell_amount")
    };
    let moderate_support = amount >= active_fallback_hot_amount
        && (same_dir_count >= 1.0 || same_dir_amount >= active_fallback_hot_amount);
    let strong_support =
        same_dir_count >= 2.0 && same_dir_amount >= active_fallback_hot_amount * 1.5;
    moderate_support || strong_support
}

fn lookup_quote_at_or_before(timestamp: i32, qrows: &[QRow]) -> Option<&QRow> {
    let mut candidate = None;
    for row in qrows {
        if row.time as i32 <= timestamp {
            candidate = Some(row);
        } else {
            break;
        }
    }
    candidate.or_else(|| qrows.first())
}

fn active_side_sign(price: f64, quote: Option<&QRow>, side_sign: i32) -> i32 {
    if let Some(quote) = quote {
        let bid_px_1 = quote.bid_px_1;
        let ask_px_1 = quote.ask_px_1;
        let has_quote = bid_px_1 > 0.0 || ask_px_1 > 0.0;
        if price > 0.0 && ask_px_1 > 0.0 && price >= ask_px_1 {
            return 1;
        }
        if price > 0.0 && bid_px_1 > 0.0 && price <= bid_px_1 {
            return -1;
        }
        if has_quote {
            return 0;
        }
    }
    side_sign
}

fn get_bucket_f64(bucket: &HashMap<String, String>, key: &str) -> f64 {
    bucket.get(key).and_then(|v| v.parse::<f64>().ok()).unwrap_or(0.0)
}

fn add_bucket_f64(bucket: &mut HashMap<String, String>, key: &str, value: f64) {
    let current = get_bucket_f64(bucket, key);
    bucket.insert(key.to_string(), (current + value).to_string());
}

fn get_nested_f64(config: &ConfigMap, section: &str, key: &str, default: f64) -> f64 {
    config
        .get(section)
        .and_then(|value| value.as_mapping())
        .and_then(|mapping| mapping.get(serde_yaml::Value::String(key.to_string())))
        .and_then(|value| value.as_f64())
        .unwrap_or(default)
}

fn get_nested_bool(config: &ConfigMap, section: &str, key: &str, default: bool) -> bool {
    config
        .get(section)
        .and_then(|value| value.as_mapping())
        .and_then(|mapping| mapping.get(serde_yaml::Value::String(key.to_string())))
        .and_then(|value| value.as_bool())
        .unwrap_or(default)
}

fn record_to_map(headers: &[String], record: &csv::StringRecord) -> HashMap<String, String> {
    headers
        .iter()
        .enumerate()
        .map(|(index, header)| {
            (
                header.clone(),
                record.get(index).unwrap_or("").trim().to_string(),
            )
        })
        .collect()
}

struct RawBuildOutput {
    summary: HashMap<String, f64>,
    rows: Vec<HashMap<String, String>>,
}

fn build_raw(sd: &Path, config: &ConfigMap) -> Result<RawBuildOutput> {
    let mut s = HashMap::new();

    // 1. Read quote rows
    let qp = sd.join("\u{884c}\u{60c5}.csv");
    let qb = fs::read(&qp)?;
    let qt = dec(&qb); let qt = qt.strip_prefix('\u{FEFF}').unwrap_or(&qt);
    let mut qr = ReaderBuilder::new().has_headers(true).from_reader(qt.as_bytes());
    let qh: Vec<String> = qr.headers()?.iter().map(|x| x.to_string()).collect();
    let qi: HashMap<&str,usize> = qh.iter().enumerate().map(|(i,h)|(h.as_str(),i)).collect();
    let qv = |r: &csv::StringRecord, n: &str| -> f64 {
        qi.get(n).and_then(|&i| r.get(i)).and_then(|v| v.parse::<f64>().ok()).unwrap_or(0.0)
    };

    let mut qrows: Vec<QRow> = Vec::new();
    for res in qr.records() {
        let r = match res { Ok(r)=>r, Err(_)=>continue };
        let mut bv = [0.0f64; 10]; let mut av = [0.0f64; 10];
        for i in 0..10 {
            bv[i] = qv(&r, &format!("\u{7533}\u{4e70}\u{91cf}{}", i+1));
            av[i] = qv(&r, &format!("\u{7533}\u{5356}\u{91cf}{}", i+1));
        }
        qrows.push(QRow {
            time: qv(&r, "\u{65f6}\u{95f4}"),
            close: scaled_price(qv(&r, "\u{6210}\u{4ea4}\u{4ef7}")),
            open: scaled_price(qv(&r, "\u{5f00}\u{76d8}\u{4ef7}")),
            high: scaled_price(qv(&r, "\u{6700}\u{9ad8}\u{4ef7}")),
            low: scaled_price(qv(&r, "\u{6700}\u{4f4e}\u{4ef7}")),
            prev_close: scaled_price(qv(&r, "\u{524d}\u{6536}\u{76d8}")),
            up: qv(&r, "\u{4e0a}\u{6da8}\u{54c1}\u{79cd}\u{6570}"),
            down: qv(&r, "\u{4e0b}\u{8dcc}\u{54c1}\u{79cd}\u{6570}"),
            flat: qv(&r, "\u{6301}\u{5e73}\u{54c1}\u{79cd}\u{6570}"),
            bid_px_1: scaled_price(qv(&r, "\u{7533}\u{4e70}\u{4ef7}1")),
            bid_px_2: scaled_price(qv(&r, "\u{7533}\u{4e70}\u{4ef7}2")),
            ask_px_1: scaled_price(qv(&r, "\u{7533}\u{5356}\u{4ef7}1")),
            ask_px_2: scaled_price(qv(&r, "\u{7533}\u{5356}\u{4ef7}2")),
            bid_vols: bv, ask_vols: av,
        });
    }
    let active_qrows: Vec<QRow> = qrows
        .iter()
        .filter(|quote| quote.bid_px_1 > 0.0 || quote.ask_px_1 > 0.0)
        .cloned()
        .collect();

    let last_q = qrows.last();
    let prev_close = last_q.map(|q| q.prev_close).unwrap_or(0.0);
    let up_count = last_q.map(|q| q.up).unwrap_or(0.0) as i64;
    let down_count = last_q.map(|q| q.down).unwrap_or(0.0) as i64;
    let flat_count = last_q.map(|q| q.flat).unwrap_or(0.0) as i64;

    // bid/ask from last quote
    let (bid_vol, ask_vol) = if let Some(lq) = last_q {
        (lq.bid_vols.iter().sum::<f64>(), lq.ask_vols.iter().sum::<f64>())
    } else { (0.0, 0.0) };
    let total_liq = bid_vol + ask_vol;
    let bid_support = if total_liq > 0.0 { bid_vol / total_liq } else { 0.0 };
    let ask_pressure = if total_liq > 0.0 { ask_vol / total_liq } else { 0.0 };

    // Collect non-zero prices from quotes
    let nz_closes: Vec<f64> = qrows.iter().map(|q| q.close).filter(|&c| c > 0.0).collect();
    let nz_opens: Vec<f64> = qrows.iter().map(|q| q.open).filter(|&c| c > 0.0).collect();
    let nz_highs: Vec<f64> = qrows.iter().map(|q| q.high).filter(|&c| c > 0.0).collect();
    let nz_lows: Vec<f64> = qrows.iter().map(|q| q.low).filter(|&c| c > 0.0).collect();

    let close_price = nz_closes.last().copied().unwrap_or(0.0);
    let open_price = nz_opens.first().copied().unwrap_or(0.0);
    let high_price = nz_highs.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let high_price = if high_price == f64::NEG_INFINITY { close_price } else { high_price };
    let low_price = nz_lows.iter().copied().fold(f64::INFINITY, f64::min);
    let low_price = if low_price == f64::INFINITY { close_price } else { low_price };

    let price_impact = if prev_close > 0.0 && close_price > 0.0 {
        (close_price - prev_close).abs() / prev_close
    } else { 0.0 };

    let reference_open = if open_price > 0.0 { open_price } else { prev_close };
    let mut net_direction = 0.0;
    let mut close_return = 0.0;
    let mut open_return = 0.0;
    let mut intraday_range = 0.0;
    let mut close_strength = 0.0;

    if prev_close > 0.0 && close_price > 0.0 {
        net_direction = (close_price - reference_open) / prev_close;
        close_return = (close_price - prev_close) / prev_close;
        open_return = (reference_open - prev_close) / prev_close;
        if high_price > 0.0 && low_price > 0.0 {
            intraday_range = (high_price - low_price) / prev_close;
        }
    }
    if high_price > low_price && close_price > 0.0 {
        close_strength = (close_price - low_price) / (high_price - low_price);
    }

    // 2. Read orders for both lifecycle recovery and summary stats
    let mut order_rows: Vec<HashMap<String, String>> = Vec::new();
    let mut cancel_ratio = 0.0;
    let mut order_buy_ratio = 0.5;
    let mut order_count = 0usize;
    let op = sd.join("\u{9010}\u{7b14}\u{59d4}\u{6258}.csv");
    if op.exists() {
        if let Ok(ob) = fs::read(&op) {
            let ot = dec(&ob);
            let ot = ot.strip_prefix('\u{FEFF}').unwrap_or(&ot);
            let mut or_ = ReaderBuilder::new().has_headers(true).from_reader(ot.as_bytes());
            if let Ok(hd) = or_.headers() {
                let oh: Vec<String> = hd.iter().map(|x| x.to_string()).collect();
                let oi: HashMap<&str, usize> = oh.iter().enumerate().map(|(i, h)| (h.as_str(), i)).collect();
                let osv = |r: &csv::StringRecord, n: &str| -> String {
                    oi.get(n).and_then(|&i| r.get(i)).unwrap_or("").trim().to_string()
                };
                let mut cancel_like = 0usize;
                let mut buy_orders = 0usize;
                let mut sell_orders = 0usize;
                for res in or_.records() {
                    let r = match res { Ok(r) => r, Err(_) => continue };
                    order_count += 1;
                    order_rows.push(record_to_map(&oh, &r));
                    let otype = osv(&r, "\u{59d4}\u{6258}\u{7c7b}\u{578b}");
                    let code = osv(&r, "\u{59d4}\u{6258}\u{4ee3}\u{7801}");
                    if !otype.is_empty() && otype != "0" {
                        cancel_like += 1;
                    }
                    if code == "B" {
                        buy_orders += 1;
                    }
                    if code == "S" {
                        sell_orders += 1;
                    }
                }
                cancel_ratio = if order_count > 0 { cancel_like as f64 / order_count as f64 } else { 0.0 };
                order_buy_ratio = if buy_orders + sell_orders > 0 {
                    buy_orders as f64 / (buy_orders + sell_orders) as f64
                } else {
                    0.5
                };
            }
        }
    }

    // 3. Read trades
    let tp = sd.join("\u{9010}\u{7b14}\u{6210}\u{4ea4}.csv");
    let tb = fs::read(&tp)?;
    let tt = dec(&tb); let tt = tt.strip_prefix('\u{FEFF}').unwrap_or(&tt);
    let mut tr = ReaderBuilder::new().has_headers(true).from_reader(tt.as_bytes());
    let th: Vec<String> = tr.headers()?.iter().map(|x| x.to_string()).collect();
    let species_large_threshold = get_nested_f64(config, "species_rules", "large_order_amount_threshold", 500_000.0);
    let passive_survival_minutes = get_nested_f64(config, "species_rules", "passive_survival_minutes", 5.0);
    let active_fallback_to_side = get_nested_bool(config, "species_rules", "active_fallback_to_side", true);
    let active_fallback_hot_amount = get_nested_f64(config, "species_rules", "active_fallback_hot_amount", 100_000.0);
    let mut trade_rows: Vec<HashMap<String, String>> = Vec::new();
    for res in tr.records() {
        let r = match res { Ok(r) => r, Err(_) => continue };
        trade_rows.push(record_to_map(&th, &r));
    }
    let mut lifecycle_resolver = OrderLifecycleResolver::new(&order_rows, &trade_rows);

    let mut trade_amounts: Vec<f64> = Vec::new();
    let mut trade_times: Vec<i64> = Vec::new();
    let mut total_volume = 0.0f64;
    let mut bucket_amounts: HashMap<i64, f64> = HashMap::new();
    let mut pid_buckets: Vec<HashMap<String, String>> = (0..48)
        .map(|idx| {
            let mut bucket = HashMap::new();
            bucket.insert("window_id".into(), idx.to_string());
            for key in [
                "deal_amount",
                "signal_deal_buy_amount",
                "signal_deal_sell_amount",
                "CH_rule_t",
                "Q_rule_t",
                "R_seed_t",
                "signed_large_active_amount",
                "signed_mix_qr_amount",
                "large_active_buy_amount",
                "large_active_sell_amount",
                "small_passive_buy_amount",
                "small_passive_sell_amount",
                "unknown_side_amount",
                "active_non_large_amount",
                "passive_quant_amount",
                "passive_retail_amount",
                "window_open_price",
                "window_close_price",
                "window_trade_count",
                "active_inferred_count",
                "side_fallback_count",
                "active_buy_count",
                "active_sell_count",
                "active_buy_amount",
                "active_sell_amount",
                "order_age_recovered_count",
                "order_age_missing_count",
                "order_age_direct_count",
                "order_age_fifo_count",
                "order_age_unresolved_count",
                "pi_max_price_impact_pct",
            ] {
                bucket.insert(key.into(), "0".into());
            }
            bucket
        })
        .collect();

    for row in &trade_rows {
        let trade_type = row.get("\u{6210}\u{4ea4}\u{4ee3}\u{7801}").map(|v| v.trim()).unwrap_or("");
        let trade_type_upper = trade_type.to_uppercase();
        if matches!(trade_type_upper.as_str(), "D" | "C" | "CANCEL" | "DELETE") || trade_type.contains('\u{64a4}') {
            continue;
        }
        let price = row
            .get("\u{6210}\u{4ea4}\u{4ef7}\u{683c}")
            .or_else(|| row.get("price"))
            .and_then(|v| v.parse::<f64>().ok())
            .map(scaled_price)
            .unwrap_or(0.0);
        let volume = row
            .get("\u{6210}\u{4ea4}\u{6570}\u{91cf}")
            .or_else(|| row.get("volume"))
            .and_then(|v| v.parse::<f64>().ok())
            .unwrap_or(0.0);
        let time = row
            .get("\u{65f6}\u{95f4}")
            .or_else(|| row.get("time"))
            .or_else(|| row.get("timestamp_ms"))
            .and_then(|v| v.parse::<f64>().ok())
            .unwrap_or(0.0) as i64;
        let explicit_amount = row
            .get("\u{6210}\u{4ea4}\u{91d1}\u{989d}")
            .or_else(|| row.get("amount"))
            .and_then(|v| v.parse::<f64>().ok())
            .unwrap_or(0.0);
        let amount = if explicit_amount > 0.0 { explicit_amount } else { price * volume };
        if amount <= 0.0 {
            continue;
        }
        trade_amounts.push(amount);
        trade_times.push(time);
        total_volume += volume;

        let hhmm = time / 100000;
        let bucket = if hhmm > 0 { hhmm / 5 } else { 0 };
        *bucket_amounts.entry(bucket).or_insert(0.0) += amount;

        let window_id = time_to_window_id(time);
        if let Some(window_id) = window_id {
            let side_sign = trade_side_sign_from_row(row);
            let quote = lookup_quote_at_or_before(time as i32, &active_qrows);
            let active_sign = if quote.is_some() {
                active_side_sign(price, quote, side_sign)
            } else if active_fallback_to_side {
                side_sign
            } else {
                0
            };
            let bucket = &mut pid_buckets[window_id];
            add_bucket_f64(bucket, "deal_amount", amount);
            add_bucket_f64(bucket, "window_trade_count", 1.0);
            if get_bucket_f64(bucket, "window_open_price") <= 0.0 && price > 0.0 {
                bucket.insert("window_open_price".into(), price.to_string());
            }
            if price > 0.0 {
                bucket.insert("window_close_price".into(), price.to_string());
            }
            if active_sign != 0 && quote.is_some() {
                add_bucket_f64(bucket, "active_inferred_count", 1.0);
            } else if active_sign != 0 {
                add_bucket_f64(bucket, "side_fallback_count", 1.0);
            }
            let signed_amount = side_sign as f64 * amount;
            if side_sign > 0 {
                add_bucket_f64(bucket, "signal_deal_buy_amount", amount);
            } else if side_sign < 0 {
                add_bucket_f64(bucket, "signal_deal_sell_amount", amount);
            }
            let order_age = lifecycle_resolver.lookup_order_age_minutes(
                row,
                row.get("\u{65f6}\u{95f4}")
                    .or_else(|| row.get("time"))
                    .or_else(|| row.get("timestamp_ms"))
                    .map(|v| v.as_str())
                    .and_then(time_value_to_seconds),
                active_sign,
                side_sign,
                price,
                volume,
            );
            if order_age.order_age_minutes.is_some() {
                add_bucket_f64(bucket, "order_age_recovered_count", 1.0);
            } else {
                add_bucket_f64(bucket, "order_age_missing_count", 1.0);
            }
            match order_age.recovery_method.as_str() {
                "direct_order_id" => add_bucket_f64(bucket, "order_age_direct_count", 1.0),
                "fifo_price_queue" => add_bucket_f64(bucket, "order_age_fifo_count", 1.0),
                _ => add_bucket_f64(bucket, "order_age_unresolved_count", 1.0),
            }

            let is_active = active_sign != 0;
            let is_price_shaping_active =
                is_active && is_aggressive_price_shaping(price, quote, active_sign, amount, active_fallback_hot_amount);
            let is_large_active = qualifies_hot_money(
                bucket,
                active_sign,
                amount,
                species_large_threshold,
                active_fallback_hot_amount,
                is_price_shaping_active,
                quote.is_some(),
            );
            if is_active {
                if active_sign > 0 {
                    add_bucket_f64(bucket, "active_buy_count", 1.0);
                    add_bucket_f64(bucket, "active_buy_amount", amount);
                } else {
                    add_bucket_f64(bucket, "active_sell_count", 1.0);
                    add_bucket_f64(bucket, "active_sell_amount", amount);
                }
            }
            let rule_signed_amount = if is_large_active {
                active_sign as f64 * amount
            } else {
                signed_amount
            };
            if is_large_active {
                add_bucket_f64(bucket, "CH_rule_t", rule_signed_amount);
                add_bucket_f64(bucket, "signed_large_active_amount", rule_signed_amount);
                if rule_signed_amount > 0.0 {
                    add_bucket_f64(bucket, "large_active_buy_amount", amount);
                } else {
                    add_bucket_f64(bucket, "large_active_sell_amount", amount);
                }
            } else {
                if !is_active && order_age.order_age_minutes.unwrap_or(0.0) > passive_survival_minutes {
                    add_bucket_f64(bucket, "R_seed_t", rule_signed_amount);
                    add_bucket_f64(bucket, "passive_retail_amount", rule_signed_amount);
                } else if is_active || active_fallback_to_side {
                    let quant_amount = if is_active { active_sign as f64 * amount } else { rule_signed_amount };
                    add_bucket_f64(bucket, "Q_rule_t", quant_amount);
                    if is_active {
                        add_bucket_f64(bucket, "active_non_large_amount", quant_amount);
                    } else {
                        add_bucket_f64(bucket, "passive_quant_amount", quant_amount);
                        if order_age.order_age_minutes.is_none() {
                            add_bucket_f64(bucket, "low_fallback_count", 1.0);
                        }
                    }
                } else {
                    add_bucket_f64(bucket, "Q_rule_t", rule_signed_amount);
                    add_bucket_f64(bucket, "passive_quant_amount", rule_signed_amount);
                    if order_age.order_age_minutes.is_none() {
                        add_bucket_f64(bucket, "low_fallback_count", 1.0);
                    }
                }
                add_bucket_f64(bucket, "signed_mix_qr_amount", signed_amount);
                if side_sign > 0 {
                    add_bucket_f64(bucket, "small_passive_buy_amount", amount);
                } else if side_sign < 0 {
                    add_bucket_f64(bucket, "small_passive_sell_amount", amount);
                } else {
                    add_bucket_f64(bucket, "unknown_side_amount", amount);
                }
            }
        }
    }

    let mut previous_close = 0.0;
    for bucket in &mut pid_buckets {
        let open_price = get_bucket_f64(bucket, "window_open_price");
        let close_price = get_bucket_f64(bucket, "window_close_price");
        let impact = if previous_close > 0.0 && close_price > 0.0 {
            (close_price - previous_close) / previous_close
        } else if open_price > 0.0 && close_price > 0.0 {
            (close_price - open_price) / open_price
        } else {
            0.0
        };
        bucket.insert("pi_max_price_impact_pct".into(), impact.to_string());
        if close_price > 0.0 {
            previous_close = close_price;
        }
    }

    let total_trade_amount: f64 = trade_amounts.iter().sum();
    let tail_trade_amount: f64 = trade_amounts.iter().zip(trade_times.iter())
        .filter(|(_, &t)| t >= 143000000)
        .map(|(&a, _)| a)
        .sum();
    let avg_trade_size = if !trade_amounts.is_empty() {
        total_trade_amount / trade_amounts.len() as f64
    } else { 0.0 };

    let burst_ratio = if !bucket_amounts.is_empty() {
        let total_b: f64 = bucket_amounts.values().sum();
        if total_b > 0.0 {
            bucket_amounts.values().copied().fold(0.0f64, f64::max) / total_b
        } else { 0.0 }
    } else { 0.0 };

    let buy_amount = net_direction.max(0.0) * total_trade_amount;
    let sell_amount = (-net_direction).max(0.0) * total_trade_amount;
    let tail_ratio = if total_trade_amount > 0.0 { tail_trade_amount / total_trade_amount } else { 0.0 };

    // last15_return from quote rows
    let last15_prices: Vec<f64> = qrows.iter()
        .filter(|q| q.time >= 144500000.0 && q.close > 0.0)
        .map(|q| q.close)
        .collect();
    let last15_return = if last15_prices.len() >= 2 && prev_close > 0.0 {
        (last15_prices[last15_prices.len()-1] - last15_prices[0]) / prev_close
    } else { 0.0 };

    let directional_efficiency = if intraday_range > 0.0 {
        ((close_return - open_return).abs() / intraday_range).min(1.0)
    } else { 0.0 };
    let reversal_strength = close_return - open_return;

    s.insert("deal_amount".into(), total_trade_amount);
    s.insert("buy_amount".into(), buy_amount);
    s.insert("sell_amount".into(), sell_amount);
    s.insert("net_direction".into(), net_direction);
    s.insert("close_return".into(), close_return);
    s.insert("open_return".into(), open_return);
    s.insert("intraday_range".into(), intraday_range);
    s.insert("close_strength".into(), close_strength);
    s.insert("cancel_ratio".into(), cancel_ratio);
    s.insert("burst_ratio".into(), burst_ratio);
    s.insert("price_impact".into(), price_impact);
    s.insert("bid_support".into(), bid_support);
    s.insert("ask_pressure".into(), ask_pressure);
    s.insert("tail_ratio".into(), tail_ratio);
    s.insert("last15_return".into(), last15_return);
    s.insert("window_count".into(), bucket_amounts.len().max(1) as f64);
    s.insert("total_volume".into(), total_volume);
    s.insert("order_count".into(), order_count as f64);
    s.insert("trade_count".into(), trade_amounts.len() as f64);
    s.insert("avg_trade_size".into(), avg_trade_size);
    s.insert("order_buy_ratio".into(), order_buy_ratio);
    s.insert("directional_efficiency".into(), directional_efficiency);
    s.insert("reversal_strength".into(), reversal_strength);
    s.insert("up_count_market".into(), up_count as f64);
    s.insert("down_count_market".into(), down_count as f64);
    s.insert("flat_count_market".into(), flat_count as f64);
    let raw_order_age_recovered_count: f64 = pid_buckets.iter().map(|row| get_bucket_f64(row, "order_age_recovered_count")).sum();
    let raw_order_age_missing_count: f64 = pid_buckets.iter().map(|row| get_bucket_f64(row, "order_age_missing_count")).sum();
    let raw_order_age_direct_count: f64 = pid_buckets.iter().map(|row| get_bucket_f64(row, "order_age_direct_count")).sum();
    let raw_order_age_fifo_count: f64 = pid_buckets.iter().map(|row| get_bucket_f64(row, "order_age_fifo_count")).sum();
    let raw_order_age_unresolved_count: f64 = pid_buckets.iter().map(|row| get_bucket_f64(row, "order_age_unresolved_count")).sum();
    let raw_order_age_total_count = raw_order_age_recovered_count + raw_order_age_missing_count;
    s.insert("raw_order_age_recovered_count".into(), raw_order_age_recovered_count);
    s.insert("raw_order_age_missing_count".into(), raw_order_age_missing_count);
    s.insert("raw_order_age_direct_count".into(), raw_order_age_direct_count);
    s.insert("raw_order_age_fifo_count".into(), raw_order_age_fifo_count);
    s.insert("raw_order_age_unresolved_count".into(), raw_order_age_unresolved_count);
    s.insert(
        "raw_order_age_recovery_ratio".into(),
        if raw_order_age_total_count > 0.0 {
            raw_order_age_recovered_count / raw_order_age_total_count
        } else {
            0.0
        },
    );
    let rows = pid_buckets
        .into_iter()
        .filter(|row| row.get("deal_amount").and_then(|v| v.parse::<f64>().ok()).unwrap_or(0.0) > 0.0)
        .collect();
    Ok(RawBuildOutput { summary: s, rows })
}

fn build_ref(_h: &[String], ci: &HashMap<&str,usize>, rows: impl Iterator<Item=csv::StringRecord>) -> HashMap<String,f64> {
    let gv = |r: &csv::StringRecord, ns: &[&str]| -> f64 {
        for n in ns { if let Some(&i)=ci.get(n){if let Some(v)=r.get(i){if let Ok(v)=v.parse::<f64>(){return v;}}} }
        0.0
    };
    let mut s=HashMap::new();
    let (mut ds,mut bs2,mut ss,mut cns,mut brs,mut bis,mut aks)=(0.0,0.0,0.0,0.0,0.0,0.0,0.0);
    let mut n=0u64; let mut fo=0.0; let mut lv=[0.0f64;13];
    for r in rows {
        if n==0{fo=gv(&r,&["open_return"]);}
        ds+=gv(&r,&["deal_amount","amount"]); bs2+=gv(&r,&["signal_deal_buy_amount","buy_amount"]);
        ss+=gv(&r,&["signal_deal_sell_amount","sell_amount"]);
        cns+=gv(&r,&["cb_cancel_order_ratio","cancel_ratio"]); brs+=gv(&r,&["rs_burst_ratio","burst_ratio"]);
        bis+=gv(&r,&["obp_at_best_bid_ratio","bid_support"]); aks+=gv(&r,&["obp_at_best_ask_ratio","ask_pressure"]);
        lv[0]=gv(&r,&["close_return","pct_change"]); lv[1]=gv(&r,&["open_return"]);
        lv[2]=gv(&r,&["intraday_range"]); lv[3]=gv(&r,&["close_strength"]);
        lv[4]=gv(&r,&["tail_ratio"]); lv[5]=gv(&r,&["last15_return"]);
        lv[6]=gv(&r,&["avg_trade_size"]); lv[7]=gv(&r,&["order_buy_ratio"]);
        lv[8]=gv(&r,&["directional_efficiency"]); lv[9]=gv(&r,&["reversal_strength"]);
        lv[10]=gv(&r,&["price_impact","pi_max_price_impact_pct"]); lv[11]=gv(&r,&["up_count_market","market_up_count"]);
        lv[12]=gv(&r,&["down_count_market","market_down_count"]);
        n+=1;
    }
    if n==0{return s;} let nf=n as f64;
    let nd=if ds>0.0{(bs2-ss)/ds}else{0.0};
    s.insert("deal_amount".into(),ds); s.insert("buy_amount".into(),bs2);
    s.insert("sell_amount".into(),ss); s.insert("net_direction".into(),nd);
    s.insert("cancel_ratio".into(),cns/nf); s.insert("burst_ratio".into(),brs/nf);
    s.insert("bid_support".into(),bis/nf); s.insert("ask_pressure".into(),aks/nf);
    s.insert("close_return".into(),lv[0]); s.insert("open_return".into(),fo);
    s.insert("intraday_range".into(),lv[2]); s.insert("close_strength".into(),lv[3]);
    s.insert("tail_ratio".into(),lv[4]); s.insert("last15_return".into(),lv[5]);
    s.insert("avg_trade_size".into(),lv[6]);
    s.insert("order_buy_ratio".into(),if lv[7]!=0.0{lv[7]}else{0.5});
    s.insert("directional_efficiency".into(),lv[8]); s.insert("reversal_strength".into(),lv[9]);
    s.insert("price_impact".into(),lv[10]); s.insert("up_count_market".into(),lv[11]);
    s.insert("down_count_market".into(),lv[12]);
    s
}

fn load_samples(inp: &Path, td: &str, sl: Option<usize>, so: usize, su: &Option<std::collections::HashSet<String>>, cfg: &ConfigMap)
    -> (Vec<DailySample>, HashMap<String,Vec<String>>, Vec<HashMap<String,f64>>)
{
    let mut smp=Vec::new(); let mut inc=HashMap::new(); let mut stm=Vec::new();
    if let Some(rf)=find_ref(inp) {
        if let Ok(b)=fs::read(&rf) {
            let t=dec(&b); let t=t.strip_prefix('\u{FEFF}').unwrap_or(&t);
            let mut rdr=ReaderBuilder::new().has_headers(true).from_reader(t.as_bytes());
            if let Ok(hd)=rdr.headers() {
                let hdr: Vec<String>=hd.iter().map(|x|x.to_string()).collect();
                let ci: HashMap<&str,usize>=hdr.iter().enumerate().map(|(i,h)|(h.as_str(),i)).collect();
                let si=ci.get("symbol").or_else(||ci.get("stock_code")).copied();
                let di=ci.get("date").or_else(||ci.get("transaction_date")).copied();
                if let Some(si)=si {
                    let mut sym: HashMap<String,Vec<csv::StringRecord>>=HashMap::new();
                    for res in rdr.records() {
                        let r=match res{Ok(r)=>r,Err(_)=>continue};
                        if let Some(di)=di{if let Some(d)=r.get(di){if !d.is_empty()&&!d.contains(td){continue;}}}
                        if let Some(s)=r.get(si){if !s.is_empty(){sym.entry(s.to_uppercase()).or_default().push(r.clone());}}
                    }
                    let mut keys: Vec<String>=sym.keys().cloned().collect(); keys.sort();
                    if let Some(u)=su{keys.retain(|s|u.contains(s));}
                    let keys: Vec<String>=keys.into_iter().skip(so).take(sl.unwrap_or(usize::MAX)).collect();
                    let total=keys.len();
                    progress(1.0, &format!("building samples 0/{}", total));
                    for (idx,k) in keys.iter().enumerate() {
                        let st=Instant::now(); let rows=sym.remove(k).unwrap_or_default();
                        if rows.is_empty(){
                            progress(stage_percent(0.0,45.0,idx+1,total), &format!("skipped empty sample {}/{} {}", idx+1, total, k));
                            continue;
                        }
                        let sm=build_ref(&hdr,&ci,rows.iter().cloned());
                        if sm.is_empty(){
                            progress(stage_percent(0.0,45.0,idx+1,total), &format!("skipped empty sample {}/{} {}", idx+1, total, k));
                            continue;
                        }
                        let el=st.elapsed().as_secs_f64();
                        let feature_rows: Vec<HashMap<String, String>> = rows
                            .iter()
                            .map(|record| {
                                hdr.iter()
                                    .enumerate()
                                    .map(|(idx, key)| (key.clone(), record.get(idx).unwrap_or("").to_string()))
                                    .collect()
                            })
                            .collect();
                        smp.push(DailySample{stock_code:k.clone(),transaction_date:td.into(),rows:feature_rows,feature_summary:sm,quality_flags:HashMap::new()});
                        let mut t2=HashMap::new(); t2.insert("sample_build_seconds".into(),rsec(el)); stm.push(t2);
                        progress(stage_percent(0.0,45.0,idx+1,total), &format!("built sample {}/{} {}", idx+1, total, k));
                    }
                }
            }
        }
        return (smp,inc,stm);
    }
    let sd: Vec<PathBuf>=filt(iter_stock_dirs(inp),su).into_iter().skip(so).take(sl.unwrap_or(usize::MAX)).collect();
    let total=sd.len();
    progress(1.0, &format!("building samples 0/{}", total));
    for (idx,d) in sd.iter().enumerate() {
        let ms=miss(d);
        let name=d.file_name().unwrap().to_string_lossy().to_string();
        if !ms.is_empty(){
            inc.insert(name.clone(),ms);
            progress(stage_percent(0.0,45.0,idx+1,total), &format!("skipped incomplete sample {}/{} {}", idx+1, total, name));
            continue;
        }
        let st=Instant::now();
        let sym=name.to_uppercase();
        let raw=match build_raw(d, cfg){
            Ok(s) if !s.summary.is_empty()=>s,
            _=>{
                inc.insert(sym.clone(),vec!["no_data".into()]);
                progress(stage_percent(0.0,45.0,idx+1,total), &format!("skipped empty sample {}/{} {}", idx+1, total, sym));
                continue;
            }
        };
        let el=st.elapsed().as_secs_f64();
        smp.push(DailySample{stock_code:sym.clone(),transaction_date:td.into(),rows:raw.rows,feature_summary:raw.summary,quality_flags:HashMap::new()});
        let mut t2=HashMap::new(); t2.insert("sample_build_seconds".into(),rsec(el)); stm.push(t2);
        progress(stage_percent(0.0,45.0,idx+1,total), &format!("built sample {}/{} {}", idx+1, total, sym));
    }
    (smp,inc,stm)
}

fn sort_ord<T>(r: &mut [T], req: &Option<Vec<String>>, kf: impl Fn(&T)->String) {
    if let Some(o)=req {
        let m: HashMap<String,usize>=o.iter().enumerate().map(|(i,s)|(s.clone(),i)).collect();
        r.sort_by_key(|i|m.get(&kf(i).to_uppercase()).copied().unwrap_or(usize::MAX));
    }
}

fn build_market_average_summary(samples: &[DailySample]) -> HashMap<String, f64> {
    let mut numeric_values: HashMap<String, Vec<f64>> = HashMap::new();
    for sample in samples {
        for (key, value) in &sample.feature_summary {
            numeric_values.entry(key.clone()).or_default().push(*value);
        }
    }

    let mut summary = HashMap::new();
    for (key, mut values) in numeric_values {
        if values.is_empty() {
            continue;
        }
        values.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let mid = values.len() / 2;
        let median = if values.len() % 2 == 0 {
            (values[mid - 1] + values[mid]) / 2.0
        } else {
            values[mid]
        };
        summary.insert(key, median);
    }
    summary.entry("order_buy_ratio".into()).or_insert(0.5);
    summary.entry("bid_support".into()).or_insert(0.5);
    summary.entry("ask_pressure".into()).or_insert(0.5);
    summary.entry("window_count".into()).or_insert(1.0);
    summary
}

fn build_imputed_results(
    missing_symbols: &[String],
    trade_date: &str,
    samples: &[DailySample],
    cfg: &ConfigMap,
    ld: &ConfigMap,
    pid_decomposer: &PIDDecomposer,
) -> (Vec<PatternResult>, Vec<PredictResult>) {
    if missing_symbols.is_empty() || samples.is_empty() {
        return (Vec::new(), Vec::new());
    }

    let market_average_summary = build_market_average_summary(samples);
    let mut pattern_results = Vec::new();
    let mut predict_results = Vec::new();

    for symbol in missing_symbols {
        let default_sample = DailySample {
            stock_code: symbol.clone(),
            transaction_date: trade_date.to_string(),
            rows: Vec::new(),
            feature_summary: market_average_summary.clone(),
            quality_flags: HashMap::from([
                ("has_reference_features".into(), false),
                ("window_count_ok".into(), false),
                ("imputed_from_market_average".into(), true),
            ]),
        };
        let pid_result = pid_decomposer.decompose_sample(&default_sample);
        let mut pattern_result = predict_pattern(&default_sample, cfg, ld, Some(&pid_result));
        pattern_result.pattern_explanation =
            format!("{} 缺失原始数据，按当日市场中位水平补全判断。", pattern_result.pattern_explanation);
        pattern_result.prototype_id = format!("imputed::{}", pattern_result.prototype_id);

        let mut predict_batch = predict_capitals(&default_sample, cfg, ld, &pid_result);
        for predict_result in &mut predict_batch {
            predict_result
                .debug_info
                .insert("imputed_from_market_average".into(), serde_json::Value::Bool(true));
            predict_result.debug_info.insert(
                "imputed_reason".into(),
                serde_json::Value::String("missing_raw_data".into()),
            );
        }

        pattern_results.push(pattern_result);
        predict_results.extend(predict_batch);
    }

    (pattern_results, predict_results)
}

pub fn run_daily_batch(td: &str, inp: &Path, out: &Path, cfg: &ConfigMap, ld: &ConfigMap,
    sl: Option<usize>, so: usize, slf: Option<&Path>, zip: bool, prof: bool)
    -> Result<HashMap<String,serde_json::Value>>
{
    let t0=Instant::now(); fs::create_dir_all(out)?;
    progress(0.0, "starting batch analysis");
    let (req,su)=load_universe(slf)?;
    let mut w: Vec<String>=Vec::new(); let mut ms=0.0f64;
    let t1=Instant::now();
    let (mut smp,inc,stm)=load_samples(inp,td,sl,so,&su,cfg);
    let sbs=t1.elapsed().as_secs_f64();
    progress(45.0, &format!("loaded samples {}", smp.len()));
    if smp.is_empty(){w.push("No samples.".into());}
    let pid_decomposer = PIDDecomposer::new(cfg);
    let t1=Instant::now();
    let total_samples=smp.len();
    let mut pid_results: HashMap<String, _> = HashMap::new();
    for (idx, sample) in smp.iter().enumerate() {
        pid_results.insert(sample.stock_code.clone(), pid_decomposer.decompose_sample(sample));
        progress(stage_percent(45.0,65.0,idx+1,total_samples), &format!("PID {}/{} {}", idx+1, total_samples, sample.stock_code));
    }
    let pid_secs=t1.elapsed().as_secs_f64();
    let t1=Instant::now();
    let mut pr: Vec<PatternResult>=Vec::new();
    for (idx, sample) in smp.iter().enumerate() {
        pr.push(predict_pattern(sample,cfg,ld,pid_results.get(&sample.stock_code)));
        progress(stage_percent(65.0,75.0,idx+1,total_samples), &format!("pattern {}/{} {}", idx+1, total_samples, sample.stock_code));
    }
    let ps=t1.elapsed().as_secs_f64();
    let t1=Instant::now();
    let mut pd: Vec<PredictResult>=Vec::new();
    for (idx, sample) in smp.iter().enumerate() {
        if let Some(pid_result) = pid_results.get(&sample.stock_code) {
            pd.extend(predict_capitals(sample,cfg,ld,pid_result));
        }
        progress(stage_percent(75.0,88.0,idx+1,total_samples), &format!("capital {}/{} {}", idx+1, total_samples, sample.stock_code));
    }
    let cps=pid_secs + t1.elapsed().as_secs_f64();
    let mut msn: Option<MarketPidSnapshot>=None;
    if !smp.is_empty()&&get_bool(cfg,"enable_market_snapshot",true) {
        progress(89.0, "estimating market snapshot");
        let t1=Instant::now();
        msn=Some(estimate_market_pid(&mut smp,&pid_results,&pr,&pd,cfg));
        if let Some(ref sn)=msn{attach_market_relative_metrics(&smp,&mut pd,sn);}
        ms=t1.elapsed().as_secs_f64();
    }
    progress(92.0, "building warnings and imputed outputs");
    let mut missing_symbols: Vec<String> = Vec::new();
    if let Some(ref rq)=req {
        let act: std::collections::HashSet<String>=smp.iter().map(|s|s.stock_code.to_uppercase()).collect();
        missing_symbols = rq.iter().filter(|s|!act.contains(&s.to_uppercase())).cloned().collect();
        if !missing_symbols.is_empty(){w.push(format!("Missing raw data for requested symbols: {}",missing_symbols.join(", ")));}
    }
    if !inc.is_empty(){
        let mut d: Vec<String>=inc.iter().map(|(s,f)|format!("{}({})",s,f.join(","))).collect();
        d.sort(); w.push(format!("Skipped: {}",d.join("; ")));
    }
    let (mut imputed_patterns, mut imputed_predicts) = build_imputed_results(&missing_symbols, td, &smp, cfg, ld, &pid_decomposer);
    if !imputed_patterns.is_empty() {
        w.push(format!("Imputed missing symbols with market-average defaults: {}", missing_symbols.join(", ")));
        pr.append(&mut imputed_patterns);
        pd.append(&mut imputed_predicts);
    }
    progress(94.0, "exporting result files");
    sort_ord(&mut pr,&req,|r|r.stock_code.clone());
    sort_ord(&mut pd,&req,|r|r.stock_code.clone());
    let t1=Instant::now();
    exporter::export_event_classified_rows(&smp, &out.join("event_classified_rows.csv"))?;
    exporter::export_window_feature_rows(&smp, &out.join("window_feature_rows.csv"))?;
    exporter::export_window_flow_rows(&smp, &out.join("pid_window_flow_rows.csv"))?;
    let mut pid_tail_rows: Vec<&crate::schemas::DecompositionResult> = pid_results.values().collect();
    pid_tail_rows.sort_by(|a,b| a.stock_code.cmp(&b.stock_code));
    exporter::export_pid_window_params(&pid_tail_rows, &out.join("pid_window_params.csv"))?;
    exporter::export_pid_window_contrib(&pid_tail_rows, &out.join("pid_window_contrib.csv"))?;
    let pid_window_diag_path = out.join("pid_window_diag.csv");
    let pid_daily_diag_path = out.join("pid_daily_diag.csv");
    let cfg_json = serde_json::to_value(cfg).unwrap_or(serde_json::Value::Null);
    exporter::export_pid_window_diag(&pid_tail_rows, &pid_window_diag_path, &cfg_json)?;
    exporter::export_pid_daily_diag(&pid_tail_rows, &pid_daily_diag_path, &cfg_json)?;
    exporter::export_pid_tail_diagnostics(&pid_tail_rows, &out.join("pid_tail_diagnostics.csv"))?;
    let mut msp: Option<String>=None; let mut mrp: Option<String>=None;
    if let Some(ref sn)=msn {
        let sp=out.join("market_pid_snapshot.csv"); let rp=out.join("market_regime_report.md");
        exporter::export_market_pid_snapshot(sn,&sp)?; exporter::export_market_regime_report(sn,&rp)?;
        msp=Some(sp.to_string_lossy().to_string()); mrp=Some(rp.to_string_lossy().to_string());
    }
    exporter::export_pattern_reco(&pr,&out.join("pattern_reco.csv"))?;
    exporter::export_predict_result(&pd,&out.join("predict_result.csv"))?;
    let (dj,dc)=exporter::export_batch_diagnostics(msn.as_ref(),&pr,&pd,out)?;
    let mut es=t1.elapsed().as_secs_f64();
    let mut sz: Option<String>=None;
    if zip {
        progress(98.0, "building submit.zip");
        let t1=Instant::now();
        match exporter::build_submit_zip(out){Ok(p)=>sz=Some(p),Err(e)=>w.push(format!("zip: {}",e))}
        es+=t1.elapsed().as_secs_f64();
    }
    let mut psm: Option<serde_json::Value>=None;
    if prof {
        let ts=t0.elapsed().as_secs_f64();
        let top: Vec<serde_json::Value>=stm.iter().rev().take(20).map(|t|{
            let mut m=serde_json::Map::new();
            m.insert("sample_build_seconds".into(),serde_json::json!(rsec(*t.get("sample_build_seconds").unwrap_or(&0.0))));
            serde_json::Value::Object(m)
        }).collect();
        let mut p=serde_json::Map::new();
        p.insert("total_seconds".into(),serde_json::json!(rsec(ts)));
        p.insert("sample_build_seconds".into(),serde_json::json!(rsec(sbs)));
        p.insert("pattern_seconds".into(),serde_json::json!(rsec(ps)));
        p.insert("capital_seconds".into(),serde_json::json!(rsec(cps)));
        p.insert("market_seconds".into(),serde_json::json!(rsec(ms)));
        p.insert("export_seconds".into(),serde_json::json!(rsec(es)));
        p.insert("processed_samples".into(),serde_json::json!(smp.len()));
        p.insert("skipped".into(),serde_json::json!(inc.len()));
        p.insert("top_slowest".into(),serde_json::Value::Array(top));
        psm=Some(serde_json::Value::Object(p));
    }
    let mut r=HashMap::new();
    r.insert("trade_date".into(),serde_json::Value::String(td.into()));
    r.insert("sample_count".into(),serde_json::json!(smp.len()));
    r.insert("output_count".into(),serde_json::json!(pr.len()));
    r.insert("imputed_output_count".into(), serde_json::json!(missing_symbols.len()));
    r.insert("stock_offset".into(), serde_json::json!(so));
    r.insert("stock_limit".into(), sl.map(serde_json::Value::from).unwrap_or(serde_json::Value::Null));
    r.insert("stock_universe_size".into(), su.as_ref().map(|s| serde_json::json!(s.len())).unwrap_or(serde_json::Value::Null));
    r.insert(
        "stock_list_file".into(),
        slf.map(|path| serde_json::Value::String(path.to_string_lossy().to_string()))
            .unwrap_or(serde_json::Value::Null),
    );
    r.insert("warnings".into(),serde_json::Value::Array(w.iter().map(|w|serde_json::Value::String(w.clone())).collect()));
    if let Some(z)=sz{r.insert("submit_zip".into(),serde_json::Value::String(z));}
    if let Some(p)=msp{r.insert("market_snapshot_path".into(),serde_json::Value::String(p));}
    if let Some(p)=mrp{r.insert("market_report_path".into(),serde_json::Value::String(p));}
    r.insert("diagnostics_json_path".into(),serde_json::Value::String(dj));
    r.insert("distribution_csv_path".into(),serde_json::Value::String(dc));
    r.insert("pid_window_diag_path".into(),serde_json::Value::String(pid_window_diag_path.to_string_lossy().to_string()));
    r.insert("pid_daily_diag_path".into(),serde_json::Value::String(pid_daily_diag_path.to_string_lossy().to_string()));
    let market_validation_report_path = exporter::export_market_pid_validation_report(msn.as_ref(), out)?;
    r.insert("market_validation_report_path".into(), serde_json::Value::String(market_validation_report_path));
    let replay_payload = serde_json::to_value(&r).unwrap_or(serde_json::Value::Null);
    let replay_validation_report_path = exporter::export_replay_validation_report(&replay_payload, out)?;
    r.insert("replay_validation_report_path".into(), serde_json::Value::String(replay_validation_report_path));
    if let Some(p)=psm{r.insert("performance_summary".into(),p);}
    progress(100.0, "batch analysis finished");
    Ok(r)
}

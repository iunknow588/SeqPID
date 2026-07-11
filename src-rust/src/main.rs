mod capital_model;
mod batch_alerts;
mod batch_reporting;
mod gui;
mod config;
mod exporter;
mod market_pid;
mod order_lifecycle;
mod pattern_model;
mod pid_decomposer;
mod scheduler;
mod schema_probe;
mod schemas;
mod state_feature_builder;

use anyhow::Result;
use chrono::Local;
use clap::Parser;
use std::path::{Path, PathBuf};

const EXTERNAL_ROOT: &str = r"C:\level-2-ana";

fn default_input_dir() -> PathBuf {
    PathBuf::from(EXTERNAL_ROOT).join("data")
}

fn default_output_dir() -> PathBuf {
    PathBuf::from(EXTERNAL_ROOT).join("output")
}

fn default_report_dir() -> PathBuf {
    default_output_dir().join("reports").join("diagnostics")
}

#[derive(Parser, Debug)]
#[command(name = "competition_system", about = "Competition system entrypoint (Rust)")]
struct Args {
    /// Run mode
    #[arg(long, default_value = "probe")]
    mode: String,

    /// Trade date, e.g. 20260710
    #[arg(long)]
    date: String,

    /// Input data directory
    #[arg(long, default_value_t = default_input_dir().to_string_lossy().to_string())]
    input_dir: String,

    /// Output directory
    #[arg(long, default_value_t = default_output_dir().to_string_lossy().to_string())]
    output_dir: String,

    /// Report directory
    #[arg(long, default_value_t = default_report_dir().to_string_lossy().to_string())]
    report_dir: String,

    /// Runtime config YAML path
    #[arg(long, default_value = "./configs/dev.yaml")]
    config: String,

    /// Label config YAML path
    #[arg(long, default_value = "./configs/label_dict.yaml")]
    label_config: String,

    /// Limit stock dirs for raw per-stock layout
    #[arg(long, default_value_t = 0)]
    stock_limit: usize,

    /// Skip N stock dirs before processing
    #[arg(long, default_value_t = 0)]
    stock_offset: usize,

    /// CSV file containing stock codes to process
    #[arg(long, default_value = "")]
    stock_list_file: String,

    /// Build submit.zip
    #[arg(long)]
    build_zip: bool,

    /// Write performance profile report for batch mode
    #[arg(long)]
    profile: bool,
}

pub fn resolve_path(path_str: &str) -> PathBuf {
    let path = Path::new(path_str);
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(path)
    }
}

pub fn looks_like_supported_input_dir(path: &Path) -> bool {
    if !path.exists() || !path.is_dir() {
        return false;
    }

    for name in &["reference_features.csv", "features.csv"] {
        if path.join(name).exists() {
            return true;
        }
    }

    let csv_files: Vec<_> = std::fs::read_dir(path)
        .ok()
        .map(|entries| {
            entries
                .filter_map(|e| e.ok())
                .filter(|e| {
                    e.path()
                        .extension()
                        .map(|ext| ext == "csv")
                        .unwrap_or(false)
                })
                .collect()
        })
        .unwrap_or_default();
    if csv_files.len() >= 3 {
        return true;
    }

    // Check subdirectories
    if let Ok(entries) = std::fs::read_dir(path) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.is_dir() {
                let sub_csvs: Vec<_> = std::fs::read_dir(&p)
                    .ok()
                    .map(|e| {
                        e.filter_map(|e| e.ok())
                            .filter(|e| {
                                e.path()
                                    .extension()
                                    .map(|ext| ext == "csv")
                                    .unwrap_or(false)
                            })
                            .collect()
                    })
                    .unwrap_or_default();
                if sub_csvs.len() >= 3 {
                    return true;
                }
            }
        }
    }
    false
}

pub fn resolve_input_dir(path_str: &str, trade_date: &str) -> PathBuf {
    let base = resolve_path(path_str);
    if looks_like_supported_input_dir(&base) {
        return base;
    }

    let candidates = [
        base.join(trade_date).join(trade_date),
        base.join(trade_date),
    ];
    for candidate in &candidates {
        if looks_like_supported_input_dir(candidate) {
            return candidate.clone();
        }
    }
    base
}

fn resolve_stock_list_file(stock_list_file: Option<PathBuf>, resolved_input_dir: &Path) -> Option<PathBuf> {
    if let Some(path) = stock_list_file {
        return Some(path);
    }
    let candidates = [
        resolved_input_dir.join("百只股票样本.csv"),
        resolved_input_dir.parent().map(|p| p.join("百只股票样本.csv")).unwrap_or_default(),
        PathBuf::from(EXTERNAL_ROOT).join("data").join("百只股票样本.csv"),
    ];
    candidates
        .into_iter()
        .find(|candidate| candidate.exists() && candidate.is_file())
}

#[allow(dead_code)]
fn infer_trade_date_from_path(path_str: &str) -> Result<String> {
    let path = Path::new(path_str);
    for part in path.components().rev() {
        let s = part.as_os_str().to_string_lossy();
        if s.len() == 8 && s.chars().all(|c| c.is_ascii_digit()) {
            return Ok(s.to_string());
        }
    }
    anyhow::bail!("Unable to infer trade date from path: {}", path_str)
}

pub fn build_timestamped_output_dir(base_dir: &Path, trade_date: &str) -> Result<PathBuf> {
    std::fs::create_dir_all(base_dir)?;
    let timestamp = Local::now().format("%Y%m%d_%H%M%S").to_string();
    let mut candidate = base_dir.join(format!("{}_{}", trade_date, timestamp));
    let mut suffix = 1u32;
    while candidate.exists() {
        candidate = base_dir.join(format!("{}_{}_{}", trade_date, timestamp, suffix));
        suffix += 1;
    }
    std::fs::create_dir_all(&candidate)?;
    Ok(candidate)
}

fn run_probe(args: &Args) -> Result<()> {
    let resolved_input_dir = resolve_input_dir(&args.input_dir, &args.date);
    let result = schema_probe::probe_input_schema(&resolved_input_dir, &args.date)?;
    let report = schema_probe::render_schema_probe_report(&result);
    let report_dir = resolve_path(&args.report_dir);
    std::fs::create_dir_all(&report_dir)?;
    let report_path = report_dir.join("schema_probe_report.md");
    std::fs::write(&report_path, &report)?;
    println!("Schema probe report written to: {}", report_path.display());
    Ok(())
}

fn run_batch(args: &Args) -> Result<()> {
    let config_path = resolve_path(&args.config);
    let label_path = resolve_path(&args.label_config);
    let cfg = config::load_runtime_config(&config_path)?;
    let label_dict = config::load_label_dict(&label_path)?;

    let resolved_input_dir = resolve_input_dir(&args.input_dir, &args.date);
    let output_base = resolve_path(&args.output_dir);
    let resolved_output_dir = build_timestamped_output_dir(&output_base, &args.date)?;

    let stock_limit = if args.stock_limit > 0 {
        Some(args.stock_limit)
    } else {
        None
    };
    let stock_list_file = if args.stock_list_file.is_empty() {
        None
    } else {
        Some(resolve_path(&args.stock_list_file))
    };
    let stock_list_file = resolve_stock_list_file(stock_list_file, &resolved_input_dir);
    let enable_zip = config::get_bool(&cfg, "enable_submit_zip", false) || args.build_zip;

    let result = scheduler::run_daily_batch(
        &args.date,
        &resolved_input_dir,
        &resolved_output_dir,
        &cfg,
        &label_dict,
        stock_limit,
        args.stock_offset,
        stock_list_file.as_deref(),
        enable_zip,
        args.profile,
    )?;

    println!("Batch finished for {}", args.date);
    println!("Input directory: {}", resolved_input_dir.display());
    println!("Output directory: {}", resolved_output_dir.display());
    if let Some(v) = result.get("sample_count") {
        println!("Samples: {}", v);
    }
    if args.stock_offset > 0 || args.stock_limit > 0 {
        println!("Slice: offset={}, limit={}", args.stock_offset, args.stock_limit);
    }
    if let Some(path) = stock_list_file.as_ref() {
        if let Some(v) = result.get("stock_universe_size") {
            println!("Stock list: {} ({} symbols)", path.display(), v);
        }
    }
    if let Some(v) = result.get("warnings") {
        if let Some(arr) = v.as_array() {
            if !arr.is_empty() {
                println!("Warnings: {}", v);
            }
        }
    }
    if let Some(v) = result.get("market_snapshot_path") {
        println!("market_pid_snapshot: {}", v.as_str().unwrap_or(""));
    }
    if let Some(v) = result.get("market_report_path") {
        println!("market_regime_report: {}", v.as_str().unwrap_or(""));
    }
    if let Some(v) = result.get("diagnostics_json_path") {
        println!("batch_diagnostics: {}", v.as_str().unwrap_or(""));
    }
    if let Some(v) = result.get("distribution_csv_path") {
        println!("label_distribution: {}", v.as_str().unwrap_or(""));
    }
    if let Some(v) = result.get("submit_zip") {
        println!("submit.zip: {}", v.as_str().unwrap_or(""));
    }
    if let Some(perf) = result.get("performance_summary") {
        let report_path = resolved_output_dir.join("performance_profile.json");
        std::fs::write(&report_path, serde_json::to_string_pretty(perf)?)?;
        println!("performance_profile: {}", report_path.display());
        if let Some(total) = perf.get("total_seconds") {
            println!("performance_total_seconds: {}", total);
        }
        if let Some(sb) = perf.get("sample_build_seconds") {
            println!("performance_sample_build_seconds: {}", sb);
        }
    }
    Ok(())
}

fn main() -> Result<()> {
    let args = Args::parse();
    match args.mode.as_str() {
        "probe" => run_probe(&args),
        "batch" => run_batch(&args),
        "gui" => gui::run_gui().map_err(|e| anyhow::anyhow!("{}", e)),
        other => anyhow::bail!("Unknown mode: {}", other),
    }
}

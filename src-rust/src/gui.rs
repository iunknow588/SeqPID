use eframe::egui;
use std::sync::mpsc;
use std::thread;

const DEFAULT_INPUT: &str = r"C:\level-2-ana\data";
const DEFAULT_OUTPUT: &str = r"C:\level-2-ana\output";

#[derive(Debug, Clone)]
enum LogEvent {
    Line(String),
    Done(String),
    Error(String),
}

pub struct App {
    input_dir: String,
    output_dir: String,
    config_path: String,
    label_config: String,
    stock_list_file: String,
    trade_date: String,
    stock_limit: String,
    stock_offset: String,
    build_zip: bool,
    profile_enabled: bool,
    log_lines: Vec<String>,
    status: String,
    running: bool,
    detected_date: String,
    rx: Option<mpsc::Receiver<LogEvent>>,
}

impl Default for App {
    fn default() -> Self {
        Self {
            input_dir: DEFAULT_INPUT.to_string(),
            output_dir: DEFAULT_OUTPUT.to_string(),
            config_path: "./configs/dev.yaml".to_string(),
            label_config: "./configs/label_dict.yaml".to_string(),
            stock_list_file: String::new(),
            trade_date: String::new(),
            stock_limit: String::new(),
            stock_offset: String::new(),
            build_zip: true,
            profile_enabled: true,
            log_lines: Vec::new(),
            status: "请配置参数后开始分析".to_string(),
            running: false,
            detected_date: String::new(),
            rx: None,
        }
    }
}

impl App {
    fn detect_date(&mut self) {
        let path = std::path::Path::new(&self.input_dir);
        self.detected_date.clear();
        for part in path.components().rev() {
            let s = part.as_os_str().to_string_lossy();
            if s.len() == 8 && s.chars().all(|c| c.is_ascii_digit()) {
                self.detected_date = s.to_string();
                if self.trade_date.is_empty() {
                    self.trade_date = s.to_string();
                }
                return;
            }
        }
    }

    fn start_analysis(&mut self) {
        if self.running {
            return;
        }
        let input_dir = self.input_dir.clone();
        let output_dir = self.output_dir.clone();
        let config_path = self.config_path.clone();
        let label_config = self.label_config.clone();
        let stock_list_file = self.stock_list_file.clone();
        let trade_date = self.trade_date.clone();
        let stock_limit: usize = self.stock_limit.parse().unwrap_or(0);
        let stock_offset: usize = self.stock_offset.parse().unwrap_or(0);
        let build_zip = self.build_zip;
        let profile = self.profile_enabled;

        let (tx, rx) = mpsc::channel();
        self.rx = Some(rx);
        self.running = true;
        self.log_lines.clear();
        self.status = "分析中，请稍候...".to_string();

        thread::spawn(move || {
            let logger = |msg: String| {
                let _ = tx.send(LogEvent::Line(msg));
            };
            let result = run_analysis(
                &input_dir,
                &output_dir,
                &config_path,
                &label_config,
                &stock_list_file,
                &trade_date,
                stock_limit,
                stock_offset,
                build_zip,
                profile,
                logger,
            );
            match result {
                Ok(out_dir) => {
                    let _ = tx.send(LogEvent::Done(out_dir));
                }
                Err(err) => {
                    let _ = tx.send(LogEvent::Error(err.to_string()));
                }
            }
        });
    }

    fn poll_logs(&mut self) {
        let mut clear_rx = false;
        if let Some(ref rx) = self.rx {
            while let Ok(event) = rx.try_recv() {
                match event {
                    LogEvent::Line(msg) => self.log_lines.push(msg),
                    LogEvent::Done(out_dir) => {
                        self.log_lines.push(format!("分析完成，输出目录: {}", out_dir));
                        self.status = "分析完成".to_string();
                        self.running = false;
                        clear_rx = true;
                    }
                    LogEvent::Error(err) => {
                        self.log_lines.push(format!("分析失败: {}", err));
                        self.status = "分析失败".to_string();
                        self.running = false;
                        clear_rx = true;
                    }
                }
            }
        }
        if clear_rx {
            self.rx = None;
        }
    }
}

fn run_analysis(
    input_dir: &str,
    output_dir: &str,
    config_path: &str,
    label_config: &str,
    stock_list_file: &str,
    trade_date: &str,
    stock_limit: usize,
    stock_offset: usize,
    build_zip: bool,
    profile: bool,
    log: impl Fn(String),
) -> anyhow::Result<String> {
    log(format!("开始分析: {}", input_dir));
    log(format!("交易日: {}", trade_date));

    let cfg_path = crate::resolve_path(config_path);
    let lbl_path = crate::resolve_path(label_config);
    let cfg = crate::config::load_runtime_config(&cfg_path)?;
    let label_dict = crate::config::load_label_dict(&lbl_path)?;

    let resolved_input = crate::resolve_input_dir(input_dir, trade_date);
    let output_base = crate::resolve_path(output_dir);
    let resolved_output = crate::build_timestamped_output_dir(&output_base, trade_date)?;

    log(format!("解析输入目录: {}", resolved_input.display()));
    log(format!("输出目录: {}", resolved_output.display()));

    let stock_limit = if stock_limit > 0 { Some(stock_limit) } else { None };
    let stock_list_file = if stock_list_file.is_empty() {
        None
    } else {
        Some(crate::resolve_path(stock_list_file))
    };
    let enable_zip = crate::config::get_bool(&cfg, "enable_submit_zip", false) || build_zip;

    let result = crate::scheduler::run_daily_batch(
        trade_date,
        &resolved_input,
        &resolved_output,
        &cfg,
        &label_dict,
        stock_limit,
        stock_offset,
        stock_list_file.as_deref(),
        enable_zip,
        profile,
    )?;

    if let Some(v) = result.get("sample_count") {
        log(format!("样本数: {}", v));
    }
    if let Some(v) = result.get("market_snapshot_path") {
        log(format!("market_pid_snapshot: {}", v.as_str().unwrap_or("")));
    }
    if let Some(v) = result.get("market_report_path") {
        log(format!("market_regime_report: {}", v.as_str().unwrap_or("")));
    }
    if let Some(v) = result.get("diagnostics_json_path") {
        log(format!("batch_diagnostics: {}", v.as_str().unwrap_or("")));
    }
    if let Some(v) = result.get("distribution_csv_path") {
        log(format!("label_distribution: {}", v.as_str().unwrap_or("")));
    }
    if let Some(v) = result.get("submit_zip") {
        log(format!("submit.zip: {}", v.as_str().unwrap_or("")));
    }
    if let Some(w) = result.get("warnings").and_then(|v| v.as_array()) {
        for item in w {
            if let Some(text) = item.as_str() {
                log(format!("警告: {}", text));
            }
        }
    }
    if let Some(perf) = result.get("performance_summary") {
        let report_path = resolved_output.join("performance_profile.json");
        if let Ok(json) = serde_json::to_string_pretty(perf) {
            let _ = std::fs::write(&report_path, json);
            log(format!("performance_profile: {}", report_path.display()));
        }
    }

    Ok(resolved_output.to_string_lossy().to_string())
}

fn form_row(ui: &mut egui::Ui, label: &str, value: &mut String) {
    ui.horizontal(|ui| {
        ui.add_sized([100.0, 24.0], egui::Label::new(label));
        ui.add_sized([520.0, 24.0], egui::TextEdit::singleline(value));
    });
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.poll_logs();
        if self.running {
            ctx.request_repaint_after(std::time::Duration::from_millis(100));
        }

        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("比赛样本分析系统");
            ui.label(&self.status);
            ui.separator();

            form_row(ui, "样本目录", &mut self.input_dir);
            form_row(ui, "输出目录", &mut self.output_dir);
            form_row(ui, "运行配置", &mut self.config_path);
            form_row(ui, "标签配置", &mut self.label_config);
            form_row(ui, "股票列表", &mut self.stock_list_file);
            form_row(ui, "交易日", &mut self.trade_date);

            ui.horizontal(|ui| {
                ui.label("limit");
                ui.add_sized([80.0, 24.0], egui::TextEdit::singleline(&mut self.stock_limit));
                ui.label("offset");
                ui.add_sized([80.0, 24.0], egui::TextEdit::singleline(&mut self.stock_offset));
                if ui.button("自动识别日期").clicked() {
                    self.detect_date();
                }
                if !self.detected_date.is_empty() {
                    ui.label(format!("识别到 {}", self.detected_date));
                }
            });

            ui.horizontal(|ui| {
                ui.checkbox(&mut self.build_zip, "生成 submit.zip");
                ui.checkbox(&mut self.profile_enabled, "性能报告");
            });

            ui.horizontal(|ui| {
                if ui
                    .add_enabled(!self.running, egui::Button::new("开始分析"))
                    .clicked()
                {
                    self.start_analysis();
                }
                if self.running {
                    ui.spinner();
                }
            });

            ui.separator();
            ui.label("运行日志");
            egui::ScrollArea::vertical()
                .auto_shrink([false, false])
                .stick_to_bottom(true)
                .show(ui, |ui| {
                    for line in &self.log_lines {
                        ui.label(line);
                    }
                });
        });
    }
}

pub fn run_gui() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("比赛样本分析系统")
            .with_inner_size([900.0, 640.0])
            .with_min_inner_size([720.0, 480.0]),
        ..Default::default()
    };
    eframe::run_native(
        "competition_system",
        options,
        Box::new(|_cc| Box::new(App::default())),
    )
}

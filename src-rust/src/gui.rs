use eframe::egui;
use std::path::PathBuf;
use std::sync::mpsc;
use std::thread;

// Design System Colors (matching reference project)
const BG: egui::Color32 = egui::Color32::from_rgb(0xf7, 0xfa, 0xfb);
const PANEL_BG: egui::Color32 = egui::Color32::from_rgb(0xff, 0xff, 0xff);
const BORDER: egui::Color32 = egui::Color32::from_rgb(0xd7, 0xe1, 0xe6);
const BORDER_DARK: egui::Color32 = egui::Color32::from_rgb(0xc9, 0xd5, 0xda);
const BTN_PRIMARY: egui::Color32 = egui::Color32::from_rgb(0x45, 0x60, 0x6b);
const BTN_HOVER: egui::Color32 = egui::Color32::from_rgb(0x3a, 0x5a, 0x66);
const TEXT_DARK: egui::Color32 = egui::Color32::from_rgb(0x17, 0x25, 0x2f);
const TEXT_MUTED: egui::Color32 = egui::Color32::from_rgb(0x62, 0x72, 0x7d);
const TEXT_DISABLED: egui::Color32 = egui::Color32::from_rgb(0x8a, 0x98, 0xa0);
const MENU_HOVER: egui::Color32 = egui::Color32::from_rgb(0xd8, 0xe3, 0xe7);
const LOG_BG: egui::Color32 = egui::Color32::from_rgb(0xf7, 0xfa, 0xfb);
const SUCCESS_BG: egui::Color32 = egui::Color32::from_rgb(0xed, 0xf7, 0xf0);
const SUCCESS_TEXT: egui::Color32 = egui::Color32::from_rgb(0x24, 0x6b, 0x3d);
const WARNING_BG: egui::Color32 = egui::Color32::from_rgb(0xfb, 0xf6, 0xdf);
const WARNING_TEXT: egui::Color32 = egui::Color32::from_rgb(0x7a, 0x5d, 0x00);

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
            status: "\u8bf7\u914d\u7f6e\u53c2\u6570\u540e\u70b9\u51fb\u201c\u5f00\u59cb\u5206\u6790\u201d".to_string(),
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
        if self.running { return; }
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
        self.status = "\u5206\u6790\u4e2d\uff0c\u8bf7\u7a0d\u5019...".to_string();

        thread::spawn(move || {
            let log = move |msg: String| { let _ = tx.send(LogEvent::Line(msg)); };
            let result = run_analysis(
                &input_dir, &output_dir, &config_path, &label_config,
                &stock_list_file, &trade_date, stock_limit, stock_offset,
                build_zip, profile, log,
            );
            match result {
                Ok(out_dir) => { let _ = tx.send(LogEvent::Done(out_dir)); }
                Err(e) => { let _ = tx.send(LogEvent::Error(e.to_string())); }
            }
        });
    }

    fn poll_logs(&mut self) {
        if let Some(ref rx) = self.rx {
            while let Ok(event) = rx.try_recv() {
                match event {
                    LogEvent::Line(msg) => { self.log_lines.push(msg); }
                    LogEvent::Done(out_dir) => {
                        self.log_lines.push(format!("\u5206\u6790\u5b8c\u6210\uff0c\u8f93\u51fa\u76ee\u5f55: {}", out_dir));
                        self.status = "\u5206\u6790\u5b8c\u6210".to_string();
                        self.running = false;
                        self.rx = None;
                    }
                    LogEvent::Error(e) => {
                        self.log_lines.push(format!("\u5206\u6790\u5931\u8d25: {}", e));
                        self.status = "\u5206\u6790\u5931\u8d25".to_string();
                        self.running = false;
                        self.rx = None;
                    }
                }
            }
        }
    }
}

fn run_analysis(
    input_dir: &str, output_dir: &str, config_path: &str, label_config: &str,
    stock_list_file: &str, trade_date: &str, stock_limit: usize, stock_offset: usize,
    build_zip: bool, profile: bool, log: impl Fn(String),
) -> anyhow::Result<String> {
    log(format!("\u5f00\u59cb\u5206\u6790: {}", input_dir));
    log(format!("\u4ea4\u6613\u65e5: {}", trade_date));

    let cfg_path = crate::resolve_path(config_path);
    let lbl_path = crate::resolve_path(label_config);
    let cfg = crate::config::load_runtime_config(&cfg_path)?;
    let label_dict = crate::config::load_label_dict(&lbl_path)?;

    let resolved_input = crate::resolve_input_dir(input_dir, trade_date);
    let output_base = crate::resolve_path(output_dir);
    let resolved_output = crate::build_timestamped_output_dir(&output_base, trade_date)?;

    log(format!("\u89e3\u6790\u8f93\u5165\u76ee\u5f55: {}", resolved_input.display()));
    log(format!("\u8f93\u51fa\u76ee\u5f55: {}", resolved_output.display()));

    let sl = if stock_limit > 0 { Some(stock_limit) } else { None };
    let slf = if stock_list_file.is_empty() { None } else { Some(crate::resolve_path(stock_list_file)) };
    let enable_zip = crate::config::get_bool(&cfg, "enable_submit_zip", false) || build_zip;

    let result = crate::scheduler::run_daily_batch(
        trade_date, &resolved_input, &resolved_output, &cfg, &label_dict,
        sl, stock_offset, slf.as_deref(), enable_zip, profile,
    )?;

    if let Some(v) = result.get("sample_count") { log(format!("\u6837\u672c\u6570: {}", v)); }
    if let Some(w) = result.get("warnings") {
        if let Some(arr) = w.as_array() {
            for item in arr { log(format!("\u8b66\u544a: {}", item.as_str().unwrap_or(""))); }
        }
    }
    if let Some(v) = result.get("market_snapshot_path") { log(format!("market_pid: {}", v.as_str().unwrap_or(""))); }
    if let Some(v) = result.get("market_report_path") { log(format!("regime_report: {}", v.as_str().unwrap_or(""))); }
    if let Some(v) = result.get("diagnostics_json_path") { log(format!("diagnostics: {}", v.as_str().unwrap_or(""))); }
    if let Some(v) = result.get("distribution_csv_path") { log(format!("distribution: {}", v.as_str().unwrap_or(""))); }
    if let Some(v) = result.get("submit_zip") { log(format!("submit.zip: {}", v.as_str().unwrap_or(""))); }
    if let Some(perf) = result.get("performance_summary") {
        let report_path = resolved_output.join("performance_profile.json");
        if let Ok(json) = serde_json::to_string_pretty(perf) {
            let _ = std::fs::write(&report_path, json);
            log(format!("performance: {}", report_path.display()));
        }
        if let Some(total) = perf.get("total_seconds") { log(format!("\u603b\u8017\u65f6: {}s", total)); }
        if let Some(sb) = perf.get("sample_build_seconds") { log(format!("\u6837\u672c\u6784\u5efa: {}s", sb)); }
    }

    Ok(resolved_output.to_string_lossy().to_string())
}

fn section_panel(ui: &mut egui::Ui, add_contents: impl FnOnce(&mut egui::Ui)) {
    egui::Frame::new()
        .fill(PANEL_BG)
        .stroke(egui::Stroke::new(1.0, BORDER))
        .corner_radius(6.0)
        .inner_margin(egui::Margin::symmetric(14.0, 10.0))
        .show(ui, add_contents);
}

fn log_panel(ui: &mut egui::Ui, lines: &[String]) {
    egui::Frame::new()
        .fill(LOG_BG)
        .stroke(egui::Stroke::new(1.0, BORDER_DARK))
        .corner_radius(6.0)
        .inner_margin(egui::Margin::symmetric(12.0, 8.0))
        .show(ui, |ui| {
            egui::ScrollArea::vertical()
                .max_height(160.0)
                .auto_shrink([false; 2])
                .stick_to_bottom(true)
                .show(ui, |ui| {
                    for line in lines {
                        ui.label(
                            egui::RichText::new(line)
                                .size(12.0)
                                .color(TEXT_DARK)
                                .family(egui::FontFamily::Monospace),
                        );
                    }
                });
        });
}

fn form_row(ui: &mut egui::Ui, label: &str, value: &mut String, has_browse: bool) -> bool {
    let mut browse_clicked = false;
    ui.horizontal(|ui| {
        ui.add_sized(
            [120.0, 28.0],
            egui::Label::new(egui::RichText::new(label).size(13.0).color(TEXT_MUTED)),
        );
        ui.add_sized(
            [380.0, 28.0],
            egui::TextEdit::singleline(value)
                .font(egui::TextStyle::Body)
                .text_color(TEXT_DARK),
        );
        if has_browse {
            if ui.add_sized([60.0, 28.0], egui::Button::new(
                egui::RichText::new("\u6d4f\u89c8").size(12.0).color(egui::Color32::WHITE),
            ).fill(BTN_PRIMARY).corner_radius(6.0)).clicked() {
                browse_clicked = true;
            }
        }
    });
    browse_clicked
}

fn primary_button(ui: &mut egui::Ui, text: &str, enabled: bool) -> egui::Response {
    let btn = egui::Button::new(
        egui::RichText::new(text).size(14.0).strong().color(egui::Color32::WHITE),
    )
    .fill(if enabled { BTN_PRIMARY } else { TEXT_DISABLED })
    .hover_fill(BTN_HOVER)
    .corner_radius(6.0)
    .min_size(egui::vec2(140.0, 36.0));
    ui.add_enabled(enabled, btn)
}

fn status_badge(ui: &mut egui::Ui, text: &str, tone: &str) {
    let (bg, fg) = match tone {
        "success" => (SUCCESS_BG, SUCCESS_TEXT),
        "warning" => (WARNING_BG, WARNING_TEXT),
        _ => (BG, TEXT_MUTED),
    };
    egui::Frame::new()
        .fill(bg)
        .corner_radius(4.0)
        .inner_margin(egui::Margin::symmetric(8.0, 3.0))
        .show(ui, |ui| {
            ui.label(egui::RichText::new(text).size(12.0).strong().color(fg));
        });
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.poll_logs();
        if self.running {
            ctx.request_repaint_after(std::time::Duration::from_millis(100));
        }

        egui::CentralPanel::default()
            .frame(egui::Frame::new().fill(BG).inner_margin(egui::Margin::same(16.0)))
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("\u6bd4\u8d5b\u6837\u672c\u5206\u6790\u7cfb\u7edf")
                            .size(18.0).strong().color(TEXT_DARK),
                    );
                    ui.add_space(12.0);
                    let tone = if self.running { "warning" }
                        else if self.status.contains("\u5b8c\u6210") { "success" }
                        else { "" };
                    status_badge(ui, &self.status, tone);
                });
                ui.add_space(12.0);

                egui::ScrollArea::vertical().show(ui, |ui| {
                    section_panel(ui, |ui| {
                        ui.label(egui::RichText::new("\u914d\u7f6e\u53c2\u6570").size(14.0).strong().color(TEXT_DARK));
                        ui.add_space(6.0);

                        if form_row(ui, "\u6837\u672c\u76ee\u5f55", &mut self.input_dir, true) {
                            if let Some(p) = rfd::FileDialog::new()
                                .set_directory(std::path::Path::new(&self.input_dir))
                                .pick_folder() {
                                self.input_dir = p.to_string_lossy().to_string();
                                self.detect_date();
                            }
                        }
                        if form_row(ui, "\u8f93\u51fa\u76ee\u5f55", &mut self.output_dir, true) {
                            if let Some(p) = rfd::FileDialog::new()
                                .set_directory(std::path::Path::new(&self.output_dir))
                                .pick_folder() {
                                self.output_dir = p.to_string_lossy().to_string();
                            }
                        }
                        if form_row(ui, "\u8fd0\u884c\u914d\u7f6e", &mut self.config_path, true) {
                            if let Some(p) = rfd::FileDialog::new()
                                .add_filter("YAML", &["yaml", "yml"])
                                .pick_file() {
                                self.config_path = p.to_string_lossy().to_string();
                            }
                        }
                        if form_row(ui, "\u6807\u7b7e\u914d\u7f6e", &mut self.label_config, true) {
                            if let Some(p) = rfd::FileDialog::new()
                                .add_filter("YAML", &["yaml", "yml"])
                                .pick_file() {
                                self.label_config = p.to_string_lossy().to_string();
                            }
                        }
                        if form_row(ui, "\u80a1\u7968\u5217\u8868", &mut self.stock_list_file, true) {
                            if let Some(p) = rfd::FileDialog::new()
                                .add_filter("CSV", &["csv"])
                                .pick_file() {
                                self.stock_list_file = p.to_string_lossy().to_string();
                            }
                        }

                        ui.add_space(6.0);
                        ui.horizontal(|ui| {
                            ui.add_sized([120.0, 28.0],
                                egui::Label::new(egui::RichText::new("\u4ea4\u6613\u65e5").size(13.0).color(TEXT_MUTED)));
                            ui.add_sized([120.0, 28.0],
                                egui::TextEdit::singleline(&mut self.trade_date)
                                    .font(egui::TextStyle::Body)
                                    .text_color(TEXT_DARK)
                                    .hint_text(egui::RichText::new("20260130").color(TEXT_DISABLED)));
                            if ui.add_sized([80.0, 28.0], egui::Button::new(
                                egui::RichText::new("\u81ea\u52a8\u8bc6\u522b").size(12.0).color(TEXT_DARK),
                            ).fill(MENU_HOVER).corner_radius(6.0)).clicked() {
                                self.detect_date();
                            }
                            if !self.detected_date.is_empty() {
                                ui.add_space(8.0);
                                ui.label(egui::RichText::new(
                                    format!("\u5df2\u8bc6\u522b: {}", self.detected_date)
                                ).size(12.0).color(TEXT_MUTED));
                            }
                        });

                        ui.add_space(4.0);
                        ui.horizontal(|ui| {
                            ui.add_sized([120.0, 28.0],
                                egui::Label::new(egui::RichText::new("\u9ad8\u7ea7\u9009\u9879").size(13.0).color(TEXT_MUTED)));
                            ui.checkbox(&mut self.build_zip, "\u751f\u6210 submit.zip");
                            ui.add_space(12.0);
                            ui.checkbox(&mut self.profile_enabled, "\u6027\u80fd\u62a5\u544a");
                            ui.add_space(12.0);
                            ui.label(egui::RichText::new("limit:").size(12.0).color(TEXT_MUTED));
                            ui.add_sized([60.0, 24.0],
                                egui::TextEdit::singleline(&mut self.stock_limit)
                                    .font(egui::TextStyle::Body).text_color(TEXT_DARK));
                            ui.add_space(8.0);
                            ui.label(egui::RichText::new("offset:").size(12.0).color(TEXT_MUTED));
                            ui.add_sized([60.0, 24.0],
                                egui::TextEdit::singleline(&mut self.stock_offset)
                                    .font(egui::TextStyle::Body).text_color(TEXT_DARK));
                        });
                    });

                    ui.add_space(10.0);
                    ui.horizontal(|ui| {
                        if primary_button(ui, "\u5f00\u59cb\u5206\u6790", !self.running).clicked() {
                            self.start_analysis();
                        }
                        ui.add_space(12.0);
                        if self.running {
                            ui.spinner();
                            ui.label(egui::RichText::new("\u8fd0\u884c\u4e2d...").size(13.0).color(TEXT_MUTED));
                        }
                    });
                    ui.add_space(10.0);

                    ui.label(egui::RichText::new("\u8fd0\u884c\u65e5\u5fd7").size(14.0).strong().color(TEXT_DARK));
                    ui.add_space(4.0);
                    log_panel(ui, &self.log_lines);
                });
            });
    }
}

pub fn run_gui() -> eframe::Result {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("\u6bd4\u8d5b\u6837\u672c\u5206\u6790\u7cfb\u7edf")
            .with_inner_size([1280.0, 480.0])
            .with_min_inner_size([960.0, 400.0])
            .with_resizable(true),
        ..Default::default()
    };
    eframe::run_native(
        "competition_system",
        options,
        Box::new(|_cc| Ok(Box::new(App::default()))),
    )
}

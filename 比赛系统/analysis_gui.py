from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import main


class AnalysisApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("比赛样本分析")
        self.root.geometry("860x540")

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.input_dir_var = tk.StringVar(value=str(main.DEFAULT_INPUT_DIR))
        self.output_dir_var = tk.StringVar(value=str(main.DEFAULT_OUTPUT_DIR))
        self.stock_list_file_var = tk.StringVar(value=str(main.EXTERNAL_ROOT / "data" / "百只股票样本.csv"))
        self.detected_date_var = tk.StringVar(value="")
        self.profile_enabled_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="请选择样本目录和输出目录，然后点击“开始分析”。")

        self._build_ui()
        self._refresh_detected_date()
        self.root.after(150, self._poll_log_queue)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

        ttk.Label(frame, text="样本目录").grid(row=0, column=0, sticky="w", pady=(0, 10))
        input_entry = ttk.Entry(frame, textvariable=self.input_dir_var)
        input_entry.grid(row=0, column=1, sticky="ew", padx=(12, 8), pady=(0, 10))
        input_entry.bind("<FocusOut>", lambda _event: self._refresh_detected_date())
        ttk.Button(frame, text="浏览", command=self._choose_input_dir).grid(row=0, column=2, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="输出目录").grid(row=1, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(frame, textvariable=self.output_dir_var).grid(row=1, column=1, sticky="ew", padx=(12, 8), pady=(0, 10))
        ttk.Button(frame, text="浏览", command=self._choose_output_dir).grid(row=1, column=2, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="识别日期").grid(row=2, column=0, sticky="w")
        ttk.Label(frame, textvariable=self.detected_date_var).grid(row=2, column=1, sticky="w", padx=(12, 8))
        ttk.Checkbutton(frame, text="生成性能报告", variable=self.profile_enabled_var).grid(row=2, column=2, sticky="e")

        ttk.Label(frame, text="股票清单").grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(frame, textvariable=self.stock_list_file_var).grid(row=3, column=1, sticky="ew", padx=(12, 8), pady=(10, 0))
        ttk.Button(frame, text="浏览", command=self._choose_stock_list_file).grid(row=3, column=2, sticky="ew", pady=(10, 0))

        log_frame = ttk.LabelFrame(frame, text="运行日志", padding=8)
        log_frame.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(16, 12))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", height=18, state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        button_bar = ttk.Frame(frame)
        button_bar.grid(row=5, column=0, columnspan=3, sticky="ew")
        button_bar.columnconfigure(1, weight=1)

        self.run_button = ttk.Button(button_bar, text="开始分析", command=self._start_analysis)
        self.run_button.grid(row=0, column=0, sticky="w")
        ttk.Label(button_bar, textvariable=self.status_var).grid(row=0, column=1, sticky="w", padx=(12, 0))

    def _choose_input_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.input_dir_var.get() or str(main.DEFAULT_INPUT_DIR))
        if chosen:
            self.input_dir_var.set(chosen)
            self._refresh_detected_date()

    def _choose_output_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(main.DEFAULT_OUTPUT_DIR))
        if chosen:
            self.output_dir_var.set(chosen)

    def _choose_stock_list_file(self) -> None:
        initial = self.stock_list_file_var.get().strip()
        initial_dir = str(Path(initial).parent) if initial else str(main.DEFAULT_INPUT_DIR)
        chosen = filedialog.askopenfilename(
            initialdir=initial_dir,
            title="选择股票清单",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if chosen:
            self.stock_list_file_var.set(chosen)

    def _refresh_detected_date(self) -> None:
        try:
            trade_date = main._infer_trade_date_from_path(self.input_dir_var.get())
        except ValueError:
            self.detected_date_var.set("无法自动识别")
        else:
            self.detected_date_var.set(trade_date)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        self.run_button.configure(state="disabled" if running else "normal")

    def _start_analysis(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("提示", "当前已有分析任务在运行。")
            return

        input_dir = self.input_dir_var.get().strip()
        output_dir = self.output_dir_var.get().strip()
        stock_list_file = self.stock_list_file_var.get().strip()
        if not input_dir or not Path(input_dir).exists():
            messagebox.showerror("路径错误", "请选择有效的样本目录。")
            return
        if not output_dir:
            messagebox.showerror("路径错误", "请选择输出目录。")
            return
        if stock_list_file and not Path(stock_list_file).exists():
            messagebox.showerror("路径错误", "请选择有效的股票清单，或清空该项。")
            return

        try:
            trade_date = main._infer_trade_date_from_path(input_dir)
        except ValueError as exc:
            messagebox.showerror("日期识别失败", str(exc))
            return

        self._append_log(f"开始分析: {input_dir}")
        self._append_log(f"自动识别交易日: {trade_date}")
        self._append_log(f"股票清单: {stock_list_file or '未指定'}")
        self.status_var.set("分析中，请稍候...")
        self._set_running(True)

        self.worker = threading.Thread(
            target=self._run_analysis_worker,
            args=(input_dir, output_dir, stock_list_file, self.profile_enabled_var.get()),
            daemon=True,
        )
        self.worker.start()

    def _run_analysis_worker(self, input_dir: str, output_dir: str, stock_list_file: str, profile_enabled: bool) -> None:
        def log(message: str) -> None:
            self.log_queue.put(("log", message))

        try:
            result = main.run_full_analysis(
                input_dir=input_dir,
                output_dir=output_dir,
                stock_list_file=stock_list_file or None,
                profile_enabled=profile_enabled,
                logger=log,
            )
        except Exception as exc:  # pragma: no cover - UI error path
            self.log_queue.put(("error", str(exc)))
            return
        self.log_queue.put(("done", result["output_dir"]))

    def _poll_log_queue(self) -> None:
        try:
            while True:
                event_type, payload = self.log_queue.get_nowait()
                if event_type == "log":
                    self._append_log(payload)
                elif event_type == "error":
                    self._append_log(f"分析失败: {payload}")
                    self.status_var.set("分析失败")
                    self._set_running(False)
                    messagebox.showerror("分析失败", payload)
                elif event_type == "done":
                    self._append_log(f"分析完成，输出目录: {payload}")
                    self.status_var.set("分析完成")
                    self._set_running(False)
                    messagebox.showinfo("分析完成", f"输出目录: {payload}")
        except queue.Empty:
            pass
        finally:
            self.root.after(150, self._poll_log_queue)


def mainloop() -> None:
    root = tk.Tk()
    AnalysisApp(root)
    root.mainloop()


if __name__ == "__main__":
    mainloop()

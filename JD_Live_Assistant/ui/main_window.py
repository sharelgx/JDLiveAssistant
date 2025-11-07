"""Tkinter 主界面实现。"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict

from loguru import logger

from JD_Live_Assistant.core.automation import BrowserController
from JD_Live_Assistant.core.config import ConfigManager
from JD_Live_Assistant.core.hotkeys import HotkeyManager
from JD_Live_Assistant.core.schedule import ScheduleManager


class MainWindow(tk.Tk):
    """应用主窗口。"""

    def __init__(
        self,
        controller: BrowserController,
        scheduler: ScheduleManager,
        hotkeys: HotkeyManager,
        config_manager: ConfigManager,
    ) -> None:
        super().__init__()
        self.title("京东直播自动化助手")
        self.geometry("820x560")
        self.minsize(780, 520)

        self.controller = controller
        self.scheduler = scheduler
        self.hotkeys = hotkeys
        self.config_manager = config_manager
        self.config = self.config_manager.data

        self.log_queue: "queue.Queue[str]" = queue.Queue()

        self._setup_variables()
        self._build_ui()
        self._load_config()
        self._bind_hotkeys()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._poll_log_queue)

    # UI 构建 -----------------------------------------------------------------
    def _setup_variables(self) -> None:
        self.port_var = tk.StringVar(value=str(self.config["app"].get("default_port", 9222)))
        self.live_url_var = tk.StringVar(value=self.config["app"].get("live_url", ""))
        self.schedule_time_var = tk.StringVar(value=self.config["schedule"].get("daily_start_time", "09:00"))

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self, padding=16)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 浏览器绑定区
        browser_frame = ttk.LabelFrame(main_frame, text="浏览器绑定", padding=12)
        browser_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(browser_frame, text="调试端口:").grid(row=0, column=0, sticky=tk.W)
        port_entry = ttk.Entry(browser_frame, textvariable=self.port_var, width=10)
        port_entry.grid(row=0, column=1, padx=8)

        connect_btn = ttk.Button(browser_frame, text="绑定浏览器", command=self._on_connect)
        connect_btn.grid(row=0, column=2, padx=(0, 8))

        disconnect_btn = ttk.Button(browser_frame, text="断开绑定", command=self._on_disconnect)
        disconnect_btn.grid(row=0, column=3)

        ttk.Label(browser_frame, text="直播后台 URL:").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        live_entry = ttk.Entry(browser_frame, textvariable=self.live_url_var, width=60)
        live_entry.grid(row=1, column=1, columnspan=3, sticky=tk.EW, pady=(8, 0))

        open_btn = ttk.Button(browser_frame, text="打开直播后台", command=self._open_live_page)
        open_btn.grid(row=1, column=4, padx=(8, 0), pady=(8, 0))

        browser_frame.columnconfigure(1, weight=1)
        browser_frame.columnconfigure(2, weight=0)

        # 定时任务区
        schedule_frame = ttk.LabelFrame(main_frame, text="定时任务", padding=12)
        schedule_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(schedule_frame, text="每日开播时间 (HH:MM):").grid(row=0, column=0, sticky=tk.W)
        time_entry = ttk.Entry(schedule_frame, textvariable=self.schedule_time_var, width=10)
        time_entry.grid(row=0, column=1, padx=8)

        add_job_btn = ttk.Button(schedule_frame, text="设置每日开播", command=self._on_schedule_start)
        add_job_btn.grid(row=0, column=2)

        remove_job_btn = ttk.Button(schedule_frame, text="取消定时", command=self._on_remove_schedule)
        remove_job_btn.grid(row=0, column=3, padx=(8, 0))

        # 热键提示区
        hotkey_frame = ttk.LabelFrame(main_frame, text="快捷键", padding=12)
        hotkey_frame.pack(fill=tk.X, pady=(0, 12))

        self.hotkey_tree = ttk.Treeview(hotkey_frame, columns=("action", "hotkey"), show="headings", height=4)
        self.hotkey_tree.heading("action", text="操作")
        self.hotkey_tree.heading("hotkey", text="热键")
        self.hotkey_tree.column("action", width=180)
        self.hotkey_tree.column("hotkey", width=160)
        self.hotkey_tree.pack(fill=tk.X)

        # 日志输出区
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding=12)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 底部按钮
        footer = ttk.Frame(main_frame)
        footer.pack(fill=tk.X, pady=(12, 0))

        save_btn = ttk.Button(footer, text="保存配置", command=self._on_save_config)
        save_btn.pack(side=tk.RIGHT)

    # 行为逻辑 ----------------------------------------------------------------
    def _load_config(self) -> None:
        self._refresh_hotkey_table()

    def _bind_hotkeys(self) -> None:
        handlers: Dict[str, Callable[[], None]] = {
            "start_live": self._open_live_page,
            "stop_live": self._stop_live_placeholder,
            "refresh": self._refresh_page,
        }
        self.hotkeys.clear()
        self.hotkeys.bind_from_mapping(self.config.get("hotkeys", {}), handlers)
        self.hotkeys.start()

    def _refresh_hotkey_table(self) -> None:
        for item in self.hotkey_tree.get_children():
            self.hotkey_tree.delete(item)
        mapping = self.config.get("hotkeys", {})
        labels = {
            "start_live": "开播",
            "stop_live": "结束直播",
            "refresh": "刷新页面",
        }
        for key, hotkey in mapping.items():
            self.hotkey_tree.insert("", tk.END, values=(labels.get(key, key), hotkey))

    def _on_connect(self) -> None:
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("输入错误", "请输入合法的数字端口号。")
            return

        def worker() -> None:
            try:
                self.controller.connect(port)
                self._log(f"绑定浏览器成功：端口 {port}")
            except Exception as exc:  # noqa: BLE001
                logger.exception("绑定浏览器失败")
                self._log(f"绑定失败：{exc}")
                messagebox.showerror("绑定失败", str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_disconnect(self) -> None:
        self.controller.disconnect()
        self._log("浏览器连接已断开。")

    def _open_live_page(self) -> None:
        url = self.live_url_var.get().strip()
        if not url:
            messagebox.showwarning("缺少地址", "请先填写直播后台地址。")
            return
        try:
            self.controller.navigate(url)
            self._log(f"打开直播后台：{url}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("跳转直播后台失败")
            self._log(f"跳转失败：{exc}")
            messagebox.showerror("跳转失败", str(exc))

    def _refresh_page(self) -> None:
        try:
            self.controller.perform(lambda page: page.reload())
            self._log("刷新直播页面完成。")
        except Exception as exc:  # noqa: BLE001
            logger.exception("刷新页面失败")
            self._log(f"刷新失败：{exc}")

    def _stop_live_placeholder(self) -> None:
        self._log("收到结束直播指令，可在此接入实际逻辑。")

    def _on_schedule_start(self) -> None:
        time_str = self.schedule_time_var.get().strip()
        if not time_str:
            messagebox.showwarning("缺少时间", "请填写每日开播时间，例如 09:00。")
            return

        self.scheduler.add_daily_job("daily_start", time_str, self._open_live_page)
        self.scheduler.start()
        self._log(f"已设定每日 {time_str} 自动打开直播后台。")

    def _on_remove_schedule(self) -> None:
        self.scheduler.remove("daily_start")
        self._log("已取消每日开播定时任务。")

    def _on_save_config(self) -> None:
        self.config["app"]["default_port"] = int(self.port_var.get())
        self.config["app"]["live_url"] = self.live_url_var.get().strip()
        self.config["schedule"]["daily_start_time"] = self.schedule_time_var.get().strip()
        self.config_manager.save(self.config)
        self._log("配置保存成功。")
        messagebox.showinfo("保存成功", "配置已写入 settings.yaml。")

    # 日志与退出 ----------------------------------------------------------------
    def _log(self, message: str) -> None:
        self.log_queue.put(message)

    def _poll_log_queue(self) -> None:
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"{msg}\n")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        self.after(200, self._poll_log_queue)

    def _on_close(self) -> None:
        if messagebox.askokcancel("退出", "确定要退出程序吗？"):
            self.scheduler.shutdown()
            self.hotkeys.clear()
            self.controller.disconnect()
            self.destroy()


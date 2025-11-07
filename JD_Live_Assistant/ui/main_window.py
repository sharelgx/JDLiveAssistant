"""Tkinter 主界面实现。"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict, List

from loguru import logger

from JD_Live_Assistant.core.automation import BrowserController
from JD_Live_Assistant.core.config import ConfigManager
from JD_Live_Assistant.core.hotkeys import HotkeyManager
from JD_Live_Assistant.core.schedule import ScheduleManager
from JD_Live_Assistant.core.license import LicenseError, LicenseManager


class MainWindow(tk.Tk):
    """应用主窗口。"""

    def __init__(
        self,
        controller: BrowserController,
        scheduler: ScheduleManager,
        hotkeys: HotkeyManager,
        config_manager: ConfigManager,
        license_manager: LicenseManager,
    ) -> None:
        super().__init__()
        self.title("京东直播自动化助手")
        self.geometry("820x560")
        self.minsize(780, 520)

        self.controller = controller
        self.scheduler = scheduler
        self.hotkeys = hotkeys
        self.config_manager = config_manager
        self.license_manager = license_manager
        self.config = self.config_manager.data

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.control_widgets: List[tk.Widget] = []

        self._setup_variables()
        self._build_ui()
        self._load_config()
        self._refresh_license_status()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._poll_log_queue)

    # UI 构建 -----------------------------------------------------------------
    def _setup_variables(self) -> None:
        license_info = self.license_manager.info
        self.port_var = tk.StringVar(value=str(self.config["app"].get("default_port", 9222)))
        self.live_url_var = tk.StringVar(value=self.config["app"].get("live_url", ""))
        self.schedule_time_var = tk.StringVar(value=self.config["schedule"].get("daily_start_time", "09:00"))
        self.license_var = tk.StringVar(value=license_info.key if license_info else "")
        self.license_status_var = tk.StringVar(value="未授权，功能已锁定")

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self, padding=16)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 授权区
        license_frame = ttk.LabelFrame(main_frame, text="授权状态", padding=12)
        license_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(license_frame, text="卡密:").grid(row=0, column=0, sticky=tk.W)
        license_entry = ttk.Entry(license_frame, textvariable=self.license_var, width=30, show="*")
        license_entry.grid(row=0, column=1, padx=8, sticky=tk.W)

        verify_btn = ttk.Button(license_frame, text="验证授权", command=self._on_validate_license)
        verify_btn.grid(row=0, column=2, padx=(0, 8))

        self.license_status_label = ttk.Label(license_frame, textvariable=self.license_status_var, foreground="#0F730C")
        self.license_status_label.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(8, 0))

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

        self.control_widgets.extend([port_entry, connect_btn, disconnect_btn, live_entry, open_btn])

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

        self.control_widgets.extend([time_entry, add_job_btn, remove_job_btn])

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

        self.control_widgets.append(save_btn)

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
        if not self._ensure_license():
            return
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
        if not self._ensure_license():
            return
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
        if not self._ensure_license():
            return
        try:
            self.controller.perform(lambda page: page.reload())
            self._log("刷新直播页面完成。")
        except Exception as exc:  # noqa: BLE001
            logger.exception("刷新页面失败")
            self._log(f"刷新失败：{exc}")

    def _stop_live_placeholder(self) -> None:
        self._log("收到结束直播指令，可在此接入实际逻辑。")

    def _on_schedule_start(self) -> None:
        if not self._ensure_license():
            return
        time_str = self.schedule_time_var.get().strip()
        if not time_str:
            messagebox.showwarning("缺少时间", "请填写每日开播时间，例如 09:00。")
            return

        self.scheduler.add_daily_job("daily_start", time_str, self._open_live_page)
        self.scheduler.start()
        self._log(f"已设定每日 {time_str} 自动打开直播后台。")

    def _on_remove_schedule(self) -> None:
        if not self._ensure_license():
            return
        self.scheduler.remove("daily_start")
        self._log("已取消每日开播定时任务。")

    def _on_save_config(self) -> None:
        self.config["app"]["default_port"] = int(self.port_var.get())
        self.config["app"]["live_url"] = self.live_url_var.get().strip()
        self.config["schedule"]["daily_start_time"] = self.schedule_time_var.get().strip()
        self.config_manager.save(self.config)
        self._log("配置保存成功。")
        messagebox.showinfo("保存成功", "配置已写入 settings.yaml。")

    # 授权相关 ----------------------------------------------------------------
    def _on_validate_license(self) -> None:
        key = self.license_var.get().strip()
        try:
            info = self.license_manager.validate_key(key)
        except LicenseError as exc:
            self.license_manager.invalidate()
            self._refresh_license_status()
            messagebox.showerror("验证失败", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("卡密验证出现异常")
            messagebox.showerror("验证异常", str(exc))
            return

        self._log(f"授权成功，卡密 {info.key} 有效期至 {info.expiry_date}")
        messagebox.showinfo("授权成功", f"授权有效期至 {info.expiry_date}")
        self._refresh_license_status()

    def _refresh_license_status(self) -> None:
        if self.license_manager.is_valid and self.license_manager.info:
            remaining = self.license_manager.remaining_days
            expiry = self.license_manager.info.expiry_date
            self.license_status_var.set(f"授权有效，剩余 {remaining} 天（至 {expiry}）")
            self.license_status_label.configure(foreground="#0F730C")
            self._set_controls_enabled(True)
            self._bind_hotkeys()
        else:
            self.license_status_var.set("未授权或已过期，请输入有效卡密后使用。")
            self.license_status_label.configure(foreground="#B3261E")
            self._set_controls_enabled(False)
            self.hotkeys.clear()

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for widget in self.control_widgets:
            try:
                widget.configure(state=state)
            except tk.TclError:
                continue

    def _ensure_license(self) -> bool:
        if self.license_manager.is_valid:
            return True
        messagebox.showwarning("授权提示", "当前卡密未激活或已过期，请先验证授权。")
        self._refresh_license_status()
        return False

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


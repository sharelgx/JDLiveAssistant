"""Tkinter 主界面实现。"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from loguru import logger
from playwright.sync_api import Page

from JD_Live_Assistant.core.automation import BrowserController
from JD_Live_Assistant.core.chrome_launcher import ChromeLauncher
from JD_Live_Assistant.core.config import ConfigManager
from JD_Live_Assistant.core.hotkeys import HotkeyManager
from JD_Live_Assistant.core.license import LicenseError, LicenseManager
from JD_Live_Assistant.core.schedule import ScheduleManager
from JD_Live_Assistant.ui.page_interactor import PageInteractor
from JD_Live_Assistant.ui.page_scripts import PageScripts
from JD_Live_Assistant.ui.product_processor import ProductProcessor


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
        self.title("卡点讲解自动化助手")
        self.geometry("900x620")
        self.minsize(860, 560)

        self.controller = controller
        self.scheduler = scheduler
        self.hotkeys = hotkeys
        self.config_manager = config_manager
        self.license_manager = license_manager
        self.config = self.config_manager.data
        self.browser_config: Dict[str, Any] = self.config.setdefault("browser", {})
        self.material_config: Dict[str, Any] = self.config.setdefault(
            "materials",
            {"directory": ""},
        )
        self.chrome_launcher = ChromeLauncher(
            chrome_path=self.browser_config.get("chrome_path"),
            profile_root=self.browser_config.get("profile_root") or None,
        )

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.control_widgets: List[tk.Widget] = []
        self.task_thread: Optional[threading.Thread] = None
        self.task_stop_event = threading.Event()
        self.is_task_running = False
        self.controls_enabled = True

        self._setup_variables()
        self._ensure_browser_config()
        self._build_ui()
        self._load_config()
        self._refresh_license_status()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._poll_log_queue)

    # UI 构建 -----------------------------------------------------------------
    def _setup_variables(self) -> None:
        license_info = self.license_manager.info
        self.port_var = tk.StringVar(value=str(self.config["app"].get("default_port", 9222)))
        task_config = self.config.setdefault(
            "task",
            {
                "duration_seconds": 8,
                "interval_seconds": 2,
            },
        )
        self.duration_var = tk.StringVar(value=str(task_config.get("duration_seconds", 8)))
        self.interval_var = tk.StringVar(value=str(task_config.get("interval_seconds", 2)))
        self.material_path_var = tk.StringVar(value=self.material_config.get("directory", ""))
        self.license_var = tk.StringVar(value=license_info.key if license_info else "")
        self.license_status_var = tk.StringVar(value="未授权，功能已锁定")
        self.hotkey_summary_var = tk.StringVar(value="")
        self.chrome_path_var = tk.StringVar(value=self._format_chrome_path())

    def _ensure_browser_config(self) -> None:
        """确保浏览器配置持久化。"""

        updated = False
        if self.chrome_launcher.executable and not self.browser_config.get("chrome_path"):
            self.browser_config["chrome_path"] = str(self.chrome_launcher.executable)
            updated = True

        if not self.browser_config.get("profile_root"):
            self.browser_config["profile_root"] = str(self.chrome_launcher.profile_root)
            updated = True

        if not isinstance(self.browser_config.get("port_profiles"), dict):
            self.browser_config["port_profiles"] = {}
            updated = True

        if updated:
            self.config_manager.save(self.config)

        self.chrome_path_var.set(self._format_chrome_path())

    def _format_chrome_path(self) -> str:
        path = self.browser_config.get("chrome_path") or ""
        if not path:
            return "未检测到 Chrome，绑定时将提示"
        return str(path)

    def _ensure_material_directory_selected(self) -> Optional[Path]:
        """确保素材目录可用。"""
        path_str = self.material_path_var.get().strip()
        if not path_str:
            self._log("尚未选择素材目录。")
            messagebox.showwarning("素材目录未设置", "请点击“选择目录”手动指定素材存放位置。")
            return None
        try:
            directory = Path(path_str)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("路径无效", f"无法解析素材目录：{exc}")
            return None
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("创建目录失败", f"无法创建目录：{exc}")
            return None
        return directory

    def _get_material_directory(self) -> Optional[Path]:
        """返回可用的素材目录；若未设置则提示用户选择。"""
        directory = self._ensure_material_directory_selected()
        if directory:
            return directory
        self._on_select_material_directory()
        return self._ensure_material_directory_selected()

    def _on_select_material_directory(self) -> None:
        initial_dir = self.material_path_var.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(
            title="选择素材目录",
            initialdir=initial_dir,
        )
        if not selected:
            return
        directory = Path(selected).resolve()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("创建目录失败", f"无法创建目录：{exc}")
            return
        self.material_path_var.set(str(directory))
        self.material_config["directory"] = str(directory)
        self.config_manager.save(self.config)
        self._log(f"素材目录已更新为：{directory}")

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self, padding=16)
        main_frame.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(main_frame)
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(
            header,
            text="本产品仅供学习使用！",
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(side=tk.LEFT)

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        home_tab = ttk.Frame(notebook, padding=4)
        notebook.add(home_tab, text="主页")

        task_frame = ttk.LabelFrame(home_tab, text="执行任务", padding=12)
        task_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(task_frame, text="端口").grid(row=0, column=0, sticky=tk.E)
        port_entry = ttk.Entry(task_frame, textvariable=self.port_var, width=12)
        port_entry.grid(row=0, column=1, padx=(8, 16), sticky=tk.W)

        ttk.Label(task_frame, text="讲解时间/秒").grid(row=0, column=2, sticky=tk.E)
        duration_entry = ttk.Entry(task_frame, textvariable=self.duration_var, width=12)
        duration_entry.grid(row=0, column=3, padx=(8, 16), sticky=tk.W)

        ttk.Label(task_frame, text="间隔延时/秒").grid(row=0, column=4, sticky=tk.E)
        interval_entry = ttk.Entry(task_frame, textvariable=self.interval_var, width=12)
        interval_entry.grid(row=0, column=5, padx=(8, 16), sticky=tk.W)

        ttk.Label(task_frame, text="素材目录").grid(row=1, column=0, sticky=tk.E, pady=(12, 0))
        material_entry = ttk.Entry(task_frame, textvariable=self.material_path_var, state="readonly")
        material_entry.grid(row=1, column=1, columnspan=5, sticky=tk.EW, padx=(8, 8), pady=(12, 0))
        material_btn = ttk.Button(task_frame, text="选择目录", command=self._on_select_material_directory)
        material_btn.grid(row=1, column=6, sticky=tk.W, pady=(12, 0))

        ttk.Label(task_frame, text="Chrome 路径").grid(row=2, column=0, sticky=tk.E, pady=(12, 0))
        chrome_label = ttk.Label(task_frame, textvariable=self.chrome_path_var, foreground="#555555")
        chrome_label.grid(row=2, column=1, columnspan=6, sticky=tk.W, padx=(8, 0), pady=(12, 0))

        button_column = ttk.Frame(task_frame)
        button_column.grid(row=0, column=7, rowspan=3, sticky="ns", padx=(16, 0))

        connect_btn = ttk.Button(button_column, text="绑定浏览器", command=self._on_connect)
        connect_btn.pack(fill=tk.X)

        disconnect_btn = ttk.Button(button_column, text="断开绑定", command=self._on_disconnect)
        disconnect_btn.pack(fill=tk.X, pady=4)

        self.start_task_btn = ttk.Button(button_column, text="执行任务", command=self._on_start_task)
        self.start_task_btn.pack(fill=tk.X)

        self.stop_task_btn = ttk.Button(button_column, text="结束进程", command=self._on_stop_task)
        self.stop_task_btn.pack(fill=tk.X, pady=4)
        self.stop_task_btn.configure(state=tk.DISABLED)

        exit_btn = ttk.Button(button_column, text="退出", command=self._on_close)
        exit_btn.pack(fill=tk.X)

        for column in range(1, 6):
            task_frame.columnconfigure(column, weight=1)
        task_frame.columnconfigure(6, weight=0)
        task_frame.columnconfigure(7, weight=0)

        license_frame = ttk.LabelFrame(home_tab, text="授权管理", padding=12)
        license_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(license_frame, text="卡密").grid(row=0, column=0, sticky=tk.E)
        license_entry = ttk.Entry(license_frame, textvariable=self.license_var, show="*")
        license_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 8))

        browse_license_btn = ttk.Button(license_frame, text="浏览", command=self._on_browse_license_file)
        browse_license_btn.grid(row=0, column=2, padx=(0, 8))

        verify_btn = ttk.Button(license_frame, text="验证授权", command=self._on_validate_license)
        verify_btn.grid(row=0, column=3)

        license_frame.columnconfigure(1, weight=1)

        self.license_status_label = ttk.Label(
            license_frame,
            textvariable=self.license_status_var,
            foreground="#0F730C",
        )
        self.license_status_label.grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(12, 0))

        hotkey_frame = ttk.LabelFrame(home_tab, text="快捷键提示", padding=12)
        hotkey_frame.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(hotkey_frame, textvariable=self.hotkey_summary_var).pack(anchor=tk.W)

        log_frame = ttk.LabelFrame(home_tab, text="运行日志", padding=12)
        log_frame.pack(fill=tk.BOTH, expand=True)

        log_container = ttk.Frame(log_frame)
        log_container.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_container, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(
            log_container,
            height=12,
            wrap=tk.WORD,
            state=tk.DISABLED,
            yscrollcommand=scrollbar.set,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.configure(command=self.log_text.yview)

        footer = ttk.Frame(home_tab)
        footer.pack(fill=tk.X, pady=(12, 0))
        save_btn = ttk.Button(footer, text="保存配置", command=self._on_save_config)
        save_btn.pack(side=tk.RIGHT)

        self.control_widgets.extend(
            [
                port_entry,
                duration_entry,
                interval_entry,
                material_btn,
                connect_btn,
                disconnect_btn,
                self.start_task_btn,
                save_btn,
            ]
        )

    # 行为逻辑 ----------------------------------------------------------------
    def _load_config(self) -> None:
        self._refresh_hotkey_summary()

    def _bind_hotkeys(self) -> None:
        handlers: Dict[str, Callable[[], None]] = {
            "start_live": self._open_live_page,
            "stop_live": self._stop_live_placeholder,
            "refresh": self._refresh_page,
        }
        self.hotkeys.clear()
        self.hotkeys.bind_from_mapping(self.config.get("hotkeys", {}), handlers)
        self.hotkeys.start()

    def _refresh_hotkey_summary(self) -> None:
        mapping = self.config.get("hotkeys", {})
        labels = {
            "start_live": "开播",
            "stop_live": "结束直播",
            "refresh": "刷新页面",
        }
        if not mapping:
            summary = "暂无快捷键配置。"
        else:
            summary_items = [f"{labels.get(key, key)}: {hotkey}" for key, hotkey in mapping.items()]
            summary = " | ".join(summary_items)
        self.hotkey_summary_var.set(summary)

    def _parse_positive_float(self, var: tk.StringVar, field: str, allow_zero: bool = False) -> Optional[float]:
        try:
            value = float(var.get())
        except ValueError:
            messagebox.showerror("输入错误", f"{field} 请输入数字。")
            return None
        if allow_zero:
            if value < 0:
                messagebox.showerror("输入错误", f"{field} 不能为负数。")
                return None
        else:
            if value <= 0:
                messagebox.showerror("输入错误", f"{field} 必须大于 0。")
                return None
        return value

    def _on_connect(self) -> None:
        """绑定按钮点击事件：连接到用户手动打开的浏览器。"""
        if not self._ensure_license():
            return
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("输入错误", "请输入合法的数字端口号。")
            return

        def worker() -> None:
            try:
                self._log(f"开始绑定浏览器，端口: {port}")
                self._log("提示：请确保已手动打开带参数的Chrome浏览器")
                self._connect_browser(port)
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "绑定成功",
                        f"已成功绑定到端口 {port} 的浏览器。\n请在“素材目录”区域手动选择素材存放路径。",
                    ),
                )
            except RuntimeError as exc:
                logger.exception("绑定浏览器失败")
                self._log(f"绑定失败：{exc}")
                error_msg = f"无法连接到端口 {port} 的浏览器。\n\n请确保：\n1. 已手动打开带参数的Chrome浏览器\n2. Chrome启动命令包含 --remote-debugging-port={port}\n3. 端口号正确"
                self.after(0, lambda e=error_msg: messagebox.showerror("绑定失败", e))
            except Exception as exc:  # noqa: BLE001
                logger.exception("绑定浏览器失败")
                self._log(f"绑定失败：{exc}")
                self.after(0, lambda e=exc: messagebox.showerror("绑定失败", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _connect_browser(self, port: int) -> None:
        """绑定浏览器：连接到已打开的浏览器并获取其属性参数。"""
        self._connect_controller_instance(self.controller, port)

    def _connect_controller_instance(self, controller: BrowserController, port: int) -> None:
        """连接浏览器实例：仅连接已手动打开的浏览器，不自动启动。"""
        # 直接连接，不自动启动浏览器（用户已手动打开带参数的Chrome浏览器）
        controller.connect(port)
        self._log(f"绑定浏览器成功：端口 {port}")

    def _on_disconnect(self) -> None:
        self.controller.disconnect()
        self._log("浏览器连接已断开。")

    def _open_live_page(self) -> None:
        if not self._ensure_license():
            return
        url = self.config["app"].get("live_url", "").strip()
        if not url:
            messagebox.showwarning("缺少地址", "请先在配置文件中填写直播后台地址。")
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

    def _on_start_task(self) -> None:
        if not self._ensure_license():
            return
        if self.task_thread and self.task_thread.is_alive():
            messagebox.showwarning("任务运行中", "当前已有任务在执行，请先结束进程。")
            return

        duration = self._parse_positive_float(self.duration_var, "讲解时间")
        if duration is None:
            return

        interval = self._parse_positive_float(self.interval_var, "间隔延时", allow_zero=True)
        if interval is None:
            return

        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("输入错误", "端口必须为整数。")
            return

        directory = self._get_material_directory()
        if not directory:
            return
        self._log(f"素材目录：{directory}")

        if not self.controller.is_connected:
            proceed = messagebox.askyesno("未绑定浏览器", "当前未绑定浏览器，是否仅记录日志继续执行？")
            if not proceed:
                return

        task_config = self.config.setdefault("task", {})
        task_config["duration_seconds"] = duration
        task_config["interval_seconds"] = interval

        self.task_stop_event.clear()
        self.task_thread = threading.Thread(
            target=self._task_worker,
            args=(directory, duration, interval, port),
            daemon=True,
        )
        self.task_thread.start()
        self._log("自动讲解任务开始执行。")
        self._set_task_running(True)

    def _on_stop_task(self) -> None:
        thread = self.task_thread
        if not thread or not thread.is_alive():
            self._log("当前没有正在运行的任务。")
            return

        self._log("正在停止自动讲解任务...")
        self.task_stop_event.set()
        thread.join(timeout=10)
        if thread.is_alive():
            self._log("任务停止超时，请稍后再试。")
            return

        self.controller.disconnect()
        self._log("任务已停止，并已断开浏览器连接。")

    def _count_products(self, interactor: PageInteractor, item_selector: str) -> Dict[str, int]:
        """
        统计当前页的商品数量。

        Args:
            interactor: 页面交互器
            item_selector: 商品选择器

        Returns:
            包含 total 和 valid 的字典
        """
        count_result = interactor.with_context(
                lambda ctx: ctx.evaluate(
                    """
                (selector) => {
                    const items = Array.from(document.querySelectorAll(selector));
                    const totalCount = items.length;
                    
                    const validItems = items.filter(item => {
                        const style = window.getComputedStyle(item);
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                            return false;
                        }
                        
                        const buttons = Array.from(item.querySelectorAll('button, span, div, a'));
                        const hasExplainButton = buttons.some(btn => {
                            const text = (btn.textContent || '').trim();
                            return text === '讲解' || (text.includes('讲解') && !text.includes('取消') && !text.includes('结束'));
                        });
                        
                        return hasExplainButton;
                    });

                        return {
                        total: totalCount,
                        valid: validItems.length
                    };
                }
                """,
                item_selector
            ),
            require_selector=False
        ) or {"total": 0, "valid": 0}
        
        return {
            "total": count_result.get("total", 0) if isinstance(count_result, dict) else 0,
            "valid": count_result.get("valid", 0) if isinstance(count_result, dict) else (count_result or 0)
        }

    def _navigate_to_next_page(self, interactor: PageInteractor, current_page: int, total_pages: int) -> tuple[bool, int]:
        """
        翻到下一页。

        Args:
            interactor: 页面交互器
            current_page: 当前页码
            total_pages: 总页数

        Returns:
            (是否成功, 新页码)
        """
        if current_page >= total_pages:
            return False, current_page
        
        pagination_status = interactor.get_pagination_status()
        next_disabled = pagination_status.get("nextDisabled", True)
        
        if next_disabled:
            return False, current_page
        
        # 点击下一页
        next_clicked = interactor.click_next_page()
        
        if not next_clicked:
            return False, current_page
        
        new_page = current_page + 1
        self._log(f"已点击下一页，开始处理第 {new_page} 页（共 {total_pages} 页）。")
        logger.info("已点击下一页，开始处理第 {} 页（共 {} 页）", new_page, total_pages)
        
        # 等待页面加载
        try:
            interactor.with_context(
                lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000),
                require_selector=False
            )
            time.sleep(2)  # 等待页面渲染
        except Exception:
            pass
        
        return True, new_page

    def _task_worker(self, directory: Path, duration: float, interval: float, port: int) -> None:
        controller = BrowserController()
        # 使用封装的选择器
        item_selector = PageScripts.ITEM_SELECTOR

        # 创建页面交互器
        interactor = PageInteractor(controller, item_selector)

        def _go_to_page(target_page: int) -> bool:
            """跳转到指定页码。"""
            return interactor.go_to_page(target_page)

        def _go_to_last_page(page_count: int) -> bool:
            """跳转到最后一页。"""
            if page_count <= 1:
                return False
            self._log(f"检测到分页，共 {page_count} 页，准备跳转到最后一页开始处理。")
            success = _go_to_page(page_count)
            if success:
                self._log("已跳转到最后一页（倒序第 1 页）。")
            else:
                self._log("⚠️ 未能跳转到最后一页，将从当前页开始处理。")
            return success

        try:
            try:
                self._connect_controller_instance(controller, port)
                self._log(f"任务线程已连接浏览器：端口 {port}")
            except Exception as exc:  # noqa: BLE001
                logger.exception("任务线程连接浏览器失败")
                self._log(f"任务启动失败：{exc}")
                self.after(0, lambda e=exc: messagebox.showerror("执行失败", str(e)))
                return

            pagination_status = interactor.get_pagination_status()
            total_pages = max(1, pagination_status.get("pageCount", 1))
            current_page = pagination_status.get("currentPage", 1)
            
            # 从第一页开始播放
            if total_pages > 1:
                self._log(f"检测到分页，共 {total_pages} 页。从第一页开始播放。")
                logger.info("检测到分页，共 {} 页。从第一页开始播放。", total_pages)
                
                # 跳转到第一页
                if current_page != 1:
                    _go_to_page(1)
                    # 等待页面加载
                    try:
                        interactor.with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000), require_selector=False)
                        time.sleep(2)  # 等待商品列表渲染
                    except Exception:
                        pass
                    pagination_status = interactor.get_pagination_status()
                    current_page = pagination_status.get("currentPage", 1)
                    self._log(f"已跳转到第一页（页码 {current_page}/{total_pages}），等待商品列表加载...")
                    time.sleep(2)
                else:
                    self._log("当前已在第一页，将直接开始处理。")
            else:
                self._log("未检测到分页，当前页视为第 1 页。")
            
            current_page_num = 1  # 当前处理的页码
            self._log(f"开始处理第 {current_page_num} 页（共 {total_pages} 页）。")

            # 先等待页面加载，不要求找到选择器
            try:
                self._log("等待页面加载完成...")
                # 等待页面加载状态
                interactor.with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000), require_selector=False)
                # 额外等待，确保React应用完全渲染
                time.sleep(3)
                self._log("页面加载完成，开始查找商品列表...")
            except Exception as exc:  # noqa: BLE001
                logger.exception("页面加载失败")
                self._log(f"页面加载失败：{exc}")

            # 先检查页面状态，获取诊断信息
            self._log("检查页面状态...")
            page_info = None
            try:
                # 首先检查所有frames的信息
                try:
                    frames_info = controller.perform(
                        lambda page: {
                            "main_url": page.url,
                            "main_title": page.title,
                            "frame_count": len(page.frames),
                            "frames": [
                                {
                                    "url": frame.url,
                                    "name": frame.name or "",
                                    "title": frame.title() if hasattr(frame, 'title') else "",
                                    "is_main": frame == page.main_frame
                                }
                                for frame in page.frames[:10]  # 限制最多10个frames
                            ]
                        }
                    )
                    if frames_info:
                        self._log(f"页面框架信息：")
                        self._log(f"  - 主页面URL: {frames_info.get('main_url', '未知')}")
                        self._log(f"  - 主页面标题: {frames_info.get('main_title', '未知')}")
                        self._log(f"  - 框架总数: {frames_info.get('frame_count', 0)}")
                        for idx, frame_info in enumerate(frames_info.get('frames', [])[:5]):
                            frame_type = "主框架" if frame_info.get('is_main') else "子框架"
                            self._log(f"  - 框架{idx+1} ({frame_type}): {frame_info.get('url', '未知')[:100]}")
                except Exception as frame_exc:
                    logger.debug("检查frames失败: {}", frame_exc)
                    self._log(f"检查frames失败: {frame_exc}")
                
                page_info = controller.perform(
                    lambda page: page.evaluate("""
                        () => {
                            // 检查页面加载状态
                            const readyState = document.readyState;
                            const hasBody = !!document.body;
                            const bodyChildren = hasBody ? document.body.children.length : 0;
                            
                            // 检查是否有加载动画
                            const loadingElements = document.querySelectorAll('.ant-spin-spinning, .page-loading-warp, [class*="loading"], [class*="spin"]');
                            const hasLoading = loadingElements.length > 0;
                            
                            // 检查iframe数量
                            const iframes = document.querySelectorAll('iframe');
                            
                            // 检查表格行（新结构）
                            const tableRows = document.querySelectorAll('tr.ant-table-row');
                            
                            // 检查表格（更通用的选择器）
                            const tables = document.querySelectorAll('table');
                            const antTables = document.querySelectorAll('table.ant-table, .ant-table');
                            
                            // 检查商品容器（新结构）
                            const skuContainers = document.querySelectorAll('div.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-skuContainer');
                            
                            // 检查旧结构的商品容器
                            const oldWrappers = document.querySelectorAll('div.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-wrapper');
                            
                            // 检查是否有商品相关的元素
                            const goodsElements = document.querySelectorAll('[class*="goods"], [class*="sku"], [class*="item"]');
                            
                            // 获取所有包含"讲解"文本的按钮
                            const explainButtons = Array.from(document.querySelectorAll('button, a, span, div')).filter(el => {
                                const text = (el.textContent || '').trim();
                                return text === '讲解' || text.includes('讲解');
                            });
                            
                            // 检查tbody
                            const tbody = document.querySelector('tbody.ant-table-tbody');
                            const allTbodies = document.querySelectorAll('tbody');
                            
                            // 检查所有tr元素
                            const allTrs = document.querySelectorAll('tr');
                            const trsWithAntTableRow = Array.from(allTrs).filter(tr => {
                                const className = tr.className || '';
                                return typeof className === 'string' && className.includes('ant-table-row');
                            });
                            
                            // 查找包含"讲解"按钮的父容器
                            const goodsContainers = new Set();
                            const explainButtonDetails = [];
                            explainButtons.forEach((btn, idx) => {
                                const btnText = (btn.textContent || '').trim();
                                const btnTag = btn.tagName || '';
                                const btnClass = (btn.className || '').toString();
                                
                                explainButtonDetails.push({
                                    index: idx,
                                    tag: btnTag,
                                    class: btnClass.substring(0, 100),
                                    text: btnText.substring(0, 50)
                                });
                                
                                let parent = btn.parentElement;
                                let depth = 0;
                                while (parent && depth < 10) {
                                    if (parent.tagName === 'TR' || (parent.classList && parent.classList.length > 0)) {
                                        const className = parent.className;
                                        if (typeof className === 'string' && className.trim()) {
                                            goodsContainers.add(className.split(' ')[0]);
                                        } else if (parent.tagName === 'TR') {
                                            goodsContainers.add('TR');
                                        }
                                    }
                                    parent = parent.parentElement;
                                    depth++;
                                }
                            });
                            
                            // 检查页面是否有内容
                            const hasContent = document.body && document.body.innerHTML && document.body.innerHTML.length > 100;
                            
                            // 检查是否有React根元素
                            const reactRoots = document.querySelectorAll('[id*="root"], [id*="app"], [class*="root"], [class*="app"]');
                            
                            return {
                                readyState: readyState,
                                hasBody: hasBody,
                                bodyChildren: bodyChildren,
                                hasContent: hasContent,
                                hasLoading: hasLoading,
                                loadingCount: loadingElements.length,
                                iframeCount: iframes.length,
                                tableCount: tables.length,
                                antTableCount: antTables.length,
                                tableRowCount: tableRows.length,
                                allTrCount: allTrs.length,
                                trsWithAntTableRowCount: trsWithAntTableRow.length,
                                skuContainerCount: skuContainers.length,
                                oldWrapperCount: oldWrappers.length,
                                goodsCount: goodsElements.length,
                                explainButtonCount: explainButtons.length,
                                explainButtonDetails: explainButtonDetails.slice(0, 5), // 只返回前5个按钮的详情
                                hasTbody: !!tbody,
                                tbodyCount: allTbodies.length,
                                reactRootCount: reactRoots.length,
                                url: window.location.href,
                                title: document.title,
                                containerClasses: Array.from(goodsContainers).slice(0, 10),
                                bodyHtmlLength: hasBody ? document.body.innerHTML.length : 0
                            };
                        }
                    """)
                )
                
                if page_info:
                    self._log(f"页面状态：")
                    self._log(f"  - 当前URL: {page_info.get('url', '未知')}")
                    self._log(f"  - 页面标题: {page_info.get('title', '未知')}")
                    self._log(f"  - 页面readyState: {page_info.get('readyState', '未知')}")
                    self._log(f"  - 是否有body: {page_info.get('hasBody', False)}")
                    self._log(f"  - body子元素数量: {page_info.get('bodyChildren', 0)}")
                    self._log(f"  - body HTML长度: {page_info.get('bodyHtmlLength', 0)} 字符")
                    self._log(f"  - 是否有内容: {page_info.get('hasContent', False)}")
                    self._log(f"  - React根元素数量: {page_info.get('reactRootCount', 0)}")
                    self._log(f"  - iframe数量: {page_info.get('iframeCount', 0)}")
                    self._log(f"  - 是否有加载动画: {page_info.get('hasLoading', False)} (数量: {page_info.get('loadingCount', 0)})")
                    self._log(f"  - 表格数量: {page_info.get('tableCount', 0)}")
                    self._log(f"  - Ant Design表格数量: {page_info.get('antTableCount', 0)}")
                    self._log(f"  - tbody数量: {page_info.get('tbodyCount', 0)}")
                    self._log(f"  - 所有tr元素数量: {page_info.get('allTrCount', 0)}")
                    self._log(f"  - 包含'ant-table-row'类的tr数量: {page_info.get('trsWithAntTableRowCount', 0)}")
                    self._log(f"  - 表格行数量 (tr.ant-table-row): {page_info.get('tableRowCount', 0)}")
                    self._log(f"  - 商品容器数量 (skuContainer): {page_info.get('skuContainerCount', 0)}")
                    self._log(f"  - 旧容器数量 (wrapper): {page_info.get('oldWrapperCount', 0)}")
                    self._log(f"  - 商品相关元素数量: {page_info.get('goodsCount', 0)}")
                    self._log(f"  - '讲解'按钮数量: {page_info.get('explainButtonCount', 0)}")
                    self._log(f"  - 是否有tbody.ant-table-tbody: {page_info.get('hasTbody', False)}")
                    
                    # 显示"讲解"按钮的详细信息
                    explain_button_details = page_info.get('explainButtonDetails', [])
                    if explain_button_details:
                        self._log(f"  - '讲解'按钮详情（前{len(explain_button_details)}个）:")
                        for btn_detail in explain_button_details:
                            self._log(f"    按钮{btn_detail.get('index', 0)+1}: 标签={btn_detail.get('tag', '')}, 类名={btn_detail.get('class', '')[:50]}, 文本={btn_detail.get('text', '')}")
                    
                    container_classes = page_info.get('containerClasses', [])
                    if container_classes:
                        self._log(f"  - 检测到的商品容器类名: {', '.join(container_classes[:5])}")
                    
                    # 诊断建议
                    if not page_info.get('hasBody'):
                        self._log("⚠️ 警告: 页面没有body元素，可能页面还未加载")
                    elif page_info.get('bodyHtmlLength', 0) < 100:
                        self._log("⚠️ 警告: body内容很少，可能页面内容未加载")
                    elif page_info.get('readyState') != 'complete':
                        self._log(f"⚠️ 警告: 页面readyState为'{page_info.get('readyState')}'，可能还在加载中")
                    
                    if page_info.get('hasLoading'):
                        self._log("页面仍在加载中，等待加载完成...")
                        time.sleep(5)
                    
                    # 如果找到表格行，直接使用表格行作为选择器
                    if page_info.get('tableRowCount', 0) > 0:
                        self._log(f"✓ 检测到 {page_info.get('tableRowCount')} 个表格行，将优先使用表格行选择器")
                    elif page_info.get('allTrCount', 0) > 0:
                        self._log(f"⚠️ 找到 {page_info.get('allTrCount')} 个tr元素，但都不包含'ant-table-row'类")
                    
                    # 如果找到"讲解"按钮，尝试通过按钮定位商品容器
                    if page_info.get('explainButtonCount', 0) > 0:
                        self._log(f"✓ 找到 {page_info.get('explainButtonCount')} 个'讲解'按钮")
                    else:
                        self._log("⚠️ 未找到'讲解'按钮，可能页面结构已改变或页面未完全加载")
                    
                    logger.info(
                        "页面状态诊断 -> url={}, readyState={}, tr.ant-table-row={}, skuContainer={}, explainButtons={}, goodsElements={}, hasLoading={}, iframeCount={}",
                        page_info.get('url'),
                        page_info.get('readyState'),
                        page_info.get('tableRowCount'),
                        page_info.get('skuContainerCount'),
                        page_info.get('explainButtonCount'),
                        page_info.get('goodsCount'),
                        page_info.get('hasLoading'),
                        page_info.get('iframeCount'),
                    )
            except Exception as e:
                logger.warning("页面状态检查失败: {}", e)
                self._log(f"页面状态检查失败: {e}")
            
            # 如果页面状态检查成功，但没找到元素，尝试在所有frames中查找
            if page_info and page_info.get('tableRowCount', 0) == 0 and page_info.get('skuContainerCount', 0) == 0:
                self._log("页面状态检查显示未找到表格行和容器，尝试在所有frames中查找...")
                try:
                    frames_check = controller.perform(
                        lambda page: {
                            "main_frame": {
                                "url": page.url,
                                "tr_count": len(page.query_selector_all("tr")),
                                "table_row_count": len(page.query_selector_all("tr.ant-table-row")),
                                "explain_button_count": len([el for el in page.query_selector_all("button, a, span, div") if "讲解" in (el.inner_text() or "")])
                            },
                            "other_frames": [
                                {
                                    "url": frame.url,
                                    "name": frame.name or "",
                                    "tr_count": len(frame.query_selector_all("tr")) if hasattr(frame, 'query_selector_all') else 0,
                                    "table_row_count": len(frame.query_selector_all("tr.ant-table-row")) if hasattr(frame, 'query_selector_all') else 0,
                                    "explain_button_count": len([el for el in frame.query_selector_all("button, a, span, div") if "讲解" in (el.inner_text() or "")]) if hasattr(frame, 'query_selector_all') else 0
                                }
                                for frame in page.frames[1:6]  # 检查前5个子frames
                            ]
                        }
                    )
                    if frames_check:
                        main_info = frames_check.get("main_frame", {})
                        self._log(f"主框架: URL={main_info.get('url', '未知')[:80]}, tr数量={main_info.get('tr_count', 0)}, 表格行数量={main_info.get('table_row_count', 0)}, 讲解按钮数量={main_info.get('explain_button_count', 0)}")
                        for idx, frame_info in enumerate(frames_check.get("other_frames", [])):
                            if frame_info.get('tr_count', 0) > 0 or frame_info.get('explain_button_count', 0) > 0:
                                self._log(f"子框架{idx+1}: URL={frame_info.get('url', '未知')[:80]}, tr数量={frame_info.get('tr_count', 0)}, 表格行数量={frame_info.get('table_row_count', 0)}, 讲解按钮数量={frame_info.get('explain_button_count', 0)}")
                    logger.info(
                        "frame诊断 -> main(url={}, tr={}, tr_ant={}, explain={}), 子frame数量={}",
                        main_info.get('url'),
                        main_info.get('tr_count'),
                        main_info.get('table_row_count'),
                        main_info.get('explain_button_count'),
                        len(frames_check.get("other_frames", [])),
                    )
                except Exception as frames_exc:
                    logger.debug("检查frames失败: {}", frames_exc)
                    self._log(f"检查frames失败: {frames_exc}")
                
                # 尝试直接使用JavaScript查找所有可能的元素
                self._log("尝试直接查找所有tr元素...")
                try:
                    all_trs = controller.perform(
                        lambda page: page.evaluate("""
                            () => {
                                const allTrs = document.querySelectorAll('tr');
                                return {
                                    total: allTrs.length,
                                    withClass: Array.from(allTrs).filter(tr => tr.className && tr.className.includes('ant-table-row')).length,
                                    firstTrClass: allTrs.length > 0 ? (allTrs[0].className || '') : '',
                                    firstTrHtml: allTrs.length > 0 ? (allTrs[0].outerHTML || '').substring(0, 200) : ''
                                };
                            }
                        """)
                    )
                    if all_trs:
                        self._log(f"  找到 {all_trs.get('total', 0)} 个tr元素，其中 {all_trs.get('withClass', 0)} 个包含'ant-table-row'类")
                        if all_trs.get('firstTrClass'):
                            self._log(f"  第一个tr的类名: {all_trs.get('firstTrClass')}")
                        if all_trs.get('firstTrHtml'):
                            self._log(f"  第一个tr的HTML片段: {all_trs.get('firstTrHtml')}")
                        logger.info(
                            "all_tr诊断 -> total={}, with_ant={}, first_tr_class={}",
                            all_trs.get('total', 0),
                            all_trs.get('withClass', 0),
                            all_trs.get('firstTrClass'),
                        )
                except Exception as tr_exc:
                    logger.debug("查找tr元素失败: {}", tr_exc)
            
            # 尝试多种选择器策略，增加等待时间
            # 优先尝试通过"讲解"按钮定位商品（使用JavaScript方式）
            alternative_selectors = [
                # 方法1: 新的表格结构选择器（优先）
                "tr.ant-table-row",
                "div.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-skuContainer",
                # 方法2: 原始选择器（兼容旧结构）
                item_selector,
                "div.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-wrapper",
                # 方法3: 通用选择器
                "div[class*='goods'][class*='item']",
                "div[class*='sku'][class*='item']",
                "div[class*='goods-sku']",
                "[class*='wrapper'][class*='goods']",
                "div[class*='goods']",
                "div[class*='sku']",
            ]

            found_selector = None
            # 多次尝试查找，因为商品列表可能需要时间加载
            for attempt in range(5):  # 最多尝试5次
                if attempt > 0:
                    self._log(f"第 {attempt + 1} 次尝试查找商品列表...")
                    time.sleep(2)  # 每次尝试之间等待2秒
                
                for alt_selector in alternative_selectors:
                    try:
                        self._log(f"尝试选择器: {alt_selector}")
                        # 先尝试使用Playwright选择器
                        try:
                            result = controller.perform(
                                lambda page, selector=alt_selector: (
                                    # 先等待选择器出现
                                    page.wait_for_selector(selector, timeout=5000, state="attached"),
                                    len(page.query_selector_all(selector))
                                )
                            )
                            if result and result[1] > 0:
                                found_selector = alt_selector
                                self._log(f"找到 {result[1]} 个商品，使用选择器: {alt_selector}")
                                break
                        except Exception as pw_exc:
                            # 如果Playwright选择器失败，尝试使用JavaScript直接查找
                            logger.debug("Playwright选择器失败，尝试JavaScript查找: {}", pw_exc)
                            try:
                                js_result = controller.perform(
                                    lambda page, sel=alt_selector: page.evaluate("""
                                        (selector) => {
                                            try {
                                                const elements = document.querySelectorAll(selector);
                                                const firstEl = elements.length > 0 ? elements[0] : null;
                                                let firstElementInfo = null;
                                                if (firstEl) {
                                                    const tagName = firstEl.tagName || '';
                                                    const className = firstEl.className || '';
                                                    const classStr = typeof className === 'string' ? className : (Array.isArray(className) ? className.join(' ') : String(className));
                                                    firstElementInfo = tagName + (classStr ? '.' + classStr.split(' ')[0] : '');
                                                }
                                                return {
                                                    count: elements.length,
                                                    found: elements.length > 0,
                                                    firstElement: firstElementInfo,
                                                    selector: selector
                                                };
                                            } catch (e) {
                                                return { 
                                                    count: 0, 
                                                    found: false, 
                                                    error: e.message,
                                                    selector: selector
                                                };
                                            }
                                        }
                                    """, alt_selector)
                                )
                                if js_result:
                                    if js_result.get('found') and js_result.get('count', 0) > 0:
                                        found_selector = alt_selector
                                        self._log(f"✓ 通过JavaScript找到 {js_result.get('count')} 个商品，使用选择器: {alt_selector}")
                                        if js_result.get('firstElement'):
                                            self._log(f"  第一个元素: {js_result.get('firstElement')}")
                                        logger.info(
                                            "JS选择器成功 -> selector={}, count={}, firstElement={}",
                                            alt_selector,
                                            js_result.get('count'),
                                            js_result.get('firstElement'),
                                        )
                                        break
                                    elif js_result.get('error'):
                                        logger.debug("JavaScript查找出错: {}", js_result.get('error'))
                                    else:
                                        logger.info(
                                            "JS选择器未找到元素 -> selector={}, count={}",
                                            alt_selector,
                                            js_result.get('count'),
                                        )
                            except Exception as js_exc:
                                logger.debug("JavaScript查找异常: {}", js_exc)
                                continue
                    except Exception as e:
                        # 记录失败原因以便调试
                        logger.debug("选择器 {} 失败: {}", alt_selector, e)
                        continue
                
                if found_selector:
                    break
                
                # 如果还没找到，尝试通过JavaScript直接查找包含"讲解"按钮的元素
                if not found_selector and attempt >= 1:
                    try:
                        self._log("尝试通过JavaScript查找包含'讲解'按钮的商品容器...")
                        js_result = controller.perform(
                            lambda page: page.evaluate("""
                                () => {
                                    // 查找所有包含"讲解"文本的元素
                                    const allElements = Array.from(document.querySelectorAll('*'));
                                    const explainElements = allElements.filter(el => {
                                        const text = (el.textContent || '').trim();
                                        return text === '讲解' || (text.includes('讲解') && text.length < 10);
                                    });
                                    
                                    if (explainElements.length === 0) {
                                        return { count: 0, buttonCount: 0, found: false, selectors: [] };
                                    }
                                    
                                    // 找到这些元素的父容器，并提取选择器
                                    const containers = [];
                                    const seenClasses = new Set();
                                    
                                    explainElements.forEach(el => {
                                        let parent = el.parentElement;
                                        let depth = 0;
                                        while (parent && depth < 8) {
                                            if (parent.tagName === 'DIV' && parent.className) {
                                                let className = '';
                                                if (typeof parent.className === 'string') {
                                                    className = parent.className;
                                                } else if (parent.className.baseVal) {
                                                    className = parent.className.baseVal;
                                                } else if (Array.isArray(parent.className)) {
                                                    className = parent.className.join(' ');
                                                } else {
                                                    className = String(parent.className);
                                                }
                                                
                                                if (className && className.trim() && !seenClasses.has(className)) {
                                                    seenClasses.add(className);
                                                    // 尝试构建选择器
                                                    const classParts = className.split(' ').filter(c => c && c.length > 0);
                                                    if (classParts.length > 0) {
                                                        // 使用第一个有意义的类名
                                                        const selector = '.' + classParts[0].replace(/[\\s]+/g, '.');
                                                        containers.push({
                                                            selector: selector,
                                                            className: className,
                                                            element: parent
                                                        });
                                                    }
                                                }
                                            }
                                            parent = parent.parentElement;
                                            depth++;
                                        }
                                    });
                                    
                                    // 去重并返回最常用的选择器
                                    const selectorCounts = {};
                                    containers.forEach(c => {
                                        selectorCounts[c.selector] = (selectorCounts[c.selector] || 0) + 1;
                                    });
                                    
                                    const sortedSelectors = Object.entries(selectorCounts)
                                        .sort((a, b) => b[1] - a[1])
                                        .slice(0, 3)
                                        .map(([sel]) => sel);
                                    
                                    return {
                                        count: containers.length,
                                        buttonCount: explainElements.length,
                                        found: containers.length > 0,
                                        selectors: sortedSelectors
                                    };
                                }
                            """)
                        )
                        
                        if js_result and js_result.get('found') and js_result.get('count', 0) > 0:
                            self._log(f"通过JavaScript找到 {js_result.get('buttonCount')} 个'讲解'按钮，位于 {js_result.get('count')} 个容器中")
                            selectors = js_result.get('selectors', [])
                            if selectors:
                                self._log(f"尝试使用JavaScript找到的选择器: {', '.join(selectors)}")
                                # 尝试使用找到的选择器
                                for js_selector in selectors:
                                    try:
                                        result = controller.perform(
                                            lambda page, sel=js_selector: (
                                                page.wait_for_selector(sel, timeout=5000, state="attached"),
                                                len(page.query_selector_all(sel))
                                            )
                                        )
                                        if result and result[1] > 0:
                                            found_selector = js_selector
                                            self._log(f"成功使用JavaScript找到的选择器: {js_selector}，找到 {result[1]} 个元素")
                                            break
                                    except Exception:
                                        continue
                    except Exception as js_e:
                        logger.debug("JavaScript查找失败: {}", js_e)

            if not found_selector:
                # 如果所有选择器都失败，尝试输出页面内容用于诊断
                logger.exception("等待讲解列表加载失败")
                self._log("未检测到可讲解商品，尝试输出页面 HTML 片段用于诊断。")
                try:
                    snippet = interactor.with_context(lambda ctx: ctx.inner_html("body"), require_selector=False)
                    if snippet:
                        debug_path = directory / "debug-snippet.html"
                        try:
                            debug_path.write_text(snippet, encoding="utf-8")
                            self._log(f"已将页面内容写入：{debug_path}")
                            
                            # 检查页面是否还在加载中
                            loading_check = controller.perform(
                                lambda page: page.evaluate("""
                                    () => {
                                        // 检查是否有加载动画
                                        const loadingElements = document.querySelectorAll('.ant-spin-spinning, .page-loading-warp, [class*="loading"], [class*="spin"]');
                                        const hasLoading = loadingElements.length > 0;
                                        
                                        // 检查是否有商品相关的元素
                                        const goodsElements = document.querySelectorAll('[class*="goods"], [class*="sku"], [class*="item"]');
                                        
                                        // 获取所有包含"讲解"文本的元素
                                        const explainElements = Array.from(document.querySelectorAll('*')).filter(el => {
                                            const text = el.textContent || '';
                                            return text.includes('讲解');
                                        });
                                        
                                        return {
                                            hasLoading: hasLoading,
                                            loadingCount: loadingElements.length,
                                            goodsCount: goodsElements.length,
                                            explainCount: explainElements.length,
                                            url: window.location.href
                                        };
                                    }
                                """)
                            )
                            
                            if loading_check:
                                self._log(f"页面状态检查：")
                                self._log(f"  - 当前URL: {loading_check.get('url', '未知')}")
                                self._log(f"  - 是否有加载动画: {loading_check.get('hasLoading', False)}")
                                self._log(f"  - 加载元素数量: {loading_check.get('loadingCount', 0)}")
                                self._log(f"  - 商品相关元素数量: {loading_check.get('goodsCount', 0)}")
                                self._log(f"  - 包含'讲解'的元素数量: {loading_check.get('explainCount', 0)}")
                                
                                if loading_check.get('hasLoading'):
                                    self._log("页面仍在加载中，请等待页面完全加载后再试。")
                                elif loading_check.get('goodsCount', 0) == 0:
                                    self._log("页面已加载，但未找到商品列表元素。")
                                    self._log("请确认：")
                                    self._log("1. 是否已打开正确的直播后台页面（商品列表页面）")
                                    self._log("2. 页面是否需要登录")
                                    self._log("3. 商品列表是否需要手动刷新")
                            
                            # 尝试查找页面中的所有可能的选择器
                            selectors_found = controller.perform(
                                lambda page: page.evaluate("""
                                    () => {
                                        const allDivs = Array.from(document.querySelectorAll('div[class]'));
                                        const classNames = new Set();
                                        allDivs.forEach(div => {
                                            if (div.className && typeof div.className === 'string') {
                                                classNames.add(div.className);
                                            }
                                        });
                                        return Array.from(classNames).slice(0, 50);
                                    }
                                """)
                            )
                            if selectors_found:
                                debug_selector_path = directory / "debug-selectors.txt"
                                debug_selector_path.write_text("\n".join(selectors_found), encoding="utf-8")
                                self._log(f"已保存页面中的类名到：{debug_selector_path}")
                        except OSError as write_exc:
                            self._log(f"写入调试文件失败：{write_exc}")
                except Exception as debug_exc:  # noqa: BLE001
                    logger.exception("获取调试信息失败")
                    self._log(f"获取调试信息失败：{debug_exc}")
                
                self._log("未检测到可讲解商品，请检查：")
                self._log("1. 是否已打开直播后台页面")
                self._log("2. 页面是否已完全加载")
                self._log("3. 商品列表是否已显示")
                return
            
            # 使用找到的选择器
            item_selector = found_selector

            # 只统计有"讲解"按钮的商品项，避免统计过多元素
            count_result = self._count_products(interactor, item_selector)
            goods_count = count_result["valid"]
            total_count = count_result["total"]
            
            # 初始化跨页面的商品编号跟踪变量（需要在分页循环外部初始化，避免每次进入新页时重置）
            last_processed_item_index = None  # 记录上次处理的商品编号（itemIndex），跨页面保持
            
            # 分页循环：从第一页开始，逐页往后处理
            while current_page_num <= total_pages:
                if self.task_stop_event.is_set():
                    break
                
                # 重新统计当前页的商品数量
                count_result = self._count_products(interactor, item_selector)
                goods_count = count_result["valid"]
                total_count = count_result["total"]
                
                if goods_count == 0:
                    self._log(f"第 {current_page_num} 页未找到可讲解的商品。")
                    if total_count > 0:
                        self._log(f"提示：选择器匹配到 {total_count} 个元素，但没有找到可讲解的商品。")
                    # 如果是第一页且没有商品，等待一下再重试统计（可能是页面还没完全加载）
                    if current_page_num == 1:
                        self._log("第一页统计为0，等待3秒后重新统计...")
                        time.sleep(3)
                        # 重新统计一次
                        count_result = self._count_products(interactor, item_selector)
                        goods_count = count_result["valid"]
                        total_count = count_result["total"]
                        self._log(f"重新统计完成：共 {goods_count} 个可讲解商品（总数 {total_count}）")
                        logger.info("重新统计完成：共 {} 个可讲解商品", goods_count)
                else:
                    if total_count > goods_count:
                        self._log(f"第 {current_page_num} 页：选择器匹配到 {total_count} 个元素，过滤后找到 {goods_count} 个可讲解商品。")
                    else:
                        self._log(f"第 {current_page_num} 页：共检测到 {goods_count} 个可讲解商品，开始依次处理。")

                processed_count = 0
                processed_indices = set()  # 记录已处理过的商品索引，避免重复处理
                processed_skus = set()  # 记录已处理过的商品SKU，避免重复处理
                
                # 第一次查询商品列表，按编号降序排序
                self._log(f"查询第 {current_page_num} 页商品列表...")
                logger.info("查询第 {} 页商品列表", current_page_num)
                time.sleep(0.5)  # 等待页面稳定
                
                try:
                    current_items = interactor.with_context(
                    lambda ctx: ctx.evaluate(
                        """
                        ({ itemSelector, buttonSelector }) => {
                            const items = Array.from(document.querySelectorAll(itemSelector));
                            return items.map((item, idx) => {
                                // 查找"讲解"按钮 - 排除下拉菜单的触发按钮（三个点...）
                                let button = null;
                                
                                // 辅助函数：检查是否是下拉菜单的触发按钮（三个点）
                                const isDropdownTrigger = (node) => {
                                    if (!node) return false;
                                    const text = (node.textContent || node.innerText || '').trim();
                                    if (text === '讲解') {
                                    return false;
                                    }
                                    if (text === '...' || text === '⋯' || text === '⋮' || (text.length <= 2 && text !== '讲解')) {
                                        return true;
                                    }
                                    const className = node.className || '';
                                    if (typeof className === 'string') {
                                        if (className.includes('dropdown') || className.includes('more') || 
                                            className.includes('menu') || className.includes('trigger')) {
                                            return true;
                                        }
                                    }
                                    let parent = node.parentElement;
                                    let checkCount = 0;
                                    while (parent && checkCount < 3) {
                                        const parentClass = parent.className || '';
                                        if (typeof parentClass === 'string') {
                                            if (parentClass.includes('dropdown') || parentClass.includes('menu')) {
                                                return true;
                                            }
                                        }
                                        parent = parent.parentElement;
                                        checkCount++;
                                    }
                                    return false;
                                };
                                
                                const getFullText = (node) => {
                                    if (!node) return '';
                                    let text = (node.textContent || '').trim();
                                    if (!text) {
                                        text = (node.innerText || '').trim();
                                    }
                                    if (!text) {
                                        const innerSpan = node.querySelector('span');
                                        if (innerSpan) {
                                            text = (innerSpan.textContent || innerSpan.innerText || '').trim();
                                        }
                                    }
                                    return text;
                                };
                                
                                const selectBtnSpans = Array.from(item.querySelectorAll('span.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn'));
                                button = selectBtnSpans.find((span) => {
                                    const text = getFullText(span);
                                    return text === "讲解";
                                });
                                
                                if (!button) {
                                    const allSpans = Array.from(item.querySelectorAll('span'));
                                    button = allSpans.find((span) => {
                                        const text = getFullText(span);
                                        return text === "讲解" && !isDropdownTrigger(span);
                                    });
                                }
                                
                                if (!button) {
                                    const allButtons = Array.from(item.querySelectorAll('button, span, div, a'));
                                    button = allButtons.find((node) => {
                                        const text = getFullText(node);
                                        return text === "讲解" && !isDropdownTrigger(node);
                                    });
                                }
                                
                                const buttonText = button ? getFullText(button) : '';
                                const isProcessed = !button || (
                                    buttonText !== "讲解" && 
                                    !buttonText.includes("讲解") &&
                                    (buttonText.includes("取消") || buttonText.includes("结束"))
                                );
                                
                                let itemIndex = null;
                                const indexSpan = item.querySelector('span.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-index');
                                if (indexSpan) {
                                    const indexText = (indexSpan.textContent || indexSpan.innerText || '').trim();
                                    const indexNum = parseInt(indexText, 10);
                                    if (!isNaN(indexNum)) {
                                        itemIndex = indexNum;
                                    } else {
                                        itemIndex = indexText;
                                    }
                                }
                                
                                let sku = null;
                                const allTextElements = Array.from(item.querySelectorAll('*'));
                                for (const el of allTextElements) {
                                    const text = el.textContent || '';
                                    const skuMatch = text.match(/SKU[：:][\\s]*(\\d+)/i);
                                    if (skuMatch && skuMatch[1]) {
                                        sku = skuMatch[1];
                                        break;
                                    }
                                }
                                
                                if (!sku) {
                                    const skuElements = Array.from(item.querySelectorAll('[data-sku], [data-id], [data-product-id], [class*="sku"]'));
                                    for (const el of skuElements) {
                                        const skuValue = el.getAttribute('data-sku') || 
                                                        el.getAttribute('data-id') || 
                                                        el.getAttribute('data-product-id') ||
                                                        el.getAttribute('id');
                                        if (skuValue && skuValue.length > 0 && skuValue !== '商品图') {
                                            if (/^\\d+$/.test(skuValue)) {
                                                sku = skuValue;
                                                break;
                                            } else {
                                                const numMatch = skuValue.match(/\\d{10,}/);
                                                if (numMatch) {
                                                    sku = numMatch[0];
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                }
                                
                                if (!sku) {
                                    const images = Array.from(item.querySelectorAll('img'));
                                    for (const img of images) {
                                        const imgSrc = img.src || img.getAttribute('data-src') || '';
                                        if (imgSrc) {
                                            let skuMatch = imgSrc.match(/[\\/]jfs[\\/]t\\d+[\\/](\\d+)[\\/]/);
                                            if (skuMatch && skuMatch[1]) {
                                                sku = skuMatch[1];
                                                break;
                                            }
                                            skuMatch = imgSrc.match(/[\\/](\\d{8,})[\\/]/);
                                            if (skuMatch && skuMatch[1]) {
                                                sku = skuMatch[1];
                                                break;
                                            }
                                            skuMatch = imgSrc.match(/[\\/](\\d{10,})/);
                                            if (skuMatch && skuMatch[1]) {
                                                sku = skuMatch[1];
                                                break;
                                            }
                                        }
                                    }
                                }
                                
                                if (!sku) {
                                    const itemText = item.textContent || '';
                                    const skuMatch = itemText.match(/\\d{13}/);
                                    if (skuMatch) {
                                        sku = skuMatch[0];
                                    } else {
                                        const longNumMatch = itemText.match(/\\d{10,}/);
                                        if (longNumMatch) {
                                            sku = longNumMatch[0];
                                        }
                                    }
                                }
                                
                                if (!sku) {
                                    const titleEl = item.querySelector('[class*="title"], [class*="name"], [title]');
                                    if (titleEl) {
                                        const title = titleEl.textContent?.trim() || titleEl.getAttribute('title') || '';
                                        if (title && title.length > 0 && title !== '商品图') {
                                        sku = title.substring(0, 100);
                                        }
                                    }
                                }
                                
                                if (!sku) {
                                    sku = `item_${idx}_${buttonText}`;
                                }
                                
                                return {
                                index: idx,
                                itemIndex: itemIndex,
                                    hasButton: !!button,
                                    buttonText: buttonText,
                                    isProcessed: isProcessed,
                                sku: sku
                                };
                            });
                        }
                        """,
                        {
                            "itemSelector": item_selector,
                            "buttonSelector": button_selector,
                        },
                    )
                ) or []
                except Exception as e:
                    logger.exception("查询商品列表时发生异常")
                    self._log(f"⚠️ 查询商品列表异常: {e}")
                    current_items = []

                # 按编号降序排序
                items_with_index = []
                items_without_index = []
                
                for item_info in current_items:
                    item_index = item_info.get("itemIndex")
                    if item_index is not None:
                        items_with_index.append(item_info)
                    else:
                        items_without_index.append(item_info)
                
                def sort_key(item):
                    item_index = item.get("itemIndex")
                    if isinstance(item_index, (int, float)):
                        return (0, -item_index)
                    elif isinstance(item_index, str):
                        try:
                            num = int(item_index)
                            return (0, -num)
                        except ValueError:
                            return (1, item_index)
                    else:
                        return (2, 0)
                
                items_with_index.sort(key=sort_key)
                current_items = items_with_index + items_without_index
                
                # 过滤出有"讲解"按钮的商品
                current_items = [item for item in current_items if item.get("buttonText") == "讲解"]
                
                self._log(f"✓ 查询商品列表完成，共 {len(current_items)} 个可讲解商品（已按编号降序排序）")
                logger.info("查询商品列表完成，共 {} 个可讲解商品", len(current_items))
                
                if len(current_items) == 0:
                    self._log(f"第 {current_page_num} 页没有可讲解的商品")
                    logger.info("第 {} 页没有可讲解的商品", current_page_num)
                    # 如果第一页没有商品，等待一下再重试一次（可能是页面还没完全加载）
                    if current_page_num == 1:
                        self._log("第一页没有商品，等待2秒后重试...")
                        time.sleep(2)
                        # 重新查询一次
                        try:
                            current_items = interactor.with_context(
                                lambda ctx: ctx.evaluate(
                                """
                                ({ itemSelector, buttonSelector }) => {
                                    const items = Array.from(document.querySelectorAll(itemSelector));
                                    return items.map((item, idx) => {
                                    // 查找"讲解"按钮 - 排除下拉菜单的触发按钮（三个点...）
                                    let button = null;
                                    
                                    // 辅助函数：检查是否是下拉菜单的触发按钮（三个点）
                                    const isDropdownTrigger = (node) => {
                                        if (!node) return false;
                                        const text = (node.textContent || node.innerText || '').trim();
                                        if (text === '讲解') {
                                            return false;
                                        }
                                        if (text === '...' || text === '⋯' || text === '⋮' || (text.length <= 2 && text !== '讲解')) {
                                            return true;
                                        }
                                        const className = node.className || '';
                                        if (typeof className === 'string') {
                                            if (className.includes('dropdown') || className.includes('more') || 
                                                className.includes('menu') || className.includes('trigger')) {
                                                return true;
                                            }
                                        }
                                        let parent = node.parentElement;
                                        let checkCount = 0;
                                        while (parent && checkCount < 3) {
                                            const parentClass = parent.className || '';
                                            if (typeof parentClass === 'string') {
                                                if (parentClass.includes('dropdown') || parentClass.includes('menu')) {
                                                    return true;
                                                }
                                            }
                                            parent = parent.parentElement;
                                            checkCount++;
                                        }
                                        return false;
                                    };
                                    
                                    const getFullText = (node) => {
                                        if (!node) return '';
                                        let text = (node.textContent || '').trim();
                                        if (!text) {
                                            text = (node.innerText || '').trim();
                                        }
                                        if (!text) {
                                            const innerSpan = node.querySelector('span');
                                            if (innerSpan) {
                                                text = (innerSpan.textContent || innerSpan.innerText || '').trim();
                                            }
                                        }
                                        return text;
                                    };
                                    
                                    const selectBtnSpans = Array.from(item.querySelectorAll('span.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn'));
                                    button = selectBtnSpans.find((span) => {
                                        const text = getFullText(span);
                                        return text === "讲解";
                                    });
                                    
                                    if (!button) {
                                        const allSpans = Array.from(item.querySelectorAll('span'));
                                        button = allSpans.find((span) => {
                                            const text = getFullText(span);
                                            return text === "讲解" && !isDropdownTrigger(span);
                                        });
                                    }
                                    
                                    if (!button) {
                                        const allButtons = Array.from(item.querySelectorAll('button, span, div, a'));
                                        button = allButtons.find((node) => {
                                            const text = getFullText(node);
                                            return text === "讲解" && !isDropdownTrigger(node);
                                        });
                                    }
                                    
                                    const buttonText = button ? getFullText(button) : '';
                                    const isProcessed = !button || (
                                        buttonText !== "讲解" && 
                                        !buttonText.includes("讲解") &&
                                        (buttonText.includes("取消") || buttonText.includes("结束"))
                                    );
                                    
                                    // 获取商品编号（itemIndex）
                                    let itemIndex = null;
                                    const indexNode = item.querySelector('.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-index');
                                    if (indexNode) {
                                        const indexText = (indexNode.textContent || indexNode.innerText || '').trim();
                                        if (indexText) {
                                            const match = indexText.match(/\\d+/);
                                            if (match) {
                                                itemIndex = match[0];
                                            }
                                        }
                                    }
                                    
                                    // 获取SKU（用于去重）
                                    let sku = null;
                                    const skuNode = item.querySelector('.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-sku');
                                    if (skuNode) {
                                        sku = (skuNode.textContent || skuNode.innerText || '').trim();
                                    }
                                    
                                    // 如果没有找到SKU，尝试从标题中提取
                                    if (!sku) {
                                        const titleNode = item.querySelector('.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-title');
                                        if (titleNode) {
                                            const title = (titleNode.textContent || titleNode.innerText || '').trim();
                                            if (title) {
                                                sku = title.substring(0, 100);
                                            }
                                        }
                                    }
                                    
                                    if (!sku) {
                                        sku = `item_${idx}_${buttonText}`;
                                    }
                                    
                                    return {
                                        index: idx,
                                        itemIndex: itemIndex,
                                        hasButton: !!button,
                                        buttonText: buttonText,
                                        isProcessed: isProcessed,
                                        sku: sku
                                    };
                                });
                                }
                                """,
                                {
                                    "itemSelector": item_selector,
                                    "buttonSelector": button_selector,
                                },
                                )
                            ) or []
                            # 重新排序和过滤
                            items_with_index = []
                            items_without_index = []
                            for item_info in current_items:
                                item_index = item_info.get("itemIndex")
                                if item_index is not None:
                                    items_with_index.append(item_info)
                                else:
                                    items_without_index.append(item_info)
                            
                            def sort_key(item):
                                item_index = item.get("itemIndex")
                                if isinstance(item_index, (int, float)):
                                    return (0, -item_index)
                                elif isinstance(item_index, str):
                                    try:
                                        num = int(item_index)
                                        return (0, -num)
                                    except ValueError:
                                        return (1, item_index)
                                else:
                                    return (2, 0)
                            
                            items_with_index.sort(key=sort_key)
                            current_items = items_with_index + items_without_index
                            current_items = [item for item in current_items if item.get("buttonText") == "讲解"]
                            self._log(f"重试查询完成，共 {len(current_items)} 个可讲解商品")
                            logger.info("重试查询完成，共 {} 个可讲解商品", len(current_items))
                        except Exception as retry_exc:
                            logger.exception("重试查询商品列表时发生异常")
                            self._log(f"⚠️ 重试查询商品列表异常: {retry_exc}")
                            current_items = []
                    # 如果重试后仍然没有商品，且不是第一页，才继续执行（会跳到翻页逻辑）
                    # 如果是第一页且仍然没有商品，记录警告但继续尝试处理（可能商品确实不存在）
                    if len(current_items) == 0 and current_page_num == 1:
                        self._log("⚠️ 警告：第一页重试后仍然没有找到可讲解的商品，请检查第一页是否确实有商品")
                        logger.warning("第一页重试后仍然没有找到可讲解的商品")
                else:
                    # 输出商品列表
                    self._log(f"商品列表（按编号降序，从大到小）: {[item.get('itemIndex', '无编号') for item in current_items]}")
                    logger.info("商品列表: {}", [item.get('itemIndex', '无编号') for item in current_items])
                
                # 按列表下标从0开始顺序播放
                current_item_index = 0  # 当前播放到列表的哪个位置
                
                # 只有当有商品时才进入处理循环
                if len(current_items) > 0:
                    self._log(f"开始处理第 {current_page_num} 页的商品，共 {len(current_items)} 个商品")
                    logger.info("开始处理第 {} 页的商品，共 {} 个商品", current_page_num, len(current_items))
                    self._log(f"商品列表详情：{[{'编号': item.get('itemIndex', '无编号'), '按钮': item.get('buttonText', ''), '索引': item.get('index', -1)} for item in current_items]}")
                else:
                    self._log(f"⚠️ 第 {current_page_num} 页没有可讲解的商品，跳过处理循环")
                    logger.warning("第 {} 页没有可讲解的商品", current_page_num)
                
                self._log(f"准备进入商品处理循环：current_item_index={current_item_index}, len(current_items)={len(current_items)}, processed_count={processed_count}, goods_count={goods_count}")
                logger.info("准备进入商品处理循环：current_item_index={}, len(current_items)={}, processed_count={}, goods_count={}", current_item_index, len(current_items), processed_count, goods_count)
                
                while current_item_index < len(current_items) and processed_count < goods_count:
                    if self.task_stop_event.is_set():
                                break

                    # 直接按列表下标获取下一个商品
                    self._log(f"从列表中获取商品：current_item_index={current_item_index}, 列表长度={len(current_items)}")
                    next_item = current_items[current_item_index]
                    current_item_index += 1  # 移动到下一个商品

                index = next_item.get("index", 0)
                item_index = next_item.get("itemIndex", "无编号")
                button_text = next_item.get("buttonText", "")
                sku = next_item.get("sku", "")
                
                self._log(f"✓ 获取到商品：准备处理第 {processed_count + 1} 个商品（列表下标 {current_item_index - 1}/{len(current_items)}，商品编号: {item_index}, DOM索引: {index}, SKU: {sku}, 按钮文本: '{button_text}'）")
                logger.info("准备处理商品：列表下标={}/{}, 编号={}, DOM索引={}, SKU={}, 按钮文本={}", current_item_index - 1, len(current_items), item_index, index, sku, button_text)
                
                # 跳过已经处理过的商品
                if sku and sku in processed_skus:
                    self._log(f"跳过商品编号 {item_index} (SKU: {sku})：SKU已在已处理列表中")
                    continue
                
                if index in processed_indices:
                    self._log(f"跳过商品编号 {item_index}：索引已在已处理列表中")
                    continue
                
                # 检查按钮文本
                if button_text.strip() != "讲解":
                    if "取消" in button_text or "结束" in button_text:
                        self._log(f"跳过商品 {index}：按钮文本已改变（'{button_text}'），可能已处理过")
                        processed_indices.add(index)
                        processed_count += 1
                        continue
                    elif "讲解" not in button_text:
                        self._log(f"跳过商品 {index}：按钮文本不是'讲解'（'{button_text}'）")
                        processed_indices.add(index)
                        processed_count += 1
                        continue
                
                # 处理商品（继续使用原有的处理逻辑）
                try:
                    # 先下载图片
                    info = interactor.with_context(
                        lambda ctx, idx=index: ctx.evaluate(
                        """
                        ({ itemSelector, buttonSelector, imageSelector, index }) => {
                            const items = Array.from(document.querySelectorAll(itemSelector));
                            const item = items[index];
                            if (!item) {
                                return null;
                            }
                            
                            // 查找"讲解"按钮 - 尝试多种方式
                            // 注意：要排除下拉菜单的触发按钮（三个点...），只选择文本严格为"讲解"的按钮
                            let button = null;
                            
                            // 辅助函数：检查是否是下拉菜单的触发按钮（三个点）
                            const isDropdownTrigger = (node) => {
                                const text = (node.textContent || '').trim();
                                // 检查是否是三个点或包含下拉菜单相关的类名
                                if (text === '...' || text === '⋯' || text === '⋮' || text.length <= 2) {
                                    return true;
                                }
                                // 检查是否包含下拉菜单相关的类名
                                const className = node.className || '';
                                if (typeof className === 'string') {
                                    if (className.includes('dropdown') || className.includes('more') || 
                                        className.includes('menu') || className.includes('trigger')) {
                                        return true;
                                    }
                                }
                                // 检查父元素是否是下拉菜单
                                let parent = node.parentElement;
                                let checkCount = 0;
                                while (parent && checkCount < 3) {
                                    const parentClass = parent.className || '';
                                    if (typeof parentClass === 'string') {
                                        if (parentClass.includes('dropdown') || parentClass.includes('menu')) {
                                            return true;
                                        }
                                    }
                                    parent = parent.parentElement;
                                    checkCount++;
                                }
                                return false;
                            };
                            
                            // 辅助函数：获取元素的完整文本（包括内部所有子元素的文本）
                            const getFullText = (node) => {
                                if (!node) return '';
                                // 先尝试获取 textContent（包含所有子元素的文本）
                                let text = (node.textContent || '').trim();
                                // 如果 textContent 为空，尝试获取 innerText
                                if (!text) {
                                    text = (node.innerText || '').trim();
                                }
                                // 如果还是为空，尝试查找内部的 span 等元素
                                if (!text) {
                                    const innerSpan = node.querySelector('span');
                                    if (innerSpan) {
                                        text = (innerSpan.textContent || innerSpan.innerText || '').trim();
                                    }
                                }
                                return text;
                            };
                            
                            // 方式1: 查找包含"讲解"文本的span，且类名包含selectBtn
                            // 根据HTML结构：<span class="antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn">讲解</span>
                            const selectBtnSpans = Array.from(item.querySelectorAll('span.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn'));
                            button = selectBtnSpans.find((span) => {
                                const text = getFullText(span);
                                // 严格匹配：文本必须是"讲解"
                                return text === "讲解";
                            });
                            
                            // 方式2: 如果没找到，查找包含"讲解"文本的span，但排除下拉菜单
                            if (!button) {
                                const allSpans = Array.from(item.querySelectorAll('span'));
                                button = allSpans.find((span) => {
                                    const text = getFullText(span);
                                    // 严格匹配：文本必须是"讲解"，不能是下拉菜单触发按钮
                                    return text === "讲解" && !isDropdownTrigger(span);
                                });
                            }
                            
                            // 方式3: 如果还是没找到，在整个item中查找，但排除下拉菜单
                            if (!button) {
                                const allButtons = Array.from(item.querySelectorAll('button, span, div, a'));
                                button = allButtons.find((node) => {
                                    const text = getFullText(node);
                                    // 严格匹配：文本必须是"讲解"，不能是下拉菜单触发按钮
                                    return text === "讲解" && !isDropdownTrigger(node);
                                });
                            }
                            
                            if (!button) {
                                return null;
                            }
                            
                            // 查找图片 - 只选择alt为"商品图"的图片，排除"AI手卡图片"等其他图片
                            let image = null;
                            
                            // 辅助函数：检查图片是否是"AI手卡"图片
                            const isAIShoukaImage = (img) => {
                                const alt = (img.alt || '').trim();
                                const src = (img.src || img.getAttribute('data-src') || '').toLowerCase();
                                const title = (img.title || '').trim();
                                
                                // 检查alt、src、title中是否包含"AI"和"手卡"
                                if (alt.includes('AI') && alt.includes('手卡')) return true;
                                if (src.includes('ai') && (src.includes('shouka') || src.includes('手卡'))) return true;
                                if (title.includes('AI') && title.includes('手卡')) return true;
                                
                                // 检查父元素或兄弟元素的文本中是否包含"AI手卡"
                                let parent = img.parentElement;
                                let checkCount = 0;
                                while (parent && checkCount < 3) {
                                    const parentText = (parent.textContent || '').trim();
                                    if (parentText.includes('AI') && parentText.includes('手卡')) {
                                        return true;
                                    }
                                    parent = parent.parentElement;
                                    checkCount++;
                                }
                                
                                return false;
                            };
                            
                            // 方式1: 使用特定选择器，检查alt是否为"商品图"，且不是"AI手卡"图片
                            image = item.querySelector(imageSelector);
                            if (image && (isAIShoukaImage(image) || (image.alt || '').trim() !== '商品图')) {
                                image = null;
                            }
                            
                            // 方式2: 查找item中所有img，只选择alt为"商品图"的图片，排除"AI手卡"图片
                            if (!image) {
                                const images = Array.from(item.querySelectorAll("img"));
                                image = images.find(img => {
                                    const alt = (img.alt || '').trim();
                                    const src = img.src || img.getAttribute('data-src') || '';
                                    // 必须是"商品图"，且不是"AI手卡"图片
                                    return src && src.trim() !== '' && 
                                           alt === '商品图' && 
                                           !isAIShoukaImage(img);
                                });
                            }
                            
                            // 方式3: 查找button附近的img，只选择alt为"商品图"的图片
                            if (!image && button) {
                                const parent = button.closest("div");
                                if (parent) {
                                    const images = Array.from(parent.querySelectorAll("img"));
                                    image = images.find(img => {
                                        const alt = (img.alt || '').trim();
                                        const src = img.src || img.getAttribute('data-src') || '';
                                        return src && src.trim() !== '' && 
                                               alt === '商品图' && 
                                               !isAIShoukaImage(img);
                                    });
                                }
                            }
                            
                            // 方式4: 如果还是没找到alt为"商品图"的，选择第一个有src的图片（作为后备），但要排除"AI手卡"图片
                            // 注意：如果找不到alt为"商品图"的图片，说明可能没有商品图，不应该使用后备方案
                            // 这样可以避免下载"AI手卡"图片
                            // if (!image) {
                            //     const images = Array.from(item.querySelectorAll("img"));
                            //     image = images.find(img => {
                            //         const src = img.src || img.getAttribute('data-src') || '';
                            //         return src && src.trim() !== '' && !isAIShoukaImage(img);
                            //     });
                            // }
                            
                            // 获取商品标题
                            const titleNode =
                                item.querySelector('[class*="title"]') ||
                                item.querySelector('[class*="name"]') ||
                                item.querySelector('[class*="Title"]') ||
                                item.querySelector('[class*="Name"]') ||
                                item.querySelector('span[title]') ||
                                item.querySelector('div[title]');
                            
                            let titleText = '';
                            if (titleNode) {
                                titleText = titleNode.textContent?.trim() || titleNode.getAttribute('title') || '';
                            }
                            
                            // 如果还是没有标题，尝试查找所有文本节点
                            if (!titleText) {
                                const textNodes = Array.from(item.querySelectorAll('span, div, p'))
                                    .map(node => node.textContent?.trim())
                                    .filter(text => text && text.length > 0 && text !== '讲解');
                                if (textNodes.length > 0) {
                                    titleText = textNodes[0];
                                }
                            }
                            
                            return {
                                imageUrl: image ? image.src : null,
                                imageSrcset: image ? image.srcset : null,
                                imageDataSrc: image ? image.getAttribute('data-src') : null,
                                imageAlt: image ? (image.alt || '') : null,
                                imageTitle: image ? (image.title || '') : null,
                                imageSrc: image ? image.src : null,
                                imageClassName: image ? image.className : null,
                                imageParentText: image && image.parentElement ? (image.parentElement.textContent || '').substring(0, 100) : null,
                                title: titleText || `商品 ${index + 1}`,
                                buttonIndex: index,
                                buttonFound: !!button
                            };
                        }
                        """,
                        {
                            "itemSelector": item_selector,
                            "imageSelector": image_selector,
                            "buttonSelector": button_selector,
                            "index": idx,
                        },
                    )
                )
                except Exception as info_exc:  # noqa: BLE001
                    logger.exception("获取商品信息失败")
                    self._log(f"获取商品信息失败：{info_exc}")
                    processed_indices.add(index)
                    processed_count += 1
                    continue
                except Exception as item_exc:  # noqa: BLE001
                    logger.exception("处理商品时发生异常")
                    self._log(f"处理商品异常：{item_exc}")
                    # 即使发生异常，也标记为已处理，避免重复处理
                    processed_indices.add(index)
                    if sku:
                        processed_skus.add(sku)
                    processed_count += 1
                    continue
                
                # 继续处理商品（这部分代码在 try 块内）
                if not info:
                    self._log(f"未能获取第 {processed_count + 1} 个商品信息，跳过。")
                    processed_count += 1
                    continue

                title = info.get("title", f"商品 {index + 1}")
                self._log(f"获取商品信息：{title}")
                
                # 记录图片详细信息，用于调试
                image_alt = info.get("imageAlt", "")
                image_title = info.get("imageTitle", "")
                image_src = info.get("imageSrc", "")
                image_class_name = info.get("imageClassName", "")
                image_parent_text = info.get("imageParentText", "")
                
                self._log(f"图片详细信息：")
                self._log(f"  - alt: {image_alt}")
                self._log(f"  - title: {image_title}")
                self._log(f"  - src: {image_src}")
                self._log(f"  - className: {image_class_name}")
                self._log(f"  - 父元素文本: {image_parent_text}")
                
                # 尝试多种方式获取图片URL
                image_url = info.get("imageUrl") or info.get("imageDataSrc")
                
                # 如果没有直接URL，尝试从srcset中提取
                if not image_url:
                    srcset = info.get("imageSrcset")
                    if srcset:
                        # srcset格式通常是 "url1 size1, url2 size2"，取第一个URL
                        first_url = srcset.split(',')[0].strip().split()[0]
                        if first_url:
                            image_url = first_url
                
                # 如果还是没有URL，尝试重新查找图片
                if not image_url:
                    self._log("未从商品信息中获取到图片URL，尝试重新查找...")
                    try:
                        image_info = interactor.with_context(
                            lambda ctx, idx=index: ctx.evaluate(
                                """
                                ({ itemSelector, imageSelector, index }) => {
                                    const items = Array.from(document.querySelectorAll(itemSelector));
                                    const item = items[index];
                                    if (!item) {
                                        return null;
                                    }
                                    
                                    // 查找图片 - 只选择alt为"商品图"的图片，排除"AI手卡图片"等其他图片
                                    let image = null;
                                    
                                    // 辅助函数：检查图片是否是"AI手卡"图片
                                    const isAIShoukaImage = (img) => {
                                        const alt = (img.alt || '').trim();
                                        const src = (img.src || img.getAttribute('data-src') || '').toLowerCase();
                                        const title = (img.title || '').trim();
                                        
                                        // 检查alt、src、title中是否包含"AI"和"手卡"
                                        if (alt.includes('AI') && alt.includes('手卡')) return true;
                                        if (src.includes('ai') && (src.includes('shouka') || src.includes('手卡'))) return true;
                                        if (title.includes('AI') && title.includes('手卡')) return true;
                                        
                                        // 检查父元素或兄弟元素的文本中是否包含"AI手卡"
                                        let parent = img.parentElement;
                                        let checkCount = 0;
                                        while (parent && checkCount < 3) {
                                            const parentText = (parent.textContent || '').trim();
                                            if (parentText.includes('AI') && parentText.includes('手卡')) {
                                                return true;
                                            }
                                            parent = parent.parentElement;
                                            checkCount++;
                                        }
                                        
                                        return false;
                                    };
                                    
                                    // 方式1: 使用特定选择器，检查alt是否为"商品图"，且不是"AI手卡"图片
                                    image = item.querySelector(imageSelector);
                                    if (image && (isAIShoukaImage(image) || (image.alt || '').trim() !== '商品图')) {
                                        image = null;
                                    }
                                    
                                    // 方式2: 查找item中所有img，只选择alt为"商品图"的图片，排除"AI手卡"图片
                                    if (!image) {
                                        const images = Array.from(item.querySelectorAll("img"));
                                        image = images.find(img => {
                                            const alt = (img.alt || '').trim();
                                            const src = img.src || img.getAttribute('data-src') || '';
                                            // 必须是"商品图"，且不是"AI手卡"图片
                                            return src && src.trim() !== '' && 
                                                   alt === '商品图' && 
                                                   !isAIShoukaImage(img);
                                        });
                                    }
                                    
                                    // 方式3: 如果还是没找到alt为"商品图"的，选择第一个有src的图片（作为后备），但要排除"AI手卡"图片
                                    // 注意：如果找不到alt为"商品图"的图片，说明可能没有商品图，不应该使用后备方案
                                    // 这样可以避免下载"AI手卡"图片
                                    // if (!image) {
                                    //     const images = Array.from(item.querySelectorAll("img"));
                                    //     image = images.find(img => {
                                    //         const src = img.src || img.getAttribute('data-src') || '';
                                    //         return src && src.trim() !== '' && !isAIShoukaImage(img);
                                    //     });
                                    // }
                                    
                                    return {
                                        imageUrl: image ? image.src : null,
                                        imageSrcset: image ? image.srcset : null,
                                        imageDataSrc: image ? image.getAttribute('data-src') : null,
                                        imageAlt: image ? (image.alt || '') : null,
                                        imageTitle: image ? (image.title || '') : null,
                                        imageSrc: image ? image.src : null,
                                        imageClassName: image ? image.className : null,
                                        imageParentText: image && image.parentElement ? (image.parentElement.textContent || '').substring(0, 100) : null
                                    };
                                }
                                """,
                                {
                                    "itemSelector": item_selector,
                                    "imageSelector": image_selector,
                                    "index": idx,
                                },
                                ),
                            )
                            
                        if image_info:
                            image_url = image_info.get("imageUrl") or image_info.get("imageDataSrc")
                            if not image_url and image_info.get("imageSrcset"):
                                srcset = image_info.get("imageSrcset")
                                first_url = srcset.split(',')[0].strip().split()[0]
                                if first_url:
                                    image_url = first_url
                            
                            # 记录重新查找的图片信息
                            if image_info.get("imageAlt"):
                                self._log(f"重新查找的图片alt: {image_info.get('imageAlt')}")
                            if image_info.get("imageParentText"):
                                self._log(f"重新查找的图片父元素文本: {image_info.get('imageParentText')}")
                    except Exception as img_exc:  # noqa: BLE001
                        logger.exception("重新查找图片时发生异常")
                        self._log(f"重新查找图片异常：{img_exc}")

                if not image_url:
                    self._log(f"[{processed_count + 1}/{goods_count}] 未获取到图片URL，跳过下载。")
                    self._log(f"图片信息：alt={image_alt}, title={image_title}, src={image_src}")
                    processed_count += 1
                    continue
                
                # 处理相对URL
                if not urlparse(image_url).netloc:
                    # 获取当前页面URL作为基础URL
                    base_url = interactor.with_context(lambda ctx: ctx.url, require_selector=False) or "https://live.jd.com"
                    image_url = urljoin(base_url, image_url)
                
                # 检查图片URL和alt属性，排除"AI手卡图片"等非商品图片
                image_alt_check = info.get("imageAlt", "")
                if image_alt_check:
                    self._log(f"图片alt属性: {image_alt_check}")
                    if 'AI' in image_alt_check and '手卡' in image_alt_check:
                        self._log(f"警告：图片alt同时包含'AI'和'手卡'关键词，跳过下载：{image_alt_check}")
                        processed_count += 1
                        continue
                
                # 检查图片URL是否包含"AI"或"手卡"等关键词
                if 'AI' in image_url.upper() and ('手卡' in image_url or 'shouka' in image_url.lower() or 'aishouka' in image_url.lower()):
                    self._log(f"警告：图片URL同时包含'AI'和'手卡'关键词，跳过下载：{image_url}")
                    processed_count += 1
                    continue
                
                # 检查父元素文本
                if image_parent_text and 'AI' in image_parent_text and '手卡' in image_parent_text:
                    self._log(f"警告：图片父元素文本同时包含'AI'和'手卡'关键词，跳过下载：{image_parent_text}")
                    processed_count += 1
                    continue
                
                # 使用固定文件名 1.jpg，后面的图片会覆盖前面的
                destination = directory / "1.jpg"
                
                self._log(f"[{processed_count + 1}/{goods_count}] 开始下载图片：{title}")
                self._log(f"图片URL: {image_url}")
                self._log(f"保存路径: {destination}")
                if not self._download_image(image_url, destination):
                    self._log(f"下载失败，跳过讲解：{title}")
                    processed_count += 1
                    continue
                self._log("下载完成。")

                # 使用JavaScript查找并点击"讲解"按钮
                self._log(f"开始查找并点击讲解按钮（商品编号: {item_index}, DOM索引: {index}）...")
                logger.info("开始查找并点击讲解按钮：商品编号={}, DOM索引={}", item_index, index)
                clicked = False
                try:
                    clicked = interactor.with_context(
                        lambda ctx, idx=index: ctx.evaluate(
                            """
                            ({ itemSelector, buttonSelector, index }) => {
                                const items = Array.from(document.querySelectorAll(itemSelector));
                                const item = items[index];
                                if (!item) {
                                    return false;
                                }
                                
                                const isDropdownTrigger = (node) => {
                                    if (!node) return false;
                                    const text = (node.textContent || '').trim();
                                    if (text === '...' || text === '⋯' || text === '⋮' || (text.length <= 2 && text !== '讲解')) {
                                        return true;
                                    }
                                    const className = node.className || '';
                                    if (typeof className === 'string') {
                                        const lower = className.toLowerCase();
                                        if (lower.includes('dropdown') || lower.includes('more') || lower.includes('trigger')) {
                                            return true;
                                        }
                                    }
                                    let parent = node.parentElement;
                                    let depth = 0;
                                    while (parent && depth < 3) {
                                        const parentClass = parent.className || '';
                                        if (typeof parentClass === 'string') {
                                            const lower = parentClass.toLowerCase();
                                            if (lower.includes('dropdown') || lower.includes('menu')) {
                                                return true;
                                            }
                                        }
                                        parent = parent.parentElement;
                                        depth++;
                                    }
                                    return false;
                                };
                                
                                const getFullText = (node) => {
                                    if (!node) return '';
                                    let text = (node.textContent || '').trim();
                                    if (!text) {
                                        text = (node.innerText || '').trim();
                                    }
                                    if (!text) {
                                        const span = node.querySelector('span');
                                        if (span) {
                                            text = (span.textContent || span.innerText || '').trim();
                                        }
                                    }
                                    return text;
                                };
                                
                                let button = null;
                                
                                if (buttonSelector) {
                                    const buttons = Array.from(item.querySelectorAll(buttonSelector));
                                    button = buttons.find((node) => getFullText(node) === '讲解');
                                }
                                
                                if (!button) {
                                    const candidates = Array.from(item.querySelectorAll('button, span, div, a'));
                                    button = candidates.find((node) => getFullText(node) === '讲解' && !isDropdownTrigger(node));
                                }
                                
                                if (!button) {
                                    return false;
                                }
                                
                                try {
                                    button.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                } catch (e) {}
                                
                                try {
                                    button.click();
                                    return true;
                                } catch (e) {
                                    try {
                                        const clickEvent = new MouseEvent('click', {
                                            bubbles: true,
                                            cancelable: true,
                                            view: window,
                                        });
                                        button.dispatchEvent(clickEvent);
                                        return true;
                                    } catch (e2) {
                                        return false;
                                    }
                                }
                            }
                            """,
                            {
                                "itemSelector": item_selector,
                                "buttonSelector": button_selector,
                                "index": index,
                            },
                        ),
                        require_selector=False,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("点击讲解按钮时发生异常")
                    self._log(f"点击按钮异常：{exc}")
                    clicked = False

                if not clicked:
                    self._log(f"❌ 未找到第 {processed_count + 1} 个商品的讲解按钮（商品编号: {item_index}, DOM索引: {index}），跳过。")
                    logger.warning("未找到讲解按钮：商品编号={}, DOM索引={}", item_index, index)
                    processed_indices.add(index)
                    if sku:
                        processed_skus.add(sku)
                    processed_count += 1
                    continue

                self._log(f"✓✓✓ 已点击讲解按钮：{title}（商品编号: {item_index}, DOM索引: {index}）")
                logger.info("已点击讲解按钮：{}, 商品编号={}, DOM索引={}", title, item_index, index)
                
                # 每次点击讲解按钮后都检查并处理确认弹窗（"该商品已关联/已上传讲解"等提示）
                try:
                    self._log("检查是否需要确认（每次点击后都检查）...")
                    # 等待模态框出现（最多等待3秒）
                    modal_confirmed = False
                    for wait_attempt in range(30):  # 30次，每次100ms，共3秒
                        if self.task_stop_event.is_set():
                            break
                        try:
                            modal_confirmed = interactor.with_context(
                                    lambda ctx: ctx.evaluate(
                                        """
                                        () => {
                                            // 查找确认模态框/弹出框
                                            // 优先在 ant-popover 中查找
                                            const popover = document.querySelector('.ant-popover');
                                            if (popover) {
                                                    // 检查是否包含"该商品已关联"或"已上传讲解"或"覆盖已有切片"等关键词
                                                    const popoverText = popover.textContent || '';
                                                    const hasConfirmMessage = popoverText.includes('该商品已关联') || 
                                                                              popoverText.includes('已上传讲解') || 
                                                                              popoverText.includes('覆盖已有切片') ||
                                                                              popoverText.includes('确定讲解吗');
                                                    
                                                    if (hasConfirmMessage) {
                                                        const popoverButtons = Array.from(popover.querySelectorAll('button'));
                                                        const confirmButton = popoverButtons.find((node) => {
                                                            // 获取按钮文本（包括内部span的文本）
                                                            const text = (node.textContent || '').trim().replace(/[\\s]+/g, '');
                                                            // 查找包含"确定"且是 primary 类型的按钮
                                                            return (text === "确定" || text.includes("确定")) && 
                                                                   node.classList.contains('ant-btn-primary');
                                                        });
                                                        
                                                        if (confirmButton) {
                                                            // 滚动到按钮位置
                                                            confirmButton.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                                            // 等待一下
                                                            const startTime = Date.now();
                                                            while (Date.now() - startTime < 200) {}
                                                            
                                                            // 点击确定按钮
                                                            try {
                                                                confirmButton.click();
                                                                return true;
                                                            } catch (e) {
                                                                try {
                                                                    const clickEvent = new MouseEvent('click', {
                                                                        bubbles: true,
                                                                        cancelable: true,
                                                                        view: window
                                                                    });
                                                                    confirmButton.dispatchEvent(clickEvent);
                                                                    return true;
                                                                } catch (e2) {
                                                                    return false;
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            
                                            // 如果没找到popover，尝试查找所有包含"确定"的primary按钮
                                            const allButtons = Array.from(document.querySelectorAll('button.ant-btn-primary'));
                                            const confirmButton = allButtons.find((node) => {
                                                const text = (node.textContent || '').trim().replace(/\\s+/g, '');
                                                return text === "确定" || text.includes("确定");
                                            });
                                            
                                            if (confirmButton) {
                                                // 检查按钮附近是否有确认消息
                                                const parent = confirmButton.closest('.ant-popover');
                                                if (parent) {
                                                    const parentText = parent.textContent || '';
                                                    const hasConfirmMessage = parentText.includes('该商品已关联') || 
                                                                              parentText.includes('已上传讲解') || 
                                                                              parentText.includes('覆盖已有切片') ||
                                                                              parentText.includes('确定讲解吗');
                                                    if (hasConfirmMessage) {
                                                        confirmButton.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                                        const startTime = Date.now();
                                                        while (Date.now() - startTime < 200) {}
                                                        
                                                        try {
                                                            confirmButton.click();
                                                            return true;
                                                        } catch (e) {
                                                            try {
                                                                const clickEvent = new MouseEvent('click', {
                                                                    bubbles: true,
                                                                    cancelable: true,
                                                                    view: window
                                                                });
                                                                confirmButton.dispatchEvent(clickEvent);
                                                                return true;
                                                            } catch (e2) {
                                                                return false;
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                            
                                            return false;
                                        }
                                        """
                                    ),
                                require_selector=False,
                            )
                            if modal_confirmed:
                                self._log("✓ 已点击确认按钮（处理'该商品已关联/已上传讲解'提示）")
                                logger.info("已点击确认按钮，处理确认弹窗")
                                # 等待模态框关闭
                                time.sleep(0.5)
                                break
                        except Exception:
                            pass
                        time.sleep(0.1)
                    
                    if not modal_confirmed:
                        self._log("未检测到确认模态框（这是正常的，不是所有商品都需要确认）")
                except Exception as modal_exc:  # noqa: BLE001
                    logger.exception("处理确认模态框时发生异常")
                    self._log(f"处理确认模态框异常：{modal_exc}")
                
                # 点击"讲解"后，页面可能会重新加载，需要等待页面完全加载
                self._log("等待页面重新加载（点击讲解后）...")
                try:
                    # 等待页面加载完成（如果页面重新加载了）
                    interactor.with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000), require_selector=False)
                    self._log("页面加载完成")
                except Exception:
                    self._log("页面可能没有重新加载，继续等待...")
                
                # 等待商品列表重新渲染
                self._log("等待商品列表重新渲染...")
                time.sleep(3)  # 等待3秒，确保React应用完全渲染
                
                # 再次等待网络空闲，确保所有资源加载完成
                try:
                    interactor.with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=10000), require_selector=False)
                    time.sleep(1)  # 额外等待1秒
                except Exception:
                    pass
                
                self._log("页面状态已稳定，开始讲解")
                self._log(f"开始讲解：{title}")
                
                # 等待讲解时间：与页面显示的"讲解中"计时同步
                self._log(f"开始监控页面讲解时长，目标 {duration} 秒")
                start_time = time.time()
                last_timer_text: Optional[str] = None
                timer_not_found_logged = False
                while not self.task_stop_event.is_set():
                    elapsed = time.time() - start_time
                    reached = False
                    timer_info = None
                    try:
                        timer_info = interactor.with_context(
                            lambda ctx, idx=index: ctx.evaluate(
                                """
                                ({ itemSelector, index }) => {
                                    const items = Array.from(document.querySelectorAll(itemSelector));
                                    const item = items[index];
                                    if (!item) {
                                        return null;
                                    }
                                    const timerNode = item.querySelector('.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-newExplain');
                                    if (!timerNode) {
                                        return { text: null, seconds: null };
                                    }
                                    const rawText = (timerNode.textContent || '').trim();
                                    const match = rawText.match(/(\\d{1,2}:\\d{2})$/);
                                    if (!match) {
                                        return { text: rawText || null, seconds: null };
                                    }
                                    const timeText = match[1];
                                    const parts = timeText.split(':');
                                    const minutes = parseInt(parts[0], 10);
                                    const seconds = parseInt(parts[1], 10);
                                    if (Number.isNaN(minutes) || Number.isNaN(seconds)) {
                                        return { text: timeText, seconds: null };
                                    }
                                    return {
                                        text: timeText,
                                        seconds: minutes * 60 + seconds,
                                    };
                                }
                                """,
                                {
                                    "itemSelector": item_selector,
                                    "index": index,
                                },
                            ),
                            require_selector=False,
                        )
                    except Exception as timer_exc:  # noqa: BLE001
                        logger.debug("获取页面讲解计时器失败: {}", timer_exc)
                        timer_info = None
                    
                    if timer_info and timer_info.get("seconds") is not None:
                        current_seconds = timer_info["seconds"]
                        timer_text = timer_info.get("text") or ""
                        if timer_text and timer_text != last_timer_text:
                            self._log(f"页面讲解计时：{timer_text}（{current_seconds} 秒）")
                            last_timer_text = timer_text
                        if current_seconds >= duration:
                            self._log(f"页面讲解计时达到目标 {duration} 秒（当前 {timer_text}），准备停止当前讲解")
                            reached = True
                    else:
                        if not timer_not_found_logged:
                            self._log("未检测到页面讲解计时器，使用本地计时作为兜底")
                            timer_not_found_logged = True
                        if elapsed >= duration:
                            self._log(f"本地计时达到 {duration} 秒，页面未提供有效计时，准备停止当前讲解")
                            reached = True
                    
                    if reached:
                        break
                    
                    if elapsed >= duration * 2:
                        self._log(f"页面计时迟迟未达到目标，已等待 {elapsed:.1f} 秒，安全停止当前讲解")
                        break
                    
                    if self.task_stop_event.wait(1):
                        break
                
                # 在开始下一个商品之前，先停止当前讲解
                self._log(f"讲解时间到，准备停止当前讲解：{title}")
                try:
                    # 先等待一下，确保页面有时间更新显示停止按钮
                    time.sleep(0.5)
                    
                    # 使用 Playwright 的方式查找和点击停止按钮
                    stopped = False
                    max_attempts = 20  # 增加尝试次数到20次
                    
                    for stop_attempt in range(max_attempts):
                        if self.task_stop_event.is_set():
                            break
                        try:
                            # 尝试使用 Playwright 选择器查找停止按钮
                            def try_click_stop_button(page: Page) -> tuple[bool, str]:
                                """尝试点击停止按钮，返回(是否成功, 调试信息)"""
                                debug_msgs = []
                                
                                # 获取当前商品项
                                try:
                                    items = page.query_selector_all(item_selector)
                                    if index < len(items):
                                        current_item = items[index]
                                        debug_msgs.append(f"找到当前商品项（索引 {index}）")
                                        
                                        # 方式1: 在当前商品项内查找"结束"按钮（包含selectBtn和hover类）
                                        try:
                                            # 先查找包含这两个类的span
                                            candidate_spans = current_item.query_selector_all(
                                                'span.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-hover'
                                            )
                                            for span in candidate_spans:
                                                text = span.inner_text().strip() if hasattr(span, 'inner_text') else (span.evaluate('el => el.textContent') or '').strip()
                                                if text == '结束':
                                                    debug_msgs.append("方式1: 在当前商品项内找到停止按钮（selectBtn+hover）")
                                                    span.scroll_into_view_if_needed()
                                                    span.click(timeout=1000)
                                                    return True, " | ".join(debug_msgs)
                                        except Exception:
                                            pass
                                        
                                        # 方式2: 在当前商品项内查找包含"结束"文本的span
                                        try:
                                            all_spans = current_item.query_selector_all('span')
                                            for span in all_spans:
                                                text = span.inner_text().strip() if hasattr(span, 'inner_text') else (span.evaluate('el => el.textContent') or '').strip()
                                                if text == '结束':
                                                    debug_msgs.append("方式2: 在当前商品项内找到'结束'文本的span")
                                                    span.scroll_into_view_if_needed()
                                                    span.click(timeout=1000)
                                                    return True, " | ".join(debug_msgs)
                                        except Exception:
                                            pass
                                except Exception as e:
                                    debug_msgs.append(f"获取商品项失败: {e}")
                                
                                # 方式3: 在整个页面查找包含"结束"文本的可见按钮
                                try:
                                    # 查找所有包含"结束"的span
                                    all_spans = page.query_selector_all('span')
                                    for span in all_spans:
                                        try:
                                            text = span.inner_text().strip() if hasattr(span, 'inner_text') else (span.evaluate('el => el.textContent') or '').strip()
                                            if text == '结束':
                                                # 检查是否可见
                                                is_visible = span.evaluate('el => { const rect = el.getBoundingClientRect(); return rect.width > 0 && rect.height > 0; }')
                                                if is_visible:
                                                    debug_msgs.append("方式3: 在页面中找到可见的'结束'按钮")
                                                    span.scroll_into_view_if_needed()
                                                    span.click(timeout=1000)
                                                    return True, " | ".join(debug_msgs)
                                        except Exception:
                                            continue
                                except Exception:
                                    pass
                                
                                # 方式4: 使用JavaScript查找和点击
                                try:
                                    result = page.evaluate("""
                                        ([itemSelector, itemIndex]) => {
                                            // 获取当前商品项
                                            const items = Array.from(document.querySelectorAll(itemSelector));
                                            const currentItem = items[itemIndex];
                                        
                                            // 优先在当前商品项内查找
                                            if (currentItem) {
                                                const itemSpans = Array.from(currentItem.querySelectorAll('span'));
                                                for (const span of itemSpans) {
                                                const text = (span.textContent || '').trim();
                                                if (text === '结束') {
                                                        const rect = span.getBoundingClientRect();
                                                        if (rect.width > 0 && rect.height > 0) {
                                                            span.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                                            setTimeout(() => span.click(), 100);
                                                            return { success: true, method: 'currentItem' };
                                                    }
                                                }
                                                }
                                        }
                                        
                                            // 在整个页面查找
                                            const allSpans = Array.from(document.querySelectorAll('span'));
                                            for (const span of allSpans) {
                                                const text = (span.textContent || '').trim();
                                                if (text === '结束') {
                                                    const rect = span.getBoundingClientRect();
                                                    if (rect.width > 0 && rect.height > 0) {
                                                        span.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                                        setTimeout(() => span.click(), 100);
                                                        return { success: true, method: 'page' };
                                                    }
                                                }
                                            }
                                            
                                            return { success: false, error: '未找到停止按钮' };
                                        }
                                    """, [item_selector, index])
                                    
                                    if result and result.get("success"):
                                        debug_msgs.append(f"方式4: JavaScript找到并点击停止按钮（方法: {result.get('method')}）")
                                        return True, " | ".join(debug_msgs)
                                except Exception as e:
                                    debug_msgs.append(f"JavaScript查找失败: {e}")
                                
                                return False, " | ".join(debug_msgs) if debug_msgs else "未找到停止按钮"
                            
                            success, debug_msg = interactor.with_context(try_click_stop_button, require_selector=False)
                            
                            if success:
                                self._log(f"✓ 已点击停止按钮（尝试 {stop_attempt + 1}/{max_attempts}）")
                                self._log(f"  调试信息: {debug_msg}")
                                stopped = True
                                time.sleep(2)  # 等待停止操作完成
                                break
                            else:
                                # 记录调试信息
                                if stop_attempt == 0 or stop_attempt % 5 == 0:  # 每5次尝试记录一次
                                    self._log(f"查找停止按钮（尝试 {stop_attempt + 1}/{max_attempts}）: {debug_msg}")
                                    
                                # 额外记录页面状态
                                try:
                                    page_info = interactor.with_context(
                                        lambda ctx: ctx.evaluate("""
                                            () => {
                                                const allSpans = Array.from(document.querySelectorAll('span'));
                                                const endButtons = allSpans.filter(s => (s.textContent || '').trim() === '结束');
                                                return {
                                                    totalEndButtons: endButtons.length,
                                                    visibleEndButtons: endButtons.filter(s => {
                                                        const rect = s.getBoundingClientRect();
                                                        return rect.width > 0 && rect.height > 0;
                                                    }).length
                                                };
                                            }
                                            """),
                                        require_selector=False
                                    )
                                    if page_info:
                                        self._log(f"  页面状态: 共找到 {page_info.get('totalEndButtons', 0)} 个'结束'按钮，其中 {page_info.get('visibleEndButtons', 0)} 个可见")
                                except Exception:
                                    pass
                                    
                        except Exception as e:  # noqa: BLE001
                            if stop_attempt == 0 or stop_attempt % 5 == 0:
                                logger.debug("查找停止按钮异常（尝试 {}）: {}", stop_attempt + 1, e)
                                self._log(f"查找停止按钮异常（尝试 {stop_attempt + 1}/{max_attempts}）: {e}")
                        time.sleep(0.4)  # 等待间隔
                    
                    if not stopped:
                        self._log(f"⚠️ 警告: 未找到停止按钮（已尝试 {max_attempts} 次），可能页面结构已变化或按钮未显示")
                        logger.warning("未找到停止按钮，商品: {}", title)
                except Exception as stop_exc:  # noqa: BLE001
                    logger.exception("停止讲解时发生异常")
                    self._log(f"停止讲解异常：{stop_exc}")
                    
                self._log(f"讲解结束：{title}")
                
                # 停止后，页面可能会重新加载，需要等待页面完全加载
                self._log("等待页面重新加载...")
                try:
                    # 等待页面加载完成（如果页面重新加载了）
                    interactor.with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000), require_selector=False)
                    self._log("页面加载完成")
                except Exception:
                    self._log("页面可能没有重新加载，继续等待...")
                
                # 等待页面完全稳定，确保商品列表重新渲染
                self._log("等待商品列表重新渲染...")
                time.sleep(3)  # 等待3秒，确保React应用完全渲染
                
                # 再次等待网络空闲，确保所有资源加载完成
                try:
                    interactor.with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=10000), require_selector=False)
                    time.sleep(1)  # 额外等待1秒
                except Exception:
                    pass
                
                self._log("页面状态已稳定，准备处理下一个商品")
                
                # 处理完成后，将索引和SKU添加到已处理列表
                processed_indices.add(index)
                if sku:
                    processed_skus.add(sku)
                last_processed_index = index  # 记录本次处理的索引
                last_processed_sku = sku  # 记录本次处理的SKU
                self._log(f"已标记商品为已处理：索引={index}, SKU={sku}, 编号={item_index}，已处理列表大小：索引={len(processed_indices)}, SKU={len(processed_skus)}")
                logger.info("已标记商品为已处理：索引={}, SKU={}, 编号={}，已处理列表大小：索引={}, SKU={}", index, sku, item_index, len(processed_indices), len(processed_skus))
                # 记录本次处理的商品编号（itemIndex）
                try:
                    if item_index is not None and item_index != "无编号":
                        # 尝试转换为数字以便后续比较
                        if isinstance(item_index, str):
                            try:
                                last_processed_item_index = int(item_index)
                            except ValueError:
                                last_processed_item_index = item_index
                        else:
                            last_processed_item_index = int(item_index)
                        self._log(f"已记录商品编号: {last_processed_item_index}")
                        logger.info("已记录商品编号: {}", last_processed_item_index)
                        
                    else:
                        self._log("商品编号为空或无效，无法记录")
                        logger.info("商品编号为空或无效，无法记录")
                except Exception as e:
                    logger.debug("记录商品编号时发生异常: {}", e)
                    last_processed_item_index = None
                
                self._log(f"已记录商品（索引: {index}, SKU: {sku}, 编号: {last_processed_item_index}）到已处理列表（处理完成）")
                logger.info("已记录商品（索引: {}, SKU: {}, 编号: {}）到已处理列表（处理完成）", index, sku, last_processed_item_index)
                
                processed_count += 1

                # 如果还有商品未处理，等待间隔时间
                if processed_count < goods_count and interval > 0:
                    self._log(f"等待 {interval} 秒准备下一场。")
                    if self.task_stop_event.wait(interval):
                        break
                    
                    # 间隔等待后，再次确保页面稳定
                    try:
                        interactor.with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=5000), require_selector=False)
                        time.sleep(1)  # 增加等待时间，确保页面状态更新
                    except Exception:
                        pass
                
                    # 重要：在下次循环开始前，再次等待一下，确保页面状态完全更新
                    # 这样重新查询商品列表时，第一个商品的状态应该已经更新（不再是"讲解"）
                    time.sleep(0.5)
            
            # 当前页处理完成，尝试翻到下一页继续处理
            
            # 当前页处理完成，尝试翻到下一页继续处理
                # 如果是第一页且没有处理任何商品，记录警告并阻止翻页
                if current_page_num == 1 and processed_count == 0:
                        if len(current_items) == 0:
                            self._log("⚠️ 警告：第一页没有找到任何可讲解的商品，请检查第一页是否确实有商品")
                            logger.warning("第一页没有找到任何可讲解的商品")
                            # 如果是第一页且没有商品，不应该翻页，应该结束任务
                            self._log("第一页没有商品，停止处理")
                            break
                        else:
                            self._log("⚠️ 警告：第一页有商品但未处理任何商品，可能是处理逻辑有问题")
                            logger.warning("第一页有商品但未处理任何商品")
                            # 即使有商品但没处理，也不应该翻页，应该继续尝试处理
                            self._log("继续尝试处理第一页的商品...")
                            continue
                
                if current_page_num < total_pages:
                    success, new_page = self._navigate_to_next_page(interactor, current_page_num, total_pages)
                    if success:
                        current_page_num = new_page
                    # 重置当前页的处理状态
                    processed_indices.clear()
                    processed_skus.clear()
                    last_processed_index = -1
                    last_processed_sku = None
                        # 重新获取商品列表，继续处理（继续外层循环）
                    continue
                else:
                    self._log("下一页按钮不可用，已处理完所有页面。")
                    logger.info("下一页按钮不可用，已处理完所有页面")
            else:
                self._log(f"已处理完最后一页（第 {total_pages} 页），所有页面处理完成。")
                logger.info("已处理完最后一页（第 {} 页），所有页面处理完成", total_pages)

            if self.task_stop_event.is_set():
                self._log("自动讲解任务已被手动停止。")
            else:
                self._log("自动讲解任务已完成。")
        finally:
            controller.disconnect()
            self.task_thread = None
            self.task_stop_event.clear()
            self.after(0, lambda: self._set_task_running(False))

    def _download_image(self, url: str, destination: Path) -> bool:
        try:
            # 清理URL，移除可能的查询参数和片段
            clean_url = url.split('?')[0].split('#')[0]
            
            # 设置更完整的请求头，模拟浏览器
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://live.jd.com/",
            }
            
            request = Request(clean_url, headers=headers)
            with urlopen(request, timeout=30) as response:
                # 检查响应状态
                if response.status != 200:
                    self._log(f"下载图片失败：HTTP状态码 {response.status}")
                    return False
                
                # 检查内容类型
                content_type = response.headers.get("Content-Type", "").lower()
                if not content_type.startswith("image/"):
                    self._log(f"警告：响应不是图片类型，Content-Type: {content_type}")
                    # 继续尝试下载，因为某些服务器可能不返回正确的Content-Type
                
                data = response.read()
                
                # 验证数据不为空
                if not data or len(data) < 100:  # 至少100字节
                    self._log("下载的图片数据为空或过小")
                    return False
                    
        except URLError as exc:
            logger.exception("下载图片失败")
            self._log(f"下载图片失败：{exc}")
            return False
        except Exception as exc:  # noqa: BLE001
            logger.exception("下载图片时发生异常")
            self._log(f"下载图片异常：{exc}")
            return False

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as file_handle:
                file_handle.write(data)
            self._log(f"图片已保存到：{destination}")
        except OSError as exc:
            logger.exception("保存图片失败")
            self._log(f"保存图片失败：{exc}")
            return False

        return True

    def _on_browse_license_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="选择卡密文件",
            filetypes=[("文本文件", "*.txt *.key *.lic"), ("所有文件", "*.*")],
        )
        if not file_path:
            return
        try:
            content = Path(file_path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            messagebox.showerror("读取失败", f"无法读取文件：{exc}")
            return
        if not content:
            messagebox.showwarning("内容为空", "所选文件未包含卡密内容。")
            return
        self.license_var.set(content)
        self._log(f"已从文件加载卡密：{file_path}")

    def _on_save_config(self) -> None:
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("输入错误", "端口必须为整数。")
            return

        duration = self._parse_positive_float(self.duration_var, "讲解时间")
        if duration is None:
            return
        interval = self._parse_positive_float(self.interval_var, "间隔延时", allow_zero=True)
        if interval is None:
            return

        self.config["app"]["default_port"] = port
        self.config["task"]["duration_seconds"] = duration
        self.config["task"]["interval_seconds"] = interval
        self.material_config["directory"] = self.material_path_var.get().strip()
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

    def _set_task_running(self, running: bool) -> None:
        self.is_task_running = running
        if running:
            self.start_task_btn.configure(state=tk.DISABLED)
            self.stop_task_btn.configure(state=tk.NORMAL)
        else:
            start_state = tk.NORMAL if self.controls_enabled else tk.DISABLED
            self.start_task_btn.configure(state=start_state)
            self.stop_task_btn.configure(state=tk.DISABLED)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.controls_enabled = enabled
        state = tk.NORMAL if enabled else tk.DISABLED
        for widget in self.control_widgets:
            try:
                widget.configure(state=state)
            except tk.TclError:
                continue
        if enabled and not self.is_task_running:
            self.start_task_btn.configure(state=tk.NORMAL)
        if not enabled:
            self.start_task_btn.configure(state=tk.DISABLED)
        if self.is_task_running:
            self.stop_task_btn.configure(state=tk.NORMAL)
        else:
            self.stop_task_btn.configure(state=tk.DISABLED)

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
            self.task_stop_event.set()
            if self.task_thread and self.task_thread.is_alive():
                self.task_thread.join(timeout=5)
            self.scheduler.shutdown()
            self.hotkeys.clear()
            if self.controller.is_connected:
                try:
                    self.controller.disconnect()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("关闭窗口时断开浏览器连接失败: {}", exc)
            self.destroy()


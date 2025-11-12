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
from JD_Live_Assistant.core.config import ConfigManager
from JD_Live_Assistant.core.hotkeys import HotkeyManager
from JD_Live_Assistant.core.license import LicenseError, LicenseManager
from JD_Live_Assistant.core.schedule import ScheduleManager


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

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.control_widgets: List[tk.Widget] = []
        self.task_thread: Optional[threading.Thread] = None
        self.task_stop_event = threading.Event()
        self.is_task_running = False
        self.controls_enabled = True

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
        task_config = self.config.setdefault(
            "task",
            {
                "duration_seconds": 8,
                "interval_seconds": 2,
                "material_path": "",
            },
        )
        self.duration_var = tk.StringVar(value=str(task_config.get("duration_seconds", 8)))
        self.interval_var = tk.StringVar(value=str(task_config.get("interval_seconds", 2)))
        self.material_path_var = tk.StringVar(value=task_config.get("material_path", ""))  # type: ignore[arg-type]
        self.license_var = tk.StringVar(value=license_info.key if license_info else "")
        self.license_status_var = tk.StringVar(value="未授权，功能已锁定")
        self.hotkey_summary_var = tk.StringVar(value="")

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

        ttk.Label(task_frame, text="卡点素材路径").grid(row=1, column=0, sticky=tk.E, pady=(12, 0))
        material_entry = ttk.Entry(task_frame, textvariable=self.material_path_var)
        material_entry.grid(row=1, column=1, columnspan=5, sticky=tk.EW, padx=(8, 16), pady=(12, 0))

        browse_material_btn = ttk.Button(task_frame, text="浏览", command=self._on_browse_material)
        browse_material_btn.grid(row=1, column=6, sticky=tk.W, pady=(12, 0))

        button_column = ttk.Frame(task_frame)
        button_column.grid(row=0, column=7, rowspan=2, sticky="ns", padx=(16, 0))

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
                material_entry,
                browse_material_btn,
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

        material_path = self.material_path_var.get().strip()
        if not material_path:
            messagebox.showwarning("缺少素材", "请先选择卡点素材路径。")
            return

        directory = Path(material_path).expanduser().resolve()
        if not directory.is_dir():
            messagebox.showerror("路径无效", "请选择有效的素材文件夹。")
            return

        if not self.controller.is_connected:
            proceed = messagebox.askyesno("未绑定浏览器", "当前未绑定浏览器，是否仅记录日志继续执行？")
            if not proceed:
                return

        task_config = self.config.setdefault("task", {})
        task_config["duration_seconds"] = duration
        task_config["interval_seconds"] = interval
        task_config["material_path"] = str(directory)

        self.task_stop_event.clear()
        try:
            port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("输入错误", "端口必须为整数。")
            return

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

    def _task_worker(self, directory: Path, duration: float, interval: float, port: int) -> None:
        controller = BrowserController()
        # 商品项选择器 - 使用更通用的选择器策略
        item_selector = "div.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-wrapper"
        # 图片选择器 - 优先使用特定类名，如果没有则回退到通用img
        image_selector = "img.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-img"
        # 按钮选择器 - 查找包含"讲解"文本的按钮
        button_selector = ".antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn"

        try:
            try:
                controller.connect(port)
                self._log(f"任务线程已连接浏览器：端口 {port}")
            except Exception as exc:  # noqa: BLE001
                logger.exception("任务线程连接浏览器失败")
                self._log(f"任务启动失败：{exc}")
                self.after(0, lambda e=exc: messagebox.showerror("执行失败", str(e)))
                return

            def with_context(callback: Callable[[Page], Optional[Any]], require_selector: bool = True) -> Optional[Any]:
                def run(page: Page) -> Optional[Any]:
                    # 先尝试主页面
                    try:
                        # 等待页面加载完成
                        page.wait_for_load_state("networkidle", timeout=10000)
                        if require_selector:
                            page.wait_for_selector(item_selector, timeout=10000)
                        return callback(page)
                    except Exception:
                        if not require_selector:
                            # 如果不需要选择器，直接返回主页面
                            return callback(page)
                        pass
                    
                    # 如果主页面没有，尝试所有frames
                    if require_selector:
                        frames = page.frames
                        for candidate in frames:
                            try:
                                candidate.wait_for_selector(item_selector, timeout=3000)
                                return callback(candidate)
                            except Exception:
                                continue
                        raise RuntimeError("未在任何 frame 中检测到商品列表。")
                    else:
                        # 不需要选择器时，返回主页面
                        return callback(page)

                return controller.perform(run)

            # 先等待页面加载，不要求找到选择器
            try:
                self._log("等待页面加载完成...")
                # 等待页面加载状态
                with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000), require_selector=False)
                # 额外等待，确保React应用完全渲染
                time.sleep(3)
                self._log("页面加载完成，开始查找商品列表...")
            except Exception as exc:  # noqa: BLE001
                logger.exception("页面加载失败")
                self._log(f"页面加载失败：{exc}")

            # 尝试多种选择器策略，增加等待时间
            alternative_selectors = [
                item_selector,
                "div[class*='goods'][class*='item']",
                "div[class*='sku'][class*='item']",
                "div[class*='goods-sku']",
                ".antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-wrapper",
                "[class*='wrapper'][class*='goods']",
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
                        result = controller.perform(
                            lambda page, selector=alt_selector: (
                                # 先等待选择器出现
                                page.wait_for_selector(selector, timeout=3000),
                                len(page.query_selector_all(selector))
                            )
                        )
                        if result and result[1] > 0:
                            found_selector = alt_selector
                            self._log(f"找到 {result[1]} 个商品，使用选择器: {alt_selector}")
                            break
                    except Exception:
                        continue
                
                if found_selector:
                    break

            if not found_selector:
                # 如果所有选择器都失败，尝试输出页面内容用于诊断
                logger.exception("等待讲解列表加载失败")
                self._log("未检测到可讲解商品，尝试输出页面 HTML 片段用于诊断。")
                try:
                    snippet = with_context(lambda ctx: ctx.inner_html("body"), require_selector=False)
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
            # 使用 require_selector=False，因为我们已经找到了选择器，不需要再次等待
            # 将选择器作为参数传递，避免在 f-string 中直接插入导致语法错误
            count_result = with_context(
                lambda ctx: ctx.evaluate(
                    """
                    (selector) => {
                        const items = Array.from(document.querySelectorAll(selector));
                        const totalCount = items.length;
                        
                        // 只统计有"讲解"按钮的商品，并且要求：
                        // 1. 元素可见（不在隐藏状态）
                        // 2. 有"讲解"按钮
                        // 3. 按钮文本严格匹配"讲解"（排除"取消讲解"等）
                        const validItems = items.filter(item => {
                            // 检查元素是否可见
                            const style = window.getComputedStyle(item);
                            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                                return false;
                            }
                            
                            // 查找"讲解"按钮
                            const buttons = Array.from(item.querySelectorAll('button, span, div, a'));
                            const hasExplainButton = buttons.some(btn => {
                                const text = (btn.textContent || '').trim();
                                // 严格匹配：文本必须是"讲解"，不能包含"取消"、"结束"等
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
            
            goods_count = count_result.get("valid", 0) if isinstance(count_result, dict) else (count_result or 0)
            total_count = count_result.get("total", 0) if isinstance(count_result, dict) else 0
            
            if goods_count == 0:
                self._log("当前页面未找到可讲解的商品，自动讲解结束。")
                if total_count > 0:
                    self._log(f"提示：选择器匹配到 {total_count} 个元素，但没有找到可讲解的商品。")
                return

            if total_count > goods_count:
                self._log(f"选择器匹配到 {total_count} 个元素，过滤后找到 {goods_count} 个可讲解商品。")
            self._log(f"共检测到 {goods_count} 个可讲解商品，开始依次处理。")

            processed_count = 0
            max_attempts = goods_count * 2  # 最多尝试次数，防止无限循环
            attempt = 0
            modal_handled = False  # 标记是否已经处理过模态框
            processed_indices = set()  # 记录已处理过的商品索引，避免重复处理
            processed_skus = set()  # 记录已处理过的商品SKU，避免重复处理
            last_processed_index = -1  # 记录上次处理的商品索引
            last_processed_sku = None  # 记录上次处理的商品SKU

            while processed_count < goods_count and attempt < max_attempts:
                attempt += 1
                if self.task_stop_event.is_set():
                    break

                # 每次循环都重新查询商品列表，因为点击后页面可能变化
                # 等待一下，确保页面状态已更新
                time.sleep(1)  # 增加等待时间，确保页面状态更新
                
                current_items = with_context(
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
                                    // 检查是否是三个点（但排除文本为"讲解"的情况）
                                    if (text === '讲解') {
                                        return false; // "讲解"按钮不是下拉菜单触发按钮
                                    }
                                    // 检查是否是三个点或包含下拉菜单相关的类名
                                    if (text === '...' || text === '⋯' || text === '⋮' || (text.length <= 2 && text !== '讲解')) {
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
                                
                                // 获取按钮文本（使用完整文本获取函数）
                                const buttonText = button ? getFullText(button) : '';
                                // 判断是否已处理：按钮文本不是"讲解"或包含"取消"、"结束"等
                                const isProcessed = !button || (
                                    buttonText !== "讲解" && 
                                    !buttonText.includes("讲解") &&
                                    (buttonText.includes("取消") || buttonText.includes("结束"))
                                );
                                
                                // 获取商品编号（index）
                                // 根据HTML结构：<span class="antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-index">08</span>
                                let itemIndex = null;
                                const indexSpan = item.querySelector('span.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-index');
                                if (indexSpan) {
                                    const indexText = (indexSpan.textContent || indexSpan.innerText || '').trim();
                                    // 尝试解析为数字
                                    const indexNum = parseInt(indexText, 10);
                                    if (!isNaN(indexNum)) {
                                        itemIndex = indexNum;
                                    } else {
                                        // 如果无法解析为数字，使用文本
                                        itemIndex = indexText;
                                    }
                                }
                                
                                // 尝试获取SKU信息 - 多种方式
                                let sku = null;
                                
                                // 方式1: 查找包含"SKU:"文本的元素，提取SKU后面的数字
                                const allTextElements = Array.from(item.querySelectorAll('*'));
                                for (const el of allTextElements) {
                                    const text = el.textContent || '';
                                    // 查找包含"SKU:"或"SKU："的文本
                                    const skuMatch = text.match(/SKU[：:]\s*(\\d+)/i);
                                    if (skuMatch && skuMatch[1]) {
                                        sku = skuMatch[1];
                                        break;
                                    }
                                }
                                
                                // 方式2: 查找包含SKU的元素（data-sku, data-id等属性）
                                if (!sku) {
                                    const skuElements = Array.from(item.querySelectorAll('[data-sku], [data-id], [data-product-id], [class*="sku"]'));
                                    for (const el of skuElements) {
                                        const skuValue = el.getAttribute('data-sku') || 
                                                        el.getAttribute('data-id') || 
                                                        el.getAttribute('data-product-id') ||
                                                        el.getAttribute('id');
                                        if (skuValue && skuValue.length > 0 && skuValue !== '商品图') {
                                            // 如果是纯数字，直接使用；否则尝试提取数字
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
                                
                                // 方式3: 从图片URL中提取SKU（京东商品URL通常包含SKU）
                                if (!sku) {
                                    const images = Array.from(item.querySelectorAll('img'));
                                    for (const img of images) {
                                        const imgSrc = img.src || img.getAttribute('data-src') || '';
                                        if (imgSrc) {
                                            // 尝试从URL中提取SKU（多种格式）
                                            // 格式1: /jfs/t1/数字/数字/数字/数字/xxx.jpg
                                            let skuMatch = imgSrc.match(/[\\/]jfs[\\/]t\\d+[\\/](\\d+)[\\/]/);
                                            if (skuMatch && skuMatch[1]) {
                                                sku = skuMatch[1];
                                                break;
                                            }
                                            // 格式2: /数字/数字.jpg 或 /数字数字数字.jpg
                                            skuMatch = imgSrc.match(/[\\/](\\d{8,})[\\/]/);
                                            if (skuMatch && skuMatch[1]) {
                                                sku = skuMatch[1];
                                                break;
                                            }
                                            // 格式3: 查找URL中的长数字串（10位以上）
                                            skuMatch = imgSrc.match(/[\\/](\\d{10,})/);
                                            if (skuMatch && skuMatch[1]) {
                                                sku = skuMatch[1];
                                                break;
                                            }
                                        }
                                    }
                                }
                                
                                // 方式4: 在整个item的文本中查找长数字串（可能是SKU）
                                if (!sku) {
                                    const itemText = item.textContent || '';
                                    // 查找13位数字（京东SKU通常是13位）
                                    const skuMatch = itemText.match(/\\d{13}/);
                                    if (skuMatch) {
                                        sku = skuMatch[0];
                                    } else {
                                        // 如果没找到13位，尝试10位以上的数字
                                        const longNumMatch = itemText.match(/\\d{10,}/);
                                        if (longNumMatch) {
                                            sku = longNumMatch[0];
                                        }
                                    }
                                }
                                
                                // 方式5: 查找商品标题作为唯一标识
                                if (!sku) {
                                    const titleEl = item.querySelector('[class*="title"], [class*="name"], [title]');
                                    if (titleEl) {
                                        const title = titleEl.textContent?.trim() || titleEl.getAttribute('title') || '';
                                        if (title && title.length > 0 && title !== '商品图') {
                                            sku = title.substring(0, 100); // 使用完整标题作为标识
                                        }
                                    }
                                }
                                
                                // 方式6: 使用索引+按钮文本作为后备方案（不使用时间戳，确保同一商品每次获取的SKU相同）
                                if (!sku) {
                                    sku = `item_${idx}_${buttonText}`;
                                }
                                
                                return {
                                    index: idx, // DOM索引
                                    itemIndex: itemIndex, // 商品编号（从页面获取的编号，如08）
                                    hasButton: !!button,
                                    buttonText: buttonText,
                                    isProcessed: isProcessed,
                                    sku: sku // 确保有值
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

                # 按商品编号（itemIndex）升序排序
                # 先过滤出有编号的商品，然后按编号排序
                items_with_index = []
                items_without_index = []
                
                for item_info in current_items:
                    item_index = item_info.get("itemIndex")
                    if item_index is not None:
                        items_with_index.append(item_info)
                    else:
                        items_without_index.append(item_info)
                
                # 按编号升序排序（编号可能是数字或字符串）
                def sort_key(item):
                    item_index = item.get("itemIndex")
                    if isinstance(item_index, (int, float)):
                        return (0, item_index)  # 数字排在前面
                    elif isinstance(item_index, str):
                        # 尝试解析字符串中的数字
                        try:
                            num = int(item_index)
                            return (0, num)
                        except ValueError:
                            return (1, item_index)  # 无法解析的字符串排在后面
                    else:
                        return (2, 0)  # 没有编号的排在最后
                
                items_with_index.sort(key=sort_key)
                
                # 合并：有编号的在前（已排序），没有编号的在后
                current_items = items_with_index + items_without_index
                
                # 找到第一个未处理的商品（按钮文本是"讲解"），按编号顺序
                next_item = None
                self._log(f"查询商品列表，共 {len(current_items)} 个商品（已按编号升序排序）")
                
                # 输出所有商品的状态，用于调试
                for item_info in current_items:
                    idx = item_info.get("index", -1)
                    item_index = item_info.get("itemIndex", "无编号")
                    btn_text = item_info.get("buttonText", "")
                    sku = item_info.get("sku", "")
                    is_proc = item_info.get("isProcessed", False)
                    is_in_processed = idx in processed_indices
                    is_sku_processed = sku in processed_skus
                    self._log(f"  商品编号 {item_index} (DOM索引 {idx}): SKU='{sku}', 按钮文本='{btn_text}', 已处理={is_proc}, 索引已记录={is_in_processed}, SKU已记录={is_sku_processed}")
                
                for item_info in current_items:
                    index = item_info.get("index", 0)
                    button_text = item_info.get("buttonText", "").strip()
                    sku = item_info.get("sku", "")
                    
                    # 跳过已经处理过的商品（通过SKU判断，更可靠）
                    if sku and sku in processed_skus:
                        self._log(f"跳过商品 {index} (SKU: {sku})：SKU已在已处理列表中")
                        continue
                    
                    # 跳过已经处理过的商品（通过索引判断，作为后备）
                    if index in processed_indices:
                        self._log(f"跳过商品 {index}：索引已在已处理列表中")
                        continue
                    
                    # 跳过上次处理的商品（通过SKU判断）
                    if sku and sku == last_processed_sku:
                        self._log(f"跳过商品 {index} (SKU: {sku})：这是上次处理的商品")
                        continue
                    
                    # 跳过上次处理的商品（通过索引判断，作为后备）
                    if index == last_processed_index:
                        self._log(f"跳过商品 {index}：这是上次处理的商品（索引）")
                        continue
                    
                    # 只选择按钮文本确实是"讲解"的商品（不包含"取消"或"结束"）
                    item_index = item_info.get("itemIndex", "无编号")
                    if button_text == "讲解":
                        next_item = item_info
                        self._log(f"找到未处理的商品：编号 {item_index}, DOM索引 {index}, SKU: {sku}")
                        break
                    elif button_text and "讲解" in button_text:
                        # 如果包含"讲解"但还包含其他文本，需要检查
                        if "取消" not in button_text and "结束" not in button_text:
                            next_item = item_info
                            self._log(f"找到未处理的商品：编号 {item_index}, DOM索引 {index}, SKU: {sku}")
                            break

                if not next_item:
                    self._log("所有商品都已处理完成或没有找到可讲解的商品。")
                    break

                index = next_item.get("index", 0)
                item_index = next_item.get("itemIndex", "无编号")
                button_text = next_item.get("buttonText", "")
                sku = next_item.get("sku", "")
                self._log(f"准备处理第 {processed_count + 1} 个商品（商品编号: {item_index}, DOM索引: {index}, SKU: {sku}，按钮文本: '{button_text}'）")
                
                # 再次确认：确保按钮文本确实是"讲解"
                if button_text.strip() != "讲解":
                    if "取消" in button_text or "结束" in button_text:
                        self._log(f"跳过商品 {index}：按钮文本已改变（'{button_text}'），可能已处理过")
                        processed_indices.add(index)  # 记录到已处理列表
                        processed_count += 1
                        continue
                    elif "讲解" not in button_text:
                        self._log(f"跳过商品 {index}：按钮文本不是'讲解'（'{button_text}'）")
                        processed_indices.add(index)  # 记录到已处理列表
                        processed_count += 1
                        continue
                
                # 注意：在处理完成后才添加索引，避免处理失败时误标记
                # 这里先不添加，等处理完成后再添加
                
                # ========== 测试模式：暂时隐藏点击"讲解"按钮功能 ==========
                self._log("【测试模式】跳过点击讲解按钮，直接下载图片")
                
                # 先下载图片
                info = with_context(
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
                        image_info = with_context(
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
                            )
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
                    base_url = with_context(lambda ctx: ctx.url) or "https://live.jd.com"
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

                # ========== 测试模式：暂时隐藏点击"讲解"按钮功能 ==========
                # 跳过点击讲解按钮，直接标记为已处理并继续下一个商品
                self._log("【测试模式】跳过点击讲解按钮，直接准备下一个商品")
                
                # 处理完成后，将索引和SKU添加到已处理列表
                processed_indices.add(index)
                if sku:
                    processed_skus.add(sku)
                last_processed_index = index  # 记录本次处理的索引
                last_processed_sku = sku  # 记录本次处理的SKU
                self._log(f"已记录商品（索引: {index}, SKU: {sku}）到已处理列表（图片已下载）")
                
                processed_count += 1
                
                # 如果还有商品未处理，等待间隔时间
                if processed_count < goods_count and interval > 0:
                    self._log(f"等待 {interval} 秒准备下一个商品。")
                    if self.task_stop_event.wait(interval):
                        break
                    
                    # 间隔等待后，再次确保页面稳定
                    try:
                        with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=5000), require_selector=False)
                        time.sleep(0.5)  # 确保页面状态更新
                    except Exception:
                        pass
                
                # 继续下一个商品
                continue
                
                # ========== 原始代码（已注释，用于测试后恢复）==========
                # # 使用JavaScript查找并点击"讲解"按钮
                # clicked = False
                # try:
                #     clicked = with_context(...)
                # except Exception as exc:
                #     logger.exception("点击讲解按钮时发生异常")
                #     self._log(f"点击按钮异常：{exc}")
                #     clicked = False
                # 
                # if not clicked:
                #     self._log(f"未找到第 {processed_count + 1} 个商品的讲解按钮，跳过。")
                #     processed_count += 1
                #     continue
                # 
                # self._log(f"已点击讲解按钮：{title}")
                
                # 只在第一次点击时等待并处理确认模态框
                if not modal_handled:
                    try:
                        self._log("检查是否需要确认（仅第一次）...")
                        # 等待模态框出现（最多等待2秒）
                        modal_confirmed = False
                        for wait_attempt in range(20):  # 20次，每次100ms，共2秒
                            if self.task_stop_event.is_set():
                                break
                            try:
                                modal_confirmed = with_context(
                                    lambda ctx: ctx.evaluate(
                                        """
                                        () => {
                                            // 查找确认模态框/弹出框
                                            // 优先在 ant-popover 中查找
                                            const popover = document.querySelector('.ant-popover');
                                            if (popover) {
                                                const popoverButtons = Array.from(popover.querySelectorAll('button'));
                                                const confirmButton = popoverButtons.find((node) => {
                                                    // 获取按钮文本（包括内部span的文本）
                                                    const text = (node.textContent || '').trim().replace(/\s+/g, '');
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
                                            
                                            // 如果没找到popover，尝试查找所有包含"确定"的primary按钮
                                            const allButtons = Array.from(document.querySelectorAll('button.ant-btn-primary'));
                                            const confirmButton = allButtons.find((node) => {
                                                const text = (node.textContent || '').trim().replace(/\s+/g, '');
                                                return text === "确定" || text.includes("确定");
                                            });
                                            
                                            if (confirmButton) {
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
                                            
                                            return false;
                                        }
                                        """
                                    ),
                                    require_selector=False
                                )
                                if modal_confirmed:
                                    self._log("已点击确认按钮")
                                    modal_handled = True  # 标记已处理
                                    # 等待模态框关闭
                                    time.sleep(0.5)
                                    break
                            except Exception:
                                pass
                            time.sleep(0.1)
                        
                        if not modal_confirmed:
                            self._log("未检测到确认模态框（这是正常的，不是所有商品都需要确认）")
                            modal_handled = True  # 即使没找到模态框，也标记为已处理，后续不再检查
                    except Exception as modal_exc:  # noqa: BLE001
                        logger.exception("处理确认模态框时发生异常")
                        self._log(f"处理确认模态框异常：{modal_exc}")
                        modal_handled = True  # 发生异常也标记为已处理，避免后续重复检查
                else:
                    self._log("跳过模态框检查（已处理过）")
                
                # 点击"讲解"后，页面可能会重新加载，需要等待页面完全加载
                self._log("等待页面重新加载（点击讲解后）...")
                try:
                    # 等待页面加载完成（如果页面重新加载了）
                    with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000), require_selector=False)
                    self._log("页面加载完成")
                except Exception:
                    self._log("页面可能没有重新加载，继续等待...")
                
                # 等待商品列表重新渲染
                self._log("等待商品列表重新渲染...")
                time.sleep(3)  # 等待3秒，确保React应用完全渲染
                
                # 再次等待网络空闲，确保所有资源加载完成
                try:
                    with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=10000), require_selector=False)
                    time.sleep(1)  # 额外等待1秒
                except Exception:
                    pass
                
                self._log("页面状态已稳定，开始讲解")
                self._log(f"开始讲解：{title}")
                
                # 等待讲解时间
                if self.task_stop_event.wait(duration):
                    break
                
                # 在开始下一个商品之前，先停止当前讲解
                self._log(f"讲解时间到，准备停止当前讲解：{title}")
                try:
                    # 多次尝试查找停止按钮，因为可能需要等待页面更新
                    stopped = False
                    for stop_attempt in range(10):  # 最多尝试10次，每次200ms，共2秒
                        if self.task_stop_event.is_set():
                            break
                        try:
                            stopped = with_context(
                                lambda ctx: ctx.evaluate(
                                    """
                                    () => {
                                        // 查找"结束"按钮
                                        // 根据HTML结构，"结束"按钮是一个span元素，在包含"取消｜结束"的容器中
                                        
                                        let stopButton = null;
                                        
                                        // 方式1: 查找包含"结束"文本的span，且类名包含selectBtn和hover
                                        // 根据HTML结构：<span class="antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-hover">结束</span>
                                        const allSpans = Array.from(document.querySelectorAll('span'));
                                        stopButton = allSpans.find((span) => {
                                            const text = (span.textContent || span.innerText || '').trim();
                                            // 检查类名：必须同时包含selectBtn和hover类
                                            const hasSelectBtnClass = span.classList.contains('antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn');
                                            const hasHoverClass = span.classList.contains('antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-hover');
                                            // 严格匹配：文本必须是"结束"，且必须同时有这两个类
                                            return text === '结束' && hasSelectBtnClass && hasHoverClass;
                                        });
                                        
                                        // 方式2: 查找包含"结束"文本的span，且父元素包含"取消"和"结束"
                                        if (!stopButton) {
                                            stopButton = allSpans.find((span) => {
                                                const text = (span.textContent || '').trim();
                                                if (text === '结束') {
                                                    // 向上查找包含"取消"和"结束"的父容器
                                                    let parent = span.parentElement;
                                                    while (parent) {
                                                        const parentText = (parent.textContent || '').trim();
                                                        if (parentText.includes('取消') && parentText.includes('结束')) {
                                                            // 检查父元素是否有selectBtn类
                                                            if (parent.classList.contains('antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn') ||
                                                                parent.querySelector('.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn')) {
                                                                return true;
                                                            }
                                                        }
                                                        parent = parent.parentElement;
                                                    }
                                                }
                                                return false;
                                            });
                                        }
                                        
                                        // 方式3: 查找所有包含"结束"文本的span，且在同一容器中有"取消"
                                        if (!stopButton) {
                                            stopButton = allSpans.find((span) => {
                                                const text = (span.textContent || '').trim();
                                                if (text === '结束') {
                                                    // 查找最近的包含"取消"的容器
                                                    const container = span.closest('[class*="selectBtn"], [class*="buttonContainer"]');
                                                    if (container) {
                                                        const containerText = container.textContent || '';
                                                        return containerText.includes('取消') && containerText.includes('结束');
                                                    }
                                                }
                                                return false;
                                            });
                                        }
                                        
                                        // 方式4: 查找所有包含"结束"文本的元素
                                        if (!stopButton) {
                                            const allElements = Array.from(document.querySelectorAll('span'));
                                            stopButton = allElements.find((node) => {
                                                const text = (node.textContent || '').trim();
                                                return text === '结束';
                                            });
                                        }
                                        
                                        if (stopButton) {
                                            // 滚动到按钮位置
                                            stopButton.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                            // 等待一下
                                            const startTime = Date.now();
                                            while (Date.now() - startTime < 500) {}
                                            
                                            // 点击停止按钮
                                            try {
                                                stopButton.click();
                                                // 等待点击响应
                                                const clickWaitTime = Date.now();
                                                while (Date.now() - clickWaitTime < 200) {}
                                                return true;
                                            } catch (e) {
                                                try {
                                                    const clickEvent = new MouseEvent('click', {
                                                        bubbles: true,
                                                        cancelable: true,
                                                        view: window
                                                    });
                                                    stopButton.dispatchEvent(clickEvent);
                                                    const clickWaitTime = Date.now();
                                                    while (Date.now() - clickWaitTime < 200) {}
                                                    return true;
                                                } catch (e2) {
                                                    return false;
                                                }
                                            }
                                        }
                                        
                                        return false;
                                    }
                                    """
                                ),
                                require_selector=False
                            )
                            if stopped:
                                self._log("已点击停止按钮")
                                time.sleep(1)  # 等待停止操作完成
                                break
                        except Exception:
                            pass
                        time.sleep(0.2)
                    
                    if not stopped:
                        self._log("未找到停止按钮，尝试继续...")
                except Exception as stop_exc:  # noqa: BLE001
                    logger.exception("停止讲解时发生异常")
                    self._log(f"停止讲解异常：{stop_exc}")
                    
                self._log(f"讲解结束：{title}")
                
                # 停止后，页面可能会重新加载，需要等待页面完全加载
                self._log("等待页面重新加载...")
                try:
                    # 等待页面加载完成（如果页面重新加载了）
                    with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000), require_selector=False)
                    self._log("页面加载完成")
                except Exception:
                    self._log("页面可能没有重新加载，继续等待...")
                
                # 等待页面完全稳定，确保商品列表重新渲染
                self._log("等待商品列表重新渲染...")
                time.sleep(3)  # 等待3秒，确保React应用完全渲染
                
                # 再次等待网络空闲，确保所有资源加载完成
                try:
                    with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=10000), require_selector=False)
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
                self._log(f"已记录商品（索引: {index}, SKU: {sku}）到已处理列表（处理完成）")
                
                processed_count += 1

                # 如果还有商品未处理，等待间隔时间
                if processed_count < goods_count and interval > 0:
                    self._log(f"等待 {interval} 秒准备下一场。")
                    if self.task_stop_event.wait(interval):
                        break
                    
                    # 间隔等待后，再次确保页面稳定
                    try:
                        with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=5000), require_selector=False)
                        time.sleep(1)  # 增加等待时间，确保页面状态更新
                    except Exception:
                        pass
                
                # 重要：在下次循环开始前，再次等待一下，确保页面状态完全更新
                # 这样重新查询商品列表时，第一个商品的状态应该已经更新（不再是"讲解"）
                time.sleep(0.5)

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

    def _on_browse_material(self) -> None:
        path = filedialog.askdirectory(title="选择卡点素材文件夹")
        if path:
            self.material_path_var.set(path)
            self._log(f"已选择素材目录：{path}")

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
        self.config["task"]["material_path"] = self.material_path_var.get().strip()
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
            self.controller.disconnect()
            self.destroy()

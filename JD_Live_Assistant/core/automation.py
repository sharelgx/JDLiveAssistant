"""浏览器控制模块，基于 Playwright 实现与京东直播页面的通信。"""

from __future__ import annotations

import socket
import threading
from contextlib import suppress
from typing import Any, Callable, Optional

from loguru import logger
from playwright.sync_api import Browser, Error, Page, Playwright, sync_playwright


class BrowserController:
    """封装 Playwright 连接逻辑，提供基础浏览器控制接口。"""

    def __init__(self, connect_timeout: int = 10) -> None:
        """
        初始化浏览器控制器。
        
        Args:
            connect_timeout: 连接超时时间（秒），默认10秒
        """
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._lock = threading.Lock()
        self._connect_timeout = connect_timeout

    def _check_port_available(self, port: int) -> bool:
        """检查指定端口是否可访问。"""
        try:
            logger.debug("创建socket连接检查端口 {}...", port)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)  # 2秒超时
            logger.debug("尝试连接 127.0.0.1:{}...", port)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            logger.debug("端口连接测试完成，结果码: {}", result)
            return result == 0
        except Exception as e:
            logger.warning("端口检查异常: {}", e)
            return False

    def connect(self, port: int) -> None:
        """
        连接指定远程调试端口的浏览器。
        
        Args:
            port: Chrome远程调试端口
            
        Raises:
            RuntimeError: 连接失败时抛出异常
        """
        logger.info("正在尝试连接调试端口: {}", port)
        
        # 尝试获取锁，如果锁被占用则说明有其他连接正在进行
        if not self._lock.acquire(timeout=1):
            error_msg = "连接操作正在进行中，请稍候再试"
            logger.warning(error_msg)
            raise RuntimeError(error_msg)
        
        try:
            logger.debug("已获取连接锁，开始检查端口...")
            
            # 先检查端口是否可访问
            logger.debug("检查端口 {} 是否可访问...", port)
            port_available = self._check_port_available(port)
            logger.debug("端口检查完成，结果: {}", port_available)
            
            if not port_available:
                error_msg = (
                    f"无法连接到端口 {port}。\n"
                    "请确保：\n"
                    "1. Chrome浏览器已启动并启用了远程调试\n"
                    "2. Chrome启动参数包含：--remote-debugging-port={port}\n"
                    "3. 端口号正确无误"
                ).format(port=port)
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            logger.debug("端口检查通过，开始断开旧连接...")
            self.disconnect(_lock_acquired=True)
            
            logger.debug("启动 Playwright...")
            self._playwright = sync_playwright().start()
            logger.debug("Playwright 启动成功")
            
            endpoint = f"http://127.0.0.1:{port}"
            logger.debug("准备连接CDP端点: {}...", endpoint)
            
            # Playwright 的 sync API 使用 greenlet，不能跨线程使用
            # 由于端口检查已通过，connect_over_cdp 应该很快完成
            # 如果卡住，通常是 Chrome CDP 端点的问题，而不是代码问题
            try:
                logger.debug("执行 connect_over_cdp...")
                self._browser = self._playwright.chromium.connect_over_cdp(endpoint)
                logger.debug("CDP连接成功")
            except Error as e:
                # Playwright 特定的错误
                error_msg = (
                    f"连接浏览器失败: {str(e)}\n"
                    "可能的原因：\n"
                    "1. Chrome浏览器未启用远程调试\n"
                    "2. Chrome CDP端点不可用\n"
                    "3. Chrome版本与Playwright不兼容"
                )
                logger.error(error_msg)
                self.disconnect(_lock_acquired=True)  # 清理资源
                raise RuntimeError(error_msg) from e
            
            # 获取或创建上下文和页面
            logger.debug("获取浏览器上下文和页面...")
            context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
            
            # 收集所有页面并尝试找到京东相关页面
            all_pages = context.pages
            if not all_pages:
                logger.debug("没有现有页面，创建新页面")
                self._page = context.new_page()
            else:
                logger.debug("找到 {} 个页面，尝试自动选择京东相关页面", len(all_pages))
                
                # 尝试找到京东相关页面（通过URL或标题判断）
                jd_page = None
                for page in all_pages:
                    try:
                        url = page.url
                        title = page.title() if hasattr(page.title, '__call__') else str(page.title)
                        logger.debug("检查页面: URL={}, 标题={}", url[:80] if url else '', title[:50] if title else '')
                        
                        # 判断是否是京东相关页面
                        if 'jd.com' in url.lower() or 'jd.com' in title.lower():
                            jd_page = page
                            logger.info("✓ 自动选择京东页面: {} ({})", title[:50], url[:80])
                            break
                        elif '京东' in title or '直播' in title or '商品' in title:
                            jd_page = page
                            logger.info("✓ 自动选择相关页面: {} ({})", title[:50], url[:80])
                            break
                    except Exception as page_check_exc:
                        logger.debug("检查页面失败: {}", page_check_exc)
                        continue
                
                if jd_page:
                    self._page = jd_page
                else:
                    # 如果没找到京东页面，使用第一个非DevTools页面
                    for page in all_pages:
                        try:
                            url = page.url
                            if not url.startswith('devtools://') and not url.startswith('chrome-extension://'):
                                self._page = page
                                logger.warning("未找到京东页面，使用第一个普通页面: {}", url[:80])
                                break
                        except Exception:
                            continue
                    
                    # 如果还是没找到，使用第一个页面
                    if not self._page:
                        self._page = all_pages[0]
                        logger.warning("使用第一个页面（可能不是目标页面）")
            
            logger.debug("上下文和页面获取成功")
            
            try:
                if self._page:
                    self._page.bring_to_front()
                    logger.debug("已调用 bring_to_front，当前页面 URL: {}", self._page.url)
            except Exception as bring_exc:
                logger.debug("尝试 bring_to_front 失败: {}", bring_exc)
            
            logger.success("绑定浏览器成功: 端口 {}", port)
            
        except RuntimeError:
            # 超时错误已处理，直接重新抛出
            raise
        except Error as e:
            error_msg = (
                f"连接浏览器失败: {str(e)}\n"
                "可能的原因：\n"
                "1. Chrome浏览器未启用远程调试\n"
                "2. 端口被其他程序占用\n"
                "3. Chrome版本与Playwright不兼容"
            )
            logger.error(error_msg)
            self.disconnect(_lock_acquired=True)  # 清理资源
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"连接过程中发生未知错误: {str(e)}"
            logger.exception(error_msg)
            self.disconnect(_lock_acquired=True)  # 清理资源
            raise RuntimeError(error_msg) from e
        finally:
            # 确保释放锁
            self._lock.release()
            logger.debug("已释放连接锁")

    def navigate(self, url: str) -> None:
        """跳转到指定地址。"""

        with self._lock:
            if not self._page:
                raise RuntimeError("浏览器尚未连接，无法执行跳转。")
            logger.info("浏览器跳转: {}", url)
            self._page.goto(url, wait_until="load")

    def eval_script(self, script: str) -> None:
        """在当前页面执行 JavaScript。"""

        with self._lock:
            if not self._page:
                raise RuntimeError("浏览器尚未连接，无法执行脚本。")
            logger.debug("执行脚本: {}", script[:80])
            self._page.evaluate(script)

    def perform(self, callback: Callable[[Page], Any]) -> Any:
        """传入回调以访问原生 Page 对象，方便扩展更多操作，并返回回调结果。"""

        with self._lock:
            if not self._page:
                raise RuntimeError("浏览器尚未连接，无法执行操作。")
            return callback(self._page)

    def disconnect(self, _lock_acquired: bool = False) -> None:
        """
        断开浏览器连接并释放资源。
        
        Args:
            _lock_acquired: 内部参数，如果为True表示调用者已持有锁，不需要再次获取
        """
        if not _lock_acquired:
            self._lock.acquire()
        
        try:
            if self._page:
                logger.debug("清理 Page 对象")
                self._page = None
            if self._browser:
                with suppress(Error):
                    logger.debug("关闭浏览器连接")
                    self._browser.close()
                self._browser = None
            if self._playwright:
                logger.debug("停止 Playwright 服务")
                self._playwright.stop()
                self._playwright = None
        finally:
            if not _lock_acquired:
                self._lock.release()

    @property
    def is_connected(self) -> bool:
        """当前是否已经绑定浏览器。"""

        return self._browser is not None and self._page is not None

    def __del__(self) -> None:
        self.disconnect()


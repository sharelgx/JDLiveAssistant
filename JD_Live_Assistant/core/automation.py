"""浏览器控制模块，基于 Playwright 实现与京东直播页面的通信。"""

from __future__ import annotations

import threading
from contextlib import suppress
from typing import Callable, Optional

from loguru import logger
from playwright.sync_api import Browser, Error, Page, Playwright, sync_playwright


class BrowserController:
    """封装 Playwright 连接逻辑，提供基础浏览器控制接口。"""

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._lock = threading.Lock()

    def connect(self, port: int) -> None:
        """连接指定远程调试端口的浏览器。"""

        with self._lock:
            logger.info("正在尝试连接调试端口: {}", port)
            self.disconnect()
            self._playwright = sync_playwright().start()
            endpoint = f"http://127.0.0.1:{port}"
            self._browser = self._playwright.chromium.connect_over_cdp(endpoint)
            context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
            self._page = context.pages[0] if context.pages else context.new_page()
            logger.success("绑定浏览器成功: 端口 {}", port)

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

    def perform(self, callback: Callable[[Page], None]) -> None:
        """传入回调以访问原生 Page 对象，方便扩展更多操作。"""

        with self._lock:
            if not self._page:
                raise RuntimeError("浏览器尚未连接，无法执行操作。")
            callback(self._page)

    def disconnect(self) -> None:
        """断开浏览器连接并释放资源。"""

        with self._lock:
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

    @property
    def is_connected(self) -> bool:
        """当前是否已经绑定浏览器。"""

        return self._browser is not None and self._page is not None

    def __del__(self) -> None:
        self.disconnect()


"""全局热键管理模块。"""

from __future__ import annotations

from typing import Callable, Dict

import keyboard
from loguru import logger


class HotkeyManager:
    """封装 keyboard 库的热键注册与释放。"""

    def __init__(self) -> None:
        self._callbacks: Dict[str, Callable[[], None]] = {}
        self._registered: Dict[str, int] = {}
        self._active = False

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        """注册新的热键与回调。"""

        if hotkey in self._callbacks:
            logger.warning("热键 {} 已存在，将覆盖旧回调", hotkey)
        self._callbacks[hotkey] = callback
        if self._active:
            self._registered[hotkey] = keyboard.add_hotkey(hotkey, callback)
            logger.info("启用热键: {}", hotkey)

    def unregister(self, hotkey: str) -> None:
        identifier = self._registered.pop(hotkey, None)
        if identifier is not None:
            keyboard.remove_hotkey(identifier)
            logger.info("移除热键: {}", hotkey)
        self._callbacks.pop(hotkey, None)

    def start(self) -> None:
        if self._active:
            return
        logger.debug("启动热键监听")
        for hotkey, callback in self._callbacks.items():
            self._registered[hotkey] = keyboard.add_hotkey(hotkey, callback)
            logger.info("启用热键: {}", hotkey)
        self._active = True

    def stop(self) -> None:
        if not self._active:
            return
        logger.debug("停止热键监听")
        for identifier in list(self._registered.values()):
            keyboard.remove_hotkey(identifier)
        self._registered.clear()
        self._active = False

    def clear(self) -> None:
        self.stop()
        self._callbacks.clear()

    def bind_from_mapping(self, mapping: Dict[str, str], handlers: Dict[str, Callable[[], None]]) -> None:
        """根据配置映射批量注册热键。"""

        for name, hotkey in mapping.items():
            handler = handlers.get(name)
            if handler:
                self.register(hotkey, handler)
            else:
                logger.warning("未找到对应处理器: {}", name)


"""京东直播自动化助手入口模块。"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import sys

from loguru import logger

from JD_Live_Assistant.core import (
    BrowserController,
    ConfigManager,
    HotkeyManager,
    LicenseManager,
    ScheduleManager,
)
from JD_Live_Assistant.ui.main_window import MainWindow


def get_app_dir() -> Path:
    """获取应用运行目录。

    - 开发模式：返回当前文件所在目录。
    - 打包模式：返回可执行文件所在目录。
    """

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def setup_logging(base_dir: Path) -> None:
    """初始化日志输出。"""

    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(log_dir / "runtime.log", rotation="5 MB", retention="10 days", encoding="utf-8")
    logger.info("日志系统初始化完成。")


def main() -> None:
    base_dir = get_app_dir()
    setup_logging(base_dir)

    config_path = base_dir / "config" / "settings.yaml"
    config_manager = ConfigManager(config_path)
    license_path = base_dir / "config" / "license.json"
    license_manager = LicenseManager(license_path)
    controller = BrowserController()
    scheduler = ScheduleManager()
    hotkeys = HotkeyManager()

    app = MainWindow(controller, scheduler, hotkeys, config_manager, license_manager)
    app.mainloop()


if __name__ == "__main__":
    main()


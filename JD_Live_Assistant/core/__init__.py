"""核心业务模块包。"""

from .automation import BrowserController
from .config import ConfigManager
from .hotkeys import HotkeyManager
from .license import LicenseManager
from .schedule import ScheduleManager

__all__ = [
    "BrowserController",
    "HotkeyManager",
    "ScheduleManager",
    "ConfigManager",
    "LicenseManager",
]


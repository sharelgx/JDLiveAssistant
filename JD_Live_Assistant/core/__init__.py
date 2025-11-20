"""核心业务模块包。"""

from .automation import BrowserController
from .chrome_launcher import ChromeLauncher
from .config import ConfigManager
from .hotkeys import HotkeyManager
from .license import LicenseManager
from .schedule import ScheduleManager

__all__ = [
    "BrowserController",
    "ChromeLauncher",
    "HotkeyManager",
    "ScheduleManager",
    "ConfigManager",
    "LicenseManager",
]


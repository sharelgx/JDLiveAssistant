"""配置管理模块，负责读取与写入应用配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml

DEFAULT_CONFIG: Dict[str, Any] = {
    "app": {
        "default_port": 9222,
        "live_url": "https://live.jd.com/#/anchor/live-list",
    },
    "schedule": {
        "daily_start_time": "09:00",
    },
    "hotkeys": {
        "start_live": "ctrl+alt+f5",
        "stop_live": "ctrl+alt+f6",
        "refresh": "ctrl+alt+r",
    },
}


@dataclass
class ConfigManager:
    """配置文件管理器。"""

    path: Path
    _config: Dict[str, Any] = field(default_factory=dict, init=False)

    def ensure_exists(self) -> None:
        """确保配置文件存在，不存在时写入默认内容。"""

        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.save(DEFAULT_CONFIG)

    def load(self) -> Dict[str, Any]:
        """读取配置文件。"""

        self.ensure_exists()
        with self.path.open("r", encoding="utf-8") as fh:
            self._config = yaml.safe_load(fh) or {}
        return self._config

    def save(self, config: Dict[str, Any]) -> None:
        """保存配置。"""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(config, fh, allow_unicode=True, sort_keys=False)
        self._config = config

    @property
    def data(self) -> Dict[str, Any]:
        """返回当前配置数据。"""

        if not self._config:
            return self.load()
        return self._config


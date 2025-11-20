"""Chrome 启动与检测工具。"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, Optional

from loguru import logger


def _candidate_paths() -> Iterable[Path]:
    """生成常见的 Chrome 可执行路径。"""

    env_path = os.environ.get("CHROME_PATH")
    if env_path:
        yield Path(env_path)

    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        yield Path(local_app) / "Google" / "Chrome" / "Application" / "chrome.exe"
        yield Path(local_app) / "Google" / "Chrome" / "Bin" / "chrome.exe"

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        yield Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe"

    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if program_files_x86:
        yield Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe"

    # 常见的便携版安装路径
    portable_dir = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Bin" / "chrome.exe"
    yield portable_dir


def detect_chrome_path(preferred: Optional[str] = None) -> Optional[Path]:
    """检测 Chrome 可执行文件路径。"""

    candidates = []
    if preferred:
        candidates.append(Path(preferred))
    candidates.extend(_candidate_paths())

    for path in candidates:
        try:
            if path and path.is_file():
                logger.info("检测到 Chrome 路径: {}", path)
                return path
        except Exception:
            continue
    logger.warning("未能自动检测到 Chrome，可执行路径为空。")
    return None


def _is_port_open(port: int) -> bool:
    """检查本地端口是否监听。"""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        try:
            return sock.connect_ex(("127.0.0.1", port)) == 0
        except OSError:
            return False


class ChromeLauncher:
    """负责自动启动并等待 Chrome 远程调试端口就绪。"""

    def __init__(self, chrome_path: Optional[str] = None, profile_root: Optional[str] = None) -> None:
        self._chrome_path = detect_chrome_path(chrome_path)
        self._profile_root = Path(profile_root) if profile_root else Path.home() / "AppData" / "Local" / "JDLiveAssistant" / "ChromeProfiles"
        self._last_profile_dir: Optional[Path] = None

    @property
    def executable(self) -> Optional[Path]:
        return self._chrome_path

    @property
    def profile_root(self) -> Path:
        return self._profile_root

    @property
    def last_profile_dir(self) -> Optional[Path]:
        return self._last_profile_dir

    def ensure_executable(self) -> Path:
        if not self._chrome_path:
            detected = detect_chrome_path()
            if not detected:
                raise RuntimeError("未找到 Chrome 浏览器，请手动安装或指定路径。")
            self._chrome_path = detected
        return self._chrome_path

    def launch_if_needed(self, port: int, profile_name: Optional[str] = None, timeout: float = 10.0) -> bool:
        """
        启动 Chrome，如果端口已就绪则直接返回。
        Args:
            port: 调试端口
            profile_name: 自定义配置目录名称，默认使用端口号
            timeout: 等待端口就绪的秒数
        Returns:
            bool: 端口是否就绪
        """

        if _is_port_open(port):
            logger.debug("端口 {} 已在监听，跳过自动启动。", port)
            return True

        executable = self.ensure_executable()
        profile_dir = self.profile_root / (profile_name or str(port))
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._last_profile_dir = profile_dir

        cmd = [
            str(executable),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--disable-first-run-ui",
        ]

        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        logger.info("启动 Chrome：{} (profile: {})", executable, profile_dir)
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
        except FileNotFoundError as exc:
            raise RuntimeError(f"未找到 Chrome 浏览器：{executable}") from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"启动 Chrome 失败：{exc}") from exc

        deadline = time.time() + timeout
        while time.time() < deadline:
            if _is_port_open(port):
                logger.info("Chrome 端口 {} 已就绪。", port)
                return True
            time.sleep(0.5)

        logger.warning("等待 Chrome 端口 {} 就绪超时。", port)
        return False


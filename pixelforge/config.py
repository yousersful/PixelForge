"""应用配置管理。

负责读取/写入 JSON 配置文件，管理窗口状态、默认模型、数据目录路径等。
API Key 不存于此文件，由 security.key_manager 加密管理。
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class AppConfig:
    """应用配置。

    默认数据目录结构:
      data/
        config.json      # 本配置文件（不含密钥）
        history.db       # 生成历史 (SQLite)
        images/          # 生成的图片
        sessions/        # 创作会话（对话式 UI 的本地持久化）
        key.bin          # 加密的 API Key
    """

    APP_NAME = "PixelForge"
    REPO_URL = "https://github.com/yousersful/PixelForge"
    DEFAULT_CONFIG: dict = {
        "window": {"width": 1000, "height": 720, "maximized": False},
        "model": {
            "provider": "siliconflow",
            "model": "Kwai-Kolors/Kolors",
            "size": "1024x1024",
            "num_images": 1,
        },
        "paths": {
            "image_dir": "",  # 为空则用默认 data/images
        },
    }

    def __init__(self, config_dir: Path | None = None) -> None:
        # 默认数据目录：项目根目录下 data/
        base_dir = Path(__file__).resolve().parent.parent
        self.config_dir = config_dir or (base_dir / "data")
        self.config_path = self.config_dir / "config.json"
        self.image_dir = self.config_dir / "images"
        self.history_path = self.config_dir / "history.db"
        self.sessions_dir = self.config_dir / "sessions"
        self.key_path = self.config_dir / "key.bin"

        self._data = json.loads(json.dumps(self.DEFAULT_CONFIG))  # 深拷贝默认值

    # ------------------------------------------------------------------
    # 目录初始化
    # ------------------------------------------------------------------
    def ensure_dirs(self) -> None:
        """确保数据目录存在。"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 加载 / 保存
    # ------------------------------------------------------------------
    def load(self) -> "AppConfig":
        """从磁盘加载配置，若不存在则使用默认值。"""
        self.ensure_dirs()
        if self.config_path.exists():
            try:
                stored = json.loads(self.config_path.read_text(encoding="utf-8"))
                self._deep_update(self._data, stored)
            except (json.JSONDecodeError, OSError):
                pass  # 损坏时回退到默认
        return self

    def save(self) -> None:
        """保存配置到磁盘。"""
        self.ensure_dirs()
        self.config_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # 键值访问
    # ------------------------------------------------------------------
    def get(self, key: str, default=None):
        """通过点分路径读取，如 config.get("paths.image_dir")。"""
        node: dict = self._data
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def set(self, key: str, value) -> None:
        """通过点分路径写入。"""
        parts = key.split(".")
        node: dict = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    @property
    def effective_image_dir(self) -> Path:
        """实际图片保存目录（配置覆盖时优先）。"""
        custom = self.get("paths.image_dir")
        if custom:
            return Path(custom)
        return self.image_dir

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    @staticmethod
    def _deep_update(base: dict, extra: dict) -> None:
        """递归合并 extra 到 base（保留 base 中未被覆盖的键）。"""
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                AppConfig._deep_update(base[key], value)
            else:
                base[key] = value

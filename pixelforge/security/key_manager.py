"""API Key 加密存储（支持多 Provider）。

使用 cryptography 的 Fernet 对称加密，密钥由机器绑定的标识符派生，
API Key 仅保存在本地加密文件，绝不上传。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class KeyManager:
    """API Key 的加密保存与读取（支持多 Provider）。

    说明：
      - 加密密钥从机器标识（hostname + 用户名 + 固定盐）派生，
        即使 key.bin 泄露，在其他机器上也难以解密。
      - 支持为不同 Provider 分别保存 Key（JSON 结构）。
      - 若换机器迁移，需重新录入 Key。
    """

    def __init__(self, key_path: Path) -> None:
        self.key_path = Path(key_path)

    # ------------------------------------------------------------------
    # 密钥派生
    # ------------------------------------------------------------------
    @staticmethod
    def _derive_key() -> bytes:
        """从机器标识派生一个固定密钥。"""
        machine = (
            platform.node()
            + os.getenv("USERNAME", "")  # Windows
            + os.getenv("USER", "")      # Linux/macOS
        )
        digest = hashlib.sha256(machine.encode("utf-8")).digest()
        # Fernet 需要 32 字节 url-safe base64 编码的密钥
        return base64.urlsafe_b64encode(digest)

    @staticmethod
    def _fernet() -> Fernet:
        return Fernet(KeyManager._derive_key())

    # ------------------------------------------------------------------
    # 存储文件（JSON：{provider_id: encrypted_token}）
    # ------------------------------------------------------------------
    def _read_all(self) -> dict:
        """读取全部 provider 的密文；兼容旧的单 token 文件。"""
        if not self.key_path.exists():
            return {}
        try:
            raw = self.key_path.read_bytes()
        except OSError:
            return {}
        if not raw or not raw.strip():
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            pass
        # 旧格式：单个加密串，视为 siliconflow
        try:
            return {"siliconflow": raw.decode("utf-8")}
        except UnicodeDecodeError:
            return {}

    def _write_all(self, data: dict) -> None:
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)

    # ------------------------------------------------------------------
    # 保存 / 读取 / 删除
    # ------------------------------------------------------------------
    def save(self, api_key: str, provider_id: str = "siliconflow") -> None:
        """加密保存指定 Provider 的 API Key。"""
        data = self._read_all()
        token = self._fernet().encrypt(api_key.encode("utf-8")).decode("ascii")
        data[provider_id] = token
        self._write_all(data)

    def load(self, provider_id: str = "siliconflow") -> str | None:
        """读取并解密指定 Provider 的 API Key；不存在或失败返回 None。"""
        token = self._read_all().get(provider_id)
        if not token:
            return None
        try:
            return self._fernet().decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, OSError, ValueError):
            return None

    def delete(self, provider_id: str = "siliconflow") -> None:
        """删除指定 Provider 已保存的 Key。"""
        data = self._read_all()
        if provider_id in data:
            data.pop(provider_id)
            self._write_all(data)

    def has_key(self, provider_id: str = "siliconflow") -> bool:
        """指定 Provider 是否已保存有效的 Key。"""
        return self.load(provider_id) is not None

    def known_providers(self) -> list:
        """已保存 Key 的 Provider ID 列表。"""
        return list(self._read_all().keys())

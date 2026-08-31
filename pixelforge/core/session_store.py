"""创作会话（session）持久化。

对话式创作流的会话保存在 data/sessions/ 下，每个会话一个 JSON：
  {
    "id": "20260828_153000_ab12cd",
    "created_at": "...",
    "updated_at": "...",
    "provider": "siliconflow",
    "model": "Kwai-Kolors/Kolors",
    "mode": "standard",
    "messages": [
      {"role": "user", "type": "text", "text": "..."},
      {"role": "user", "type": "image", "path": "D:/.../ref.png"},
      {"role": "assistant", "type": "image", "paths": ["..."], "duration": 15.2},
      {"role": "assistant", "type": "error", "text": "..."}
    ],
    "current_image": "D:/.../last.png"   # 当前图（图生图修改时的默认参考图）
  }

「新的创作」= 把当前会话写入磁盘并开启空会话；
侧栏「恢复上次对话」= 读取 updated_at 最新的会话文件。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional


class SessionStore:
    """基于 JSON 文件的会话存储。"""

    def __init__(self, sessions_dir: Path) -> None:
        self.dir = Path(sessions_dir)

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------
    def _ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def new_session(
        provider: str = "",
        model: str = "",
        mode: str = "standard",
    ) -> dict:
        """构造一个空会话对象（不落盘）。"""
        now = datetime.now().isoformat(timespec="milliseconds")
        return {
            "id": f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
            "created_at": now,
            "updated_at": now,
            "provider": provider,
            "model": model,
            "mode": mode,
            "messages": [],
            "current_image": None,
        }

    def _path(self, session_id: str) -> Path:
        return self.dir / f"{session_id}.json"

    # ------------------------------------------------------------------
    # 保存 / 读取
    # ------------------------------------------------------------------
    def save(self, session: dict) -> Path:
        """保存（或覆盖）一个会话，返回文件路径。自动刷新 updated_at。"""
        self._ensure_dir()
        session["updated_at"] = datetime.now().isoformat(timespec="milliseconds")
        path = self._path(session["id"])
        path.write_text(
            json.dumps(session, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load(self, session_id: str) -> Optional[dict]:
        """按 ID 读取会话；不存在或损坏返回 None。"""
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None

    def latest(self) -> Optional[dict]:
        """返回最近更新的会话（用于「恢复上次对话」），没有则 None。"""
        sessions = self.list_sessions()
        if not sessions:
            return None
        return self.load(sessions[0]["id"])

    # ------------------------------------------------------------------
    # 列表 / 删除
    # ------------------------------------------------------------------
    def list_sessions(self, limit: int = 50) -> List[dict]:
        """按更新时间倒序列出会话摘要（不含 messages，避免大对象）。

        thumb 为会话中第一张生成图路径（无则空串），供侧栏缩略图使用。
        """
        if not self.dir.exists():
            return []
        items: List[dict] = []
        for p in self.dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                msgs = data.get("messages") or []
                thumb = ""
                for m in msgs:
                    if m.get("role") == "assistant" and m.get("type") == "images":
                        paths = m.get("paths") or []
                        if paths:
                            thumb = paths[0]
                            break
                items.append(
                    {
                        "id": data.get("id", p.stem),
                        "updated_at": data.get("updated_at", ""),
                        "model": data.get("model", ""),
                        "message_count": len(msgs),
                        "thumb": thumb,
                        # 首条用户文字消息，作为列表预览
                        "preview": next(
                            (
                                m.get("text", "")[:40]
                                for m in msgs
                                if m.get("role") == "user" and m.get("type") == "text"
                            ),
                            "",
                        ),
                    }
                )
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
        items.sort(key=lambda x: x["updated_at"], reverse=True)
        return items[:limit]

    def delete(self, session_id: str) -> bool:
        """删除一个会话文件，返回是否删除成功。"""
        path = self._path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

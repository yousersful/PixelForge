"""生成历史存储（SQLite）。

记录每次生成：提示词、模型、尺寸、保存路径、时间等。
仅保存在本地。
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class HistoryRecord:
    """一条生成历史记录。"""

    prompt: str
    model: str
    size: str
    path: str
    seed: Optional[int] = None
    created_at: str = ""  # ISO 时间，留空则自动填充
    id: Optional[int] = None


class HistoryStore:
    """基于 SQLite 的历史记录存储。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._conn = None
        self._lock = threading.Lock()  # 保护连接跨线程使用

    # ------------------------------------------------------------------
    # 连接 / 初始化
    # ------------------------------------------------------------------
    def connect(self) -> "HistoryStore":
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False：允许在后台生成线程中写入历史记录
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt TEXT NOT NULL,
                    model TEXT NOT NULL,
                    size TEXT NOT NULL,
                    path TEXT NOT NULL,
                    seed INTEGER,
                    created_at TEXT NOT NULL
                )
                """
            )
        return self

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    # ------------------------------------------------------------------
    # 增 / 查 / 删
    # ------------------------------------------------------------------
    def add(self, record: HistoryRecord) -> int:
        """插入一条记录，返回自增 ID。"""
        if not record.created_at:
            record.created_at = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO history (prompt, model, size, path, seed, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.prompt,
                    record.model,
                    record.size,
                    record.path,
                    record.seed,
                    record.created_at,
                ),
            )
            self._conn.commit()
            record.id = cur.lastrowid
            return record.id

    def recent(self, limit: int = 50) -> List[HistoryRecord]:
        """返回最近的生成记录（倒序）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, prompt, model, size, path, seed, created_at "
                "FROM history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            HistoryRecord(
                id=r[0], prompt=r[1], model=r[2], size=r[3],
                path=r[4], seed=r[5], created_at=r[6],
            )
            for r in rows
        ]

    def clear(self) -> None:
        """清空全部历史。"""
        with self._lock:
            self._conn.execute("DELETE FROM history")
            self._conn.commit()

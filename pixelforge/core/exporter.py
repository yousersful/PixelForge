"""生成历史导出。

支持两种方式：
  - 仅元数据：导出为单个 JSON / CSV 文件
  - 包含图片：导出一个文件夹，内含 manifest(JSON/CSV) + images/ 图片副本
"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Union

from pixelforge.core.storage import HistoryRecord

# 导出字段顺序
_FIELDS = ["time", "prompt", "model", "size", "seed", "image"]


def _record_dict(rec: HistoryRecord, image_ref: str | None = None) -> dict:
    """把一条记录转成可导出的字典。"""
    return {
        "time": rec.created_at,
        "prompt": rec.prompt,
        "model": rec.model,
        "size": rec.size,
        "seed": rec.seed,
        "image": image_ref if image_ref is not None else rec.path,
    }


def _write(rows: List[dict], format: str, path: Path) -> None:
    """按格式写入文件。"""
    if format == "csv":
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    else:  # json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def export_history(
    records: List[HistoryRecord],
    format: str = "json",
    include_images: bool = False,
    dest_dir: Union[str, Path] = ".",
    prefix: str = "history",
) -> Path:
    """导出历史记录，返回导出的文件/文件夹路径。

    - include_images=False：单个 manifest 文件（不含图）
    - include_images=True ：一个文件夹，内含 manifest + images/ 副本
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    # ---- 包含图片：导出为文件夹 ----
    if include_images:
        out_dir = dest / f"{prefix}_{_stamp()}"
        out_dir.mkdir(parents=True)
        img_dir = out_dir / "images"
        img_dir.mkdir()

        rows: List[dict] = []
        for rec in records:
            src = Path(rec.path)
            if src.exists():
                new = img_dir / src.name
                shutil.copy2(src, new)
                rows.append(_record_dict(rec, f"images/{new.name}"))
            else:
                rows.append(_record_dict(rec, rec.path))  # 保留原路径（文件缺失）

        _write(rows, format, out_dir / f"manifest.{format}")
        return out_dir

    # ---- 仅元数据：单个文件 ----
    ext = "csv" if format == "csv" else "json"
    file = dest / f"{prefix}.{ext}"
    _write([_record_dict(r) for r in records], format, file)
    return file

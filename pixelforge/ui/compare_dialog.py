"""批量对比对话框：将多张生成结果以大图并排同时展示，方便对比差异。"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from pixelforge.utils.helpers import error, info, load_pixmap, save_image_dialog

MAX_PREVIEW = 900  # 单张对比预览的最大边长


class CompareDialog(QDialog):
    """多图并排对比。"""

    def __init__(self, paths: List[Path], parent=None) -> None:
        super().__init__(parent)
        self.paths = list(paths)
        self.setWindowTitle(f"对比 - 共 {len(self.paths)} 张")
        self.resize(920, 680)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setSpacing(20)
        layout.setContentsMargins(10, 10, 10, 10)
        for i, path in enumerate(self.paths):
            layout.addWidget(self._make_card(path, i))
        layout.addStretch(1)
        scroll.setWidget(container)

        main = QVBoxLayout(self)
        hint = QLabel("各结果并排显示，可滚动查看；每张可单独保存")
        hint.setStyleSheet("color:#666; padding:4px;")
        main.addWidget(hint)
        main.addWidget(scroll, 1)

    # ------------------------------------------------------------------
    def _make_card(self, path: Path, index: int) -> QWidget:
        """生成单张图片的卡片（大图 + 标题 + 保存按钮）。"""
        card = QWidget()
        v = QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)

        pixmap = load_pixmap(str(path), max_size=MAX_PREVIEW)
        img = QLabel()
        img.setAlignment(Qt.AlignCenter)
        img.setPixmap(pixmap)
        img.setMinimumSize(240, 240)
        v.addWidget(img, 1)

        title = QLabel(f"#{index + 1}   {path.name}")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight:bold; padding:4px;")
        v.addWidget(title)

        save_btn = QPushButton("保存这张")
        save_btn.clicked.connect(lambda _=False, p=path: self._save(p))
        v.addWidget(save_btn)
        return card

    def _save(self, path: Path) -> None:
        """复制当前图片到用户选择的位置。"""
        dst = save_image_dialog(self, path.name)
        if dst:
            try:
                shutil.copy2(path, dst)
            except OSError as exc:
                error(self, "保存失败", str(exc))
                return
            info(self, "保存成功", f"图片已保存到：\n{dst}")

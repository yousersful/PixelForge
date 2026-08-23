"""收藏夹面板：以缩略图网格展示已收藏的图片，可打开、取消收藏。"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QSize, Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon
from PyQt5.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from pixelforge.utils.helpers import error, load_pixmap

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}
_ICON_SIZE = QSize(160, 160)
_GRID_SIZE = QSize(180, 210)


class FavoritesPanel(QWidget):
    """收藏夹浏览面板。"""

    def __init__(self, service, parent=None) -> None:
        super().__init__(parent)
        self.service = service

        root = QVBoxLayout(self)

        # 顶部操作栏
        bar = QHBoxLayout()
        bar.addWidget(QLabel("已收藏的图片（双击打开原图）"))
        bar.addStretch(1)

        self.open_btn = QPushButton("打开原图")
        self.open_btn.clicked.connect(self.open_selected)
        bar.addWidget(self.open_btn)

        self.unfav_btn = QPushButton("取消收藏")
        self.unfav_btn.clicked.connect(self.unfavorite_selected)
        bar.addWidget(self.unfav_btn)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_btn)
        root.addLayout(bar)

        # 缩略图网格
        self.list = QListWidget(self)
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(_ICON_SIZE)
        self.list.setGridSize(_GRID_SIZE)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda _item: self.open_selected())
        root.addWidget(self.list, 1)

        self.refresh()

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """重新扫描收藏夹目录并填充网格。"""
        self.list.clear()
        like_dir = self.service.favorite_dir
        if not like_dir.exists():
            self._set_empty("收藏夹为空")
            return

        paths = sorted(
            (p for p in like_dir.iterdir() if p.is_file()),
            key=lambda p: p.name.lower(),
        )
        image_paths = [p for p in paths if p.suffix.lower() in _IMAGE_SUFFIXES]
        if not image_paths:
            self._set_empty("收藏夹为空")
            return

        for p in image_paths:
            pixmap = load_pixmap(str(p), max_size=_ICON_SIZE.width() * 2)
            if pixmap.isNull():
                pixmap = pixmap  # 保留无效图，仍显示占位图标
            item = QListWidgetItem(QIcon(pixmap), p.name)
            item.setData(Qt.UserRole, str(p))
            item.setToolTip(str(p))
            self.list.addItem(item)

    def _set_empty(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        self.list.addItem(item)

    def _selected_path(self) -> str | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------
    def open_selected(self) -> None:
        """用系统默认程序打开选中的图片。"""
        path = self._selected_path()
        if not path:
            return
        if Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            error(self, "无法打开", "图片文件不存在或已被移动。")

    def unfavorite_selected(self) -> None:
        """取消收藏选中的图片。"""
        path = self._selected_path()
        if not path:
            return
        name = Path(path).name
        if (
            QMessageBox.question(
                self,
                "取消收藏",
                f"确定要取消收藏 “{name}” 吗？\n（将从收藏夹中移除）",
            )
            == QMessageBox.Yes
        ):
            self.service.unfavorite(path)
            self.refresh()

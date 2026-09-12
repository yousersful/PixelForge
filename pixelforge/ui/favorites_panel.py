"""收藏夹面板（设计稿 Page 6）：按月分组缩略图 + 可点击时间轴 + 日期搜索。"""
from __future__ import annotations

import time
from pathlib import Path

from PyQt5.QtCore import QSize, Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from pixelforge.ui.month_helpers import (
    cn_month_label, group_by_month, match_date, month_key_of_ts,
)
from pixelforge.ui.timeline import MonthTimeline
from pixelforge.utils.helpers import error, load_pixmap

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}
_ICON_SIZE = QSize(150, 150)
_GRID_W, _GRID_H = 170, 200
_COLS = 4


class _FavCell(QWidget):
    """一个收藏图格子：缩略图 + 收藏时间，右键操作。"""

    def __init__(self, path: str, when: str, parent=None) -> None:
        super().__init__(parent)
        self.path = path
        self.setFixedSize(_GRID_W, _GRID_H)
        col = QVBoxLayout(self)
        col.setContentsMargins(6, 6, 6, 6)
        col.setSpacing(4)

        img = QLabel()
        img.setPixmap(load_pixmap(path, _ICON_SIZE.width() * 2))
        img.setFixedSize(_ICON_SIZE)
        img.setScaledContents(True)
        img.setAlignment(Qt.AlignCenter)
        img.setStyleSheet("border-radius:8px;")
        col.addWidget(img)

        tag = QLabel(when)
        tag.setProperty("class", "hint")
        tag.setAlignment(Qt.AlignCenter)
        col.addWidget(tag)


class FavoritesPanel(QWidget):
    """收藏夹按月分组展示。"""

    def __init__(self, service, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self._groups: list[dict] = []  # [{month, label, items}]
        self._month_widgets: dict[str, int] = {}  # month -> 滚动偏移（索引）

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 20, 16, 20)
        root.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(12)

        # 顶部标题栏
        bar = QHBoxLayout()
        self.title = QLabel("收藏夹")
        self.title.setProperty("class", "pageTitle")
        bar.addWidget(self.title)
        cap = QLabel("——你喜欢的都在此处")
        cap.setProperty("class", "pageCaption")
        bar.addWidget(cap)
        bar.addStretch(1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("输入日期来搜索相关图片……")
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self._apply_filter)
        bar.addWidget(self.search)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_btn)
        left.addLayout(bar)

        # 分组滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.holder = QWidget()
        self.holder_col = QVBoxLayout(self.holder)
        self.holder_col.setContentsMargins(0, 0, 0, 0)
        self.holder_col.setSpacing(14)
        self.holder_col.addStretch(1)
        self.scroll.setWidget(self.holder)
        left.addWidget(self.scroll, 1)

        root.addLayout(left, 1)

        # 时间轴
        self.timeline = MonthTimeline()
        self.timeline.month_clicked.connect(self._jump_to_month)
        root.addWidget(self.timeline)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        items: list[dict] = []
        like_dir = self.service.favorite_dir
        if like_dir.exists():
            for p in like_dir.iterdir():
                if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES:
                    try:
                        mt = p.stat().st_mtime
                    except OSError:
                        mt = None
                    items.append(
                        {
                            "path": str(p),
                            "ts": mt,
                            "month": month_key_of_ts(mt),
                            "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(mt)),
                        }
                    )
        # 按时间倒序
        items.sort(key=lambda x: x["date"], reverse=True)
        self._all_months = group_by_month(items)
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search.text()
        shown: list[dict] = []
        for g in self._all_months:
            its = [it for it in g["items"] if match_date(query, it["month"], it["date"])]
            if its:
                shown.append({**g, "items": its})
        self._render(shown, query)

    def _render(self, groups: list[dict], query: str = "") -> None:
        # 清空
        while self.holder_col.count() > 1:
            item = self.holder_col.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not groups:
            if not self._all_months and not query:
                # 真·空收藏夹（有图被滤掉或正在搜索时给搜索反馈）：
                # 居中的缘分文案
                self.holder_col.insertStretch(0)
                empty = QLabel("缘分到来之时，你就会遇见自己喜欢的图片")
                empty.setProperty("class", "pageCaption")
                empty.setAlignment(Qt.AlignCenter)
                self.holder_col.insertWidget(1, empty)
            else:
                empty = QLabel("没有符合条件的收藏")
                empty.setProperty("class", "hint")
                self.holder_col.insertWidget(0, empty)
        else:
            for g in groups:
                header = QLabel(g["label"])
                header.setProperty("class", "pageCaption")
                self.holder_col.insertWidget(self.holder_col.count() - 1, header)
                grid = QWidget()
                gl = QGridLayout(grid)
                gl.setContentsMargins(0, 0, 0, 0)
                gl.setSpacing(10)
                for i, it in enumerate(g["items"]):
                    cell = _FavCell(it["path"], it["date"][:10])  # 显示 YYYY-MM-DD
                    cell.setContextMenuPolicy(Qt.CustomContextMenu)
                    cell.customContextMenuRequested.connect(
                        lambda pos, p=it["path"]: self._menu(p).exec_(cell.mapToGlobal(pos))
                    )
                    cell.mouseDoubleClickEvent = lambda _e, p=it["path"]: self._open(p)
                    gl.addWidget(cell, i // _COLS, i % _COLS)
                self.holder_col.insertWidget(self.holder_col.count() - 1, grid)

        # 时间轴
        months = [
            {"month": g["month"], "label": g["label"], "count": len(g["items"])}
            for g in groups
        ]
        self.timeline.set_months(months)

    def _menu(self, path: str) -> QMenu:
        menu = QMenu(self)
        menu.addAction("打开原图", lambda: self._open(path))
        menu.addAction("取消收藏", lambda: self._unfav(path))
        return menu

    def _open(self, path: str) -> None:
        if Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            error(self, "无法打开", "图片文件不存在或已被移动。")

    def _unfav(self, path: str) -> None:
        if (
            QMessageBox.question(
                self,
                "取消收藏",
                f"确定要取消收藏 “{Path(path).name}” 吗？\n（将从收藏夹中移除）",
            )
            == QMessageBox.Yes
        ):
            self.service.unfavorite(path)
            self.refresh()

    def _jump_to_month(self, month: str) -> None:
        """滚动到指定月份分组。"""
        sb = self.scroll.verticalScrollBar()
        # 找到该月标题在 holder 里的位置
        widget = self.holder
        for i in range(widget.layout().count()):
            w = widget.layout().itemAt(i).widget()
            if isinstance(w, QLabel) and w.text() in (
                cn_month_label(month),
                month,
            ):
                sb.setValue(w.y())
                self.timeline.highlight(month)
                return

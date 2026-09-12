"""历史记录面板（设计稿 Page 8）：表格（时间排序）+ 时间轴 + 日期搜索 + 导出 CSV/JSON。"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from pixelforge.core.exporter import export_history
from pixelforge.ui.month_helpers import (
    cn_month_label, match_date, month_key_of,
)
from pixelforge.ui.timeline import MonthTimeline
from pixelforge.utils.helpers import error, info

_COLS = ("时间", "提示词", "模型", "存储路径")


def _display_date(created_at: str) -> str:
    """把 ISO/任意时间字符串转成 'YYYY-MM-DD HH:MM' 显示；失败原样返回。"""
    s = created_at.strip()
    if "T" in s:
        s = s.replace("T", " ")
    if len(s) >= 16:
        return s[:16]
    return s


class HistoryPanel(QWidget):
    """历史生成记录表格。"""

    def __init__(self, history, parent=None) -> None:
        super().__init__(parent)
        self.history = history
        self._records: list = []
        self._sort_asc = False

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 20, 16, 20)
        root.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(12)

        # 顶部标题栏
        bar = QHBoxLayout()
        title = QLabel("历史记录")
        title.setProperty("class", "pageTitle")
        bar.addWidget(title)
        self.cap = QLabel("——每一点灵感都值得被记录")
        self.cap.setProperty("class", "pageCaption")
        bar.addWidget(self.cap)
        bar.addStretch(1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("输入日期来搜索相关图片……")
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self.refresh)
        bar.addWidget(self.search)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_btn)

        self.csv_btn = QPushButton("导出 CSV")
        self.csv_btn.clicked.connect(lambda: self._export("csv"))
        bar.addWidget(self.csv_btn)

        self.json_btn = QPushButton("导出 JSON")
        self.json_btn.clicked.connect(lambda: self._export("json"))
        bar.addWidget(self.json_btn)
        left.addLayout(bar)

        # 表格
        self.table = QTableWidget(0, len(_COLS), self)
        self.table.setHorizontalHeaderLabels(list(_COLS))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._row_menu)
        # 点击表头排序（时间列）
        header.setSortIndicatorShown(True)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        self.table.doubleClicked.connect(self._open_image)
        left.addWidget(self.table, 1)

        root.addLayout(left, 1)

        # 时间轴
        self.timeline = MonthTimeline()
        self.timeline.month_clicked.connect(self._jump_to_month)
        root.addWidget(self.timeline)

        self.refresh()

    # ------------------------------------------------------------------
    def resizeEvent(self, ev) -> None:  # noqa: N802
        # 窄窗口时隐藏副标题，避免工具栏挤压
        self.cap.setVisible(self.width() >= 1150)
        super().resizeEvent(ev)

    def refresh(self) -> None:
        records = self.history.recent(10000)
        query = self.search.text()
        self._records = [
            r for r in records
            if match_date(query, month_key_of(r.created_at), r.created_at)
        ]
        self._fill_table()

    def _fill_table(self) -> None:
        rows = list(reversed(self._records))  # 时间倒序在前
        self.table.setRowCount(len(rows))
        for row, rec in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(_display_date(rec.created_at)))
            self.table.setItem(row, 1, QTableWidgetItem(rec.prompt))
            self.table.setItem(row, 2, QTableWidgetItem(rec.model))
            self.table.setItem(row, 3, QTableWidgetItem(rec.path))
            self.table.item(row, 0).setData(Qt.UserRole, rec)

        # 时间轴：按月份统计当前行数
        from collections import Counter
        cnt = Counter(month_key_of(r.created_at) for r in rows)
        months = [
            {"month": m, "label": cn_month_label(m), "count": c}
            for m, c in sorted(cnt.items(), reverse=True)
        ]
        self.timeline.set_months(months)

    def _on_header_clicked(self, col: int) -> None:
        if col != 0:
            return
        self._sort_asc = not self._sort_asc
        self._records.sort(
            key=lambda r: r.created_at,
            reverse=not self._sort_asc,
        )
        self._fill_table()

    def _row_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        rec = self.table.item(row, 0).data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("打开图片", lambda: self._open_path(rec.path))
        menu.addAction("复制提示词", lambda: self._copy(rec.prompt))
        menu.addAction("复制路径", lambda: self._copy(rec.path))
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _copy(self, text: str) -> None:
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def _open_image(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        rec = self.table.item(row, 0).data(Qt.UserRole)
        self._open_path(rec.path)

    def _open_path(self, path: str) -> None:
        if Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            error(self, "无法打开", "图片文件不存在或已被移动。")

    def _jump_to_month(self, month: str) -> None:
        """定位到指定月份的第一行。"""
        for row in range(self.table.rowCount()):
            rec = self.table.item(row, 0).data(Qt.UserRole)
            if rec and month_key_of(rec.created_at) == month:
                self.table.selectRow(row)
                self.table.scrollToItem(self.table.item(row, 0))
                self.timeline.highlight(month)
                return

    # ------------------------------------------------------------------
    def _export(self, fmt: str) -> None:
        records = self._records
        if not records:
            error(self, "无数据", "当前没有可导出的历史记录。")
            return
        ext = "csv" if fmt == "csv" else "json"
        file, _ = QFileDialog.getSaveFileName(
            self,
            "导出历史记录",
            f"history.{ext}",
            f"{ext.upper()} 文件 (*.{ext})",
        )
        if not file:
            return
        try:
            out = export_history(
                records, fmt, False, Path(file).parent, prefix=Path(file).stem,
            )
            info(self, "导出成功", f"已导出到：\n{out}")
        except OSError as exc:
            error(self, "导出失败", str(exc))

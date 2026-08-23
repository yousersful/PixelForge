"""历史记录面板：以列表展示最近生成记录，可双击查看并打开图片。"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import (
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from pixelforge.core.exporter import export_history
from pixelforge.ui.export_dialog import ExportDialog
from pixelforge.utils.helpers import error, info


class HistoryPanel(QWidget):
    """展示历史生成的表格面板。"""

    def __init__(self, history, parent=None) -> None:
        super().__init__(parent)
        self.history = history

        root = QVBoxLayout(self)
        root.addWidget(QLabel("最近生成记录（双击打开图片）"))

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["时间", "描述", "模型", "图片路径"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.doubleClicked.connect(self._open_image)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        bottom.addWidget(self.refresh_btn)

        self.export_btn = QPushButton("导出")
        self.export_btn.clicked.connect(self._export)
        bottom.addWidget(self.export_btn)
        bottom.addStretch(1)
        root.addLayout(bottom)

        self.refresh()

    def refresh(self) -> None:
        """重新加载历史记录。"""
        records = self.history.recent(100)
        self.table.setRowCount(len(records))
        for row, rec in enumerate(records):
            self.table.setItem(row, 0, QTableWidgetItem(rec.created_at))
            self.table.setItem(row, 1, QTableWidgetItem(rec.prompt))
            self.table.setItem(row, 2, QTableWidgetItem(rec.model))
            self.table.setItem(row, 3, QTableWidgetItem(rec.path))

    def _export(self) -> None:
        """导出历史记录。"""
        records = self.history.recent(10000)
        if not records:
            error(self, "无数据", "当前没有可导出的历史记录。")
            return

        dialog = ExportDialog(self)
        if dialog.exec_() != ExportDialog.Accepted:
            return
        fmt = dialog.selected_format
        incl = dialog.include_images

        try:
            if incl:
                # 包含图片 -> 选择目标文件夹，导出为子文件夹
                dir_ = QFileDialog.getExistingDirectory(
                    self, "选择导出位置"
                )
                if not dir_:
                    return
                out = export_history(
                    records, fmt, True, dir_, prefix="history"
                )
                info(self, "导出成功", f"已导出到：\n{out}")
            else:
                # 仅元数据 -> 选择文件路径
                ext = "csv" if fmt == "csv" else "json"
                file, _ = QFileDialog.getSaveFileName(
                    self,
                    "导出历史",
                    f"history.{ext}",
                    f"{ext.upper()} 文件 (*.{ext})",
                )
                if not file:
                    return
                out = export_history(
                    records, fmt, False, Path(file).parent,
                    prefix=Path(file).stem,
                )
                info(self, "导出成功", f"已导出到：\n{out}")
        except OSError as exc:
            error(self, "导出失败", str(exc))

    def _open_image(self) -> None:
        """用系统默认程序打开所选记录的图片。"""
        row = self.table.currentRow()
        path = self.table.item(row, 3).text() if row >= 0 else ""
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            error(self, "无法打开", "图片文件不存在或已被移动。")

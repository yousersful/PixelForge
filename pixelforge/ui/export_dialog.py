"""导出历史对话框：选择格式与是否包含图片。"""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QVBoxLayout,
)


class ExportDialog(QDialog):
    """导出选项对话框。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出历史")
        self.setMinimumWidth(380)

        form = QFormLayout()
        form.addRow("格式:", QLabel("JSON / CSV（可用 Excel 打开）"))

        self.format_combo = QComboBox()
        self.format_combo.addItem("JSON", "json")
        self.format_combo.addItem("CSV（表格）", "csv")
        form.addRow("导出格式:", self.format_combo)

        self.include_images_box = QCheckBox("包含图片（导出为一个文件夹）")
        self.include_images_box.setToolTip(
            "勾选后会把图片一起复制进导出的文件夹；不勾选则只导出记录文本"
        )
        form.addRow(self.include_images_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @property
    def selected_format(self) -> str:
        return self.format_combo.currentData()

    @property
    def include_images(self) -> bool:
        return self.include_images_box.isChecked()

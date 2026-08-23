"""通用工具函数。"""
from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QDoubleSpinBox, QFileDialog, QGridLayout, QGroupBox, QLabel,
    QMessageBox, QSpinBox,
)


class OptimizeWorker(QThread):
    """后台调用 LLM 优化提示词，避免阻塞 UI。"""

    finished = pyqtSignal(str)  # 优化结果
    failed = pyqtSignal(str)    # 错误信息

    def __init__(self, service, text: str) -> None:
        super().__init__()
        self.service = service
        self.text = text

    def run(self) -> None:
        try:
            self.finished.emit(self.service.optimize_prompt(self.text))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))



def load_pixmap(path: str, max_size: int = 1024) -> QPixmap:
    """加载图片并等比缩放到不超过 max_size，用于预览。"""
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return pixmap
    if pixmap.width() > max_size or pixmap.height() > max_size:
        pixmap = pixmap.scaled(
            max_size, max_size,
            aspectRatioMode=1,  # KeepAspectRatio
            transformMode=0,    # FastTransformation
        )
    return pixmap


class AdvancedParams(QGroupBox):
    """可折叠的高级参数区（勾选才生效）。

    三个参数留空(=0/默认)时不发送，由模型使用默认值：
      - 引导强度 guidance_scale（数值越大越贴合提示词）
      - 推理步数 num_inference_steps（越大越精细但越慢）
      - CFG scale cfg_scale
    """

    def __init__(self, parent=None) -> None:
        super().__init__("高级参数", parent)
        self.setCheckable(True)
        self.setChecked(False)

        grid = QGridLayout(self)

        grid.addWidget(QLabel("引导强度"), 0, 0)
        self.guidance_scale = QDoubleSpinBox()
        self.guidance_scale.setRange(0, 30)
        self.guidance_scale.setDecimals(1)
        self.guidance_scale.setSingleStep(0.5)
        self.guidance_scale.setValue(0)
        self.guidance_scale.setSpecialValueText("默认")
        self.guidance_scale.setToolTip(
            "数值越大越严格贴合提示词，过高可能导致过曝"
        )
        grid.addWidget(self.guidance_scale, 0, 1)

        grid.addWidget(QLabel("推理步数"), 1, 0)
        self.steps = QSpinBox()
        self.steps.setRange(0, 150)
        self.steps.setValue(0)
        self.steps.setSpecialValueText("默认")
        self.steps.setToolTip("步数越多越精细，但生成越慢")
        grid.addWidget(self.steps, 1, 1)

        grid.addWidget(QLabel("CFG scale"), 2, 0)
        self.cfg_scale = QDoubleSpinBox()
        self.cfg_scale.setRange(0, 30)
        self.cfg_scale.setDecimals(1)
        self.cfg_scale.setSingleStep(0.5)
        self.cfg_scale.setValue(0)
        self.cfg_scale.setSpecialValueText("默认")
        self.cfg_scale.setToolTip("分类器引导强度，多数模型用不到")
        grid.addWidget(self.cfg_scale, 2, 1)

    def values(self) -> dict:
        """返回应发送的高级参数字典（值为 0 的项省略）。"""
        out: dict = {}
        if not self.isChecked():
            return out
        g = self.guidance_scale.value()
        s = self.steps.value()
        c = self.cfg_scale.value()
        if g > 0:
            out["guidance_scale"] = g
        if s > 0:
            out["num_inference_steps"] = s
        if c > 0:
            out["cfg_scale"] = c
        return out


def save_image_dialog(parent, default_name: str = "pixelforge.png") -> str | None:
    """弹出保存对话框，返回用户选择的路径；取消则返回 None。"""
    path, _ = QFileDialog.getSaveFileName(
        parent,
        "保存图片",
        default_name,
        "PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg);;所有文件 (*)",
    )
    return path or None


def info(parent, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def warn(parent, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def error(parent, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)

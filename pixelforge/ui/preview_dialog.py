"""大图预览：无边框模态遮罩层。

双击缩略图打开；按住左键拖动、滚轮以鼠标位置为锚点缩放、
Esc 或再次双击退出。不依赖任何图片处理依赖，QPixmap 直读原图
保证放大后清晰（缩略图用的是 load_pixmap 的缩小版）。
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence, QPixmap
from PyQt5.QtWidgets import QLabel, QShortcut, QWidget

ZOOM_MIN = 0.2   # 相对"适应窗口"基准的最小倍率
ZOOM_MAX = 8.0
OVERLAY_BG = "rgba(10, 12, 16, 0.88)"


class ImagePreviewDialog(QWidget):
    """全窗口遮罩式大图预览。"""

    def __init__(self, parent, path: str) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setStyleSheet(f"background-color: {OVERLAY_BG};")
        self.setCursor(Qt.OpenHandCursor)

        host = parent.window() if parent is not None else None
        if host is not None:
            self.setGeometry(host.geometry())

        self._pm: QPixmap = QPixmap(path)
        self._drag_start = None
        self._label_start = None

        if self._pm.isNull():
            self._label = QLabel("图片无法加载", self)
            self._label.setAlignment(Qt.AlignCenter)
            self._label.setStyleSheet("color: #9CA3AF; font-size: 15px;")
            self._base = None
        else:
            # 基准尺寸：适应窗口的 90%
            avail_w = max(320, self.width() - 80)
            avail_h = max(240, self.height() - 120)
            self._base = min(avail_w / self._pm.width(),
                             avail_h / self._pm.height(), 1.0)
            self._factor = 1.0
            self._label = QLabel(self)
            self._label.setScaledContents(True)
            self._label.setCursor(Qt.OpenHandCursor)
            self._apply_zoom()

        hint = QLabel("拖动移动 · 滚轮缩放 · 双击或 Esc 退出", self)
        hint.setStyleSheet("color: #E7EAF0; background: rgba(15, 23, 42, 0.72);"
                           " border-radius: 8px; padding: 6px 14px;"
                           " font-size: 12px;")
        self._hint = hint

        QShortcut(QKeySequence(Qt.Key_Escape), self, self.close)
        self._center_children()

    # ------------------------------------------------------------------
    def resizeEvent(self, ev) -> None:  # noqa: N802
        self._center_children()
        super().resizeEvent(ev)

    def _center_children(self) -> None:
        self._hint.adjustSize()
        self._hint.move((self.width() - self._hint.width()) // 2,
                        self.height() - self._hint.height() - 18)
        if self._base is not None and self._label is not None \
                and not hasattr(self, "_placed"):
            w = int(self._pm.width() * self._base * self._factor)
            h = int(self._pm.height() * self._base * self._factor)
            self._label.resize(w, h)
            self._label.move((self.width() - w) // 2, (self.height() - h) // 2)
            self._placed = True

    # ------------------------------------------------------------------
    # 缩放（以鼠标位置为锚点）
    # ------------------------------------------------------------------
    def wheelEvent(self, ev) -> None:  # noqa: N802
        if self._base is None:
            return
        delta = ev.angleDelta().y()
        if delta == 0:
            return
        old_factor = self._factor
        self._factor = max(ZOOM_MIN, min(ZOOM_MAX, self._factor * (1.25 ** (delta / 120))))
        if self._factor == old_factor:
            return
        cursor = ev.pos()  # 窗口坐标
        label_pos = self._label.pos()
        w_old, h_old = self._label.width(), self._label.height()
        w_new = int(self._pm.width() * self._base * self._factor)
        h_new = int(self._pm.height() * self._base * self._factor)
        # 保持光标下的图像点不动
        rel_x = (cursor.x() - label_pos.x()) / w_old
        rel_y = (cursor.y() - label_pos.y()) / h_old
        self._label.resize(w_new, h_new)
        self._label.move(int(cursor.x() - rel_x * w_new),
                         int(cursor.y() - rel_y * h_new))
        self._rescale_pixmap()

    def _apply_zoom(self) -> None:
        if self._base is None:
            return
        w = int(self._pm.width() * self._base * self._factor)
        h = int(self._pm.height() * self._base * self._factor)
        self._label.resize(w, h)
        self._label.move((self.width() - w) // 2, (self.height() - h) // 2)
        self._rescale_pixmap()

    def _rescale_pixmap(self) -> None:
        # SmoothTransformation：缩小清晰，放大优先速度（设备像素直读保底）
        self._label.setPixmap(self._pm.scaled(
            self._label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ------------------------------------------------------------------
    # 拖动
    # ------------------------------------------------------------------
    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.LeftButton:
            self._drag_start = ev.globalPos()
            self._label_start = self._label.pos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._drag_start is not None:
            delta = ev.globalPos() - self._drag_start
            self._label.move(self._label_start + delta)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        self._drag_start = None
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        self.close()


def show_image_preview(parent, path: str) -> None:
    """打开大图预览（模态、随用随建随销毁）。"""
    dlg = ImagePreviewDialog(parent, path)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()

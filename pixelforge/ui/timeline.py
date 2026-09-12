"""可点击的右侧时间轴：竖排月份色块，点击跳转到对应分组（设计稿 Page 6/8）。"""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget


class MonthTimeline(QScrollArea):
    """右侧时间轴。

    set_months([{month, label, count}]) 填充月份按钮（倒序，最近在上）；
    点击某月发射 month_clicked(month)；highlight(month) 高亮当前月。
    """

    month_clicked = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setFixedWidth(132)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        holder = QWidget()
        self.col = QVBoxLayout(holder)
        self.col.setContentsMargins(0, 0, 6, 0)
        self.col.setSpacing(6)
        self.col.setAlignment(Qt.AlignTop)
        title = QLabel("时间轴")
        title.setProperty("class", "hint")
        self.col.addWidget(title)
        self.setWidget(holder)
        self._buttons: list[QPushButton] = []

    def set_months(self, months: list[dict]) -> None:
        """months: [{month, label, count}]。"""
        # 清空「时间轴」标题以外的所有项（含上次遗留的弹簧——
        # 否则弹簧每次刷新累积一条，把按钮越推越低）
        while self.col.count() > 1:
            item = self.col.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()
        self._buttons.clear()
        for m in sorted(months, key=lambda x: x["month"] or "", reverse=True):
            btn = QPushButton()
            btn.setProperty("class", "nav")
            btn.setProperty("month", m["month"])
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(f"跳转到 {m['label']}")
            btn.setText(f"({m['count']}) {m['label']}")
            btn.clicked.connect(
                lambda _=False, month=m["month"]: self.month_clicked.emit(month)
            )
            self.col.addWidget(btn)
            self._buttons.append(btn)
        self.col.addStretch(1)

    def highlight(self, month: str | None) -> None:
        """高亮当前月；None 取消全部高亮。"""
        for btn in self._buttons:
            btn.setChecked(btn.property("month") == month)

    def month_count(self) -> int:
        return len(self._buttons)

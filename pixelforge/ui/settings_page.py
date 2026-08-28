"""设置整页（原型 Page 9）：左侧子导航 返回/通用/提供商/关于。"""
from __future__ import annotations

import requests

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

from pixelforge.models.providers import PROVIDERS, get_provider
from pixelforge.ui.theme import build_qss, resolve_theme
from pixelforge.utils.helpers import error, info

_THEME_LABELS = [("system", "跟随系统"), ("light", "浅色"), ("dark", "深色")]


def _card() -> QFrame:
    card = QFrame()
    card.setProperty("class", "card")
    return card


class ProviderCard(QFrame):
    """一个厂商的设置卡片：APIkey / URL / 启用 / 获取 key / 测试连接。"""

    def __init__(self, config, key_manager, provider, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.key_manager = key_manager
        self.provider = provider
        self.setProperty("class", "card")

        pid = provider.id
        form = QFormLayout(self)
        form.setContentsMargins(20, 16, 20, 16)
        form.setSpacing(10)

        # 标题行：厂商名 + 已保存状态
        title_row = QHBoxLayout()
        name = QLabel(provider.name)
        name.setStyleSheet("font-size:15px; font-weight:600;")
        title_row.addWidget(name)
        title_row.addStretch(1)
        self.status_label = QLabel("")
        title_row.addWidget(self.status_label)
        form.addRow(title_row)

        # API Key（掩码 + 显示切换）
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-xxxx")
        eye = QPushButton("显示")
        eye.setProperty("class", "ghost")
        eye.setCheckable(True)
        eye.toggled.connect(
            lambda on: self.key_edit.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password
            )
        )
        key_row = QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(eye)
        form.addRow("API Key:", key_row)

        # URL（启用自定义端点的厂商需要）
        self.base_url_edit = QLineEdit(
            str(config.get(f"providers.{pid}.base_url", ""))
        )
        self.base_url_edit.setPlaceholderText("例如：https://……（留空用官方默认）")
        form.addRow("URL 地址:", self.base_url_edit)

        # 自定义厂商的模型 ID
        self.models_edit = None
        if pid == "custom":
            self.models_edit = QLineEdit(
                str(config.get("providers.custom.models", ""))
            )
            self.models_edit.setPlaceholderText("多个模型用英文逗号分隔")
            form.addRow("模型 ID:", self.models_edit)

        # 启用（单选：勾选即切换当前厂商）+ 获取 key / 测试连接
        bottom = QHBoxLayout()
        self.enable_check = QCheckBox("启用")
        self.enable_check.setChecked(
            config.get("model.provider", "siliconflow") == pid
        )
        bottom.addWidget(self.enable_check)
        bottom.addStretch(1)
        if provider.doc_url:
            link = QPushButton("点击获取key→")
            link.setProperty("class", "ghost")
            link.setCursor(Qt.PointingHandCursor)
            link.clicked.connect(self._open_doc)
            bottom.addWidget(link)
        test = QPushButton("测试连接")
        test.clicked.connect(self._test_connection)
        bottom.addWidget(test)
        form.addRow(bottom)

        self._refresh_status()

    # ------------------------------------------------------------------
    def _open_doc(self) -> None:
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(self.provider.doc_url))

    def _refresh_status(self) -> None:
        if self.key_manager.has_key(self.provider.id):
            self.status_label.setProperty("class", "statusOk")
            self.status_label.setText("当前APIkey已经保存，去实现你的创意吧~")
        else:
            self.status_label.setProperty("class", "hint")
            self.status_label.setText("未保存 Key")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _test_connection(self) -> None:
        base = self.base_url_edit.text().strip() or self.provider.api_base
        if not base:
            error(self, "测试失败", "请先填写 API 地址（URL）再测试连接。")
            return
        api_key = self.key_edit.text().strip() or self.key_manager.load(self.provider.id)
        if not api_key:
            error(self, "测试失败", "请先填写 API Key 再测试连接。")
            return
        try:
            resp = requests.get(
                f"{base.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=8,
            )
            if resp.status_code == 200:
                try:
                    n = len(resp.json().get("data", []))
                    info(self, "测试连接", f"连接成功！该端点共返回 {n} 个模型。")
                except ValueError:
                    info(self, "测试连接", "连接成功！")
            else:
                error(
                    self, "测试失败",
                    "连接失败了，检查一下APIkey和URL？\n"
                    f"（HTTP {resp.status_code}：{resp.text[:120]}）",
                )
        except requests.RequestException as exc:
            error(self, "测试失败", f"连接失败了，检查一下APIkey和URL？\n（{exc}）")
        self._refresh_status()

    # ------------------------------------------------------------------
    def apply(self) -> None:
        """把卡片当前值写入配置（不做校验，校验由 SettingsPage 统一做）。"""
        pid = self.provider.id
        self.config.set(f"providers.{pid}.base_url", self.base_url_edit.text().strip())
        if self.models_edit is not None:
            self.config.set("providers.custom.models", self.models_edit.text().strip())
        new_key = self.key_edit.text().strip()
        if new_key:
            self.key_manager.save(new_key, pid)
        if self.enable_check.isChecked():
            self.config.set("model.provider", pid)

    def validate(self) -> str | None:
        """保存前校验，返回错误说明或 None。"""
        if self.enable_check.isChecked() and self.provider.id == "custom":
            if not self.base_url_edit.text().strip():
                return "自定义厂商需要填写 API 地址"
            if not [m for m in self.models_edit.text().split(",") if m.strip()]:
                return "自定义厂商需要至少一个模型 ID"
        return None


class SettingsPage(QWidget):
    """设置整页：返回 / 通用 / 提供商（关于为独立页面，由主窗口组装）。"""

    back_requested = pyqtSignal()
    settings_changed = pyqtSignal()  # 保存后发射（刷新模型列表等）

    def __init__(self, config, key_manager, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.key_manager = key_manager

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 左侧子导航
        nav = QWidget()
        nav.setFixedWidth(200)
        nav_col = QVBoxLayout(nav)
        nav_col.setContentsMargins(12, 16, 12, 16)
        nav_col.setSpacing(4)

        self.back_btn = QPushButton("‹  返回")
        self.back_btn.setProperty("class", "nav")
        self.back_btn.clicked.connect(self.back_requested.emit)
        nav_col.addWidget(self.back_btn)

        self.nav_general = QPushButton("⚙  通用")
        self.nav_provider = QPushButton("🖧  提供商")
        for b in (self.nav_general, self.nav_provider):
            b.setProperty("class", "nav")
            b.setCheckable(True)
            nav_col.addWidget(b)
        nav_col.addStretch(1)

        self.stack = QStackedWidget()

        # ---- 通用页 ----
        general = QWidget()
        gcol = QVBoxLayout(general)
        gcol.setContentsMargins(32, 24, 32, 24)
        gcol.setSpacing(16)
        title = QLabel("通用")
        title.setProperty("class", "pageTitle")
        gcol.addWidget(title)

        gcard = _card()
        gform = QFormLayout(gcard)
        gform.setContentsMargins(20, 16, 20, 16)
        gform.setSpacing(14)

        self.theme_combo = QComboBox()
        for value, label in _THEME_LABELS:
            self.theme_combo.addItem(label, value)
        self.theme_combo.setCurrentIndex(
            max(0, self.theme_combo.findData(config.get("appearance.theme", "system")))
        )
        gform.addRow("窗口色调:", self.theme_combo)
        theme_hint = QLabel("设定窗口的主色调：浅色，深色，或是跟随系统")
        theme_hint.setProperty("class", "hint")
        gform.addRow("", theme_hint)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem("中文", "zh-CN")
        gform.addRow("语言:", self.lang_combo)
        lang_hint = QLabel("更多语言支持将在后续版本提供")
        lang_hint.setProperty("class", "hint")
        gform.addRow("", lang_hint)

        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(str(config.effective_image_dir))
        dir_row.addWidget(self.dir_edit, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse)
        gform.addRow("图片存储路径:", dir_row)
        dir_hint = QLabel("更改图片的默认存储路径，默认在项目 data/images/ 下")
        dir_hint.setProperty("class", "hint")
        gform.addRow("", dir_hint)
        gcol.addWidget(gcard)
        gcol.addStretch(1)

        # ---- 提供商页（卡片墙，可滚动）----
        provider_widget = QWidget()
        pcol = QVBoxLayout(provider_widget)
        pcol.setContentsMargins(32, 24, 32, 24)
        pcol.setSpacing(16)
        ptitle = QLabel("提供商")
        ptitle.setProperty("class", "pageTitle")
        pcol.addWidget(ptitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)
        self.provider_cards: list[ProviderCard] = []
        for i, p in enumerate(PROVIDERS):
            card = ProviderCard(config, key_manager, p)
            self.provider_cards.append(card)
            grid.addWidget(card, i // 2, i % 2)
        grid.setRowStretch(grid.rowCount(), 1)
        grid.setColumnStretch(2, 1)
        scroll.setWidget(inner)
        pcol.addWidget(scroll, 1)

        # 保存 / 取消
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(cancel)
        save = QPushButton("保存")
        save.setProperty("class", "primary")
        save.clicked.connect(self._on_save)
        btn_row.addWidget(save)
        pcol.addLayout(btn_row)

        self.stack.addWidget(general)
        self.stack.addWidget(provider_widget)

        self.nav_general.clicked.connect(lambda: self._switch(0))
        self.nav_provider.clicked.connect(lambda: self._switch(1))
        self._switch(0)

        root.addWidget(nav)
        root.addWidget(self.stack, 1)

    # ------------------------------------------------------------------
    def _switch(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_general.setChecked(index == 0)
        self.nav_provider.setChecked(index == 1)

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "选择图片保存目录", self.dir_edit.text()
        )
        if path:
            self.dir_edit.setText(path)

    def _on_cancel(self) -> None:
        # 还原界面值
        self.theme_combo.setCurrentIndex(
            max(0, self.theme_combo.findData(self.config.get("appearance.theme", "system")))
        )
        self.dir_edit.setText(str(self.config.effective_image_dir))
        for card in self.provider_cards:
            card.base_url_edit.setText(
                str(self.config.get(f"providers.{card.provider.id}.base_url", ""))
            )
            if card.models_edit is not None:
                card.models_edit.setText(str(self.config.get("providers.custom.models", "")))
            card.enable_check.setChecked(
                self.config.get("model.provider", "siliconflow") == card.provider.id
            )
            card._refresh_status()

    def _on_save(self) -> None:
        for card in self.provider_cards:
            err = card.validate()
            if err:
                error(self, "无法保存", err)
                return
        theme_value = self.theme_combo.currentData()
        self.config.set("appearance.theme", theme_value)
        self.config.set("paths.image_dir", self.dir_edit.text().strip())
        for card in self.provider_cards:
            card.apply()
        self.config.save()
        # 主题即时生效
        from PyQt5.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(build_qss(resolve_theme(theme_value)))
        info(self, "保存成功", "当前设置已保存，去实现你的创意吧~")
        self.settings_changed.emit()

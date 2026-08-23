"""设置对话框：管理 API Key、选择厂商、配置存储目录。"""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from pixelforge.models.providers import PROVIDERS
from pixelforge.utils.helpers import warn


class SettingsDialog(QDialog):
    """应用设置对话框。"""

    def __init__(self, config, key_manager, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.key_manager = key_manager

        self.setWindowTitle("设置")
        self.setMinimumWidth(460)

        form = QFormLayout()

        # 厂商选择
        self.provider_combo = QComboBox()
        for p in PROVIDERS:
            self.provider_combo.addItem(p.name, p.id)
        idx = self.provider_combo.findData(
            config.get("model.provider", "siliconflow")
        )
        self.provider_combo.setCurrentIndex(max(0, idx))
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("服务商:", self.provider_combo)

        # API 地址（千问/百炼需要填工作区专属 URL，硅基流动可留空用默认）
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText(
            "如 https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        )
        self.base_url_edit.setText(
            str(config.get(f"providers.{self.provider_combo.currentData()}.base_url", ""))
        )
        form.addRow("API 地址:", self.base_url_edit)

        # API Key
        key_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)  # 掩码显示
        self.key_edit.setPlaceholderText("sk-xxxx")
        key_row.addWidget(self.key_edit)
        self.show_btn = QPushButton("显示")
        self.show_btn.setCheckable(True)
        self.show_btn.toggled.connect(
            lambda on: self.key_edit.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password
            )
        )
        key_row.addWidget(self.show_btn)
        form.addRow("API Key:", key_row)

        # 当前已保存 Key 提示
        self.status_label = QLabel("")
        self._refresh_status()
        form.addRow("状态:", self.status_label)

        # 图片保存目录
        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(str(config.effective_image_dir))
        dir_row.addWidget(self.dir_edit)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse)
        form.addRow("图片目录:", dir_row)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "选择图片保存目录", self.dir_edit.text()
        )
        if path:
            self.dir_edit.setText(path)

    def _on_provider_changed(self) -> None:
        """切换服务商时刷新该服务商已保存的 API 地址。"""
        provider_id = self.provider_combo.currentData()
        self.base_url_edit.setText(
            str(self.config.get(f"providers.{provider_id}.base_url", ""))
        )
        self._refresh_status()

    def _refresh_status(self) -> None:
        provider_id = self.provider_combo.currentData()
        if self.key_manager.has_key(provider_id):
            self.status_label.setText("已保存（已加密存储在本地）")
        else:
            self.status_label.setText("未保存 Key")

    def _on_accept(self) -> None:
        provider_id = self.provider_combo.currentData()
        # 厂商
        self.config.set("model.provider", provider_id)
        # API 地址
        self.config.set(
            f"providers.{provider_id}.base_url",
            self.base_url_edit.text().strip(),
        )
        # 图片目录
        self.config.set("paths.image_dir", self.dir_edit.text().strip())
        self.config.save()

        # API Key：若用户输入了新值则保存
        new_key = self.key_edit.text().strip()
        if new_key:
            self.key_manager.save(new_key, provider_id)
        elif not self.key_manager.has_key(provider_id):
            warn(self, "提示", "尚未填写 API Key，生成图片时将无法使用。")

        self.accept()

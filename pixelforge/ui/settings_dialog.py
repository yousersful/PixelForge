"""设置对话框：管理 API Key、选择厂商、配置存储目录。"""
from __future__ import annotations

import requests

from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from pixelforge.models.providers import PROVIDERS, get_provider
from pixelforge.utils.helpers import error, info, warn


class SettingsDialog(QDialog):
    """应用设置对话框。"""

    def __init__(self, config, key_manager, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.key_manager = key_manager

        self.setWindowTitle("设置")
        self.setMinimumWidth(520)

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

        # API 地址（千问/自定义必填，其余可留空用默认）
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText(
            "如 https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        )
        self.base_url_edit.setText(
            str(config.get(f"providers.{self.provider_combo.currentData()}.base_url", ""))
        )
        form.addRow("API 地址:", self.base_url_edit)

        # 模型 ID（仅自定义厂商需要：OpenAI 协议网关无统一模型查询）
        self.models_edit = QLineEdit()
        self.models_edit.setPlaceholderText(
            "多个模型用英文逗号分隔，如 my-model, my-model-v2"
        )
        self.models_edit.setText(
            str(config.get("providers.custom.models", ""))
        )
        self.models_label = QLabel("模型 ID:")
        form.addRow(self.models_label, self.models_edit)

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

        # 连接测试 + 当前已保存 Key 提示
        test_row = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test_connection)
        test_row.addWidget(self.test_btn)
        test_row.addStretch(1)
        self.status_label = QLabel("")
        self._refresh_status()
        test_row.addWidget(self.status_label)
        form.addRow("状态:", test_row)

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
        self._on_provider_changed()

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "选择图片保存目录", self.dir_edit.text()
        )
        if path:
            self.dir_edit.setText(path)

    def _on_provider_changed(self) -> None:
        """切换服务商时刷新该服务商已保存的 API 地址与字段可见性。"""
        provider_id = self.provider_combo.currentData()
        self.base_url_edit.setText(
            str(self.config.get(f"providers.{provider_id}.base_url", ""))
        )
        # 模型 ID 仅自定义厂商显示
        is_custom = provider_id == "custom"
        self.models_label.setVisible(is_custom)
        self.models_edit.setVisible(is_custom)
        self.base_url_edit.setPlaceholderText(
            "例如：https://your-gateway.example.com/v1"
            if is_custom else
            "如 https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        )
        self._refresh_status()

    def _refresh_status(self) -> None:
        provider_id = self.provider_combo.currentData()
        if self.key_manager.has_key(provider_id):
            self.status_label.setText("已保存（已加密存储在本地）")
        else:
            self.status_label.setText("未保存 Key")

    def _test_connection(self) -> None:
        """用当前填写的信息做一次连通性测试（GET {base}/models）。"""
        provider_id = self.provider_combo.currentData()
        provider = get_provider(provider_id) or get_provider("siliconflow")
        base = self.base_url_edit.text().strip() or provider.api_base
        if not base:
            error(self, "测试失败", "请先填写 API 地址（URL）再测试连接。")
            return
        api_key = self.key_edit.text().strip() or self.key_manager.load(provider_id)
        if not api_key:
            error(self, "测试失败", "请先填写 API Key 再测试连接。")
            return

        self.test_btn.setEnabled(False)
        self.status_label.setText("测试中…")
        try:
            resp = requests.get(
                f"{base.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=8,
            )
            if resp.status_code == 200:
                try:
                    n = len(resp.json().get("data", []))
                    msg = f"连接成功！该端点共返回 {n} 个模型。"
                except ValueError:
                    msg = "连接成功！"
                info(self, "测试连接", msg)
            else:
                detail = resp.text[:120].replace("\n", " ")
                error(
                    self, "测试失败",
                    f"连接失败了，检查一下 API Key 和 URL？\n"
                    f"（HTTP {resp.status_code}：{detail}）",
                )
        except requests.RequestException as exc:
            error(
                self, "测试失败",
                f"连接失败了，检查一下 API Key 和 URL？\n（{exc}）",
            )
        finally:
            self.test_btn.setEnabled(True)
            self._refresh_status()

    def _on_accept(self) -> None:
        provider_id = self.provider_combo.currentData()

        # 自定义厂商必填项校验
        if provider_id == "custom":
            missing = []
            if not self.base_url_edit.text().strip():
                missing.append("API 地址")
            if not [
                m for m in self.models_edit.text().split(",") if m.strip()
            ]:
                missing.append("至少一个模型 ID")
            if missing:
                error(self, "无法保存", "自定义厂商需要填写：" + "、".join(missing))
                return

        # 厂商
        self.config.set("model.provider", provider_id)
        # API 地址
        self.config.set(
            f"providers.{provider_id}.base_url",
            self.base_url_edit.text().strip(),
        )
        # 模型 ID（自定义厂商）
        self.config.set("providers.custom.models", self.models_edit.text().strip())
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

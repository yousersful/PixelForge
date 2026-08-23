"""应用主窗口。

布局：顶部工具栏（设置 / 清空历史）+ 中央多页签（生成 / 历史）。
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction, QMainWindow, QMessageBox, QTabWidget, QToolBar,
)

from pixelforge.core.image_service import ImageService
from pixelforge.core.storage import HistoryStore
from pixelforge.security.key_manager import KeyManager
from pixelforge.ui.generate_tab import GenerateTab
from pixelforge.ui.favorites_panel import FavoritesPanel
from pixelforge.ui.history_panel import HistoryPanel
from pixelforge.ui.image_to_image_tab import ImageToImageTab
from pixelforge.ui.settings_dialog import SettingsDialog
from pathlib import Path


class MainWindow(QMainWindow):
    """PixelForge 主窗口。"""

    def __init__(self, config) -> None:
        super().__init__()
        self.config = config
        self.config.ensure_dirs()

        # 初始化底层服务
        self.key_manager = KeyManager(self.config.key_path)
        self.history = HistoryStore(self.config.history_path).connect()
        self.service = ImageService(self.config, self.key_manager, self.history)

        self._setup_ui()
        self._connect_signals()
        self._restore_window_state()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        self.setWindowTitle("PixelForge - AI 图像生成")
        self.setMinimumSize(720, 560)

        # 中央页签
        self.tabs = QTabWidget(self)
        self.generate_tab = GenerateTab(self.config, self.service, self)
        self.img2img_tab = ImageToImageTab(self.config, self.service, self)
        self.history_panel = HistoryPanel(self.history, self)
        self.favorites_panel = FavoritesPanel(self.service, self)
        self.tabs.addTab(self.generate_tab, "文生图")
        self.tabs.addTab(self.img2img_tab, "图生图")
        self.tabs.addTab(self.history_panel, "历史")
        self.tabs.addTab(self.favorites_panel, "收藏夹")
        self.setCentralWidget(self.tabs)

        # 工具栏
        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        self.action_settings = QAction("设置", self)
        self.action_clear = QAction("清空历史", self)
        toolbar.addAction(self.action_settings)
        toolbar.addAction(self.action_clear)

    def _connect_signals(self) -> None:
        self.action_settings.triggered.connect(self.open_settings)
        self.action_clear.triggered.connect(self.clear_history)
        # 文生图 → 图生图“继续编辑”
        self.generate_tab.continue_edit_requested.connect(
            self._send_to_image_edit
        )
        # 切换页签时刷新面板（收藏夹/历史）
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, _index: int) -> None:
        widget = self.tabs.currentWidget()
        if hasattr(widget, "refresh"):
            widget.refresh()

    def _send_to_image_edit(self, path: str) -> None:
        """把文生图结果发送到图生图页作为参考图，并切换过去。"""
        self.img2img_tab.set_reference(Path(path))
        self.img2img_tab.status.setText("已设为参考图，输入编辑指令继续生成")
        self.tabs.setCurrentWidget(self.img2img_tab)
        self.img2img_tab.prompt_edit.setFocus()

    # ------------------------------------------------------------------
    # 窗口状态
    # ------------------------------------------------------------------
    def _restore_window_state(self) -> None:
        size = self.config.get("window")
        self.resize(size.get("width", 1000), size.get("height", 720))
        if size.get("maximized"):
            self.showMaximized()

    def closeEvent(self, event) -> None:  # noqa: N802
        """保存窗口状态并关闭数据库连接。"""
        self.config.set("window.width", self.width())
        self.config.set("window.height", self.height())
        self.config.set("window.maximized", self.isMaximized())
        self.config.save()
        self.history.close()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------
    def open_settings(self) -> None:
        """打开设置对话框。"""
        dialog = SettingsDialog(
            self.config,
            self.key_manager,
            parent=self,
        )
        if dialog.exec_() == SettingsDialog.Accepted:
            # 设置变更后刷新生成页的模型/尺寸列表
            self.generate_tab.refresh_models()
            self.img2img_tab.refresh_models()
            self.history_panel.refresh()

    def clear_history(self) -> None:
        """清空全部生成历史。"""
        if (
            QMessageBox.question(
                self,
                "确认",
                "确定要清空所有生成历史吗？此操作不可撤销。",
            )
            == QMessageBox.Yes
        ):
            self.history.clear()
            self.history_panel.refresh()

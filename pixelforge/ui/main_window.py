"""应用主窗口。

布局：左侧固定侧栏（新的创作 / 收藏夹 / 历史记录 / 恢复上次对话，
底部设置）+ 中央页面栈。

创作页当前仍承载 文生图 / 图生图 两个页签；
对话式创作流上线后由此替换（见 doc/markdown/box1.md）。
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from pixelforge.core.image_service import ImageService
from pixelforge.core.session_store import SessionStore
from pixelforge.core.storage import HistoryStore
from pixelforge.security.key_manager import KeyManager
from pixelforge.ui.about_page import AboutPage
from pixelforge.ui.generate_tab import GenerateTab
from pixelforge.ui.favorites_panel import FavoritesPanel
from pixelforge.ui.history_panel import HistoryPanel
from pixelforge.ui.image_to_image_tab import ImageToImageTab
from pixelforge.ui.settings_page import SettingsPage


class MainWindow(QMainWindow):
    """PixelForge 主窗口。"""

    # 页面索引
    PAGE_CREATE, PAGE_FAV, PAGE_HISTORY, PAGE_SETTINGS, PAGE_ABOUT = range(5)

    def __init__(self, config) -> None:
        super().__init__()
        self.config = config
        self.config.ensure_dirs()

        # 初始化底层服务
        self.key_manager = KeyManager(self.config.key_path)
        self.history = HistoryStore(self.config.history_path).connect()
        self.service = ImageService(self.config, self.key_manager, self.history)
        self.sessions = SessionStore(config.sessions_dir)

        self._setup_ui()
        self._connect_signals()
        self._restore_window_state()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        self.setWindowTitle("PixelForge - AI 图像生成")
        self.setMinimumSize(860, 600)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 左侧栏 ----
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        col = QVBoxLayout(sidebar)
        col.setContentsMargins(12, 16, 12, 16)
        col.setSpacing(6)

        title = QLabel("PixelForge")
        title.setObjectName("appTitle")
        col.addWidget(title)
        col.addSpacing(12)

        self.btn_new = QPushButton("+  新的创作")
        self.btn_new.setProperty("class", "primary")
        self.btn_new.setCursor(Qt.PointingHandCursor)
        col.addWidget(self.btn_new)
        col.addSpacing(6)

        self._nav_group = QButtonGroup(self)
        self.nav_buttons = []
        for label, page in [
            ("☆  收藏夹", self.PAGE_FAV),
            ("🕐  历史记录", self.PAGE_HISTORY),
        ]:
            btn = QPushButton(label)
            btn.setProperty("class", "nav")
            btn.setCheckable(True)
            self._nav_group.addButton(btn)
            btn.clicked.connect(lambda _=False, p=page: self.switch_page(p))
            col.addWidget(btn)
            self.nav_buttons.append(btn)

        # 恢复上次对话（创作流上线后可用）
        self.btn_restore = QPushButton("↺  恢复上次对话")
        self.btn_restore.setProperty("class", "nav")
        self.btn_restore.setEnabled(False)
        self.btn_restore.setToolTip("对话式创作流将在后续更新中可用")
        col.addWidget(self.btn_restore)

        col.addStretch(1)

        line = QFrame()
        line.setProperty("class", "hline")
        col.addWidget(line)

        self.btn_about = QPushButton("关于 PixelForge")
        self.btn_about.setProperty("class", "nav")
        self.btn_about.clicked.connect(lambda: self.switch_page(self.PAGE_ABOUT))
        col.addWidget(self.btn_about)

        self.btn_settings = QPushButton("⚙  设置")
        self.btn_settings.setProperty("class", "nav")
        self.btn_settings.clicked.connect(lambda: self.switch_page(self.PAGE_SETTINGS))
        col.addWidget(self.btn_settings)

        root.addWidget(sidebar)

        # ---- 中央页面栈 ----
        self.stack = QStackedWidget()

        # 创作页：暂以 文生图/图生图 页签承载
        create_page = QWidget()
        create_col = QVBoxLayout(create_page)
        create_col.setContentsMargins(16, 16, 16, 16)
        self.tabs = QTabWidget()
        self.generate_tab = GenerateTab(self.config, self.service, self)
        self.img2img_tab = ImageToImageTab(self.config, self.service, self)
        self.tabs.addTab(self.generate_tab, "文生图")
        self.tabs.addTab(self.img2img_tab, "图生图")
        create_col.addWidget(self.tabs)
        self.stack.addWidget(create_page)

        self.favorites_panel = FavoritesPanel(self.service, self)
        self.stack.addWidget(self.favorites_panel)

        self.history_panel = HistoryPanel(self.history, self)
        self.stack.addWidget(self.history_panel)

        self.settings_page = SettingsPage(self.config, self.key_manager, self)
        self.stack.addWidget(self.settings_page)

        self.about_page = AboutPage(self)
        self.stack.addWidget(self.about_page)

        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        # 文生图 → 图生图“继续编辑”
        self.generate_tab.continue_edit_requested.connect(
            self._send_to_image_edit
        )
        # 设置保存 → 刷新模型列表 / 面板
        self.settings_page.settings_changed.connect(self._on_settings_changed)
        self.settings_page.back_requested.connect(
            lambda: self.switch_page(self.PAGE_CREATE)
        )

    # ------------------------------------------------------------------
    # 页面切换
    # ------------------------------------------------------------------
    def switch_page(self, page: int) -> None:
        """切换到指定页面；收藏夹/历史在进入时刷新。"""
        widget = self.stack.widget(page)
        if hasattr(widget, "refresh"):
            widget.refresh()
        self.stack.setCurrentIndex(page)
        # 侧栏选中态（收藏夹/历史两个 nav 按钮与页面对应）
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(
                (page == self.PAGE_FAV and i == 0)
                or (page == self.PAGE_HISTORY and i == 1)
            )

    def _on_settings_changed(self) -> None:
        self.generate_tab.refresh_models()
        self.img2img_tab.refresh_models()

    def _send_to_image_edit(self, path: str) -> None:
        """把文生图结果发送到图生图页作为参考图，并切换过去。"""
        self.switch_page(self.PAGE_CREATE)
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

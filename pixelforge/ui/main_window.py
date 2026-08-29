"""应用主窗口。

布局：左侧固定侧栏（新的创作 / 收藏夹 / 历史记录 / 恢复上次对话，
底部设置）+ 中央页面栈。

创作页当前仍承载 文生图 / 图生图 两个页签；
对话式创作流上线后由此替换（见 doc/markdown/box1.md）。
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from pixelforge.core.image_service import ImageService
from pixelforge.core.session_store import SessionStore
from pixelforge.core.storage import HistoryStore
from pixelforge.security.key_manager import KeyManager
from pixelforge.ui.about_page import AboutPage
from pixelforge.ui.chat_tab import ChatPage
from pixelforge.ui.favorites_panel import FavoritesPanel
from pixelforge.ui.history_panel import HistoryPanel
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

        # 恢复上次对话
        self.btn_restore = QPushButton("↺  恢复上次对话")
        self.btn_restore.setProperty("class", "nav")
        self.btn_restore.setEnabled(bool(self.sessions.list_sessions(limit=1)))
        self.btn_restore.clicked.connect(
            lambda: self._restore_last_session()
        )
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

        # 创作页：对话式创作流
        self.chat_page = ChatPage(self.config, self.service, self.sessions, self)
        self.stack.addWidget(self.chat_page)

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
        # 新的创作：切回创作页、归档当前会话并开始新会话。
        # 无论当前在哪个页面，点击后都应看到"清空并回到创作页"的反馈
        self.btn_new.clicked.connect(lambda: self._start_new_session())
        # 设置保存 → 刷新模型列表 / 面板
        self.settings_page.settings_changed.connect(self._on_settings_changed)
        self.settings_page.back_requested.connect(
            lambda: self.switch_page(self.PAGE_CREATE)
        )

    def _start_new_session(self) -> None:
        """「新的创作」：归档当前会话、切回创作页并聚焦输入框。"""
        self.switch_page(self.PAGE_CREATE)
        self.chat_page.new_session()
        self.chat_page.prompt_edit.setFocus()

    # ------------------------------------------------------------------
    # 页面切换
    # ------------------------------------------------------------------
    def switch_page(self, page: int) -> None:
        """切换到指定页面；进入时刷新对应面板。"""
        widget = self.stack.widget(page)
        if hasattr(widget, "refresh"):
            widget.refresh()
        self.btn_restore.setEnabled(bool(self.sessions.list_sessions(limit=1)))
        self.stack.setCurrentIndex(page)
        # 侧栏选中态（收藏夹/历史两个 nav 按钮与页面对应）
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(
                (page == self.PAGE_FAV and i == 0)
                or (page == self.PAGE_HISTORY and i == 1)
            )

    def _on_settings_changed(self) -> None:
        self.chat_page.refresh_models()

    def _restore_last_session(self) -> None:
        """恢复上次对话并回到创作页。"""
        if self.chat_page.restore_last() is None:
            QMessageBox.information(self, "提示", "还没有可恢复的历史对话")
            return
        self.switch_page(self.PAGE_CREATE)

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

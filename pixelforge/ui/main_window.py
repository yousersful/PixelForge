"""应用主窗口。

布局：左侧固定侧栏（新的创作 / 收藏夹 / 历史记录 / 恢复上次对话，
底部设置）+ 中央页面栈。

创作页当前仍承载 文生图 / 图生图 两个页签；
对话式创作流上线后由此替换（见 doc/markdown/box1.md）。
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout,
    QWidget,
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


def _relative_time(iso: str) -> str:
    """把 updated_at 转成「x分钟前 / x小时前 / 昨天 / x天前 / 日期」。"""
    from datetime import datetime

    try:
        t = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return iso
    delta = datetime.now() - t
    seconds = delta.total_seconds()
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds // 60)}分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)}小时前"
    if seconds < 172800:
        return "昨天"
    if seconds < 86400 * 30:
        return f"{int(seconds // 86400)}天前"
    return t.strftime("%Y-%m-%d")


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
        self._refresh_session_list()
        self._restore_window_state()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        self.setWindowTitle("PixelForge - AI 图像生成")
        # 1000px：历史记录工具栏（标题+副题+搜索+刷新+双导出）的完整宽度下限，
        # 再小按钮会互相挤压
        self.setMinimumSize(1000, 600)

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

        # 最近的对话（会话列表，点击恢复）
        self.session_label = QLabel("最近的对话")
        self.session_label.setProperty("class", "hint")
        self.session_label.setVisible(False)  # 无会话时隐藏
        col.addWidget(self.session_label)

        self.session_list = QListWidget(self)
        self.session_list.setFrameShape(QFrame.NoFrame)
        self.session_list.setIconSize(QSize(36, 36))
        self.session_list.setMaximumHeight(240)
        self.session_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.session_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.session_list.setWordWrap(True)
        self.session_list.itemClicked.connect(self._on_session_clicked)
        # 右键菜单：打开 / 删除会话
        self.session_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(
            self._session_context_menu
        )
        col.addWidget(self.session_list) 

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
        """「新的创作」：归档当前会话、切回创作页并聚焦输入框。

        先归档再切页，保证侧栏「最近的对话」刷新时能看到本会话。
        """
        self.chat_page.new_session()
        self.switch_page(self.PAGE_CREATE)
        self.chat_page.prompt_edit.setFocus()

    # ------------------------------------------------------------------
    # 页面切换
    # ------------------------------------------------------------------
    def switch_page(self, page: int) -> None:
        """切换到指定页面；进入时刷新对应面板。"""
        widget = self.stack.widget(page)
        if hasattr(widget, "refresh"):
            widget.refresh()
        self._refresh_session_list()
        self.stack.setCurrentIndex(page)
        # 侧栏选中态（收藏夹/历史两个 nav 按钮与页面对应）
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(
                (page == self.PAGE_FAV and i == 0)
                or (page == self.PAGE_HISTORY and i == 1)
            )

    def _on_settings_changed(self) -> None:
        self.chat_page.refresh_models()

    def _refresh_session_list(self) -> None:
        """刷新侧栏「最近的对话」列表。"""
        from pixelforge.utils.helpers import load_pixmap

        self.session_list.clear()
        items = self.sessions.list_sessions(limit=15)
        self.session_label.setVisible(bool(items))
        self.session_list.setVisible(bool(items))
        for it in items:
            label = f"{it['preview'] or '(无文字记录)'}\n{_relative_time(it['updated_at'])}"
            icon = QIcon()
            thumb = it.get("thumb", "")
            if thumb and Path(thumb).exists():
                pm = load_pixmap(thumb, 72)
                if not pm.isNull():
                    icon = QIcon(pm)
            item = QListWidgetItem(icon, label)
            item.setData(Qt.UserRole, it["id"])
            item.setToolTip(
                f"{it['model']}\n{it['message_count']} 条消息\n{it['updated_at']}"
            )
            self.session_list.addItem(item)

    def _on_session_clicked(self, item) -> None:
        """点击侧栏会话条目：恢复该会话并回到创作页。"""
        session_id = item.data(Qt.UserRole)
        if self.chat_page.restore_session(session_id) is None:
            QMessageBox.warning(self, "恢复失败", "会话数据不存在或已损坏")
            self._refresh_session_list()
            return
        self.switch_page(self.PAGE_CREATE)

    def _session_context_menu(self, pos) -> None:
        """会话列表右键菜单：打开 / 删除。"""
        item = self.session_list.itemAt(pos)
        if item is None:
            return
        session_id = item.data(Qt.UserRole)
        # 定位点击的是否当前正在编辑的会话（高亮预防误删正在进行的）
        menu = QMenu(self)
        act_open = menu.addAction("打开该会话")
        menu.addSeparator()
        act_del = menu.addAction("删除该会话")
        chosen = menu.exec_(self.session_list.mapToGlobal(pos))
        if chosen is act_open:
            # 复用 itemClicked 的恢复逻辑
            self._on_session_clicked(item)
        elif chosen is act_del:
            preview = item.text().split("\n")[0]
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("删除对话")
            box.setText("确定要删除这个对话吗？（已经生成的图片不会被删除）")
            if preview and preview != "(无文字记录)":
                box.setInformativeText(f"「{preview}」")
            del_btn = box.addButton("确定", QMessageBox.AcceptRole)
            box.addButton("取消", QMessageBox.RejectRole)
            box.setDefaultButton(del_btn)
            box.exec_()
            if box.clickedButton() is del_btn:
                # 若删除的正是当前编辑中的会话，重置为新的空白会话，
                # 避免当前页还指向已被删除的内存会话
                if self.chat_page.session.get("id") == session_id:
                    self.chat_page.session = self.chat_page.sessions.new_session(
                        provider=self.config.get("model.provider", ""),
                    )
                    self.chat_page._clear_flow()
                    self.chat_page._update_welcome()
                    self.chat_page.prompt_edit.clear()
                self.sessions.delete(session_id)
                self._refresh_session_list()

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

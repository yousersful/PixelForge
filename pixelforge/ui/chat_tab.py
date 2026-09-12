"""对话式创作流（原型 Page 5）。

聊天式界面：
  - 用户提示词 = 右对齐气泡（附参考图时一并预览）
  - 生成结果 = 图卡片（元信息：用时/模型/日期；操作：收藏/下载/打开文件夹）
  - 「当前图」机制：最新一轮的最后一张为当前图，点选卡片可切换；
    只输入修改意见时以当前图作为参考图走图生图
  - 会话持久化：每轮结束写入 data/sessions，「新的创作」归档并开新会话
"""
from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QPoint, QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QShortcut, QSpinBox, QStackedWidget,
    QVBoxLayout, QWidget,
)

from pixelforge.models.gen_modes import GENERATION_MODES, get_mode
from pixelforge.models.prompts import TEMPLATES
from pixelforge.utils.helpers import load_pixmap, save_image_dialog

CARD_IMG = 260  # 结果卡片图片显示尺寸（px）


# ----------------------------------------------------------------------
# 后台生成线程
# ----------------------------------------------------------------------
class _ChatWorker(QThread):
    """一次生成请求；自动区分文生图 / 图生图。"""

    finished_ok = pyqtSignal(list, float)  # 保存路径列表, 用时（秒）
    finished_err = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # 批序号, 总批数（>1 时提示用）

    def __init__(self, service, prompt, model, size, num, mode,
                 ref_path=None, custom_params: dict | None = None) -> None:
        super().__init__()
        self.service = service
        self.prompt = prompt
        self.model = model
        self.size = size
        self.num = num
        self.mode = mode
        self.ref_path = ref_path
        self.custom_params = custom_params or {}

    def run(self) -> None:
        started = time.monotonic()
        try:

            def _report(batch_no: int, total: int) -> None:
                self.progress.emit(batch_no, total)

            if self.ref_path:
                paths = self.service.image_to_image(
                    self.prompt, self.model, self.ref_path, self.size,
                    self.num, mode=self.mode, progress_cb=_report,
                    **self.custom_params,
                )
            else:
                paths = self.service.generate(
                    self.prompt, self.model, self.size, self.num,
                    mode=self.mode, progress_cb=_report,
                    **self.custom_params,
                )
            self.finished_ok.emit(paths, time.monotonic() - started)
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))


# ----------------------------------------------------------------------
# 消息气泡 / 结果卡片
# ----------------------------------------------------------------------
def _meta_label(model: str, duration: float) -> str:
    stamp = datetime.now().strftime("%m月%d日 %H:%M")
    parts = []
    if duration:
        parts.append(f"用时：{duration:.0f}s")
    if model:
        parts.append(model)
    parts.append(stamp)
    return "  ·  ".join(parts)


class _ClickableImage(QLabel):
    """可点选的图片（用于「当前图」选择；双击打开大图预览）。"""

    clicked = pyqtSignal()
    double_clicked = pyqtSignal()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class _UserBubble(QFrame):
    """右侧的用户消息气泡。"""

    def __init__(self, text: str, image_path: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("class", "bubble-user")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        box = QVBoxLayout()
        box.setContentsMargins(16, 12, 16, 12)
        if image_path:
            img = QLabel()
            img.setPixmap(load_pixmap(image_path, 200))
            img.setAlignment(Qt.AlignCenter)
            box.addWidget(img)
            box.addSpacing(6)
        label = QLabel(text)
        label.setWordWrap(True)
        box.addWidget(label)
        holder = QWidget()
        holder.setProperty("class", "bubble-user-inner")
        # 自定义 QWidget 子类需显式启用样式表背景绘制
        holder.setAttribute(Qt.WA_StyledBackground, True)
        holder.setLayout(box)
        holder.setFixedWidth(420)
        row.addWidget(holder)


class _ErrorBubble(QLabel):
    """左对齐的错误提示气泡。"""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(f"⚠ 生成失败：{text}", parent)
        self.setWordWrap(True)
        self.setProperty("class", "bubble-error")


class _ResultCard(QWidget):
    """一轮结果中的一个缩略格：图片（点击设为当前图）+ 操作行。

    无边框（由外层 _ResultGroup 提供卡片外观）；操作行
    （收藏/下载/打开文件夹）仅在本格是「当前图」时可见。
    """

    selected = pyqtSignal(str)  # 图片路径
    deleted = pyqtSignal(str)   # 请求删除这张图
    preview = pyqtSignal(str)   # 双击预览大图

    def __init__(self, service, path: str, model: str, duration: float,
                 thumb: int = CARD_IMG, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.path = path
        self.setProperty("class", "cell")

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        self.image = _ClickableImage()
        self.image.setPixmap(load_pixmap(path, thumb))
        self.image.setFixedSize(thumb, thumb)
        self.image.setScaledContents(True)
        self.image.setProperty("class", "cellimg")
        self.image.setCursor(Qt.PointingHandCursor)
        self.image.setToolTip("单击选中 · 双击预览大图")
        self.image.clicked.connect(lambda: self.selected.emit(self.path))
        self.image.double_clicked.connect(lambda: self.preview.emit(self.path))
        col.addWidget(self.image)

        # 操作条悬浮在图片底部（不参与网格布局，显示/隐藏不会挤动格子）
        self._actions = QWidget(self.image)
        self._actions.setAttribute(Qt.WA_StyledBackground, True)
        self._actions.setStyleSheet(
            "background-color: rgba(15, 23, 42, 0.72); border-radius: 8px;")
        row = QHBoxLayout(self._actions)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(2)
        btn_css = (
            "border: none; background: transparent; color: #FFFFFF;"
            "padding: 2px 4px; font-size: 12px;"
        )
        self.fav_btn = QPushButton("☆ 收藏")
        self.fav_btn.setToolTip("收藏到收藏夹（Like 目录）")
        self.fav_btn.setCursor(Qt.PointingHandCursor)
        save_btn = QPushButton("下载")
        save_btn.setToolTip("把这张图另存到别处")
        save_btn.setCursor(Qt.PointingHandCursor)
        folder_btn = QPushButton("文件夹")
        folder_btn.setToolTip("打开图片所在文件夹")
        folder_btn.setCursor(Qt.PointingHandCursor)
        del_btn = QPushButton("删除")
        del_btn.setToolTip("删除这张图（移入回收站，并从对话与历史记录中移除）")
        del_btn.setCursor(Qt.PointingHandCursor)
        for b in (self.fav_btn, save_btn, folder_btn, del_btn):
            b.setStyleSheet(btn_css)
            row.addWidget(b)
        self.fav_btn.clicked.connect(self._toggle_favorite)
        save_btn.clicked.connect(self._save)
        folder_btn.clicked.connect(self._open_folder)
        del_btn.clicked.connect(lambda: self.deleted.emit(self.path))
        self._actions.adjustSize()
        self._layout_actions()
        self._refresh_fav()

    # ---- 操作 ----
    def _layout_actions(self) -> None:
        """操作条水平居中贴图片底部（悬浮层，不影响外部布局）。"""
        bar = self._actions
        bar.adjustSize()
        t = self.image.width()
        bar.move(max(4, (t - bar.width()) // 2), t - bar.height() - 6)
        bar.raise_()

    def _refresh_fav(self) -> None:
        try:
            fav = self.service.is_favorited(self.path)
        except Exception:  # noqa: BLE001
            fav = False
        self.fav_btn.setText("★ 已收藏" if fav else "☆ 收藏")
        self._layout_actions()

    def _toggle_favorite(self) -> None:
        try:
            if self.service.is_favorited(self.path):
                self.service.unfavorite(self.path)
            else:
                self.service.favorite(self.path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "收藏失败", str(exc))
        self._refresh_fav()

    def _save(self) -> None:
        dest = save_image_dialog(self, Path(self.path).name)
        if dest:
            shutil.copy2(self.path, dest)
            QMessageBox.information(self, "已保存", f"图片已保存到：\n{dest}")

    def _open_folder(self) -> None:
        folder = str(Path(self.path).parent)
        try:
            os.startfile(folder)  # Windows
        except AttributeError:  # 其他平台
            import subprocess
            subprocess.Popen(["xdg-open", folder])

    # ---- 选中态 ----
    def set_selected(self, on: bool) -> None:
        """当前图高亮 + 操作行仅当前图可见。"""
        self.image.setProperty("current", "true" if on else "false")
        self.image.style().unpolish(self.image)
        self.image.style().polish(self.image)
        self._actions.setVisible(on)


class _ResultGroup(QFrame):
    """一轮生成的结果组：元信息 + 缩略图网格。

    1 张 → 单列原尺寸；2–4 张 → 2 列；≥5 张 → 3 列。
    一轮生成在对话流中只占一个消息块。
    """

    selected = pyqtSignal(str)  # 转发格子点击
    deleted = pyqtSignal(str)   # 转发格子删除请求
    preview = pyqtSignal(str)   # 转发双击预览

    def __init__(self, service, items: list, parent=None) -> None:
        """items: [(path, model, duration), ...]"""
        super().__init__(parent)
        self.setProperty("class", "card")
        self.cells: list[_ResultCard] = []

        col = QVBoxLayout(self)
        col.setContentsMargins(14, 10, 14, 12)
        col.setSpacing(8)

        n = len(items)
        caption = _meta_label(items[0][1], items[0][2])
        self._caption_base = caption
        meta = QLabel(caption + (f"  ·  {n} 张" if n > 1 else ""))
        meta.setProperty("class", "hint")
        self._meta = meta
        col.addWidget(meta)

        thumb = CARD_IMG if n == 1 else (200 if n <= 4 else 180)
        cols = 1 if n == 1 else (2 if n <= 4 else 3)
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (path, model, duration) in enumerate(items):
            cell = _ResultCard(service, path, model, duration, thumb=thumb)
            cell.selected.connect(self.selected)
            cell.deleted.connect(self.deleted)
            cell.preview.connect(self.preview)
            self.cells.append(cell)
            grid.addWidget(cell, i // cols, i % cols, Qt.AlignLeft | Qt.AlignTop)
        # 网格整体靠左：多余宽度留在右侧，不被均摊到各列
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addLayout(grid)
        row.addStretch(1)
        col.addLayout(row)

    def update_count(self, n: int) -> None:
        """删图后刷新元信息里的张数。"""
        self._meta.setText(self._caption_base + (f"  ·  {n} 张" if n > 1 else ""))


_SPIN_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class _PendingCard(QFrame):
    """生成进行中的骨架占位卡。

    结构复刻结果卡（图区 260×260），图区内显示旋转指示 + 状态文字；
    完成/失败后整卡被移除，替换为真实结果卡或错误气泡。
    """

    def __init__(self, model: str, num: int, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("class", "card")
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 10, 14, 12)
        col.setSpacing(8)

        meta = QLabel(f"生成中 · {model}" if model else "生成中")
        meta.setProperty("class", "hint")
        col.addWidget(meta)

        area = QFrame()
        area.setProperty("class", "pending-area")
        area.setFixedSize(CARD_IMG, CARD_IMG)
        box = QVBoxLayout(area)
        box.addStretch(1)
        self.spin = QLabel("")
        self.spin.setProperty("class", "pending-spin")
        self.spin.setAlignment(Qt.AlignCenter)
        box.addWidget(self.spin)
        self.status = QLabel("")
        self.status.setProperty("class", "pending-text")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setWordWrap(True)
        self.status.setMaximumWidth(CARD_IMG - 24)
        box.addWidget(self.status)
        box.addStretch(1)
        col.addWidget(area, 0, Qt.AlignLeft)

        self._frame = 0
        self._timer = QTimer(self)
        self._timer.setInterval(110)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._tick()

        self.set_status(num)

    # ---- 状态文字 ----
    def set_status(self, num: int) -> None:
        if num > 1:
            self.status.setText(f"正在生成 {num} 张图片，请稍候…")
        else:
            self.status.setText("正在生成图片，请稍候…")

    def set_batch(self, batch: int, total: int) -> None:
        """分批生成（厂商单次只回一张）时给出第几批提示。"""
        if total > 1:
            self.status.setText(f"正在生成第 {batch}/{total} 批…")

    # ---- 动画 ----
    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(_SPIN_FRAMES)
        self.spin.setText(_SPIN_FRAMES[self._frame])

    def stop(self) -> None:
        """移除前停止动画定时器。"""
        self._timer.stop()


# ----------------------------------------------------------------------
# 创作页
# ----------------------------------------------------------------------

class _AdvancedPanel(QFrame):
    """高级选项浮层：尺寸/张数 + 自定义参数开关。

    开关启用时用户参数覆盖生成模式预设（与内核「显式参数优先」一致）；
    关闭时完全跟随模式预设。
    """

    def __init__(self, chat: "ChatPage", parent=None) -> None:
        super().__init__(parent or chat)
        self.setProperty("class", "card")
        self.setFixedWidth(340)
        col = QVBoxLayout(self)
        col.setContentsMargins(16, 12, 16, 12)
        col.setSpacing(10)

        row = QHBoxLayout()
        row.addWidget(QLabel("尺寸"))
        self.size_combo = QComboBox()
        row.addWidget(self.size_combo, 1)
        row.addWidget(QLabel("张数"))
        self.num_spin = QSpinBox()
        self.num_spin.setRange(1, 9)
        row.addWidget(self.num_spin)
        col.addLayout(row)

        self.custom_check = QCheckBox("启用自定义参数（覆盖生成模式预设）")
        self.custom_check.toggled.connect(self._toggle_custom)
        col.addWidget(self.custom_check)

        form = QFormLayout()
        form.setSpacing(6)
        self.guidance_spin = QDoubleSpinBox()
        self.guidance_spin.setRange(1.0, 20.0)
        self.guidance_spin.setSingleStep(0.5)
        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(1, 100)
        form.addRow("引导值:", self.guidance_spin)
        form.addRow("步数:", self.steps_spin)
        col.addLayout(form)

        self.preset_hint = QLabel("")
        self.preset_hint.setProperty("class", "hint")
        self.preset_hint.setWordWrap(True)
        col.addWidget(self.preset_hint)
        self._toggle_custom(False)

    def hideEvent(self, ev) -> None:  # noqa: N802
        # Popup 关闭的所有路径（点击外部/Esc/再次点齿轮）统一收口：
        # 同步齿轮按钮状态并持久化设置
        chat = self.parent()
        if chat is not None and hasattr(chat, "adv_btn"):
            chat.adv_btn.setChecked(False)
            chat._persist_adv_settings()
        super().hideEvent(ev)

    def _toggle_custom(self, on: bool) -> None:
        self.guidance_spin.setEnabled(on)
        self.steps_spin.setEnabled(on)

    def update_preset_hint(self, mode_id: str) -> None:
        """显示当前模式预设，让用户知道关闭自定义时会发生什么。"""
        m = get_mode(mode_id)
        if m.num_inference_steps is None:
            self.preset_hint.setText("当前模式「标准」使用厂商默认参数")
        else:
            self.preset_hint.setText(
                f"当前模式「{m.name}」预设：步数 {m.num_inference_steps}，"
                f"引导值 {m.guidance_scale}（关闭自定义时生效）"
            )


class ChatPage(QWidget):
    """对话式创作页。"""

    def __init__(self, config, service, sessions, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.service = service
        self.sessions = sessions
        self.session = sessions.new_session()
        self._pending_ref: str | None = None  # 本轮用户主动上传的参考图
        self._worker: _ChatWorker | None = None
        self._cards: list[_ResultCard] = []
        self._placeholder: _PendingCard | None = None
        # 归属绑定：进行中生成任务的发起会话 ID。
        # 完成回调据此决定结果进当前界面还是写回发起会话的存档。
        self._active_session_id: str | None = None

        col = QVBoxLayout(self)
        col.setContentsMargins(24, 20, 24, 20)
        col.setSpacing(12)

        # ---- 消息流 ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.flow_holder = QWidget()
        self.flow = QVBoxLayout(self.flow_holder)
        self.flow.setContentsMargins(0, 0, 0, 0)
        self.flow.setSpacing(14)
        self.flow.addStretch(1)
        self.scroll.setWidget(self.flow_holder)

        # ---- 欢迎 / 消息流 双页切换：空会话显示欢迎页 ----
        self.body_stack = QStackedWidget()
        self.body_stack.addWidget(self._build_welcome())
        self.body_stack.addWidget(self.scroll)
        col.addWidget(self.body_stack, 1)

        self.hint_label = QLabel(
            "输入描述开始创作；生成后想修改，直接说出修改意见即可"
            "（会以最新的图继续）"
        )
        self.hint_label.setProperty("class", "hint")
        self.hint_label.setAlignment(Qt.AlignCenter)
        col.addWidget(self.hint_label)

        # ---- 底部输入区 ----
        input_card = QFrame()
        input_card.setProperty("class", "card")
        icol = QVBoxLayout(input_card)
        icol.setContentsMargins(16, 12, 16, 12)
        icol.setSpacing(10)

        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText("说出你的修改意见……")
        self.prompt_edit.setFixedHeight(76)
        icol.addWidget(self.prompt_edit)

        tools = QHBoxLayout()
        tools.setSpacing(10)

        self.ref_btn = QPushButton("+ 参考图")
        self.ref_btn.setToolTip("上传参考图（图生图）；再次点击可取消")
        self.ref_btn.setCheckable(True)
        self.ref_btn.toggled.connect(self._toggle_ref)
        tools.addWidget(self.ref_btn)

        self.tpl_btn = QPushButton("◇ 选择模板")
        self.tpl_btn.setToolTip("从内置提示词模板中选择，填入输入框")
        self.tpl_btn.clicked.connect(self._show_template_menu)
        tools.addWidget(self.tpl_btn)

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(150)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        tools.addWidget(QLabel("模型"))
        tools.addWidget(self.model_combo, 1)

        tools.addWidget(QLabel("模式"))
        self.mode_combo = QComboBox()
        for m in GENERATION_MODES:
            self.mode_combo.addItem(f"{m.name} - {m.description.split('，')[0]}", m.id)
        self.mode_combo.setCurrentIndex(1)  # 标准
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        tools.addWidget(self.mode_combo)

        # 高级选项（尺寸/张数/自定义参数收进齿轮面板）
        self.adv_btn = QPushButton("⚙")
        self.adv_btn.setToolTip("高级选项：尺寸、张数、自定义参数")
        self.adv_btn.setCheckable(True)
        self.adv_btn.setCursor(Qt.PointingHandCursor)
        self.adv_btn.clicked.connect(self._toggle_adv_panel)
        tools.addWidget(self.adv_btn)

        self.send_btn = QPushButton("生成  ➤")
        self.send_btn.setProperty("class", "primary")
        self.send_btn.setShortcut(QKeySequence("Ctrl+Return"))
        self.send_btn.clicked.connect(self._send)
        tools.addWidget(self.send_btn)

        icol.addLayout(tools)
        col.addWidget(input_card)

        # 高级选项弹出面板：原生 Popup 窗口（点击外部自动收起，
        # 内部控件正常交互，无需自制"点击外部"判断）
        self.adv_panel = _AdvancedPanel(self)
        self.adv_panel.setWindowFlags(Qt.Popup)
        self.adv_panel.hide()

        self._restore_adv_settings()

        QShortcut(QKeySequence("Ctrl+Up"), self, self._scroll_to_top)

        self.refresh_models()
        self._update_welcome()

    # ------------------------------------------------------------------
    # 欢迎页（空会话状态）
    # ------------------------------------------------------------------
    def _build_welcome(self) -> QWidget:
        """欢迎页：logo + 标语 + 提示词模板建议卡。"""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.addStretch(1)

        center = QVBoxLayout()
        center.setSpacing(14)
        center.setAlignment(Qt.AlignHCenter)

        # 标题行：欢迎使用 + logo 图片
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignHCenter)
        title_row.setSpacing(14)
        t = QLabel("欢迎使用")
        t.setStyleSheet("font-size: 34px; font-weight: 800;")
        title_row.addWidget(t)

        logo = QLabel()
        logo_path = Path(__file__).resolve().parents[2] / "Logo_with_Font.png"
        pm = load_pixmap(str(logo_path), 220) if logo_path.exists() else QPixmap()
        if not pm.isNull():
            logo.setPixmap(pm)
            logo.setScaledContents(True)
            logo.setFixedHeight(56)
            logo.setFixedWidth(int(pm.width() * 56 / pm.height()))
        else:  # 图片缺失时退回文字
            logo.setText("PixelForge")
            logo.setStyleSheet("font-size: 34px; font-weight: 800; font-style: italic;")
        title_row.addWidget(logo)
        center.addLayout(title_row)

        sub = QLabel("今天有什么天马行空的想法？")
        sub.setProperty("class", "pageCaption")
        sub.setAlignment(Qt.AlignCenter)
        center.addWidget(sub)
        center.addSpacing(10)

        tip = QLabel("暂时没有想法？试试这些：")
        tip.setProperty("class", "hint")
        tip.setAlignment(Qt.AlignCenter)
        center.addWidget(tip)

        # 模板建议卡（取自内置提示词模板，占位符用默认值填充）
        from pixelforge.models.prompts import TEMPLATES

        import re

        def filled(tpl) -> str:
            return re.sub(r"\{[^}]*\}", tpl.placeholder or "", tpl.text)

        picks = [TEMPLATES[i] for i in (0, 6, 2, 7) if i < len(TEMPLATES)]
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, tpl in enumerate(picks):
            btn = QPushButton(filled(tpl))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(f"模板：{tpl.name}（{tpl.category}）\n点击填入输入框")
            btn.clicked.connect(
                lambda _=False, text=filled(tpl): self._use_template(text)
            )
            grid.addWidget(btn, i // 2, i % 2)
        holder = QWidget()
        holder.setLayout(grid)
        center.addWidget(holder, 0, Qt.AlignHCenter)

        outer.addLayout(center)
        outer.addStretch(2)
        return page

    def _use_template(self, text: str) -> None:
        """点模板卡：填入输入框并聚焦。"""
        self.prompt_edit.setPlainText(text)
        self.prompt_edit.setFocus()

    def _update_welcome(self) -> None:
        """会话为空时显示欢迎页，有内容时显示消息流。"""
        empty = not self.session.get("messages")
        self.body_stack.setCurrentIndex(0 if empty else 1)

    # ------------------------------------------------------------------
    # 会话
    # ------------------------------------------------------------------
    def new_session(self) -> None:
        """「新的创作」：归档当前会话并开始新会话。"""
        if self.session["messages"]:
            self.sessions.save(self.session)
        self.session = self.sessions.new_session(
            provider=self.config.get("model.provider", ""),
            model=self._current_model_id(),
            mode=self.mode_combo.currentData(),
        )
        self._clear_flow()
        self.hint_label.setText("已开启新的创作，上一段对话已保存")
        self._update_welcome()

    def restore_last(self) -> dict | None:
        """「恢复上次对话」。返回会话数据；没有可恢复的会话时 None。"""
        latest = self.sessions.list_sessions(limit=1)
        if not latest:
            return None
        return self.restore_session(latest[0]["id"])

    def restore_session(self, session_id: str) -> dict | None:
        """按 ID 恢复任意会话（侧栏「最近的对话」点击）。"""
        data = self.sessions.load(session_id)
        if not data:
            return None
        if self.session["messages"]:
            self.sessions.save(self.session)
        self.session = data
        self._rebuild_from_session()
        self._update_welcome()
        return data

    def _rebuild_from_session(self) -> None:
        """按会话记录重建消息流。"""
        self._clear_flow()
        for msg in self.session.get("messages", []):
            role, mtype = msg.get("role"), msg.get("type")
            if role == "user" and mtype == "text":
                self._add_bubble(_UserBubble(msg.get("text", ""), msg.get("image")))
            elif role == "user" and mtype == "image":
                self._add_bubble(_UserBubble("(参考图)", msg.get("path")))
            elif role == "assistant" and mtype == "images":
                self._add_result_group(
                    msg.get("paths", []), msg.get("model", ""),
                    msg.get("durations", []),
                )
            elif role == "assistant" and mtype == "error":
                self._add_bubble(_ErrorBubble(msg.get("text", "")))
        self._apply_current_image()

    def _clear_flow(self) -> None:
        self._placeholder = None  # 生成中切换会话：占位卡随之销毁，回调不再更新它
        while self.flow.count() > 1:  # 保留末尾 stretch
            item = self.flow.takeAt(0)
            w = item.widget()
            if w:
                if isinstance(w, _PendingCard):
                    w.stop()
                w.deleteLater()
        self._cards.clear()

    # ------------------------------------------------------------------
    # 模型 / 尺寸
    # ------------------------------------------------------------------
    def refresh_models(self) -> None:
        current = self._current_model_id()
        models = self.service.list_available_models()
        if not models:
            from pixelforge.models.providers import get_provider
            provider = get_provider(self.config.get("model.provider", "siliconflow"))
            models = provider.models if provider else []
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for m in models:
            self.model_combo.addItem(m.name, m.id)
        self.model_combo.blockSignals(False)
        if current:
            idx = self.model_combo.findData(current)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        self._on_model_changed()

    # 尺寸/张数控件移入高级面板，属性代理保持外部引用不变
    @property
    def size_combo(self) -> QComboBox:
        return self.adv_panel.size_combo

    @property
    def num_spin(self) -> QSpinBox:
        return self.adv_panel.num_spin

    def _current_model_id(self) -> str:
        return self.model_combo.currentData() or ""

    def _on_model_changed(self) -> None:
        model_id = self._current_model_id()
        sizes = None
        for m in self.service.list_available_models():
            if m.id == model_id and m.sizes:
                sizes = m.sizes
                break
        if sizes is None:
            from pixelforge.models.providers import get_provider
            provider = get_provider(self.config.get("model.provider", "siliconflow"))
            if provider:
                for m in provider.models:
                    if m.id == model_id and m.sizes:
                        sizes = m.sizes
                        break
        self.size_combo.clear()
        self.size_combo.addItems(sizes or ["1024x1024"])

    # ------------------------------------------------------------------
    # 参考图
    # ------------------------------------------------------------------
    def set_reference(self, path: str | Path) -> None:
        """外部（历史/收藏）设置参考图。"""
        self._pending_ref = str(path)
        self.ref_btn.setChecked(True)
        self.ref_btn.setText("✓ 参考图已选")

    def _toggle_ref(self, on: bool) -> None:
        if on:
            if not self._pending_ref:
                path, _ = QFileDialog.getOpenFileName(
                    self, "选择参考图", "",
                    "图片 (*.png *.jpg *.jpeg *.bmp *.webp)",
                )
                if not path:
                    self.ref_btn.setChecked(False)
                    return
                self._pending_ref = path
            self.ref_btn.setText("✓ 参考图已选")
        else:
            self._pending_ref = None
            self.ref_btn.setText("+ 参考图")

    # ------------------------------------------------------------------
    # 高级选项面板 / 模板菜单
    # ------------------------------------------------------------------
    def _toggle_adv_panel(self) -> None:
        """齿轮按钮：在齿轮上方弹出高级选项面板。"""
        if not self.adv_btn.isChecked():
            return  # 面板已由 Popup 机制关闭（hideEvent 已同步状态）
        self.adv_panel.update_preset_hint(self.mode_combo.currentData())
        self.adv_panel.adjustSize()
        origin = self.adv_btn.mapToGlobal(QPoint(0, 0))
        x = origin.x() + self.adv_btn.width() - self.adv_panel.width()
        y = origin.y() - self.adv_panel.height() - 8
        self.adv_panel.move(x, y)
        self.adv_panel.show()
        self.adv_panel.raise_()

    def _on_mode_changed(self) -> None:
        """模式切换时刷新面板里的预设提示。"""
        if hasattr(self, "adv_panel"):
            self.adv_panel.update_preset_hint(self.mode_combo.currentData())

    def _show_template_menu(self) -> None:
        """「选择模板」：弹出全部内置模板，点击填入输入框。"""
        import re

        menu = QMenu(self)
        for t in TEMPLATES:
            text = re.sub(r"\{[^}]*\}", t.placeholder or "", t.text)
            menu.addAction(
                f"[{t.category}] {t.name}",
                lambda text=text: self._use_template(text),
            )
        menu.exec_(self.tpl_btn.mapToGlobal(QPoint(0, self.tpl_btn.height())))

    def _custom_params(self) -> dict:
        """自定义参数（开关启用时生效，与内核显式参数优先规则一致）。"""
        p = self.adv_panel
        if not p.custom_check.isChecked():
            return {}
        return {
            "guidance_scale": p.guidance_spin.value(),
            "num_inference_steps": int(p.steps_spin.value()),
        }

    def _persist_adv_settings(self) -> None:
        p = self.adv_panel
        self.config.set("chat.adv_custom", p.custom_check.isChecked())
        self.config.set("chat.adv_guidance", p.guidance_spin.value())
        self.config.set("chat.adv_steps", p.steps_spin.value())
        self.config.set("chat.adv_num", p.num_spin.value())
        self.config.save()

    def _restore_adv_settings(self) -> None:
        c = self.config
        p = self.adv_panel
        p.custom_check.setChecked(bool(c.get("chat.adv_custom", False)))
        guidance = c.get("chat.adv_guidance")
        if guidance:
            p.guidance_spin.setValue(float(guidance))
        steps = c.get("chat.adv_steps")
        if steps:
            p.steps_spin.setValue(int(steps))
        num = c.get("chat.adv_num")
        if num:
            p.num_spin.setValue(int(num))

    # ------------------------------------------------------------------
    # 发送与结果
    # ------------------------------------------------------------------
    def _send(self) -> None:
        if self._worker is not None:
            return
        text = self.prompt_edit.toPlainText().strip()
        use_ref = self._pending_ref or self.session.get("current_image")
        if not text and not self._pending_ref:
            return  # 空输入

        ref = self._pending_ref
        if not ref and use_ref:
            ref = use_ref  # 修改模式：以当前图为参考
        if not text:
            text = "(以参考图继续生成)"

        model = self._current_model_id()
        if not model:
            QMessageBox.warning(self, "提示", "尚未选择模型；请先在设置中配置 API Key")
            return

        # 记录用户消息
        user_msg = {"role": "user", "type": "text", "text": text}
        if ref:
            user_msg["image"] = str(ref)
        self.session["messages"].append(user_msg)
        self._add_bubble(_UserBubble(
            self.prompt_edit.toPlainText().strip() or "(参考图)",
            ref,
        ))
        self._update_welcome()

        self.prompt_edit.clear()
        self._pending_ref = None
        self.ref_btn.setChecked(False)

        self._worker = _ChatWorker(
            self.service, text, model,
            self.adv_panel.size_combo.currentText(), self.adv_panel.num_spin.value(),
            self.mode_combo.currentData(), ref_path=ref,
            custom_params=self._custom_params(),
        )
        self._active_session_id = self.session["id"]
        self._persist_adv_settings()
        # 先插入骨架占位卡再启动线程：即使生成瞬间完成，信号也是排队投递，
        # 占位卡保证先出现在对话流里，完成回调再把它替换掉
        self._placeholder = _PendingCard(model, self.adv_panel.num_spin.value())
        self.flow.insertWidget(self.flow.count() - 1, self._placeholder)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.finished_err.connect(self._on_err)
        self.send_btn.setEnabled(False)
        self.send_btn.setText("生成中…")
        self._worker.start()
        self._scroll_to_bottom()

    def _on_progress(self, batch: int, total: int) -> None:
        if self._placeholder is not None:
            self._placeholder.set_batch(batch, total)

    def _remove_placeholder(self) -> None:
        """移除骨架占位卡（完成/失败/清空消息流时调用）。"""
        if self._placeholder is None:
            return
        self._placeholder.stop()
        widget = self._placeholder
        self._placeholder = None
        idx = self.flow.indexOf(widget)
        if idx >= 0:
            self.flow.takeAt(idx)
        widget.deleteLater()

    def _request_is_local(self) -> bool:
        """发起生成的会话是否仍是当前会话（归属信息缺失时按本地兜底）。"""
        return self._active_session_id is None \
            or self.session.get("id") == self._active_session_id

    def _write_back_to_origin(self, message: dict,
                              current_image: str | None) -> None:
        """用户已切走：把结果写回发起会话的存档，不碰当前界面。

        发起会话若已被删除则跳过（图片仍在历史库中，不会丢失）。
        """
        origin, self._active_session_id = self._active_session_id, None
        data = self.sessions.load(origin)
        if not data:
            return
        data["messages"].append(message)
        if current_image:
            data["current_image"] = current_image
        self.sessions.save(data)

    def _on_ok(self, paths: list, duration: float) -> None:
        self._remove_placeholder()
        worker, self._worker = self._worker, None
        self.send_btn.setEnabled(True)
        self.send_btn.setText("生成  ➤")
        model = worker.model if worker else self._current_model_id()
        durations = [round(duration, 1)] * len(paths)
        message = {
            "role": "assistant", "type": "images",
            "paths": [str(p) for p in paths], "durations": durations,
            "model": model,
        }
        current = str(paths[-1]) if paths else None
        if self._request_is_local():
            self._active_session_id = None
            self._add_result_group([str(p) for p in paths], model, durations)
            self.session["messages"].append(message)
            if current:
                self.session["current_image"] = current
            self._apply_current_image()
            self.sessions.save(self.session)
            self._scroll_to_bottom()
        else:
            self._write_back_to_origin(message, current)

    def _on_err(self, message: str) -> None:
        self._remove_placeholder()
        self._worker = None
        self.send_btn.setEnabled(True)
        self.send_btn.setText("生成  ➤")
        msg = {"role": "assistant", "type": "error", "text": message}
        if self._request_is_local():
            self._active_session_id = None
            self._add_bubble(_ErrorBubble(message))
            self.session["messages"].append(msg)
            self.sessions.save(self.session)
            self._scroll_to_bottom()
        else:
            self._write_back_to_origin(msg, None)

    # ------------------------------------------------------------------
    # 流内容
    # ------------------------------------------------------------------
    def _add_bubble(self, widget: QWidget) -> None:
        self.flow.insertWidget(self.flow.count() - 1, widget)
        self._scroll_to_bottom()

    def _add_result_group(self, paths: list, model: str,
                          durations: list) -> _ResultGroup:
        """一轮生成的所有图放进一个消息块（缩略图网格）。"""
        durs = list(durations) + [0.0] * (len(paths) - len(durations))
        items = [(str(p), model, d) for p, d in zip(paths, durs)]
        group = _ResultGroup(self.service, items)
        group.selected.connect(self._select_current)
        group.deleted.connect(self._request_delete_image)
        group.preview.connect(self._open_preview)
        self._cards.extend(group.cells)
        self.flow.insertWidget(self.flow.count() - 1, group)
        self._scroll_to_bottom()
        return group

    def _select_current(self, path: str) -> None:
        self.session["current_image"] = path
        self._apply_current_image()
        self.sessions.save(self.session)

    def _open_preview(self, path: str) -> None:
        """双击缩略图：打开大图预览（拖动/滚轮缩放/Esc 或再双击退出）。"""
        from pixelforge.ui.preview_dialog import show_image_preview

        show_image_preview(self.window(), path)

    # ------------------------------------------------------------------
    # 删除单张图
    # ------------------------------------------------------------------
    def _request_delete_image(self, path: str) -> None:
        """删除前确认（文案与按钮风格对齐会话删除）。"""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("删除图片")
        box.setText("确定要删除这张图片吗？")
        box.setInformativeText(
            "图片会移入回收站，并从当前对话与历史记录中移除；"
            "收藏夹里的副本不受影响。"
        )
        del_btn = box.addButton("确定", QMessageBox.AcceptRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(del_btn)
        box.exec_()
        if box.clickedButton() is del_btn:
            self._delete_image_confirmed(path)

    def _delete_image_confirmed(self, path: str) -> None:
        """执行删除：回收站 ← 历史库 ← 会话存档 ← 界面，任一步失败即中止。"""
        from pixelforge.utils.helpers import send_to_recycle_bin

        if not send_to_recycle_bin(path):
            QMessageBox.warning(
                self, "删除失败", "图片未能移入回收站，请确认文件是否仍存在"
            )
            return
        try:
            self.service.history.delete_path(path)
        except Exception:  # noqa: BLE001  历史库异常不阻断会话清理
            pass

        # 会话消息：从所属 images 消息中摘除该路径
        msgs = self.session.get("messages", [])
        for msg in msgs:
            if msg.get("type") == "images" and path in msg.get("paths", []):
                i = msg["paths"].index(path)
                del msg["paths"][i]
                durs = msg.get("durations")
                if durs and i < len(durs):
                    del durs[i]
                if not msg.get("paths"):
                    msgs.remove(msg)
                break
        # 当前图指向被删的图时，回退到会话里最后一张
        if self.session.get("current_image") == path:
            new_cur = None
            for msg in reversed(msgs):
                if msg.get("type") == "images" and msg.get("paths"):
                    new_cur = msg["paths"][-1]
                    break
            if new_cur:
                self.session["current_image"] = new_cur
            else:
                self.session.pop("current_image", None)
        self.sessions.save(self.session)

        # 界面：移除格子；组空则整组移除
        group = self._group_of(path)
        if group is not None:
            cell = next((c for c in group.cells if c.path == path), None)
            if cell is not None:
                group.cells.remove(cell)
                if cell in self._cards:
                    self._cards.remove(cell)
                cell.deleteLater()
                group.update_count(len(group.cells))
            if not group.cells:
                idx = self.flow.indexOf(group)
                if idx >= 0:
                    self.flow.takeAt(idx)
                group.deleteLater()
        self._apply_current_image()
        self._update_welcome()

    def _group_of(self, path: str) -> "_ResultGroup | None":
        for i in range(self.flow.count()):
            w = self.flow.itemAt(i).widget()
            if isinstance(w, _ResultGroup) and any(
                c.path == path for c in w.cells
            ):
                return w
        return None

    def _apply_current_image(self) -> None:
        current = self.session.get("current_image")
        for card in self._cards:
            card.set_selected(card.path == current)
        if current:
            self.hint_label.setText(
                f"当前图已选定，直接输入修改意见即可继续（以最新生成的图为基础）"
                if len(self._cards) <= 1 else
                "已选定当前图（高亮边框），输入修改意见即以它为参考继续生成"
            )

    def _scroll_to_bottom(self) -> None:
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _scroll_to_top(self) -> None:
        self.scroll.verticalScrollBar().setValue(0)

    def refresh(self) -> None:
        """进入页面时刷新模型列表（保持当前选择）。"""
        self.refresh_models()

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

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QShortcut,
    QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from pixelforge.models.gen_modes import GENERATION_MODES
from pixelforge.utils.helpers import load_pixmap, save_image_dialog

CARD_IMG = 260  # 结果卡片图片显示尺寸（px）


# ----------------------------------------------------------------------
# 后台生成线程
# ----------------------------------------------------------------------
class _ChatWorker(QThread):
    """一次生成请求；自动区分文生图 / 图生图。"""

    finished_ok = pyqtSignal(list, float)  # 保存路径列表, 用时（秒）
    finished_err = pyqtSignal(str)

    def __init__(self, service, prompt, model, size, num, mode,
                 ref_path=None) -> None:
        super().__init__()
        self.service = service
        self.prompt = prompt
        self.model = model
        self.size = size
        self.num = num
        self.mode = mode
        self.ref_path = ref_path

    def run(self) -> None:
        started = time.monotonic()
        try:
            if self.ref_path:
                paths = self.service.image_to_image(
                    self.prompt, self.model, self.ref_path, self.size,
                    self.num, mode=self.mode,
                )
            else:
                paths = self.service.generate(
                    self.prompt, self.model, self.size, self.num, mode=self.mode,
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
    """可点选的图片（用于「当前图」选择）。"""

    clicked = pyqtSignal()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


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


class _ResultCard(QFrame):
    """一张生成结果卡片：元信息 + 图片 + 操作（收藏/下载/打开文件夹）。

    点击图片把它设为「当前图」。
    """

    selected = pyqtSignal(str)  # 图片路径

    def __init__(self, service, path: str, model: str, duration: float,
                 parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.path = path
        self.setProperty("class", "card")

        col = QVBoxLayout(self)
        col.setContentsMargins(14, 10, 14, 12)
        col.setSpacing(8)

        meta = QLabel(_meta_label(model, duration))
        meta.setProperty("class", "hint")
        col.addWidget(meta)

        self.image = _ClickableImage()
        self.image.setPixmap(load_pixmap(path, CARD_IMG))
        self.image.setFixedSize(CARD_IMG, CARD_IMG)
        self.image.setScaledContents(True)
        self.image.setCursor(Qt.PointingHandCursor)
        self.image.setToolTip("点击设为当前图（修改时会以它为参考）")
        self.image.clicked.connect(lambda: self.selected.emit(self.path))
        col.addWidget(self.image)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        self.fav_btn = QPushButton("☆ 收藏")
        self.fav_btn.setProperty("class", "ghost")
        self.fav_btn.clicked.connect(self._toggle_favorite)
        save_btn = QPushButton("下载")
        save_btn.setProperty("class", "ghost")
        save_btn.clicked.connect(self._save)
        folder_btn = QPushButton("打开文件夹")
        folder_btn.setProperty("class", "ghost")
        folder_btn.clicked.connect(self._open_folder)
        for b in (self.fav_btn, save_btn, folder_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        col.addLayout(actions)
        self._refresh_fav()

    # ---- 操作 ----
    def _refresh_fav(self) -> None:
        try:
            fav = self.service.is_favorited(self.path)
        except Exception:  # noqa: BLE001
            fav = False
        self.fav_btn.setText("★ 已收藏" if fav else "☆ 收藏")

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
        self.setProperty("current", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)


# ----------------------------------------------------------------------
# 创作页
# ----------------------------------------------------------------------
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

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(170)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        tools.addWidget(QLabel("模型"))
        tools.addWidget(self.model_combo, 1)

        tools.addWidget(QLabel("尺寸"))
        self.size_combo = QComboBox()
        tools.addWidget(self.size_combo)

        tools.addWidget(QLabel("张数"))
        self.num_spin = QSpinBox()
        self.num_spin.setRange(1, 4)
        tools.addWidget(self.num_spin)

        tools.addWidget(QLabel("模式"))
        self.mode_combo = QComboBox()
        for m in GENERATION_MODES:
            self.mode_combo.addItem(f"{m.name} - {m.description.split('，')[0]}", m.id)
        self.mode_combo.setCurrentIndex(1)  # 标准
        tools.addWidget(self.mode_combo)

        self.send_btn = QPushButton("生成  ➤")
        self.send_btn.setProperty("class", "primary")
        self.send_btn.setShortcut(QKeySequence("Ctrl+Return"))
        self.send_btn.clicked.connect(self._send)
        tools.addWidget(self.send_btn)

        icol.addLayout(tools)
        col.addWidget(input_card)

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
                for p, dur in zip(msg.get("paths", []), msg.get("durations", [])):
                    self._add_card(p, msg.get("model", ""), dur, record=False)
            elif role == "assistant" and mtype == "error":
                self._add_bubble(_ErrorBubble(msg.get("text", "")))
        self._apply_current_image()

    def _clear_flow(self) -> None:
        while self.flow.count() > 1:  # 保留末尾 stretch
            item = self.flow.takeAt(0)
            w = item.widget()
            if w:
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
            self.size_combo.currentText(), self.num_spin.value(),
            self.mode_combo.currentData(), ref_path=ref,
        )
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.finished_err.connect(self._on_err)
        self.send_btn.setEnabled(False)
        self.send_btn.setText("生成中…")
        self._worker.start()

    def _on_ok(self, paths: list, duration: float) -> None:
        self._worker = None
        self.send_btn.setEnabled(True)
        self.send_btn.setText("生成  ➤")
        model = self._current_model_id()
        durations = [round(duration, 1)] * len(paths)
        for p in paths:
            self._add_card(str(p), model, round(duration, 1))
        self.session["messages"].append(
            {
                "role": "assistant", "type": "images",
                "paths": [str(p) for p in paths], "durations": durations,
                "model": model,
            }
        )
        if paths:
            self.session["current_image"] = str(paths[-1])
        self._apply_current_image()
        self.sessions.save(self.session)
        self._scroll_to_bottom()

    def _on_err(self, message: str) -> None:
        self._worker = None
        self.send_btn.setEnabled(True)
        self.send_btn.setText("生成  ➤")
        self._add_bubble(_ErrorBubble(message))
        self.session["messages"].append(
            {"role": "assistant", "type": "error", "text": message}
        )
        self.sessions.save(self.session)
        self._scroll_to_bottom()

    # ------------------------------------------------------------------
    # 流内容
    # ------------------------------------------------------------------
    def _add_bubble(self, widget: QWidget) -> None:
        self.flow.insertWidget(self.flow.count() - 1, widget)
        self._scroll_to_bottom()

    def _add_card(self, path: str, model: str, duration: float,
                  record: bool = True) -> _ResultCard:
        card = _ResultCard(self.service, path, model, duration)
        card.selected.connect(self._select_current)
        self._cards.append(card)
        self.flow.insertWidget(self.flow.count() - 1, card)
        self._scroll_to_bottom()
        return card

    def _select_current(self, path: str) -> None:
        self.session["current_image"] = path
        self._apply_current_image()
        self.sessions.save(self.session)

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

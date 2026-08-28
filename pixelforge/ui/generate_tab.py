"""生成页签：输入提示词、选择模型与参数、预览与保存图片。

支持：
  - 提示词模板一键填入
  - 批量生成多张，缩略图条并排展示，点击切换大图对比
  - 保存当前选中图片 / 打开原图
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

from PyQt5.QtCore import QThread, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QKeySequence
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QShortcut, QSizePolicy, QSpinBox,
    QVBoxLayout, QWidget,
)

from pixelforge.models.providers import get_provider
from pixelforge.models.prompts import TEMPLATES
from pixelforge.ui.compare_dialog import CompareDialog
from pixelforge.utils.helpers import (
    AdvancedParams, OptimizeWorker, error, info, load_pixmap,
    save_image_dialog,
)

THUMB_SIZE = 120  # 缩略图显示高度


class _GenerationWorker(QThread):
    """后台生成线程，避免阻塞 UI。"""

    finished_ok = pyqtSignal(list)   # 保存路径列表
    finished_err = pyqtSignal(str)   # 错误信息

    def __init__(self, service, prompt, model, size, num, neg="", adv=None) -> None:
        super().__init__()
        self.service = service
        self.prompt = prompt
        self.model = model
        self.size = size
        self.num = num
        self.neg = neg
        self.adv = adv or {}
        self._cancelled = False

    def cancel(self) -> None:
        """标记取消。因接口为同步阻塞，无法中断底层请求，
        请求仍会跑完，但结果会被丢弃。"""
        self._cancelled = True

    def run(self) -> None:
        try:
            paths = self.service.generate(
                self.prompt, self.model, self.size, self.num,
                self.neg, **self.adv,
            )
            if self._cancelled:
                return  # 已取消：丢弃结果
            self.finished_ok.emit(paths)
        except Exception as exc:  # noqa: BLE001
            if not self._cancelled:
                self.finished_err.emit(str(exc))


class _ThumbLabel(QLabel):
    """可点击的缩略图。"""

    clicked = pyqtSignal(int)

    def __init__(self, index: int) -> None:
        super().__init__()
        self.index = index
        self.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            "border:2px solid rgba(128,128,128,0.45); background:rgba(128,128,128,0.10);"
        )
        self.setScaledContents(False)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setStyleSheet(
            "border:2px solid #0891B2; background:rgba(128,128,128,0.10);"
            if selected
            else "border:2px solid rgba(128,128,128,0.45); background:rgba(128,128,128,0.10);"
        )


class GenerateTab(QWidget):
    """生成主界面。"""

    # 用户点击“用作图生图参考”时发射，携带图片路径
    continue_edit_requested = pyqtSignal(str)

    def __init__(self, config, service, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.service = service

        self._current_paths: List[Path] = []
        self._current_index: int = 0
        self._thumb_labels: List[_ThumbLabel] = []
        self._worker: _GenerationWorker | None = None

        self._build_ui()
        self._bind_shortcuts()
        self.refresh_models()
        self._check_api_key()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- 主预览区域 ---
        self.preview = QLabel("在这里显示生成的图片", self)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(280)
        self.preview.setStyleSheet(
            "background:rgba(128,128,128,0.10); color:#888; border:1px dashed rgba(128,128,128,0.45);"
        )
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setContextMenuPolicy(3)  # CustomContextMenu
        self.preview.customContextMenuRequested.connect(self._show_context_menu)
        root.addWidget(self.preview, 1)

        # --- 参数行：模型 / 尺寸 / 数量 ---
        params = QHBoxLayout()
        params.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        params.addWidget(self.model_combo, 2)

        params.addWidget(QLabel("尺寸:"))
        self.size_combo = QComboBox()
        params.addWidget(self.size_combo)

        params.addWidget(QLabel("数量:"))
        self.num_spin = QSpinBox()
        self.num_spin.setRange(1, 4)
        self.num_spin.setValue(1)
        params.addWidget(self.num_spin)
        root.addLayout(params)

        # --- 模板行 ---
        tpl_row = QHBoxLayout()
        tpl_row.addWidget(QLabel("模板:"))
        self.tpl_category = QComboBox()
        self.tpl_category.currentIndexChanged.connect(self._fill_templates)
        tpl_row.addWidget(self.tpl_category)

        self.tpl_combo = QComboBox()
        self.tpl_combo.addItem("（不使用模板）", None)
        self.tpl_combo.activated.connect(self._apply_template)
        tpl_row.addWidget(self.tpl_combo, 1)
        root.addLayout(tpl_row)

        # --- 提示词 + 生成 ---
        prompt_row = QHBoxLayout()
        self.prompt_edit = QLineEdit()
        self.prompt_edit.setPlaceholderText(
            "请输入图片描述，例如：一只在海边奔跑的金毛犬，夕阳背景"
        )
        prompt_row.addWidget(self.prompt_edit, 1)

        self.optimize_btn = QPushButton("✨ 优化提示词")
        self.optimize_btn.setToolTip(
            "调用 AI 把当前描述改写成更高质量的提示词（结果可编辑）"
        )
        self.optimize_btn.clicked.connect(self.optimize_prompt)
        prompt_row.addWidget(self.optimize_btn)

        self.generate_btn = QPushButton("生成")
        self.generate_btn.clicked.connect(self.generate)
        prompt_row.addWidget(self.generate_btn)
        root.addLayout(prompt_row)

        # --- 负面提示词（negative prompt） ---
        neg_row = QHBoxLayout()
        neg_row.addWidget(QLabel("不想要:"))
        self.neg_edit = QLineEdit()
        self.neg_edit.setPlaceholderText(
            "负面提示词（可留空）：描述不希望出现的内容，如：模糊、低质量、变形的手"
        )
        self.neg_edit.setClearButtonEnabled(True)
        neg_row.addWidget(self.neg_edit, 1)
        root.addLayout(neg_row)

        # --- 高级参数（折叠） ---
        self.adv_params = AdvancedParams()
        root.addWidget(self.adv_params)

        # --- 缩略图条（批量结果对比） ---
        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setFixedHeight(THUMB_SIZE + 12)
        self.thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.thumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        thumb_container = QWidget()
        self.thumb_layout = QHBoxLayout(thumb_container)
        self.thumb_layout.setContentsMargins(0, 0, 0, 0)
        self.thumb_layout.addStretch(1)
        self.thumb_scroll.setWidget(thumb_container)
        self.thumb_scroll.setVisible(False)
        root.addWidget(self.thumb_scroll)

        # --- 操作行 ---
        actions = QHBoxLayout()
        self.fav_btn = QPushButton("☆ 收藏")
        self.fav_btn.setToolTip("把当前图片收藏到收藏夹")
        self.fav_btn.setEnabled(False)
        self.fav_btn.clicked.connect(self._favorite)
        actions.addWidget(self.fav_btn)

        self.save_btn = QPushButton("保存当前图片")
        self.save_btn.clicked.connect(self.save_image)
        self.save_btn.setEnabled(False)
        actions.addWidget(self.save_btn)

        self.open_btn = QPushButton("打开原图")
        self.open_btn.clicked.connect(self.open_current)
        self.open_btn.setEnabled(False)
        actions.addWidget(self.open_btn)

        self.compare_btn = QPushButton("并排对比")
        self.compare_btn.setToolTip("把当前这批结果以大图并排展示对比")
        self.compare_btn.setEnabled(False)
        self.compare_btn.clicked.connect(self.open_compare)
        actions.addWidget(self.compare_btn)

        self.edit_btn = QPushButton("用作图生图参考")
        self.edit_btn.setToolTip(
            "把当前图片发送到图生图标签页，作为继续编辑的参考图"
        )
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._send_to_edit)
        actions.addWidget(self.edit_btn)

        self.status = QLabel("")
        self.status.setStyleSheet("color:#666;")
        actions.addWidget(self.status, 1)
        root.addLayout(actions)

        # 填充模板分类
        self._fill_categories()

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+Return"), self, self.generate)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self.generate)

    # ------------------------------------------------------------------
    # 模板
    # ------------------------------------------------------------------
    def _fill_categories(self) -> None:
        cats = []
        for t in TEMPLATES:
            if t.category not in cats:
                cats.append(t.category)
        self.tpl_category.blockSignals(True)
        self.tpl_category.addItem("全部", None)
        for c in cats:
            self.tpl_category.addItem(c, c)
        self.tpl_category.blockSignals(False)
        self._fill_templates()

    def _fill_templates(self) -> None:
        """按当前分类填充模板下拉框。"""
        category = self.tpl_category.currentData()
        items = [t for t in TEMPLATES if not category or t.category == category]
        self.tpl_combo.blockSignals(True)
        self.tpl_combo.clear()
        self.tpl_combo.addItem("（不使用模板）", None)
        for t in items:
            self.tpl_combo.addItem(t.name, t)
        self.tpl_combo.blockSignals(False)

    def _apply_template(self) -> None:
        """把选中的模板填入提示词编辑框，保留用户已输入的部分。"""
        tpl = self.tpl_combo.currentData()
        if tpl is None:
            return
        content = self.prompt_edit.text().strip() or tpl.placeholder
        # 替换第一个 {占位符}
        final = re.sub(r"\{[^}]*\}", content, tpl.text, count=1)
        self.prompt_edit.setText(final)
        self.prompt_edit.setFocus()

    # ------------------------------------------------------------------
    # 数据刷新
    # ------------------------------------------------------------------
    def refresh_models(self) -> None:
        """填充模型下拉框。

        已配置 Key 时动态查询当前账户可用模型（更准确）；
        否则使用预置回退列表。
        """
        current = self.config.get("model.model", "")
        models = []

        # 优先动态查询可用模型
        if self.service.has_api_key():
            models = self.service.list_available_models()

        # 回退到预置列表
        if not models:
            provider = get_provider(
                self.config.get("model.provider", "siliconflow")
            )
            models = provider.models if provider else []

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for m in models:
            self.model_combo.addItem(m.name, m.id)
        idx = self.model_combo.findData(current)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)
        self._on_model_changed()

    def _on_model_changed(self) -> None:
        """切换模型时刷新可选尺寸。"""
        provider = get_provider(self.config.get("model.provider", "siliconflow"))
        model_id = self.model_combo.currentData()
        sizes = self.config.get("model.size", "1024x1024")
        if provider:
            for m in provider.models:
                if m.id == model_id and m.sizes:
                    sizes = m.sizes[0] if sizes not in m.sizes else sizes
        self.size_combo.clear()
        if provider:
            for m in provider.models:
                if m.id == model_id:
                    self.size_combo.addItems(m.sizes or [sizes])
                    break
        if self.size_combo.count() == 0:
            self.size_combo.addItem(sizes)

    # ------------------------------------------------------------------
    # 交互动作
    # ------------------------------------------------------------------
    def _check_api_key(self) -> None:
        if not self.service.has_api_key():
            self.status.setText("提示：尚未设置 API Key，请点击工具栏 [设置]")

    def optimize_prompt(self) -> None:
        """调用 LLM 优化当前提示词，结果填入输入框（可编辑）。"""
        text = self.prompt_edit.text().strip()
        if not text:
            error(self, "提示", "请先输入要优化的描述")
            return
        self.optimize_btn.setEnabled(False)
        self.optimize_btn.setText("优化中…")
        self.status.setText("正在优化提示词…")
        self._opt_worker = OptimizeWorker(self.service, text)
        self._opt_worker.finished.connect(self._on_optimized)
        self._opt_worker.failed.connect(self._on_optimize_failed)
        self._opt_worker.start()

    def _on_optimized(self, result: str) -> None:
        self.prompt_edit.setText(result)
        self._reset_optimize_btn()
        self.status.setText("提示词已优化，可手动修改后再生成")

    def _on_optimize_failed(self, message: str) -> None:
        self._reset_optimize_btn()
        self.status.setText("提示词优化失败")
        error(self, "优化失败", message)

    def _reset_optimize_btn(self) -> None:
        self.optimize_btn.setEnabled(True)
        self.optimize_btn.setText("✨ 优化提示词")

    def generate(self) -> None:
        """触发生成；若正在生成则切换为取消。"""
        if self._worker and self._worker.isRunning():
            self._cancel_worker()
            return

        prompt = self.prompt_edit.text().strip()
        if not prompt:
            error(self, "提示", "请先输入图片描述")
            return

        model = self.model_combo.currentData()
        size = self.size_combo.currentText()
        num = self.num_spin.value()
        neg = self.neg_edit.text().strip()
        adv = self.adv_params.values()

        # 生成中：禁用其他按钮，但生成按钮保持可用（作为“取消”）
        self.generate_btn.setEnabled(True)
        self.save_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.fav_btn.setEnabled(False)
        self.compare_btn.setEnabled(False)
        self.status.setText("正在生成，请稍候…")
        self.preview.clear()
        self._clear_thumbs()

        self._worker = _GenerationWorker(
            self.service, prompt, model, size, num, neg, adv
        )
        self._worker.finished_ok.connect(self._on_done)
        self._worker.finished_err.connect(self._on_fail)
        self._worker.start()

        # 生成中按钮变为“取消”
        self.generate_btn.setText("取消")

    def _cancel_worker(self) -> None:
        """取消当前生成：立即恢复 UI，后台请求继续跑完但结果被丢弃。"""
        if not self._worker:
            return
        self._worker.cancel()
        # 断开信号，避免孤儿线程结束后仍更新界面
        try:
            self._worker.finished_ok.disconnect()
        except (RuntimeError, TypeError):
            pass
        try:
            self._worker.finished_err.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._worker = None

        self.generate_btn.setText("生成")
        self.generate_btn.setEnabled(True)
        self.status.setText("已取消（本次生成费用不会返还）")

    def _on_done(self, paths: List[Path]) -> None:
        self._current_paths = paths
        self._current_index = 0
        self.preview.setStyleSheet("background:rgba(128,128,128,0.10); border:1px solid rgba(128,128,128,0.45);")
        self._show_image(0)
        self._populate_thumbs()
        self.status.setText(f"完成，生成 {len(paths)} 张图片")
        self.save_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        self.fav_btn.setEnabled(True)
        self.compare_btn.setEnabled(len(paths) >= 2)
        self.edit_btn.setEnabled(True)
        self._update_fav_state()
        self.generate_btn.setText("生成")
        self.generate_btn.setEnabled(True)

    def _on_fail(self, message: str) -> None:
        self.status.setText("生成失败")
        self.generate_btn.setText("生成")
        self.generate_btn.setEnabled(True)
        error(self, "生成失败", message)

    # ------------------------------------------------------------------
    # 预览 / 缩略图
    # ------------------------------------------------------------------
    def _show_image(self, index: int) -> None:
        """在主预览显示第 index 张。"""
        if not self._current_paths or not (0 <= index < len(self._current_paths)):
            return
        self._current_index = index
        pixmap = load_pixmap(str(self._current_paths[index]))
        self.preview.setPixmap(pixmap)
        for i, lbl in enumerate(self._thumb_labels):
            lbl.set_selected(i == index)
        self._update_fav_state()
        self.status.setText(f"查看第 {index + 1}/{len(self._current_paths)} 张")

    def _clear_thumbs(self) -> None:
        for lbl in self._thumb_labels:
            lbl.deleteLater()
        self._thumb_labels.clear()
        self.thumb_scroll.setVisible(False)

    def _populate_thumbs(self) -> None:
        """为所有生成结果创建缩略图。"""
        self._clear_thumbs()
        for i, path in enumerate(self._current_paths):
            pixmap = load_pixmap(str(path), max_size=THUMB_SIZE * 2)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    THUMB_SIZE, THUMB_SIZE,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
            thumb = _ThumbLabel(i)
            thumb.setPixmap(pixmap)
            thumb.clicked.connect(self._show_image)
            thumb.set_selected(i == 0)
            self._thumb_labels.append(thumb)
            # 缩略图插入到 stretch 之前
            self.thumb_layout.insertWidget(
                self.thumb_layout.count() - 1, thumb
            )
        if self._current_paths:
            self.thumb_scroll.setVisible(True)

    # ------------------------------------------------------------------
    # 收藏夹
    # ------------------------------------------------------------------
    def _favorite(self) -> None:
        """收藏 / 取消收藏当前图片。"""
        if not self._current_paths:
            return
        src = self._current_paths[self._current_index]

        # 已在收藏夹 -> 取消收藏（需确认，防止误删）
        if self.service.is_favorited(src):
            if (
                QMessageBox.question(
                    self,
                    "取消收藏",
                    "确定要取消收藏这张图片吗？\n（将从收藏夹中移除）",
                )
                == QMessageBox.Yes
            ):
                self.service.unfavorite(src)
                self._update_fav_state()
            return

        # 未收藏 -> 收藏
        try:
            dst = self.service.favorite(src)
        except Exception as exc:  # noqa: BLE001
            error(self, "收藏失败", str(exc))
            return
        self._update_fav_state()
        info(self, "收藏成功", f"已收藏到：\n{dst}")

    def _update_fav_state(self) -> None:
        """根据当前图片是否已收藏，刷新星星按钮状态。"""
        fav = bool(
            self._current_paths
            and self.service.is_favorited(
                self._current_paths[self._current_index]
            )
        )
        self.fav_btn.setText("★ 已收藏" if fav else "☆ 收藏")
        self.fav_btn.setStyleSheet(
            "color:#f5a623; font-weight:bold;" if fav else ""
        )
        self.fav_btn.setToolTip(
            "点击取消收藏" if fav else "把当前图片收藏到收藏夹"
        )

    # ------------------------------------------------------------------
    # 保存 / 打开
    # ------------------------------------------------------------------
    def save_image(self) -> None:
        if not self._current_paths:
            return
        src = self._current_paths[self._current_index]
        dst = save_image_dialog(self, src.name)
        if dst:
            Path(src).replace(dst)
            info(self, "保存成功", f"图片已保存到：\n{dst}")

    def open_current(self) -> None:
        """用系统默认程序打开当前图片。"""
        if not self._current_paths:
            return
        path = self._current_paths[self._current_index]
        if Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            error(self, "无法打开", "图片文件不存在或已被移动。")

    def open_compare(self) -> None:
        """打开对比对话框，并排展示当前批次所有结果。"""
        if len(self._current_paths) < 2:
            return
        CompareDialog(self._current_paths, self).exec_()

    def _send_to_edit(self) -> None:
        """把当前图片发送到图生图标签页作为参考图。"""
        if not self._current_paths:
            return
        path = self._current_paths[self._current_index]
        if not Path(path).exists():
            error(self, "无法发送", "图片文件不存在或已被移动。")
            return
        self.continue_edit_requested.emit(str(path))

    def _show_context_menu(self, pos) -> None:
        """右键预览区域：保存当前图片 / 打开原图。"""
        if not self._current_paths:
            return
        menu = self.preview.createStandardContextMenu()
        menu.addSeparator()
        save_action = menu.addAction("保存当前图片")
        open_action = menu.addAction("打开原图")
        chosen = menu.exec_(self.preview.mapToGlobal(pos))
        if chosen == save_action:
            self.save_image()
        elif chosen == open_action:
            self.open_current()

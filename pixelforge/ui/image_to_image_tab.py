"""图生图标签页：选择参考图 + 文本指令，调用图生图模型生成。

交互类似文生图，但多了"选择参考图"步骤。模型使用编辑类模型
（如 Qwen-Image-Edit）。
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QKeySequence
from PyQt5.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QShortcut, QSizePolicy, QSpinBox,
    QVBoxLayout, QWidget,
)

from pixelforge.ui.compare_dialog import CompareDialog
from pixelforge.utils.helpers import (
    AdvancedParams, OptimizeWorker, error, info, load_pixmap,
    save_image_dialog,
)

THUMB_SIZE = 120
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


class _EditWorker(QThread):
    """后台图生图线程。"""

    finished_ok = pyqtSignal(list)
    finished_err = pyqtSignal(str)

    def __init__(self, service, prompt, model, size, num, ref_path, neg="", adv=None) -> None:
        super().__init__()
        self.service = service
        self.prompt = prompt
        self.model = model
        self.size = size
        self.num = num
        self.ref_path = ref_path
        self.neg = neg
        self.adv = adv or {}
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            paths = self.service.image_to_image(
                self.prompt, self.model, self.ref_path, self.size,
                self.num, self.neg, **self.adv,
            )
            if self._cancelled:
                return
            self.finished_ok.emit(paths)
        except Exception as exc:  # noqa: BLE001
            if not self._cancelled:
                self.finished_err.emit(str(exc))


class _ThumbLabel(QLabel):
    clicked = pyqtSignal(int)

    def __init__(self, index: int) -> None:
        super().__init__()
        self.index = index
        self.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border:2px solid #555; background:#1e1e1e;")
        self.setScaledContents(False)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setStyleSheet(
            "border:2px solid #4a90d9; background:#1e1e1e;"
            if selected
            else "border:2px solid #555; background:#1e1e1e;"
        )


class ImageToImageTab(QWidget):
    """图生图主界面。"""

    def __init__(self, config, service, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.service = service

        self.ref_image: Optional[Path] = None
        self._current_paths: List[Path] = []
        self._current_index: int = 0
        self._thumb_labels: List[_ThumbLabel] = []
        self._worker: _EditWorker | None = None

        self._build_ui()
        self._bind_shortcuts()
        self.refresh_models()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # 参考图选择
        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("参考图:"))
        self.ref_preview = QLabel("（未选择）")
        self.ref_preview.setFixedSize(96, 96)
        self.ref_preview.setAlignment(Qt.AlignCenter)
        self.ref_preview.setStyleSheet(
            "background:#2a2a2a; color:#888; border:1px dashed #555;"
        )
        ref_row.addWidget(self.ref_preview)

        self.ref_name = QLabel("")
        self.ref_name.setStyleSheet("color:#888;")
        ref_row.addWidget(self.ref_name, 1)

        self.choose_btn = QPushButton("选择图片")
        self.choose_btn.clicked.connect(self.choose_reference)
        ref_row.addWidget(self.choose_btn)
        root.addLayout(ref_row)

        # 参数行
        params = QHBoxLayout()
        params.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
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

        # 主预览
        self.preview = QLabel("在这里显示生成的图片", self)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(260)
        self.preview.setStyleSheet(
            "background:#1e1e1e; color:#888; border:1px dashed #555;"
        )
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setContextMenuPolicy(3)
        self.preview.customContextMenuRequested.connect(self._show_context_menu)
        root.addWidget(self.preview, 1)

        # 提示词 + 生成
        prompt_row = QHBoxLayout()
        self.prompt_edit = QLineEdit()
        self.prompt_edit.setPlaceholderText(
            "输入编辑指令，例如：把画面改成水彩风格，或给人物戴上帽子"
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

        # 负面提示词
        neg_row = QHBoxLayout()
        neg_row.addWidget(QLabel("不想要:"))
        self.neg_edit = QLineEdit()
        self.neg_edit.setPlaceholderText(
            "负面提示词（可留空）：描述不希望出现的内容，如：模糊、低质量、变形"
        )
        self.neg_edit.setClearButtonEnabled(True)
        neg_row.addWidget(self.neg_edit, 1)
        root.addLayout(neg_row)

        # 高级参数（折叠）
        self.adv_params = AdvancedParams()
        root.addWidget(self.adv_params)

        # 缩略图条
        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setFixedHeight(THUMB_SIZE + 12)
        self.thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.thumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tc = QWidget()
        self.thumb_layout = QHBoxLayout(tc)
        self.thumb_layout.setContentsMargins(0, 0, 0, 0)
        self.thumb_layout.addStretch(1)
        self.thumb_scroll.setWidget(tc)
        self.thumb_scroll.setVisible(False)
        root.addWidget(self.thumb_scroll)

        # 操作行
        actions = QHBoxLayout()
        self.fav_btn = QPushButton("☆ 收藏")
        self.fav_btn.setEnabled(False)
        self.fav_btn.clicked.connect(self._favorite)
        actions.addWidget(self.fav_btn)

        self.save_btn = QPushButton("保存当前图片")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_image)
        actions.addWidget(self.save_btn)

        self.compare_btn = QPushButton("并排对比")
        self.compare_btn.setEnabled(False)
        self.compare_btn.clicked.connect(self.open_compare)
        actions.addWidget(self.compare_btn)

        self.edit_btn = QPushButton("用此结果继续编辑")
        self.edit_btn.setToolTip(
            "把当前结果作为新的参考图，输入新的编辑指令继续迭代"
        )
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._continue_editing)
        actions.addWidget(self.edit_btn)

        self.status = QLabel("")
        self.status.setStyleSheet("color:#666;")
        actions.addWidget(self.status, 1)
        root.addLayout(actions)

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+Return"), self, self.generate)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self.generate)

    # ------------------------------------------------------------------
    # 参考图
    # ------------------------------------------------------------------
    def choose_reference(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择参考图", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)",
        )
        if path:
            self.set_reference(Path(path))

    def set_reference(self, path: Path) -> None:
        self.ref_image = path
        pixmap = load_pixmap(str(path), max_size=96)
        self.ref_preview.setPixmap(pixmap)
        self.ref_name.setText(path.name)
    # ------------------------------------------------------------------
    # 模型
    # ------------------------------------------------------------------
    def refresh_models(self) -> None:
        models = self.service.list_available_edit_models()
        self.model_combo.clear()
        for m in models:
            self.model_combo.addItem(m.name, m.id)
        if self.model_combo.count() == 0:
            # 当前平台无可用图生图模型：给出提示而非塞入不可用模型
            self.model_combo.addItem(
                "（当前平台无可用图生图模型，请切换到硅基流动）", None
            )
            self.model_combo.setEnabled(False)
        else:
            self.model_combo.setEnabled(True)
        self._on_model_changed()

    def _on_model_changed(self) -> None:
        self.size_combo.clear()
        self.size_combo.addItems(["512x512", "768x768", "1024x1024"])

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------
    def optimize_prompt(self) -> None:
        """调用 LLM 优化当前编辑指令，结果填入输入框（可编辑）。"""
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
        if self._worker and self._worker.isRunning():
            self._cancel_worker()
            return

        if self.ref_image is None:
            error(self, "提示", "请先选择一张参考图")
            return
        prompt = self.prompt_edit.text().strip()
        if not prompt:
            error(self, "提示", "请输入编辑指令")
            return

        model = self.model_combo.currentData()
        if not model:
            error(
                self, "提示",
                "当前平台没有可用的图生图模型，请在设置中切换到硅基流动。",
            )
            return
        size = self.size_combo.currentText()
        num = self.num_spin.value()
        neg = self.neg_edit.text().strip()
        adv = self.adv_params.values()

        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("取消")
        self.save_btn.setEnabled(False)
        self.fav_btn.setEnabled(False)
        self.compare_btn.setEnabled(False)
        self.status.setText("正在生成，请稍候…")
        self.preview.clear()
        self._clear_thumbs()

        self._worker = _EditWorker(
            self.service, prompt, model, size, num, str(self.ref_image),
            neg, adv,
        )
        self._worker.finished_ok.connect(self._on_done)
        self._worker.finished_err.connect(self._on_fail)
        self._worker.start()

    def _cancel_worker(self) -> None:
        if not self._worker:
            return
        self._worker.cancel()
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
        self.preview.setStyleSheet("background:#1e1e1e; border:1px solid #444;")
        self._show_image(0)
        self._populate_thumbs()
        self.status.setText(f"完成，生成 {len(paths)} 张图片")
        self.save_btn.setEnabled(True)
        self.fav_btn.setEnabled(True)
        self.compare_btn.setEnabled(len(paths) >= 2)
        self.edit_btn.setEnabled(True)
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
        if not self._current_paths or not (0 <= index < len(self._current_paths)):
            return
        self._current_index = index
        pixmap = load_pixmap(str(self._current_paths[index]))
        self.preview.setPixmap(pixmap)
        for i, lbl in enumerate(self._thumb_labels):
            lbl.set_selected(i == index)
        self._update_fav_state()

    def _clear_thumbs(self) -> None:
        for lbl in self._thumb_labels:
            lbl.deleteLater()
        self._thumb_labels.clear()
        self.thumb_scroll.setVisible(False)

    def _populate_thumbs(self) -> None:
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
            self.thumb_layout.insertWidget(self.thumb_layout.count() - 1, thumb)
        if self._current_paths:
            self.thumb_scroll.setVisible(True)

    # ------------------------------------------------------------------
    # 收藏
    # ------------------------------------------------------------------
    def _favorite(self) -> None:
        if not self._current_paths:
            return
        src = self._current_paths[self._current_index]
        if self.service.is_favorited(src):
            if (
                QMessageBox.question(
                    self, "取消收藏",
                    "确定要取消收藏这张图片吗？\n（将从收藏夹中移除）",
                )
                == QMessageBox.Yes
            ):
                self.service.unfavorite(src)
                self._update_fav_state()
            return
        try:
            dst = self.service.favorite(src)
        except Exception as exc:  # noqa: BLE001
            error(self, "收藏失败", str(exc))
            return
        self._update_fav_state()
        info(self, "收藏成功", f"已收藏到：\n{dst}")

    def _update_fav_state(self) -> None:
        fav = bool(
            self._current_paths
            and self.service.is_favorited(self._current_paths[self._current_index])
        )
        self.fav_btn.setText("★ 已收藏" if fav else "☆ 收藏")
        self.fav_btn.setStyleSheet(
            "color:#f5a623; font-weight:bold;" if fav else ""
        )

    # ------------------------------------------------------------------
    # 保存 / 对比
    # ------------------------------------------------------------------
    def save_image(self) -> None:
        if not self._current_paths:
            return
        src = self._current_paths[self._current_index]
        dst = save_image_dialog(self, src.name)
        if dst:
            import shutil
            shutil.copy2(src, dst)
            info(self, "保存成功", f"图片已保存到：\n{dst}")

    def open_compare(self) -> None:
        if len(self._current_paths) < 2:
            return
        CompareDialog(self._current_paths, self).exec_()

    def _continue_editing(self) -> None:
        """把当前结果设为新的参考图，供继续迭代编辑。"""
        if not self._current_paths:
            return
        path = self._current_paths[self._current_index]
        if not Path(path).exists():
            error(self, "无法继续", "图片文件不存在或已被移动。")
            return
        self.set_reference(path)
        self.status.setText("已将结果设为参考图，输入新的编辑指令继续")
        self.prompt_edit.setFocus()
        self.prompt_edit.selectAll()

    def _show_context_menu(self, pos) -> None:
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
            path = self._current_paths[self._current_index]
            if Path(path).exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

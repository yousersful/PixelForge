"""PixelForge 主题系统。

设计语言（Material 3 + Apple HIG 折中，适配桌面 PyQt5）：
  - 单一强调色：青色 Cyan（延续原型的对话气泡色）
  - 中性灰阶分 4 层：背景 / 卡片表面 / 描边 / 文字两级
  - 圆角统一 10px（大卡片 14px），阴影单层克制
  - 间距遵循 8pt 网格

浅色 / 深色两套 QSS 由同一 token 表生成，保证一致性；
「跟随系统」通过窗口底色亮度判断。
"""
from __future__ import annotations

from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QApplication

# ----------------------------------------------------------------------
# 设计 Token（浅色 / 深色）
# ----------------------------------------------------------------------
_LIGHT = {
    "bg":        "#F6F7FA",   # 窗口背景
    "surface":   "#FFFFFF",   # 卡片 / 输入框表面
    "surface2":  "#EEF1F5",   # 次级表面（悬停、表格斑马纹）
    "outline":   "#E3E6EC",   # 描边
    "text":      "#1B1E27",   # 主文字
    "text_sub":  "#6B7280",   # 次文字
    "accent":    "#0891B2",   # 强调色（青，可点击元素）
    "accent_on": "#FFFFFF",   # 强调色上的文字
    "accent_soft": "#CFFAFE",  # 强调色柔和底（气泡、选中态）
    "accent_text": "#155E75",  # 柔和底上的文字
    "danger":    "#DC2626",
    "shadow":    "rgba(15, 23, 42, 0.08)",
    "scroll":    "#C9CEDA",
}

_DARK = {
    "bg":        "#15171E",
    "surface":   "#1E222B",
    "surface2":  "#262B36",
    "outline":   "#313745",
    "text":      "#E7EAF0",
    "text_sub":  "#9CA3AF",
    "accent":    "#22D3EE",
    "accent_on": "#0E3A44",
    "accent_soft": "#164E5C",
    "accent_text": "#A5F3FC",
    "danger":    "#F87171",
    "shadow":    "rgba(0, 0, 0, 0.45)",
    "scroll":    "#3B414F",
}

_FONT_FAMILY = '"Microsoft YaHei UI", "PingFang SC", "Noto Sans SC", sans-serif'


def build_qss(theme: str = "light") -> str:
    """生成全局 QSS。theme: light / dark。"""
    t = _DARK if theme == "dark" else _LIGHT
    return f"""
* {{
    font-family: {_FONT_FAMILY};
    font-size: 14px;
    color: {t['text']};
    selection-background-color: {t['accent']};
    selection-color: {t['accent_on']};
}}
QMainWindow, QDialog {{ background-color: {t['bg']}; }}
/* 普通容器必须显式绘制主题背景：透明会漏出系统原生调色板
   （浅色主题在系统深色下会出现黑块） */
QWidget {{ background-color: {t['bg']}; }}
QLabel, QCheckBox, QRadioButton {{
    background: transparent;
}}
QMenuBar {{
    background-color: {t['surface']};
}}
QMenu {{
    background-color: {t['surface']};
    border: 1px solid {t['outline']};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 20px; border-radius: 6px; }}
QMenu::item:selected {{ background-color: {t['accent_soft']}; color: {t['accent_text']}; }}
QToolTip {{
    background-color: {t['surface']};
    color: {t['text']};
    border: 1px solid {t['outline']};
    border-radius: 6px;
    padding: 6px 10px;
}}

/* ---------- 侧栏导航 ---------- */
QWidget#sidebar {{
    background-color: {t['surface']};
    border-right: 1px solid {t['outline']};
}}
QLabel#appTitle {{
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: {t['text']};
    background: transparent;
}}
QPushButton.nav {{
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-radius: 10px;
    color: {t['text_sub']};
    font-size: 15px;
    background: transparent;
}}
QPushButton.nav:hover {{ background-color: {t['surface2']}; color: {t['text']}; }}
QPushButton.nav:checked {{
    background-color: {t['accent_soft']};
    color: {t['accent_text']};
    font-weight: 600;
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background-color: {t['surface']};
    border: 1px solid {t['outline']};
    border-radius: 10px;
    padding: 8px 18px;
    min-height: 20px;
}}
QPushButton:hover {{ background-color: {t['surface2']}; }}
QPushButton:pressed {{ background-color: {t['outline']}; }}
QPushButton:disabled {{ color: {t['text_sub']}; background-color: {t['surface2']}; }}
QPushButton[class="primary"] {{
    background-color: {t['accent']};
    color: {t['accent_on']};
    border: none;
    font-weight: 600;
}}
QPushButton[class="primary"]:hover {{ opacity: 0.9; background-color: {t['accent']}; }}
QPushButton[class="ghost"] {{
    border: none;
    background: transparent;
    color: {t['accent']};
    padding: 4px 8px;
}}
QPushButton[class="ghost"]:hover {{ color: {t['accent_text']}; }}

/* ---------- 输入 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {t['surface']};
    border: 1px solid {t['outline']};
    border-radius: 10px;
    padding: 8px 12px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1.5px solid {t['accent']};
}}
/* 数字框的上下按钮（否则漏出 Windows 原生样式） */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 20px;
    padding: 2px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {t['surface2']};
    border-radius: 4px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    width: 8px; height: 8px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {t['text_sub']};
}}
QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover {{
    border-bottom-color: {t['accent']};
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    width: 8px; height: 8px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t['text_sub']};
}}
QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover {{
    border-top-color: {t['accent']};
}}
QComboBox {{
    background-color: {t['surface']};
    border: 1px solid {t['outline']};
    border-radius: 10px;
    padding: 8px 12px;
    min-width: 90px;
}}
QComboBox:hover {{ background-color: {t['surface2']}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox QAbstractItemView {{
    background-color: {t['surface']};
    border: 1px solid {t['outline']};
    border-radius: 8px;
    selection-background-color: {t['accent_soft']};
    selection-color: {t['accent_text']};
    outline: none;
}}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border: 1.5px solid {t['outline']};
    border-radius: 5px;
    background: {t['surface']};
}}
QCheckBox::indicator:checked {{
    background: {t['accent']};
    border-color: {t['accent']};
}}

/* ---------- 卡片 ---------- */
QFrame[class="card"] {{
    background-color: {t['surface']};
    border: 1px solid {t['outline']};
    border-radius: 14px;
}}
QFrame[class="card"][current="true"] {{
    border: 2px solid {t['accent']};
}}
/* 结果组网格中的缩略格：透明底 + 图片圆角/选中描边 */
QWidget[class="cell"] {{ background: transparent; }}
QLabel[class="cellimg"] {{
    border: 2px solid transparent;
    border-radius: 10px;
}}
QLabel[class="cellimg"][current="true"] {{
    border: 2px solid {t['accent']};
}}
/* 对话气泡 */
QWidget[class="bubble-user-inner"] {{
    background-color: {t['accent_soft']};
    border-radius: 16px;
}}
QLabel[class="bubble-error"] {{
    background-color: {t['surface']};
    color: {t['danger']};
    border: 1px solid {t['danger']};
    border-radius: 12px;
    padding: 10px 14px;
}}
/* 生成中的骨架占位卡（PendingCard） */
QFrame[class="pending-area"] {{
    background-color: {t['surface2']};
    border: 1.5px dashed {t['outline']};
    border-radius: 10px;
}}
QLabel[class="pending-spin"] {{
    font-size: 22px;
    color: {t['accent']};
    background: transparent;
}}
QLabel[class="pending-text"] {{
    font-size: 13px;
    color: {t['text_sub']};
    background: transparent;
}}
QLabel[class="pageTitle"] {{
    font-size: 24px;
    font-weight: 700;
    background: transparent;
}}
QLabel[class="pageCaption"] {{
    font-size: 15px;
    color: {t['text_sub']};
    background: transparent;
}}
QLabel[class="hint"] {{ font-size: 12px; color: {t['text_sub']}; background: transparent; }}
QLabel[class="statusOk"] {{ color: {t['accent_text']}; background: transparent; }}
QLabel[class="statusErr"] {{ color: {t['danger']}; background: transparent; }}

/* ---------- 表格 / 列表 ---------- */
QTableWidget, QTableView {{
    background-color: {t['surface']};
    alternate-background-color: {t['surface2']};
    border: 1px solid {t['outline']};
    border-radius: 10px;
    gridline-color: {t['outline']};
    outline: none;
}}
QHeaderView::section {{
    background-color: {t['surface2']};
    color: {t['text_sub']};
    border: none;
    padding: 8px;
    font-weight: 600;
}}
QTableWidget::item, QTableView::item {{ padding: 4px 8px; }}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {t['accent_soft']};
    color: {t['accent_text']};
}}
QListWidget {{
    background-color: {t['surface']};
    border: 1px solid {t['outline']};
    border-radius: 10px;
    outline: none;
}}
QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget::item:selected {{
    background-color: {t['accent_soft']};
    color: {t['accent_text']};
}}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {t['scroll']}; border-radius: 4px; min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {t['text_sub']}; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {t['scroll']}; border-radius: 4px; min-width: 32px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- 分隔线 / 标签页 ---------- */
QFrame[class="hline"] {{
    border: none;
    border-top: 1px solid {t['outline']};
    max-height: 1px;
}}
QTabWidget::pane {{
    border: 1px solid {t['outline']};
    border-radius: 10px;
    background: {t['surface']};
}}
QTabBar::tab {{
    background: transparent;
    color: {t['text_sub']};
    padding: 8px 18px;
    border: none;
}}
QTabBar::tab:selected {{
    color: {t['accent_text']};
    font-weight: 600;
    border-bottom: 2px solid {t['accent']};
}}
QProgressBar {{
    background: {t['surface2']};
    border: none; border-radius: 5px;
    max-height: 10px;
}}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 5px; }}
"""


def detect_system_theme() -> str:
    """侦测系统深浅色（基于调色板窗口色亮度）。"""
    palette = QApplication.palette()
    return "dark" if palette.color(QPalette.Window).lightness() < 128 else "light"


def resolve_theme(setting: str) -> str:
    """把配置值（light/dark/system）解析成实际主题名。"""
    if setting == "system":
        return detect_system_theme()
    return setting if setting in ("light", "dark") else "light"


def apply_theme(app: QApplication, config) -> str:
    """按配置应用主题，返回实际应用的主题名。"""
    actual = resolve_theme(config.get("appearance.theme", "system"))
    app.setStyleSheet(build_qss(actual))
    return actual

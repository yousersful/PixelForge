"""关于页（原型 Page 10）：简介、署名、开源信息。"""
from __future__ import annotations

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QFrame, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from pixelforge.config import AppConfig

APP_VERSION = "0.2"

_ABOUT_HTML = """
<p>PixelForge 是一个可以让你使用各个平台的 API Key 来生成图片的小工具。</p>
<p>与文本模型的调用不一样，通常而言，如果你需要调用图片生成模型，
你需要按照官方文档给出的示例，自己编写 Python 和 curl 脚本来生成图片。</p>
<p>而市面上大部分有名的工具都有每日的使用额度，一旦用完就无法生成；
这对于不会写代码的朋友们是很大的挑战。于是，在 AI 时代的加持之下，这个工具诞生了——
只要你有某一家模型的 API Key，不需要编写任何代码，就能将你的心中所想复现出来。</p>
<p><b>本工具所有数据均保存在本地</b>，且除了与服务商通讯之外，<b>本身不会联网</b>，请放心使用。</p>
<p>目前已经在 GitHub 上开放源码！欢迎各位下载体验~ 如果大神们对这个工具有什么想法，
也可以随时魔改，但需要注意：<span style="color:#EF4444; font-weight:600;">
不可以将这个工具用于任何违法犯罪的用途！</span></p>
<p>最后，感谢大家下载使用本工具~ 年轻的孩子渴望一颗 GitHub 上的小星星 ⭐~</p>
"""


class AboutPage(QWidget):
    """居中的关于信息页。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(32, 40, 32, 32)
        col.setSpacing(12)
        col.addStretch(1)

        logo = QLabel("PixelForge")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("font-size: 34px; font-weight: 800; letter-spacing: 1px;")
        col.addWidget(logo)

        made = QLabel("Made By Pi Agent + Deepseek + Me(Limeng) + Zcode + GLM")
        made.setAlignment(Qt.AlignCenter)
        made.setProperty("class", "pageCaption")
        col.addWidget(made)

        ver = QLabel(f"Ver {APP_VERSION}")
        ver.setAlignment(Qt.AlignCenter)
        ver.setProperty("class", "hint")
        col.addWidget(ver)

        col.addSpacing(12)

        card = QFrame()
        card.setProperty("class", "card")
        card_col = QVBoxLayout(card)
        card_col.setContentsMargins(28, 20, 28, 20)
        body = QTextBrowser()
        body.setOpenExternalLinks(False)
        body.setHtml(_ABOUT_HTML)
        body.setFrameShape(QFrame.NoFrame)
        body.setReadOnly(True)
        body.setStyleSheet("background: transparent; border: none;")
        card_col.addWidget(body)
        col.addWidget(card, 1)

        link = QPushButton("点击这里前往 PixelForge 的 GitHub 网站 --->")
        link.setProperty("class", "ghost")
        link.setCursor(Qt.PointingHandCursor)
        link.clicked.connect(self._open_repo)
        col.addWidget(link, 0, Qt.AlignCenter)
        col.addStretch(1)

    @staticmethod
    def _open_repo() -> None:
        QDesktopServices.openUrl(QUrl(AppConfig.REPO_URL))

"""PixelForge 应用入口"""
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from pixelforge.config import AppConfig
from pixelforge.ui.main_window import MainWindow
from pixelforge.ui.theme import apply_theme


def main() -> int:
    """启动应用"""
    # 高分屏适配：跟随系统缩放（如 2560x1600 + 150%），须在 QApplication 创建前设置
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("PixelForge")
    app.setOrganizationName("PixelForge")

    config = AppConfig()
    config.load()

    apply_theme(app, config)

    window = MainWindow(config)
    window.show()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())

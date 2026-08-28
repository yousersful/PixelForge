"""PixelForge 应用入口"""
import sys

from PyQt5.QtWidgets import QApplication

from pixelforge.config import AppConfig
from pixelforge.ui.main_window import MainWindow
from pixelforge.ui.theme import apply_theme


def main() -> int:
    """启动应用"""
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

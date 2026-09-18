"""GUI entry point for the Expo Studio desktop application."""

from __future__ import annotations

import logging
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from expo_jbm329.app.bootstrap import run_bootstrap
from expo_jbm329.app.expo_studio import ExpoStudio


def gui_main() -> int:
    """Main function for the GUI application.

    Initializes the QApplication, shows a splash screen, and starts the main window.
    :return: Int
    """
    app = QApplication(sys.argv)
    run_bootstrap()

    splash = QSplashScreen(QPixmap(":/splash/splash.png"))
    splash.showMessage("Starting…", Qt.AlignmentFlag.AlignTop, Qt.GlobalColor.white)
    splash.show()
    app.processEvents()

    win = ExpoStudio()
    win.init_services()

    splash.finish(win)
    splash.deleteLater()
    app.processEvents()

    win.show()

    exit_code = app.exec()

    # The application has already run its closeEvent cleanup at this point.
    # On some Linux/PyQt/Python combinations, QApplication destruction can
    # segfault during interpreter shutdown. Avoid that native teardown path.
    # closeEvent has already stopped jobs, closed DB connections, and flushed app cleanup.
    # This only skips final Python/PyQt wrapper destruction.
    if (
        sys.platform.startswith("linux")
        and os.environ.get("EXPO_HARD_EXIT_AFTER_QT", "1") == "1"
    ):
        logging.shutdown()
        os._exit(exit_code)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(gui_main())

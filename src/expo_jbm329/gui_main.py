"""GUI entry point for the Expo Studio desktop application."""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from expo_jbm329.app.bootstrap import run_bootstrap
from expo_jbm329.app.expo_studio import ExpoStudio

if TYPE_CHECKING:
    from collections.abc import Sequence


def _extract_console_log_flag(argv: Sequence[str]) -> tuple[list[str], bool]:
    """Remove the launch flag without consuming Qt options or arguments after `--`."""
    if not argv:
        return [], False
    qt_args = [argv[0]]
    requested = False
    for index, arg in enumerate(argv[1:], start=1):
        if arg == "--":
            qt_args.extend(argv[index:])
            break
        if arg == "--console-log":
            requested = True
        else:
            qt_args.append(arg)
    return qt_args, requested


def gui_main() -> int:
    """Main function for the GUI application.

    Initializes the QApplication, shows a splash screen, and starts the main window.
    :return: Int
    """
    qt_args, console_log = _extract_console_log_flag(sys.argv)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(qt_args)
    run_bootstrap()

    splash = QSplashScreen(QPixmap(":/splash/splash.png"))
    splash.showMessage("Starting…", Qt.AlignmentFlag.AlignTop, Qt.GlobalColor.white)
    splash.show()
    app.processEvents()

    win = ExpoStudio()
    win.init_services(console_log=console_log)

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
    if sys.platform.startswith("linux") and os.environ.get("EXPO_HARD_EXIT_AFTER_QT", "1") == "1":
        logging.shutdown()
        os._exit(exit_code)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(gui_main())

# hooks/rthook_restore_environ.py
import os
import sys

# Restore LD_LIBRARY_PATH and Qt environment variables on Linux if running in a PyInstaller frozen bundle.
# PyInstaller modifies LD_LIBRARY_PATH to point to _internal, and PyQt6 runtime hooks set QT_PLUGIN_PATH
# and QML2_IMPORT_PATH, which causes external helper tools (e.g. kde-open, xdg-open, web browsers)
# to fail due to dynamic linker or Qt platform plugin conflicts.
if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
    # Dynamic linker path
    if "LD_LIBRARY_PATH_ORIG" in os.environ:
        os.environ["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH_ORIG"]
    elif "LD_LIBRARY_PATHORIG" in os.environ:
        os.environ["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATHORIG"]
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)

    # Qt plugin and QML environment variables
    for var in (
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QML_IMPORT_PATH",
        "QML2_IMPORT_PATH",
    ):
        orig_var = f"{var}_ORIG"
        if orig_var in os.environ:
            os.environ[var] = os.environ[orig_var]
        else:
            os.environ.pop(var, None)

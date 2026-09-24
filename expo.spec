# PyInstaller spec file (Python)
from pathlib import Path

import os
import warnings

from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
    collect_dynamic_libs,
    copy_metadata,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyInstaller.building.build_main import (
        Analysis,
        PYZ,    # type: ignore[misc]
        EXE,    # type: ignore[misc]
        COLLECT     # type: ignore[misc]
    )


import platform
IS_WIN = platform.system() == "Windows"


block_cipher = None

# -------------------------------
# Project root
# -------------------------------
ROOT = Path.cwd()
print(f"[spec] ROOT={ROOT}")

# -------------------------------
# Collect data files, binaries and hidden imports
# -------------------------------
datas = []
binaries = []

PROFILING_IMPORT_PACKAGE = "data_profiling"
PROFILING_DISTRIBUTION = "fg-data-profiling"

# -------------------------------
# Qt6 (PyQt6) - plugins and DLL:s
# -------------------------------
qt6_plugins = collect_data_files(
    "PyQt6.Qt6",
    includes=[
        "plugins/platforms/*",
        "plugins/imageformats/*",
        "plugins/styles/*",
    ],
)
qt6_libs = collect_dynamic_libs("PyQt6.Qt6")

datas += qt6_plugins
binaries += qt6_libs

# -------------------------------
# Hidden imports (Core + optional profiling)
# -------------------------------
hiddenimports = []
hiddenimports += collect_submodules("jinja2")
# hiddenimports += collect_submodules("pkg_resources")
hiddenimports += ["pkg_resources"]
hiddenimports += ["matplotlib.backends.backend_svg"]

try:
    import data_profiling  # noqa: F401
except ImportError:
    print("[spec] data_profiling not installed; profiling support will not be bundled.")
else:
    hiddenimports += collect_submodules(f"{PROFILING_IMPORT_PACKAGE}.model.pandas")
    hiddenimports += collect_submodules(f"{PROFILING_IMPORT_PACKAGE}.report.presentation.flavours.html")
    datas += copy_metadata(PROFILING_DISTRIBUTION)
    datas += collect_data_files(
        PROFILING_IMPORT_PACKAGE,
        includes=[
            "report/presentation/flavours/html/templates/*",
            "report/presentation/flavours/html/templates/**/*",
            "assets/*",
            "assets/**/*",
        ],
        include_py_files=False,
    )

for _pkg in ("jinja2", "pandas", "numpy"):
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass

# -------------------------------
# Highlighter themes (custom JSON)
# -------------------------------
datas += [
    (
        "src/expo_jbm329/workbench/theme/themes/custom/*.json",
        "theme/themes/custom"
    )
]

# -------------------------------
# i18n / Qt translations (runtime)
# -------------------------------
datas += [
    (
        "src/expo_jbm329/i18n/locales/*.qm",
        "i18n/locales",
    )
]

# -------------------------------
# REST samples (runtime)
# -------------------------------
datas += [
    (
        "src/expo_jbm329/bootstrap/rest/*.json",
        "bootstrap/rest",
    )
]

# -------------------------------
# Analysis (OBS: runtime-hook to shut down typeguard)
# -------------------------------
a = Analysis(
    ["src/expo_jbm329/gui_main.py"],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[
        str(ROOT / "hooks" / "rthook_disable_typeguard.py"),
        str(ROOT / "hooks" / "rthook_typeguard_nop.py"),
        str(ROOT / "hooks" / "rthook_tqdm_disable.py"),
    ],
    excludes=[
        "Cython",
        "IPython",
        "_pytest",
        "coverage",
        "cython",
        "google.colab",
        "ipywidgets",
        "matplotlib.tests",
        "notebook",
        "pyspark",
        "pytest",
        "sphinx",
        "data_profiling.model.spark",
        "data_profiling.report.presentation.flavours.widget",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Build mode env: EXPO_ONEFILE=1 -> onefile, else onedir
IS_ONEFILE = os.environ.get("EXPO_ONEFILE") == "1"
print(f"[spec] ONEFILE={IS_ONEFILE}")
if IS_ONEFILE:
    # ONEFILE: everything in one EXE, no separate COLLECT
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        exclude_binaries=False,
        name="expo",
        debug=False,
        bootloader_ignore_signals=False,
        strip=not IS_WIN,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(ROOT / "src" / "expo_jbm329" / "workbench" / "icon" / "app.ico"),
    )
else:
    # ONEDIR: EXE + COLLECT
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="expo",
        debug=False,
        bootloader_ignore_signals=False,
        strip=not IS_WIN,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(ROOT / "src" / "expo_jbm329" / "workbench" / "icon" / "app.ico"),
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=not IS_WIN,
        upx=True,
        upx_exclude=[],
        name="expo",
    )

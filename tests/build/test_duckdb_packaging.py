from __future__ import annotations

import importlib.metadata
import importlib.util
import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from expo_jbm329.build.notices.attribution import AttributionContext, attribute_entry
from expo_jbm329.build.notices.distributions import DistributionIndex, distribution_info_from_metadata
from expo_jbm329.build.notices.license_policy import resolve_distribution_license
from expo_jbm329.build.notices.models import BundledEntry, ComponentId, ComponentKind, EntryOrigin

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("system", ["Windows", "Linux"])
@pytest.mark.parametrize("onefile", [False, True])
def test_spec_collects_duckdb_imports_and_metadata_on_both_platforms(monkeypatch, system, onefile):
    metadata = MagicMock(side_effect=lambda name: [(f"{name}.dist-info/METADATA", f"{name}.dist-info")])
    hooks = SimpleNamespace(
        copy_metadata=metadata,
        collect_submodules=lambda name: [name],
        collect_data_files=lambda *args, **kwargs: [],
        collect_dynamic_libs=lambda *args, **kwargs: [],
    )
    for name in ("PyInstaller", "PyInstaller.utils"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", hooks)
    monkeypatch.setattr("expo_jbm329.build.mysql_binaries.collect_mysql_connector_openssl_binaries", list)
    monkeypatch.setattr("platform.system", lambda: system)
    if onefile:
        monkeypatch.setenv("EXPO_ONEFILE", "1")
    else:
        monkeypatch.delenv("EXPO_ONEFILE", raising=False)
    analysis = MagicMock(
        return_value=SimpleNamespace(pure=[], zipped_data=[], scripts=[], binaries=[], zipfiles=[], datas=[])
    )
    exe = MagicMock()
    collect = MagicMock()

    runpy.run_path(
        str(ROOT / "expo.spec"),
        init_globals={"Analysis": analysis, "PYZ": MagicMock(), "EXE": exe, "COLLECT": collect},
    )

    options = analysis.call_args.kwargs
    assert {"duckdb_engine", "duckdb", "_duckdb"} <= set(options["hiddenimports"])
    assert not {"duckdb_engine", "duckdb", "_duckdb"} & set(options["excludes"])
    for name in ("duckdb", "duckdb-engine"):
        metadata.assert_any_call(name)
        assert (f"{name}.dist-info/METADATA", f"{name}.dist-info") in options["datas"]
    assert exe.call_args.kwargs["strip"] is (system != "Windows")
    assert exe.call_args.kwargs["exclude_binaries"] is not onefile
    assert collect.called is not onefile


@pytest.mark.parametrize(
    ("distribution_name", "module_name", "origin"),
    [
        ("duckdb", "_duckdb", EntryOrigin.FILE),
        ("duckdb", "duckdb", EntryOrigin.ARCHIVE_MODULE),
        ("duckdb-engine", "duckdb_engine", EntryOrigin.ARCHIVE_MODULE),
    ],
)
def test_notice_pipeline_attributes_installed_duckdb_components(distribution_name, module_name, origin):
    distribution = distribution_info_from_metadata(importlib.metadata.distribution(distribution_name))
    spec = importlib.util.find_spec(module_name)
    assert spec is not None and spec.origin is not None
    source = Path(spec.origin)
    entry = BundledEntry(
        destination=source.name if origin is EntryOrigin.FILE else module_name,
        source=source,
        typecode="EXTENSION" if origin is EntryOrigin.FILE else "PYMODULE",
        origin=origin,
    )
    context = AttributionContext(
        executable_name="expo",
        first_party_distribution="expo_jbm329",
        first_party_roots=(ROOT / "src",),
        python_runtime_roots=(),
    )

    assert attribute_entry(entry, DistributionIndex([distribution]), context) == ComponentId(
        kind=ComponentKind.PYTHON_DISTRIBUTION, key=distribution_name
    )
    license_result = resolve_distribution_license(distribution, ())
    assert license_result.issues == ()
    assert license_result.license.name in {"MIT", "MIT License"}
    assert license_result.texts
    assert any("Permission is hereby granted" in text.text for text in license_result.texts)


def test_duckdb_metadata_contains_sqlalchemy_dialect_entry_point():
    entry_points = importlib.metadata.distribution("duckdb-engine").entry_points
    dialect = next(entry for entry in entry_points if entry.group == "sqlalchemy.dialects" and entry.name == "duckdb")
    assert dialect.value == "duckdb_engine:Dialect"
    assert dialect.load().__module__ == "duckdb_engine"

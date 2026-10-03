from __future__ import annotations

import json
from pathlib import Path

import pytest

from expo_jbm329.build.notices.attribution import (
    FIRST_PARTY_COMPONENT,
    MSVC_RUNTIME_COMPONENT,
    PYTHON_RUNTIME_COMPONENT,
    AttributionContext,
    attribute_entry,
)
from expo_jbm329.build.notices.dependency_scope import classify_dependency_scope
from expo_jbm329.build.notices.distributions import DistributionIndex, is_license_file, own_dist_info_dir
from expo_jbm329.build.notices.licenses import (
    LEGACY_LICENSE_TEXT_NAME,
    resolve_license,
    resolve_license_name,
    resolve_license_texts,
)
from expo_jbm329.build.notices.models import (
    BundledEntry,
    ComponentId,
    ComponentKind,
    DistributionInfo,
    EntryOrigin,
    IssueSeverity,
    LicenseSource,
    ResolvedLicense,
)
from expo_jbm329.build.notices.pyinstaller_toc import (
    TocFormatError,
    list_onedir_files,
    load_bundle_contents,
)
from expo_jbm329.build.notices.renderer import render_manifest, render_notices_text
from expo_jbm329.build.notices.service import NoticeConfig, analyze_onedir, write_notice_files


def _distribution(
    name: str,
    *,
    files: tuple[Path, ...] = (),
    license_files: tuple[Path, ...] = (),
    requirements: tuple[str, ...] = (),
    license_expression: str | None = "MIT",
    license_field: str | None = None,
    classifiers: tuple[str, ...] = (),
    dist_info_dir: Path | None = None,
) -> DistributionInfo:
    return DistributionInfo(
        name=name,
        version="1.0",
        license_expression=license_expression,
        license_field=license_field,
        classifiers=classifiers,
        requirements=requirements,
        homepage=f"https://example.invalid/{name}",
        files=files,
        license_files=license_files,
        dist_info_dir=dist_info_dir,
    )


def _write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _file_entry(destination: str, source: Path, typecode: str = "BINARY") -> BundledEntry:
    return BundledEntry(destination=destination, source=source, typecode=typecode, origin=EntryOrigin.FILE)


# ---------------------------------------------------------------- TOC reading


def test_load_bundle_contents_maps_destinations_and_skips_namespaces(tmp_path: Path) -> None:
    work_dir = tmp_path / "build"
    _write(
        work_dir / "PKG-00.toc",
        repr(("pkg", {}, [("pyi-contents-directory libs", "", "OPTION"), ("PYZ-00.pyz", "x", "PYZ")])),
    )
    _write(
        work_dir / "COLLECT-00.toc",
        repr((
            [
                ("expo.exe", "C:\\build\\expo.exe", "EXECUTABLE"),
                ("pkg\\mod.pyd", "C:\\site\\pkg\\mod.pyd", "EXTENSION"),
                ("lib.so", "real/lib.so.1", "SYMLINK"),
            ],
        )),
    )
    _write(
        work_dir / "PYZ-00.toc",
        repr(("PYZ-00.pyz", [("pkg", "C:\\site\\pkg\\__init__.py", "PYMODULE"), ("nspkg", "-", "PYMODULE")])),
    )

    contents = load_bundle_contents(work_dir)

    assert contents.expected_files == frozenset({"expo.exe", "libs/pkg/mod.pyd", "libs/lib.so"})
    assert [(entry.destination, entry.origin) for entry in contents.entries] == [
        ("expo.exe", EntryOrigin.FILE),
        ("libs/pkg/mod.pyd", EntryOrigin.FILE),
        ("pkg", EntryOrigin.ARCHIVE_MODULE),
    ]


def test_load_bundle_contents_rejects_invalid_toc(tmp_path: Path) -> None:
    _write(tmp_path / "COLLECT-00.toc", "not a literal (")

    with pytest.raises(TocFormatError):
        load_bundle_contents(tmp_path)


def test_list_onedir_files_returns_posix_relative_paths(tmp_path: Path) -> None:
    _write(tmp_path / "expo.exe")
    _write(tmp_path / "_internal" / "pkg" / "a.dll")

    assert list_onedir_files(tmp_path) == frozenset({"expo.exe", "_internal/pkg/a.dll"})


# ---------------------------------------------------------------- distributions and licenses


def test_is_license_file_detects_pep639_and_named_files(tmp_path: Path) -> None:
    dist_info = tmp_path / "pkg-1.0.dist-info"

    assert is_license_file(dist_info / "licenses" / "vendor" / "zlib.txt")
    assert is_license_file(dist_info / "LICENSE.txt")
    assert is_license_file(dist_info / "COPYING")
    assert not is_license_file(dist_info / "METADATA")
    assert not is_license_file(tmp_path / "pkg" / "LICENSE")


def test_distribution_index_finds_owner_by_file_and_name(tmp_path: Path) -> None:
    owned = tmp_path / "site" / "pkg" / "mod.py"
    index = DistributionIndex([_distribution("My_Pkg", files=(owned,))])

    found = index.find_by_file(owned)

    assert found is not None
    assert found.name == "My_Pkg"
    assert index.get("my-pkg") is found
    assert index.find_by_file(tmp_path / "other.py") is None


def test_resolve_license_name_prefers_expression_then_short_field_then_classifiers() -> None:
    classifiers = ("License :: OSI Approved :: BSD License",)

    assert resolve_license_name(_distribution("a", license_field="Other", classifiers=classifiers)) == "MIT"
    assert resolve_license_name(_distribution("a", license_expression=None, license_field="Apache 2.0")) == "Apache 2.0"
    assert (
        resolve_license_name(
            _distribution("a", license_expression=None, license_field="Long\ntext", classifiers=classifiers)
        )
        == "BSD License"
    )
    assert resolve_license_name(_distribution("a", license_expression=None)) is None


def test_resolve_license_texts_reads_files_or_falls_back_to_long_license_field(tmp_path: Path) -> None:
    license_file = _write(tmp_path / "pkg-1.0.dist-info" / "licenses" / "LICENSE", "  MIT text \n")

    texts = resolve_license_texts(_distribution("pkg", license_files=(license_file,)))
    fallback = resolve_license_texts(_distribution("pkg", license_field="Copyright\nFull text"))

    assert [(text.name, text.text) for text in texts] == [("licenses/LICENSE", "MIT text")]
    assert [(text.name, text.text) for text in fallback] == [(LEGACY_LICENSE_TEXT_NAME, "Copyright\nFull text")]
    assert resolve_license_texts(_distribution("pkg", license_field="MIT")) == ()


def test_resolve_license_texts_labels_vendored_files_and_merges_identical_texts(tmp_path: Path) -> None:
    own_dist_info = tmp_path / "pkg-1.0.dist-info"
    vendor_dir = tmp_path / "pkg" / "_vendor"
    vendored_a = _write(vendor_dir / "aaa-2.0.dist-info" / "LICENSE", "MIT text")
    vendored_b = _write(vendor_dir / "bbb-3.0.dist-info" / "LICENSE.txt", "Apache text")
    vendored_c = _write(vendor_dir / "ccc-4.0.dist-info" / "LICENSE", "MIT text")
    own = _write(own_dist_info / "licenses" / "LICENSE", "MIT text")
    distribution = _distribution(
        "pkg",
        license_files=(vendored_a, vendored_b, vendored_c, own),
        dist_info_dir=own_dist_info,
    )

    texts = resolve_license_texts(distribution)

    assert [(text.name, text.text) for text in texts] == [
        (
            "licenses/LICENSE\naaa-2.0.dist-info/LICENSE (vendored)\nccc-4.0.dist-info/LICENSE (vendored)",
            "MIT text",
        ),
        ("bbb-3.0.dist-info/LICENSE.txt (vendored)", "Apache text"),
    ]


def test_own_dist_info_dir_picks_shallowest_dist_info_with_metadata(tmp_path: Path) -> None:
    own = tmp_path / "pkg-1.0.dist-info"
    vendored = tmp_path / "pkg" / "_vendor" / "aaa-2.0.dist-info"

    assert own_dist_info_dir((vendored / "METADATA", own / "RECORD", own / "METADATA")) == own
    assert own_dist_info_dir((tmp_path / "pkg" / "mod.py",)) is None


def test_resolve_license_reports_where_the_identifier_comes_from() -> None:
    classifiers = ("License :: OSI Approved :: BSD License",)

    assert resolve_license(_distribution("a")) == ResolvedLicense("MIT", LicenseSource.METADATA)
    assert resolve_license(_distribution("a", license_expression=None, classifiers=classifiers)) == ResolvedLicense(
        "BSD License", LicenseSource.CLASSIFIER
    )
    assert resolve_license(_distribution("a", license_expression=None)) == ResolvedLicense(None, LicenseSource.UNKNOWN)


# ---------------------------------------------------------------- dependency scope


def test_classify_dependency_scope_separates_dev_only_dependencies() -> None:
    root = _distribution(
        "app",
        requirements=(
            "runtime-lib",
            'profiler; extra == "profiling"',
            'test-tool; extra == "dev"',
            'shared; extra == "dev"',
        ),
    )
    index = DistributionIndex([
        root,
        _distribution("runtime-lib", requirements=("shared",)),
        _distribution("profiler"),
        _distribution("test-tool", requirements=("tool-helper",)),
        _distribution("tool-helper"),
        _distribution("shared"),
    ])

    scope = classify_dependency_scope(root, index, allowed_extras=("profiling",), dev_extras=("dev",))

    assert scope.allowed == frozenset({"runtime-lib", "profiler", "shared"})
    assert scope.dev_only == frozenset({"test-tool", "tool-helper"})


def test_classify_dependency_scope_follows_extras_requested_after_first_visit() -> None:
    root = _distribution("app", requirements=("lib", "other"))
    index = DistributionIndex([
        root,
        _distribution("lib", requirements=('optional-dep; extra == "fast"',)),
        _distribution("other", requirements=("lib[fast]",)),
        _distribution("optional-dep"),
    ])

    scope = classify_dependency_scope(root, index, allowed_extras=(), dev_extras=())

    assert "optional-dep" in scope.allowed


# ---------------------------------------------------------------- attribution


@pytest.fixture
def attribution_context(tmp_path: Path) -> AttributionContext:
    return AttributionContext(
        executable_name="expo.exe",
        first_party_distribution="expo_jbm329",
        first_party_roots=(tmp_path / "project" / "src",),
        python_runtime_roots=(tmp_path / "python",),
    )


def test_attribute_entry_rules(tmp_path: Path, attribution_context: AttributionContext) -> None:
    site = tmp_path / "python" / "Lib" / "site-packages"
    record_file = site / "pkg" / "mod.pyd"
    unrecorded_site_file = site / "loose.py"
    index = DistributionIndex([
        _distribution("pkg", files=(record_file, site / "pkg" / "VCRUNTIME140.dll")),
        _distribution("pyinstaller"),
        _distribution("expo_jbm329", files=(site / "expo_jbm329-1.0.dist-info" / "METADATA",)),
    ])

    def attribute(destination: str, source: Path) -> ComponentId | None:
        return attribute_entry(_file_entry(destination, source), index, attribution_context)

    assert attribute("_internal/pkg/VCRUNTIME140.dll", site / "pkg" / "VCRUNTIME140.dll") == MSVC_RUNTIME_COMPONENT
    assert attribute("_internal/base_library.zip", tmp_path / "build" / "base_library.zip") == PYTHON_RUNTIME_COMPONENT
    assert attribute("expo.exe", tmp_path / "build" / "expo.exe") == ComponentId(
        ComponentKind.PYTHON_DISTRIBUTION, "pyinstaller"
    )
    assert attribute("_internal/pkg/mod.pyd", record_file) == ComponentId(ComponentKind.PYTHON_DISTRIBUTION, "pkg")
    assert attribute("_internal/x/METADATA", site / "expo_jbm329-1.0.dist-info" / "METADATA") == FIRST_PARTY_COMPONENT
    assert attribute("_internal/theme/a.json", tmp_path / "project" / "src" / "a.json") == FIRST_PARTY_COMPONENT
    assert attribute("_internal/python313.dll", tmp_path / "python" / "python313.dll") == PYTHON_RUNTIME_COMPONENT
    assert attribute("_internal/loose.py", unrecorded_site_file) is None
    assert attribute("_internal/unknown.dll", tmp_path / "elsewhere" / "unknown.dll") is None


def test_executable_is_unattributed_without_bootloader_distribution(attribution_context: AttributionContext) -> None:
    entry = _file_entry("expo.exe", Path("build/expo.exe"), typecode="EXECUTABLE")

    assert attribute_entry(entry, DistributionIndex([]), attribution_context) is None


# ---------------------------------------------------------------- end-to-end analysis


def _build_fixture(tmp_path: Path) -> tuple[NoticeConfig, list[DistributionInfo]]:
    site = tmp_path / "venv" / "site-packages"
    runtime_file = _write(site / "runtime_lib" / "core.pyd")
    runtime_license = _write(site / "runtime_lib-1.0.dist-info" / "LICENSE", "Runtime license")
    dev_file = _write(site / "dev_tool" / "tool.pyd")
    python_root = tmp_path / "python"
    _write(python_root / "LICENSE.txt", "PSF license")
    python_dll = _write(python_root / "python313.dll")

    work_dir = tmp_path / "build"
    collect_rows = [
        ("expo.exe", str(tmp_path / "build" / "expo.exe"), "EXECUTABLE"),
        ("runtime_lib\\core.pyd", str(runtime_file), "EXTENSION"),
        ("dev_tool\\tool.pyd", str(dev_file), "EXTENSION"),
        ("python313.dll", str(python_dll), "BINARY"),
        ("mystery.dll", str(tmp_path / "nowhere" / "mystery.dll"), "BINARY"),
    ]
    _write(work_dir / "COLLECT-00.toc", repr((collect_rows,)))

    dist_dir = tmp_path / "dist"
    for relative in ("expo.exe", "_internal/runtime_lib/core.pyd", "_internal/dev_tool/tool.pyd"):
        _write(dist_dir / relative)
    _write(dist_dir / "_internal" / "python313.dll")
    _write(dist_dir / "_internal" / "mystery.dll")
    _write(dist_dir / "_internal" / "stray.txt")

    installed = [
        _distribution("app", requirements=("runtime-lib", 'dev-tool; extra == "dev"')),
        _distribution("runtime-lib", files=(runtime_file,), license_files=(runtime_license,)),
        _distribution("dev-tool", files=(dev_file,), license_expression=None),
        _distribution("pyinstaller", license_expression="GPL-2.0-or-later WITH Bootloader-exception"),
    ]
    config = NoticeConfig(
        dist_dir=dist_dir,
        work_dir=work_dir,
        application_name="Expo Studio",
        application_version="1.2.3",
        root_distribution="app",
        attribution=AttributionContext(
            executable_name="expo.exe",
            first_party_distribution="app",
            first_party_roots=(tmp_path / "src",),
            python_runtime_roots=(python_root,),
        ),
        allowed_extras=(),
        dev_extras=("dev",),
        case_sensitive_paths=True,
    )
    return config, installed


def test_analyze_onedir_reports_components_and_issues(tmp_path: Path) -> None:
    config, installed = _build_fixture(tmp_path)

    report = analyze_onedir(config, installed)

    assert [component.name for component in report.components] == ["dev-tool", "pyinstaller", "Python", "runtime-lib"]
    error_messages = [issue.message for issue in report.errors]
    assert any("Development-only distribution is bundled: dev-tool" in message for message in error_messages)
    assert any("could not be attributed" in message and "mystery.dll" in message for message in error_messages)
    assert any("not described by the PyInstaller build: _internal/stray.txt" in message for message in error_messages)
    assert report.has_errors
    assert any(
        issue.component == "dev-tool" and issue.message.startswith("No license identifier or license text found")
        for issue in report.errors
    )
    assert any(
        issue.component == "pyinstaller" and issue.message.startswith("No license text found")
        for issue in report.errors
    )
    assert not any(issue.message.startswith("No license") for issue in report.warnings)
    python_component = next(component for component in report.components if component.name == "Python")
    assert python_component.license_texts[0].text == "PSF license"


def test_analyze_onedir_reports_missing_onedir_files(tmp_path: Path) -> None:
    config, installed = _build_fixture(tmp_path)
    (config.dist_dir / "_internal" / "python313.dll").unlink()

    report = analyze_onedir(config, installed)

    assert any(
        issue.severity is IssueSeverity.ERROR and "missing from the onedir output" in issue.message
        for issue in report.issues
    )


def test_write_notice_files_is_deterministic(tmp_path: Path) -> None:
    config, installed = _build_fixture(tmp_path)
    report = analyze_onedir(config, installed)

    first = write_notice_files(report, config, tmp_path / "out1")
    second = write_notice_files(analyze_onedir(config, installed), config, tmp_path / "out2")

    notices = first.notices.read_text(encoding="utf-8")
    assert notices == second.notices.read_text(encoding="utf-8")
    assert notices.startswith("THIRD-PARTY SOFTWARE NOTICES AND INFORMATION")
    assert "Expo Studio 1.2.3" in notices
    assert "Runtime license" in notices
    manifest = json.loads(first.manifest.read_text(encoding="utf-8"))
    assert manifest["application"] == {"name": "Expo Studio", "version": "1.2.3"}
    runtime_lib = next(component for component in manifest["components"] if component["key"] == "runtime-lib")
    assert runtime_lib["license_source"] == "metadata"
    assert {component["key"] for component in manifest["components"]} == {
        "dev-tool",
        "pyinstaller",
        "python",
        "runtime-lib",
    }
    assert render_notices_text(report, "A", "1") == render_notices_text(report, "A", "1")
    assert render_manifest(report, "A", "1") == render_manifest(report, "A", "1")

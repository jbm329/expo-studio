"""Tests for documentation publication policy."""

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from runpy import run_path
from unittest.mock import MagicMock, Mock
from urllib.error import HTTPError, URLError

import pytest

HELPER_PATH = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "docs_publication.py"
HELPER = run_path(str(HELPER_PATH))
parse_stable_tag = HELPER["parse_stable_tag"]
is_stable_release = HELPER["is_stable_release"]
latest_stable_tag = HELPER["latest_stable_tag"]
require_latest_stable_tag = HELPER["require_latest_stable_tag"]
validate_commit_sha = HELPER["validate_commit_sha"]
require_commit = HELPER["require_commit"]
require_ancestor = HELPER["require_ancestor"]
require_remote_branch_contains_commit = HELPER["require_remote_branch_contains_commit"]
require_correction_file = HELPER["require_correction_file"]
require_correction_changes = HELPER["require_correction_changes"]
resolve_stable_tag_commit = HELPER["resolve_stable_tag_commit"]
require_correction_source = HELPER["require_correction_source"]
require_documentation_setup = HELPER["require_documentation_setup"]
require_release_source = HELPER["require_release_source"]
require_bootstrap_content = HELPER["require_bootstrap_content"]
require_bootstrap_configuration = HELPER["require_bootstrap_configuration"]
require_bootstrap_source = HELPER["require_bootstrap_source"]
require_publication_progress = HELPER["require_publication_progress"]
parse_publication_manifest = HELPER["parse_publication_manifest"]
require_manifest_progress = HELPER["require_manifest_progress"]
read_publication_manifest = HELPER["read_publication_manifest"]
fetch_published_manifest = HELPER["fetch_published_manifest"]
write_publication_manifest = HELPER["write_publication_manifest"]
parse_github_releases = HELPER["parse_github_releases"]
fetch_github_releases = HELPER["fetch_github_releases"]
fetch_pages_deployments = HELPER["fetch_pages_deployments"]
fetch_deployment_statuses = HELPER["fetch_deployment_statuses"]
latest_deployment_status = HELPER["latest_deployment_status"]
fetch_current_pages_deployment = HELPER["fetch_current_pages_deployment"]
require_deployment_run = HELPER["require_deployment_run"]
require_manual_publication_run = HELPER["require_manual_publication_run"]
require_publication_job = HELPER["require_publication_job"]
fetch_manual_publication_metadata = HELPER["fetch_manual_publication_metadata"]
refresh_publication_refs = HELPER["refresh_publication_refs"]
prepare_publication = HELPER["prepare_publication"]
main = HELPER["main"]


@pytest.fixture
def publication_site(tmp_path: Path, publication_manifest: dict[str, object]) -> tuple[Path, Path]:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<!doctype html><title>Manual</title>", encoding="utf-8")
    write_publication_manifest(site / "publication.json", publication_manifest)
    proposed = tmp_path / "proposed.json"
    write_publication_manifest(proposed, publication_manifest)
    return site, proposed


def test_verify_site_command_accepts_matching_artifact(publication_site: tuple[Path, Path]) -> None:
    site, proposed = publication_site
    before = {path.name: path.read_bytes() for path in site.iterdir()}

    main(["verify-site", "--site", str(site), "--proposed", str(proposed)])

    assert {path.name: path.read_bytes() for path in site.iterdir()} == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mode", "correction"),
        ("baseline_tag", "v1.5.0"),
        ("source_sha", "a" * 40),
        ("run_id", "987654321"),
    ],
)
def test_verify_site_command_rejects_mismatched_metadata(
    publication_site: tuple[Path, Path], publication_manifest: dict[str, object], field: str, value: str
) -> None:
    site, proposed = publication_site
    write_publication_manifest(site / "publication.json", {**publication_manifest, field: value})

    with pytest.raises(ValueError, match="does not match"):
        main(["verify-site", "--site", str(site), "--proposed", str(proposed)])


@pytest.mark.parametrize("name", ["index.html", "publication.json"])
@pytest.mark.parametrize("replacement", ["missing", "directory"])
def test_verify_site_command_requires_regular_output_files(
    publication_site: tuple[Path, Path], name: str, replacement: str
) -> None:
    site, proposed = publication_site
    (site / name).unlink()
    if replacement == "directory":
        (site / name).mkdir()

    with pytest.raises(ValueError, match="regular"):
        main(["verify-site", "--site", str(site), "--proposed", str(proposed)])


@pytest.mark.parametrize("failure", ["empty-page", "malformed-metadata", "missing-site", "missing-proposal"])
def test_verify_site_command_rejects_incomplete_artifact(publication_site: tuple[Path, Path], failure: str) -> None:
    site, proposed = publication_site
    if failure == "empty-page":
        (site / "index.html").write_bytes(b"")
    elif failure == "malformed-metadata":
        (site / "publication.json").write_text("{}", encoding="utf-8")
    elif failure == "missing-site":
        site = site / "missing"
    else:
        proposed.unlink()

    with pytest.raises(FileNotFoundError if failure == "missing-proposal" else ValueError):
        main(["verify-site", "--site", str(site), "--proposed", str(proposed)])


@pytest.mark.parametrize("name", ["site", "index.html", "publication.json"])
def test_verify_site_command_rejects_symlink_outputs(
    monkeypatch: pytest.MonkeyPatch, publication_site: tuple[Path, Path], name: str
) -> None:
    site, proposed = publication_site
    target = site if name == "site" else site / name
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == target or original(path))

    with pytest.raises(ValueError, match="regular"):
        main(["verify-site", "--site", str(site), "--proposed", str(proposed)])


def test_prepare_command_writes_validated_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, publication_manifest: dict[str, object]
) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "validated.json"
    write_publication_manifest(request_path, publication_manifest)
    prepare = Mock(return_value=publication_manifest)
    monkeypatch.setitem(main.__globals__, "prepare_publication", prepare)

    main([
        "prepare",
        "--repository",
        str(tmp_path),
        "--repository-slug",
        "jbm329/expo-studio",
        "--request",
        str(request_path),
        "--output",
        str(output_path),
    ])

    prepare.assert_called_once_with(tmp_path, "jbm329/expo-studio", publication_manifest)
    assert read_publication_manifest(output_path) == publication_manifest


def test_prepare_command_does_not_write_output_after_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, publication_manifest: dict[str, object]
) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "validated.json"
    write_publication_manifest(request_path, publication_manifest)
    monkeypatch.setitem(main.__globals__, "prepare_publication", Mock(side_effect=ValueError("Source rejected")))

    with pytest.raises(ValueError, match="Source rejected"):
        main([
            "prepare",
            "--repository",
            str(tmp_path),
            "--repository-slug",
            "jbm329/expo-studio",
            "--request",
            str(request_path),
            "--output",
            str(output_path),
        ])

    assert not output_path.exists()


@pytest.mark.parametrize(
    "arguments",
    [[], ["deploy"], ["prepare"], ["check-progress"], ["fetch-published"], ["inspect-published"], ["verify-site"]],
)
def test_prepare_command_requires_explicit_arguments(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(arguments)

    assert error.value.code == 2


def test_publication_script_help_runs_without_side_effects() -> None:
    result = subprocess.run(
        [sys.executable, str(HELPER_PATH), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "{prepare,check-progress,fetch-published,inspect-published,verify-site}" in result.stdout
    assert "without building or deploying" in result.stdout


@pytest.mark.parametrize("has_publication", [False, True])
def test_inspect_published_command_reports_state_without_authorizing_deployment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    publication_manifest: dict[str, object],
    correction_history: tuple[Path, str, str],
    has_publication: bool,
) -> None:
    repository, baseline, correction = correction_history
    published = {**publication_manifest, "source_sha": baseline} if has_publication else None
    proposed = {
        **publication_manifest,
        "source_sha": correction,
        "mode": "release" if has_publication else "bootstrap",
    }
    proposed_path = tmp_path / "proposed.json"
    write_publication_manifest(proposed_path, proposed)
    inspect = Mock(return_value=published)
    monkeypatch.setitem(main.__globals__, "fetch_manual_publication_metadata", inspect)
    output = tmp_path / "inspection.json"

    main([
        "inspect-published",
        "--confirm-initial-bootstrap",
        "--repository-slug",
        "jbm329/expo-studio",
        "--repository",
        str(repository),
        "--proposed",
        str(proposed_path),
        "--output",
        str(output),
    ])

    inspect.assert_called_once_with("jbm329/expo-studio")
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "state": "metadata-cross-checked" if has_publication else "no-deployment-records",
        "publication": published,
        "proposed": proposed,
        "progress_check": "passed" if has_publication else "no-published-source",
        "deployment_authorized": False,
        "initial_bootstrap_confirmed": not has_publication,
    }


@pytest.mark.parametrize("mode", ["correction", "release"])
def test_inspect_published_command_requires_bootstrap_when_history_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    publication_manifest: dict[str, object],
    mode: str,
) -> None:
    inspect = Mock(return_value=None)
    monkeypatch.setitem(main.__globals__, "fetch_manual_publication_metadata", inspect)
    progress = Mock()
    monkeypatch.setitem(main.__globals__, "require_manifest_progress", progress)
    proposed = tmp_path / "proposed.json"
    write_publication_manifest(proposed, {**publication_manifest, "mode": mode})
    output = tmp_path / "inspection.json"

    with pytest.raises(ValueError, match="explicitly validated bootstrap"):
        main([
            "inspect-published",
            "--confirm-initial-bootstrap",
            "--repository-slug",
            "jbm329/expo-studio",
            "--repository",
            str(tmp_path),
            "--proposed",
            str(proposed),
            "--output",
            str(output),
        ])

    inspect.assert_called_once_with("jbm329/expo-studio")
    progress.assert_not_called()
    assert not output.exists()


def test_inspect_published_command_requires_explicit_initial_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, publication_manifest: dict[str, object]
) -> None:
    monkeypatch.setitem(main.__globals__, "fetch_manual_publication_metadata", Mock(return_value=None))
    proposed = tmp_path / "proposed.json"
    write_publication_manifest(proposed, {**publication_manifest, "mode": "bootstrap"})
    output = tmp_path / "inspection.json"

    with pytest.raises(ValueError, match="explicit operator confirmation"):
        main([
            "inspect-published",
            "--repository-slug",
            "jbm329/expo-studio",
            "--repository",
            str(tmp_path),
            "--proposed",
            str(proposed),
            "--output",
            str(output),
        ])

    assert not output.exists()


def test_inspect_published_command_does_not_write_report_after_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, publication_manifest: dict[str, object]
) -> None:
    monkeypatch.setitem(
        main.__globals__, "fetch_manual_publication_metadata", Mock(side_effect=ValueError("Inspection failed"))
    )
    output = tmp_path / "inspection.json"
    proposed_path = tmp_path / "proposed.json"
    write_publication_manifest(proposed_path, publication_manifest)

    with pytest.raises(ValueError, match="Inspection failed"):
        main([
            "inspect-published",
            "--confirm-initial-bootstrap",
            "--repository-slug",
            "jbm329/expo-studio",
            "--repository",
            str(tmp_path),
            "--proposed",
            str(proposed_path),
            "--output",
            str(output),
        ])

    assert not output.exists()


def test_inspect_published_command_rejects_source_regression(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    publication_manifest: dict[str, object],
    correction_history: tuple[Path, str, str],
) -> None:
    repository, baseline, correction = correction_history
    monkeypatch.setitem(
        main.__globals__,
        "fetch_manual_publication_metadata",
        Mock(return_value={**publication_manifest, "source_sha": correction}),
    )
    proposed_path = tmp_path / "proposed.json"
    write_publication_manifest(proposed_path, {**publication_manifest, "source_sha": baseline})
    output = tmp_path / "inspection.json"

    with pytest.raises(ValueError, match="ancestor"):
        main([
            "inspect-published",
            "--confirm-initial-bootstrap",
            "--repository-slug",
            "jbm329/expo-studio",
            "--repository",
            str(repository),
            "--proposed",
            str(proposed_path),
            "--output",
            str(output),
        ])

    assert not output.exists()


@pytest.mark.parametrize("failure", ["missing", "malformed"])
def test_inspect_published_command_requires_proposed_manifest_before_fetch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    inspect = Mock()
    monkeypatch.setitem(main.__globals__, "fetch_manual_publication_metadata", inspect)
    proposed = tmp_path / "proposed.json"
    if failure == "malformed":
        proposed.write_text("{}", encoding="utf-8")
    output = tmp_path / "inspection.json"

    with pytest.raises(FileNotFoundError if failure == "missing" else ValueError):
        main([
            "inspect-published",
            "--repository-slug",
            "jbm329/expo-studio",
            "--repository",
            str(tmp_path),
            "--proposed",
            str(proposed),
            "--output",
            str(output),
        ])

    inspect.assert_not_called()
    assert not output.exists()


def test_fetch_published_manifest_reads_fixed_site(
    monkeypatch: pytest.MonkeyPatch, publication_manifest: dict[str, object]
) -> None:
    response = MagicMock()
    response.status = 200
    response.read.return_value = json.dumps(publication_manifest).encode("utf-8")
    response.geturl.side_effect = lambda: opener.call_args.args[0].full_url
    opener = MagicMock()
    opener.return_value.__enter__.return_value = response
    monkeypatch.setitem(fetch_published_manifest.__globals__, "urlopen", opener)

    assert fetch_published_manifest() == publication_manifest
    first_url = opener.call_args.args[0].full_url
    assert fetch_published_manifest() == publication_manifest
    request = opener.call_args.args[0]
    assert request.full_url.startswith("https://jbm329.github.io/expo-studio/publication.json?check=")
    assert request.full_url != first_url
    assert request.get_header("Cache-control") == "no-cache"
    assert request.get_header("Accept") == "application/json"
    assert opener.call_args.kwargs == {"timeout": 30}
    response.read.assert_called_with(65_537)


@pytest.mark.parametrize(
    ("content", "error"),
    [(b"{}", ValueError), (b"not json", ValueError), (b"\xff", UnicodeDecodeError), (b"x" * 65_537, ValueError)],
    ids=["invalid-schema", "invalid-json", "invalid-utf8", "oversized"],
)
def test_fetch_published_manifest_rejects_bad_content(
    monkeypatch: pytest.MonkeyPatch, content: bytes, error: type[Exception]
) -> None:
    response = MagicMock()
    response.status = 200
    response.read.return_value = content
    opener = MagicMock()
    response.geturl.side_effect = lambda: opener.call_args.args[0].full_url
    opener.return_value.__enter__.return_value = response
    monkeypatch.setitem(fetch_published_manifest.__globals__, "urlopen", opener)

    with pytest.raises(error):
        fetch_published_manifest()


@pytest.mark.parametrize("failure", ["status", "redirect"])
def test_fetch_published_manifest_rejects_unexpected_response(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    response = MagicMock()
    opener = MagicMock()
    response.status = 204 if failure == "status" else 200
    response.geturl.side_effect = lambda: (
        "https://example.com/publication.json" if failure == "redirect" else opener.call_args.args[0].full_url
    )
    opener.return_value.__enter__.return_value = response
    monkeypatch.setitem(fetch_published_manifest.__globals__, "urlopen", opener)

    with pytest.raises(ValueError, match="without redirection"):
        fetch_published_manifest()

    response.read.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [HTTPError("https://jbm329.github.io", 404, "Not Found", None, None), URLError("unavailable"), TimeoutError()],
)
def test_fetch_published_manifest_propagates_request_failures(monkeypatch: pytest.MonkeyPatch, error: OSError) -> None:
    monkeypatch.setitem(fetch_published_manifest.__globals__, "urlopen", Mock(side_effect=error))

    with pytest.raises(type(error)):
        fetch_published_manifest()


def test_fetch_published_command_writes_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, publication_manifest: dict[str, object]
) -> None:
    fetch = Mock(return_value=publication_manifest)
    monkeypatch.setitem(main.__globals__, "fetch_published_manifest", fetch)
    output = tmp_path / "published.json"

    main(["fetch-published", "--output", str(output)])

    fetch.assert_called_once_with()
    assert read_publication_manifest(output) == publication_manifest


def test_fetch_published_command_does_not_write_after_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setitem(main.__globals__, "fetch_published_manifest", Mock(side_effect=URLError("unavailable")))
    output = tmp_path / "published.json"

    with pytest.raises(URLError):
        main(["fetch-published", "--output", str(output)])

    assert not output.exists()


@pytest.mark.parametrize("direction", ["advance", "repeat", "regress"])
def test_check_progress_command_checks_real_history(
    tmp_path: Path,
    correction_history: tuple[Path, str, str],
    publication_manifest: dict[str, object],
    direction: str,
) -> None:
    repository, baseline, correction = correction_history
    published_source = correction if direction in ("repeat", "regress") else baseline
    proposed_source = baseline if direction == "regress" else correction
    published_path = tmp_path / "published.json"
    proposed_path = tmp_path / "proposed.json"
    write_publication_manifest(published_path, {**publication_manifest, "source_sha": published_source})
    write_publication_manifest(proposed_path, {**publication_manifest, "source_sha": proposed_source})
    arguments = [
        "check-progress",
        "--repository",
        str(repository),
        "--published",
        str(published_path),
        "--proposed",
        str(proposed_path),
    ]

    if direction == "regress":
        with pytest.raises(ValueError, match="ancestor"):
            main(arguments)
    else:
        main(arguments)


@pytest.mark.parametrize("invalid_input", ["published", "proposed"])
@pytest.mark.parametrize("failure", ["missing", "malformed"])
def test_check_progress_command_requires_valid_manifests(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    publication_manifest: dict[str, object],
    invalid_input: str,
    failure: str,
) -> None:
    paths = {"published": tmp_path / "published.json", "proposed": tmp_path / "proposed.json"}
    for path in paths.values():
        write_publication_manifest(path, publication_manifest)
    if failure == "missing":
        paths[invalid_input].unlink()
    else:
        paths[invalid_input].write_text("{}", encoding="utf-8")
    check = Mock()
    monkeypatch.setitem(main.__globals__, "require_manifest_progress", check)

    with pytest.raises(FileNotFoundError if failure == "missing" else ValueError):
        main([
            "check-progress",
            "--repository",
            str(tmp_path),
            "--published",
            str(paths["published"]),
            "--proposed",
            str(paths["proposed"]),
        ])

    check.assert_not_called()


@pytest.mark.parametrize("mode", ["bootstrap", "release", "correction"])
def test_prepare_publication_connects_source_checks(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    publication_manifest: dict[str, object],
    mode: str,
) -> None:
    if mode == "bootstrap":
        repository, _, source = request.getfixturevalue("bootstrap_source_history")
        tag = "v1.3.0"
    else:
        repository, baseline, correction = request.getfixturevalue("correction_history")
        source = baseline if mode == "release" else correction
        tag = "v1.4.0"
    publication = {**publication_manifest, "mode": mode, "baseline_tag": tag, "source_sha": source.upper()}
    refresh = Mock()
    fetch = Mock(return_value=[{"tag_name": tag, "draft": False, "prerelease": False}])
    monkeypatch.setitem(prepare_publication.__globals__, "refresh_publication_refs", refresh)
    monkeypatch.setitem(prepare_publication.__globals__, "fetch_github_releases", fetch)

    manifest = prepare_publication(repository, "jbm329/expo-studio", publication)

    assert manifest == {**publication, "source_sha": source}
    refresh.assert_called_once_with(repository)
    fetch.assert_called_once_with("jbm329/expo-studio")


def test_prepare_publication_rejects_bad_request_before_fetching(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, publication_manifest: dict[str, object]
) -> None:
    refresh = Mock()
    monkeypatch.setitem(prepare_publication.__globals__, "refresh_publication_refs", refresh)
    publication_manifest["mode"] = "preview"

    with pytest.raises(ValueError, match="Unsupported publication manifest mode"):
        prepare_publication(tmp_path, "jbm329/expo-studio", publication_manifest)

    refresh.assert_not_called()


def test_prepare_publication_stops_after_refresh_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, publication_manifest: dict[str, object]
) -> None:
    refresh = Mock(side_effect=subprocess.CalledProcessError(1, ["git", "fetch"]))
    fetch = Mock()
    monkeypatch.setitem(prepare_publication.__globals__, "refresh_publication_refs", refresh)
    monkeypatch.setitem(prepare_publication.__globals__, "fetch_github_releases", fetch)

    with pytest.raises(subprocess.CalledProcessError):
        prepare_publication(tmp_path, "jbm329/expo-studio", publication_manifest)

    fetch.assert_not_called()


def test_prepare_publication_propagates_source_rejection(
    monkeypatch: pytest.MonkeyPatch,
    correction_history: tuple[Path, str, str],
    publication_manifest: dict[str, object],
) -> None:
    repository, _, correction = correction_history
    request = {**publication_manifest, "mode": "release", "source_sha": correction}
    monkeypatch.setitem(prepare_publication.__globals__, "refresh_publication_refs", Mock())
    monkeypatch.setitem(
        prepare_publication.__globals__,
        "fetch_github_releases",
        Mock(return_value=[{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]),
    )

    with pytest.raises(ValueError, match="does not match release"):
        prepare_publication(repository, "jbm329/expo-studio", request)


def test_refresh_publication_refs_updates_branches_and_tags(git_repository: Path) -> None:
    remote = git_repository / "remote.git"
    run_git(git_repository, "init", "--bare", "--quiet", str(remote))
    run_git(git_repository, "remote", "add", "origin", str(remote))
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    run_git(git_repository, "push", "--quiet", "origin", f"{baseline}:refs/heads/main")
    run_git(git_repository, "push", "--quiet", "origin", f"{baseline}:refs/tags/v1.4.0")
    run_git(git_repository, "update-ref", "refs/remotes/origin/deleted-branch", baseline)
    tip = create_test_commit(git_repository)
    run_git(git_repository, "push", "--quiet", "origin", f"{tip}:refs/heads/docs/1.4.0")
    head_before = run_git(git_repository, "rev-parse", "HEAD")

    refresh_publication_refs(git_repository)

    assert run_git(git_repository, "rev-parse", "refs/remotes/origin/main") == baseline
    assert run_git(git_repository, "rev-parse", "refs/remotes/origin/docs/1.4.0") == tip
    assert resolve_stable_tag_commit(git_repository, "v1.4.0") == baseline
    assert run_git(git_repository, "rev-parse", "HEAD") == head_before
    with pytest.raises(subprocess.CalledProcessError):
        run_git(git_repository, "show-ref", "--verify", "refs/remotes/origin/deleted-branch")


@pytest.mark.parametrize("response", ["true\n", "", "unexpected\n"])
def test_refresh_publication_refs_requires_full_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, response: str
) -> None:
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=response))
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(ValueError, match="full-history checkout"):
        refresh_publication_refs(tmp_path)

    assert runner.call_count == 1


def test_refresh_publication_refs_surfaces_fetch_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = Mock(
        side_effect=[
            subprocess.CompletedProcess([], 0, stdout="false\n"),
            subprocess.CalledProcessError(1, ["git", "fetch"]),
        ]
    )
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(subprocess.CalledProcessError):
        refresh_publication_refs(tmp_path)

    assert runner.call_count == 2


def test_refresh_publication_refs_surfaces_repository_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = Mock(side_effect=subprocess.CalledProcessError(128, ["git", "rev-parse"]))
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(subprocess.CalledProcessError):
        refresh_publication_refs(tmp_path)

    assert runner.call_count == 1


@pytest.fixture
def manual_metadata_checks(
    monkeypatch: pytest.MonkeyPatch,
    publication_manifest: dict[str, object],
    deployment_success: dict[str, object],
) -> Mock:
    checks = Mock()
    checks.current.return_value = ({"id": 1, "sha": "a" * 40}, deployment_success)
    checks.manifest.return_value = {**publication_manifest, "mode": "bootstrap"}
    checks.run.return_value = 2
    dependencies = {
        "fetch_current_pages_deployment": checks.current,
        "fetch_published_manifest": checks.manifest,
        "require_deployment_run": checks.association,
        "require_manual_publication_run": checks.run,
        "require_publication_job": checks.job,
    }
    for name, dependency in dependencies.items():
        monkeypatch.setitem(fetch_manual_publication_metadata.__globals__, name, dependency)
    return checks


def test_fetch_manual_publication_metadata_connects_checks(manual_metadata_checks: Mock) -> None:
    checks = manual_metadata_checks
    slug = "jbm329/expo-studio"
    deployment, status = checks.current.return_value
    manifest = checks.manifest.return_value

    assert fetch_manual_publication_metadata(slug) == manifest

    assert [item[0] for item in checks.mock_calls] == ["current", "manifest", "association", "run", "job", "current"]
    checks.association.assert_called_once_with(slug, status, manifest)
    checks.run.assert_called_once_with(slug, deployment, manifest)
    checks.job.assert_called_once_with(slug, status, manifest, 2)


def test_fetch_manual_publication_metadata_distinguishes_no_history(manual_metadata_checks: Mock) -> None:
    manual_metadata_checks.current.return_value = None

    assert fetch_manual_publication_metadata("jbm329/expo-studio") is None

    assert [item[0] for item in manual_metadata_checks.mock_calls] == ["current"]


@pytest.mark.parametrize("failure_point", ["current", "manifest", "association", "run", "job"])
def test_fetch_manual_publication_metadata_stops_on_failure(manual_metadata_checks: Mock, failure_point: str) -> None:
    sequence = ["current", "manifest", "association", "run", "job"]
    getattr(manual_metadata_checks, failure_point).side_effect = ValueError("Verification failed")

    with pytest.raises(ValueError, match="Verification failed"):
        fetch_manual_publication_metadata("jbm329/expo-studio")

    assert [item[0] for item in manual_metadata_checks.mock_calls] == sequence[: sequence.index(failure_point) + 1]


@pytest.mark.parametrize("change", ["deployment", "status", "missing", "api-failure"])
def test_fetch_manual_publication_metadata_rejects_changes_during_inspection(
    manual_metadata_checks: Mock, change: str
) -> None:
    deployment, status = manual_metadata_checks.current.return_value
    changed = {
        "deployment": ({**deployment, "id": 2}, status),
        "status": (deployment, {**status, "id": 2}),
        "missing": None,
        "api-failure": subprocess.CalledProcessError(1, ["gh", "api"]),
    }
    manual_metadata_checks.current.side_effect = [(deployment, status), changed[change]]

    with pytest.raises(subprocess.CalledProcessError if change == "api-failure" else ValueError):
        fetch_manual_publication_metadata("jbm329/expo-studio")

    manual_metadata_checks.job.assert_called_once()
    assert manual_metadata_checks.current.call_count == 2


@pytest.fixture
def publication_job() -> dict[str, object]:
    return {
        "id": 987,
        "name": "Deploy documentation",
        "run_id": 123456789,
        "run_attempt": 2,
        "status": "completed",
        "conclusion": "success",
        "started_at": "2026-11-04T12:00:00Z",
        "completed_at": "2026-11-04T12:02:00Z",
    }


@pytest.fixture
def deployment_success() -> dict[str, object]:
    return {
        "id": 1,
        "state": "success",
        "log_url": "https://github.com/jbm329/expo-studio/actions/runs/123456789",
        "created_at": "2026-11-04T12:01:00Z",
    }


@pytest.mark.parametrize("suffix", ["", "/job/987"])
@pytest.mark.parametrize("timestamp", ["12:00:00", "12:01:00", "12:02:00"])
def test_require_publication_job_checks_attempt_and_execution_window(
    monkeypatch: pytest.MonkeyPatch,
    publication_manifest: dict[str, object],
    publication_job: dict[str, object],
    deployment_success: dict[str, object],
    suffix: str,
    timestamp: str,
) -> None:
    pages = [{"jobs": [{"name": "prepare"}]}, {"jobs": [publication_job]}]
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(pages)))
    monkeypatch.setattr(subprocess, "run", runner)
    status = {
        **deployment_success,
        "log_url": str(deployment_success["log_url"]) + suffix,
        "created_at": f"2026-11-04T{timestamp}Z",
    }

    require_publication_job("jbm329/expo-studio", status, publication_manifest, 2)

    runner.assert_called_once_with(
        [
            "gh",
            "api",
            "--method",
            "GET",
            "--paginate",
            "--slurp",
            "repos/jbm329/expo-studio/actions/runs/123456789/attempts/2/jobs?per_page=100",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", True),
        ("id", 0),
        ("run_id", 123456788),
        ("run_id", "123456789"),
        ("run_attempt", 1),
        ("run_attempt", "2"),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("started_at", None),
        ("completed_at", None),
        ("started_at", "2026-11-04T12:01:01Z"),
        ("completed_at", "2026-11-04T12:00:59Z"),
        ("started_at", "invalid"),
    ],
)
def test_require_publication_job_rejects_bad_job(
    monkeypatch: pytest.MonkeyPatch,
    publication_manifest: dict[str, object],
    publication_job: dict[str, object],
    deployment_success: dict[str, object],
    field: str,
    value: object,
) -> None:
    pages = [{"jobs": [{**publication_job, field: value}]}]
    monkeypatch.setattr(
        subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(pages)))
    )

    with pytest.raises(TypeError if value is None else ValueError):
        require_publication_job("jbm329/expo-studio", deployment_success, publication_manifest, 2)


@pytest.mark.parametrize("count", [0, 2])
def test_require_publication_job_requires_unique_named_job(
    monkeypatch: pytest.MonkeyPatch,
    publication_manifest: dict[str, object],
    publication_job: dict[str, object],
    deployment_success: dict[str, object],
    count: int,
) -> None:
    pages = [{"jobs": [publication_job] * count}]
    monkeypatch.setattr(
        subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(pages)))
    )

    with pytest.raises(ValueError, match="exactly one"):
        require_publication_job("jbm329/expo-studio", deployment_success, publication_manifest, 2)


@pytest.mark.parametrize("response", ["null", "{}", "[null]", "[{}]", '[{"jobs": [null]}]'])
def test_require_publication_job_rejects_malformed_pages(
    monkeypatch: pytest.MonkeyPatch,
    publication_manifest: dict[str, object],
    deployment_success: dict[str, object],
    response: str,
) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=response)))

    with pytest.raises(TypeError):
        require_publication_job("jbm329/expo-studio", deployment_success, publication_manifest, 2)


def test_require_publication_job_rejects_link_to_other_job(
    monkeypatch: pytest.MonkeyPatch,
    publication_manifest: dict[str, object],
    publication_job: dict[str, object],
    deployment_success: dict[str, object],
) -> None:
    pages = [{"jobs": [publication_job]}]
    monkeypatch.setattr(
        subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(pages)))
    )
    status = {**deployment_success, "log_url": str(deployment_success["log_url"]) + "/job/988"}

    with pytest.raises(ValueError, match="different job"):
        require_publication_job("jbm329/expo-studio", status, publication_manifest, 2)


@pytest.mark.parametrize("attempt", [True, 0, -1, "2", None])
def test_require_publication_job_rejects_invalid_attempt_before_api(
    monkeypatch: pytest.MonkeyPatch,
    publication_manifest: dict[str, object],
    deployment_success: dict[str, object],
    attempt: object,
) -> None:
    runner = Mock()
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(ValueError, match="positive integer"):
        require_publication_job("jbm329/expo-studio", deployment_success, publication_manifest, attempt)

    runner.assert_not_called()


@pytest.mark.parametrize(
    "error", [subprocess.CalledProcessError(1, ["gh", "api"]), FileNotFoundError("gh unavailable")]
)
def test_require_publication_job_propagates_api_failure(
    monkeypatch: pytest.MonkeyPatch,
    publication_manifest: dict[str, object],
    deployment_success: dict[str, object],
    error: Exception,
) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=error))

    with pytest.raises(type(error)):
        require_publication_job("jbm329/expo-studio", deployment_success, publication_manifest, 2)


@pytest.fixture
def manual_publication_run() -> dict[str, object]:
    return {
        "id": 123456789,
        "path": ".github/workflows/publish-docs.yml",
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": "a" * 40,
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "jbm329/expo-studio"},
        "head_repository": {"full_name": "jbm329/expo-studio"},
        "run_attempt": 2,
    }


def test_require_manual_publication_run_checks_api_metadata(
    monkeypatch: pytest.MonkeyPatch,
    publication_manifest: dict[str, object],
    manual_publication_run: dict[str, object],
) -> None:
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(manual_publication_run)))
    monkeypatch.setattr(subprocess, "run", runner)

    attempt = require_manual_publication_run(
        "jbm329/expo-studio", {"id": 1, "sha": "A" * 40}, {**publication_manifest, "mode": "bootstrap"}
    )

    assert attempt == 2
    runner.assert_called_once_with(
        ["gh", "api", "--method", "GET", "repos/jbm329/expo-studio/actions/runs/123456789"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", True),
        ("id", 123456788),
        ("id", "123456789"),
        ("path", ".github/workflows/other.yml"),
        ("event", "pull_request"),
        ("head_branch", "correction-branch"),
        ("head_sha", "b" * 40),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("conclusion", None),
        ("repository", {"full_name": "another/repo"}),
        ("head_repository", {"full_name": "another/repo"}),
        ("head_repository", None),
        ("run_attempt", True),
        ("run_attempt", 0),
        ("run_attempt", "2"),
    ],
)
def test_require_manual_publication_run_rejects_mismatches(
    monkeypatch: pytest.MonkeyPatch,
    publication_manifest: dict[str, object],
    manual_publication_run: dict[str, object],
    field: str,
    value: object,
) -> None:
    run = {**manual_publication_run, field: value}
    monkeypatch.setattr(
        subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(run)))
    )

    with pytest.raises(ValueError):
        require_manual_publication_run(
            "jbm329/expo-studio", {"id": 1, "sha": "a" * 40}, {**publication_manifest, "mode": "correction"}
        )


@pytest.mark.parametrize(
    ("response", "error"), [("null", TypeError), ("[]", TypeError), ("{}", ValueError), ("{", ValueError)]
)
def test_require_manual_publication_run_rejects_bad_response(
    monkeypatch: pytest.MonkeyPatch, publication_manifest: dict[str, object], response: str, error: type[Exception]
) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=response)))

    with pytest.raises(error):
        require_manual_publication_run(
            "jbm329/expo-studio", {"id": 1, "sha": "a" * 40}, {**publication_manifest, "mode": "bootstrap"}
        )


def test_require_manual_publication_run_rejects_release_before_api(
    monkeypatch: pytest.MonkeyPatch, publication_manifest: dict[str, object]
) -> None:
    runner = Mock()
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(ValueError, match="automatic release"):
        require_manual_publication_run("jbm329/expo-studio", {"id": 1, "sha": "a" * 40}, publication_manifest)

    runner.assert_not_called()


@pytest.mark.parametrize(
    "error", [subprocess.CalledProcessError(1, ["gh", "api"]), FileNotFoundError("gh unavailable")]
)
def test_require_manual_publication_run_propagates_api_failure(
    monkeypatch: pytest.MonkeyPatch, publication_manifest: dict[str, object], error: Exception
) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=error))

    with pytest.raises(type(error)):
        require_manual_publication_run(
            "jbm329/expo-studio", {"id": 1, "sha": "a" * 40}, {**publication_manifest, "mode": "bootstrap"}
        )


@pytest.mark.parametrize("suffix", ["", "/job/987654321"])
def test_require_deployment_run_accepts_matching_run(publication_manifest: dict[str, object], suffix: str) -> None:
    status = {
        "id": 1,
        "state": "success",
        "log_url": f"https://github.com/jbm329/expo-studio/actions/runs/123456789{suffix}",
        "created_at": "2026-11-04T12:00:00Z",
    }

    require_deployment_run("jbm329/expo-studio", status, publication_manifest)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://github.com/jbm329/expo-studio/actions/runs/123456788",
        "https://github.com/another/repo/actions/runs/123456789",
        "https://github.com.evil.example/jbm329/expo-studio/actions/runs/123456789",
        "http://github.com/jbm329/expo-studio/actions/runs/123456789",
        "https://github.com/jbm329/expo-studio/actions/runs/123456789?run=1",
        "https://github.com/jbm329/expo-studio/actions/runs/123456789#summary",
        "https://github.com/jbm329/expo-studio/actions/runs/123456789/job/0",
        "https://github.com/jbm329/expo-studio/actions/runs/123456789/job/01",
        "https://github.com/jbm329/expo-studio/actions/runs/123456789/",
        "https://github.com/jbm329/expo-studio/actions/runs/123456789\n",
    ],
)
def test_require_deployment_run_rejects_nonmatching_url(publication_manifest: dict[str, object], url: str) -> None:
    status = {"id": 1, "state": "success", "log_url": url, "created_at": "2026-11-04T12:00:00Z"}

    with pytest.raises(ValueError, match="does not match"):
        require_deployment_run("jbm329/expo-studio", status, publication_manifest)


@pytest.mark.parametrize("state", ["error", "failure", "inactive", "in_progress", "queued", "pending"])
def test_require_deployment_run_rejects_unsuccessful_status(
    publication_manifest: dict[str, object], state: str
) -> None:
    status = {
        "id": 1,
        "state": state,
        "log_url": "https://github.com/jbm329/expo-studio/actions/runs/123456789",
        "created_at": "2026-11-04T12:00:00Z",
    }

    with pytest.raises(ValueError, match="successful deployment"):
        require_deployment_run("jbm329/expo-studio", status, publication_manifest)


def test_require_deployment_run_validates_manifest_and_repository(publication_manifest: dict[str, object]) -> None:
    status = {
        "id": 1,
        "state": "success",
        "log_url": "https://github.com/jbm329/expo-studio/actions/runs/123456789",
        "created_at": "2026-11-04T12:00:00Z",
    }
    with pytest.raises(ValueError, match="owner/repository"):
        require_deployment_run("owner/repo?query=1", status, publication_manifest)
    with pytest.raises(ValueError, match="run ID"):
        require_deployment_run("jbm329/expo-studio", status, {**publication_manifest, "run_id": "123456789/extra"})


@pytest.mark.parametrize(
    "states",
    [
        ["success"],
        ["failure", "success", "inactive", "error"],
        ["inactive", "success", "failure"],
    ],
)
def test_fetch_current_pages_deployment_selects_unique_success(
    monkeypatch: pytest.MonkeyPatch, states: list[str]
) -> None:
    deployments = [{"id": index + 1, "sha": "a" * 40} for index in range(len(states))]
    statuses = [
        {"id": index + 10, "state": state, "log_url": "", "created_at": "2026-11-04T12:00:00Z"}
        for index, state in enumerate(states)
    ]
    history = Mock(return_value=deployments)
    fetch_status = Mock(side_effect=lambda slug, deployment_id: [statuses[deployment_id - 1]])
    monkeypatch.setitem(fetch_current_pages_deployment.__globals__, "fetch_pages_deployments", history)
    monkeypatch.setitem(fetch_current_pages_deployment.__globals__, "fetch_deployment_statuses", fetch_status)

    current = fetch_current_pages_deployment("jbm329/expo-studio")

    index = states.index("success")
    assert current == (deployments[index], statuses[index])
    history.assert_called_once_with("jbm329/expo-studio")
    assert fetch_status.call_count == len(states)


def test_fetch_current_pages_deployment_distinguishes_empty_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(fetch_current_pages_deployment.__globals__, "fetch_pages_deployments", Mock(return_value=[]))
    fetch_status = Mock()
    monkeypatch.setitem(fetch_current_pages_deployment.__globals__, "fetch_deployment_statuses", fetch_status)

    assert fetch_current_pages_deployment("jbm329/expo-studio") is None
    fetch_status.assert_not_called()


@pytest.mark.parametrize(
    ("states", "message"),
    [
        (["success", "success"], "Multiple currently successful"),
        (["failure", "inactive", "error"], "no currently successful"),
        (["pending", "success"], "unfinished"),
        (["success", "queued"], "unfinished"),
        (["in_progress"], "unfinished"),
    ],
)
def test_fetch_current_pages_deployment_rejects_uncertain_history(
    monkeypatch: pytest.MonkeyPatch, states: list[str], message: str
) -> None:
    deployments = [{"id": index + 1, "sha": "a" * 40} for index in range(len(states))]
    monkeypatch.setitem(
        fetch_current_pages_deployment.__globals__, "fetch_pages_deployments", Mock(return_value=deployments)
    )
    fetch_status = Mock(
        side_effect=lambda slug, deployment_id: [
            {
                "id": deployment_id,
                "state": states[deployment_id - 1],
                "log_url": "",
                "created_at": "2026-11-04T12:00:00Z",
            }
        ]
    )
    monkeypatch.setitem(fetch_current_pages_deployment.__globals__, "fetch_deployment_statuses", fetch_status)

    with pytest.raises(ValueError, match=message):
        fetch_current_pages_deployment("jbm329/expo-studio")


@pytest.mark.parametrize("failure_point", ["history", "statuses"])
def test_fetch_current_pages_deployment_propagates_api_failure(
    monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    error = subprocess.CalledProcessError(1, ["gh", "api"])
    history = Mock(return_value=[{"id": 1, "sha": "a" * 40}])
    statuses = Mock(side_effect=error)
    if failure_point == "history":
        history.side_effect = error
    monkeypatch.setitem(fetch_current_pages_deployment.__globals__, "fetch_pages_deployments", history)
    monkeypatch.setitem(fetch_current_pages_deployment.__globals__, "fetch_deployment_statuses", statuses)

    with pytest.raises(subprocess.CalledProcessError):
        fetch_current_pages_deployment("jbm329/expo-studio")


def test_fetch_current_pages_deployment_rejects_missing_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        fetch_current_pages_deployment.__globals__,
        "fetch_pages_deployments",
        Mock(return_value=[{"id": 1, "sha": "a" * 40}]),
    )
    monkeypatch.setitem(fetch_current_pages_deployment.__globals__, "fetch_deployment_statuses", Mock(return_value=[]))

    with pytest.raises(ValueError, match="without status records"):
        fetch_current_pages_deployment("jbm329/expo-studio")


def test_fetch_current_pages_deployment_rejects_duplicate_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    deployment = {"id": 1, "sha": "a" * 40}
    status = {"id": 1, "state": "success", "log_url": "", "created_at": "2026-11-04T12:00:00Z"}
    monkeypatch.setitem(
        fetch_current_pages_deployment.__globals__,
        "fetch_pages_deployments",
        Mock(return_value=[deployment, deployment]),
    )
    monkeypatch.setitem(
        fetch_current_pages_deployment.__globals__, "fetch_deployment_statuses", Mock(return_value=[status])
    )

    with pytest.raises(ValueError, match="Repeated"):
        fetch_current_pages_deployment("jbm329/expo-studio")


def test_fetch_deployment_statuses_combines_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    success = {
        "id": 10,
        "state": "success",
        "log_url": "https://github.com/jbm329/expo-studio/actions/runs/123",
        "created_at": "2026-11-04T12:00:00Z",
    }
    inactive = {"id": 20, "state": "inactive", "log_url": "", "created_at": "2026-11-04T12:01:00Z"}
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps([[inactive], [], [success]])))
    monkeypatch.setattr(subprocess, "run", runner)

    assert fetch_deployment_statuses("jbm329/expo-studio", 42) == [inactive, success]
    runner.assert_called_once_with(
        [
            "gh",
            "api",
            "--method",
            "GET",
            "--paginate",
            "--slurp",
            "repos/jbm329/expo-studio/deployments/42/statuses?per_page=100",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.parametrize("state", ["error", "failure", "inactive", "in_progress", "queued", "pending", "success"])
def test_fetch_deployment_statuses_preserves_states(monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    status = {"id": 1, "state": state, "log_url": "", "created_at": "2026-11-04T12:00:00Z"}
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps([[status]])))
    monkeypatch.setattr(subprocess, "run", runner)

    assert fetch_deployment_statuses("jbm329/expo-studio", 42) == [status]


@pytest.mark.parametrize("response", ["[]", "[[]]"])
def test_fetch_deployment_statuses_accepts_empty_results(monkeypatch: pytest.MonkeyPatch, response: str) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=response)))

    assert fetch_deployment_statuses("jbm329/expo-studio", 42) == []


@pytest.mark.parametrize("response", ["null", "{}", "[null]", "[[null]]", "[[{}]]"])
def test_fetch_deployment_statuses_rejects_bad_response(monkeypatch: pytest.MonkeyPatch, response: str) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=response)))

    with pytest.raises(TypeError):
        fetch_deployment_statuses("jbm329/expo-studio", 42)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("id", True, TypeError),
        ("id", 1.0, TypeError),
        ("id", "1", TypeError),
        ("id", 0, TypeError),
        ("id", -1, TypeError),
        ("state", "unknown", ValueError),
        ("state", None, ValueError),
        ("log_url", None, TypeError),
        ("log_url", 123, TypeError),
        ("created_at", None, TypeError),
        ("created_at", 123, TypeError),
        ("created_at", "invalid", ValueError),
        ("created_at", "2026-11-04T12:00:00", ValueError),
        ("created_at", "2026-11-04T12:00:00+01:00", ValueError),
    ],
)
def test_fetch_deployment_statuses_rejects_bad_fields(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object, error: type[Exception]
) -> None:
    status = {
        "id": 1,
        "state": "success",
        "log_url": "",
        "created_at": "2026-11-04T12:00:00Z",
        field: value,
    }
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps([[status]])))
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(error):
        fetch_deployment_statuses("jbm329/expo-studio", 42)


@pytest.mark.parametrize("deployment_id", [None, True, 1.0, "42", 0, -1])
def test_fetch_deployment_statuses_rejects_bad_id_before_cli(
    monkeypatch: pytest.MonkeyPatch, deployment_id: object
) -> None:
    runner = Mock()
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(ValueError, match="positive integer"):
        fetch_deployment_statuses("jbm329/expo-studio", deployment_id)

    runner.assert_not_called()


@pytest.mark.parametrize(
    "error", [subprocess.CalledProcessError(1, ["gh", "api"]), FileNotFoundError("gh unavailable")]
)
def test_fetch_deployment_statuses_propagates_cli_failure(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=error))

    with pytest.raises(type(error)):
        fetch_deployment_statuses("jbm329/expo-studio", 42)


def test_fetch_deployment_statuses_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout="{")))

    with pytest.raises(json.JSONDecodeError):
        fetch_deployment_statuses("jbm329/expo-studio", 42)


def test_fetch_deployment_statuses_rejects_bad_repository_before_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Mock()
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(ValueError, match="owner/repository"):
        fetch_deployment_statuses("owner/repo?query=1", 42)

    runner.assert_not_called()


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("state", ["success", "inactive", "failure", "in_progress"])
def test_latest_deployment_status_uses_timestamp_not_id_or_state(reverse: bool, state: str) -> None:
    older = {"id": 99, "state": "success", "log_url": "", "created_at": "2026-11-04T12:00:00Z"}
    newer = {"id": 1, "state": state, "log_url": "", "created_at": "2026-11-04T12:01:00Z"}
    statuses = [older, newer]
    if reverse:
        statuses.reverse()

    assert latest_deployment_status(statuses) == newer


def test_latest_deployment_status_rejects_empty_history() -> None:
    with pytest.raises(ValueError, match="without status records"):
        latest_deployment_status([])


def test_latest_deployment_status_rejects_ambiguous_latest_records() -> None:
    success = {"id": 1, "state": "success", "log_url": "", "created_at": "2026-11-04T12:00:00Z"}
    inactive = {**success, "id": 2, "state": "inactive"}

    with pytest.raises(ValueError, match="ambiguous"):
        latest_deployment_status([success, inactive])


def test_latest_deployment_status_allows_identical_duplicates_and_older_ties() -> None:
    older = {"id": 1, "state": "pending", "log_url": "", "created_at": "2026-11-04T12:00:00Z"}
    latest = {**older, "id": 3, "state": "success", "created_at": "2026-11-04T12:01:00Z"}

    assert latest_deployment_status([older, {**older, "id": 2}, latest, latest.copy()]) == latest


def test_fetch_deployment_statuses_requires_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    status = {"id": 1, "state": "success", "log_url": ""}
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps([[status]])))
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(TypeError, match="created_at"):
        fetch_deployment_statuses("jbm329/expo-studio", 42)


def test_fetch_pages_deployments_combines_and_validates_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    first = {"id": 20, "sha": "A" * 40, "environment": "github-pages", "extra": "ignored"}
    second = {"id": 10, "sha": "b" * 40, "environment": "github-pages"}
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps([[first], [], [second]])))
    monkeypatch.setattr(subprocess, "run", runner)

    assert fetch_pages_deployments("jbm329/expo-studio") == [
        {"id": 20, "sha": "a" * 40},
        {"id": 10, "sha": "b" * 40},
    ]
    runner.assert_called_once_with(
        [
            "gh",
            "api",
            "--method",
            "GET",
            "--paginate",
            "--slurp",
            "repos/jbm329/expo-studio/deployments?per_page=100&environment=github-pages",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.parametrize("response", ["[]", "[[]]"])
def test_fetch_pages_deployments_accepts_empty_history(monkeypatch: pytest.MonkeyPatch, response: str) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=response)))

    assert fetch_pages_deployments("jbm329/expo-studio") == []


@pytest.mark.parametrize("response", ["null", "{}", "[null]", "[[null]]", "[[{}]]"])
def test_fetch_pages_deployments_rejects_bad_response(monkeypatch: pytest.MonkeyPatch, response: str) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=response)))

    with pytest.raises(TypeError):
        fetch_pages_deployments("jbm329/expo-studio")


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("id", True, TypeError),
        ("id", 1.0, TypeError),
        ("id", "1", TypeError),
        ("id", 0, TypeError),
        ("id", -1, TypeError),
        ("sha", None, TypeError),
        ("sha", "main", ValueError),
        ("environment", "production", TypeError),
        ("environment", None, TypeError),
    ],
)
def test_fetch_pages_deployments_rejects_bad_fields(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object, error: type[Exception]
) -> None:
    entry = {"id": 1, "sha": "a" * 40, "environment": "github-pages", field: value}
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps([[entry]])))
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(error):
        fetch_pages_deployments("jbm329/expo-studio")


@pytest.mark.parametrize(
    "error", [subprocess.CalledProcessError(1, ["gh", "api"]), FileNotFoundError("gh unavailable")]
)
def test_fetch_pages_deployments_propagates_cli_failure(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=error))

    with pytest.raises(type(error)):
        fetch_pages_deployments("jbm329/expo-studio")


def test_fetch_pages_deployments_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout="{")))

    with pytest.raises(json.JSONDecodeError):
        fetch_pages_deployments("jbm329/expo-studio")


def test_fetch_pages_deployments_rejects_bad_repository_before_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Mock()
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(ValueError, match="owner/repository"):
        fetch_pages_deployments("owner/repo?environment=production")

    runner.assert_not_called()


def test_fetch_github_releases_combines_all_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    older = {"tag_name": "v1.9.0", "draft": False, "prerelease": False}
    newer = {"tag_name": "v1.10.0", "draft": False, "prerelease": False}
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps([[older], [newer], []])))
    monkeypatch.setattr(subprocess, "run", runner)

    releases = fetch_github_releases("jbm329/expo-studio")

    assert releases == [older, newer]
    assert latest_stable_tag(releases) == "v1.10.0"
    runner.assert_called_once_with(
        [
            "gh",
            "api",
            "--method",
            "GET",
            "--paginate",
            "--slurp",
            "repos/jbm329/expo-studio/releases?per_page=100",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.parametrize("response", ["[[]]", "[]"])
def test_fetch_github_releases_accepts_empty_results(monkeypatch: pytest.MonkeyPatch, response: str) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=response)))

    assert fetch_github_releases("jbm329/expo-studio") == []


@pytest.mark.parametrize(
    "response",
    [
        "null",
        "{}",
        "[null]",
        '[{"tag_name": "v1.4.0", "draft": false, "prerelease": false}]',
        '[[{"tag_name": "v1.4.0"}]]',
    ],
)
def test_fetch_github_releases_rejects_invalid_pages(monkeypatch: pytest.MonkeyPatch, response: str) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout=response)))

    with pytest.raises(TypeError):
        fetch_github_releases("jbm329/expo-studio")


def test_fetch_github_releases_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, stdout="{")))

    with pytest.raises(json.JSONDecodeError):
        fetch_github_releases("jbm329/expo-studio")


@pytest.mark.parametrize(
    "error", [subprocess.CalledProcessError(1, ["gh", "api"]), FileNotFoundError("gh unavailable")]
)
def test_fetch_github_releases_surfaces_cli_failure(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=error))

    with pytest.raises(type(error)):
        fetch_github_releases("jbm329/expo-studio")


@pytest.mark.parametrize(
    "slug", ["", "expo-studio", "../repo", "owner/repo/extra", "owner/repo?query=1", "-owner/repo"]
)
def test_fetch_github_releases_rejects_invalid_repository_before_cli(
    monkeypatch: pytest.MonkeyPatch, slug: str
) -> None:
    runner = Mock()
    monkeypatch.setattr(subprocess, "run", runner)

    with pytest.raises(ValueError, match="owner/repository"):
        fetch_github_releases(slug)

    runner.assert_not_called()


def test_parse_github_releases_preserves_required_metadata() -> None:
    response = [
        {"tag_name": "v1.4.0", "draft": False, "prerelease": False, "id": 123},
        {"tag_name": "v1.5.0-rc1", "draft": False, "prerelease": True},
        {"tag_name": "unrelated", "draft": True, "prerelease": False},
    ]

    releases = parse_github_releases(response)

    assert releases == [
        {"tag_name": "v1.4.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.5.0-rc1", "draft": False, "prerelease": True},
        {"tag_name": "unrelated", "draft": True, "prerelease": False},
    ]
    assert response[0]["id"] == 123
    assert latest_stable_tag(releases) == "v1.4.0"


def test_parse_github_releases_accepts_empty_page() -> None:
    assert parse_github_releases([]) == []


@pytest.mark.parametrize("response", [None, {}, {"message": "API error"}, "releases", [None], [[]]])
def test_parse_github_releases_rejects_invalid_response(response: object) -> None:
    with pytest.raises(TypeError, match="GitHub release"):
        parse_github_releases(response)


@pytest.mark.parametrize("field", ["tag_name", "draft", "prerelease"])
def test_parse_github_releases_rejects_missing_fields(field: str) -> None:
    release = {"tag_name": "v1.4.0", "draft": False, "prerelease": False}
    del release[field]

    with pytest.raises(TypeError, match="requires a string tag_name and boolean"):
        parse_github_releases([release])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tag_name", None),
        ("tag_name", 123),
        ("draft", "false"),
        ("draft", 0),
        ("draft", None),
        ("prerelease", "false"),
        ("prerelease", 1),
        ("prerelease", None),
    ],
)
def test_parse_github_releases_rejects_invalid_field_types(field: str, value: object) -> None:
    release = {"tag_name": "v1.4.0", "draft": False, "prerelease": False}
    release[field] = value

    with pytest.raises(TypeError, match="requires a string tag_name and boolean"):
        parse_github_releases([release])


def test_parse_github_releases_rejects_invalid_entry_after_valid_release() -> None:
    response = [
        {"tag_name": "v1.4.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.5.0", "draft": False},
    ]

    with pytest.raises(TypeError, match="index 1"):
        parse_github_releases(response)


@pytest.fixture
def publication_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "release",
        "baseline_tag": "v1.4.0",
        "source_sha": "0123456789abcdef0123456789abcdef01234567",
        "run_id": "123456789",
    }


@pytest.mark.parametrize("mode", ["bootstrap", "release", "correction"])
def test_publication_manifest_accepts_supported_modes(publication_manifest: dict[str, object], mode: str) -> None:
    publication_manifest["mode"] = mode

    assert parse_publication_manifest(publication_manifest) == publication_manifest


def test_publication_manifest_normalizes_sha_without_mutating_input(publication_manifest: dict[str, object]) -> None:
    source = str(publication_manifest["source_sha"]).upper()
    publication_manifest["source_sha"] = source

    parsed = parse_publication_manifest(publication_manifest)

    assert parsed["source_sha"] == source.lower()
    assert publication_manifest["source_sha"] == source


@pytest.mark.parametrize("field", ["schema_version", "mode", "baseline_tag", "source_sha", "run_id"])
def test_publication_manifest_rejects_missing_fields(publication_manifest: dict[str, object], field: str) -> None:
    del publication_manifest[field]

    with pytest.raises(ValueError, match="exactly the supported provenance fields"):
        parse_publication_manifest(publication_manifest)


def test_publication_manifest_rejects_unknown_fields(publication_manifest: dict[str, object]) -> None:
    publication_manifest["unexpected"] = "value"

    with pytest.raises(ValueError, match="exactly the supported provenance fields"):
        parse_publication_manifest(publication_manifest)


@pytest.mark.parametrize("value", [None, [], "manifest", 1])
def test_publication_manifest_requires_an_object(value: object) -> None:
    with pytest.raises(ValueError, match="exactly the supported provenance fields"):
        parse_publication_manifest(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("schema_version", "1"),
        ("schema_version", 1.0),
        ("schema_version", 2),
        ("mode", "preview"),
        ("mode", None),
        ("mode", []),
        ("baseline_tag", None),
        ("baseline_tag", "v1.4.0-rc1"),
        ("source_sha", None),
        ("source_sha", "main"),
        ("run_id", 123),
        ("run_id", "0"),
        ("run_id", "-1"),
        ("run_id", "0123"),
        ("run_id", "123\n"),
        ("run_id", "https://example.invalid/run"),
    ],
)
def test_publication_manifest_rejects_invalid_values(
    publication_manifest: dict[str, object], field: str, value: object
) -> None:
    publication_manifest[field] = value

    with pytest.raises(ValueError):
        parse_publication_manifest(publication_manifest)


def test_manifest_file_round_trip(tmp_path: Path, publication_manifest: dict[str, object]) -> None:
    path = tmp_path / "publication.json"

    write_publication_manifest(path, publication_manifest)

    assert read_publication_manifest(path) == publication_manifest
    expected = json.dumps(publication_manifest, indent=2, sort_keys=True) + "\n"
    assert path.read_bytes() == expected.encode("utf-8")


def test_read_manifest_surfaces_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_publication_manifest(tmp_path / "missing.json")


@pytest.mark.parametrize("content", ["{", "null", "[]", "{}"])
def test_read_manifest_rejects_invalid_file_content(tmp_path: Path, content: str) -> None:
    path = tmp_path / "publication.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError):
        read_publication_manifest(path)


def test_read_manifest_surfaces_invalid_encoding(tmp_path: Path) -> None:
    path = tmp_path / "publication.json"
    path.write_bytes(b"\xff")

    with pytest.raises(UnicodeDecodeError):
        read_publication_manifest(path)


def test_write_manifest_validates_before_replacing_file(
    tmp_path: Path, publication_manifest: dict[str, object]
) -> None:
    path = tmp_path / "publication.json"
    write_publication_manifest(path, publication_manifest)
    original = path.read_bytes()
    publication_manifest["mode"] = "invalid"

    with pytest.raises(ValueError, match="Unsupported publication manifest mode"):
        write_publication_manifest(path, publication_manifest)

    assert path.read_bytes() == original


def test_write_manifest_surfaces_invalid_destination(tmp_path: Path, publication_manifest: dict[str, object]) -> None:
    with pytest.raises(FileNotFoundError):
        write_publication_manifest(tmp_path / "missing-directory" / "publication.json", publication_manifest)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v0.0.0", (0, 0, 0)),
        ("v1.3.0", (1, 3, 0)),
        ("v1.10.2", (1, 10, 2)),
        ("v12.34.56", (12, 34, 56)),
    ],
)
def test_parse_stable_tag(tag: str, expected: tuple[int, int, int]) -> None:
    assert parse_stable_tag(tag) == expected


@pytest.mark.parametrize(
    "tag",
    [
        "",
        "1.3.0",
        "v1.3",
        "v1.3.0.1",
        "v1.4.0-rc1",
        "v1.4.0-a1",
        "v1.4.0-b1",
        "v1.3.0+build",
        "v01.3.0",
        "v1.03.0",
        "v1.3.00",
        " v1.3.0",
        "v1.3.0\n",
    ],
)
def test_parse_stable_tag_rejects_invalid_tags(tag: str) -> None:
    with pytest.raises(ValueError, match="Unsupported stable release tag"):
        parse_stable_tag(tag)


@pytest.mark.parametrize(
    ("tag", "draft", "prerelease", "expected"),
    [
        ("v1.4.0", False, False, True),
        ("v0.0.0", False, False, True),
        ("v1.4.0", True, False, False),
        ("v1.4.0", False, True, False),
        ("v1.4.0", True, True, False),
        ("v1.4.0-rc1", False, False, False),
        ("v1.4.0-a1", False, False, False),
        ("v1.4.0-b1", False, False, False),
        ("1.4.0", False, False, False),
        ("v01.4.0", False, False, False),
        ("", False, False, False),
    ],
)
def test_is_stable_release(
    tag: str,
    draft: bool,
    prerelease: bool,
    expected: bool,
) -> None:
    assert is_stable_release(tag, draft=draft, prerelease=prerelease) is expected


def test_stable_versions_compare_numerically() -> None:
    assert parse_stable_tag("v1.10.0") > parse_stable_tag("v1.9.0")
    assert parse_stable_tag("v2.0.0") > parse_stable_tag("v1.99.99")


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (["v1.3.0"], "v1.3.0"),
        (["v1.9.0", "v1.10.0", "v1.2.0"], "v1.10.0"),
        (["v1.2.0", "v1.10.0", "v1.9.0"], "v1.10.0"),
        (["v1.99.99", "v2.0.0"], "v2.0.0"),
        (["v1.3.0", "v1.3.0"], "v1.3.0"),
    ],
)
def test_latest_stable_tag_uses_numeric_order(tags: list[str], expected: str) -> None:
    releases = [{"tag_name": tag, "draft": False, "prerelease": False} for tag in tags]

    assert latest_stable_tag(releases) == expected


def test_latest_stable_tag_excludes_ineligible_releases() -> None:
    releases = [
        {"tag_name": "v1.3.0", "draft": False, "prerelease": False},
        {"tag_name": "v9.0.0", "draft": True, "prerelease": False},
        {"tag_name": "v8.0.0", "draft": False, "prerelease": True},
        {"tag_name": "v7.0.0-rc1", "draft": False, "prerelease": False},
        {"tag_name": "v06.0.0", "draft": False, "prerelease": False},
        {"tag_name": "unrelated-tag", "draft": False, "prerelease": False},
    ]

    assert latest_stable_tag(releases) == "v1.3.0"


@pytest.mark.parametrize(
    "releases",
    [
        [],
        [{"tag_name": "v1.3.0", "draft": True, "prerelease": False}],
        [{"tag_name": "v1.3.0", "draft": False, "prerelease": True}],
        [{"tag_name": "v1.4.0-rc1", "draft": False, "prerelease": False}],
        [{"tag_name": "unrelated-tag", "draft": False, "prerelease": False}],
    ],
)
def test_latest_stable_tag_requires_an_eligible_release(releases: list[dict[str, object]]) -> None:
    with pytest.raises(ValueError, match="No supported published stable release"):
        latest_stable_tag(releases)


def test_require_latest_stable_tag_accepts_current_baseline() -> None:
    releases = [
        {"tag_name": "v1.9.0", "draft": False, "prerelease": False},
        {"tag_name": "v2.0.0", "draft": True, "prerelease": False},
        {"tag_name": "v1.11.0", "draft": False, "prerelease": True},
        {"tag_name": "v1.10.0", "draft": False, "prerelease": False},
    ]

    assert require_latest_stable_tag("v1.10.0", releases) is None


@pytest.mark.parametrize("expected_tag", ["v1.9.0", "v1.11.0", "v2.0.0"])
def test_require_latest_stable_tag_rejects_other_baselines(expected_tag: str) -> None:
    releases = [
        {"tag_name": "v1.9.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.10.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.11.0", "draft": False, "prerelease": True},
        {"tag_name": "v2.0.0", "draft": True, "prerelease": False},
    ]

    with pytest.raises(ValueError, match="is not the latest published stable release") as error:
        require_latest_stable_tag(expected_tag, releases)

    assert expected_tag in str(error.value)
    assert "v1.10.0" in str(error.value)


@pytest.mark.parametrize("expected_tag", ["v1.10.0-rc1", "main", ""])
def test_require_latest_stable_tag_rejects_unsupported_tags(expected_tag: str) -> None:
    releases = [{"tag_name": "v1.10.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="Unsupported stable release tag"):
        require_latest_stable_tag(expected_tag, releases)


def test_require_latest_stable_tag_rejects_missing_stable_release() -> None:
    with pytest.raises(ValueError, match="No supported published stable release"):
        require_latest_stable_tag("v1.10.0", [])


def test_require_latest_stable_tag_rejects_superseded_baseline() -> None:
    releases = [{"tag_name": "v1.10.0", "draft": False, "prerelease": False}]
    require_latest_stable_tag("v1.10.0", releases)

    releases.append({"tag_name": "v1.11.0", "draft": False, "prerelease": False})

    with pytest.raises(ValueError, match="is not the latest published stable release"):
        require_latest_stable_tag("v1.10.0", releases)


@pytest.mark.parametrize(
    "source_sha",
    [
        "0123456789abcdef0123456789abcdef01234567",
        "0123456789ABCDEF0123456789ABCDEF01234567",
        "0123456789aBcDeF0123456789AbCdEf01234567",
    ],
)
def test_validate_commit_sha_normalizes_full_ids(source_sha: str) -> None:
    assert validate_commit_sha(source_sha) == source_sha.lower()


@pytest.mark.parametrize(
    "source_sha",
    [
        "",
        "main",
        "v1.3.0",
        "abcdef0",
        "a" * 39,
        "a" * 41,
        "a" * 64,
        "g" * 40,
        " " + "a" * 40,
        "a" * 40 + "\n",
        "a" * 40 + "^{commit}",
        "-" + "a" * 39,
    ],
)
def test_validate_commit_sha_rejects_non_full_ids(source_sha: str) -> None:
    with pytest.raises(ValueError, match="Expected a full 40-character hexadecimal commit SHA"):
        validate_commit_sha(source_sha)


def run_git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def git_repository(tmp_path: Path) -> Path:
    run_git(tmp_path, "init", "--quiet")
    run_git(tmp_path, "config", "user.name", "Documentation Tests")
    run_git(tmp_path, "config", "user.email", "docs-tests@example.invalid")
    (tmp_path / "example.txt").write_text("Synthetic test content.\n", encoding="utf-8")
    run_git(tmp_path, "add", "example.txt")
    run_git(tmp_path, "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Initial test commit")
    return tmp_path


@pytest.mark.parametrize("uppercase", [False, True])
def test_require_commit_accepts_existing_commit(git_repository: Path, uppercase: bool) -> None:
    commit_sha = run_git(git_repository, "rev-parse", "HEAD")

    assert require_commit(git_repository, commit_sha.upper() if uppercase else commit_sha) == commit_sha


@pytest.mark.parametrize("revision", ["HEAD:example.txt", "HEAD^{tree}", "refs/tags/example"])
def test_require_commit_rejects_other_object_types(git_repository: Path, revision: str) -> None:
    run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "-a", "example", "-m", "Annotated test tag")
    object_sha = run_git(git_repository, "rev-parse", revision)

    with pytest.raises(ValueError, match="is not a Git commit"):
        require_commit(git_repository, object_sha)


def test_require_commit_rejects_missing_object(git_repository: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        require_commit(git_repository, "0" * 40)


def test_require_commit_rejects_invalid_sha_before_running_git(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Expected a full 40-character hexadecimal commit SHA"):
        require_commit(tmp_path / "nonexistent", "main")


def test_require_commit_surfaces_invalid_repository(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        require_commit(tmp_path, "a" * 40)


def create_test_commit(repository: Path, message: str = "Test descendant") -> str:
    run_git(repository, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "--quiet", "-m", message)
    return run_git(repository, "rev-parse", "HEAD")


def test_require_ancestor_accepts_same_commit(git_repository: Path) -> None:
    commit_sha = run_git(git_repository, "rev-parse", "HEAD")

    assert require_ancestor(git_repository, commit_sha, commit_sha) is None


def test_require_ancestor_accepts_transitive_history(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    create_test_commit(git_repository)
    descendant = create_test_commit(git_repository)

    assert require_ancestor(git_repository, baseline.upper(), descendant.upper()) is None


def test_require_ancestor_rejects_reversed_history(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    descendant = create_test_commit(git_repository)

    with pytest.raises(ValueError, match="is not an ancestor of") as error:
        require_ancestor(git_repository, descendant, baseline)

    assert baseline in str(error.value)
    assert descendant in str(error.value)


def test_require_ancestor_rejects_divergent_history(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    first = create_test_commit(git_repository)
    run_git(git_repository, "checkout", "--quiet", "--detach", baseline)
    second = create_test_commit(git_repository, "Divergent test descendant")

    assert first != second
    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_ancestor(git_repository, first, second)


@pytest.mark.parametrize("missing_ancestor", [False, True])
def test_require_ancestor_surfaces_missing_commit(git_repository: Path, missing_ancestor: bool) -> None:
    existing = run_git(git_repository, "rev-parse", "HEAD")
    ancestor, descendant = ("0" * 40, existing) if missing_ancestor else (existing, "0" * 40)

    with pytest.raises(subprocess.CalledProcessError):
        require_ancestor(git_repository, ancestor, descendant)


@pytest.mark.parametrize("branch", ["main", "docs/1.4.0"])
def test_remote_branch_contains_tip_and_ancestors(git_repository: Path, branch: str) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    tip = create_test_commit(git_repository)
    run_git(git_repository, "update-ref", f"refs/remotes/origin/{branch}", tip)

    assert require_remote_branch_contains_commit(git_repository, branch, tip) == tip
    assert require_remote_branch_contains_commit(git_repository, branch, baseline) == tip


def test_remote_branch_rejects_unmerged_descendant(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    run_git(git_repository, "update-ref", "refs/remotes/origin/main", baseline)
    unmerged = create_test_commit(git_repository)

    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_remote_branch_contains_commit(git_repository, "main", unmerged)


def test_remote_branch_does_not_fall_back_to_local_branch(git_repository: Path) -> None:
    source = run_git(git_repository, "rev-parse", "HEAD")
    run_git(git_repository, "branch", "docs/1.4.0", source)

    with pytest.raises(subprocess.CalledProcessError):
        require_remote_branch_contains_commit(git_repository, "docs/1.4.0", source)


@pytest.mark.parametrize("branch", ["main~1", "main^{commit}", "../main", "main\n", "main space"])
def test_remote_branch_rejects_invalid_ref_names(git_repository: Path, branch: str) -> None:
    source = run_git(git_repository, "rev-parse", "HEAD")

    with pytest.raises(subprocess.CalledProcessError):
        require_remote_branch_contains_commit(git_repository, branch, source)


@pytest.mark.parametrize(
    "path",
    [
        "docs/index.md",
        "docs/data-preparation/derived-columns.md",
        "docs/assets/images/editor.png",
        "docs/assets/example.jpg",
        "docs/assets/example.jpeg",
        "docs/assets/example.gif",
        "docs/assets/example.webp",
        "docs/assets/example.avif",
    ],
)
def test_require_correction_file_accepts_manual_content(path: str) -> None:
    assert require_correction_file(path, "100644") is None


@pytest.mark.parametrize(
    "path",
    [
        "",
        "README.md",
        "zensical.toml",
        "pyproject.toml",
        "uv.lock",
        ".github/workflows/docs.yml",
        "src/example.py",
        "docs/example.py",
        "docs/example.html",
        "docs/assets/example.svg",
        "docs/assets/example.js",
        "docs/images/example.png",
        "/docs/index.md",
        "docs/../README.md",
        "./docs/index.md",
        "docs//index.md",
        "docs/index.md/",
        "docs\\index.md",
        "documentation/index.md",
    ],
)
def test_require_correction_file_rejects_out_of_scope_paths(path: str) -> None:
    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_file(path, "100644")


@pytest.mark.parametrize("mode", ["100755", "120000", "160000", "040000", "000000", ""])
def test_require_correction_file_rejects_non_content_modes(mode: str) -> None:
    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_file("docs/index.md", mode)


def commit_all(repository: Path) -> str:
    run_git(repository, "add", "--all")
    return create_test_commit(repository)


def test_correction_changes_accepts_unchanged_baseline(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")

    assert require_correction_changes(git_repository, baseline, baseline) is None


def test_correction_changes_accepts_manual_edits_additions_and_deletions(git_repository: Path) -> None:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("Original.\n", encoding="utf-8")
    (docs / "old.md").write_text("Old page.\n", encoding="utf-8")
    baseline = commit_all(git_repository)
    (docs / "index.md").write_text("Corrected.\n", encoding="utf-8")
    (docs / "old.md").unlink()
    (docs / "new page.md").write_text("New page.\n", encoding="utf-8")
    assets = docs / "assets"
    assets.mkdir()
    (assets / "example.png").write_bytes(b"Synthetic image fixture")
    source = commit_all(git_repository)

    assert require_correction_changes(git_repository, baseline, source) is None


@pytest.mark.parametrize("operation", ["modify", "delete", "rename"])
def test_correction_changes_rejects_out_of_scope_changes(git_repository: Path, operation: str) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    original = git_repository / "example.txt"
    if operation == "modify":
        original.write_text("Changed application content.\n", encoding="utf-8")
    elif operation == "delete":
        original.unlink()
    else:
        docs = git_repository / "docs"
        docs.mkdir()
        original.rename(docs / "renamed.md")
    source = commit_all(git_repository)

    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_changes(git_repository, baseline, source)


def test_correction_changes_checks_all_commits_since_baseline(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    (git_repository / "example.txt").write_text("Out-of-scope change.\n", encoding="utf-8")
    commit_all(git_repository)
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("A later documentation change.\n", encoding="utf-8")
    source = commit_all(git_repository)

    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_changes(git_repository, baseline, source)


def test_correction_changes_rejects_executable_markdown(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("Executable fixture.\n", encoding="utf-8")
    run_git(git_repository, "add", "docs/index.md")
    run_git(git_repository, "update-index", "--chmod=+x", "docs/index.md")
    source = create_test_commit(git_repository)

    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_changes(git_repository, baseline, source)


@pytest.mark.parametrize("annotated", [False, True])
def test_resolve_stable_tag_commit_accepts_tag_types(git_repository: Path, annotated: bool) -> None:
    expected = run_git(git_repository, "rev-parse", "HEAD")
    if annotated:
        run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "-a", "v1.4.0", "-m", "Test release")
    else:
        run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "v1.4.0")
    create_test_commit(git_repository)

    assert resolve_stable_tag_commit(git_repository, "v1.4.0") == expected


def test_resolve_stable_tag_commit_does_not_use_matching_branch(git_repository: Path) -> None:
    run_git(git_repository, "branch", "v1.4.0")

    with pytest.raises(subprocess.CalledProcessError):
        resolve_stable_tag_commit(git_repository, "v1.4.0")


@pytest.mark.parametrize("annotated", [False, True])
def test_resolve_stable_tag_commit_rejects_non_commit_tags(git_repository: Path, annotated: bool) -> None:
    blob = run_git(git_repository, "rev-parse", "HEAD:example.txt")
    if annotated:
        run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "-a", "v1.4.0", blob, "-m", "Blob tag")
    else:
        run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "v1.4.0", blob)

    with pytest.raises(subprocess.CalledProcessError):
        resolve_stable_tag_commit(git_repository, "v1.4.0")


@pytest.mark.parametrize("tag", ["v1.4.0-rc1", "HEAD", "v1.4.0^{commit}", ""])
def test_resolve_stable_tag_commit_rejects_invalid_tag_before_git(tmp_path: Path, tag: str) -> None:
    with pytest.raises(ValueError, match="Unsupported stable release tag"):
        resolve_stable_tag_commit(tmp_path / "nonexistent", tag)


@pytest.fixture
def correction_history(git_repository: Path) -> tuple[Path, str, str]:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("Released instructions.\n", encoding="utf-8")
    (git_repository / "zensical.toml").write_text('[project]\nsite_name = "Test manual"\n', encoding="utf-8")
    (git_repository / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (git_repository / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    baseline = commit_all(git_repository)
    run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "v1.4.0", baseline)
    (docs / "index.md").write_text("Corrected instructions.\n", encoding="utf-8")
    source = commit_all(git_repository)
    run_git(git_repository, "update-ref", "refs/remotes/origin/docs/1.4.0", source)
    return git_repository, baseline, source


def test_correction_source_accepts_matching_release_branch_and_scope(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, source = correction_history
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    assert require_correction_source(repository, "v1.4.0", source.upper(), releases) == baseline


def test_correction_source_rejects_newer_release(correction_history: tuple[Path, str, str]) -> None:
    repository, _, source = correction_history
    releases = [
        {"tag_name": "v1.4.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.5.0", "draft": False, "prerelease": False},
    ]

    with pytest.raises(ValueError, match="is not the latest published stable release"):
        require_correction_source(repository, "v1.4.0", source, releases)


def test_correction_source_rejects_unmerged_changes(correction_history: tuple[Path, str, str]) -> None:
    repository, _, _ = correction_history
    source = create_test_commit(repository)
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_correction_source(repository, "v1.4.0", source, releases)


def test_correction_source_rejects_merged_code_changes(correction_history: tuple[Path, str, str]) -> None:
    repository, _, _ = correction_history
    (repository / "example.txt").write_text("Application change.\n", encoding="utf-8")
    source = commit_all(repository)
    run_git(repository, "update-ref", "refs/remotes/origin/docs/1.4.0", source)
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="outside the permitted manual content scope"):
        require_correction_source(repository, "v1.4.0", source, releases)


def test_correction_source_rejects_branch_outside_release_history(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, _ = correction_history
    older = run_git(repository, "rev-parse", f"{baseline}^")
    run_git(repository, "update-ref", "refs/remotes/origin/docs/1.4.0", older)
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_correction_source(repository, "v1.4.0", older, releases)


def test_documentation_setup_uses_committed_files(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, _ = correction_history
    (repository / "zensical.toml").unlink()

    assert require_documentation_setup(repository, baseline) is None


@pytest.mark.parametrize("path", ["zensical.toml", "pyproject.toml", "uv.lock", "docs/index.md"])
def test_documentation_setup_rejects_missing_entry_file(correction_history: tuple[Path, str, str], path: str) -> None:
    repository, _, _ = correction_history
    repository.joinpath(*path.split("/")).unlink()
    source = commit_all(repository)

    with pytest.raises(ValueError, match="lacks required regular documentation files") as error:
        require_documentation_setup(repository, source)

    assert path in str(error.value)


def test_documentation_setup_rejects_executable_entry_file(correction_history: tuple[Path, str, str]) -> None:
    repository, _, _ = correction_history
    run_git(repository, "update-index", "--chmod=+x", "zensical.toml")
    source = create_test_commit(repository)

    with pytest.raises(ValueError, match="lacks required regular documentation files"):
        require_documentation_setup(repository, source)


def test_correction_source_rejects_baseline_without_documentation(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "v1.3.0", baseline)
    releases = [{"tag_name": "v1.3.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="lacks required regular documentation files"):
        require_correction_source(git_repository, "v1.3.0", baseline, releases)


def test_correction_source_rejects_deleted_landing_page(correction_history: tuple[Path, str, str]) -> None:
    repository, _, _ = correction_history
    (repository / "docs" / "index.md").unlink()
    source = commit_all(repository)
    run_git(repository, "update-ref", "refs/remotes/origin/docs/1.4.0", source)
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="lacks required regular documentation files"):
        require_correction_source(repository, "v1.4.0", source, releases)


def test_release_source_accepts_exact_tagged_commit(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, _ = correction_history
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    assert require_release_source(repository, "v1.4.0", baseline.upper(), releases) == baseline


@pytest.mark.parametrize("use_older_commit", [False, True])
def test_release_source_rejects_other_commits(
    correction_history: tuple[Path, str, str], use_older_commit: bool
) -> None:
    repository, baseline, correction = correction_history
    source = run_git(repository, "rev-parse", f"{baseline}^") if use_older_commit else correction
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="does not match release") as error:
        require_release_source(repository, "v1.4.0", source, releases)

    assert source in str(error.value)
    assert baseline in str(error.value)


def test_release_source_rejects_superseded_release(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, _ = correction_history
    releases = [
        {"tag_name": "v1.4.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.5.0", "draft": False, "prerelease": False},
    ]

    with pytest.raises(ValueError, match="is not the latest published stable release"):
        require_release_source(repository, "v1.4.0", baseline, releases)


def test_release_source_rejects_baseline_without_documentation(git_repository: Path) -> None:
    baseline = run_git(git_repository, "rev-parse", "HEAD")
    run_git(git_repository, "-c", "tag.gpgsign=false", "tag", "v1.3.0", baseline)
    releases = [{"tag_name": "v1.3.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="lacks required regular documentation files"):
        require_release_source(git_repository, "v1.3.0", baseline, releases)


@pytest.fixture
def bootstrap_history(git_repository: Path) -> tuple[Path, str]:
    docs = git_repository / "docs"
    docs.mkdir()
    (docs / "index.md").write_text(
        "# Expo Studio User Manual\n\nThe user manual is under construction.\n", encoding="utf-8"
    )
    return git_repository, commit_all(git_repository)


def test_bootstrap_content_accepts_committed_placeholder(bootstrap_history: tuple[Path, str]) -> None:
    repository, source = bootstrap_history
    (repository / "docs" / "index.md").write_text("Uncommitted content.\n", encoding="utf-8")

    assert require_bootstrap_content(repository, source) is None


@pytest.mark.parametrize("extra_path", ["guide.md", "assets/image.png", ".hidden.md"])
def test_bootstrap_content_rejects_additional_files(bootstrap_history: tuple[Path, str], extra_path: str) -> None:
    repository, _ = bootstrap_history
    extra = repository.joinpath("docs", *extra_path.split("/"))
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("Extra content.\n", encoding="utf-8")
    source = commit_all(repository)

    with pytest.raises(ValueError, match="must contain only the regular docs/index.md"):
        require_bootstrap_content(repository, source)


@pytest.mark.parametrize(
    "content",
    [
        "# Expo Studio User Manual\n\nActual feature instructions.\n",
        "# Expo Studio User Manual\n\nThe user manual is under construction.\n\n<script>alert(1)</script>",
        "# Expo Studio User Manual\n\nThe user manual is under construction.\n\n[Guide](guide.md)",
        "",
    ],
)
def test_bootstrap_content_rejects_unapproved_landing_text(bootstrap_history: tuple[Path, str], content: str) -> None:
    repository, _ = bootstrap_history
    (repository / "docs" / "index.md").write_text(content, encoding="utf-8")
    source = commit_all(repository)

    with pytest.raises(ValueError, match="approved under-construction heading and message"):
        require_bootstrap_content(repository, source)


def test_bootstrap_content_rejects_missing_docs(git_repository: Path) -> None:
    source = run_git(git_repository, "rev-parse", "HEAD")

    with pytest.raises(ValueError, match="must contain only the regular docs/index.md"):
        require_bootstrap_content(git_repository, source)


def test_bootstrap_content_rejects_executable_placeholder(bootstrap_history: tuple[Path, str]) -> None:
    repository, _ = bootstrap_history
    run_git(repository, "update-index", "--chmod=+x", "docs/index.md")
    source = create_test_commit(repository)

    with pytest.raises(ValueError, match="must contain only the regular docs/index.md"):
        require_bootstrap_content(repository, source)


BOOTSTRAP_CONFIGURATION = (
    '[project]\nsite_name = "Expo Studio User Manual"\n'
    'site_url = "https://jbm329.github.io/expo-studio/"\n'
    'docs_dir = "docs"\nsite_dir = "site"\n'
)


def test_bootstrap_configuration_accepts_committed_settings(correction_history: tuple[Path, str, str]) -> None:
    repository, _, _ = correction_history
    config = repository / "zensical.toml"
    config.write_text("# Bootstrap configuration\n" + BOOTSTRAP_CONFIGURATION, encoding="utf-8")
    source = commit_all(repository)
    config.write_text("invalid uncommitted TOML", encoding="utf-8")

    assert require_bootstrap_configuration(repository, source) is None


@pytest.mark.parametrize(
    "configuration",
    [
        BOOTSTRAP_CONFIGURATION.replace('docs_dir = "docs"', 'docs_dir = "src"'),
        BOOTSTRAP_CONFIGURATION.replace('site_dir = "site"', 'site_dir = "other"'),
        BOOTSTRAP_CONFIGURATION.replace("jbm329.github.io/expo-studio/", "example.invalid/"),
        BOOTSTRAP_CONFIGURATION.replace("Expo Studio User Manual", "Different manual"),
        BOOTSTRAP_CONFIGURATION.replace('docs_dir = "docs"\n', ""),
        BOOTSTRAP_CONFIGURATION + 'extra_javascript = ["remote.js"]\n',
        BOOTSTRAP_CONFIGURATION + '\n[project.theme]\ncustom_dir = "templates"\n',
        BOOTSTRAP_CONFIGURATION + '\n[unexpected]\nvalue = "extra"\n',
        "",
    ],
)
def test_bootstrap_configuration_rejects_unapproved_settings(
    correction_history: tuple[Path, str, str], configuration: str
) -> None:
    repository, _, _ = correction_history
    (repository / "zensical.toml").write_text(configuration, encoding="utf-8")
    source = commit_all(repository)

    with pytest.raises(ValueError, match="Bootstrap configuration must match"):
        require_bootstrap_configuration(repository, source)


def test_bootstrap_configuration_surfaces_invalid_toml(correction_history: tuple[Path, str, str]) -> None:
    repository, _, _ = correction_history
    (repository / "zensical.toml").write_text("[project", encoding="utf-8")
    source = commit_all(repository)

    with pytest.raises(tomllib.TOMLDecodeError):
        require_bootstrap_configuration(repository, source)


def test_bootstrap_configuration_requires_regular_config_file(correction_history: tuple[Path, str, str]) -> None:
    repository, _, _ = correction_history
    run_git(repository, "update-index", "--chmod=+x", "zensical.toml")
    source = create_test_commit(repository)

    with pytest.raises(ValueError, match="lacks required regular documentation files"):
        require_bootstrap_configuration(repository, source)


@pytest.fixture
def bootstrap_source_history(bootstrap_history: tuple[Path, str]) -> tuple[Path, str, str]:
    repository, placeholder = bootstrap_history
    baseline = run_git(repository, "rev-parse", f"{placeholder}^")
    run_git(repository, "-c", "tag.gpgsign=false", "tag", "v1.3.0", baseline)
    (repository / "zensical.toml").write_text(BOOTSTRAP_CONFIGURATION, encoding="utf-8")
    (repository / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (repository / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    source = commit_all(repository)
    run_git(repository, "update-ref", "refs/remotes/origin/main", source)
    return repository, baseline, source


def test_bootstrap_source_accepts_initial_publication(bootstrap_source_history: tuple[Path, str, str]) -> None:
    repository, baseline, source = bootstrap_source_history
    releases = [{"tag_name": "v1.3.0", "draft": False, "prerelease": False}]

    assert require_bootstrap_source(repository, "v1.3.0", source, releases) == baseline


def test_bootstrap_source_closes_after_docs_release(bootstrap_source_history: tuple[Path, str, str]) -> None:
    repository, _, source = bootstrap_source_history
    run_git(repository, "-c", "tag.gpgsign=false", "tag", "v1.4.0", source)
    releases = [{"tag_name": "v1.4.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="already contains site configuration"):
        require_bootstrap_source(repository, "v1.4.0", source, releases)


def test_bootstrap_source_rejects_unmerged_source(bootstrap_source_history: tuple[Path, str, str]) -> None:
    repository, _, _ = bootstrap_source_history
    source = create_test_commit(repository)
    releases = [{"tag_name": "v1.3.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_bootstrap_source(repository, "v1.3.0", source, releases)


@pytest.mark.parametrize("change_config", [False, True])
def test_bootstrap_source_enforces_content_and_configuration(
    bootstrap_source_history: tuple[Path, str, str], change_config: bool
) -> None:
    repository, _, _ = bootstrap_source_history
    if change_config:
        (repository / "zensical.toml").write_text('[project]\ndocs_dir = "src"\n', encoding="utf-8")
    else:
        (repository / "docs" / "guide.md").write_text("Unreleased guide.\n", encoding="utf-8")
    source = commit_all(repository)
    run_git(repository, "update-ref", "refs/remotes/origin/main", source)
    releases = [{"tag_name": "v1.3.0", "draft": False, "prerelease": False}]

    with pytest.raises(ValueError, match="Bootstrap"):
        require_bootstrap_source(repository, "v1.3.0", source, releases)


def test_bootstrap_source_rejects_superseded_baseline(bootstrap_source_history: tuple[Path, str, str]) -> None:
    repository, _, source = bootstrap_source_history
    releases = [
        {"tag_name": "v1.3.0", "draft": False, "prerelease": False},
        {"tag_name": "v1.4.0", "draft": False, "prerelease": False},
    ]

    with pytest.raises(ValueError, match="is not the latest published stable release"):
        require_bootstrap_source(repository, "v1.3.0", source, releases)


def test_publication_progress_accepts_identical_retry(correction_history: tuple[Path, str, str]) -> None:
    repository, _, source = correction_history

    assert require_publication_progress(repository, "v1.4.0", source, "v1.4.0", source) is None


def test_publication_progress_accepts_newer_correction(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, source = correction_history

    assert require_publication_progress(repository, "v1.4.0", baseline, "v1.4.0", source) is None


def test_publication_progress_rejects_release_rerun_after_correction(
    correction_history: tuple[Path, str, str],
) -> None:
    repository, baseline, correction = correction_history

    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_publication_progress(repository, "v1.4.0", correction, "v1.4.0", baseline)


def test_publication_progress_rejects_divergent_correction(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, correction = correction_history
    run_git(repository, "checkout", "--quiet", "--detach", baseline)
    divergent = create_test_commit(repository, "Alternative correction history")

    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_publication_progress(repository, "v1.4.0", correction, "v1.4.0", divergent)


def test_publication_progress_accepts_new_application_version(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, correction = correction_history

    assert require_publication_progress(repository, "v1.9.0", correction, "v1.10.0", baseline) is None


def test_publication_progress_rejects_older_application_version(correction_history: tuple[Path, str, str]) -> None:
    repository, baseline, correction = correction_history

    with pytest.raises(ValueError, match="would replace the newer published manual"):
        require_publication_progress(repository, "v1.10.0", baseline, "v1.9.0", correction)


def test_publication_progress_surfaces_missing_published_commit(correction_history: tuple[Path, str, str]) -> None:
    repository, _, source = correction_history

    with pytest.raises(subprocess.CalledProcessError):
        require_publication_progress(repository, "v1.4.0", "0" * 40, "v1.4.0", source)


@pytest.mark.parametrize("published_mode", ["release", "correction"])
def test_manifest_progress_prevents_bootstrap_after_released_manual(
    correction_history: tuple[Path, str, str],
    publication_manifest: dict[str, object],
    published_mode: str,
) -> None:
    repository, _, source = correction_history
    published = parse_publication_manifest({
        **publication_manifest,
        "mode": published_mode,
        "source_sha": source,
    })
    proposed = parse_publication_manifest({
        **published,
        "mode": "bootstrap",
        "baseline_tag": "v1.5.0",
        "run_id": "999999999",
    })

    with pytest.raises(ValueError, match="Bootstrap cannot replace"):
        require_manifest_progress(repository, published, proposed)


def test_manifest_progress_accepts_bootstrap_to_new_release(
    correction_history: tuple[Path, str, str], publication_manifest: dict[str, object]
) -> None:
    repository, baseline, source = correction_history
    published = parse_publication_manifest({
        **publication_manifest,
        "mode": "bootstrap",
        "baseline_tag": "v1.3.0",
        "source_sha": baseline,
    })
    proposed = parse_publication_manifest({**publication_manifest, "source_sha": source})

    assert require_manifest_progress(repository, published, proposed) is None


def test_manifest_progress_allows_identical_bootstrap_retry(
    correction_history: tuple[Path, str, str], publication_manifest: dict[str, object]
) -> None:
    repository, _, source = correction_history
    published = parse_publication_manifest({
        **publication_manifest,
        "mode": "bootstrap",
        "source_sha": source,
    })
    proposed = parse_publication_manifest({**published, "run_id": "1"})

    assert require_manifest_progress(repository, published, proposed) is None


def test_manifest_progress_rejects_stale_correction_despite_newer_run_id(
    correction_history: tuple[Path, str, str], publication_manifest: dict[str, object]
) -> None:
    repository, baseline, source = correction_history
    published = parse_publication_manifest({
        **publication_manifest,
        "mode": "correction",
        "source_sha": source,
    })
    proposed = parse_publication_manifest({
        **published,
        "source_sha": baseline,
        "run_id": "999999999",
    })

    with pytest.raises(ValueError, match="is not an ancestor of"):
        require_manifest_progress(repository, published, proposed)

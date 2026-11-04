"""Validate sources and release eligibility for documentation publication."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import tomllib
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal, TypedDict
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from collections.abc import Sequence


class GitHubRelease(TypedDict):
    """Release metadata required for stable-version selection."""

    tag_name: str
    draft: bool
    prerelease: bool


def parse_github_releases(value: object) -> list[GitHubRelease]:
    """Validate a decoded GitHub release-list response.

    Args:
        value: JSON-decoded release list from one API page or combined pages.

    Returns:
        Release metadata containing only fields used by publication policy.

    Raises:
        TypeError: If the response is not a list of correctly typed releases.

    Notes:
        Additional API fields are ignored. Unsupported tag formats are retained
        for the stable-release filter, not treated as malformed API data.
    """
    if not isinstance(value, list):
        message = "GitHub release response must be a list."
        raise TypeError(message)
    releases: list[GitHubRelease] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            message = f"GitHub release at index {index} must be an object."
            raise TypeError(message)
        tag = entry.get("tag_name")
        draft = entry.get("draft")
        prerelease = entry.get("prerelease")
        if not isinstance(tag, str) or not isinstance(draft, bool) or not isinstance(prerelease, bool):
            message = f"GitHub release at index {index} requires a string tag_name and boolean draft/prerelease flags."
            raise TypeError(message)
        releases.append({"tag_name": tag, "draft": draft, "prerelease": prerelease})
    return releases


def fetch_github_releases(repository_slug: str) -> list[GitHubRelease]:
    """Fetch and validate every release page through the authenticated GitHub CLI.

    Args:
        repository_slug: GitHub repository identifier in owner/repository form.

    Returns:
        Validated release metadata from all response pages.

    Raises:
        ValueError: If the repository identifier or JSON response is invalid.
        TypeError: If response pages contain incorrectly typed release metadata.
        subprocess.CalledProcessError: If the API request or CLI authentication fails.
        OSError: If the GitHub CLI cannot be started.

    Notes:
        The caller configures GitHub CLI authentication, normally with GH_TOKEN.
        CLI failures are propagated rather than returning an empty release list.
    """
    releases: list[GitHubRelease] = []
    for page in _fetch_github_list_pages(repository_slug, "releases"):
        releases.extend(parse_github_releases(page))
    return releases


def _require_repository_slug(repository_slug: str) -> None:
    """Require a plain GitHub owner/repository identifier."""
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repository_slug) is None:
        message = "Expected a GitHub repository identifier in owner/repository form."
        raise ValueError(message)


def _fetch_github_list_pages(
    repository_slug: str, resource: Literal["releases", "deployments"], *, deployment_id: int | None = None
) -> list[object]:
    """Fetch paginated release, Pages deployment, or deployment status lists."""
    _require_repository_slug(repository_slug)
    query = "per_page=100"
    if deployment_id is not None:
        if resource != "deployments" or type(deployment_id) is not int or deployment_id <= 0:
            message = "Deployment statuses require a positive integer deployment ID."
            raise ValueError(message)
        endpoint = f"deployments/{deployment_id}/statuses"
    else:
        endpoint = resource
    if resource == "deployments" and deployment_id is None:
        query += "&environment=github-pages"
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "gh",
            "api",
            "--method",
            "GET",
            "--paginate",
            "--slurp",
            f"repos/{repository_slug}/{endpoint}?{query}",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    pages = json.loads(result.stdout)
    if not isinstance(pages, list):
        message = f"Paginated GitHub {resource} response must be a list of pages."
        raise TypeError(message)
    return pages


class GitHubPagesDeployment(TypedDict):
    """GitHub deployment identity; its SHA is not necessarily the manual source."""

    id: int
    sha: str


def fetch_pages_deployments(repository_slug: str) -> list[GitHubPagesDeployment]:
    """Retrieve all github-pages deployment records through the authenticated CLI.

    Args:
        repository_slug: GitHub repository identifier in owner/repository form.

    Returns:
        Deployment IDs and commit SHAs, without assuming API ordering or success.
        An empty list means the successful query returned no deployment records.

    Raises:
        ValueError: If the repository identifier, JSON, or deployment SHA is invalid.
        TypeError: If deployment metadata has an invalid shape, ID, or environment.
        subprocess.CalledProcessError: If the API request or authentication fails.
        OSError: If the GitHub CLI cannot be started.

    Notes:
        The caller needs deployments: read permission and GH_TOKEN. Records
        include failed and pending deployments; inspect statuses separately.
        The SHA can identify the trusted workflow rather than the manual source.
        Empty history alone does not authorize bootstrap or prove a site never
        existed, since deployment records can be deleted.
    """
    deployments: list[GitHubPagesDeployment] = []
    for page in _fetch_github_list_pages(repository_slug, "deployments"):
        if not isinstance(page, list):
            message = "GitHub deployment response page must be a list."
            raise TypeError(message)
        for entry in page:
            if not isinstance(entry, dict):
                message = "GitHub deployment entry must be an object."
                raise TypeError(message)
            deployment_id = entry.get("id")
            sha = entry.get("sha")
            if type(deployment_id) is not int or deployment_id <= 0 or not isinstance(sha, str):
                message = "GitHub deployment requires a positive integer ID and string SHA."
                raise TypeError(message)
            if entry.get("environment") != "github-pages":
                message = "GitHub deployment must belong to the github-pages environment."
                raise TypeError(message)
            deployments.append({"id": deployment_id, "sha": validate_commit_sha(sha)})
    return deployments


class GitHubDeploymentStatus(TypedDict):
    """Status identity and reported workflow log location, not verified provenance."""

    id: int
    state: Literal["error", "failure", "inactive", "in_progress", "queued", "pending", "success"]
    log_url: str
    created_at: str


def _parse_status_timestamp(value: str) -> datetime:
    """Parse the UTC timestamp format returned by GitHub deployment statuses."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def latest_deployment_status(statuses: Sequence[GitHubDeploymentStatus]) -> GitHubDeploymentStatus:
    """Select the uniquely latest status from validated GitHub metadata.

    Args:
        statuses: Validated status records, in any response order.

    Returns:
        The record with the most recent creation timestamp.

    Raises:
        ValueError: If no statuses exist, a timestamp is invalid, or the latest
            timestamp is shared by distinct records.

    Notes:
        GitHub timestamps have second precision. Ambiguous latest records fail
        rather than guessing chronology from IDs or preferring success.
        Identical duplicate records from pagination do not create ambiguity.
    """
    if not statuses:
        message = "Cannot establish deployment state without status records."
        raise ValueError(message)
    latest = max(statuses, key=lambda status: _parse_status_timestamp(status["created_at"]))
    timestamp = _parse_status_timestamp(latest["created_at"])
    if any(_parse_status_timestamp(status["created_at"]) == timestamp and status != latest for status in statuses):
        message = "Latest deployment status is ambiguous: distinct records share its timestamp."
        raise ValueError(message)
    return latest


def fetch_deployment_statuses(repository_slug: str, deployment_id: int) -> list[GitHubDeploymentStatus]:
    """Retrieve and validate every status page for a GitHub deployment.

    Args:
        repository_slug: GitHub repository identifier in owner/repository form.
        deployment_id: Positive integer ID from the Pages deployment history.

    Returns:
        Status records without assuming response order. An empty list means no
        statuses were returned, not that the deployment succeeded.

    Raises:
        ValueError: If the repository identifier, deployment ID, JSON, state, or timestamp is invalid.
        TypeError: If status entries, IDs, log URLs, or timestamps have invalid types.
        subprocess.CalledProcessError: If the API request or authentication fails.
        OSError: If the GitHub CLI cannot be started.

    Notes:
        The caller needs deployments: read permission and GH_TOKEN. Historical
        success does not establish the deployment's current state. Log URLs are
        returned as metadata only; they are not fetched or trusted as evidence
        of workflow identity without further verification.
    """
    if type(deployment_id) is not int or deployment_id <= 0:
        message = "Deployment statuses require a positive integer deployment ID."
        raise ValueError(message)
    statuses: list[GitHubDeploymentStatus] = []
    for page in _fetch_github_list_pages(repository_slug, "deployments", deployment_id=deployment_id):
        if not isinstance(page, list):
            message = "GitHub deployment status page must be a list."
            raise TypeError(message)
        for entry in page:
            if not isinstance(entry, dict):
                message = "GitHub deployment status entry must be an object."
                raise TypeError(message)
            status_id = entry.get("id")
            state = entry.get("state")
            log_url = entry.get("log_url")
            created_at = entry.get("created_at")
            if type(status_id) is not int or status_id <= 0 or not isinstance(log_url, str):
                message = "GitHub deployment status requires a positive integer ID and string log_url."
                raise TypeError(message)
            if state not in ("error", "failure", "inactive", "in_progress", "queued", "pending", "success"):
                message = "Unsupported GitHub deployment status state."
                raise ValueError(message)
            if not isinstance(created_at, str):
                message = "GitHub deployment status requires a string created_at timestamp."
                raise TypeError(message)
            _parse_status_timestamp(created_at)
            statuses.append({"id": status_id, "state": state, "log_url": log_url, "created_at": created_at})
    return statuses


def fetch_current_pages_deployment(
    repository_slug: str,
) -> tuple[GitHubPagesDeployment, GitHubDeploymentStatus] | None:
    """Find the unique currently successful Pages deployment and its status.

    Args:
        repository_slug: GitHub repository identifier in owner/repository form.

    Returns:
        The deployment and latest success status, or None only when the
        deployment-history query returned no records.

    Raises:
        ValueError: If status history is missing or ambiguous, an attempt is
            unfinished, deployment IDs repeat, or existing history does not
            identify exactly one currently successful deployment.
        TypeError: If API metadata is malformed.
        subprocess.CalledProcessError: If a GitHub API request fails.
        OSError: If the GitHub CLI cannot be started.

    Notes:
        Failed and inactive attempts do not replace a current success. No
        records is not authorization for bootstrap. These separate API reads
        are not atomic; deployment serialization and final rechecks are still
        required. Call before creating the proposed deployment record.
    """
    deployments = fetch_pages_deployments(repository_slug)
    if not deployments:
        return None
    seen: set[int] = set()
    current: tuple[GitHubPagesDeployment, GitHubDeploymentStatus] | None = None
    for deployment in deployments:
        deployment_id = deployment["id"]
        if deployment_id in seen:
            message = "Repeated Pages deployment ID prevents an unambiguous history check."
            raise ValueError(message)
        seen.add(deployment_id)
        status = latest_deployment_status(fetch_deployment_statuses(repository_slug, deployment_id))
        if status["state"] in ("queued", "pending", "in_progress"):
            message = f"Pages deployment {deployment_id} is unfinished; retry after it completes."
            raise ValueError(message)
        if status["state"] == "success":
            if current is not None:
                message = "Multiple currently successful Pages deployments prevent authoritative selection."
                raise ValueError(message)
            current = deployment, status
    if current is None:
        message = "Existing Pages deployment history has no currently successful deployment."
        raise ValueError(message)
    return current


def refresh_publication_refs(repository: Path) -> None:
    """Fetch current origin branches and tags in a full-history workflow checkout.

    Args:
        repository: Dedicated workflow checkout with an origin remote.

    Raises:
        ValueError: If the checkout is shallow or Git reports unexpected state.
        subprocess.CalledProcessError: If repository inspection or fetching fails.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        Use checkout with fetch-depth: 0. This updates and prunes local refs,
        including tags, but does not check out files or alter branch history.
        Conflicting moved tags fail rather than being force-updated.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != "false":
        message = "Publication validation requires a full-history checkout (fetch-depth: 0)."
        raise ValueError(message)
    subprocess.run(
        [  # noqa: S607
            "git",
            "fetch",
            "--prune",
            "--no-recurse-submodules",
            "origin",
            "+refs/heads/*:refs/remotes/origin/*",
            "refs/tags/*:refs/tags/*",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


class PublicationManifest(TypedDict):
    """Versioned provenance stored alongside the published website."""

    schema_version: int
    mode: Literal["bootstrap", "release", "correction"]
    baseline_tag: str
    source_sha: str
    run_id: str


def parse_publication_manifest(value: object) -> PublicationManifest:
    """Validate publication provenance decoded from JSON.

    Args:
        value: Decoded JSON content of the publication manifest.

    Returns:
        Validated metadata with a normalized source commit ID.

    Raises:
        ValueError: If the manifest schema or any metadata field is invalid.

    Notes:
        A bootstrap baseline identifies the existing app release, not a claim
        that the placeholder documents that release. Metadata alone does not
        establish a successful deployment or commit eligibility.
    """
    required = {"schema_version", "mode", "baseline_tag", "source_sha", "run_id"}
    if not isinstance(value, dict) or set(value) != required:
        message = "Publication manifest must contain exactly the supported provenance fields."
        raise ValueError(message)
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        message = "Unsupported publication manifest schema version."
        raise ValueError(message)
    mode = value["mode"]
    if mode not in ("bootstrap", "release", "correction"):
        message = "Unsupported publication manifest mode."
        raise ValueError(message)
    baseline = value["baseline_tag"]
    source = value["source_sha"]
    run_id = value["run_id"]
    if not isinstance(baseline, str) or not isinstance(source, str):
        message = "Publication manifest baseline and source must be strings."
        raise ValueError(message)  # noqa: TRY004 - Invalid decoded manifest data uses one validation error type.
    parse_stable_tag(baseline)
    source = validate_commit_sha(source)
    if not isinstance(run_id, str) or re.fullmatch(r"[1-9][0-9]*", run_id) is None:
        message = "Publication manifest run ID must be a positive decimal string."
        raise ValueError(message)
    return {
        "schema_version": 1,
        "mode": mode,
        "baseline_tag": baseline,
        "source_sha": source,
        "run_id": run_id,
    }


def require_deployment_run(repository_slug: str, status: GitHubDeploymentStatus, manifest: PublicationManifest) -> None:
    """Require a successful deployment status to reference the manifest's run.

    Args:
        repository_slug: Expected GitHub owner/repository identifier.
        status: Validated latest status of the selected Pages deployment.
        manifest: Public publication metadata to validate and associate.

    Raises:
        ValueError: If the repository or manifest is invalid, the status is not
            successful, or its log URL does not identify the expected run.

    Notes:
        Accepts canonical HTTPS Actions run links with an optional job suffix.
        This checks association only. Status log URLs are supplied metadata,
        not proof of a trusted workflow, successful run, artifact contents, or
        matching run attempt. Those require independent GitHub verification.
    """
    _require_repository_slug(repository_slug)
    validated = parse_publication_manifest(manifest)
    if status["state"] != "success":
        message = "Published provenance requires a successful deployment status."
        raise ValueError(message)
    expected = re.escape(f"https://github.com/{repository_slug}/actions/runs/{validated['run_id']}")
    if re.fullmatch(expected + r"(?:/job/[1-9][0-9]*)?", status["log_url"]) is None:
        message = "Deployment log URL does not match the publication repository and workflow run."
        raise ValueError(message)


def require_manual_publication_run(
    repository_slug: str,
    deployment: GitHubPagesDeployment,
    manifest: PublicationManifest,
) -> int:
    """Verify manual publishing run metadata through the GitHub Actions API.

    Args:
        repository_slug: Expected GitHub owner/repository identifier.
        deployment: Selected Pages deployment with its workflow commit SHA.
        manifest: Public publication metadata identifying the workflow run.

    Returns:
        The API's current positive run-attempt number, for further verification.

    Raises:
        ValueError: If metadata does not identify a completed successful manual
            publishing run from main at the deployment's workflow commit.
        TypeError: If the API response is not a workflow run object.
        subprocess.CalledProcessError: If the API request or authentication fails.
        OSError: If the GitHub CLI cannot be started.

    Notes:
        Requires actions: read and GH_TOKEN. This checks API metadata, not
        workflow file contents, the deployment's exact run attempt, or artifact
        contents. A rerun may change the API's current attempt. Automatic
        release publishing is deliberately not accepted by this manual check.
    """
    _require_repository_slug(repository_slug)
    validated = parse_publication_manifest(manifest)
    workflow_sha = validate_commit_sha(deployment["sha"])
    if validated["mode"] == "release":
        message = "Manual publishing run verification does not accept automatic release provenance."
        raise ValueError(message)
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "gh",
            "api",
            "--method",
            "GET",
            f"repos/{repository_slug}/actions/runs/{validated['run_id']}",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    run = json.loads(result.stdout)
    if not isinstance(run, dict):
        message = "GitHub workflow run response must be an object."
        raise TypeError(message)
    expected = {
        "id": int(validated["run_id"]),
        "path": ".github/workflows/publish-docs.yml",
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": workflow_sha,
        "status": "completed",
        "conclusion": "success",
    }
    if type(run.get("id")) is not int or any(run.get(key) != value for key, value in expected.items()):
        message = "GitHub run does not match the successful manual publishing workflow and deployment commit."
        raise ValueError(message)
    for field in ("repository", "head_repository"):
        repository = run.get(field)
        if not isinstance(repository, dict) or repository.get("full_name") != repository_slug:
            message = "GitHub publishing run must belong to and use source from the expected repository."
            raise ValueError(message)
    attempt = run.get("run_attempt")
    if type(attempt) is not int or attempt <= 0:
        message = "GitHub publishing run requires a positive integer run_attempt."
        raise ValueError(message)
    return attempt


def require_publication_job(
    repository_slug: str,
    status: GitHubDeploymentStatus,
    manifest: PublicationManifest,
    run_attempt: int,
) -> None:
    """Associate a deployment success with the publishing job in a run attempt.

    Args:
        repository_slug: Expected GitHub owner/repository identifier.
        status: Validated success status from the selected Pages deployment.
        manifest: Publication metadata identifying the previously checked run.
        run_attempt: Positive attempt number returned by run verification.

    Raises:
        ValueError: If identifiers, job metadata, or timing do not match.
        TypeError: If the API response is not a paginated jobs response or job
            timestamps are not strings.
        subprocess.CalledProcessError: If the API request or authentication fails.
        OSError: If the GitHub CLI cannot be started.

    Notes:
        Requires actions: read and GH_TOKEN. The deployment job must be named
        "Deploy documentation". A job-specific log URL must match that job;
        run-only URLs rely on the success timestamp falling within its execution.
        This is a metadata cross-check, not proof of artifact contents.
    """
    require_deployment_run(repository_slug, status, manifest)
    if type(run_attempt) is not int or run_attempt <= 0:
        message = "Publication job verification requires a positive integer run attempt."
        raise ValueError(message)
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "gh",
            "api",
            "--method",
            "GET",
            "--paginate",
            "--slurp",
            f"repos/{repository_slug}/actions/runs/{manifest['run_id']}/attempts/{run_attempt}/jobs?per_page=100",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    pages = json.loads(result.stdout)
    if not isinstance(pages, list):
        message = "GitHub jobs response must be a list of pages."
        raise TypeError(message)
    matching: list[dict[str, object]] = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("jobs"), list):
            message = "GitHub jobs response page requires a jobs list."
            raise TypeError(message)
        for job in page["jobs"]:
            if not isinstance(job, dict) or not isinstance(job.get("name"), str):
                message = "GitHub job requires an object with a string name."
                raise TypeError(message)
            if job["name"] == "Deploy documentation":
                matching.append(job)
    if len(matching) != 1:
        message = "Run attempt must contain exactly one Deploy documentation job."
        raise ValueError(message)
    job = matching[0]
    job_id = job.get("id")
    expected = {
        "run_id": int(manifest["run_id"]),
        "run_attempt": run_attempt,
        "status": "completed",
        "conclusion": "success",
    }
    if (
        type(job_id) is not int
        or job_id <= 0
        or type(job.get("run_id")) is not int
        or type(job.get("run_attempt")) is not int
        or any(job.get(key) != value for key, value in expected.items())
    ):
        message = "Deployment job must be successful and belong to the verified run attempt."
        raise ValueError(message)
    run_url = f"https://github.com/{repository_slug}/actions/runs/{manifest['run_id']}"
    if status["log_url"] not in (run_url, f"{run_url}/job/{job_id}"):
        message = "Deployment status links to a different job."
        raise ValueError(message)
    started = job.get("started_at")
    completed = job.get("completed_at")
    if not isinstance(started, str) or not isinstance(completed, str):
        message = "Deployment job requires start and completion timestamps."
        raise TypeError(message)
    timestamp = _parse_status_timestamp(status["created_at"])
    if not _parse_status_timestamp(started) <= timestamp <= _parse_status_timestamp(completed):
        message = "Deployment success timestamp is outside the verified job execution window."
        raise ValueError(message)


def fetch_manual_publication_metadata(repository_slug: str) -> PublicationManifest | None:
    """Retrieve public manual provenance and cross-check its deployment metadata.

    Args:
        repository_slug: Expected GitHub owner/repository identifier.

    Returns:
        Public provenance associated with the selected manual publishing run,
        or None only when the initial deployment query returns no records.

    Raises:
        ValueError: If metadata checks fail or the selected deployment changes.
        TypeError: If GitHub API metadata is malformed.
        subprocess.CalledProcessError: If a GitHub API request fails.
        OSError: If an API command or public website request fails.
        UnicodeDecodeError: If public provenance is not valid UTF-8.

    Notes:
        None does not authorize bootstrap. This composes metadata checks only,
        not artifact or workflow-content verification. Reads are not atomic;
        rechecking the selected deployment detects changes during inspection,
        but deployment serialization and final eligibility checks remain needed.
        Automatic release provenance is not accepted by this manual-only path.
    """
    current = fetch_current_pages_deployment(repository_slug)
    if current is None:
        return None
    deployment, status = current
    manifest = fetch_published_manifest()
    require_deployment_run(repository_slug, status, manifest)
    attempt = require_manual_publication_run(repository_slug, deployment, manifest)
    require_publication_job(repository_slug, status, manifest, attempt)
    if fetch_current_pages_deployment(repository_slug) != current:
        message = "Pages deployment changed during provenance inspection; retry against current state."
        raise ValueError(message)
    return manifest


def prepare_publication(
    repository: Path,
    repository_slug: str,
    request: PublicationManifest,
) -> PublicationManifest:
    """Refresh release information and validate a publication source by mode.

    Args:
        repository: Dedicated full-history workflow checkout.
        repository_slug: GitHub repository identifier in owner/repository form.
        request: Proposed publication provenance, validated before fetching.

    Returns:
        Validated provenance for the eligible source commit.

    Raises:
        ValueError: If request metadata or source eligibility is invalid.
        TypeError: If GitHub release metadata is malformed.
        subprocess.CalledProcessError: If Git or GitHub CLI operations fail.
        OSError: If required commands or repository files are unavailable.
        UnicodeDecodeError: If source text is not valid UTF-8.

    Notes:
        This does not build, write files, check deployed provenance, or deploy.
        Release mode still requires a trusted caller enforcing release success.
    """
    manifest = parse_publication_manifest(request)
    refresh_publication_refs(repository)
    releases = fetch_github_releases(repository_slug)
    validators = {
        "bootstrap": require_bootstrap_source,
        "release": require_release_source,
        "correction": require_correction_source,
    }
    validators[manifest["mode"]](
        repository,
        manifest["baseline_tag"],
        manifest["source_sha"],
        releases,
    )
    return manifest


def read_publication_manifest(path: Path) -> PublicationManifest:
    """Read and validate a UTF-8 JSON publication manifest.

    Args:
        path: Local manifest file to read.

    Returns:
        Validated publication provenance.

    Raises:
        ValueError: If JSON or publication metadata is invalid.
        OSError: If the manifest cannot be read, including when it is missing.
        UnicodeDecodeError: If the file is not valid UTF-8.
    """
    return parse_publication_manifest(json.loads(path.read_text(encoding="utf-8")))


def fetch_published_manifest() -> PublicationManifest:
    """Read provenance from the fixed public documentation website.

    Returns:
        Structurally validated metadata served by the public website.

    Raises:
        ValueError: If the response status, destination, size, JSON, or metadata is invalid.
        OSError: If the HTTPS request fails, including HTTP errors and timeouts.
        UnicodeDecodeError: If response content is not valid UTF-8.

    Notes:
        Missing content is an error, not evidence of a first deployment.
        A unique query and no-cache header request fresh data. This does not
        authenticate deployment history or guarantee CDN consistency; callers
        must independently verify provenance before authorizing a deployment.
    """
    url = f"https://jbm329.github.io/expo-studio/publication.json?check={secrets.token_hex(16)}"
    request = Request(url, headers={"Accept": "application/json", "Cache-Control": "no-cache"})
    maximum_size = 65_536
    with urlopen(request, timeout=30) as response:  # noqa: S310 - Fixed HTTPS destination, not caller input.
        if response.status != HTTPStatus.OK or response.geturl() != url:
            message = "Published provenance requires HTTP 200 from the expected website without redirection."
            raise ValueError(message)
        content = response.read(maximum_size + 1)
    if len(content) > maximum_size:
        message = "Published provenance exceeds the 64 KiB response limit."
        raise ValueError(message)
    return parse_publication_manifest(json.loads(content.decode("utf-8")))


def write_publication_manifest(path: Path, manifest: PublicationManifest) -> None:
    """Validate and write deterministic UTF-8 JSON publication provenance.

    Args:
        path: Output manifest file in an existing directory.
        manifest: Publication provenance to validate and serialize.

    Raises:
        ValueError: If the publication metadata is invalid.
        OSError: If the manifest cannot be written.
    """
    validated = parse_publication_manifest(manifest)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def require_site_manifest(site: Path, expected: PublicationManifest) -> None:
    """Check built-site metadata against the independently validated proposal.

    Args:
        site: Extracted website directory in a dedicated artifact location.
        expected: Validated provenance supplied separately from the website.

    Raises:
        ValueError: If required output is not regular, the landing page is empty,
            or website provenance differs from the proposal.
        OSError: If required files cannot be inspected or read.
        UnicodeDecodeError: If provenance is not valid UTF-8.

    Notes:
        Does not execute website content. Matching metadata does not prove all
        website bytes came from that source; artifact identity and trusted
        build/deployment wiring must be checked separately.
    """
    manifest = parse_publication_manifest(expected)
    if site.is_symlink() or not site.is_dir():
        message = "Publication artifact requires a regular website directory."
        raise ValueError(message)
    for name in ("index.html", "publication.json"):
        path = site / name
        if path.is_symlink() or not path.is_file():
            message = f"Publication artifact requires a regular {name} file."
            raise ValueError(message)
    if (site / "index.html").stat().st_size == 0:
        message = "Publication artifact landing page must not be empty."
        raise ValueError(message)
    if read_publication_manifest(site / "publication.json") != manifest:
        message = "Website publication metadata does not match the validated proposal."
        raise ValueError(message)


def parse_stable_tag(tag: str) -> tuple[int, int, int]:
    """Parse a stable application release tag for numeric comparison.

    Args:
        tag: Release tag in vMAJOR.MINOR.PATCH format.

    Returns:
        Numeric major, minor, and patch components.

    Raises:
        ValueError: If the tag is not a supported stable release tag.
    """
    match = re.fullmatch(
        r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        tag,
    )
    if match is None:
        message = f"Unsupported stable release tag: {tag!r}"
        raise ValueError(message)

    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def require_correction_changes(repository: Path, baseline_sha: str, source_sha: str) -> None:
    """Require the net changes from a release baseline to contain only manual files.

    Args:
        repository: Working directory of the checked-out repository.
        baseline_sha: Full commit ID of the stable release baseline.
        source_sha: Full commit ID of the proposed corrected documentation.

    Raises:
        ValueError: If ancestry fails or a changed file is outside correction scope.
        subprocess.CalledProcessError: If Git cannot inspect the commits or diff.
        OSError: If Git cannot be started or the working directory is invalid.
        UnicodeDecodeError: If a changed path is not valid UTF-8.

    Notes:
        Checks the complete tree difference, not only the most recent commit.
        Renames are inspected as a deletion and an addition.
    """
    baseline = validate_commit_sha(baseline_sha)
    source = validate_commit_sha(source_sha)
    require_ancestor(repository, baseline, source)
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "git",
            "--no-replace-objects",
            "diff",
            "--raw",
            "--no-abbrev",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "-z",
            baseline,
            source,
            "--",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    fields = result.stdout.split(b"\0")
    for index in range(0, len(fields) - 1, 2):
        metadata = fields[index].decode("ascii").split()
        path = fields[index + 1].decode("utf-8")
        for mode in (metadata[0].removeprefix(":"), metadata[1]):
            if mode != "000000":
                require_correction_file(path, mode)


def is_stable_release(
    tag: str,
    *,
    draft: bool,
    prerelease: bool,
) -> bool:
    """Return whether a GitHub release is eligible for stable-version selection.

    Args:
        tag: Release tag reported by GitHub.
        draft: Whether GitHub marks the release as a draft.
        prerelease: Whether GitHub marks the release as a prerelease.

    Returns:
        True for a published stable release with a supported tag format.
    """
    if draft or prerelease:
        return False

    try:
        parse_stable_tag(tag)
    except ValueError:
        # Unsupported tags are excluded when filtering GitHub releases.
        return False

    return True


def latest_stable_tag(releases: Sequence[GitHubRelease]) -> str:
    """Select the numerically newest published stable release tag.

    Args:
        releases: Release metadata, in any order, collected from GitHub.

    Returns:
        The highest supported stable release tag.

    Raises:
        ValueError: If no supported published stable release is available.
    """
    eligible_tags = [
        release["tag_name"]
        for release in releases
        if is_stable_release(
            release["tag_name"],
            draft=release["draft"],
            prerelease=release["prerelease"],
        )
    ]
    if not eligible_tags:
        message = "No supported published stable release is available."
        raise ValueError(message)

    return max(eligible_tags, key=parse_stable_tag)


def require_latest_stable_tag(expected_tag: str, releases: Sequence[GitHubRelease]) -> None:
    """Require the requested baseline to match the newest stable release.

    Args:
        expected_tag: Stable release tag the caller intends to document.
        releases: Release metadata collected from GitHub.

    Raises:
        ValueError: If the requested tag is unsupported, no stable release is
            available, or the requested tag is not the newest stable release.
    """
    parse_stable_tag(expected_tag)
    latest_tag = latest_stable_tag(releases)
    if expected_tag != latest_tag:
        message = f"Requested release {expected_tag!r} is not the latest published stable release {latest_tag!r}."
        raise ValueError(message)


def validate_commit_sha(source_sha: str) -> str:
    """Validate a full SHA-1 commit ID and normalize its hexadecimal casing.

    Args:
        source_sha: Explicit source commit ID supplied for publication.

    Returns:
        The lowercase, 40-character hexadecimal commit ID.

    Raises:
        ValueError: If the input is not a full SHA-1 object ID.

    Notes:
        This checks syntax only, not whether the object exists or is a commit.
    """
    if re.fullmatch(r"[0-9a-fA-F]{40}", source_sha) is None:
        message = f"Expected a full 40-character hexadecimal commit SHA: {source_sha!r}"
        raise ValueError(message)

    return source_sha.lower()


def require_commit(repository: Path, source_sha: str) -> str:
    """Require a full object ID to identify a local Git commit.

    Args:
        repository: Working directory of the checked-out repository.
        source_sha: Explicit source commit ID supplied for publication.

    Returns:
        The validated lowercase commit ID.

    Raises:
        ValueError: If the SHA format is invalid or the object is not a commit.
        subprocess.CalledProcessError: If Git cannot inspect the object.
        OSError: If Git cannot be started or the working directory is invalid.
    """
    commit_sha = validate_commit_sha(source_sha)
    # The command is fixed and its only input argument is a validated object ID.
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "cat-file", "-t", commit_sha],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != "commit":
        message = f"Publication source {commit_sha!r} is not a Git commit."
        raise ValueError(message)

    return commit_sha


def resolve_stable_tag_commit(repository: Path, tag: str) -> str:
    """Resolve an exact stable release tag to its underlying commit.

    Args:
        repository: Working directory of the checked-out repository.
        tag: Stable release tag in vMAJOR.MINOR.PATCH format.

    Returns:
        The lowercase commit ID, peeling annotated tags when necessary.

    Raises:
        ValueError: If the tag format is unsupported.
        subprocess.CalledProcessError: If the exact tag is missing, does not
            resolve to a commit, or Git cannot inspect it.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        The caller must fetch the release tags before resolving them.
        A local tag does not establish that a GitHub Release was published.
    """
    parse_stable_tag(tag)
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return require_commit(repository, result.stdout.strip())


def require_ancestor(repository: Path, ancestor_sha: str, descendant_sha: str) -> None:
    """Require one commit to be an ancestor of another, allowing equality.

    Args:
        repository: Working directory of the checked-out repository.
        ancestor_sha: Full commit ID of the required baseline.
        descendant_sha: Full commit ID whose history must include the baseline.

    Raises:
        ValueError: If either ID is invalid or the ancestry requirement fails.
        subprocess.CalledProcessError: If Git cannot inspect the commits or history.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        The repository must contain the history needed to establish ancestry.
    """
    ancestor = require_commit(repository, ancestor_sha)
    descendant = require_commit(repository, descendant_sha)
    # Git uses status 1 for a valid query with no ancestor relationship.
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "merge-base", "--is-ancestor", ancestor, descendant],  # noqa: S607
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 1:
        message = f"Commit {ancestor!r} is not an ancestor of {descendant!r}."
        raise ValueError(message)
    result.check_returncode()


def require_remote_branch_contains_commit(repository: Path, branch: str, source_sha: str) -> str:
    """Require the source commit to be reachable from an origin branch.

    Args:
        repository: Working directory of the checked-out repository.
        branch: Branch name, such as main or docs/1.4.0, without a ref prefix.
        source_sha: Full commit ID to check for branch membership.

    Returns:
        The resolved branch-tip commit ID.

    Raises:
        ValueError: If the source ID is invalid or is not in the branch history.
        subprocess.CalledProcessError: If the branch name is invalid, the remote
            branch is missing, or Git cannot inspect the history.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        This inspects local remote-tracking refs. The caller must fetch fresh
        origin branch refs and sufficient history before calling it. Reachability
        does not establish that a pull request was reviewed or approved.
    """
    source = require_commit(repository, source_sha)
    remote_ref = f"refs/remotes/origin/{branch}"
    subprocess.run(  # noqa: S603
        ["git", "check-ref-format", remote_ref],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "show-ref", "--verify", "--hash", remote_ref],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    branch_tip = require_commit(repository, result.stdout.strip())
    require_ancestor(repository, source, branch_tip)
    return branch_tip


def require_correction_file(path: str, mode: str) -> None:
    """Require a correction file to be non-executable manual content.

    Args:
        path: Repository-relative Git path, using forward slashes.
        mode: Git file mode, which must be 100644 for a regular content file.

    Raises:
        ValueError: If the path or file mode is outside the correction scope.

    Notes:
        SVG and HTML are excluded because they can contain active content.
        This validates metadata, not file contents or image decoding.
    """
    file_path = PurePosixPath(path)
    canonical = (
        file_path.as_posix() == path
        and not file_path.is_absolute()
        and ".." not in file_path.parts
        and "\\" not in path
        and PurePosixPath("docs") in file_path.parents
    )
    markdown = file_path.suffix == ".md"
    image = PurePosixPath("docs/assets") in file_path.parents and file_path.suffix in {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".avif",
    }
    if mode != "100644" or not canonical or not (markdown or image):
        message = f"Correction file is outside the permitted manual content scope: {path!r} (mode {mode!r})."
        raise ValueError(message)


def require_documentation_setup(repository: Path, source_sha: str) -> None:
    """Require the documentation entry files to exist in a commit.

    Args:
        repository: Working directory of the checked-out repository.
        source_sha: Full commit ID to inspect without checking it out.

    Raises:
        ValueError: If the commit ID is invalid or required regular files are missing.
        subprocess.CalledProcessError: If Git cannot inspect the commit.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        File presence does not establish valid configuration or buildability.
    """
    source = require_commit(repository, source_sha)
    required_paths = ("zensical.toml", "pyproject.toml", "uv.lock", "docs/index.md")
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "ls-tree", "-r", "-z", source, "--", *required_paths],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
    )
    regular_paths = set()
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        mode, object_type, _ = metadata.split()
        if mode == b"100644" and object_type == b"blob":
            regular_paths.add(path.decode("utf-8"))
    missing = sorted(set(required_paths) - regular_paths)
    if missing:
        message = f"Commit {source!r} lacks required regular documentation files: {', '.join(missing)}."
        raise ValueError(message)


def require_correction_source(
    repository: Path,
    expected_tag: str,
    source_sha: str,
    releases: Sequence[GitHubRelease],
) -> str:
    """Validate a correction's release baseline, branch history, and changed files.

    Args:
        repository: Repository with freshly fetched release tags and origin refs.
        expected_tag: Published stable release the correction must document.
        source_sha: Full commit ID of the proposed corrected documentation.
        releases: Current release metadata collected from GitHub.

    Returns:
        The resolved release-baseline commit ID.

    Raises:
        ValueError: If release eligibility, source format, required documentation
            files, ancestry, or correction scope fails.
        subprocess.CalledProcessError: If required Git objects or refs are missing,
            or Git cannot inspect the history.
        OSError: If Git cannot be started or the working directory is invalid.
        UnicodeDecodeError: If a changed path is not valid UTF-8.

    Notes:
        This does not yet check website buildability or deployed provenance.
        Maintenance-branch reachability does not prove pull-request approval.
    """
    source = validate_commit_sha(source_sha)
    require_latest_stable_tag(expected_tag, releases)
    baseline = resolve_stable_tag_commit(repository, expected_tag)
    require_documentation_setup(repository, baseline)
    require_remote_branch_contains_commit(repository, f"docs/{expected_tag.removeprefix('v')}", source)
    require_correction_changes(repository, baseline, source)
    require_documentation_setup(repository, source)
    return baseline


def require_release_source(
    repository: Path,
    expected_tag: str,
    source_sha: str,
    releases: Sequence[GitHubRelease],
) -> str:
    """Require automatic publication to use the newest stable release's commit.

    Args:
        repository: Repository with freshly fetched release tags.
        expected_tag: Published stable release to document.
        source_sha: Full commit ID supplied by the release workflow.
        releases: Current release metadata collected from GitHub.

    Returns:
        The validated release commit ID.

    Raises:
        ValueError: If the release is ineligible, the source does not match the
            tag, or required documentation files are missing.
        subprocess.CalledProcessError: If required Git objects or tags are
            missing, or Git cannot inspect them.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        The caller must enforce successful application release publication.
        This does not yet check website buildability or deployed provenance.
    """
    source = validate_commit_sha(source_sha)
    require_latest_stable_tag(expected_tag, releases)
    release_commit = resolve_stable_tag_commit(repository, expected_tag)
    if source != release_commit:
        message = f"Publication source {source!r} does not match release {expected_tag!r} commit {release_commit!r}."
        raise ValueError(message)
    require_documentation_setup(repository, release_commit)
    return release_commit


def require_bootstrap_content(repository: Path, source_sha: str) -> None:
    """Restrict the committed bootstrap manual to the approved placeholder.

    Args:
        repository: Working directory of the checked-out repository.
        source_sha: Full commit ID containing the proposed bootstrap content.

    Raises:
        ValueError: If the documentation tree or landing-page text is unexpected.
        subprocess.CalledProcessError: If Git cannot inspect the source.
        OSError: If Git cannot be started or the working directory is invalid.
        UnicodeDecodeError: If the landing page is not valid UTF-8.

    Notes:
        Configuration routing and release eligibility are checked separately.
    """
    source = require_commit(repository, source_sha)
    tree = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "ls-tree", "-r", "-z", source, "--", "docs"],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
    )
    entries = [entry for entry in tree.stdout.split(b"\0") if entry]
    if len(entries) != 1:
        message = "Bootstrap documentation must contain only the regular docs/index.md placeholder."
        raise ValueError(message)
    metadata, path = entries[0].split(b"\t", 1)
    mode, object_type, _ = metadata.split()
    if path != b"docs/index.md" or mode != b"100644" or object_type != b"blob":
        message = "Bootstrap documentation must contain only the regular docs/index.md placeholder."
        raise ValueError(message)
    page = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "show", f"{source}:docs/index.md"],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
    )
    content = page.stdout.decode("utf-8").replace("\r\n", "\n").strip()
    expected = "# Expo Studio User Manual\n\nThe user manual is under construction."
    if content != expected:
        message = "Bootstrap landing page must contain only the approved under-construction heading and message."
        raise ValueError(message)


def require_bootstrap_configuration(repository: Path, source_sha: str) -> None:
    """Require the committed bootstrap configuration to match the approved setup.

    Args:
        repository: Working directory of the checked-out repository.
        source_sha: Full commit ID containing the proposed configuration.

    Raises:
        ValueError: If required files are missing, TOML is invalid, or the
            configuration differs from the approved bootstrap settings.
        subprocess.CalledProcessError: If Git cannot inspect the source.
        OSError: If Git cannot be started or the working directory is invalid.
        UnicodeDecodeError: If the configuration is not valid UTF-8.

    Notes:
        Parsed values are compared, so comments and formatting may differ.
        Normal released manuals are not restricted to this bootstrap setup.
    """
    source = validate_commit_sha(source_sha)
    require_documentation_setup(repository, source)
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "show", f"{source}:zensical.toml"],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
    )
    configuration = tomllib.loads(result.stdout.decode("utf-8"))
    expected = {
        "project": {
            "site_name": "Expo Studio User Manual",
            "site_url": "https://jbm329.github.io/expo-studio/",
            "docs_dir": "docs",
            "site_dir": "site",
        }
    }
    if configuration != expected:
        message = "Bootstrap configuration must match the approved site identity, URL, and source/output directories."
        raise ValueError(message)


def require_publication_progress(
    repository: Path,
    published_tag: str,
    published_sha: str,
    expected_tag: str,
    source_sha: str,
) -> None:
    """Prevent publication from reverting an existing released manual.

    Args:
        repository: Repository containing the published and proposed commits.
        published_tag: Application baseline recorded by the published manual.
        published_sha: Source commit recorded by the published manual.
        expected_tag: Application baseline of the proposed publication.
        source_sha: Source commit of the proposed publication.

    Raises:
        ValueError: If IDs are invalid, the proposed version is older, or its
            same-version source does not descend from the published source.
        subprocess.CalledProcessError: If Git cannot inspect required commits.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        Call only for released manuals, after validating publication eligibility.
        Bootstrap transitions and missing deployment state are handled separately.
    """
    published_version = parse_stable_tag(published_tag)
    proposed_version = parse_stable_tag(expected_tag)
    published_source = require_commit(repository, published_sha)
    source = require_commit(repository, source_sha)
    if proposed_version < published_version:
        message = f"Publication for {expected_tag!r} would replace the newer published manual for {published_tag!r}."
        raise ValueError(message)
    if proposed_version == published_version:
        require_ancestor(repository, published_source, source)


def require_manifest_progress(
    repository: Path,
    published: PublicationManifest,
    proposed: PublicationManifest,
) -> None:
    """Require a publication to advance or repeat the deployed provenance.

    Args:
        repository: Repository containing both publication source commits.
        published: Validated provenance of the existing deployment.
        proposed: Validated provenance of the proposed deployment.

    Raises:
        ValueError: If bootstrap would replace a released manual, the application
            baseline moves backward, or same-version source history regresses.
        subprocess.CalledProcessError: If required Git commits cannot be inspected.
        OSError: If Git cannot be started or the working directory is invalid.

    Notes:
        Validate both manifests before calling. Source eligibility must also be
        checked independently; run IDs are provenance, not publication ordering.
    """
    if published["mode"] != "bootstrap" and proposed["mode"] == "bootstrap":
        message = "Bootstrap cannot replace an already published released manual."
        raise ValueError(message)
    require_publication_progress(
        repository,
        published["baseline_tag"],
        published["source_sha"],
        proposed["baseline_tag"],
        proposed["source_sha"],
    )


def require_bootstrap_source(
    repository: Path,
    expected_tag: str,
    source_sha: str,
    releases: Sequence[GitHubRelease],
) -> str:
    """Validate the initial landing-page publication against a pre-docs release.

    Args:
        repository: Repository with freshly fetched release tags and origin refs.
        expected_tag: Latest stable release, which must predate site configuration.
        source_sha: Full commit ID of the approved bootstrap source on main.
        releases: Current release metadata collected from GitHub.

    Returns:
        The resolved stable-release baseline commit ID.

    Raises:
        ValueError: If the baseline already contains site configuration or any
            release, source, branch, content, or configuration check fails.
        subprocess.CalledProcessError: If Git cannot inspect required objects.
        OSError: If Git cannot be started or the working directory is invalid.
        UnicodeDecodeError: If source text is not valid UTF-8.

    Notes:
        Any committed zensical.toml entry closes bootstrap, even if incomplete.
        Deployment provenance and website buildability are checked separately.
    """
    source = validate_commit_sha(source_sha)
    require_latest_stable_tag(expected_tag, releases)
    baseline = resolve_stable_tag_commit(repository, expected_tag)
    result = subprocess.run(  # noqa: S603
        ["git", "--no-replace-objects", "ls-tree", "-z", baseline, "--", "zensical.toml"],  # noqa: S607
        cwd=repository,
        check=True,
        capture_output=True,
    )
    if result.stdout:
        message = f"Bootstrap is unavailable: stable release {expected_tag!r} already contains site configuration."
        raise ValueError(message)
    require_remote_branch_contains_commit(repository, "main", source)
    require_ancestor(repository, baseline, source)
    require_bootstrap_configuration(repository, source)
    require_bootstrap_content(repository, source)
    return baseline


def main(argv: Sequence[str] | None = None) -> None:
    """Prepare a publication, retrieve public metadata, or check provenance progress.

    Args:
        argv: Command-line arguments, or None to use the process arguments.

    Raises:
        SystemExit: If command-line arguments are invalid or help is requested.
        ValueError: If metadata, source eligibility, or publication progress is invalid.
        TypeError: If GitHub release metadata is malformed.
        subprocess.CalledProcessError: If Git or GitHub CLI operations fail.
        OSError: If a command or required file is unavailable.
        UnicodeDecodeError: If input text is not valid UTF-8.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Validate a source without building or deploying.")
    prepare.add_argument("--repository", type=Path, required=True, help="Dedicated full-history checkout.")
    prepare.add_argument("--repository-slug", required=True, help="GitHub owner/repository identifier.")
    prepare.add_argument("--request", type=Path, required=True, help="Publication request JSON file.")
    prepare.add_argument("--output", type=Path, required=True, help="Validated manifest JSON output file.")
    progress = commands.add_parser("check-progress", help="Reject regression against verified deployed provenance.")
    progress.add_argument("--repository", type=Path, required=True, help="Checkout containing both source commits.")
    progress.add_argument("--published", type=Path, required=True, help="Verified deployed manifest JSON file.")
    progress.add_argument("--proposed", type=Path, required=True, help="Validated proposed manifest JSON file.")
    fetch = commands.add_parser(
        "fetch-published", help="Retrieve public provenance; deployment verification is separate."
    )
    fetch.add_argument("--output", type=Path, required=True, help="Public manifest JSON output file.")
    inspect = commands.add_parser(
        "inspect-published", help="Report manual deployment metadata without authorizing publication."
    )
    inspect.add_argument("--repository-slug", required=True, help="GitHub owner/repository identifier.")
    inspect.add_argument("--repository", type=Path, required=True, help="Full-history checkout for source comparison.")
    inspect.add_argument("--proposed", type=Path, required=True, help="Validated proposed manifest JSON file.")
    inspect.add_argument("--output", type=Path, required=True, help="Inspection report JSON output file.")
    inspect.add_argument(
        "--confirm-initial-bootstrap",
        action="store_true",
        help="Operator confirms an initial placeholder publication; never bypasses existing deployment checks.",
    )
    verify_site = commands.add_parser("verify-site", help="Check built website metadata against a validated proposal.")
    verify_site.add_argument("--site", type=Path, required=True, help="Extracted website artifact directory.")
    verify_site.add_argument("--proposed", type=Path, required=True, help="Independently validated manifest JSON file.")
    arguments = parser.parse_args(argv)
    if arguments.command == "verify-site":
        require_site_manifest(arguments.site, read_publication_manifest(arguments.proposed))
        return
    if arguments.command == "inspect-published":
        proposed = read_publication_manifest(arguments.proposed)
        published = fetch_manual_publication_metadata(arguments.repository_slug)
        if published is None and proposed["mode"] != "bootstrap":
            message = "Empty Pages deployment history requires an explicitly validated bootstrap proposal."
            raise ValueError(message)
        if published is None and not arguments.confirm_initial_bootstrap:
            message = "Initial placeholder publication requires explicit operator confirmation."
            raise ValueError(message)
        if published is not None:
            require_manifest_progress(arguments.repository, published, proposed)
        report = {
            "schema_version": 1,
            "state": "no-deployment-records" if published is None else "metadata-cross-checked",
            "publication": published,
            "proposed": proposed,
            "progress_check": "no-published-source" if published is None else "passed",
            "deployment_authorized": False,
            "initial_bootstrap_confirmed": published is None and arguments.confirm_initial_bootstrap,
        }
        arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return
    if arguments.command == "fetch-published":
        write_publication_manifest(arguments.output, fetch_published_manifest())
        return
    if arguments.command == "check-progress":
        published = read_publication_manifest(arguments.published)
        proposed = read_publication_manifest(arguments.proposed)
        require_manifest_progress(arguments.repository, published, proposed)
        return
    request = read_publication_manifest(arguments.request)
    manifest = prepare_publication(arguments.repository, arguments.repository_slug, request)
    write_publication_manifest(arguments.output, manifest)


if __name__ == "__main__":
    main()

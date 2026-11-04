# Contributing

Thanks for your interest in contributing 🎉

## Ground rules
- Be respectful and constructive.
- Please read our [Code of Conduct](CODE_OF_CONDUCT.md).

## Where to contribute
- **Bug reports:** open an Issue using the Bug Report template.
- **Feature ideas:** open an Issue using the Feature Request template (or start in Discussions).

## Pull requests
- Create a focused branch (`feat/...`, `fix/...`, `docs/...`, `chore/...`).
- Keep changes small and clear.
- Use clear commit messages (e.g. `fix: handle null response`).
- Open a PR describing:
  - what changed
  - why it changed
  - how you tested it

## Documentation infrastructure

Before final deployment checks can ignore an environment job's own pending
record, the helper requires matching workflow commit, current run ID, and an
exact job-specific Actions log URL. Run-only URLs and other jobs are insufficient.
This identity cross-check alone does not authorize excluding records or publishing.
Current-job lookup now queries every jobs page for the exact run attempt,
requiring one in-progress `Deploy documentation` job with the expected workflow
commit and runner name. It returns the numeric job ID, with malformed responses
and mismatches failing explicitly. Runtime identifiers must come from the trusted
runner context, not manual inputs.
The history selector now optionally resolves this trusted execution context and
excludes at most one unfinished record matching the verified job and commit.
Other unfinished records, duplicate current-job records, and failed-only prior
history remain errors. Only the current job's record is equivalent to no prior
history; initial-bootstrap confirmation is still required by publication policy.
The provenance inspector passes this optional context to both history reads,
resolving the executing job independently on each read. When no prior history
remains, it also rechecks before returning that state; this does not authorize
bootstrap or bypass its explicit confirmation.
This optional path is not wired into publication commands or the workflow yet.
Public environment-deployment metadata confirms job-specific log URLs are used;
the first hosted run must still verify this repository's actual metadata.

The helper's `verify-published --repository-slug <owner/repo> --proposed <manifest>`
command checks the latest stable release and requires the public website's
provenance to match the deployed proposal. It can run while the current workflow
is active, without requiring that workflow or its deployment job to have finished.
It is not wired into deployment yet. A mismatch, superseding release, or request
failure is an error, not a rollback: the website may already have been published.
CDN propagation may delay matching metadata; do not treat a failed check as proof
that deployment did not happen.

The deployment helper also checks name-based Pages artifact selection: after
checking package identity, it lists every artifact page for the run and requires
exactly one `github-pages` entry with the verified immutable ID. Missing,
replaced, duplicate, or malformed entries fail explicitly. The existing
`verify-pages-artifact` command now includes this safeguard, so the post-build
recheck enforces both package identity and unique name selection. Deployment
is not wired yet; the API check and eventual deployment are not atomic.

The manual publication form includes a default-off `deploy_website` checkbox.
It is currently a recorded request only: even when checked, the workflow does
not deploy. The validated-request summary shows the selection. Initial-bootstrap
confirmation remains a separate input; requesting deployment does not replace
that confirmation or bypass any validation. The guarded deployment job will be
added in a subsequent implementation step.

The user manual uses Zensical. Markdown sources live in `docs/`, and
`zensical.toml` configures the website. Feature documentation has not yet
been added.

Install the documentation dependencies:

```powershell
uv sync --frozen --extra docs
```

Start the local preview:

```powershell
uv run --frozen --extra docs zensical serve
```

Create a clean build with warnings treated as errors:

```powershell
uv run --frozen --extra docs zensical build --clean --strict
```

The generated website is written to `site/`. Do not edit or commit that
directory.

The Documentation GitHub Actions workflow checks relevant pull requests
targeting `main` or a `docs/*` maintenance branch. It builds the website,
uploads a `documentation-site` artifact for review, and runs the publication
policy tests and checks. It has read-only repository permissions and does
not publish the website.

The separate Documentation publication workflow currently validates manual
bootstrap or correction requests from `main` and uploads a validated manifest.
A separate read-only job checks out that exact validated source commit, checks
its dependency lockfile, and builds the website. The resulting
`documentation-publication-preview` artifact is available for seven days.
It includes `publication.json`, recording the validated mode, application
baseline, source commit, and workflow run. This filename is reserved for
generated provenance; do not add a documentation asset with that output path.
The Actions run summary also identifies the validated source and preview.
For bootstrap, the baseline identifies the existing application release, not
a claim that the placeholder documents that version. The workflow does not
deploy the website yet.

The publication helper also provides `check-progress` for comparing validated
proposed provenance with verified deployed provenance. It rejects older
application baselines and older or divergent source commits for the same
baseline, while allowing identical-source retries. Both manifest files are
required; a missing file is not treated as an empty deployment.
This command does not retrieve or authenticate deployed state, establish source
eligibility, or deploy anything. It is not connected to the workflow yet.

The helper's `fetch-published --output <path>` command retrieves `publication.json`
from the fixed public website over HTTPS and validates its schema. It requests
fresh content and rejects unexpected redirects, oversized responses, and malformed
metadata. HTTP errors (including a missing file), timeouts, and network failures
are errors, not evidence that no previous deployment exists. Public metadata
must still be checked against trusted GitHub deployment history before it is
used to authorize publication; that integration is not implemented yet.

The helper can also query every page of GitHub's `github-pages` deployment
records using a token with `deployments: read`. API failures and malformed
records fail explicitly rather than producing an empty history. These records
alone do not establish deployment success or verify public provenance, and an
empty history alone does not authorize a first publication.

Deployment status retrieval preserves all reported states, including pending,
failed, successful, and inactive records. It does not assume API ordering or
treat an empty status list as success. The latest status is selected by its
validated UTC creation timestamp, not its ID, state, or response position.
Distinct records tied for the latest timestamp are rejected as ambiguous.
The helper combines these queries to identify exactly one currently successful
deployment. Failed and inactive attempts do not replace that success; unfinished
attempts, missing status histories, or conflicting successes stop the check.
No deployment records is distinguished from existing history with no current
success, but neither result authorizes bootstrap on its own. These API reads
are not atomic and must run before creating a proposed deployment record.
The helper can check that the selected success status links to the repository
and Actions run recorded in the public manifest. This association check accepts
canonical HTTPS run links with an optional job suffix; it does not fetch the link
or prove a trusted workflow, matching run attempt, or artifact contents.
For manual bootstrap/correction provenance, a further read-only Actions API
check requires a completed `publish-docs.yml` dispatch from `main`,
the expected repository (including the source repository), and the deployment's
workflow commit SHA. It returns the current run-attempt number for subsequent
verification. This does not verify workflow file contents, the deployment's
exact attempt, or artifact contents. Automatic release runs are not accepted by
this manual check.

The overall workflow conclusion is not used as evidence of deployment success:
the website may already have been published before a later verification fails
or the run is cancelled. The separate deployment-job check below still requires
a successful job. This permits inspection of a published site after a subsequent
workflow failure without accepting a failed or cancelled deployment job.

A separate job check requires exactly one successful job named
`Deploy documentation` in that run attempt. A job-specific status link must
identify that same job, and its success timestamp cannot precede the job's start.
GitHub may record deployment success after job completion, so an exact job link
does not impose a completion-time cutoff. Run-only links still require success
within the job's execution window because they do not directly identify the job.
Job timestamps must be valid and completion cannot precede start. These checks
do not establish artifact contents. The deploy job has not been
added yet; artifact verification and final deployment wiring remain unfinished.

`fetch_manual_publication_metadata` connects the current-deployment, public
manifest, run-association, manual-run, and job checks. It rechecks the selected
deployment after inspection and rejects a changed deployment or status.
Only an initially empty deployment history returns no metadata; every failed
check propagates as an error. This is still metadata inspection, not artifact
verification or permission to publish.

The manual workflow now runs this inspection in a separate trusted-policy job
with `contents: read`, `actions: read`, and `deployments: read`. It does not
install or execute the selected documentation source. Its
`documentation-publication-inspection` artifact is retained for seven days.
The `inspect-published --repository-slug <owner/repo> --repository <checkout>
--proposed <manifest> --output <path>` command
writes either `no-deployment-records` or `metadata-cross-checked`, explicitly
recording `deployment_authorized: false`. Inspection errors fail the job without
writing a report; they are not reported as empty history. The preview build
remains independent of inspection after source validation. There are still no
Pages write permissions or deployment steps.

Inspection also compares the downloaded proposed manifest with the cross-checked
published source using the full-history trusted checkout. Regressions fail the
inspection job without a report. Successful reports include the proposed
metadata and a `progress_check` of `passed` or `no-published-source`; the latter
means there was nothing to compare, not that bootstrap is authorized. This is
an early review check, not the serialized final check required for deployment.
When history is empty, inspection requires a bootstrap proposal; correction and
release proposals fail without a report. Bootstrap eligibility must already have
passed source preparation, including the placeholder-only and pre-documentation
release checks. This restriction applies to both initial and post-build
inspection. It does not prove that a site never existed (records can be deleted)
or authorize deployment by itself.

For empty deployment history, the operator must also select the manual workflow's
`confirm_initial_bootstrap` checkbox, which defaults to unchecked. The CLI
equivalent is `--confirm-initial-bootstrap`. Both inspection passes require
this confirmation and record `initial_bootstrap_confirmed: true` when used for
empty history. Confirmation never bypasses API failures, known deployment
checks, source eligibility, or regression checks. With existing deployment
metadata, normal checks still apply and the report records the field as false.
This is an explicit operator assertion, not automated proof that no site existed.

The helper's `verify-site --site <directory> --proposed <manifest>` command
checks an extracted website against a separately validated proposal. It requires
a regular website directory, a nonempty regular `index.html`, and a regular
`publication.json` matching every validated provenance field. It does not execute
website content or prove the origin of all website bytes.
Before Pages packaging, verification also walks the entire extracted website,
rejecting symlinks, Windows junctions, and special files anywhere in the tree.
Only regular files and directories are accepted; unreadable directories fail
explicitly. This prevents the Pages packager from following links in its input.

The manual workflow runs this command in a separate read-only `verify` job
after the preview build. It downloads the website and validated proposal from
the same Actions run into separate directories outside the trusted checkout.
The build exposes the website upload's immutable artifact ID; verification
requires a positive numeric ID and downloads that exact artifact, not a
name-based replacement. The verified ID appears in the Actions summary.
Missing or deleted artifacts fail verification rather than falling back to
another preview. The ID is available for the future deployment step to reuse.
Validation likewise exposes and checks the manifest upload's immutable artifact
ID. The build, inspection, verification, and post-build recheck all download
that exact proposal by ID, without falling back to an artifact name.
Only the trusted helper is executed, without installing application dependencies
or retaining checkout credentials. Its Actions summary confirms successful
structure and metadata checks, not authorization to deploy. Deployment wiring
and verification of the previously published artifact remain unfinished.

After metadata verification, that same job uses `actions/upload-pages-artifact`
to package the downloaded website in GitHub Pages' required archive format.
The `github-pages` artifact is retained for seven days, and its immutable ID is
checked, exposed as a job output, and included in the Actions summary. This is
a separate artifact from the browsable preview; it contains the Pages archive
of the verified website, including `publication.json`. Packaging does not publish
the site or require Pages write permissions. A later eligibility recheck can
still fail even though this artifact was uploaded.

The helper can independently check the packaged artifact's GitHub API metadata:
the immutable ID, `github-pages` name, and workflow run must match, and the
artifact must be nonempty and unexpired. API failures and missing metadata fail
explicitly. This checks identity and availability, not archive contents or run
attempt. The post-build `recheck` job now runs this check using the exact Pages
artifact ID exposed by `verify` and the current workflow run ID. It calls
`verify-pages-artifact --repository-slug <owner/repo> --artifact-id <id>
--run-id <id>` through the trusted helper, with the job's existing read-only
Actions permission. Failure stops the job before the successful recheck summary.
Later deletion or expiration
must fail deployment rather than trigger an artifact substitution.

Publication runs share the fixed `documentation-publication` concurrency group,
independent of source branch, commit, or mode. An active run is not automatically
cancelled when another request arrives. GitHub does not guarantee queue order
and may replace an older pending run with a newer request; inspect run status
and retry a still-relevant request if needed. The future automatic release path
must use this same group without adding a conflicting group to its caller.
The read-only PR preview workflow is not serialized by this group. Concurrency
does not freeze release metadata or public deployment state, so final eligibility
and progress rechecks are still required before deployment.

After both inspection and artifact verification succeed, a read-only `recheck`
job runs source preparation again using the trusted policy and freshly fetched
refs and releases. It compares the resulting manifest byte-for-byte with the
original validated proposal. A superseded release or no-longer-eligible source
fails the run instead of accepting an outdated preview request. This job retains
read-only checkout credentials for fetching, but does not install or execute the
selected source. With job-scoped `actions: read` and `deployments: read`, it
also reruns deployment metadata inspection and source-progress comparison using
the rechecked proposal, rather than reusing the earlier inspection report.
The `documentation-publication-recheck` artifact retains that fresh report for
seven days. Failed inspection or a regressing source fails the job. No deployment
records still means nothing to compare, not bootstrap authorization.
These reads are not atomic and do not verify published artifact contents or
authorize deployment; final checks must still be connected to the future
deployment step.

## Notes
This is a spare-time project, so response times may vary.  
Thanks for your patience and for helping improve the project 💛
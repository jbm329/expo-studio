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
do not establish deployment success or verify public provenance yet, and an
empty history alone does not authorize a first publication. No workflow
permissions have been expanded for this query yet.

Deployment status retrieval preserves all reported states, including pending,
failed, successful, and inactive records. It does not assume API ordering or
treat an empty status list as success. Selecting the authoritative deployment
and verifying its workflow against the public manifest are still separate,
unfinished integration steps.

## Notes
This is a spare-time project, so response times may vary.  
Thanks for your patience and for helping improve the project 💛
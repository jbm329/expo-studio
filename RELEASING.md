# Publishing a GitHub Release

A release tag points to a **commit**, not to a branch. Tag a commit **after it has been merged into `main`** so the release is built from the code on `main`. You do not need permission to push commits directly to `main`, but you do need permission to push the release tag.

1. Create a branch as usual. Make the release-ready changes there, including the version in `pyproject.toml` and, if appropriate, `CHANGELOG.md`.
2. Run `uv lock` and include the updated `uv.lock` in the branch. For a release candidate (RC), use a Python version such as `1.0.0rc1`.
3. Push the branch, open a PR, and let CI run. Review and squash-merge it into `main` as usual.
4. Check out `main` in PyCharm and update it from the remote. Confirm it contains the merged version and release workflow you intend to use.
5. Create a tag **on that `main` commit** and push the tag. For example, for `version = "1.0.0rc1"`:

   ```text
   git tag v1.0.0-rc1
   git push origin v1.0.0-rc1
   ```

   For a stable `version = "1.0.0"`, use `v1.0.0`. You can create and push the tag through IDE (if supported) instead if you prefer.
6. The tag push starts the release workflow. It checks the version and lockfile, builds both platforms, and, if both succeed, publishes the GitHub Release with its files. Check the Actions run and the resulting release page.

Your branch can be deleted after the merge; the release tag remains attached to the merged commit. **Do not tag the feature branch before merging**: that could release a commit different from the one on `main`. If GitHub rejects the tag push, that is a separate tag-permission or repository-rules setting, not a need for direct-push access to `main`.


## Automatic documentation publication preparation

Release validation exposes whether the validated tag is a canonical stable
version and the exact checked-out release commit. Prerelease tags are explicitly
classified as non-stable. These outputs do not publish documentation yet:
automatic integration must run only after successful `publish-release`, verify
that the release remains the newest stable release, and share the manual
publication concurrency group.

The existing publication pipeline exposes a `workflow_call` interface with the
same explicit inputs as manual dispatch. Deployment and initial-bootstrap
confirmation both default to false; no custom secrets are requested.
No release caller is connected yet, and main-only execution guards remain in
place. Caller-aware eligibility and provenance validation must be added before
release-tag execution is enabled. Manual and automatic entry points will share
this pipeline rather than duplicate its build and deployment safeguards.

## Manual documentation publication recovery

Documentation publication is separate from application releases. Its default
is preview-only; `Deploy website` explicitly enables publication. The workflow
does not automatically recover from ambiguous deployment history or roll back
a site after a failed public verification.

### Start a new run instead of rerunning publication

Use **Run workflow** from `main` for a new publication attempt, with a freshly
reviewed source and the current stable baseline. Do not use **Re-run all jobs**
or **Re-run failed jobs** on a publication run for now:

- Artifact names are scoped to a run, not an attempt. Rebuilding can create
  duplicate packages and is deliberately rejected by the unique-artifact check.
- Published provenance records the run ID, while inspection currently checks
  that run's latest attempt. A partial rerun can leave the successful deployment
  job in an older attempt and make later inspection fail.

If a publication run was already rerun, stop and inspect its attempt/job history
before proceeding. Do not delete successful deployment records to bypass this
check. Supporting that history requires a policy fix, not a cleanup shortcut.

### Public verification failed after deployment

If `Deploy documentation` succeeded but `Verify published documentation` failed,
the site may already be live. Inspect the returned URL, public
[`publication.json`](https://jbm329.github.io/expo-studio/publication.json),
the validated proposal artifact, and verification logs. Allow for CDN
propagation, and check whether a newer stable application release superseded
the requested baseline. A missing file, HTTP error, or overall failed workflow
does not establish that no publication occurred.

Do not delete this deployment or rerun the workflow to clear a verification
error. After establishing the served state, use a fresh eligible publication
run if another publication is necessary. A successful deployment job remains
inspectable even if its overall workflow failed later.

### First bootstrap failed before the Pages action ran

An environment job creates deployment records before it executes the Pages
action. A failure during setup or final checks can therefore leave history but
no published site. The initial-bootstrap checkbox does **not** bypass this
history; a failed-only history remains an error.

Manual cleanup is limited to this unambiguous pre-publication case:

1. Wait until the failed run is finished and no documentation publication is
   active or queued. Save its run URL, job URL, logs, proposal, and deployment
   metadata before changing anything.
2. Verify that `Deploy verified Pages package` was **never started** in any
   attempt and that no other run or mechanism has published the website.
   Inspect all `github-pages` deployment records and status histories.
   Confirm every record proposed for removal belongs to those failed bootstrap
   jobs, and that no successful publication exists. A website 404 alone is
   insufficient evidence.
3. If the Pages action started, publication success is recorded, provenance
   exists, or ownership/outcome is uncertain, **stop**. Do not mark the record
   inactive or delete it. Investigate the actual served state first.
4. Only after these checks, a maintainer may mark each individually verified
   failed bootstrap record inactive and delete that exact record using GitHub's
   deployment API. Never delete the environment, unrelated records, or a
   successful publication, and never bulk-delete deployment history.

For inspection, use the GitHub CLI with an authenticated maintainer account.
The CLI must be installed separately; it is not an application dependency.
List all pages, then replace `DEPLOYMENT_ID` below with one reviewed numeric ID:

```powershell
gh api --paginate "repos/jbm329/expo-studio/deployments?environment=github-pages&per_page=100"
gh api "repos/jbm329/expo-studio/deployments/DEPLOYMENT_ID"
gh api --paginate "repos/jbm329/expo-studio/deployments/DEPLOYMENT_ID/statuses?per_page=100"
```

The following commands **change and delete deployment metadata** and require
deployment write permission. Run them only for the exact failed pre-publication
record approved above, checking the result of each command before continuing:

```powershell
gh api --method POST "repos/jbm329/expo-studio/deployments/DEPLOYMENT_ID/statuses" -f state=inactive -f description="Reviewed failed bootstrap; Pages action never started" -F auto_inactive=false
gh api --method DELETE "repos/jbm329/expo-studio/deployments/DEPLOYMENT_ID"
```

Re-list the full history and confirm it is empty; if it is not, inspect the
remaining records rather than bypassing the check. Then start a **new** workflow
run. First leave `Deploy website` unchecked and review its preview and empty
history report. Only after that succeeds, start another new run with deployment
and initial-bootstrap confirmation explicitly selected.


# Release tracking issue template

# Release vX.Y.Z

## Summary
Prepare and publish release **vX.Y.Z** for `expo-studio`.

- Target date: YYYY-MM-DD
- Release type: patch / minor / major
- Owner: @jbm329

---

## Scope (since last release)
This release includes all merged work since the previous tag/release, grouped below.

### Features
- [ ] #123 — Add diagnostic logging to Reshape area
- [ ] #124 — <feature title>

### Fixes
- [ ] #130 — <bug fix title>

### Refactors
- [ ] #135 — <refactor title>

### Documentation
- [ ] #140 — <docs title>

### Chores / Maintenance
- [ ] #145 — Add issue templates (bug/feature/refactor/documentation)
- [ ] #146 — Project workflow/filter updates
- [ ] #147 — CI/dependency/tooling maintenance

---

## Included PRs
<!-- Include everything merged since last release -->
- [ ] #201 — feat: add reshape diagnostic logging (`Closes #123`)
- [ ] #202 — docs: add documentation issue template
- [ ] #203 — chore: add/refine issue templates
- [ ] #204 — chore: update project automation filters

---

## Release checklist

### 1) Scope freeze
- [ ] Confirm all PRs intended for vX.Y.Z are merged
- [ ] Move any unfinished items to next release issue/milestone

### 2) Versioning
- [ ] Determine semantic version bump (patch/minor/major)
- [ ] Update app/package version(s)
- [ ] Commit message follows convention (e.g., `chore(release): vX.Y.Z`)

### 3) Release notes
- [ ] Draft release notes from included PRs/issues
- [ ] Ensure user-facing changes are clear
- [ ] Keep chores brief in public notes

### 4) QA / verification
- [ ] Smoke test core flows
- [ ] Verify Reshape logging behavior (success + error path)
- [ ] Confirm no sensitive data appears in logs

### 5) Publish
- [ ] Create release PR (if used)
- [ ] Merge release PR
- [ ] Create/push tag `vX.Y.Z`
- [ ] Publish GitHub Release with notes

### 6) Post-release
- [ ] Verify production/runtime health
- [ ] Announce release (if applicable)
- [ ] Create next release tracking issue

---

## Draft release notes (public)

### ✨ Features
- Added diagnostic logging in the Reshape area to improve troubleshooting and observability.

### 🐛 Fixes
- <Add fix summaries>

### ♻️ Refactors
- <Add refactor summaries>

### 📝 Documentation
- Added/improved issue templates and contribution workflow guidance.

### 🧰 Chores
- Repository maintenance updates (labels/templates/project automation).

---

## References
- Previous release: <link>
- Compare changes: <link>
- Milestone/Project view: <link>
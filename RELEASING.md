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
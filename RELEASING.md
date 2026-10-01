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

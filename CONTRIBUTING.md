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

## Documentation

The English online user manual is authored with Zensical. Its Markdown sources
are in `docs/`, and `zensical.toml` configures the site.

Install the documentation dependencies with
`uv sync --frozen --extra docs`. Run `uv run preview-documentation` to preview
locally or `uv run build-documentation` to build with strict checks. These
commands do not publish the site; generated files in `site/` should not be
committed.

See [DOCUMENTATION.md](DOCUMENTATION.md) for detailed workflow and publication
information, and [RELEASING.md](RELEASING.md) for recovery procedures.

## Notes

This is a spare-time project, so response times may vary.  
Thanks for your patience and for helping improve the project 💛

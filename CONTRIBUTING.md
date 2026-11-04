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
It does not build or deploy the website yet.

## Notes
This is a spare-time project, so response times may vary.  
Thanks for your patience and for helping improve the project 💛
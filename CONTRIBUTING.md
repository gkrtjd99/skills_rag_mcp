# Contributing

## Local checks

Use the repository's pinned environment:

```bash
uv sync --frozen
make check
```

The default test suite is offline and must not require a Hugging Face model
cache or a cloud API. Model-quality changes should add or update a fixture and
run the disposable Docker benchmark separately.

After installing a real corpus, run `make eval-personal` before changing the
default model or thresholds. The command reads `~/.skills` and does not write
the corpus into the repository.

## Change policy

- Keep `~/.skills/`, LanceDB indexes, model caches, and benchmark output out of
  commits.
- Record behavioral changes under `docs/superpowers/specs/` and
  `docs/superpowers/plans/`.
- Update both READMEs when user-visible defaults or commands change.
- Keep MCP response contracts backward-compatible unless the change is
  explicitly documented as a release migration.

## Release flow

1. Update `CHANGELOG.md` and the version in `pyproject.toml`.
2. Run `make check`.
3. Create a semver Git tag and a GitHub Release with the built wheel/sdist.
4. Do not attach model weights, private corpora, indexes, or telemetry data.

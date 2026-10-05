# Contributing to BehaviorWeave

Thank you for helping improve BehaviorWeave. This guide describes the development workflow
and the standards every change must meet. By participating, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/smuniharish/behaviorweave
cd behaviorweave
uv sync --all-groups
```

`uv sync` installs the `dev` group (tests, lint, and type checking); `--all-groups` also
installs the `docs` and `examples` groups, which the documentation build, the example tests,
and the type checker need.

## Quality gates

CI runs every check below on Linux and Windows with Python 3.12, 3.13, and 3.14, and once
against the lowest supported dependency versions. Run them before opening a pull request:

```bash
uv run pytest --cov            # 100% line and branch coverage; warnings are errors
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check
uv run mkdocs build --strict
uv run python scripts/render_diagrams.py --check
uv build
```

Set `HYPOTHESIS_PROFILE=ci` to run the property-based tests with more examples, as CI does.

## Tests

- Add tests for every behavior change. Coverage is enforced at 100% for lines and branches.
- Property-based tests use [Hypothesis](https://hypothesis.readthedocs.io/). Prefer checking
  semantics against a simple reference model over asserting single examples; the engine, the
  state store, and the middleware's halts each have a stateful model-based test.
- When changing state behavior, cover scope isolation, duplicate delivery, concurrency, and
  serialization.
- `tests/support.py` provides a fixed clock, a recording state store, a scripted chat model,
  and a tool-call request builder for testing without a provider.
- `tests/test_examples.py` runs every example offline with a rule-based chat model. To run
  the examples against a real endpoint as well, set `BEHAVIORWEAVE_LIVE_TESTS=1` with the
  variables described in [`examples/README.md`](examples/README.md); these runs make paid
  provider calls.
- Python snippets in `README.md`, `docs/`, and the Agent Skill are executed by
  `tests/test_docs.py`, and every `print(...)  # expected` comment is checked against the
  actual output. Put `<!-- skip-snippet: reason -->` on the line before a fence only when a
  snippet needs a live model or an external service.
- `tests/test_performance.py` holds generous performance budgets. For measurements, run
  `uv run python scripts/benchmark.py`.

## Documentation and diagrams

- Preview the documentation with `uv run mkdocs serve`.
- Diagrams are written in Mermaid under `docs/diagrams/` and rendered to PNG under
  `docs/assets/diagrams/`. After editing a `.mmd` file, run
  `uv run python scripts/render_diagrams.py` (requires Node.js) and commit the sources, the
  images, and `docs/diagrams/manifest.json`.
- Document every public symbol with a Google-style docstring; the API reference is generated
  from them. Keep internal helpers underscored so they stay out of the reference.

## Agent Skill

The Agent Skill in [`behaviorweave-skills/`](behaviorweave-skills/) must match the package.
When public API or documented behavior changes, update the skill and follow
[`behaviorweave-skills/validation/README.md`](behaviorweave-skills/validation/README.md).
`tests/test_skill.py` validates it on every run.

## Design principles

- Keep detection (patterns), decisions (policies), and execution (the host) separate.
- Integrations use public framework APIs only; never monkey-patch framework internals.
- Prefer explicit, validated configuration over silent fallbacks.

## Pull requests

Keep pull requests focused, describe the behavior change and how it is tested, and add an
entry to `CHANGELOG.md` for user-visible changes.

## Releases

Releases are published to PyPI by the `Release` workflow when a GitHub release is published.
The release tag must be `v` followed by the version in `src/behaviorweave/__init__.py`, and
the `CHANGELOG.md` entry for that version must be complete. Publishing uses PyPI trusted
publishing, so no API token is stored in the repository.

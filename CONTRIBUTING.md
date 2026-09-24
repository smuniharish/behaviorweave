# Contributing

Use Python 3.12 and uv. Run:

```text
uv sync
uv run pytest
uv run ruff check .
uv run black --check .
uv run pyrefly check
uv run mkdocs build --strict
uv build
```

Keep pattern detection, policy selection, and intervention execution separate. Add
tests for scope, duplicate delivery, concurrency, and serialization when changing
state behavior.

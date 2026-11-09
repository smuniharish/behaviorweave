# Project

- [Changelog](https://github.com/smuniharish/behaviorweave/blob/master/CHANGELOG.md)
- [Contributing](https://github.com/smuniharish/behaviorweave/blob/master/CONTRIBUTING.md)
- [Security policy](https://github.com/smuniharish/behaviorweave/blob/master/SECURITY.md)
- [Source and issues](https://github.com/smuniharish/behaviorweave)

CI checks Python 3.12 through 3.15 on Ubuntu and Windows, lint, formatting, pyrefly,
100% branch coverage, package builds, database contracts, examples, and the Zensical site.

Run locally:

```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check
uv run pytest --cov=behaviorweave
uv run zensical build --strict
uv run python scripts/check_site_links.py
```

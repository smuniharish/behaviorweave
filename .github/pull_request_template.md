<!--
Thanks for contributing to BehaviorWeave! This template helps reviewers understand and
validate your change quickly.
-->

## Summary

<!-- What does this pull request change, and why? -->

## Related issues

<!-- Link related issues, for example "Closes #123". -->

## Type of change

- [ ] Bug fix
- [ ] New feature (pattern, policy option, integration, or adapter method)
- [ ] Documentation
- [ ] Refactor or internal cleanup (no behavior change)
- [ ] Other (describe above)

## Checklist

- [ ] I read [CONTRIBUTING.md](../CONTRIBUTING.md).
- [ ] New or changed behavior is covered by tests, including property-based tests for
      changes to counting, state, or precedence.
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass.
- [ ] `uv run pyrefly check` passes.
- [ ] `uv run pytest --cov` passes with 100% line and branch coverage.
- [ ] `uv run mkdocs build --strict` passes, and diagrams were re-rendered if a
      `docs/diagrams/*.mmd` source changed.
- [ ] Documentation and the Agent Skill were updated if this changes public API or
      documented behavior.
- [ ] `CHANGELOG.md` has an entry if this is a user-visible change.

## Behavior impact

<!--
Does this change which events are counted, when policies fire, what state is stored, or
what reaches an audit sink? Describe the effect, or write "None".
-->

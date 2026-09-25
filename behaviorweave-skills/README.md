# BehaviorWeave Agent Skills distribution

This directory is the canonical Agent Skills distribution for BehaviorWeave. It contains procedural guidance for coding agents that need to integrate, configure, test, or debug the existing BehaviorWeave package.

It is not a Python package and does not add runtime behavior.

| Component | Location | Purpose |
| --- | --- | --- |
| BehaviorWeave runtime | [`../src/behaviorweave/`](../src/behaviorweave) | The published Python package and its supported public API. |
| BehaviorWeave Agent Skill | [`skills/behaviorweave/`](./skills/behaviorweave) | Canonical agent-oriented instructions and concise reference material. |
| Skill validation | [`validation/`](./validation) | Validation procedure and realistic activation/task matrix. |

The canonical skill follows the Agent Skills `SKILL.md` format: a directory-scoped Markdown instruction file with required `name` and `description` YAML frontmatter. Its `name` matches its containing directory (`behaviorweave`), and only the specification's required frontmatter is used for portability.

The authoritative documentation is at https://behaviorweave.readthedocs.io/en/latest/ and the source repository is https://github.com/smuniharish/behaviorweave.

Compatible agents should load [`skills/behaviorweave/SKILL.md`](./skills/behaviorweave/SKILL.md) when working on BehaviorWeave integrations, behavioral policy tuning, repeated tool-call loops, or runtime intervention design. The skill links to the repository's authoritative documentation and examples instead of maintaining a second copy of them.

## Maintaining the distribution

When BehaviorWeave's public API, supported integrations, or documented behavior changes:

1. Update the canonical skill and only the reference material affected by that verified change.
2. Link to the corresponding implementation, tests, examples, or documentation; do not duplicate runtime logic.
3. Run the validation process in [`validation/README.md`](./validation/README.md).
4. Do not add platform-specific copies of the skill text. Add thin metadata only when a host's current official documentation demonstrates it is required.

The distribution is covered by the repository's Apache License 2.0; see the [repository license](https://github.com/smuniharish/behaviorweave/blob/master/LICENSE).

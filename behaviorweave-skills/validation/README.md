# BehaviorWeave Agent Skill validation

This directory documents the repeatable validation process for the canonical skill. It is intentionally not a second runtime test suite and does not provide a host-specific package.

The authoritative documentation for this package is https://behaviorweave.readthedocs.io/en/latest/ and the source repository is https://github.com/smuniharish/behaviorweave.

The Agent Skills specification defines `name` and `description` as the required frontmatter. No official validator is specified there, so validation combines structural checks with source-backed content review.

## Structural validation

For every change:

1. Confirm [`../skills/behaviorweave/SKILL.md`](../skills/behaviorweave/SKILL.md) exists and starts with YAML frontmatter.
2. Confirm `name` is exactly `behaviorweave` (the directory name), contains only lowercase letters and hyphens, and is at most 64 characters.
3. Confirm `description` is non-empty, at most 1024 characters, and states both the capability and when to activate it.
4. Confirm only `name` and `description` appear in frontmatter unless a current specification and demonstrated host requirement justify more.
5. Resolve every relative Markdown target in the skill, its references, and this directory; no target may point to a deleted file.
6. Confirm the distribution contains one `skills/behaviorweave/` canonical knowledge source and no duplicate host-specific copies.
7. Search the distribution for stale package names, invented CLI commands, credentials, or unrelated project references.

## Source-accuracy review

Review every code snippet and factual claim against its source:

| Claim area | Source of truth |
| --- | --- |
| Public import and package version | [`../../src/behaviorweave/__init__.py`](../../src/behaviorweave/__init__.py) |
| Engine and policy evaluation flow | [`../../src/behaviorweave/engine.py`](../../src/behaviorweave/engine.py) |
| Built-in patterns and state tracking | [`../../src/behaviorweave/patterns.py`](../../src/behaviorweave/patterns.py) |
| Policy rules and intervention mapping | [`../../src/behaviorweave/policies.py`](../../src/behaviorweave/policies.py) |
| Events and observable data model | [`../../src/behaviorweave/events.py`](../../src/behaviorweave/events.py) |
| State store and cooldown semantics | [`../../src/behaviorweave/state.py`](../../src/behaviorweave/state.py) |
| Supported behavior and design principles | [`../../docs/index.md`](../../docs/index.md), [`../../docs/quickstart.md`](../../docs/quickstart.md), [`../../docs/patterns.md`](../../docs/patterns.md), [`../../docs/policies.md`](../../docs/policies.md) |
| Executable workflows and examples | [`../../examples/`](../../examples) and [`../../tests/`](../../tests) |

If a behavior lacks an implementation, test, or authoritative source, omit it from the skill rather than infer a public API.

## Agent-task matrix

The following matrix was reviewed against the canonical [`SKILL.md`](../skills/behaviorweave/SKILL.md), the supporting references, and the runtime implementation.

| Task | Activates | Grounded route | Avoids |
| --- | --- | --- | --- |
| “Add BehaviorWeave to my LangChain tool boundary.” | Yes | `references/integration.md` and the public `BehaviorEvent`/`BehaviorEngine` API. | Invented adapter APIs or prompt-only guardrails. |
| “My agent keeps retrying the same tool.” | Yes | Built-in pattern mapping and policy rule guidance. | Blindly mapping every loop to `STOP` or a generic guardrail. |
| “My node or delegation loop is repeating.” | Yes | Built-in `repeated_node_execution` and `delegation_streak` patterns. | Silently ignoring `scope` or concurrency semantics. |
| “Define a custom pattern for repeated behavior.” | Yes | Custom `Pattern` guidance in the skill and docs. | Copying built-in pattern logic or inventing a second runtime API. |
| “Configure production-grade policy thresholds.” | Yes | `PolicyRule`, `cooldown`, `once_only`, and priority semantics. | Hard-coded thresholds without observing runtime behavior. |
| “Debug why my intervention never fires.” | Yes | Event-stream and state debugging guidance. | Guessing from prompt text or changing internal state manually. |

## Repository validation

Skill-only work should at least run the structural/link/source review above and review the resulting Git diff. If runtime files change, run the CI-equivalent checks documented in [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md). This distribution must not require a BehaviorWeave runtime change.

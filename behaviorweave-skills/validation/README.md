# Validating the BehaviorWeave skill

## Automated checks

Run from the repository root:

```bash
uv run pytest tests/test_skill.py
uvx --from skills-ref agentskills validate behaviorweave-skills/skills/behaviorweave
```

`tests/test_skill.py` runs offline in continuous integration. It checks that:

- the skill passes the reference validator, `skills-ref`, which applies the specification's
  rules for `name`, `description`, `compatibility`, and the other frontmatter fields;
- `name` matches the directory, `license` is `Apache-2.0`, and `metadata.version` equals the
  package version;
- `SKILL.md` has fewer than 500 lines, and `references/` is one level deep;
- every relative link in the skill resolves;
- `scripts/verify_setup.py` passes, with warnings treated as errors;
- `assets/test_behavior_policy.py` passes.

`tests/test_docs.py` also runs every Python snippet in the skill that is not marked
`<!-- skip-snippet: ... -->` and compares each `print(...)  # expected` comment with the
actual output.

## Source review

Automated checks cannot tell whether guidance is correct. For every change, check each
snippet and claim against its source:

| Claim area | Source of truth |
| --- | --- |
| Public imports and the package version | [`src/behaviorweave/__init__.py`](../../src/behaviorweave/__init__.py) and [`pyproject.toml`](../../pyproject.toml) |
| Engine flow, precedence, and idempotency | [`src/behaviorweave/engine.py`](../../src/behaviorweave/engine.py) |
| Built-in patterns and counting rules | [`src/behaviorweave/patterns.py`](../../src/behaviorweave/patterns.py) |
| Policy rules, cooldowns, and once-only | [`src/behaviorweave/policies.py`](../../src/behaviorweave/policies.py) |
| Events, identities, and fingerprints | [`src/behaviorweave/events.py`](../../src/behaviorweave/events.py) |
| State, stores, and serialization | [`src/behaviorweave/state.py`](../../src/behaviorweave/state.py) |
| Middleware and adapters | [`src/behaviorweave/integrations/`](../../src/behaviorweave/integrations/) |
| Documented behavior | [`docs/`](../../docs/), especially `policies.md`, `state.md`, and `integrations/` |
| Working patterns | [`examples/`](../../examples/) and [`tests/`](../../tests/) |

If a behavior has no implementation, test, or documentation, leave it out of the skill rather
than infer it.

## Activation matrix

Review that the description and instructions lead an agent to the right route for each task:

| Task | Activates | Route | Avoids |
| --- | --- | --- | --- |
| "Add BehaviorWeave to my LangChain agent." | Yes | `BehaviorWeaveMiddleware` in `create_agent(middleware=[...])`, scoped by `thread_id`. | Hand-written tool guards or invented adapter APIs. |
| "My agent keeps calling the same tool." | Yes | `repeated_tool_call` with a nudge-then-stop ladder. | Prompt-only "do not repeat" instructions. |
| "My tool keeps failing and the agent keeps retrying." | Yes | `failure_streak` or `retry_streak`, with outcomes tracked by the middleware. | Ad hoc retry counters beside the engine. |
| "Two agents keep handing the task back and forth." | Yes | `oscillation` with handoff or delegation events. | Treating ping-pong as a consecutive repeat. |
| "My graph node loops." | Yes | `repeated_node_execution` or an `event_frequency` budget, routed in a conditional edge. | Changing graph internals or only raising the recursion limit. |
| "Pause for a human when the agent is stuck." | Yes | A `human_review` rule on tool calls with `interrupt()` in `on_decision`, or a `pause` rule on outcomes with `release(scope)` from the application before resuming; a checkpointer either way. | Skipping duplicates around `interrupt()`, or releasing a halt from inside the hook. |
| "Why does my intervention never fire?" | Yes | Troubleshooting: event types, identities, scopes, resets, cooldowns, and once-only. | Guessing from prompt text or editing state keys. |
| "Classify whether my agent is behaving well with an LLM." | No | Not this package's purpose. | Inventing model-based detectors. |

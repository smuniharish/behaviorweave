---
description: Install the BehaviorWeave Agent Skill so coding agents can integrate, configure, test, and debug BehaviorWeave.
---

# Agent Skills

BehaviorWeave publishes two portable Agent Skills that teach coding agents how to integrate,
configure, test, debug, and extend BehaviorWeave. Skills are guidance for agents; installing
them does not install or change Python packages.

| Component | Location |
| --- | --- |
| Integration skill | [`behaviorweave`](https://github.com/smuniharish/behaviorweave/tree/master/behaviorweave-skills/skills/behaviorweave) |
| Extension skill | [`behaviorweave-extend`](https://github.com/smuniharish/behaviorweave/tree/master/behaviorweave-skills/skills/behaviorweave-extend) |

## What the skill contains

The skill follows the [Agent Skills specification](https://agentskills.io/specification).
Agents read `SKILL.md` first and open the other files only when a task needs them:

- **`SKILL.md`**: when to use the skill, the core workflow, and the rules an integration
  follows. Its frontmatter has `name`, `description`, `license`, `compatibility`, and
  `metadata.version`, the BehaviorWeave release it describes.
- **`references/API.md`**: public imports, signatures, defaults, and decision fields.
- **`references/RECIPES.md`**: complete patterns for guarding agents, graphs, multi-agent
  handoffs, retry loops, and MCP servers; human review; cooldowns; provenance audits; durable
  state; and audit logs.
- **`references/TROUBLESHOOTING.md`**: symptoms, causes, and fixes.
- **`scripts/verify_setup.py`**: an offline check that the project's environment has
  compatible versions, and that a guarded agent, a guarded graph, and provenance mapping work.
- **`assets/test_behavior_policy.py`**: a pytest template that tests an application's
  policies: escalation, argument and scope isolation, redelivery, and cooldowns.

The repository validates the skill on every change: the reference validator, link checks,
every runnable recipe, the setup script, and the template run in its test suite. There is no
separate Claude, Codex, Cursor, or Copilot copy of the skill.

## Install from skills.sh

The [skills CLI](https://www.skills.sh/docs/cli) installs skills from a GitHub source:

```bash
npx skills add https://github.com/smuniharish/behaviorweave/tree/master/behaviorweave-skills/skills/behaviorweave
```

Follow the CLI's prompts to choose a target, then check that it placed the `behaviorweave`
folder in the target agent's skills directory.

## Install manually

Copy the complete `behaviorweave` directory, including `references/`, `scripts/`, and
`assets/`, into one of the locations below. `SKILL.md` links to the other files, so do not
copy it alone.

| Host | Current repository | All projects |
| --- | --- | --- |
| Claude Code | `.claude/skills/behaviorweave/` | `~/.claude/skills/behaviorweave/` |
| Codex | `.agents/skills/behaviorweave/` | `~/.agents/skills/behaviorweave/` |
| Cursor | `.agents/skills/behaviorweave/` or `.cursor/skills/behaviorweave/` | `~/.agents/skills/behaviorweave/` or `~/.cursor/skills/behaviorweave/` |
| GitHub Copilot | `.agents/skills/behaviorweave/`, `.github/skills/behaviorweave/`, or `.claude/skills/behaviorweave/` | `~/.agents/skills/behaviorweave/` or `~/.copilot/skills/behaviorweave/` |

Restart or reload the host after copying, then confirm that it lists `behaviorweave`. Hosts
select the skill automatically from its description, or you can invoke it explicitly:

- **Claude Code:** `/behaviorweave`. See [Claude Code skills](https://code.claude.com/docs/en/skills).
- **Codex:** `$behaviorweave`, or `/skills` to list skills.
- **Cursor:** type `/` in Agent chat and select `behaviorweave`. See
  [Cursor Agent Skills](https://cursor.com/docs/skills).
- **GitHub Copilot CLI:** `/skills reload`, then `/skills info behaviorweave`. See
  [adding agent skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills).

For other compatible hosts, copy the directory into the host's documented skills location.
The skill relies only on standard frontmatter, so no host-specific adapter is needed.

## Update and verify

To update a manual installation, replace the installed `behaviorweave` directory with the
latest one from the repository, then reload the host. From your project's Python environment,
the setup check should pass:

```bash
python <skills directory>/behaviorweave/scripts/verify_setup.py
```

The output lists the installed versions and verifies the policy ladder, replay,
middleware, graph loop, and agxai provenance. It ends with `All checks passed.`.

See the distribution's
[README](https://github.com/smuniharish/behaviorweave/blob/master/behaviorweave-skills/README.md)
and [validation process](https://github.com/smuniharish/behaviorweave/blob/master/behaviorweave-skills/validation/README.md)
for maintenance details.

## Extension skill

`behaviorweave-extend` covers async ABC implementations for stores, patterns, and sinks,
plus distributed atomicity and contract tests. Install it from the same skills directory.
The root `skills.sh.json` makes both skills discoverable. Evaluation prompts and expected
routes live in `behaviorweave-skills/validation/evals.json`.

## Upstream skills

These independently maintained skills are optional and do not install Python dependencies.
Use a compatible Agent Skills host and Node.js 22.20 or newer for the skills CLI. After
installation, reload the agent and use the relevant skill for the task; consult the upstream
documentation for host-specific setup and compatibility.

| Upstream | Skills | Purpose |
| --- | --- | --- |
| [agxai](https://agxai.readthedocs.io/en/latest/agent-skills/install/) | `agxai`, `agxai-extend` | Integrate provenance or extend agxai providers. |
| [LangChain](https://github.com/langchain-ai/langchain-skills) | `langchain-build-agent`, `langchain-agent-tracing`, `langchain-agent-monitoring`, `langchain-eval-engineering` | Build agents and work with LangSmith tracing, monitoring, and evaluation. |
| [Langfuse](https://github.com/langfuse/skills) | `langfuse`, `migrate-to-langfuse` | Integrate Langfuse or migrate observability data. |
| [Pydantic](https://pydantic.dev/articles/pydantic-ai-logfire-claude-code-skills) | `pydantic` | Work with the validation library used by upstream dependencies. |
| [Redis](https://redis.io/docs/latest/develop/setup/build-with-an-agent/) | `redis-core`, `redis-connections`, `redis-security` | Work with data, connections, and security for the optional Redis store. |

Install the skill you need, for example:

```bash
npx skills add smuniharish/agxai --skill agxai
npx skills add smuniharish/agxai --skill agxai-extend
npx skills add langchain-ai/langchain-skills --skill langchain-build-agent
npx skills add langchain-ai/langchain-skills --skill langchain-agent-tracing
npx skills add langchain-ai/langchain-skills --skill langchain-agent-monitoring
npx skills add langchain-ai/langchain-skills --skill langchain-eval-engineering
npx skills add langfuse/skills --skill langfuse
npx skills add langfuse/skills --skill migrate-to-langfuse
npx skills add pydantic/skills --skill pydantic
npx skills add redis/agent-skills
```

LangChain notes that its skills are in early development. Langfuse operations require a
configured account and credentials; LangSmith workspace operations require appropriate
workspace access. Follow the upstream instructions rather than placing credentials in skills
or repository files. No independently installable skill is assumed for other dependencies.

For development tools, [Astral's plugin](https://github.com/astral-sh/agent-plugins) supplies
`uv` and `ruff` skills. In Codex, install it with:

```bash
codex plugin marketplace add astral-sh/agent-plugins
codex plugin add astral@astral-sh
```

Invoke them as `$astral:uv` or `$astral:ruff`. Claude Code installation and invocation are
documented by Astral; the plugin also includes an optional `ty` skill.

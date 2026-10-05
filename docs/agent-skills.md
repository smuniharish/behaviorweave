---
description: Install the BehaviorWeave Agent Skill so coding agents can integrate, configure, test, and debug BehaviorWeave.
---

# Agent Skills

BehaviorWeave publishes one portable Agent Skill that teaches coding agents how to integrate,
configure, test, and debug BehaviorWeave in an application. The skill is guidance for agents;
it is not part of the Python package and does not change how BehaviorWeave is installed.

| Component | Location |
| --- | --- |
| The Agent Skill | [`behaviorweave-skills/skills/behaviorweave/`](https://github.com/smuniharish/behaviorweave/tree/master/behaviorweave-skills/skills/behaviorweave) |
| Its instructions | [`SKILL.md`](https://github.com/smuniharish/behaviorweave/blob/master/behaviorweave-skills/skills/behaviorweave/SKILL.md) |

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

```text
PASS  Python 3.12.14 (3.12 or newer required)
PASS  behaviorweave 1.0.0 (1.x expected by this skill)
PASS  langchain 1.4.3 (>=1.4.3,<2 required)
PASS  langchain-core 1.6.6 (>=1.6.6,<2 required)
PASS  langgraph 1.2.12 (>=1.2.12,<2 required)
PASS  langgraph-xai 1.0.0 (>=1.0.0,<2 required)
INFO  optional packages: langchain-openai 1.6.7, deepagents 0.7.21, langgraph-swarm 0.1.0, mcp 2.3.0
PASS  policy ladder decided ['noop', 'nudge', 'stop']
PASS  a redelivered event repeats its original intervention, marked duplicate
PASS  middleware guided the second call and blocked the third (2 tool runs)
PASS  LangGraph loop stopped by policy after 3 steps
PASS  langgraph-xai provenance mapped: 2 tool executions, decision linked to its provenance record
All checks passed.
```

See the distribution's
[README](https://github.com/smuniharish/behaviorweave/blob/master/behaviorweave-skills/README.md)
and [validation process](https://github.com/smuniharish/behaviorweave/blob/master/behaviorweave-skills/validation/README.md)
for maintenance details.

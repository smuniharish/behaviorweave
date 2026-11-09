---
description: Install the BehaviorWeave Agent Skill so coding agents can integrate, configure, test, and debug BehaviorWeave.
---

# Agent Skills

BehaviorWeave publishes two portable Agent Skills that teaches coding agents how to integrate,
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

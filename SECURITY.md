# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 1.x | Yes |
| < 1.0 | No |

## Reporting a vulnerability

Please do not report security issues through public issues, discussions, or pull requests.
Report them privately through
[GitHub private vulnerability reporting](https://github.com/smuniharish/behaviorweave/security/advisories/new).

Include the affected version, a description of the issue, steps to reproduce it, and its
impact. Reports are acknowledged and triaged as quickly as possible, and you will be kept
informed until a fix is released.

## Security model

- BehaviorWeave records observable execution metadata only. It never captures private model
  reasoning.
- Tool calls are identified by the tool name and a SHA-256 digest of their arguments; raw
  argument values are never used as identities or stored in pattern state.
- Event metadata is application context, not a vault. Do not put secrets, tokens, or prompts
  containing credentials in events, and redact sensitive tool arguments before reporting.
- Policies are plain data. Serialized state is JSON and is never evaluated as code.
- The in-memory state store is process-local and is not a durable security boundary.

See the [security and privacy guide](https://behaviorweave.readthedocs.io/en/latest/security/)
for details.

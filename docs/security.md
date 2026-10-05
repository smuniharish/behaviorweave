# Security and privacy

BehaviorWeave evaluates observable execution metadata. It is designed so that the data it
keeps is minimal, bounded, and free of model reasoning.

## What BehaviorWeave stores

| Data | Where | Notes |
| --- | --- | --- |
| Event identity | Pattern state | Tool calls are identified by the tool name and a SHA-256 digest of the arguments, never by raw argument values. |
| Counts and timestamps | Pattern state | Current count, run start, last event time. |
| Recent event IDs and decisions | Pattern state | The 256 most recent IDs per history and the decisions emitted for them, for idempotency. |
| Fired policies and cooldowns | Pattern state | Policy IDs and cooldown expiry times. |
| Halted scopes | `BehaviorWeaveMiddleware` memory | Scopes halted by an outcome decision, until released. |

Events themselves are not stored. If you configure an `audit_sink`, the records it receives
contain the full event, including its metadata, and their retention is up to you.

## Guidance

- **Keep secrets out of events.** Never put credentials, tokens, or private model reasoning
  in event metadata. `BehaviorEvent.tool_call` records tool arguments in
  `metadata["arguments"]`, and `BehaviorWeaveMiddleware` reports every tool call this way,
  so `on_decision` hooks and audit sinks receive the arguments. Redact sensitive arguments
  before reporting events, and treat audit records with the same care as the tool calls
  themselves.
- **Choose scopes deliberately.** A scope is an isolation boundary. Include the tenant in
  multi-tenant scopes, for example `"tenant-7:thread-42"`.
- **Treat the in-memory store as process-local.** It is not a durable or shared security
  boundary. Release finished conversations with `clear(scope)` or a `ttl`.
- **Keep credentials in the environment.** The examples read provider credentials only from
  environment variables; `.env` files are git-ignored.
- **No code execution from configuration.** Policies are plain data. Serialized states are
  JSON and are never evaluated.

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub security advisories](https://github.com/smuniharish/behaviorweave/security/advisories/new)
rather than public issues. See the repository's
[security policy](https://github.com/smuniharish/behaviorweave/blob/master/SECURITY.md) for
supported versions and response expectations.

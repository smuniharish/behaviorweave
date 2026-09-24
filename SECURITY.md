# Security

BehaviorWeave records observable execution metadata only. Do not put secrets, tokens,
prompts containing credentials, or private model reasoning in event metadata. State
serialization uses JSON and never evaluates policy strings or arbitrary code.

In-memory state is process-local and should not be treated as a durable security
boundary. Validate and redact payloads at the integration boundary.

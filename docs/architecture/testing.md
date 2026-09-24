# Testing strategy

Unit tests cover immutable events, fingerprints, detectors, state, policy precedence,
crossing, cooldown, scopes, and serialization. Integration tests use deterministic
LangGraph graphs and adapter payloads. Concurrency tests exercise 100 simultaneous
events and verify atomic state updates. Provider credentials are never required.


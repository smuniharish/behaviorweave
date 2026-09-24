# Project structure

```text
src/behaviorweave/
  events.py                  immutable normalized events
  state.py                   scoped atomic state store
  patterns.py                composable behavioral detectors
  policies.py                deterministic policy rules
  interventions.py           decision and explanation models
  engine.py                  orchestration boundary
  integrations/              LangGraph, LangChain, and xAI adapters
tests/                       deterministic unit and concurrency coverage
examples/                    provider-free runnable demonstrations as single files
docs/                        user, architecture, and compatibility documentation
```

Framework integrations translate observations only. Core modules never import private
LangGraph or LangChain internals.

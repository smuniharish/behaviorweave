# Architecture overview

## The problem

Graph agents repeat tool calls, retry failing dependencies, bounce work between agents, and
delegate without converging. LangGraph executes these behaviors correctly; it is not its job
to judge them. Prompt instructions such as "do not repeat yourself" are not enforceable and
carry no memory across steps. Applications need a separate, deterministic layer that
remembers observable behavior per conversation, applies explicit thresholds and cooldowns,
and tells the host what to do.

## The design

BehaviorWeave separates *what is happening* from *what should happen* and from *what the
host does about it*:

![BehaviorWeave architecture](../assets/diagrams/architecture.png)

| Stage | Responsibility |
| --- | --- |
| Integrations | Translate framework activity into normalized events, using public APIs only. |
| `BehaviorEvent` | Immutable, validated observation with a deterministic identity. |
| Patterns | Detect behavior and advance scoped state atomically; never decide. |
| State store | Hold per-history state with atomic updates, expiry, and idempotency. |
| Policies | Map pattern counts to interventions with precedence, cooldowns, and once-only. |
| `InterventionDecision` | Typed, explained request; the host decides how to apply it. |

## Responsibilities

| Component | Owns |
| --- | --- |
| LangGraph | Graph execution, routing, persistence, interrupts. |
| LangChain | Agent, model, and tool abstractions; the middleware lifecycle. |
| langgraph-xai | Execution context, provenance, evidence, and explanation records. |
| BehaviorWeave | Event normalization, fingerprints, patterns, state, policies, decisions, audit records. |
| Your application | Choosing scopes, configuring policies, and applying decisions. |

## Design principles

- **Detection, decisions, and execution stay separate.** Patterns detect behavior and keep
  state, policies map pattern counts to interventions, and the host applies them. Each part
  is testable on its own. The engine never stops, reroutes, or mutates your graph; the
  optional LangChain middleware applies decisions only at the tool-call boundary, as you
  configure it.
- **Scope is explicit.** Every event names its scope (a thread, run, or tenant-qualified
  session), so state never leaks between conversations or tenants.
- **State transitions are atomic and idempotent.** A redelivered event changes nothing and
  repeats its decision, a once-only policy fires exactly once even when workers race, and a
  cooldown on one policy never mutes another policy's escalation.
- **Precedence is deterministic.** When several rules or patterns apply, one stable decision
  wins, chosen by priority, terminal kind, count, and declaration order.
- **You pay only for what you use.** Only patterns referenced by a policy are evaluated;
  unused patterns cost nothing and keep no state.
- **Privacy is built in.** Tool calls are identified by name and a SHA-256 digest of their
  arguments; raw argument values and model reasoning are never stored.
- **Integrations use public framework APIs.** LangChain, LangGraph, and langgraph-xai are
  integrated at their public boundaries without monkey-patching, and LangGraph Swarm and Deep
  Agents remain optional.
- **The state-store boundary is minimal.** A durable store implements one atomic `update`
  operation, so new backends never require engine changes.

## Goals

- Deterministic, reproducible behavioral detection and policy evaluation.
- Explicit scope, idempotency, cooldown, and once-only semantics.
- Correct in-process concurrency, with a clean boundary for durable stores.
- A small, typed, documented public API with framework integrations at the edges.
- Explainable decisions and immutable audit records that never contain model reasoning.

## Non-goals

BehaviorWeave is not an agent framework, a model provider abstraction, an observability
platform, a structured-output parser, an intervention executor, or a semantic classifier.
Redis, PostgreSQL, OpenTelemetry, LangSmith, provider SDKs, LangGraph Swarm, and Deep Agents
are not required to use it.

## Further reading

- [Failure semantics](failure-strategy.md): which errors are raised, and when.
- [State and concurrency](../state.md): the guarantees under concurrent use.
- [Security and privacy](../security.md): what BehaviorWeave stores and how to keep it safe.

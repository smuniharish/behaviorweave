# Architecture Decision Records

This page is the authoritative, consolidated record of BehaviorWeave architecture
decisions. Each record states the decision, why it was made, and the resulting
trade-off. All records are **Accepted** for the 0.1.0 alpha unless explicitly changed
by a later ADR.

## Decision index

| ADR | Decision | Primary consequence |
|---|---|---|
| 0001 | Focus on LangGraph and LangChain | Not a generic event-processing framework |
| 0002 | Require `langgraph-xai` | Provenance is consumed, not recreated |
| 0003 | Exclude `xstructured` | Parsing concerns stay out of scope |
| 0004 | Separate patterns from policies | Detection is reusable and deterministic |
| 0005 | Model interventions as decisions | The host owns execution/control flow |
| 0006 | Use an extensible state boundary | Durable stores can be added later |
| 0007 | Require explicit scope isolation | State cannot leak across tenants/runs |
| 0008 | Lock in-memory updates | Safe in one process, not distributed-safe |
| 0009 | Make delivery idempotent | Duplicate events are deterministic no-ops |
| 0010 | Keep temporal semantics distinct | Streaks are not frequency windows |
| 0011 | Define policy precedence | Competing policies produce one stable outcome |
| 0012 | Keep LangGraph at an adapter boundary | No policy logic in graph callbacks |
| 0013 | Keep LangChain at an adapter boundary | No private API use or monkey patching |
| 0014 | Keep Swarm optional | Core install remains focused |
| 0015 | Keep Deep Agents optional | Core install remains focused |
| 0016 | Keep a small public API | Internals stay evolvable |

## ADR-0001 — LangGraph and LangChain focus

**Status:** Accepted  
**Decision:** BehaviorWeave is designed around LangGraph/LangChain execution semantics,
with framework-neutral internal domain models and explicit adapters.

**Rationale:** Patterns such as tools, nodes, handoffs, delegation, and retries have
clear meaning in these runtimes. Making the package a general event bus would obscure
the domain and enlarge the API without improving its primary use case.

**Consequences:** The core remains testable without framework objects, while adapters
own normalization. Non-LangGraph frameworks require a deliberate future adapter.

## ADR-0002 — `langgraph-xai` is mandatory

**Status:** Accepted  
**Decision:** `langgraph-xai` is a normal runtime dependency and its public
`XAIRuntime.instrument` integration is used for graph provenance/context.

**Rationale:** Execution context and provenance are first-class inputs to behavioral
explanation. Reimplementing explainability would duplicate a dedicated subsystem.

**Consequences:** BehaviorWeave stores provenance references and observable metadata
only. It does not capture private reasoning or import xAI private modules.

## ADR-0003 — Exclude `xstructured`

**Status:** Accepted  
**Decision:** Do not depend on or integrate `xstructured`.

**Rationale:** Structured-output parsing is not behavioral detection or intervention.
Keeping it separate avoids coupling unrelated release cycles and configuration.

**Consequences:** Applications may use structured-output libraries independently; they
are not part of BehaviorWeave's supported core surface.

## ADR-0004 — Separate patterns, policies, and interventions

**Status:** Accepted  
**Decision:** Pattern detectors report *what happened*, policy rules decide *what
should happen*, and interventions represent *the decision emitted*.

**Rationale:** Combining these concerns makes a detector unusable outside one response
strategy and makes threshold/cooldown behavior hard to reason about.

**Consequences:** Adding a detector does not require adding intervention behavior.
Policy composition and precedence can be tested independently.

## ADR-0005 — Intervention decisions are not executors

**Status:** Accepted  
**Decision:** Interventions are immutable, typed decisions; BehaviorWeave never stops,
pauses, redirects, or invokes arbitrary host code itself.

**Rationale:** LangGraph owns runtime lifecycle and routing. A policy library should
not silently take control of an application's graph.

**Consequences:** Hosts translate `STOP`, `PAUSE`, `FORCE_SYNTHESIS`, and similar
decisions into runtime-specific actions.

## ADR-0006 — State store protocol

**Status:** Accepted  
**Decision:** Define a stable state-management boundary with a local default and
support for future durable providers.

**Rationale:** State is required for temporal patterns, but Redis/PostgreSQL must not be
mandatory for local use or examples.

**Consequences:** A durable provider can preserve the behavioral contract without
changing policy logic or application-facing policy configuration.

## ADR-0007 — Explicit scope isolation

**Status:** Accepted  
**Decision:** Every behavioral state key includes an explicit scope, and engines are
instance-owned rather than global singletons.

**Rationale:** User, tenant, thread, run, and agent data must not contaminate one
another.

**Consequences:** Callers must provide a meaningful scope. Multiple engines can safely
coexist in one process.

## ADR-0008 — In-process concurrency contract

**Status:** Accepted  
**Decision:** The in-memory store serializes atomic updates with a re-entrant lock.

**Rationale:** State updates must not lose events under concurrent tool invocations.

**Consequences:** The implementation is safe for threads and async workloads within one
process. It explicitly makes no distributed/process-safety claim.

## ADR-0009 — Idempotent event delivery

**Status:** Accepted  
**Decision:** Track bounded event identifiers in state and treat duplicate delivery as
a no-op.

**Rationale:** Graph and callback systems can replay or redeliver observations.

**Consequences:** Replays are deterministic. Retention is bounded, so long-running
durable systems should supply an appropriate persistent store.

## ADR-0010 — Distinct temporal semantics

**Status:** Accepted  
**Decision:** Consecutive streaks, frequency counts, and time-window patterns are
separate semantics.

**Rationale:** “Three consecutive failures” is not equivalent to “three failures in
five minutes.”

**Consequences:** Detector names and state must make their retention/window behavior
explicit; policies do not infer temporal meaning from a bare count.

## ADR-0011 — Deterministic policy precedence

**Status:** Accepted  
**Decision:** Rules are selected deterministically by priority, threshold, terminal
intervention status, and stable declaration order.

**Rationale:** Multiple matching policies must never produce ambiguous host behavior.

**Consequences:** `STOP`/`PAUSE` can supersede lower-severity outcomes. Tests protect
threshold crossing and cooldown behavior.

## ADR-0012 — LangGraph integration boundary

**Status:** Accepted  
**Decision:** LangGraph adapters normalize public node/tool/runtime observations but do
not embed policy evaluation in graph callbacks.

**Rationale:** Graph structure and lifecycle belong to LangGraph; behavior decisions
belong to BehaviorWeave.

**Consequences:** Hosts choose how decisions influence routing, interrupts, or state.
The live examples demonstrate an explicit graph node around this boundary.

## ADR-0013 — LangChain integration boundary

**Status:** Accepted  
**Decision:** Use current public LangChain v1 APIs, including `create_agent`, tools,
and MCP support; never monkey-patch private internals.

**Rationale:** Private APIs create upgrade risk and make agent behavior difficult to
test or support.

**Consequences:** LangChain is a core dependency. Provider integrations remain optional
extras, and live credentials are environment-only.

## ADR-0014 — Swarm stays optional

**Status:** Accepted  
**Decision:** `langgraph-swarm` is an optional example/integration dependency.

**Rationale:** Swarm handoffs are useful behavioral signals but are not required by
every BehaviorWeave application.

**Consequences:** The live Swarm example uses public handoff APIs; core users do not
install Swarm transitively.

## ADR-0015 — Deep Agents stays optional

**Status:** Accepted  
**Decision:** `deepagents` is an optional example/integration dependency.

**Rationale:** Delegation and subagents are supported through normalized events without
requiring every package user to adopt Deep Agents.

**Consequences:** Live Deep Agent examples use `create_deep_agent` and `SubAgent`;
the core library remains independent from those types.

## ADR-0016 — Small intentional public API

**Status:** Accepted  
**Decision:** Export only the engine, normalized domain models, state store, pattern
interfaces, policy rules, and intervention types from the package root.

**Rationale:** A narrow typed surface supports compatibility and allows internals to
evolve.

**Consequences:** Integrations are explicit imports. Applications are not coupled to
implementation details that may change between releases.

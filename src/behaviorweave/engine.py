"""The BehaviorWeave engine: events in, one intervention decision out."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from ._util import freeze
from .errors import PolicyConfigurationError
from .events import BehaviorEvent
from .interventions import AuditRecord, Intervention, InterventionDecision, InterventionType
from .patterns import Pattern, PatternObservation, built_in_patterns
from .policies import PolicyEngine, PolicyRule, _decision, _suppression_reason
from .state import _EVENT_RETENTION, BehaviorState, BehaviorStateStore, InMemoryBehaviorStateStore

__all__ = ["AuditSink", "BehaviorEngine"]

type AuditSink = Callable[[AuditRecord], None]
"""Callable that receives one [`AuditRecord`][behaviorweave.AuditRecord] per processed event."""


@dataclass(frozen=True, slots=True)
class _Candidate:
    observation: PatternObservation
    rule: PolicyRule | None
    decision: InterventionDecision


class BehaviorEngine:
    """Detects behavioral patterns in events and returns intervention decisions.

    The engine is thread-safe: all state transitions go through the state store's atomic
    ``update``. Only patterns referenced by at least one policy are evaluated, so unused
    patterns cost nothing and keep no state.

    For each event the engine observes every matching pattern, evaluates its policies, and
    returns the strongest decision: actionable over `noop`, then higher rule ``priority``,
    then terminal interventions, then higher pattern count, then earlier pattern declaration.
    Only the returned decision is recorded against cooldowns and once-only history, and that
    record is made atomically, so a once-only policy fires exactly once even under contention.

    Event delivery is idempotent: once an event has been processed, processing it again
    changes no state. An actionable decision is returned again, marked ``duplicate``; any other
    decision, including a suppressed one, comes back as a `noop` marked ``duplicate``. A host
    that lost a decision (for example, because its process crashed or an interrupted graph step
    is resumed) can therefore process the same event again and apply the answer. A copy
    processed concurrently with the original is still counted once, but may receive a `noop`.
    Events that no policy's pattern observes leave no state behind, so processing them again
    returns an unmarked `noop`.

    Args:
        policies: Rules mapping pattern thresholds to interventions.
        patterns: Pattern detectors to provide. ``None`` selects
            [`built_in_patterns()`][behaviorweave.built_in_patterns]; an empty collection
            provides none.
        state_store: Store for pattern state. ``None`` creates an
            [`InMemoryBehaviorStateStore`][behaviorweave.InMemoryBehaviorStateStore].
        audit_sink: Optional callable receiving an [`AuditRecord`][behaviorweave.AuditRecord]
            for every processed event. It runs after the decision is recorded; if it raises,
            the exception propagates, and processing the same event again returns the decision.

    Raises:
        PolicyConfigurationError: If pattern IDs repeat, an item is not a pattern, or a policy
            references a pattern the engine does not provide.
    """

    def __init__(
        self,
        *,
        policies: Iterable[PolicyRule] = (),
        patterns: Iterable[Pattern] | None = None,
        state_store: BehaviorStateStore | None = None,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self.store: BehaviorStateStore = (
            state_store if state_store is not None else InMemoryBehaviorStateStore()
        )
        self.patterns: tuple[Pattern, ...] = (
            built_in_patterns() if patterns is None else tuple(patterns)
        )
        self.policy_engine = PolicyEngine(policies)
        self.audit_sink = audit_sink
        self._rules_by_id = {rule.policy_id: rule for rule in self.policy_engine.rules}

        provided: set[str] = set()
        for pattern in self.patterns:
            if not isinstance(pattern, Pattern):
                raise PolicyConfigurationError(
                    f"{type(pattern).__name__} does not implement the Pattern protocol"
                )
            if pattern.pattern_id in provided:
                raise PolicyConfigurationError(f"duplicate pattern_id {pattern.pattern_id!r}")
            provided.add(pattern.pattern_id)
        unknown = sorted(self.policy_engine.pattern_ids - provided)
        if unknown:
            raise PolicyConfigurationError(
                f"policies reference unknown pattern(s) {unknown}; "
                f"available patterns: {sorted(provided)}"
            )
        referenced = self.policy_engine.pattern_ids
        self._active: tuple[Pattern, ...] = tuple(
            pattern for pattern in self.patterns if pattern.pattern_id in referenced
        )

    @property
    def rules(self) -> tuple[PolicyRule, ...]:
        """The configured policy rules, in declaration order."""
        return self.policy_engine.rules

    def process(self, event: BehaviorEvent) -> InterventionDecision:
        """Process one event and return the decision for the host to apply.

        Processing an event whose ``event_id`` was already processed leaves state unchanged
        and returns the original decision marked ``duplicate``; when the original decision was
        a `noop`, including a suppressed one, the result is a plain `noop` marked
        ``duplicate``. An event that no policy's pattern observes always yields an unmarked
        `noop`.

        Args:
            event: The normalized runtime observation.

        Returns:
            The decision; its intervention is `noop` when no action is needed.
        """
        candidates: list[_Candidate] = []
        for pattern in self._active:
            if pattern.matches(event):
                observation = pattern.observe(event, self.store)
                if observation.accepted:
                    rule, decision = self.policy_engine._select(observation)
                else:
                    rule, decision = self._replay(event, observation)
                candidates.append(_Candidate(observation, rule, decision))

        chosen = self._resolve(event, candidates)
        if chosen is None:
            decision = InterventionDecision(Intervention(InterventionType.NOOP, scope=event.scope))
        else:
            decision = chosen.decision
            if event.provenance_ref and decision.explanation is not None:
                decision = replace(
                    decision,
                    explanation=replace(decision.explanation, provenance_ref=event.provenance_ref),
                )
        if self.audit_sink is not None:
            self.audit_sink(
                AuditRecord(
                    event=event,
                    pattern=chosen.observation.pattern_id if chosen is not None else None,
                    state=chosen.observation.state if chosen is not None else None,
                    decision=decision,
                )
            )
        return decision

    def _replay(
        self, event: BehaviorEvent, observation: PatternObservation
    ) -> tuple[PolicyRule | None, InterventionDecision]:
        """Rebuild the decision this pattern originally produced for a redelivered event."""
        record = next(
            (
                entry
                for entry in reversed(observation.state.emissions)
                if entry[0] == event.event_id
            ),
            None,
        )
        rule = self._rules_by_id.get(record[1]) if record is not None else None
        if record is None or rule is None or rule.pattern_id != observation.pattern_id:
            return self.policy_engine._select(observation)
        _, _, count, reason = record
        return rule, _decision(
            rule,
            pattern_id=observation.pattern_id,
            scope=observation.scope,
            count=count,
            reason=reason,
            duplicate=True,
        )

    def _resolve(self, event: BehaviorEvent, candidates: list[_Candidate]) -> _Candidate | None:
        fallback: _Candidate | None = None
        # sorted() is stable, so ties keep pattern declaration order.
        for candidate in sorted(candidates, key=_rank, reverse=True):
            if not candidate.decision.actionable:
                return fallback or candidate
            rule = candidate.rule
            if (
                candidate.decision.duplicate
                or rule is None
                or self._commit(event, candidate.observation, rule)
            ):
                return candidate
            # Another thread claimed the policy first; report this one as suppressed.
            fallback = fallback or _suppressed(candidate, event)
        return fallback

    def _commit(
        self, event: BehaviorEvent, observation: PatternObservation, rule: PolicyRule
    ) -> bool:
        record = (event.event_id, rule.policy_id, observation.count, observation.reason)
        claimed = False

        def claim(current: BehaviorState | None) -> BehaviorState:
            nonlocal claimed
            base = current if current is not None else observation.state
            if _suppression_reason(rule, base, event.timestamp) is not None:
                claimed = False
                return base
            claimed = True
            history = base.intervention_history
            if rule.policy_id not in history:
                history = (*history, rule.policy_id)
            cooldowns = base.cooldowns
            if rule.cooldown is not None:
                cooldowns = freeze({**cooldowns, rule.policy_id: event.timestamp + rule.cooldown})
            return replace(
                base,
                intervention_history=history,
                cooldowns=cooldowns,
                emissions=(*base.emissions[1 - _EVENT_RETENTION :], record),
                version=base.version + 1,
            )

        self.store.update(observation.state_key, claim)
        return claimed


def _rank(candidate: _Candidate) -> tuple[int, int, bool, int]:
    decision = candidate.decision
    if decision.actionable:
        status = 3
    elif decision.suppressed:
        status = 2
    elif decision.duplicate:
        status = 1
    else:
        status = 0
    priority = candidate.rule.priority if candidate.rule is not None else 0
    return (status, priority, decision.intervention.kind.is_terminal, candidate.observation.count)


def _suppressed(candidate: _Candidate, event: BehaviorEvent) -> _Candidate:
    decision = candidate.decision
    rule = candidate.rule
    policy = rule.policy_id if rule is not None else None
    reason = f"policy {policy!r} was already applied by a concurrent event"
    return replace(
        candidate,
        decision=InterventionDecision(
            Intervention(
                InterventionType.NOOP,
                reason=reason,
                pattern=decision.intervention.pattern,
                policy=policy,
                scope=event.scope,
            ),
            replace(decision.explanation, reason=reason) if decision.explanation else None,
            suppressed=True,
        ),
    )

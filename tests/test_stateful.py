"""Stateful model-based tests: the engine and the store against independent reference models."""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, initialize, rule

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    BehaviorState,
    EventType,
    InMemoryBehaviorStateStore,
    InterventionDecision,
    InterventionType,
    Outcome,
    PolicyRule,
)
from support import ManualClock, at

COOLDOWN = timedelta(seconds=30)
POLICIES = [
    PolicyRule("tool-nudge", "repeated_tool_call", 2, InterventionType.NUDGE, cooldown=COOLDOWN),
    PolicyRule("tool-stop", "repeated_tool_call", 4, InterventionType.STOP),
    PolicyRule("fail-escalate", "failure_streak", 2, InterventionType.ESCALATE, once_only=True),
    PolicyRule("ping-pong", "oscillation", 2, InterventionType.WARNING),
]


@dataclass
class ScopeModel:
    tool_fingerprint: str | None = None
    tool_run: int = 0
    nudge_until: datetime | None = None
    failures: int = 0
    escalated: bool = False
    handoffs: list[str] = field(default_factory=list)
    bounces: int = 0


@dataclass(frozen=True)
class Sent:
    event: BehaviorEvent
    matched: bool
    decision: InterventionDecision


class EngineMachine(RuleBasedStateMachine):
    sent = Bundle("sent")

    @initialize()
    def setup(self) -> None:
        self.engine = BehaviorEngine(policies=POLICIES)
        self.models: dict[str, ScopeModel] = {"a": ScopeModel(), "b": ScopeModel()}
        self.seconds = 0

    def _check(
        self, decision: InterventionDecision, kind: InterventionType, *, suppressed: bool = False
    ) -> None:
        assert decision.intervention.kind is kind
        assert decision.suppressed is suppressed
        assert not decision.duplicate

    @rule(seconds=st.integers(0, 40))
    def advance_clock(self, seconds: int) -> None:
        self.seconds += seconds

    @rule(
        target=sent, scope=st.sampled_from("ab"), name=st.sampled_from("xy"), arg=st.integers(0, 1)
    )
    def call_tool(self, scope: str, name: str, arg: int) -> Sent:
        event = BehaviorEvent.tool_call(name, {"arg": arg}, scope=scope, timestamp=at(self.seconds))
        model = self.models[scope]
        model.tool_run = model.tool_run + 1 if event.fingerprint == model.tool_fingerprint else 1
        model.tool_fingerprint = event.fingerprint
        decision = self.engine.process(event)
        if model.tool_run >= 4:
            self._check(decision, InterventionType.STOP)
        elif model.tool_run >= 2:
            if model.nudge_until is not None and model.nudge_until > event.timestamp:
                self._check(decision, InterventionType.NOOP, suppressed=True)
            else:
                self._check(decision, InterventionType.NUDGE)
                model.nudge_until = event.timestamp + COOLDOWN
        else:
            self._check(decision, InterventionType.NOOP)
        return Sent(event, matched=True, decision=decision)

    @rule(target=sent, scope=st.sampled_from("ab"), outcome=st.sampled_from(list(Outcome)))
    def report_outcome(self, scope: str, outcome: Outcome) -> Sent:
        event = BehaviorEvent.outcome_event(outcome, scope=scope, timestamp=at(self.seconds))
        model = self.models[scope]
        decision = self.engine.process(event)
        if outcome is Outcome.FAILURE:
            model.failures += 1
        elif outcome is Outcome.SUCCESS:
            model.failures = 0
        if outcome is Outcome.FAILURE and model.failures >= 2:
            if model.escalated:
                self._check(decision, InterventionType.NOOP, suppressed=True)
            else:
                self._check(decision, InterventionType.ESCALATE)
                model.escalated = True
        else:
            self._check(decision, InterventionType.NOOP)
        return Sent(event, matched=outcome is not Outcome.RETRY, decision=decision)

    @rule(
        target=sent,
        scope=st.sampled_from("ab"),
        source=st.sampled_from("pq"),
        target_agent=st.sampled_from("pqr"),
    )
    def hand_off(self, scope: str, source: str, target_agent: str) -> Sent:
        event = BehaviorEvent(
            EventType.AGENT_HANDOFF,
            scope=scope,
            agent_name=source,
            target_agent=target_agent,
            timestamp=at(self.seconds),
        )
        model = self.models[scope]
        identity = event.identity()
        history = model.handoffs
        bounced = len(history) >= 2 and identity == history[-2] and identity != history[-1]
        model.bounces = model.bounces + 1 if bounced else 0
        history.append(identity)
        decision = self.engine.process(event)
        expected = InterventionType.WARNING if model.bounces >= 2 else InterventionType.NOOP
        self._check(decision, expected)
        return Sent(event, matched=True, decision=decision)

    @rule(previous=sent)
    def redeliver(self, previous: Sent) -> None:
        decision = self.engine.process(previous.event)
        assert decision.duplicate is previous.matched
        if previous.decision.actionable:
            assert decision == replace(previous.decision, duplicate=True)
        else:
            assert not decision.actionable


TestEngineMachine = EngineMachine.TestCase

# Keys start with their scope, so the model can tell which scope a key belongs to.
KEYS = st.sampled_from(["a|repeats", "a|streak", "b|repeats"])


class StoreMachine(RuleBasedStateMachine):
    """The in-memory store against a dictionary model, with expiry on a manual clock."""

    @initialize(ttl=st.sampled_from([None, 5, 30]))
    def setup(self, ttl: int | None) -> None:
        self.clock = ManualClock()
        self.ttl = timedelta(seconds=ttl) if ttl is not None else None
        self.store = InMemoryBehaviorStateStore(self.ttl, clock=self.clock)
        self.model: dict[str, tuple[BehaviorState, datetime | None]] = {}
        self.writes = 0

    def _expired(self, expires: datetime | None) -> bool:
        return expires is not None and expires <= self.clock()

    def _live(self, key: str) -> BehaviorState | None:
        state, expires = self.model.get(key, (None, None))
        if state is not None and self._expired(expires):
            del self.model[key]  # the store drops an expired entry when it is read
            return None
        return state

    def _write(self, key: str, state: BehaviorState) -> None:
        if self.ttl is None:
            self.model[key] = (state, None)
            return
        self.writes += 1
        if self.writes % InMemoryBehaviorStateStore._PURGE_EVERY == 0:
            self._purge()
        self.model[key] = (state, self.clock() + self.ttl)

    def _purge(self) -> int:
        expired = [key for key, (_, expires) in self.model.items() if self._expired(expires)]
        for key in expired:
            del self.model[key]
        return len(expired)

    @rule(seconds=st.integers(0, 20))
    def advance_clock(self, seconds: int) -> None:
        self.clock.advance(seconds=seconds)

    @rule(key=KEYS, count=st.integers(0, 3))
    def put(self, key: str, count: int) -> None:
        state = BehaviorState("p", key[0], count=count)
        self.store.put(key, state)
        self._write(key, state)

    @rule(key=KEYS)
    def update(self, key: str) -> None:
        current = self._live(key)
        received: list[BehaviorState | None] = []

        def bump(existing: BehaviorState | None) -> BehaviorState:
            received.append(existing)
            base = existing if existing is not None else BehaviorState("p", key[0])
            return replace(base, count=base.count + 1, version=base.version + 1)

        result = self.store.update(key, bump)
        assert received == [current], "update sees the live state, or None once it expired"
        assert result == bump(current)
        self._write(key, result)

    @rule(key=KEYS)
    def get(self, key: str) -> None:
        assert self.store.get(key) == self._live(key)

    @rule(key=KEYS)
    def delete(self, key: str) -> None:
        self.store.delete(key)
        self.model.pop(key, None)

    @rule(scope=st.none() | st.sampled_from("ab"))
    def clear(self, scope: str | None) -> None:
        cleared = [key for key in self.model if scope is None or key[0] == scope]
        live = sum(1 for key in cleared if not self._expired(self.model[key][1]))
        assert self.store.clear(scope) == live
        for key in cleared:
            del self.model[key]

    @rule()
    def purge_expired(self) -> None:
        expected = self._purge()
        assert self.store.purge_expired() == expected


TestStoreMachine = StoreMachine.TestCase

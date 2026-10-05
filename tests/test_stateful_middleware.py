"""Stateful model-based test of the middleware's halt, release, and replay semantics."""

import asyncio
from dataclasses import dataclass, field, replace

from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, initialize, rule
from langchain.agents.middleware import ToolCallRequest
from langchain.messages import ToolMessage

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware
from support import tool_request

GUIDANCE = "[BehaviorWeave:stop] Stop now."
SCOPES = st.sampled_from(["s1", "s2"])


@dataclass(frozen=True)
class Call:
    """One tool call; replaying it reuses its ID, conversation position, and result."""

    scope: str
    call_id: str
    fails: bool

    @property
    def event_id(self) -> str:
        return f"{self.call_id}@1"  # the middleware pairs the call ID with the message count


@dataclass
class ScopeModel:
    failures: int = 0
    halted: bool = False
    origins: set[str] = field(default_factory=set)  # calls whose outcome halted the scope
    # Recorded outcome events, keyed by (call ID, failed), and whether each one halted.
    outcomes: dict[tuple[str, bool], bool] = field(default_factory=dict)


class HaltMachine(RuleBasedStateMachine):
    """A blocking outcome halts its scope until release; replays may change their outcome."""

    calls = Bundle("calls")

    @initialize()
    def setup(self) -> None:
        engine = BehaviorEngine(
            policies=[
                PolicyRule("halt", "failure_streak", 2, InterventionType.STOP, message="Stop now.")
            ]
        )
        self.middleware = BehaviorWeaveMiddleware(engine)
        self.models = {"s1": ScopeModel(), "s2": ScopeModel()}
        self.ran: list[str] = []
        self.created = 0

    def _invoke(self, call: Call, asynchronous: bool) -> ToolMessage:
        def result() -> ToolMessage:
            self.ran.append(call.call_id)
            return ToolMessage(
                content="boom" if call.fails else "ok",
                tool_call_id=call.call_id,
                status="error" if call.fails else "success",
            )

        def handler(request: ToolCallRequest) -> ToolMessage:
            return result()

        async def ahandler(request: ToolCallRequest) -> ToolMessage:
            return result()

        request = tool_request(call_id=call.call_id, thread_id=call.scope, messages=[0])
        message = (
            asyncio.run(self.middleware.awrap_tool_call(request, ahandler))
            if asynchronous
            else self.middleware.wrap_tool_call(request, handler)
        )
        assert isinstance(message, ToolMessage)
        return message

    def _run(self, call: Call, asynchronous: bool) -> None:
        model = self.models[call.scope]
        ran_before = len(self.ran)
        message = self._invoke(call, asynchronous)
        if model.halted and call.event_id not in model.origins:
            assert len(self.ran) == ran_before, "a halted scope refuses the call before it runs"
            assert (message.content, message.status) == (GUIDANCE, "error")
            return
        assert self.ran[ran_before:] == [call.call_id]
        outcome = (call.call_id, call.fails)
        if outcome in model.outcomes:
            # A redelivered outcome changes no state and repeats its decision; it never
            # restores a released halt.
            halting = model.outcomes[outcome]
        else:
            # A new outcome, including a replayed call whose result changed, is recorded.
            model.failures = model.failures + 1 if call.fails else 0
            halting = call.fails and model.failures >= 2
            model.outcomes[outcome] = halting
            if halting:
                model.halted = True
                model.origins.add(call.event_id)
        expected = "boom" if call.fails else "ok"
        assert message.content == (f"{expected}\n{GUIDANCE}" if halting else expected)

    @rule(target=calls, scope=SCOPES, fails=st.booleans(), asynchronous=st.booleans())
    def call_tool(self, scope: str, fails: bool, asynchronous: bool) -> Call:
        self.created += 1
        call = Call(scope, f"c{self.created}", fails)
        self._run(call, asynchronous)
        return call

    @rule(call=calls, flip=st.booleans(), asynchronous=st.booleans())
    def replay(self, call: Call, flip: bool, asynchronous: bool) -> None:
        # A replayed step runs the tool again, which may now succeed or fail.
        self._run(replace(call, fails=call.fails != flip), asynchronous)

    @rule(scope=SCOPES)
    def release(self, scope: str) -> None:
        model = self.models[scope]
        assert self.middleware.release(scope) is model.halted
        model.halted = False


TestHaltMachine = HaltMachine.TestCase

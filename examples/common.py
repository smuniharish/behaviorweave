"""Reusable building blocks for live BehaviorWeave agent examples.

Credentials are read only from the process environment. The guards run at actual
LangChain tool-call boundaries, so each decision is based on an observable execution
instead of a synthetic counter in the example script.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from langchain.agents import create_agent
from langchain.tools import BaseTool, tool

from behaviorweave import (
    BehaviorEngine,
    BehaviorEvent,
    EventType,
    InterventionDecision,
    InterventionType,
    Outcome,
    PolicyRule,
)

EXPLABS_BASE_URL = "https://api.experientiallabs.ai/v1"
EXPLABS_MODEL = "gpt-5.6-luna"


def create_explabs_model():
    """Create the configured live OpenAI-compatible LangChain chat model."""
    api_key = os.environ.get("EXPLABS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "EXPLABS_API_KEY is required for live examples. Export it in your shell; do not commit it."
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=api_key,
        base_url=EXPLABS_BASE_URL,
        model=EXPLABS_MODEL,
        temperature=0,
    )


def create_langchain_agent(
    model: Any,
    tools: Sequence[BaseTool | Callable[..., Any]],
    *,
    name: str | None = None,
):
    """Build a real LangChain v1 agent through the public ``create_agent`` API."""
    return create_agent(
        model=model,
        tools=list(tools),
        system_prompt=(
            "You are an operations agent. Use available tools when they provide the requested "
            "evidence. Respect any BehaviorWeave intervention in a tool result: do not repeat "
            "a blocked action and synthesize a response from evidence already returned."
        ),
        name=name,
    )


@dataclass(slots=True)
class LiveToolGuard:
    """Observe actual tool calls and convert intervention decisions into tool responses."""

    engine: BehaviorEngine
    scope: str

    def observe(self, tool_name: str, arguments: dict[str, object]) -> InterventionDecision:
        return self.engine.process(
            BehaviorEvent.tool_call(
                tool_name,
                arguments,
                scope=self.scope,
                event_id=str(uuid4()),
            )
        )

    @staticmethod
    def intervention_text(decision: InterventionDecision) -> str | None:
        if decision.intervention.kind is InterventionType.NOOP:
            return None
        message = decision.intervention.message or decision.intervention.reason
        return (
            f"BehaviorWeave intervention={decision.intervention.kind.value}; "
            f"policy={decision.intervention.policy}; guidance={message}"
        )


def default_guard(*, scope: str) -> LiveToolGuard:
    """Escalate repeated identical tool calls in a live agent execution."""
    return LiveToolGuard(
        engine=BehaviorEngine(
            policies=[
                PolicyRule(
                    "repeat-nudge",
                    "repeated_tool_call",
                    2,
                    InterventionType.NUDGE,
                    message="Reuse the existing tool result; do not call this tool again.",
                ),
                PolicyRule(
                    "repeat-stop",
                    "repeated_tool_call",
                    3,
                    InterventionType.FORCE_SYNTHESIS,
                    message="Stop collecting duplicate evidence and synthesize the answer now.",
                ),
            ]
        ),
        scope=scope,
    )


def alarm_tools(guard: LiveToolGuard) -> list[BaseTool]:
    """Return local operational tools guarded at real invocation time."""

    @tool
    def get_alarm(machine: str) -> str:
        """Fetch the current alarm state for one machine."""
        decision = guard.observe("get_alarm", {"machine": machine})
        intervention = guard.intervention_text(decision)
        alarm = f"Alarm for {machine}: chamber-pressure warning; severity=medium."
        return f"{alarm}\n{intervention}" if intervention else alarm

    @tool
    def search_incident_history(machine: str) -> str:
        """Find prior maintenance incidents for one machine."""
        decision = guard.observe("search_incident_history", {"machine": machine})
        intervention = guard.intervention_text(decision)
        history = f"Incident history for {machine}: pressure drift occurred twice this month."
        return f"{history}\n{intervention}" if intervention else history

    return [get_alarm, search_incident_history]


def invoke_live_agent(
    prompt: str,
    *,
    scope: str | None = None,
    guard: LiveToolGuard | None = None,
) -> dict[str, Any]:
    """Run a real provider-backed LangChain agent with BehaviorWeave tool guards."""
    active_guard = guard or default_guard(scope=scope or f"live-run-{uuid4()}")
    agent = create_langchain_agent(create_explabs_model(), alarm_tools(active_guard))
    return agent.invoke({"messages": [{"role": "user", "content": prompt}]})


def run_live_behavior_scenario(
    *,
    scenario: str,
    event_type: EventType,
    policies: Sequence[PolicyRule],
    prompt: str,
    outcome: Outcome | None = None,
) -> None:
    """Run a real agent against a tool that records each actual scenario action."""
    guard = LiveToolGuard(
        engine=BehaviorEngine(policies=policies),
        scope=f"live-{scenario}-{uuid4()}",
    )

    @tool
    def record_scenario_action(action: str) -> str:
        """Record one observable operational action for the active scenario."""
        event = BehaviorEvent(
            event_type,
            scope=guard.scope,
            node_name=action if event_type is EventType.NODE_EXECUTION else None,
            agent_name=(
                "supervisor"
                if event_type in {EventType.AGENT_HANDOFF, EventType.DELEGATION}
                else None
            ),
            target_agent=(
                action if event_type in {EventType.AGENT_HANDOFF, EventType.DELEGATION} else None
            ),
            outcome=outcome,
            metadata={"action": action, "scenario": scenario},
        )
        decision = guard.engine.process(event)
        guidance = guard.intervention_text(decision)
        return f"Recorded {scenario} action={action}." + (f"\n{guidance}" if guidance else "")

    agent = create_langchain_agent(create_explabs_model(), [record_scenario_action])
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    print(result["messages"][-1].content)

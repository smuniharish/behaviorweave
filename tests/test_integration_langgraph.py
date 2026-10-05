from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from behaviorweave import BehaviorEngine, EventType, InterventionType, Outcome, PolicyRule
from behaviorweave.integrations.langgraph import LangGraphEventAdapter


def test_adapter_builds_normalized_events() -> None:
    adapter = LangGraphEventAdapter()
    node = adapter.node("planner", scope="s", metadata={"step": 1}, event_id="n1")
    assert (node.event_type, node.node_name, node.event_id) == (
        EventType.NODE_EXECUTION,
        "planner",
        "n1",
    )
    assert node.metadata == {"step": 1}
    assert (
        adapter.node("planner", scope="s").event_id != adapter.node("planner", scope="s").event_id
    )
    tool = adapter.tool("search", scope="s", arguments={"q": "x"})
    assert tool.event_type is EventType.TOOL_CALL
    assert tool.metadata["arguments"] == {"q": "x"}
    outcome = adapter.outcome(Outcome.FAILURE, scope="s", node_name="planner")
    assert (outcome.outcome, outcome.node_name) == (Outcome.FAILURE, "planner")
    handoff = adapter.handoff("triage", "billing", scope="s")
    assert handoff.event_type is EventType.AGENT_HANDOFF
    assert handoff.identity() == "triage->billing"
    delegation = adapter.delegation("lead", "researcher", scope="s", event_id="d1")
    assert (delegation.event_type, delegation.event_id) == (EventType.DELEGATION, "d1")


class LoopState(TypedDict):
    steps: int
    stopped_by: str | None


def test_graph_routes_on_behaviorweave_decisions() -> None:
    adapter = LangGraphEventAdapter()
    engine = BehaviorEngine(
        policies=[PolicyRule("loop-guard", "repeated_node_execution", 4, InterventionType.STOP)]
    )

    def work(state: LoopState) -> dict[str, object]:
        decision = engine.process(adapter.node("work", scope="thread-7"))
        stopped = decision.intervention.policy if decision.intervention.kind.is_terminal else None
        return {"steps": state["steps"] + 1, "stopped_by": stopped}

    def route(state: LoopState) -> str:
        return END if state["stopped_by"] or state["steps"] >= 50 else "work"

    builder = StateGraph(LoopState)
    builder.add_node("work", work)
    builder.add_edge(START, "work")
    builder.add_conditional_edges("work", route)
    result = builder.compile().invoke({"steps": 0, "stopped_by": None})
    assert result == {"steps": 4, "stopped_by": "loop-guard"}


def test_oscillating_handoffs_are_detected() -> None:
    adapter = LangGraphEventAdapter()
    engine = BehaviorEngine(
        policies=[PolicyRule("ping-pong", "oscillation", 2, InterventionType.REDIRECT)]
    )
    hops = [("triage", "billing"), ("billing", "triage"), ("triage", "billing")]
    kinds = [engine.process(adapter.handoff(a, b, scope="s")).intervention.kind for a, b in hops]
    assert kinds == ["noop", "noop", "noop"]
    fourth = engine.process(adapter.handoff("billing", "triage", scope="s"))
    assert fourth.intervention.kind is InterventionType.REDIRECT

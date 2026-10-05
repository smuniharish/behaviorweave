"""Check that BehaviorWeave is installed and works in this Python environment.

Runs offline and changes nothing. Prints one PASS, FAIL, or INFO line per check and exits
with status 1 if any check fails:

    python scripts/verify_setup.py
"""

from __future__ import annotations

import platform
import re
import sys
from collections.abc import Callable
from importlib import metadata
from typing import Any, TypedDict

REQUIRED = {
    "langchain": ((1, 4, 3), (2,)),
    "langchain-core": ((1, 6, 6), (2,)),
    "langgraph": ((1, 2, 12), (2,)),
    "langgraph-xai": ((1, 0, 0), (2,)),
}
OPTIONAL = ("langchain-openai", "deepagents", "langgraph-swarm", "mcp")

failures: list[str] = []


def report(passed: bool, message: str) -> bool:
    print(f"{'PASS' if passed else 'FAIL'}  {message}")
    if not passed:
        failures.append(message)
    return passed


def installed(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def release(version: str) -> tuple[int, ...]:
    """Return the numeric release of a version string: "1.2.12rc1" -> (1, 2, 12)."""
    numbers = []
    for part in version.split(".")[:3]:
        digits = re.match(r"\d+", part)
        numbers.append(int(digits.group()) if digits else 0)
    return tuple(numbers)


def dotted(version: tuple[int, ...]) -> str:
    return ".".join(map(str, version))


def check_environment() -> bool:
    report(
        sys.version_info >= (3, 12),
        f"Python {platform.python_version()} (3.12 or newer required)",
    )
    version = installed("behaviorweave")
    if version is None:
        return report(False, "behaviorweave is not installed: pip install behaviorweave")
    report(release(version)[:1] == (1,), f"behaviorweave {version} (1.x expected by this skill)")
    for distribution, (lowest, below) in REQUIRED.items():
        found = installed(distribution)
        report(
            found is not None and lowest <= release(found) < below,
            f"{distribution} {found or 'is not installed'} "
            f"(>={dotted(lowest)},<{dotted(below)} required)",
        )
    extras = {name: installed(name) for name in OPTIONAL}
    present = [f"{name} {version}" for name, version in extras.items() if version]
    absent = [name for name, version in extras.items() if not version]
    print(
        f"INFO  optional packages: {', '.join(present) or 'none'}"
        + (f" (not installed: {', '.join(absent)})" if absent else "")
    )
    return not failures


def ladder() -> Any:
    from behaviorweave import BehaviorEngine, InterventionType, PolicyRule

    return BehaviorEngine(
        policies=[
            PolicyRule("repeat-nudge", "repeated_tool_call", 2, InterventionType.NUDGE),
            PolicyRule("repeat-stop", "repeated_tool_call", 3, InterventionType.STOP),
        ]
    )


def check_engine() -> None:
    from behaviorweave import BehaviorEvent

    engine = ladder()
    events = [
        BehaviorEvent.tool_call("get_alarm", {"machine": "ETCH-3"}, scope="verify")
        for _ in range(3)
    ]
    decisions = [engine.process(event) for event in events]
    kinds = [decision.intervention.kind.value for decision in decisions]
    explanation = decisions[-1].explanation
    report(
        kinds == ["noop", "nudge", "stop"]
        and explanation is not None
        and (explanation.count, explanation.threshold) == (3, 3),
        f"policy ladder decided {kinds}",
    )
    replay = engine.process(events[-1])
    report(
        replay.duplicate and replay.intervention == decisions[-1].intervention,
        "a redelivered event repeats its original intervention, marked duplicate",
    )


def check_middleware() -> None:
    from langchain.agents import create_agent
    from langchain.messages import AIMessage
    from langchain.tools import tool
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware

    class ScriptedModel(GenericFakeChatModel):
        def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedModel:
            return self

    def call(call_id: str) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[{"name": "get_alarm", "args": {"machine": "ETCH-3"}, "id": call_id}],
        )

    runs: list[str] = []

    @tool
    def get_alarm(machine: str) -> str:
        """Return the current alarm for one machine."""
        runs.append(machine)
        return f"{machine}: chamber-pressure warning"

    model = ScriptedModel(
        messages=iter([call("c1"), call("c2"), call("c3"), AIMessage(content="Done.")])
    )
    agent = create_agent(model, [get_alarm], middleware=[BehaviorWeaveMiddleware(ladder())])
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Inspect ETCH-3."}]},
        config={"configurable": {"thread_id": "verify-setup"}},
    )
    results = [message.text for message in result["messages"] if message.type == "tool"]
    report(
        len(runs) == 2
        and len(results) == 3
        and "[BehaviorWeave:nudge]" in results[1]
        and results[2].startswith("[BehaviorWeave:stop]"),
        f"middleware guided the second call and blocked the third ({len(runs)} tool runs)",
    )


class LoopState(TypedDict):
    """State of the loop-guard graph."""

    steps: int
    stopped_by: str | None


def check_langgraph() -> None:
    from langgraph.graph import END, START, StateGraph

    from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
    from behaviorweave.integrations.langgraph import LangGraphEventAdapter

    adapter = LangGraphEventAdapter()
    engine = BehaviorEngine(
        policies=[PolicyRule("loop-guard", "repeated_node_execution", 3, InterventionType.STOP)]
    )

    def work(state: LoopState) -> dict[str, object]:
        decision = engine.process(adapter.node("work", scope="verify-graph"))
        terminal = decision.intervention.kind.is_terminal
        return {
            "steps": state["steps"] + 1,
            "stopped_by": decision.intervention.policy if terminal else None,
        }

    builder = StateGraph(LoopState)
    builder.add_node("work", work)
    builder.add_edge(START, "work")
    builder.add_conditional_edges("work", lambda state: END if state["stopped_by"] else "work")
    final = builder.compile().invoke({"steps": 0, "stopped_by": None})
    report(
        final == {"steps": 3, "stopped_by": "loop-guard"},
        f"LangGraph loop stopped by policy after {final['steps']} steps",
    )


class Order(TypedDict):
    """State of the provenance graph."""

    items: list[str]


def check_langgraph_xai() -> None:
    from langchain.tools import tool
    from langgraph.graph import END, START, StateGraph
    from langgraph_xai import ProvenanceStore, StoreFilter, XAIRuntime
    from langgraph_xai.core import ToolExecutionEvent

    from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
    from behaviorweave.integrations.langgraph_xai import LangGraphXAIEventAdapter

    @tool
    def lookup(item: str) -> str:
        """Look up one inventory item."""
        return f"{item}: in stock"

    def check_stock(state: Order) -> dict[str, list[str]]:
        return {"items": [lookup.invoke({"item": item}) for item in state["items"]]}

    builder = StateGraph(Order)
    builder.add_node("check_stock", check_stock)
    builder.add_edge(START, "check_stock")
    builder.add_edge("check_stock", END)
    runtime = XAIRuntime(application_id="verify-setup", tenant_id="local", graph_id="orders")
    graph = LangGraphXAIEventAdapter.instrument_graph(builder.compile(), runtime=runtime)
    with runtime.collect_runs() as runs:
        graph.invoke({"items": ["valve", "valve"]})
    (run,) = runs

    async def recorded() -> list[Any]:
        store = runtime.registry.get(ProvenanceStore)
        if store is None:
            return []
        query = StoreFilter(
            application_id="verify-setup",
            tenant_id="local",
            run_id=run.run_id,
            item_type=ToolExecutionEvent,
        )
        return [record async for record in store.query(query)]

    try:
        records = runtime.run_sync(recorded())
    finally:
        runtime.run_sync(runtime.close())
    auditor = BehaviorEngine(
        policies=[PolicyRule("busy", "event_frequency", 2, InterventionType.WARNING)]
    )
    adapter = LangGraphXAIEventAdapter()
    decisions = [auditor.process(adapter.event(record, scope="audit")) for record in records]
    explanation = decisions[-1].explanation if decisions else None
    report(
        len(records) == 2
        and decisions[-1].actionable
        and explanation is not None
        and explanation.provenance_ref == str(records[-1].id),
        f"langgraph-xai provenance mapped: {len(records)} tool executions, "
        "decision linked to its provenance record",
    )


def main() -> int:
    if check_environment():
        checks: tuple[Callable[[], None], ...] = (
            check_engine,
            check_middleware,
            check_langgraph,
            check_langgraph_xai,
        )
        for check in checks:
            try:
                check()
            except Exception as error:  # report every failing check, then the summary
                report(False, f"{check.__name__}: {type(error).__name__}: {error}")
    print("All checks passed." if not failures else f"{len(failures)} check(s) failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

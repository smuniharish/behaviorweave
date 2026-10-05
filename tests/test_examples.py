"""Run every example: offline with a rule-based chat model, and live when explicitly enabled.

The offline runs replace ``common.create_model`` with a deterministic model that follows each
example's instructions, so the examples' BehaviorWeave guidance is verified on every test run
without a provider. Live runs execute each script against a real endpoint; enable them with
``BEHAVIORWEAVE_LIVE_TESTS=1`` plus the variables described in ``examples/README.md``.
"""

from __future__ import annotations

import importlib
import os
import re
import runpy
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
MACHINE = {"machine": "ETCH-3"}

type Responder = Callable[[Sequence[BaseMessage], tuple[str, ...]], AIMessage]


class RuleModel(BaseChatModel):
    """A deterministic stand-in for a provider model: it replies by rules on the conversation."""

    respond: Responder
    tools: tuple[str, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "rule-based"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> RuleModel:  # type: ignore[override]
        names = tuple(convert_to_openai_tool(tool)["function"]["name"] for tool in tools)
        return self.model_copy(update={"tools": names})

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self.respond(messages, self.tools))])


def call(name: str, **arguments: object) -> AIMessage:
    tool_call = {"name": name, "args": arguments, "id": f"call_{uuid.uuid4().hex[:12]}"}
    return AIMessage(content="", tool_calls=[tool_call])


def results(messages: Sequence[BaseMessage]) -> list[str]:
    return [message.text for message in messages if message.type == "tool"]


def text(message: BaseMessage) -> str:
    return message.text


def calls(*steps: tuple[str, Mapping[str, object]], answer: str = "Done.") -> Responder:
    """Make each tool call in turn, one per model turn, then answer."""

    def respond(messages: Sequence[BaseMessage], tools: tuple[str, ...]) -> AIMessage:
        done = len(results(messages))
        if done < len(steps):
            name, arguments = steps[done]
            return call(name, **arguments)
        return AIMessage(content=answer)

    return respond


def writer_and_reviewer(messages: Sequence[BaseMessage], tools: tuple[str, ...]) -> AIMessage:
    if "exacting reviewer" in text(messages[-1]):
        return AIMessage(content="Add the operator response time.")
    return AIMessage(content="ETCH-3 raised a chamber-pressure alarm. Operators were notified.")


def supervisor(messages: Sequence[BaseMessage], tools: tuple[str, ...]) -> AIMessage:
    if text(messages[0]).startswith("You are the "):
        return AIMessage(content="Pressure drifted twice this month.")
    question = {"question": "What happened on ETCH-3?"}
    return calls(
        ("ask_researcher", question),
        ("ask_researcher", question),
        ("ask_analyst", question),
        ("ask_writer", question),
        answer="Report complete.",
    )(messages, tools)


def swarm(messages: Sequence[BaseMessage], tools: tuple[str, ...]) -> AIMessage:
    own = "get_alarm" if "get_alarm" in tools else "search_incident_history"
    transfer = next(name for name in tools if name.startswith("transfer_to_"))
    last = messages[-1]
    return call(transfer) if last.type == "tool" and last.name == own else call(own, **MACHINE)


def lead_and_researcher(messages: Sequence[BaseMessage], tools: tuple[str, ...]) -> AIMessage:
    if "get_alarm" not in tools:
        evidence = {
            "description": "Collect ETCH-3 evidence.",
            "subagent_type": "incident_researcher",
        }
        return calls(("task", evidence), answer="Inspect the pressure controller.")(messages, tools)
    seen = [line for result in results(messages) for line in result.splitlines()]
    guidance = " ".join(line for line in seen if line.startswith("[BehaviorWeave:"))
    return calls(
        ("get_alarm", MACHINE),
        ("get_alarm", MACHINE),
        ("search_incident_history", MACHINE),
        answer=f"Evidence collected. {guidance}",
    )(messages, tools)


def conversations(messages: Sequence[BaseMessage], tools: tuple[str, ...]) -> AIMessage:
    prompt = next(text(message) for message in messages if message.type == "human")
    repeats = 2 if "twice" in prompt else 1
    return calls(*[("get_alarm", MACHINE)] * repeats)(messages, tools)


def fleet_worker(messages: Sequence[BaseMessage], tools: tuple[str, ...]) -> AIMessage:
    prompt = next(text(message) for message in messages if message.type == "human")
    machine = re.search(r"ETCH-\d+", prompt)
    assert machine is not None
    return calls(("get_alarm", {"machine": machine.group()}))(messages, tools)


def conversation_b_is_unguided(output: str) -> None:
    first, second = output.split("Conversation B")
    assert "[BehaviorWeave:nudge]" in first
    assert "[BehaviorWeave:" not in second


EXAMPLE_RUNS: dict[str, tuple[Responder, list[str], Callable[[str], None] | None]] = {
    "01_langchain_agent.py": (
        calls(*[("get_alarm", MACHINE)] * 3),
        [
            "-> get_alarm({'machine': 'ETCH-3'})",
            "[BehaviorWeave:nudge] You already have this result. Reuse it instead of calling "
            "the tool again.",
            "[BehaviorWeave:stop] Identical call blocked. Answer with the evidence you already "
            "have.",
        ],
        None,
    ),
    "02_langchain_mcp_live.py": (
        calls(*[("get_alarm", MACHINE)] * 3),
        [
            "[BehaviorWeave:nudge] Reuse this result instead of requesting the same alarm again.",
            "[BehaviorWeave:force_synthesis] Stop repeating this call and synthesize the "
            "evidence already received.",
        ],
        None,
    ),
    "03_langgraph_custom_graph.py": (
        writer_and_reviewer,
        ["Stopped by: Revision budget exhausted: publish the latest draft."],
        None,
    ),
    "04_langgraph_multi_agent.py": (
        supervisor,
        ["[BehaviorWeave:warning] You just consulted this specialist. Use its previous answer."],
        lambda output: assert_count(output, "[BehaviorWeave:", 1),
    ),
    "05_langgraph_swarm.py": (
        swarm,
        [
            "handoff: alarm_agent -> history_agent",
            "handoff: history_agent -> alarm_agent",
            "BehaviorWeave stopped the swarm: 2 consecutive back-and-forth transitions",
        ],
        lambda output: assert_count(output, "handoff:", 4),
    ),
    "06_deepagents.py": (
        calls(("get_alarm", MACHINE), ("get_alarm", MACHINE), ("search_incident_history", MACHINE)),
        ["[BehaviorWeave:nudge] You already have this result."],
        None,
    ),
    "07_deepagents_subagents.py": (
        lead_and_researcher,
        ["-> task(", "Evidence collected. [BehaviorWeave:nudge] You already have this result."],
        None,
    ),
    "08_failure_streak.py": (
        calls(*[("query_inventory", {"sku": "A-100"})] * 5),
        [
            "[operator page] 3 consecutive failure outcomes in example-08",
            "[BehaviorWeave:escalate] The database keeps failing. Stop retrying and report the "
            "outage.",
            "[BehaviorWeave:stop] Retry limit reached. Report the outage now.",
        ],
        None,
    ),
    "09_retry_loop.py": (
        calls(("charge_card", {"order_id": "ORD-7"})),
        [
            "attempt 3 failed: payment provider timed out for ORD-7",
            "[BehaviorWeave:stop] The payment provider is unavailable. Do not retry; tell the "
            "customer.",
        ],
        lambda output: assert_count(output, "failed: payment provider", 3),
    ),
    "10_oscillation.py": (
        calls(
            *[
                (f"transfer_to_{target}", {})
                for target in ("analyst", "researcher", "analyst", "researcher", "analyst")
            ]
        ),
        [
            "[BehaviorWeave:warning] The case is bouncing between the same two specialists.",
            "[BehaviorWeave:stop] Transfer refused. Resolve the case with the findings you "
            "already have.",
        ],
        None,
    ),
    "11_cooldown.py": (
        calls(*[("reconcile_inventory", {"warehouse": "W-1"})] * 4),
        [
            "[BehaviorWeave:nudge] Reconciliation already ran; its result is still current.",
            "[BehaviorWeave:stop] Reconciliation blocked: it already ran three times.",
        ],
        lambda output: assert_count(output, "[BehaviorWeave:nudge]", 1),
    ),
    "12_policy_escalation.py": (
        calls(*[("run_expensive_report", {"region": "EMEA"})] * 5),
        [
            "[host] nudge from policy nudge after run_expensive_report",
            "[host] warning from policy warning after run_expensive_report",
            "[host] human_review from policy review after run_expensive_report",
            "[host] paging the on-call analyst for review",
            "[BehaviorWeave:stop] Report blocked after repeated identical runs.",
        ],
        None,
    ),
    "13_multi_scope.py": (conversations, ["Conversation A"], conversation_b_is_unguided),
    "14_concurrency.py": (
        fleet_worker,
        [
            "3 concurrent agent runs returned 3 tool results.",
            "BehaviorWeave observed 3 tool calls in the shared scope.",
        ],
        None,
    ),
    "15_complete_agent_guard.py": (
        calls(("get_alarm", MACHINE), ("get_alarm", MACHINE), ("search_incident_history", MACHINE)),
        ["Answer:\nDone.", "audit: 'get_alarm' occurred 2 times (provenance "],
        lambda output: assert_count(output, "audit:", 1),
    ),
}


def assert_count(output: str, text: str, expected: int) -> None:
    assert output.count(text) == expected, f"{text!r} appears {output.count(text)} times"


@pytest.fixture
def common(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(EXAMPLES))
    return importlib.import_module("common")


@pytest.mark.examples
@pytest.mark.parametrize("name", sorted(EXAMPLE_RUNS))
def test_examples_run_offline(
    name: str,
    common: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    respond, expected, check = EXAMPLE_RUNS[name]
    monkeypatch.setattr(common, "create_model", lambda: RuleModel(respond=respond))
    monkeypatch.setenv("BEHAVIORWEAVE_CONCURRENCY_CALLS", "3")
    monkeypatch.delenv("BEHAVIORWEAVE_MCP_URL", raising=False)

    # File-descriptor capture keeps a real stderr, which the MCP stdio client hands to its server.
    runpy.run_path(str(EXAMPLES / name), run_name="__main__")

    output = capfd.readouterr().out
    for line in expected:
        assert line in output
    if check is not None:
        check(output)


def test_every_example_is_covered() -> None:
    scripts = {path.name for path in EXAMPLES.glob("*.py")}
    assert scripts == {*EXAMPLE_RUNS, "common.py", "local_alarm_mcp.py"}


@pytest.mark.live
@pytest.mark.parametrize("name", sorted(EXAMPLE_RUNS))
def test_examples_run_against_a_live_model(name: str) -> None:
    configured = all(
        os.environ.get(variable) for variable in ("OPENAI_API_KEY", "BEHAVIORWEAVE_MODEL")
    )
    if os.environ.get("BEHAVIORWEAVE_LIVE_TESTS") != "1" or not configured:
        pytest.skip(
            "set BEHAVIORWEAVE_LIVE_TESTS=1, OPENAI_API_KEY, and BEHAVIORWEAVE_MODEL to run"
        )
    environment = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "BEHAVIORWEAVE_CONCURRENCY_CALLS": "3",
    }
    # Each example runs in its own process, as users run them.
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and example path
        [sys.executable, str(EXAMPLES / name)],
        cwd=EXAMPLES,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=900,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    assert completed.stdout.strip()

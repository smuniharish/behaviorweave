"""Offline tests for the shared plumbing of the live examples (no provider calls)."""

import importlib
from pathlib import Path
from types import ModuleType

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.messages import AIMessage
from langchain_core.messages import BaseMessage
from pydantic import Field

from behaviorweave import BehaviorEngine, InterventionType
from support import ScriptedChatModel, tool_call

EXAMPLES = Path(__file__).parents[1] / "examples"


@pytest.fixture
def common(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(EXAMPLES))
    return importlib.import_module("common")


def test_model_configuration_is_required(
    common: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("BEHAVIORWEAVE_MODEL", raising=False)
    with pytest.raises(SystemExit, match="OPENAI_API_KEY and BEHAVIORWEAVE_MODEL"):
        common.create_model()


def test_model_is_configured_from_the_environment(
    common: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("langchain_openai")
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder-for-tests")
    monkeypatch.setenv("BEHAVIORWEAVE_MODEL", "demo-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9/v1")
    model = common.create_model()
    assert model.model_name == "demo-model"
    assert model.openai_api_base == "http://127.0.0.1:9/v1"


def test_repeat_guard_policies(common: ModuleType) -> None:
    nudge, stop = common.repeat_guard_policies()
    assert (nudge.threshold, nudge.intervention) == (2, InterventionType.NUDGE)
    assert (stop.threshold, stop.intervention) == (3, InterventionType.STOP)


def test_operations_tools(common: ModuleType) -> None:
    alarm, history = common.OPERATIONS_TOOLS
    assert "chamber-pressure warning" in alarm.invoke({"machine": "ETCH-3"})
    assert "pressure drift" in history.invoke({"machine": "ETCH-3"})


def test_guarded_agent_and_transcript(
    common: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    model = ScriptedChatModel(
        messages=iter(
            [
                tool_call("get_alarm", {"machine": "ETCH-3"}, "c1"),
                tool_call("get_alarm", {"machine": "ETCH-3"}, "c2"),
                tool_call("get_alarm", {"machine": "ETCH-3"}, "c3"),
                AIMessage(content="ETCH-3 has a medium pressure warning."),
            ]
        )
    )
    engine = BehaviorEngine(policies=common.repeat_guard_policies())
    agent = common.guarded_agent(engine, model=model)
    common.print_run(common.ask(agent, "Inspect ETCH-3.", thread_id="t-1"))
    output = capsys.readouterr().out
    assert output.count("-> get_alarm({'machine': 'ETCH-3'})") == 3
    assert "[BehaviorWeave:nudge] You already have this result" in output
    assert "[BehaviorWeave:stop] Identical call blocked" in output
    assert output.endswith("Final answer:\nETCH-3 has a medium pressure warning.\n")


class RecordingModel(ScriptedChatModel):
    """Scripted model that records the messages of every call in ``calls``."""

    calls: list[list[BaseMessage]] = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def, override]
        self.calls.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _named_agent(common: ModuleType, *middleware: AgentMiddleware) -> tuple[RecordingModel, object]:
    model = RecordingModel(
        calls=[],
        messages=iter(
            [tool_call("get_alarm", {"machine": "ETCH-3"}, "c1"), AIMessage(content="done")]
        ),
    )
    agent = create_agent(model, [common.get_alarm], name="alarm_agent", middleware=list(middleware))
    return model, agent


def _author_names(messages: list[BaseMessage]) -> set[str | None]:
    return {message.name for message in messages if message.type != "tool"}


def test_named_agents_label_their_messages(common: ModuleType) -> None:
    model, agent = _named_agent(common)
    agent.invoke({"messages": [{"role": "user", "content": "Inspect ETCH-3."}]})  # type: ignore[attr-defined]
    assert "alarm_agent" in _author_names(model.calls[-1])


def test_omit_message_names_strips_author_names(common: ModuleType) -> None:
    model, agent = _named_agent(common, common.OmitMessageNames())
    agent.invoke({"messages": [{"role": "user", "content": "Inspect ETCH-3."}]})  # type: ignore[attr-defined]
    assert any(message.type == "tool" for message in model.calls[-1])
    assert _author_names(model.calls[-1]) == {None}


async def test_omit_message_names_async(common: ModuleType) -> None:
    model, agent = _named_agent(common, common.OmitMessageNames())
    await agent.ainvoke({"messages": [{"role": "user", "content": "Inspect ETCH-3."}]})  # type: ignore[attr-defined]
    assert _author_names(model.calls[-1]) == {None}

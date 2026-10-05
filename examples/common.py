"""Shared helpers for the live BehaviorWeave examples.

Every example drives a real, provider-backed chat model through LangChain. Configure any
OpenAI-compatible endpoint through environment variables; credentials are never read from
files or written anywhere:

    OPENAI_API_KEY        API key for the endpoint (required)
    BEHAVIORWEAVE_MODEL   Chat model name served by the endpoint (required)
    OPENAI_BASE_URL       Endpoint URL; omit it to use api.openai.com
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.tools import BaseTool, tool
from langchain_core.language_models import BaseChatModel

from behaviorweave import BehaviorEngine, InterventionType, PolicyRule
from behaviorweave.integrations.langchain import BehaviorWeaveMiddleware

SYSTEM_PROMPT = (
    "You are an operations agent. Use the available tools to gather evidence. Tool results "
    "may contain lines starting with [BehaviorWeave:...]; follow those instructions exactly."
)


def create_model() -> BaseChatModel:
    """Return the configured chat model, or exit with setup instructions."""
    missing = [
        name for name in ("OPENAI_API_KEY", "BEHAVIORWEAVE_MODEL") if not os.environ.get(name)
    ]
    if missing:
        raise SystemExit(
            f"Set {' and '.join(missing)} to run the live examples (see examples/README.md)."
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=os.environ["BEHAVIORWEAVE_MODEL"],
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        temperature=0,
    )


class OmitMessageNames(AgentMiddleware):
    """Drop author names from non-tool messages before every model call.

    LangGraph Swarm and Deep Agents label assistant messages with the agent's name, but some
    OpenAI-compatible endpoints accept ``name`` only on tool messages.
    """

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        """Call the model with author names removed from non-tool messages."""
        return handler(_without_names(request))

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> ModelResponse:
        """Async variant of `wrap_model_call`."""
        return await handler(_without_names(request))


def _without_names(request: ModelRequest) -> ModelRequest:
    messages = [
        (
            message.model_copy(update={"name": None})
            if message.name and message.type != "tool"
            else message
        )
        for message in request.messages
    ]
    return request.override(messages=messages)


def repeat_guard_policies() -> list[PolicyRule]:
    """Nudge on the second identical tool call and block the third."""
    return [
        PolicyRule(
            "repeat-nudge",
            "repeated_tool_call",
            2,
            InterventionType.NUDGE,
            message="You already have this result. Reuse it instead of calling the tool again.",
        ),
        PolicyRule(
            "repeat-stop",
            "repeated_tool_call",
            3,
            InterventionType.STOP,
            message="Identical call blocked. Answer with the evidence you already have.",
        ),
    ]


@tool
def get_alarm(machine: str) -> str:
    """Return the current alarm state for one machine."""
    return f"Alarm for {machine}: chamber-pressure warning; severity=medium."


@tool
def search_incident_history(machine: str) -> str:
    """Return recent maintenance incidents for one machine."""
    return f"Incident history for {machine}: pressure drift occurred twice this month."


OPERATIONS_TOOLS: tuple[BaseTool, ...] = (get_alarm, search_incident_history)


def guarded_agent(
    engine: BehaviorEngine,
    tools: Sequence[BaseTool] = OPERATIONS_TOOLS,
    *,
    model: BaseChatModel | None = None,
    system_prompt: str = SYSTEM_PROMPT,
    name: str | None = None,
    **middleware_options: Any,
) -> Any:
    """Build a LangChain agent whose tool calls are guarded by BehaviorWeave."""
    return create_agent(
        model or create_model(),
        list(tools),
        system_prompt=system_prompt,
        middleware=[BehaviorWeaveMiddleware(engine, **middleware_options)],
        name=name,
    )


def ask(agent: Any, prompt: str, *, thread_id: str) -> Mapping[str, Any]:
    """Run one user turn in the conversation identified by ``thread_id``."""
    return agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"configurable": {"thread_id": thread_id}},
    )


def print_run(result: Mapping[str, Any]) -> None:
    """Print each tool call, each tool result (including guidance), and the final answer."""
    for message in result["messages"]:
        if message.type == "ai":
            for call in message.tool_calls:
                print(f"-> {call['name']}({call['args']})")
        elif message.type == "tool":
            for line in message.text.splitlines():
                print(f"   {line}")
    print(f"\nFinal answer:\n{result['messages'][-1].text}")

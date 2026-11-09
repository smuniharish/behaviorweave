"""Keep behavior state in the LangGraph store your application already runs.

``LangGraphBehaviorStateStore`` adapts any LangGraph ``BaseStore``, so behavior state can live
next to the agents' long-term memory without another database. Here it is a PostgreSQL
``AsyncPostgresStore`` with a one-hour state TTL. After the run, the example lists the states
the guard wrote under its namespace.

LangGraph stores offer no compare-and-swap, so ``update`` is atomic only within one process.
For replicas that share state, use a store such as ``postgres_state_store.py``.

Run:
    podman run -d --name behaviorweave-postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres \
        docker.io/library/postgres:18
    export BEHAVIORWEAVE_POSTGRES_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres
    uv sync --group examples
    uv run python examples/18_langgraph_store.py
"""

from datetime import timedelta
from uuid import uuid4

from langgraph.store.postgres import AsyncPostgresStore

from behaviorweave import BehaviorEngine
from behaviorweave.integrations.langgraph import LangGraphBehaviorStateStore
from common import ask, guarded_agent, print_run, repeat_guard_policies, run, service_url


async def main() -> None:
    namespace = ("behaviorweave", f"example-18-{uuid4().hex[:8]}")
    async with AsyncPostgresStore.from_conn_string(
        service_url("BEHAVIORWEAVE_POSTGRES_URL"), ttl={"refresh_on_read": False}
    ) as store:
        await store.setup()
        state_store = LangGraphBehaviorStateStore(
            store, namespace=namespace, ttl=timedelta(hours=1)
        )
        agent = guarded_agent(
            BehaviorEngine(policies=repeat_guard_policies(), state_store=state_store)
        )
        print_run(
            await ask(
                agent,
                "Call get_alarm for ETCH-3 three times, one call at a time, then summarize.",
                thread_id="example-18",
            )
        )
        print(f"\nBehavior states in the LangGraph store under {namespace}:")
        for item in await store.asearch(namespace, limit=100):
            print(f"  {item.value['pattern_id']}: count={item.value['count']}")
        for item in await store.asearch(namespace, limit=100):
            await store.adelete(namespace, item.key)


if __name__ == "__main__":
    run(main())

"""Share behavioral history between service replicas through Redis.

Two replicas of a service each build their own engine and agent, but both keep behavior
state in one Redis server. Replica A handles the first turn of a conversation, in which
the agent calls the same tool twice. The next turn lands on replica B, whose engine already
knows that history: the agent's third identical call is blocked.

Run:
    podman run -d --name behaviorweave-redis -p 6379:6379 docker.io/library/redis:8
    export BEHAVIORWEAVE_REDIS_URL=redis://127.0.0.1:6379/0
    uv sync --group examples
    uv run python examples/17_redis_state_store.py
"""

from uuid import uuid4

from behaviorweave import BehaviorEngine
from common import ask, guarded_agent, print_run, repeat_guard_policies, run, service_url
from redis_state_store import RedisBehaviorStateStore


async def main() -> None:
    store = await RedisBehaviorStateStore.connect(service_url("BEHAVIORWEAVE_REDIS_URL"))
    try:
        replica_a, replica_b = (
            guarded_agent(BehaviorEngine(policies=repeat_guard_policies(), state_store=store))
            for _ in range(2)
        )
        thread_id = f"example-17-{uuid4().hex[:8]}"
        print("Replica A")
        print_run(
            await ask(
                replica_a,
                "Call get_alarm for ETCH-3 twice, one call at a time, then summarize.",
                thread_id=thread_id,
            )
        )
        print("\nReplica B")
        print_run(
            await ask(
                replica_b,
                "Call get_alarm for ETCH-3 once more, then summarize.",
                thread_id=thread_id,
            )
        )
    finally:
        await store.close()


if __name__ == "__main__":
    run(main())

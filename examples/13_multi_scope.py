"""Live agent runs showing scope isolation across two users."""

from common import invoke_live_agent

if __name__ == "__main__":
    user_a = invoke_live_agent(
        "Call get_alarm for ETCH-3 twice and summarize any BehaviorWeave guidance.",
        scope="user-a",
    )
    user_b = invoke_live_agent(
        "Call get_alarm for ETCH-3 once and summarize the status.",
        scope="user-b",
    )
    print("User A:", user_a["messages"][-1].content)
    print("User B:", user_b["messages"][-1].content)

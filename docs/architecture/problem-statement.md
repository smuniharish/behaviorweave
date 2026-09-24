# Problem statement

Graph agents can repeatedly call tools, retry failures, cycle between agents, or
delegate excessively. LangGraph correctly executes these behaviors, but applications
need a separate deterministic layer to detect them, apply thresholds and cooldowns,
and communicate a safe intervention decision to the host runtime.


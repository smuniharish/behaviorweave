# State model

BehaviorWeave maintains state per scope and pattern so that behavior observed for one
user, thread, tenant, run, or agent does not affect another. State tracks the
information required to evaluate a policy, including counts, observed time bounds,
cooldown status, and recent delivery identifiers.

The default runtime is safe for concurrent work within a single process. Distributed
applications must provide a durable state implementation that offers equivalent atomic
update and expiry semantics. State storage details are intentionally not part of the
public integration contract.

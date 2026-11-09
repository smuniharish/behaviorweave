"""Record BehaviorWeave interventions as agxai evidence and decisions."""

from __future__ import annotations

from agxai import DecisionFactor, XAIRuntime

from ...audit import AuditSink
from ...errors import PolicyConfigurationError
from ...interventions import AuditRecord

__all__ = ["AgxaiAuditSink"]


class AgxaiAuditSink(AuditSink):
    """An [`AuditSink`][behaviorweave.AuditSink] that records interventions in agxai runs.

    For each actionable decision made while an instrumented graph runs, the sink records a
    ``behavior_pattern`` ``Evidence`` (the explanation's reason, pointing at the triggering
    event's provenance) and a ``behavior_intervention`` ``Decision`` whose selected action is
    the intervention kind, with the observed count and threshold as factors and the policy as
    a policy reference. The run's explanations and attribution then cover the intervention.
    No-op decisions, and decisions made outside a run of ``runtime``, are not recorded.

    Args:
        runtime: The ``agxai.XAIRuntime`` whose current run receives the records.

    Raises:
        PolicyConfigurationError: If ``runtime`` is not an ``agxai.XAIRuntime``.
    """

    def __init__(self, runtime: XAIRuntime) -> None:
        if not isinstance(runtime, XAIRuntime):
            raise PolicyConfigurationError(
                f"runtime must be an agxai.XAIRuntime, not {type(runtime).__name__}"
            )
        self.runtime = runtime

    async def write(self, record: AuditRecord) -> None:
        """Record ``record``'s intervention in the current agxai run, if it is actionable."""
        decision = record.decision
        run = self.runtime.current_run
        if run is None or not decision.actionable or decision.duplicate:
            return
        intervention = decision.intervention
        explanation = decision.explanation
        metadata: dict[str, object] = {
            "source": "behaviorweave",
            "event_id": record.event.event_id,
            "scope": record.event.scope,
            "severity": intervention.severity,
        }
        if intervention.pattern is not None:
            metadata["pattern"] = intervention.pattern
        evidence = await self.runtime.record_evidence(
            "behavior_pattern",
            summary=intervention.reason or None,
            content_reference=None if explanation is None else explanation.provenance_ref,
            metadata=metadata,
            run=run,
        )
        factors: list[DecisionFactor] = []
        if explanation is not None:
            factors.append(
                DecisionFactor(name="count", value=explanation.count, evidence_ids=[evidence.id])
            )
            if explanation.threshold is not None:
                factors.append(DecisionFactor(name="threshold", value=explanation.threshold))
        await self.runtime.record_decision(
            intervention.kind.value,
            decision_type="behavior_intervention",
            evidence_ids=[evidence.id],
            factors=factors,
            policy_references=[] if intervention.policy is None else [intervention.policy],
            metadata=metadata,
            run=run,
        )

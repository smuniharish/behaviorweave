# langgraph-xai boundary

BehaviorWeave integrates with the supported `langgraph-xai` runtime surface to retain
an execution/provenance reference alongside observable behavioral events. It does not
reimplement explainability or capture private model reasoning.

If provenance context cannot be obtained, the integration reports an explicit error
rather than fabricating evidence. Applications can decide whether that integration
failure should interrupt their own workflow.

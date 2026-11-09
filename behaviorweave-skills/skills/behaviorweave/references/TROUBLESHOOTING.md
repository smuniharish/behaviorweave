# Troubleshooting

1. Run `scripts/verify_setup.py` in the same interpreter as the application.
2. Inspect event type, identity, scope, timestamp, and ID, not prompt text.
3. Confirm the policy references a registered pattern and reaches its threshold.
4. Check whether a contrary outcome resets the streak or a cooldown/once-only rule suppresses it.
5. Await `engine.process`; an unawaited coroutine is not a decision.
6. Check `block_on`: advisory kinds do not block unless configured to.
7. Inspect `await middleware.halted(scope)` and explicitly release a persisted halt before
   resuming an approved run.
8. For unexpected duplicates, stop reusing IDs across distinct observations.
9. For leaked history, isolate tenant/conversation scopes.
10. For lost increments across replicas, replace instance-local locks with backend atomicity.
11. For an ABC construction error, implement all abstract methods and inherit the actual ABC.
12. For agxai capture, remember that cancelled/interrupted executions have no outcome;
    captured tool identity has no raw arguments.

Do not silently recover from backend/audit failures or change private state keys. Reproduce
the behavior with fixed timestamps and deterministic events, then add a policy regression test.

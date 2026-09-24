# Failure strategy

Malformed events raise `EventValidationError`; state-store failures propagate as
`StateStoreError`; detector and policy failures propagate with their original cause.
The core never silently fails open or executes an intervention. Hosts can choose a
runtime-specific failure policy around the engine boundary.


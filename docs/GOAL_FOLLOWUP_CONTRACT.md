# Goal-bound followup and output v2

Followup history is separately versioned immutable evidence attached to the
existing goal-progress checkpoint. The trusted supervisor records actual failed
observations; the message client cannot submit or replace this history. STOP
blocks connected reference writes and source queries. Absent new protection in
an old host remains ADVISORY, never implicit global enforcement.

Action identity binds request/revision, outcome, operation, capability and exact
targets. Blocker identity additionally binds the error class. Capability facts
and exact target preconditions have separate digests. The entire native ledger
digest is deliberately not a retry signal: recording failure changes the ledger,
not the missing capability. Unchanged facts suppress another attempt; genuinely
changed facts can permit one within a three-attempt cap for the original action.
The supervisor must retain the real observation history; arbitrary Python code
inside that trusted supervisor is not authenticated by an object digest.

The closed reference host reads native-bound followup evidence before writes.
A suppressed current action stays refused even if output identifies a different
independent outcome. That outcome needs its own exact binding, not permission
to retry the old action. No extra OWNER approval is inferred for internal binding.

`compile_goal_context` derives its matrix from real native-bound source evidence,
not a caller's completeness flag. It names all open outcomes, refuses unrelated
future suggestions and binds the actual capsule digest. The existing output
builder/renderer consumes this versioned context; absent context remains v1.
V2 refuses a loose external-action override, stale context and any strengthening
of the native decision. Partial work remains plainly partial without a needless
copy box. A completed old roadmap cannot close a distinct new question.
For the original completed request only, the last completed assignment's bound
progress remains readable for its final integrated proof. A different request
still fails the exact request comparison.

Explicit replacement planning preserves prior source and every previous outcome
with visible superseded status. AI_PROPOSAL stays a proposal after copying;
UNKNOWN is not promoted to OWNER. A new trusted OWNER message can establish an
explicit new revision/request, but this projection performs no action and grants
no authority itself. New execution still needs the current bound native scope.

# Shared goal binding (development candidate)

This version-2 envelope connects a request revision, host source, exact action,
outcome references and an existing execution capsule. It is not an executor,
permission grant, authentication scheme or new state database. The retired
`guarded_copy` route stays disabled. No installed v1 behavior is upgraded by
creating this envelope.

## Ownership and trust boundary

`build_goal_binding` is a trusted supervisor preparation API. The supervisor
supplies `HostSource` from its own message registry and retains the returned
immutable `BoundGoal` independently of the messages-only action client.
Never construct the expected binding from a client request being validated.
SHA256 detects changed content, not authorship. Arbitrary Python execution in
the supervisor process is outside this API's protection.

`HostSource.content_sha256` binds the exact `human_intent` UTF-8 text stored in
the legacy intent. Missing source metadata stays UNKNOWN. A forwarded AI
proposal retains AI_PROPOSAL and its derivation reference; a genuine new OWNER
revision needs separate trusted host evidence, not a rehashed AI statement.
Preserving these supplied relationships is not automatic language understanding.

`validate_goal_binding` compares the entire payload with the separate retained
expectation and current capsule. A client cannot change a target, request
revision, source or evidence even by recomputing the ordinary payload digest.
`continuity.validate_current_goal_binding` loads the real capsule itself and
performs this check without writing any state. A valid check still returns
NOT_PERFORMED and authority_granted=false.

## Compatibility

| Consumer | Legacy v1 | Goal binding v2 | Unknown versions |
|---|---|---|---|
| Existing intent reader | Unchanged | Reject | Reject |
| New legacy-intent reader | Unchanged, no enforcement claim | Reject | Reject |
| New goal validator | Not a goal envelope | Independent binding and live-state check | Reject |
| New goal builder | Embed unchanged intent/capsule | Explicit v2 output only | Reject |

No v1 schema or historical bytes are rewritten. The two embedded v1 values keep
their original own digests. The new envelope has its own schema and digest.
Exact-target operations are READ_EXACT and REPLACE_EXACT with recursion=false;
each target requires a hash and identity reference. Physical identity validation
belongs to the connected platform adapter, not to string validation here.
Evidence references associate outcomes, but do not establish content coverage,
usability, completion or OWNER acceptance merely by existing.

Later R15 work connects physical execution, planning/coverage, continuation and
durable handoff using this shared boundary. Until that combined proof exists,
this contract must not be marketed as complete goal-bound enforcement.

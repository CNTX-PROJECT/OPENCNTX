# Proportionate task assessment

`human_interface.assess_task_size(TaskFacts(...))` is a pure projectless entry
point. It performs no filesystem, network or model call. Counting 4,001 records
is SHORT; multiple phases require LARGE; multiple independently large streams
or full multidimensional collection analysis require MEGA. Risk is separate.
The host interprets meaning into facts; this library does not understand natural
language automatically or attest that a host's interpretation is correct.

`assess_bound_task` creates an immutable `opencntx-task-assessment`, version 2,
with its own digest, the unchanged goal-v2 digest, request identity/revision,
all outcomes, source and original source, authority, reason, classification,
assessment revision and previous assessment digest. It is a supervisor-owned
projection, not a new state ledger, scheduling engine or permission token.
Legacy v1 stays unchanged and cannot claim this absent protection.

Growing or shrinking classification preserves all obligations and history.
Dropping outcomes, changing request identity/authority/risk, or using an older
request revision refuses ordinary reassessment. A material change needs the
separate request/authority procedure, not an invented approval in classification.
Digests detect inconsistent records, not source authenticity; the supervisor
must retain the trusted assessment rather than accept one from a client.

The closed Windows reference host independently retains this assessment and
checks it before its fixed replacement. Uncertainty requires a bounded source
probe first; the replacement cannot be relabelled as a probe. LARGE/MEGA require
verified hierarchy, supplied by the next integration stage. Without it broad
execution refuses. A default SHORT assessment only describes this known small
fixture operation, never an arbitrary real-world task or unrestricted shell.

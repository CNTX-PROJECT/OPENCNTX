# Linked progress v2

One bounded `opencntx-goal-progress` v2 projection contains request, original
intent digest, parent/child/return links, dependencies, outcomes, immutable source
snapshots, evidence, status and next action. It uses the native DAG validation
and never imports the historical test-only R9 runner. Maximum 50 nodes, hierarchy
depth 8, canonical envelope maximum 256 KiB. Replanning preserves request,
authority and outcome obligations plus prior digest and retained evidence.

`progress_readiness` derives independent ready leaves. Blocked siblings do not
block independent work; an ancestor/dependency blocker does. Child labels do not
prove complete parent coverage. The parent remains PARTIAL pending separate
outcome and synthesis evidence. This is not a second scheduling database.

`recovery_resumption` makes a completed repair an explicit non-terminal event.
It accepts only a delivered `Repair:` leaf with exactly one ready sibling that
depends on that repair, retains the same outcome obligations and returns to the
same original parent leaf. Its only successful decision is
`CONTINUE_PARENT_ROADMAP` with reason
`RECOVERY_RESOLVED_RETURN_TO_PARENT`. A missing, ambiguous, blocked or altered
resume leaf is rejected fail-closed. Consequently, a solved temporary side
branch cannot be presented as the end of its parent roadmap.

`persist_goal_progress` uses existing compressed evidence objects, then writes
a content-addressed reference receipt in an explicitly allocated, already
existing supervisor evidence directory. The existing execution checkpoint CAS
binds that receipt and exact immutable source/evidence bytes. It never exempts
caller-supplied `.opencntx` evidence from the native protected-state rule.
Only the existing native event chain determines active progress. A prepared
object or receipt without a committed checkpoint is inert. CAS conflict leaves
the prior active state intact; prepared evidence is retained, not silently erased.

`load_goal_progress` selects the last verified checkpoint for the actual active
assignment. It checks request revision and original intent and reads the exact
object, not a newest-file pointer. The closed reference host loads this inside
the existing writer lock after current action validation. The supervisor selects
an exact node; the client cannot supply a hierarchy or a readiness override.
LARGE/MEGA require the matching hierarchy and early source snapshots. No broad
claim that semantic source interpretation or arbitrary Codex tools are enforced.

Source snapshots and evidence are immutable proof inputs, not mutable live
working files. Their later modification invalidates the bound native evidence.
Revised sources need distinct snapshots, retaining older evidence for history.

# Connected reference fixture host (development candidate)

This host proves one narrow Windows text-file operation through the shared goal
binding. It registers no installed CLI, Codex hook or general-purpose shell/file
tool. Free Codex and other unconnected routes remain outside its enforcement
claim. Its constructor is trusted supervisor setup, not a client operation.

## One connected boundary

The supervisor chooses an existing fixture subtree of its own project, an
approved parent-only intent and independently recorded OWNER source. It captures
physical identities and hashes and retains the v2 goal binding separately.
`ReferenceHost.dispatch` is the only client operation; `serve_reference_host`
provides bounded JSON lines (64 KiB, unique keys). Clients cannot rebind policy,
approve themselves, select another root, request recursion or execute a shell.

The existing native continuity writer lock is held while loading/checking the
current capsule and performing the action. A concurrent native writer refuses;
changed state requires a new binding. The host reuses `decide_finalization`,
including bounded recovery, instead of inventing a separate continuation rule.
Unknown/AI-only provenance cannot authorize this fixture writer. In-memory
single-use state and physical preconditions refuse replays; durable execution
receipt and cross-process restart integration remain separate R15 work.

## Exact resources and recovery

The fixture contains parent/{00,90,99}.txt, protected same names in parent/child,
matching backup/parent files and empty staging/retained directories. All names
are fixed; a missing parent never causes lookup/substitution in a child.
Only the parent content changes; exactly three declared retained files preserve
the original objects. Staging files are bounded, newly created recovery objects.
This is intentionally not an arbitrary production-file editing interface.

Windows handles protect path components, current file identities and bytes.
Reparse traversal, preexisting aliases, oversize files and drift refuse. The
writer never mutates original file data: a concurrent hardlink to the original
therefore retains original bytes. Replacement files are explicitly delete-pending
before data writes, checked for raced aliases, flushed/read back and permanently
sealed before no-clobber handle publication. Protected children/backups stay held.

A new user destination in a publication gap is never overwritten, including by
rollback. The response is PARTIAL_RECOVERY_REQUIRED and originals/backups remain
available. Unpublished pending temporary objects disappear when their handles
close. No user file or backup is deleted for cleanup. Ordinary exceptions can be
recovered; atomic three-file recovery across power/process loss is not claimed.

## Proof and platform boundary

`tests/test_reference_host.py` covers actual subprocess messages, current-state
drift, competing native writer, missing/replaced targets, Windows case-equivalent
paths, hardlinks/junctions, child/backup drift, preserved new user bytes and
bounded input. Unsupported platforms refuse before opening a file. Windows
success is not Linux write proof. General metadata fidelity and full installed
host coverage require their own explicit evidence.

The original R15-01 local prototype and its receipts remain unchanged; candidate
physical primitives derive from that successful staged algorithm. The retired
`guarded_copy` entry point remains fail-closed for stale callers.

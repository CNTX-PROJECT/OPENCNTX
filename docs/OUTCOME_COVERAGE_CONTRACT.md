# Source coverage and synthesis v2

The bounded read-only route `run_source_query` receives a supervisor-retained
goal and exact SourceQuery. The client message must equal the current native
goal; outcome, operation, source path, source digest and authority must match.
Only exact string equality over an explicit JSON record array is supported.
Limits are 1 MiB of source, 10,000 unique-ID records and a 256 KiB report envelope.
The host selects semantic fields and claims; this is not general language
understanding, automated truth discovery or authentication of arbitrary callers.

An `opencntx-outcome-report` v2 records actual denominator, inspected prefix IDs,
missing required fields, findings, query/source identity and request revision.
Missing fields produce BLOCKED/INSUFFICIENT. Selective depth produces PARTIAL.
Fully examined complete records with zero matches produce DELIVERED/USABLE;
a verified empty collection can be a valid zero, a missing source cannot.
Safety is SAFE_READ_ONLY; OWNER acceptance stays UNKNOWN independently.

`integrate_outcomes` is a pure relationship validator over supervisor-owned
reports, not independent source verification. It preserves unassessed original
outcomes, rejects duplicated outcome credit and detects contradictory declared
semantic keys. It never adds coverage denominators across separate outcomes.
Technical completion also requires an explicit synthesis bound to the exact
report digest set; no report alone can manufacture OWNER acceptance.

`compile_current_outcomes` is the stronger real evidence route: it reads only
reports bound by the existing native goal-progress checkpoint, requires each
report's exact node/source relationship, and recomputes the reported facts from
the actual source bytes. A self-rehashed false-green report is rejected. The
synthesis file must itself be native-bound immutable evidence, with matching
report-set digest and conclusion. An unbound proof cannot close the parent.
This explicit synthesis operation is not a background scan or per-token action.
R15-07 connects the resulting matrix to relevant output/finalization.

Proof remains generic local fixtures; there is no claim to have inspected any
real private collection. Source completeness is relative to the explicitly
bound collection, not an unexamined external universe. V1 stays unchanged.

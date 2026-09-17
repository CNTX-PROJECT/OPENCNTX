# OPENCNTX 1.8.4 candidate — audit hardening and portable presentation

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

**Status: local candidate; not a published release.** See the
[qualification roadmap](roadmap-1.8.4.md) for mandatory release gates.

## Implemented candidate changes

- Validate portable technique IDs, distinguish create from digest-conditional
  update, protect writers with the existing transaction layer, and bound recall.
- Bound source reads using the opened file, reject root mismatches and unsafe
  paths, and apply the existing deterministic secret policy before delivery.
- Bound the complete serialized search result using its declared estimate;
  fail explicitly when the empty envelope cannot fit. Add an opt-in delivery
  report with independent output-byte limits and visible source coverage.
- Share one source snapshot between the default CLI's v1 and v2 projections;
  avoid publishing an unchanged index, and reject outdated index publishers.
- Check external-content FTS integrity, expose structured JSON truncation,
  preserve original Unicode offsets and BM25 ordering, and protect exact paths
  from candidate crowding.
- Require explicit hard relationship prefixes and current nonempty PROVEN
  bindings. Preserve original source files and existing stored card bytes.
- Keep existing footer v1 and VISUAL_ARTIST contracts. Add negotiated partial
  telemetry with per-field provenance and context binding, English
  presentation and structured-output suppression.
- Add a bounded visual text integration route: reviewed preview, tracked apply,
  verified receipt, no-write repeat and rollback that refuses newer user edits.
  This is not a general project relocation or graphical-rendering engine.
- Bind installation simulations to wheel metadata and hashes instead of fixed
  version labels.

## New opt-in routes

```text
opencntx knowledge index search QUERY --delivery-report --max-output-bytes 10000
opencntx knowledge technique add --input card.json --expected-digest PREVIOUS_CARD_DIGEST
opencntx knowledge technique list --limit 50 --offset 0
opencntx knowledge index status --limit 100 --offset 0
opencntx knowledge visual preview --document docs/overview.md --intent intent.json
opencntx knowledge visual apply --plan plan.json --intent intent.json --review review.json
opencntx knowledge visual rollback --plan plan.json
opencntx knowledge footer --from-host-envelope-v2 telemetry.json --session-id SESSION --context-generation GENERATION --source-digest DIGEST --locale en
```

Save the exact visual preview JSON as the plan. The apply route requires a
COMPLETE visual review bound to the same intent, including human approval.
It preserves original document bytes before its appended text section. It
refuses an existing managed section without its receipt and refuses rollback
over later edits. Store plans and reviews outside indexed user content when
they are operational artifacts. The existing v1 footer route is unchanged.
Existing private owner profiles and local translations remain host-owned;
the public package and its default presentation remain in English.

## Claims requiring release evidence

No universal token-saving percentage, arbitrary-provider residency, unqualified
upgrade path, unattended visual adoption or native-hook activation is claimed.
The 1.8.4 tag and four distribution assets must not be published as stable until
the exact candidate passes the qualification roadmap.

[Documentation home](README.md)

# Project roadmap routing

[Overview](../README.md) · [Get started](start-here.md) · [Continuity](continuity.md) · [Commands](commands.md) · [Releases](releases.md) · [All guides](README.md)

OPENCNTX 1.7.5 provides deterministic building blocks for hosts that organize
work under one project roadmap. The host supplies explicit facts; OPENCNTX does
not infer intent from natural language or start an AI.

## One master, focused child roadmaps

Use one master roadmap for the project and create child roadmaps only for
independent large outcomes:

| Task relationship | Size | Route |
|---|---:|---|
| Related work | Short | Attach one step immediately to the active child roadmap |
| Related extension | Large or mega | Extend the active child roadmap |
| Distinct outcome | Large or mega | Create the next child roadmap under the master |
| Side topic | Any | Park it and retain the exact roadmap and step return anchor |
| Projectless information | Any | Answer only; do not invent a project roadmap |

This prevents a new master roadmap for every assignment while keeping two
independent large outcomes visibly separate.

## Python integration

```python
from opencntx.project_planning import ProjectTaskFacts, route_project_task

route = route_project_task(
    ProjectTaskFacts(
        project_known=True,
        relation="DISTINCT_OUTCOME",
        size_class="LARGE",
    ),
    master_roadmap_id="PROJECT-MASTER",
    current_child_roadmap_id="CHILD-1",
    existing_child_roadmap_ids=("CHILD-1",),
)
```

The returned action is `CREATE_CHILD_ROADMAP`, its parent is `PROJECT-MASTER`,
its ordinal is `2`, and the prior child remains the return anchor. The host owns
the names, storage mutation, authorization, and presentation.

## Continue without unnecessary stops

`decide_execution()` selects one bounded decision from explicit host state.
Safe authorized work with open steps returns `CONTINUE`. Completion requires
closed work plus complete evidence. Missing authority or a material owner choice
returns `ASK_OWNER`; exhausted recovery returns `BLOCKED`; rollover returns
`HANDOFF`. Feedback-only input is parked and cannot authorize a technical
mutation.

Optional telemetry or presentation failures should be represented outside the
core work result. They are not a reason to turn a completed native action into
an incomplete one.

## Load changed context, reference the rest

`plan_context_load()` orders the current step and return anchor first, then
loads changed decisions and supporting material within a fixed byte budget.
An unchanged non-anchor source is referenced by its SHA-256 digest instead of
being loaded again. The result reports naive bytes, loaded bytes, skipped or
referenced source IDs, and the measured reduction percentage.

Required anchors never disappear silently: if they alone exceed the supplied
budget, planning fails before content is loaded. This is a deterministic input
plan, not a claim about model token accounting or every host's real cost.

## Host boundary

These APIs do not alter the existing durable formats, CLI routes, or authority
model. A connected host may use the returned decisions to update its existing
roadmap store. Installation alone does not activate that host integration.

[Release scope](release-1.7.5.md) · [Roadmap continuity](continuity.md) · [Documentation home](README.md)

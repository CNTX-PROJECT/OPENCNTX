# A visual tour of your project

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

OPENCNTX keeps project context in files you can inspect. Start with a small
package; add structured knowledge and task continuity when your work needs it.

## 1. Give each place a clear job

![Local source of truth, optional GitHub mirror and optional readable notes view.](../assets/docs/knowledge-ecosystem.svg)

**Local files are the original.** Keep sources, decisions, reusable procedures,
agent-role instructions and evidence together. The optional workspace provides
CONTROL for direction, SOURCES for inputs, CHAPTERS for reviewed knowledge,
TASKS for bounded work, PLAYBOOKS for procedures and ROLES for role descriptions.
The .opencntx directory stores generated package and lifecycle data.

**GitHub is a recommended off-machine copy.** Review files, commit them, then
push to a private repository. Only pushed content reaches GitHub; ignored
files, secrets and large media need an appropriate separate backup. OPENCNTX
does not create a GitHub account or install a sync service.

**Your notes app is the human view.** Obsidian or another Markdown-friendly
tool can show explanations and linked progress. Choose one canonical technical
source and maintain a concise view of it. Set up that integration separately.

## 2. Turn a goal into a repeatable loop

![Task, context, work and check, saved outcome, next step.](../assets/docs/task-journey.svg)

The AI host reads the current assignment, performs authorized work, and checks
the result. The continuity tools record outcomes, evidence and a handoff so a
later conversation can resume. They do not run the AI themselves.

- Small work: one check in the relevant roadmap.
- Medium work: a connected checklist in the current roadmap.
- Large work: extend the current child, or create one child for a distinct outcome.
- Mega work: coordinate several outcomes under one master, with dependencies.

Size is a planning aid. The host supplies the explicit task facts used by
OPENCNTX's routing API. There is no automatic natural-language classification
merely from installing the package.

[Detailed routing rules](project-roadmaps.md) · [Runnable continuity example](continuity.md)

## 3. Make progress easy to understand

![Concept for a readable notes-app knowledge base, with a current step, knowledge links and roadmap.](../assets/docs/owner-knowledge.svg)

This is an illustrative layout, not a screenshot of an included app. Build a
home note with a short status and links to the master roadmap, current outcome
and knowledge index. In each outcome, show completed checks, the next step,
open decisions and links to evidence. Use diagrams where they explain a real
relationship; keep raw logs in the technical workspace.

For example, a website project could have one master roadmap and separate
outcomes for content, checkout and launch. A typo belongs in the content
checklist; it does not need a second project master.

## What is available now?

The released tools create and verify context packages, structure optional
workspaces and preserve bounded continuity state. Version 1.7.5 also provides
legacy-safe recovery while retaining project-routing and context-load planning
APIs. Your host remains responsible
for executing work, classifying requests and updating external applications.

[Start with one local package](start-here.md) · [Release scope](release-1.7.5.md)

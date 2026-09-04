# Visual system

[Overview](../README.md) · [Components](../site/components.html) · [Brand](brand.md) · [Security](security.md) · [All guides](README.md)

OPENCNTX uses one restrained visual system to make the next action, evidence,
state, and boundary easy to understand. It is deliberately calm: hierarchy
does the work, Plum identifies the product, and decoration never competes with
the task.

## Two cooperating reviews

`VISUAL_ARTIST` owns the visual intent: hierarchy, composition, typography,
spacing, responsive behavior, accessibility, and the professional finish of a
human-facing surface. `BOUNDED_PERFECTION` checks whether the implementation is
consistent, complete, deterministic, and inside the approved boundary.

Neither role grants permission. A surface is complete only when both checks
pass and the required human visual review has been recorded. Refinement is
bounded to three rounds; unresolved material findings then stop explicitly.

## Canonical layers

| Layer | Canonical source | Purpose |
|---|---|---|
| Intent and review | `visual-intent-v1` and `visual-review-v1` schemas | closed, portable review contracts |
| Tokens | `assets/design-system/tokens-v1.json` | color, type, spacing, radius, shadow, motion, breakpoints and states |
| Generated CSS | `assets/design-system/tokens-v1.css` | deterministic browser variables for light and dark modes |
| Components | `site/components.html` | accessible reference for controls, cards, status and evidence |
| Content order | `site/content-map-v1.json` | one task-led route and reusable surface templates |
| Surface coverage | `assets/design-system/surface-inventory-v1.json` | explicit product-wide scope and fallback classification |

## Everywhere, with an honest boundary

The system applies to every OPENCNTX-owned human-facing surface. Markdown
guides use the same task-first hierarchy and plain status language. CLI and
status output remain text-only by design, with the same ordering and no
meaning carried by color alone. Machine contracts support the system but are
not visual surfaces.

A future GUI, dashboard, or host adapter must consume the canonical intent,
tokens, component states, and review contract before it can claim alignment.
Codex chrome, operating-system controls, and third-party interfaces remain
outside OPENCNTX's visual ownership.

## Accessibility and resilience

- normal text meets WCAG AA contrast in light and dark modes;
- keyboard focus is visible and state names remain readable without color;
- reduced-motion and forced-colors modes have explicit fallbacks;
- layouts reflow on narrow screens without horizontal scrolling;
- local system fonts and local assets avoid tracking and network failure;
- every important graphical explanation retains a useful text route.

## Verify the system

The token CSS is generated from the canonical JSON and can be checked without
changing files:

```powershell
python tools/render_visual_tokens.py --check
python -m unittest tests.test_visual_design tests.test_visual_site -v
```

Use `--write` only after a deliberate token-source change. A green automated
check proves consistency and accessibility rules, not subjective human visual
acceptance and not release authority.

[Documentation home](README.md)

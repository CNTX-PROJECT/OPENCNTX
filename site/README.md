# OPENCNTX website source

This directory is a local, dependency-free reference website. It is not a live
deployment and contains no hosting configuration, tracker, remote font, client
framework, cookie banner, account flow, or external script.

## Information order

The canonical sequence is stored in `content-map-v1.json`:

1. state the one user value;
2. show the three-step mental model;
3. give one safe first action;
4. explain the proof and authority boundary;
5. route to task-oriented documentation;
6. separate ordinary support from private security reporting.

Every page or rendered report uses one of three templates: landing, reference,
or status. Each template has exactly one primary message and one visible next
safe action. A status may describe evidence but never implies OWNER approval.

## Local preview

Open `index.html` directly or serve this repository root with a local static
server. The website must work without JavaScript. `assets/opencntx.css` imports
the generated token CSS from `assets/design-system/tokens-v1.css`; official
brand SVGs remain canonical under `assets/brand/`.

Live hosting, a domain, analytics, redirects, headers, or deployment automation
remain separate OWNER decisions.

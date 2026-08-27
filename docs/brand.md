# Brand guide

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

The OPENCNTX identity is calm, exact, and recognizable. Its portal symbol uses
two offset context brackets: white represents the source context, Plum marks
the reviewed output, and the small white square represents traceable evidence.

## Core rule

- Write `OPENCNTX` in uppercase without a space.
- Write the official display wordmark as lowercase `opencntx` on a transparent
  canvas that inherits the host surface.
- `open` is white on dark screens and deep ink on light screens. `cntx` is
  always Plum.
- Use the same open-context portal for the avatar, icon, wordmark, and social
  preview.
- Center the complete mark, not only the text.
- Use exactly one purple everywhere: Plum `#DDA0DD`. Never introduce a lighter,
  darker, pastel, or alternate purple.
- Preserve the deep-navy, white, and Plum relationship inside the portal.

## Official colors

| Use | Light screen | Dark screen |
|---|---|---|
| Host canvas (not painted by embedded assets) | `#F8FAFC` | `#0B1020` |
| Surface | `#FFFFFF` | `#111827` |
| Main text | `#0F172A` | `#F8FAFC` |
| Secondary text | `#475569` | `#CBD5E1` |
| Brand Plum | `#DDA0DD` | `#DDA0DD` |
| Verified-context cyan | `#0891B2` | `#22D3EE` |
| Success accent | `#047857` | `#34D399` |

The tested text pairs meet WCAG AA contrast for normal text.

## Typography

Official logo text uses this rounded system-first stack:

```text
Trebuchet MS, Trebuchet, Arial, sans-serif
```

The wordmark uses one continuous lowercase text element with tracking fixed at
`-0.015em`. The split between `open` and `cntx` never creates a separate space;
every letter relationship therefore follows the same tracking rule. The exact
word width is fixed in each official SVG so fallbacks cannot create a visible
layout jump.

Documentation diagrams retain the more neutral reading stack:

```text
Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif
```

No font file or remote font request is bundled.

## Official files

| File | Use |
|---|---|
| `opencntx-wordmark-light.svg` | transparent centered wordmark for a light screen |
| `opencntx-wordmark-dark.svg` | transparent centered wordmark for a dark screen |
| `opencntx-avatar.svg` | theme-neutral avatar source without small text |
| `opencntx-avatar-512.png` | generated avatar upload |
| `opencntx-symbol-light.svg` | compact symbol for a light screen |
| `opencntx-symbol-dark.svg` | compact symbol for a dark screen |
| `opencntx-icon-32.png` | generated small icon |
| `opencntx-icon-128.png` | generated large icon |
| `opencntx-social-preview.svg` | standard-font social preview source |
| `opencntx-social-preview-1280x640.png` | approved exact social preview export |

Documentation diagrams use the light filename as the default and a matching
`-dark.svg` file for dark screens. Both variants have transparent outer
canvases plus identical words and geometry. Their restrained cards, accent
rails, numbered checkpoints, and connectors form one reusable information
system rather than separate artwork.

## Alignment and clear space

- Keep equal visible space on the left and right of every mark.
- Keep repeated diagram cards on a shared grid with consistent radii, border
  weight, accent rails, number markers, and text baselines.
- Use color to explain a role or state, never as decoration alone.
- Keep arrows subordinate to the content they connect.
- Do not display the horizontal wordmark below 240 pixels wide.
- Use the compact symbol below that width.
- Keep the avatar square and do not crop the portal tile.

## Do not

- change the OPEN/CNTX color relationship;
- add an opaque outer canvas behind an embedded wordmark or documentation
  diagram;
- add gradients, glow, decorative network lines, or photo textures;
- stretch, rotate, or crop the mark;
- add small text to the avatar;
- use uneven margins, arbitrary spacing, or competing accent colors;
- use unofficial colors as the primary identity.

## Reproduce and verify

The avatar and icon PNGs contain only controlled geometric shapes. They are
deterministically generated with the Python standard library:

```powershell
$env:PYTHONDONTWRITEBYTECODE="1"
python tools/render_brand.py --write
python tools/render_brand.py --check
```

The standard-font social preview is different. System fonts may rasterize
differently across operating systems, so its PNG is one reviewed export. The
SVG remains the canonical readable source. `SHA256SUMS` pins the exact approved
PNG bytes, dimensions, and every official SVG. No font file or runtime
dependency is bundled.

The documentation diagrams have their own deterministic source generator:

```powershell
$env:PYTHONDONTWRITEBYTECODE="1"
python tools/render_diagrams.py --write
python tools/render_diagrams.py --check
```

Normal verification runs `--check`. Use `--write` only after deliberately
changing the shared diagram system or diagram content.

Run `--write` only after reviewing an official source change. It regenerates
the shape-only PNGs and refreshes the manifest; it does not silently replace
the reviewed social preview export. Normal verification uses `--check` and
must not change committed files.

For contribution and support routes, see [Contributing](../CONTRIBUTING.md)
and [Support](../SUPPORT.md).

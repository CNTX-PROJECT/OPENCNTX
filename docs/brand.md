# Brand guide

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

The OPENCNTX identity is calm, readable, and symmetric. It uses one simple
context-frame symbol and a standard sans-serif wordmark.

## Core rule

- Write `OPENCNTX` in uppercase without a space.
- `OPEN` is purple.
- `CNTX` is near-black on a light screen and white on a dark screen.
- Use the same purple context-frame symbol for the avatar and wordmark.
- Center the complete mark, not only the text.

## Official colors

| Use | Light screen | Dark screen |
|---|---|---|
| Background | `#FFFFFF` | `#0D1117` |
| OPEN and diagram accent | `#6D28D9` | `#C084FC` |
| CNTX and main text | `#111318` | `#FFFFFF` |
| Diagram card | `#F6F3FF` | `#17131F` |
| Secondary text | `#4B5563` | `#D1D5DB` |
| Avatar square | `#7C3AED` | `#7C3AED` |

The tested text pairs meet WCAG AA contrast for normal text.

## Typography

Official text assets use:

```text
Arial, Helvetica, sans-serif
```

These are standard system fonts. The wordmark is ordinary bold text, not a
hand-built alphabet. Do not replace it with decorative or AI-generated text.

## Official files

| File | Use |
|---|---|
| `opencntx-wordmark-light.svg` | centered wordmark on a light screen |
| `opencntx-wordmark-dark.svg` | centered wordmark on a dark screen |
| `opencntx-avatar.svg` | theme-neutral avatar source without small text |
| `opencntx-avatar-512.png` | generated avatar upload |
| `opencntx-symbol-light.svg` | compact symbol for a light screen |
| `opencntx-symbol-dark.svg` | compact symbol for a dark screen |
| `opencntx-icon-32.png` | generated small icon |
| `opencntx-icon-128.png` | generated large icon |
| `opencntx-social-preview.svg` | standard-font social preview source |
| `opencntx-social-preview-1280x640.png` | approved exact social preview export |

Documentation diagrams use the light filename as the default and a matching
`-dark.svg` file for dark screens. Both variants must have identical words and
geometry.

## Alignment and clear space

- Keep equal visible space on the left and right of every mark.
- Keep repeated diagram cards equal in width and height.
- Keep arrow starts, arrow ends, headings, and card text on shared lines.
- Do not display the horizontal wordmark below 240 pixels wide.
- Use the compact symbol below that width.
- Keep the avatar square and do not crop the purple shape.

## Do not

- change the OPEN/CNTX color relationship;
- use a light image on a dark screen or the reverse;
- add gradients, shadows, glow, or decorative network lines;
- stretch, rotate, or crop the mark;
- add small text to the avatar;
- use uneven margins or unequal repeated shapes;
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

Run `--write` only after reviewing an official source change. It regenerates
the shape-only PNGs and refreshes the manifest; it does not silently replace
the reviewed social preview export. Normal verification uses `--check` and
must not change committed files.

For contribution and support routes, see [Contributing](../CONTRIBUTING.md)
and [Support](../SUPPORT.md).

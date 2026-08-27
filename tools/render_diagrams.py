from __future__ import annotations

import argparse
import html
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAGRAM_ROOT = ROOT / "assets" / "docs"
FONT = "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"

THEMES = {
    "light": {
        "bg": "#F8FAFC",
        "surface": "#FFFFFF",
        "surface_alt": "#F1F5F9",
        "ink": "#0F172A",
        "muted": "#475569",
        "border": "#CBD5E1",
        "line": "#94A3B8",
        "violet": "#DDA0DD",
        "violet_text": "#DDA0DD",
        "violet_soft": "#0B1020",
        "cyan": "#0891B2",
        "cyan_soft": "#CFFAFE",
        "green": "#047857",
        "green_soft": "#D1FAE5",
        "amber": "#B45309",
        "amber_soft": "#FEF3C7",
        "red": "#B91C1C",
        "red_soft": "#FEE2E2",
    },
    "dark": {
        "bg": "#0B1020",
        "surface": "#111827",
        "surface_alt": "#1E293B",
        "ink": "#F8FAFC",
        "muted": "#CBD5E1",
        "border": "#334155",
        "line": "#64748B",
        "violet": "#DDA0DD",
        "violet_text": "#DDA0DD",
        "violet_soft": "#1E293B",
        "cyan": "#22D3EE",
        "cyan_soft": "#164E63",
        "green": "#34D399",
        "green_soft": "#064E3B",
        "amber": "#FBBF24",
        "amber_soft": "#78350F",
        "red": "#FCA5A5",
        "red_soft": "#7F1D1D",
    },
}


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def text(
    x: float,
    y: float,
    value: str,
    *,
    size: int = 20,
    weight: int = 500,
    fill: str = "{ink}",
    anchor: str = "start",
    letter_spacing: float | None = None,
) -> str:
    spacing = "" if letter_spacing is None else f' letter-spacing="{letter_spacing}"'
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{fill}" '
        f'font-family="{FONT}" font-size="{size}" font-weight="{weight}"{spacing}>'
        f"{esc(value)}</text>"
    )


def header(kicker: str, title: str, subtitle: str) -> list[str]:
    width = max(124, 28 + len(kicker) * 8)
    return [
        f'<rect x="60" y="42" width="{width}" height="32" rx="16" fill="{{violet_soft}}"/>',
        text(
            60 + width / 2,
            64,
            kicker,
            size=13,
            weight=750,
            fill="{violet_text}",
            anchor="middle",
            letter_spacing=1.6,
        ),
        text(60, 124, title, size=40, weight=750, letter_spacing=-1.1),
        text(60, 158, subtitle, size=18, weight=450, fill="{muted}"),
    ]


def arrow(x1: float, x2: float, y: float) -> list[str]:
    return [
        f'<line x1="{x1}" y1="{y}" x2="{x2 - 10}" y2="{y}" stroke="{{line}}" stroke-width="2" stroke-linecap="round"/>',
        f'<polyline points="{x2 - 18},{y - 8} {x2 - 10},{y} {x2 - 18},{y + 8}" fill="none" stroke="{{line}}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    ]


def flow_card(
    identifier: str,
    x: float,
    y: float,
    width: float,
    height: float,
    number: str,
    title_value: str,
    lines: tuple[str, ...],
    *,
    accent: str = "violet",
    soft: str = "violet_soft",
    title_size: int = 23,
) -> list[str]:
    center = x + width / 2
    number_color = "violet_text" if accent == "violet" else accent
    result = [
        f'<rect x="{x + 4}" y="{y + 8}" width="{width}" height="{height}" rx="20" fill="{{surface_alt}}"/>',
        f'<rect id="card-{identifier}" x="{x}" y="{y}" width="{width}" height="{height}" rx="20" fill="{{surface}}" stroke="{{border}}" stroke-width="2"/>',
        f'<rect x="{x}" y="{y}" width="{width}" height="6" rx="3" fill="{{{accent}}}"/>',
        f'<circle cx="{center}" cy="{y + 54}" r="22" fill="{{{soft}}}"/>',
        text(
            center,
            y + 61,
            number,
            size=16,
            weight=800,
            fill=f"{{{number_color}}}",
            anchor="middle",
        ),
        text(
            center,
            y + 108,
            title_value,
            size=title_size,
            weight=720,
            anchor="middle",
            letter_spacing=-0.4,
        ),
    ]
    for index, line_value in enumerate(lines):
        result.append(
            text(
                center,
                y + 150 + index * 30,
                line_value,
                size=16,
                weight=450,
                fill="{muted}",
                anchor="middle",
            )
        )
    return result


def overview() -> tuple[int, str, str, list[str]]:
    body = header(
        "CORE PROMISE",
        "Small context. Clear evidence. Any model.",
        "A deliberate three-step path from local files to reviewed output.",
    )
    xs = (60, 435, 810)
    items = (
        (
            "select",
            "01",
            "Select",
            ("Choose local UTF-8 files", "Set patterns and budgets"),
            "violet",
            "violet_soft",
        ),
        (
            "review",
            "02",
            "Review",
            ("Inspect the context package", "Verify paths, bytes, and hashes"),
            "cyan",
            "cyan_soft",
        ),
        (
            "share",
            "03",
            "Share",
            ("Use the reviewed output", "with any tool you choose"),
            "green",
            "green_soft",
        ),
    )
    for index, (identifier, number, title_value, lines, accent, soft) in enumerate(items):
        body.extend(
            flow_card(
                identifier,
                xs[index],
                218,
                330,
                232,
                number,
                title_value,
                lines,
                accent=accent,
                soft=soft,
            )
        )
        if index < 2:
            body.extend(arrow(xs[index] + 338, xs[index + 1] - 8, 334))
    return (
        500,
        "OPENCNTX overview",
        "Three stages turn selected local files into a reviewable context package that the user may share with any AI tool.",
        body,
    )


def core_flow() -> tuple[int, str, str, list[str]]:
    body = header(
        "FIVE CHECKPOINTS",
        "The complete core flow",
        "Every checkpoint is visible, reviewable, and under your control.",
    )
    xs = (60, 284, 508, 732, 956)
    items = (
        ("init", "01", "Init", ("Create config",)),
        ("pack", "02", "Preview / pack", ("Build package",)),
        ("inspect", "03", "Inspect", ("Read all output",)),
        ("verify", "04", "Verify", ("Check drift",)),
        ("share", "05", "Share", ("Your decision",)),
    )
    for index, (identifier, number, title_value, lines) in enumerate(items):
        accent = "green" if index == 4 else ("cyan" if index == 3 else "violet")
        soft = "green_soft" if index == 4 else ("cyan_soft" if index == 3 else "violet_soft")
        body.extend(
            flow_card(
                identifier,
                xs[index],
                218,
                184,
                204,
                number,
                title_value,
                lines,
                accent=accent,
                soft=soft,
                title_size=19,
            )
        )
        if index < 4:
            body.extend(arrow(xs[index] + 191, xs[index + 1] - 7, 320))
    return (
        472,
        "Core package flow",
        "Five checkpoints show initialization, preview and packing, human review, verification, and optional sharing.",
        body,
    )


def context_selection() -> tuple[int, str, str, list[str]]:
    body = header(
        "TASK-BOUND CONTEXT",
        "Load only what the task proves it needs",
        "A simple temperature model keeps attention on the current objective.",
    )
    items = (
        ("hot", 60, "HOT", "Control and exact task", "Always required", "red", "red_soft", "01"),
        (
            "warm",
            435,
            "WARM",
            "Pinned current knowledge",
            "Included by relation",
            "amber",
            "amber_soft",
            "02",
        ),
        ("cold", 810, "COLD", "Unrelated project history", "Not loaded", "cyan", "cyan_soft", "03"),
    )
    for identifier, x, title_value, first, second, accent, soft, number in items:
        body.extend(
            flow_card(
                identifier,
                x,
                218,
                330,
                232,
                number,
                title_value,
                (first, second),
                accent=accent,
                soft=soft,
            )
        )
    return (
        500,
        "Task-bound context selection",
        "Hot, warm, and cold lanes separate required task context, related knowledge, and excluded history.",
        body,
    )


def owner_flow() -> tuple[int, str, str, list[str]]:
    body = header(
        "AUTHORITY CHAIN",
        "Every authority change is explicit",
        "The OWNER remains the only final authority from goal through acceptance.",
    )
    xs = (60, 244, 428, 612, 796, 980)
    items = (
        ("goal", "01", "OWNER", ("Goal",)),
        ("proposal", "02", "ARCHITECT", ("Proposal",)),
        ("approval", "03", "OWNER", ("Approval",)),
        ("work", "04", "EXECUTOR", ("Bounded work",)),
        ("review", "05", "ARCHITECT", ("Review",)),
        ("decision", "06", "OWNER", ("Decision",)),
    )
    for index, (identifier, number, title_value, lines) in enumerate(items):
        is_owner = title_value == "OWNER"
        body.extend(
            flow_card(
                identifier,
                xs[index],
                218,
                160,
                204,
                number,
                title_value,
                lines,
                accent="cyan" if is_owner else "violet",
                soft="cyan_soft" if is_owner else "violet_soft",
                title_size=16,
            )
        )
        if index < 5:
            body.extend(arrow(xs[index] + 166, xs[index + 1] - 6, 320))
    return (
        472,
        "OWNER approval flow",
        "Six checkpoints preserve explicit authority from the OWNER goal to the OWNER decision.",
        body,
    )


def roadmap() -> tuple[int, str, str, list[str]]:
    body = header(
        "RELEASE JOURNEY",
        "Completed public milestones",
        "The public line progresses from a small core to a stable project workspace.",
    )
    body.append(
        '<line x1="160" y1="274" x2="1040" y2="274" stroke="{border}" stroke-width="6" stroke-linecap="round"/>'
    )
    xs = (60, 340, 620, 900)
    items = (
        ("core", "01", "CORE", ("init · pack · verify",)),
        ("v010", "02", "v0.1.0", ("Public core release",)),
        ("workspace", "03", "WORKSPACE", ("Stable project flow",)),
        ("v100", "04", "v1.0.0", ("Production/Stable line",)),
    )
    for identifier, number, title_value, lines in items:
        body.extend(
            flow_card(
                identifier,
                xs[int(number) - 1],
                218,
                240,
                204,
                "✓",
                title_value,
                lines,
                accent="green",
                soft="green_soft",
                title_size=20,
            )
        )
    return (
        472,
        "Completed OPENCNTX roadmap",
        "Four completed milestones show the runnable core, public core release, workspace foundation, and version 1.0.0 Production Stable line.",
        body,
    )


def workspace_map() -> tuple[int, str, str, list[str]]:
    body = header(
        "OPTIONAL WORKSPACE",
        "Stable workspace for longer projects",
        "Four clearly separated areas keep authority, evidence, knowledge, and work understandable.",
    )
    items = (
        (
            "control",
            60,
            218,
            "01",
            "CONTROL",
            ("OWNER, ROADMAP, CURRENT",),
            "violet",
            "violet_soft",
        ),
        (
            "sources",
            620,
            218,
            "02",
            "SOURCES",
            ("Exact supplied bytes and receipts",),
            "cyan",
            "cyan_soft",
        ),
        (
            "knowledge",
            60,
            414,
            "03",
            "KNOWLEDGE",
            ("Chapters, catalog, derived text",),
            "amber",
            "amber_soft",
        ),
        (
            "work",
            620,
            414,
            "04",
            "BOUNDED WORK",
            ("Tasks, playbooks, roles, results",),
            "green",
            "green_soft",
        ),
    )
    for identifier, x, y, number, title_value, lines, accent, soft in items:
        body.extend(
            flow_card(
                identifier,
                x,
                y,
                520,
                162,
                number,
                title_value,
                lines,
                accent=accent,
                soft=soft,
                title_size=19,
            )
        )
    body.extend(
        [
            '<line x1="580" y1="299" x2="600" y2="299" stroke="{line}" stroke-width="2" stroke-linecap="round"/>',
            '<line x1="590" y1="289" x2="590" y2="496" stroke="{line}" stroke-width="2" stroke-linecap="round"/>',
            '<line x1="580" y1="496" x2="600" y2="496" stroke="{line}" stroke-width="2" stroke-linecap="round"/>',
            '<circle cx="590" cy="397" r="6" fill="{violet}"/>',
        ]
    )
    return (
        626,
        "Stable workspace map",
        "Four areas organize control, captured sources, reviewed knowledge, and bounded work inside one stable optional workspace.",
        body,
    )


def security_boundary() -> tuple[int, str, str, list[str]]:
    body = header(
        "PRIVACY BOUNDARY",
        "Local until you choose to share",
        "OPENCNTX does not upload your files; the final transfer remains your decision.",
    )
    body.extend(
        [
            '<rect x="44" y="202" width="742" height="264" rx="28" fill="none" stroke="{violet}" stroke-width="2" stroke-dasharray="10 10"/>',
            '<rect x="68" y="186" width="164" height="32" rx="16" fill="{violet_soft}"/>',
            text(
                150,
                208,
                "LOCAL BOUNDARY",
                size=13,
                weight=780,
                fill="{violet_text}",
                anchor="middle",
                letter_spacing=1.4,
            ),
        ]
    )
    body.extend(
        flow_card(
            "local-files",
            72,
            234,
            310,
            204,
            "01",
            "LOCAL FILES",
            ("You select the input", "Nothing is uploaded"),
            accent="violet",
            soft="violet_soft",
            title_size=19,
        )
    )
    body.extend(
        flow_card(
            "opencntx",
            426,
            234,
            310,
            204,
            "02",
            "OPENCNTX",
            ("Builds and verifies locally", "You inspect the output"),
            accent="cyan",
            soft="cyan_soft",
            title_size=19,
        )
    )
    body.extend(arrow(389, 419, 336))
    body.extend(
        flow_card(
            "external",
            846,
            234,
            294,
            204,
            "03",
            "EXTERNAL TOOL",
            ("Receives only what you send", "Outside OPENCNTX control"),
            accent="green",
            soft="green_soft",
            title_size=18,
        )
    )
    body.extend(arrow(786, 839, 336))
    body.extend(
        [
            '<rect x="757" y="370" width="112" height="28" rx="14" fill="{green_soft}"/>',
            text(
                813,
                390,
                "YOUR DECISION",
                size=11,
                weight=800,
                fill="{green}",
                anchor="middle",
                letter_spacing=1.0,
            ),
        ]
    )
    return (
        516,
        "Local security boundary",
        "Local files stay inside the OPENCNTX boundary until the user separately chooses to share reviewed output with an external tool.",
        body,
    )


BUILDERS = {
    "context-selection": context_selection,
    "core-flow": core_flow,
    "opencntx-overview": overview,
    "owner-flow": owner_flow,
    "roadmap": roadmap,
    "security-boundary": security_boundary,
    "workspace-map": workspace_map,
}


def render(name: str, theme_name: str) -> bytes:
    height, title_value, description, body = BUILDERS[name]()
    theme = THEMES[theme_name]
    title_suffix = " for dark screens" if theme_name == "dark" else ""
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" role="img" aria-labelledby="title desc">',
        f'  <title id="title">{esc(title_value + title_suffix)}</title>',
        f'  <desc id="desc">{esc(description)}</desc>',
        f'  <rect width="1200" height="{height}" fill="{theme["bg"]}"/>',
    ]
    lines.extend(f"  {item.format(**theme)}" for item in body)
    lines.append("</svg>")
    return ("\n".join(lines) + "\n").encode()


def write_diagrams() -> None:
    DIAGRAM_ROOT.mkdir(parents=True, exist_ok=True)
    for name in BUILDERS:
        (DIAGRAM_ROOT / f"{name}.svg").write_bytes(render(name, "light"))
        (DIAGRAM_ROOT / f"{name}-dark.svg").write_bytes(render(name, "dark"))


def check_diagrams() -> None:
    with tempfile.TemporaryDirectory(prefix="opencntx-diagrams-") as directory:
        target = Path(directory)
        for name in BUILDERS:
            expected = {
                target / f"{name}.svg": render(name, "light"),
                target / f"{name}-dark.svg": render(name, "dark"),
            }
            for temporary, content in expected.items():
                temporary.write_bytes(content)
                committed = DIAGRAM_ROOT / temporary.name
                if committed.read_bytes() != content:
                    raise SystemExit(f"diagram drift: {temporary.name}")
    print("DOCUMENTATION_DIAGRAMS_OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render and verify official OPENCNTX documentation diagrams."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write all light and dark SVG diagrams")
    mode.add_argument("--check", action="store_true", help="verify committed diagrams")
    args = parser.parse_args()
    if args.write:
        write_diagrams()
    else:
        check_diagrams()


if __name__ == "__main__":
    main()

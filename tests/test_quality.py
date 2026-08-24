from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import shlex
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from opencntx.cli import build_parser

README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
DOCS = ROOT / "docs"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _configure_windows_ci_temp_root() -> None:
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        return
    runner_temp = os.environ.get("RUNNER_TEMP")
    if runner_temp is None:
        raise RuntimeError("Windows GitHub Actions requires RUNNER_TEMP")
    canonical_temp = Path(runner_temp).resolve()
    if not canonical_temp.is_dir():
        raise RuntimeError("Windows GitHub Actions RUNNER_TEMP must exist")
    tempfile.tempdir = str(canonical_temp)


_configure_windows_ci_temp_root()

GUIDES = {
    "brand.md",
    "chapters-and-catalog.md",
    "context-navigation.md",
    "context-packets.md",
    "core.md",
    "commands.md",
    "contracts-and-compatibility.md",
    "faq.md",
    "glossary.md",
    "how-it-works.md",
    "media.md",
    "owner-flow.md",
    "playbooks-and-roles.md",
    "privacy-storage-lifecycle.md",
    "roadmap.md",
    "release-artifacts.md",
    "security.md",
    "start-here.md",
    "platforms.md",
    "troubleshooting.md",
    "workspace.md",
}

LIGHT_DIAGRAMS = {
    "context-selection.svg",
    "core-flow.svg",
    "opencntx-overview.svg",
    "owner-flow.svg",
    "roadmap.svg",
    "security-boundary.svg",
    "workspace-map.svg",
}
DARK_DIAGRAMS = {name.replace(".svg", "-dark.svg") for name in LIGHT_DIAGRAMS}
DIAGRAMS = LIGHT_DIAGRAMS | DARK_DIAGRAMS

PRIMARY_NAVIGATION = (
    "[Start here](start-here.md) · [How it works](how-it-works.md) · "
    "[Advanced / Alpha workspace](workspace.md) · [Commands](commands.md) · "
    "[Security](security.md) · [All docs](README.md)"
)
LEGACY_PRIMARY_NAVIGATION = PRIMARY_NAVIGATION.replace(
    "[Advanced / Alpha workspace]", "[Workspace]"
)
PROTECTED_LEGACY_NAVIGATION_GUIDES = {"brand.md", "roadmap.md", "security.md"}

EXPECTED_ACTION_USES = {
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
}

ORIENTATION_COMMAND_PATHS = (
    "opencntx --help",
    "opencntx --version",
    "opencntx workspace --help",
    "opencntx workspace media --help",
    "opencntx workspace task --help",
)

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
COMMAND_ROW = re.compile(r"^\|\s*\d+\s*\|\s*`([^`]+)`\s*\|", re.MULTILINE)
SHELL_FENCE_LANGUAGES = {"", "bash", "powershell", "sh", "shell"}


def _parser_leaf_command_paths(
    parser: argparse.ArgumentParser,
    prefix: tuple[str, ...] = ("opencntx",),
) -> tuple[str, ...]:
    subparser_actions = tuple(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    if not subparser_actions:
        return (" ".join(prefix),)

    paths: list[str] = []
    for action in subparser_actions:
        for name, child_parser in action.choices.items():
            paths.extend(_parser_leaf_command_paths(child_parser, (*prefix, name)))
    return tuple(paths)


def _public_shell_examples() -> tuple[tuple[Path, int, str], ...]:
    markdown_files = (README, ROOT / "SECURITY.md", *sorted(DOCS.glob("*.md")))
    examples: list[tuple[Path, int, str]] = []

    for markdown_file in markdown_files:
        lines = markdown_file.read_text(encoding="utf-8").splitlines()
        in_fence = False
        language = ""
        block: list[str] = []
        block_start = 0

        for line_number, line in enumerate(lines, start=1):
            if line.startswith("```"):
                if not in_fence:
                    in_fence = True
                    language = line[3:].strip().lower()
                    block = []
                    block_start = line_number + 1
                    continue

                if language in SHELL_FENCE_LANGUAGES:
                    index = 0
                    while index < len(block):
                        command = block[index].strip()
                        command_line = block_start + index
                        if command.startswith("opencntx "):
                            while command.endswith(("`", "\\")):
                                command = command[:-1].rstrip() + " "
                                index += 1
                                if index >= len(block):
                                    break
                                command += block[index].strip()
                            examples.append((markdown_file, command_line, command))
                        index += 1

                in_fence = False
                language = ""
                block = []
                continue

            if in_fence:
                block.append(line)

    return tuple(examples)


def _link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    return target.split(maxsplit=1)[0]


def _local_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    links: list[str] = []
    for match in MARKDOWN_LINK.finditer(text):
        target = _link_target(match.group(1))
        parsed = urlsplit(target)
        if parsed.scheme in {"http", "https", "mailto"} or not parsed.path:
            continue
        links.append(unquote(parsed.path))
    return links


class PublicQualityTests(unittest.TestCase):
    def test_all_local_markdown_links_resolve_within_repository(self) -> None:
        markdown_files = sorted(
            path
            for path in ROOT.rglob("*.md")
            if ".git" not in path.parts and ".opencntx" not in path.parts
        )
        self.assertTrue(markdown_files)

        for markdown_file in markdown_files:
            for target in _local_links(markdown_file):
                with self.subTest(file=markdown_file, target=target):
                    self.assertFalse(target.startswith("file://"))
                    self.assertFalse(Path(target).is_absolute())
                    self.assertIsNone(WINDOWS_ABSOLUTE.match(target))
                    resolved = (markdown_file.parent / target).resolve()
                    self.assertTrue(resolved.is_relative_to(ROOT))
                    self.assertTrue(resolved.exists())

    def test_docs_index_links_every_guide(self) -> None:
        index_links = {Path(target).as_posix() for target in _local_links(DOCS / "README.md")}
        self.assertEqual(GUIDES, index_links & GUIDES)

        for guide_name in GUIDES:
            guide = DOCS / guide_name
            text = guide.read_text(encoding="utf-8")
            headings = [line for line in text.splitlines() if line.startswith("# ")]
            self.assertEqual(1, len(headings), guide_name)
            self.assertIn("README.md", _local_links(guide), guide_name)

        command_text = (DOCS / "commands.md").read_text(encoding="utf-8")
        documented_paths = tuple(COMMAND_ROW.findall(command_text))
        executable_paths = _parser_leaf_command_paths(build_parser())
        self.assertEqual(
            ORIENTATION_COMMAND_PATHS + executable_paths,
            documented_paths,
        )
        self.assertEqual(44, len(executable_paths))
        self.assertEqual(49, len(documented_paths))

    def test_public_shell_examples_are_accepted_by_the_real_parser(self) -> None:
        parser = build_parser()
        examples = _public_shell_examples()
        self.assertTrue(examples)

        for markdown_file, line_number, command in examples:
            with self.subTest(
                document=markdown_file.relative_to(ROOT),
                line=line_number,
                command=command,
            ):
                arguments = shlex.split(command, posix=True)
                self.assertEqual("opencntx", arguments[0])
                try:
                    with (
                        contextlib.redirect_stdout(io.StringIO()),
                        contextlib.redirect_stderr(io.StringIO()),
                    ):
                        parser.parse_args(arguments[1:])
                except SystemExit as exc:
                    if exc.code != 0:
                        self.fail(
                            f"{markdown_file.relative_to(ROOT)}:{line_number}: "
                            f"parser rejected {command!r} with exit code {exc.code}"
                        )

    def test_readme_is_compact_and_links_the_docs(self) -> None:
        lines = README.read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), 180)
        text = README.read_text(encoding="utf-8")
        self.assertIn('srcset="assets/brand/opencntx-wordmark-dark.svg"', text)
        self.assertIn('src="assets/brand/opencntx-wordmark-light.svg"', text)
        self.assertIn('<div align="center">', text)
        self.assertIn("[Start here](docs/start-here.md)", text)
        targets = {Path(target).as_posix() for target in _local_links(README)}
        required = {
            "docs/start-here.md",
            "docs/how-it-works.md",
            "docs/workspace.md",
            "docs/commands.md",
            "docs/security.md",
            "docs/README.md",
        }
        self.assertTrue(required.issubset(targets))

    def test_one_start_page_and_fixed_primary_navigation(self) -> None:
        self.assertTrue((DOCS / "start-here.md").is_file())
        self.assertFalse((DOCS / "installation.md").exists())
        self.assertFalse((DOCS / "getting-started.md").exists())
        for markdown in (README, CHANGELOG, ROOT / "SUPPORT.md", *DOCS.glob("*.md")):
            with self.subTest(markdown=markdown.relative_to(ROOT)):
                text = markdown.read_text(encoding="utf-8")
                self.assertNotIn("installation.md", text)
                self.assertNotIn("getting-started.md", text)

        for guide_name in GUIDES:
            with self.subTest(guide=guide_name):
                lines = (DOCS / guide_name).read_text(encoding="utf-8").splitlines()
                expected_navigation = (
                    LEGACY_PRIMARY_NAVIGATION
                    if guide_name in PROTECTED_LEGACY_NAVIGATION_GUIDES
                    else PRIMARY_NAVIGATION
                )
                self.assertIn(expected_navigation, lines[:5])

        readme_navigation = PRIMARY_NAVIGATION.replace("](", "](docs/").replace(
            "](docs/README.md)", "](docs/README.md)"
        )
        self.assertIn(readme_navigation, README.read_text(encoding="utf-8"))

    def test_community_and_security_routes_are_bounded(self) -> None:
        required = {
            "CONTRIBUTING.md",
            "CODE_OF_CONDUCT.md",
            "SUPPORT.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/ISSUE_TEMPLATE/config.yml",
            ".github/pull_request_template.md",
        }
        self.assertTrue(all((ROOT / path).is_file() for path in required))

        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
        issue_config = (ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")
        pull_request = (ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8")
        self.assertIn("Report a vulnerability", security)
        self.assertIn("SUPPORT.md", security)
        self.assertIn("public issue", support)
        self.assertIn("blank_issues_enabled: false", issue_config)
        self.assertIn("/security/advisories/new", issue_config)
        self.assertNotIn("mailto:", issue_config)
        for phrase in (
            "Security and privacy boundaries",
            "New or changed dependencies",
            "Documentation and changelog",
            "render_brand.py --check",
            "Zero automated checks is not green evidence",
        ):
            self.assertIn(phrase, pull_request)

    def test_all_public_guidance_is_english(self) -> None:
        public_files = [
            README,
            CHANGELOG,
            ROOT / "SECURITY.md",
            ROOT / "CODE_OF_CONDUCT.md",
            ROOT / "CONTRIBUTING.md",
            ROOT / "SUPPORT.md",
            ROOT / "examples" / "minimal" / "opencntx.toml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml",
            ROOT / ".github" / "pull_request_template.md",
            *(DOCS / name for name in sorted(GUIDES)),
            DOCS / "README.md",
        ]
        forbidden_phrases = (
            "Versiestatus",
            "Installeren",
            "Toegevoegd",
            "Bekende beperkingen",
            "documentatie-index",
            "werkruimte",
            "hoofdstuk",
            "veiligheidsgrenzen",
            "Meld een",
            "Voor u begint",
            "Gedragscode",
            "Bijdragen aan",
        )
        for path in public_files:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                for phrase in forbidden_phrases:
                    self.assertNotIn(phrase, text)

    def test_documentation_diagrams_are_safe_accessible_and_complete(self) -> None:
        diagram_root = ROOT / "assets" / "docs"
        actual = {path.name for path in diagram_root.glob("*.svg")}
        self.assertEqual(DIAGRAMS, actual)
        forbidden = (
            b"<script",
            b"<image",
            b"<foreignObject",
            b"<iframe",
            b"<animate",
            b"href=",
            b"url(",
        )
        for name in sorted(DIAGRAMS):
            with self.subTest(name=name):
                data = (diagram_root / name).read_bytes()
                data.decode("utf-8", errors="strict")
                for token in forbidden:
                    self.assertNotIn(token, data)
                self.assertIn(b'role="img"', data)
                self.assertIn(b'aria-labelledby="title desc"', data)
                self.assertIn(b'<title id="title">', data)
                self.assertIn(b'<desc id="desc">', data)

        for light_name in sorted(LIGHT_DIAGRAMS):
            dark_name = light_name.replace(".svg", "-dark.svg")
            with self.subTest(pair=light_name):
                light = ElementTree.parse(diagram_root / light_name).getroot()
                dark = ElementTree.parse(diagram_root / dark_name).getroot()
                self.assertEqual("1200", light.attrib["width"])
                self.assertEqual(light.attrib["viewBox"], dark.attrib["viewBox"])
                self.assertEqual("#FFFFFF", list(light)[2].attrib["fill"])
                self.assertEqual("#0D1117", list(dark)[2].attrib["fill"])

                def geometry(root):
                    result = []
                    for element in root.iter():
                        name = element.tag.rsplit("}", 1)[-1]
                        if name == "title":
                            continue
                        attrs = tuple(
                            sorted(
                                (key, value)
                                for key, value in element.attrib.items()
                                if key not in {"fill", "stroke"}
                            )
                        )
                        result.append((name, attrs, (element.text or "").strip()))
                    return result

                self.assertEqual(geometry(light), geometry(dark))

                cards = [
                    element
                    for element in light.iter()
                    if element.tag.rsplit("}", 1)[-1] == "rect"
                    and element.attrib.get("stroke-width") == "4"
                ]
                widths = {float(card.attrib["width"]) for card in cards}
                heights = {float(card.attrib["height"]) for card in cards}
                self.assertEqual(1, len(widths))
                self.assertEqual(1, len(heights))
                x_values = sorted({float(card.attrib["x"]) for card in cards})
                width = widths.pop()
                self.assertEqual(60.0, x_values[0])
                self.assertEqual(1140.0, x_values[-1] + width)
                if len(x_values) > 2:
                    gaps = {
                        x_values[index + 1] - x_values[index] - width
                        for index in range(len(x_values) - 1)
                    }
                    self.assertEqual(1, len(gaps))

        public_markdown = "\n".join(
            path.read_text(encoding="utf-8") for path in (README, *DOCS.glob("*.md"))
        )
        for light_name in LIGHT_DIAGRAMS:
            dark_name = light_name.replace(".svg", "-dark.svg")
            self.assertIn(light_name, public_markdown)
            self.assertIn(dark_name, public_markdown)

    def test_workflow_uses_immutable_official_action_pins(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        uses = {
            line.split("uses:", 1)[1].split("#", 1)[0].strip()
            for line in text.splitlines()
            if "uses:" in line
        }
        self.assertEqual(EXPECTED_ACTION_USES, uses)
        for action in uses:
            self.assertRegex(action, r"^actions/[a-z-]+@[0-9a-f]{40}$")

    def test_workflow_permissions_and_triggers_are_bounded(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", text)
        self.assertIn("push:", text)
        self.assertIn("contents: read", text)
        self.assertIn("persist-credentials: false", text)
        for forbidden in (
            "pull_request_target",
            "contents: write",
            "actions: write",
            "id-token: write",
            "packages: write",
            "secrets.",
            "upload-artifact",
            "workflow_dispatch",
        ):
            self.assertNotIn(forbidden, text)

    def test_workflow_matrix_and_commands_cover_tests_build_install_smoke(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        for value in (
            "ubuntu-latest",
            "windows-latest",
            '"3.11"',
            '"3.12"',
            '"3.13"',
            '"3.14"',
            "PYTHONDONTWRITEBYTECODE",
            "PYTHONUTF8",
            "python -m pip install --disable-pip-version-check build==1.3.0 setuptools==83.0.0",
            "python -m pip install --disable-pip-version-check -r requirements-quality.txt",
            "python -m pip check",
            'environment.write("PIP_NO_INDEX=1\\n")',
            'environment.write(f"PIP_FIND_LINKS={wheelhouse}\\n")',
            "python -W error::ResourceWarning -m unittest discover -s tests",
            "COVERAGE_FILE: ${{ runner.temp }}/opencntx-coverage-data",
            "python -W error::ResourceWarning -m coverage run --branch --source=opencntx -m unittest discover -s tests",
            'python -m coverage json -o "${{ runner.temp }}/opencntx-coverage.json"',
            "python tools/quality_gate.py metrics",
            'python tools/quality_gate.py coverage "${{ runner.temp }}/opencntx-coverage.json"',
            "python tools/quality_gate.py lint",
            "python tools/quality_gate.py types",
            "python -m pip install --disable-pip-version-check -r requirements-security.txt",
            "python -m pip_audit -r requirements-quality.txt --format json",
            "tools/r8_hardening.py",
            "timeout-minutes: 30",
            '"tools/release_artifacts.py"',
            '"build"',
            '"smoke"',
            '"--expected-commit"',
            '"--expected-tree"',
        ):
            self.assertIn(value, text)

        quality_requirements = (ROOT / "requirements-quality.txt").read_text(encoding="utf-8")
        self.assertEqual(
            {
                "build==1.3.0",
                "coverage==7.15.4",
                "hypothesis==6.165.10",
                "mypy==2.3.1",
                "ruff==0.16.3",
                "setuptools==83.0.0",
            },
            set(quality_requirements.splitlines()),
        )
        self.assertEqual(
            "pip-audit==2.10.1\n",
            (ROOT / "requirements-security.txt").read_text(encoding="utf-8"),
        )
        with (ROOT / "pyproject.toml").open("rb") as project_file:
            project = tomllib.load(project_file)["project"]
        self.assertNotIn("dependencies", project)
        self.assertEqual(
            {
                "Programming Language :: Python :: 3.11",
                "Programming Language :: Python :: 3.12",
                "Programming Language :: Python :: 3.13",
                "Programming Language :: Python :: 3.14",
            },
            {
                classifier
                for classifier in project["classifiers"]
                if classifier.startswith("Programming Language :: Python :: 3.")
            },
        )
        self.assertNotIn("Operating System :: OS Independent", project["classifiers"])
        self.assertEqual(1, text.count("${{ matrix.os }} / Python ${{ matrix.python-version }}"))

    def test_public_ci_status_is_active_and_unambiguous(self) -> None:
        status_documents = (README, CHANGELOG, DOCS / "platforms.md")
        for document in status_documents:
            with self.subTest(document=document.name):
                text = document.read_text(encoding="utf-8")
                self.assertIn("CI_ACTIVE", text)
                self.assertNotIn("CI_DEFINED_INACTIVE", text)
                self.assertIn("live", text.lower())
        if os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true":
            self.assertEqual(
                Path(os.environ["RUNNER_TEMP"]).resolve(),
                Path(tempfile.gettempdir()).resolve(),
            )

    def test_objective_attempt_guidance_keeps_evidence_and_authority_bounded(self) -> None:
        commands = (DOCS / "commands.md").read_text(encoding="utf-8")
        owner_flow = (DOCS / "owner-flow.md").read_text(encoding="utf-8")
        playbooks = (DOCS / "playbooks-and-roles.md").read_text(encoding="utf-8")
        security = (DOCS / "security.md").read_text(encoding="utf-8")
        troubleshooting = (DOCS / "troubleshooting.md").read_text(encoding="utf-8")
        for option in (
            "--executor-id",
            "--action",
            "--command-type",
            "--target",
            "--input",
            "--exit-status",
            "--error-class",
            "--actions-used",
            "--duration-ms",
            "--result-evidence",
        ):
            self.assertIn(option, commands)
        self.assertNotIn("--error-signature", commands)
        self.assertNotIn("--new-basis", commands)
        for limit in (
            "SEMANTIC_REPEAT_LIMIT",
            "TOTAL_ATTEMPT_LIMIT",
            "CUMULATIVE_ACTION_LIMIT",
            "CUMULATIVE_TIME_LIMIT",
        ):
            self.assertIn(limit, troubleshooting)
        self.assertIn(
            "OPENCNTX does not run the external command",
            " ".join(owner_flow.split()),
        )
        self.assertIn("not a login", playbooks)
        self.assertIn("do not prove", security)

    def test_release_surfaces_are_consistent(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as project_file:
            project = tomllib.load(project_file)["project"]
        version = project["version"]

        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertIn("Development Status :: 3 - Alpha", project["classifiers"])
        changelog = CHANGELOG.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")
        start_here = (DOCS / "start-here.md").read_text(encoding="utf-8")
        faq = (DOCS / "faq.md").read_text(encoding="utf-8")
        roadmap = (DOCS / "roadmap.md").read_text(encoding="utf-8")
        workspace = (DOCS / "workspace.md").read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
        release_tool = (ROOT / "tools" / "release_artifacts.py").read_text(encoding="utf-8")

        self.assertRegex(changelog, rf"(?m)^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$")
        self.assertIn(
            "git clone --depth 1 https://github.com/CNTX-PROJECT/OPENCNTX.git",
            readme,
        )
        self.assertIn(
            f"git clone --branch v{version} --depth 1 https://github.com/CNTX-PROJECT/OPENCNTX.git",
            readme,
        )
        self.assertIn("The optional workspace layer", workspace)
        self.assertIn("installed --version output differs", release_tool)
        self.assertIn("expected_version", release_tool)
        self.assertNotRegex(workflow, r'expected_version\s*=\s*["\']\d')

        for public_surface in (readme, start_here, faq, roadmap):
            with self.subTest(surface=public_surface[:40]):
                self.assertIn("Alpha", public_surface)
                self.assertNotRegex(public_surface, r"(?i)\bstable release\b")

        release_surfaces = (
            ROOT / "pyproject.toml",
            ROOT / "src" / "opencntx" / "__init__.py",
            WORKFLOW,
            ROOT / "tests" / "test_cli.py",
            CHANGELOG,
            README,
            DOCS / "workspace.md",
        )
        for surface in release_surfaces:
            with self.subTest(surface=surface.relative_to(ROOT)):
                self.assertNotIn("0.2.0.dev0", surface.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

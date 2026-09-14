"""Local, deterministic knowledge indexing and presentation contracts.

The 1.8.0 knowledge layer deliberately uses ordinary Markdown/JSON metadata,
stable SHA-256 identities and bounded exact-first search. It never embeds,
uploads, executes, or rewrites a user's source files.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

INDEX_FORMAT = "ocx-index-v1"
SOURCE_NODE_FORMAT = "ocx-source-node-v1"
LINK_MANIFEST_FORMAT = "ocx-link-manifest-v1"
SEARCH_RESULT_FORMAT = "ocx-search-result-v1"
TECHNIQUE_FORMAT = "ocx-technique-card-v1"
ADOPTION_FORMAT = "ocx-project-adoption-v1"
FOOTER_FORMAT = "ocx-footer-contract-v1"

TEXT_SUFFIXES = frozenset({".md", ".markdown", ".json", ".toml", ".yaml", ".yml", ".txt"})
SKIP_DIRECTORIES = frozenset({".git", ".opencntx", ".venv", "venv", "__pycache__", "node_modules"})
RELATIONS = frozenset(
    {"contains", "requires", "supports", "history_of", "supersedes", "verify_live", "references"}
)
VERIFICATION_STATES = frozenset({"PROVEN", "STALE", "PROPOSED"})
TOKEN_PATTERN = re.compile(r"[\w-]+", re.UNICODE)
MARKDOWN_LINK = re.compile(r"!??\[([^\]]+)\]\(([^)]+)\)")
WIKI_LINK = re.compile(r"\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|[^\]]+)?\]\]")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


class KnowledgeError(ValueError):
    """A fail-closed knowledge contract error."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _text(value: object, field: str, maximum: int = 1_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise KnowledgeError(f"{field} must be non-empty bounded text.")
    if "\x00" in value or "\r" in value:
        raise KnowledgeError(f"{field} contains an unsafe control character.")
    return value.strip()


def _bounded_strings(value: object, field: str, maximum: int = 50) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise KnowledgeError(f"{field} must be a bounded list.")
    result = [_text(item, field, 1_000) for item in value]
    if len(result) != len(set(result)):
        raise KnowledgeError(f"{field} contains duplicates.")
    return result


def _root(root: Path) -> Path:
    try:
        selected = root.resolve(strict=True)
    except OSError as exc:
        raise KnowledgeError(f"Project root is unavailable: {root}") from exc
    if not selected.is_dir() or selected.is_symlink():
        raise KnowledgeError("Project root must be a real directory.")
    return selected


def _relative(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise KnowledgeError("A source path escaped the declared root.") from exc
    if not relative or relative.startswith("../") or "\x00" in relative:
        raise KnowledgeError("A source path is unsafe.")
    return relative


def _source_paths(root: Path, max_files: int, max_depth: int) -> list[Path]:
    selected: list[Path] = []
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name
            for name in directories
            if name not in SKIP_DIRECTORIES and not (current_path / name).is_symlink()
        )
        for name in sorted(names):
            candidate = current_path / name
            relative = _relative(root, candidate)
            if len(PurePosixPath(relative).parts) > max_depth:
                raise KnowledgeError(f"Source depth exceeds max_depth: {relative}")
            if candidate.is_symlink() or candidate.suffix.lower() not in TEXT_SUFFIXES:
                continue
            selected.append(candidate)
            if len(selected) > max_files:
                raise KnowledgeError(f"Source count exceeds max_files={max_files}.")
    return selected


def _read_source(root: Path, path: Path) -> tuple[str, bytes, str]:
    relative = _relative(root, path)
    try:
        data = path.read_bytes()
        text = data.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise KnowledgeError(f"Source is not readable UTF-8 text: {relative}") from exc
    return relative, data, text


def _summary(text: str) -> tuple[str, list[str]]:
    headings = [_text(value, "heading", 500) for value in HEADING.findall(text)[:20]]
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    preview = " ".join(lines)[:600]
    return preview, headings


def _node_id(root_id: str, relative: str) -> str:
    return "OCX-NODE-" + _digest(f"{root_id}:{relative}".encode())[:20]


def _root_id(root: Path) -> str:
    return "OCX-ROOT-" + _digest(str(root).casefold().encode("utf-8"))[:20]


def _parent_id(relative: str, by_path: Mapping[str, str], root_id: str) -> str:
    parts = PurePosixPath(relative).parts
    for count in range(len(parts) - 1, 0, -1):
        candidate = "/".join(parts[:count])
        stem = PurePosixPath(candidate).stem
        for name in (
            candidate,
            f"{candidate}.md",
            f"{candidate}/README.md",
            f"{candidate}/{stem}.md",
        ):
            if name in by_path:
                return by_path[name]
    return root_id


def _relation(line: str) -> str:
    lowered = line.casefold()
    for relation in sorted(RELATIONS - {"references"}, key=len, reverse=True):
        if relation in lowered:
            return relation
    return "references"


def _link_targets(text: str) -> Iterable[tuple[str, str, str]]:
    for match in MARKDOWN_LINK.finditer(text):
        _label, target = match.groups()
        target = target.split("?", 1)[0]
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path, _, anchor = target.partition("#")
        if path:
            yield (
                path.replace("\\", "/"),
                anchor,
                _relation(text[max(0, match.start() - 100) : match.end() + 100]),
            )
    for match in WIKI_LINK.finditer(text):
        path, anchor = match.groups()
        yield (
            path.strip().replace("\\", "/"),
            (anchor or "").strip(),
            _relation(text[max(0, match.start() - 100) : match.end() + 100]),
        )


def _normalized_target(source: str, target: str) -> str:
    base = PurePosixPath(source).parent
    candidate = PurePosixPath(target)
    if target.startswith("/"):
        candidate = PurePosixPath(target.lstrip("/"))
    else:
        candidate = base / candidate
    parts: list[str] = []
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _links(nodes: list[dict[str, Any]], texts: Mapping[str, str]) -> list[dict[str, Any]]:
    by_path = {node["path"]: node for node in nodes}
    by_id = {node["ocx_id"]: node for node in nodes}
    records: list[dict[str, Any]] = []
    for node in nodes:
        for target, anchor, relation in _link_targets(texts[node["path"]]):
            normalized = _normalized_target(node["path"], target)
            target_node = by_path.get(normalized) or by_path.get(f"{normalized}.md")
            target_id = target_node["ocx_id"] if target_node else None
            if target_id is not None and target_id not in by_id:
                raise KnowledgeError("Internal link target identity is inconsistent.")
            records.append(
                {
                    "format": LINK_MANIFEST_FORMAT,
                    "format_version": 1,
                    "source_id": node["ocx_id"],
                    "target_id": target_id,
                    "target_path": normalized,
                    "anchor": anchor or None,
                    "relation": relation,
                    "load_mode": "required"
                    if relation in {"requires", "contains"}
                    else "on_demand",
                    "reason": "resolved" if target_id else "unresolved_target",
                    "source_digest": node["digest"],
                    "revision": 1,
                }
            )
    return sorted(
        records, key=lambda item: (item["source_id"], item["target_path"], item["relation"])
    )


def _cycle_check(nodes: list[dict[str, Any]], links: list[dict[str, Any]]) -> None:
    graph: dict[str, list[str]] = {node["ocx_id"]: [] for node in nodes}
    for link in links:
        if link["relation"] == "contains" and link["target_id"]:
            graph[link["source_id"]].append(link["target_id"])
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise KnowledgeError("A contains link cycle was detected.")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in sorted(graph[node_id]):
            visit(child)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in sorted(graph):
        visit(node_id)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", delete=False, dir=path.parent, prefix=".ocx-"
        ) as handle:
            temporary = Path(handle.name)
            handle.write(_canonical_json(value))
        if temporary is None:
            raise KnowledgeError("Temporary metadata file was not created.")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_index(
    root: Path,
    *,
    output: Path | None = None,
    max_files: int = 10_000,
    max_bytes: int = 25_000_000,
    max_depth: int = 32,
) -> dict[str, Any]:
    """Build a deterministic index without changing any source file."""
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in (max_files, max_bytes, max_depth)
    ):
        raise KnowledgeError("Index budgets must be positive integers.")
    selected_root = _root(root)
    root_id = _root_id(selected_root)
    paths = _source_paths(selected_root, max_files, max_depth)
    nodes: list[dict[str, Any]] = []
    texts: dict[str, str] = {}
    total_bytes = 0
    for path in paths:
        relative, data, text = _read_source(selected_root, path)
        total_bytes += len(data)
        if total_bytes > max_bytes:
            raise KnowledgeError(f"Index byte budget exceeded: {total_bytes} > {max_bytes}.")
        preview, headings = _summary(text)
        nodes.append(
            {
                "format": SOURCE_NODE_FORMAT,
                "format_version": 1,
                "ocx_id": _node_id(root_id, relative),
                "root_id": root_id,
                "parent_id": None,
                "path": relative,
                "depth": len(PurePosixPath(relative).parts),
                "digest": _digest(data),
                "bytes": len(data),
                "title": headings[0] if headings else PurePosixPath(relative).stem,
                "headings": headings,
                "summary": preview,
                "privacy": "PRIVATE",
                "freshness": "CURRENT",
                "load_policy": "ON_DEMAND",
            }
        )
        texts[relative] = text
    nodes.sort(key=lambda node: node["path"])
    by_path = {node["path"]: node["ocx_id"] for node in nodes}
    for node in nodes:
        node["parent_id"] = _parent_id(node["path"], by_path, root_id)
    links = _links(nodes, texts)
    _cycle_check(nodes, links)
    basis: dict[str, Any] = {
        "format": INDEX_FORMAT,
        "format_version": 1,
        "root_id": root_id,
        "root_path_digest": _digest(str(selected_root).casefold().encode("utf-8")),
        "budgets": {"max_files": max_files, "max_bytes": max_bytes, "max_depth": max_depth},
        "nodes": nodes,
        "links": links,
        "stats": {
            "files": len(nodes),
            "bytes": total_bytes,
            "unresolved_links": sum(link["target_id"] is None for link in links),
        },
    }
    result = basis | {"index_digest": _digest(_canonical_json(basis))}
    destination = output or selected_root / ".opencntx" / "index-v1.json"
    _atomic_json(destination, result)
    return result


def _validate_index(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("format") != INDEX_FORMAT or value.get("format_version") != 1:
        raise KnowledgeError("Unsupported or invalid OCX index format.")
    digest = value.get("index_digest")
    basis = {key: item for key, item in value.items() if key != "index_digest"}
    if not isinstance(digest, str) or digest != _digest(_canonical_json(basis)):
        raise KnowledgeError("OCX index digest does not match its content.")
    nodes = value.get("nodes")
    links = value.get("links")
    if not isinstance(nodes, list) or not isinstance(links, list):
        raise KnowledgeError("OCX index nodes or links are invalid.")
    return dict(value)


def load_index(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError(f"OCX index cannot be read: {path}") from exc
    if not isinstance(value, dict):
        raise KnowledgeError("OCX index must be one JSON object.")
    return _validate_index(value)


def _query_terms(query: str) -> list[str]:
    selected = _text(query, "query", 500).casefold()
    terms = list(dict.fromkeys(TOKEN_PATTERN.findall(selected)))
    if not terms:
        raise KnowledgeError("query must contain searchable terms.")
    return terms


def _score(node: Mapping[str, Any], terms: list[str]) -> tuple[int, list[str], dict[str, int]]:
    path = str(node["path"]).casefold()
    title = str(node["title"]).casefold()
    headings = " ".join(str(item) for item in node.get("headings", [])).casefold()
    summary = str(node.get("summary", "")).casefold()
    score = 0
    reasons: list[str] = []
    components: dict[str, int] = {}
    for term in terms:
        if term in path:
            components["path"] = components.get("path", 0) + 100
            score += 100
            reasons.append("exact_path")
        if term in title:
            components["title"] = components.get("title", 0) + 60
            score += 60
            reasons.append("title_term")
        if term in headings:
            components["heading"] = components.get("heading", 0) + 30
            score += 30
            reasons.append("heading_term")
        if term in summary:
            components["summary"] = components.get("summary", 0) + 10
            score += 10
            reasons.append("summary_term")
    return score, sorted(set(reasons)), components


def search_index(
    index: Mapping[str, Any],
    query: str,
    *,
    max_results: int = 20,
    max_bytes: int = 100_000,
) -> dict[str, Any]:
    """Return deterministic, explainable search and bounded load states."""
    selected = _validate_index(index)
    if (
        isinstance(max_results, bool)
        or not isinstance(max_results, int)
        or not 0 < max_results <= 1_000
    ):
        raise KnowledgeError("max_results must be between 1 and 1000.")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise KnowledgeError("max_bytes must be a positive integer.")
    terms = _query_terms(query)
    scored = []
    for node in selected["nodes"]:
        score, reasons, components = _score(node, terms)
        if score:
            scored.append((score, node, reasons, components))
    scored.sort(key=lambda item: (-item[0], item[1]["path"], item[1]["ocx_id"]))
    results: list[dict[str, Any]] = []
    loaded_bytes = 0
    for score, node, reasons, components in scored[:max_results]:
        size = int(node["bytes"])
        if loaded_bytes + size <= max_bytes:
            state = "loaded"
            loaded_bytes += size
        else:
            state = "referenced" if results else "skipped"
        results.append(
            {
                "ocx_id": node["ocx_id"],
                "path": node["path"],
                "title": node["title"],
                "score": score,
                "score_components": components,
                "reason_codes": reasons,
                "bytes": size,
                "state": state,
            }
        )
    skipped_bytes = sum(item["bytes"] for item in results if item["state"] == "skipped")
    referenced_bytes = sum(item["bytes"] for item in results if item["state"] == "referenced")
    basis = {
        "format": SEARCH_RESULT_FORMAT,
        "format_version": 1,
        "index_digest": selected["index_digest"],
        "query": query,
        "query_terms": terms,
        "budgets": {"max_results": max_results, "max_bytes": max_bytes},
        "results": results,
        "loaded_bytes": loaded_bytes,
        "referenced_bytes": referenced_bytes,
        "skipped_bytes": skipped_bytes,
    }
    return basis | {"result_digest": _digest(_canonical_json(basis))}


def _technique_basis(card: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "format",
        "format_version",
        "technique_id",
        "name",
        "trigger",
        "preconditions",
        "steps",
        "tools",
        "risks",
        "outputs",
        "source_digests",
        "verification_state",
    }
    if set(card) - required - {"card_digest"} or set(card) != required | {"card_digest"}:
        raise KnowledgeError("Technique card fields differ from ocx-technique-card-v1.")
    if card["format"] != TECHNIQUE_FORMAT or card["format_version"] != 1:
        raise KnowledgeError("Technique card format is unsupported.")
    _text(card["technique_id"], "technique_id", 120)
    _text(card["name"], "name", 300)
    _text(card["trigger"], "trigger", 500)
    for field in ("preconditions", "steps", "tools", "risks", "outputs"):
        _bounded_strings(card[field], field, 50)
    digests = card["source_digests"]
    if not isinstance(digests, list) or any(
        not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item) for item in digests
    ):
        raise KnowledgeError("source_digests must contain SHA-256 values.")
    if card["verification_state"] not in VERIFICATION_STATES:
        raise KnowledgeError("verification_state is unsupported.")
    basis = {key: value for key, value in card.items() if key != "card_digest"}
    if card["card_digest"] != _digest(_canonical_json(basis)):
        raise KnowledgeError("Technique card digest does not match its content.")
    return dict(card)


def make_technique_card(
    *,
    technique_id: str,
    name: str,
    trigger: str,
    preconditions: list[str],
    steps: list[str],
    tools: list[str],
    risks: list[str],
    outputs: list[str],
    source_digests: list[str],
    verification_state: str = "PROPOSED",
) -> dict[str, Any]:
    basis = {
        "format": TECHNIQUE_FORMAT,
        "format_version": 1,
        "technique_id": _text(technique_id, "technique_id", 120),
        "name": _text(name, "name", 300),
        "trigger": _text(trigger, "trigger", 500),
        "preconditions": _bounded_strings(preconditions, "preconditions"),
        "steps": _bounded_strings(steps, "steps"),
        "tools": _bounded_strings(tools, "tools"),
        "risks": _bounded_strings(risks, "risks"),
        "outputs": _bounded_strings(outputs, "outputs"),
        "source_digests": list(source_digests),
        "verification_state": verification_state,
    }
    card = basis | {"card_digest": _digest(_canonical_json(basis))}
    return _technique_basis(card)


def save_technique(root: Path, card: Mapping[str, Any]) -> Path:
    selected_root = _root(root)
    valid = _technique_basis(card)
    destination = selected_root / ".opencntx" / "techniques" / f"{valid['technique_id']}.json"
    _atomic_json(destination, valid)
    return destination


def list_techniques(root: Path) -> list[dict[str, Any]]:
    selected_root = _root(root)
    directory = selected_root / ".opencntx" / "techniques"
    if not directory.is_dir():
        return []
    cards: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeError(f"Technique card cannot be read: {path.name}") from exc
        if not isinstance(value, dict):
            raise KnowledgeError(f"Technique card is not an object: {path.name}")
        cards.append(_technique_basis(value))
    return cards


def _adoption_kind(relative: str) -> str:
    upper = relative.upper()
    if "ROADMAP" in upper:
        return "roadmap"
    if upper.startswith("TASKS/"):
        return "task"
    if upper.startswith("PLAYBOOKS/"):
        return "playbook"
    if upper.startswith("ROLES/"):
        return "role"
    if "/TECHNIQUES/" in upper:
        return "technique"
    if "SKILL" in upper:
        return "skill"
    if "AGENT" in upper:
        return "agent"
    if "PLUGIN" in upper:
        return "plugin"
    return "source"


def build_adoption_manifest(root: Path, *, max_files: int = 5_000) -> dict[str, Any]:
    selected_root = _root(root)
    records: list[dict[str, Any]] = []
    allowed_roots = ("CONTROL", "TASKS", "PLAYBOOKS", "ROLES", "CHAPTERS", "INBOX", ".opencntx")
    candidates: list[Path] = []
    for name in allowed_roots:
        base = selected_root / name
        if base.is_dir():
            candidates.extend(
                path for path in base.rglob("*") if path.is_file() and not path.is_symlink()
            )
    config = selected_root / "opencntx.toml"
    if config.is_file():
        candidates.append(config)
    for path in sorted(set(candidates), key=lambda item: _relative(selected_root, item)):
        relative = _relative(selected_root, path)
        if relative in {".opencntx/index-v1.json", ".opencntx/adoption-v1.json"}:
            continue
        if relative.startswith(".opencntx/transactions/"):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        data = path.read_bytes()
        records.append(
            {
                "path": relative,
                "kind": _adoption_kind(relative),
                "bytes": len(data),
                "digest": _digest(data),
                "ownership": "EXISTING_LOCAL",
                "state": "DISCOVERED",
                "proposed_action": "BIND_READ_ONLY",
            }
        )
        if len(records) > max_files:
            raise KnowledgeError(f"Adoption inventory exceeds max_files={max_files}.")
    basis = {
        "format": ADOPTION_FORMAT,
        "format_version": 1,
        "project_id": "OCX-PROJECT-" + _digest(str(selected_root).casefold().encode("utf-8"))[:20],
        "root_path_digest": _digest(str(selected_root).casefold().encode("utf-8")),
        "ownership": "EXISTING_LOCAL",
        "state": "DISCOVERED",
        "proposed_action": "BIND_READ_ONLY",
        "records": records,
    }
    return basis | {"manifest_digest": _digest(_canonical_json(basis))}


def write_adoption_manifest(root: Path, output: Path | None = None) -> dict[str, Any]:
    selected_root = _root(root)
    manifest = build_adoption_manifest(selected_root)
    destination = output or selected_root / ".opencntx" / "adoption-v1.json"
    _atomic_json(destination, manifest)
    return manifest


def _fallback(value: object, default: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    return value.strip()


def make_footer_contract(
    *,
    task_note: str | None = None,
    status: str | None = None,
    now: str | None = None,
    thereafter: str | None = None,
    chat: str | None = None,
    tokens: str | None = None,
    model: str | None = None,
    proposal: str | None = "Luna/Max",
    profile: str = "commonmark",
) -> dict[str, Any]:
    if profile not in {"commonmark", "portable", "plain", "exact"}:
        raise KnowledgeError("Footer profile is unsupported.")
    basis = {
        "format": FOOTER_FORMAT,
        "format_version": 1,
        "task_note": _fallback(task_note, "geen opdrachtnotitie"),
        "status": _fallback(status, "onbekend"),
        "now": _fallback(now, "niet bepaald"),
        "thereafter": _fallback(thereafter, "niet bepaald"),
        "chat": _fallback(chat, "niet gemeten"),
        "tokens": _fallback(tokens, "niet gemeten"),
        "model": _fallback(model, "onbekend"),
        "proposal": _fallback(proposal, "Luna/Max"),
        "profile": profile,
    }
    return basis | {"contract_digest": _digest(_canonical_json(basis))}


def render_footer(contract: Mapping[str, Any]) -> str:
    required = set(make_footer_contract().keys())
    if set(contract) != required:
        raise KnowledgeError("Footer contract fields differ from ocx-footer-contract-v1.")
    basis = {key: value for key, value in contract.items() if key != "contract_digest"}
    if contract["contract_digest"] != _digest(_canonical_json(basis)):
        raise KnowledgeError("Footer contract digest does not match its content.")
    if contract["profile"] == "exact":
        return json.dumps(dict(contract), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    lines = [
        "---",
        "",
        f"**Opdracht:** {contract['task_note']}",
        f"**Status:** {contract['status']}",
        f"**Nu:** {contract['now']}",
        f"**Daarna:** {contract['thereafter']}",
        "",
        "---",
        "",
        (
            f"**Chat:** {contract['chat']} | **Tokens:** {contract['tokens']} | "
            f"**Model:** {contract['model']} | **Voorstel:** {contract['proposal']}"
        ),
        "",
    ]
    if contract["profile"] == "plain":
        lines = [
            "---",
            f"Opdracht: {contract['task_note']}",
            f"Status: {contract['status']}",
            f"Nu: {contract['now']}",
            f"Daarna: {contract['thereafter']}",
            "---",
            f"Chat: {contract['chat']} | Tokens: {contract['tokens']} | Model: {contract['model']} | Voorstel: {contract['proposal']}",
            "",
        ]
    return "\n".join(lines)


def footer_output(contract: Mapping[str, Any]) -> dict[str, Any]:
    valid = dict(contract)
    rendered = render_footer(valid)
    return valid | {"rendered": rendered, "rendered_digest": _digest(rendered.encode("utf-8"))}

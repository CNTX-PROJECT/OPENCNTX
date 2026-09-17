"""Local, deterministic knowledge indexing and presentation contracts.

The 1.8.0 knowledge layer deliberately uses ordinary Markdown/JSON metadata,
stable SHA-256 identities and bounded exact-first search. It never embeds,
uploads, executes, or rewrites a user's source files.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .knowledge_io import KnowledgeError, bounded_read, check_delivery, safe_path

INDEX_FORMAT = "ocx-index-v1"
SOURCE_NODE_FORMAT = "ocx-source-node-v1"
LINK_MANIFEST_FORMAT = "ocx-link-manifest-v1"
SEARCH_RESULT_FORMAT = "ocx-search-result-v1"
TECHNIQUE_FORMAT = "ocx-technique-card-v1"
ADOPTION_FORMAT = "ocx-project-adoption-v1"
FOOTER_FORMAT = "ocx-footer-contract-v1"
HOST_FOOTER_FORMAT = "ocx-footer-host-envelope-v1"
HOST_FOOTER_FIELDS = frozenset(
    {
        "format",
        "format_version",
        "adapter",
        "session_id",
        "source_session_id",
        "status",
        "chat_megabytes",
        "total_tokens",
        "model",
        "proposal",
        "source_digest",
        "envelope_digest",
    }
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

TEXT_SUFFIXES = frozenset({".md", ".markdown", ".json", ".toml", ".yaml", ".yml", ".txt"})
SKIP_DIRECTORIES = frozenset({".git", ".opencntx", ".venv", "venv", "__pycache__", "node_modules"})
ADOPTION_SKIP_DIRECTORIES = frozenset(
    {
        *SKIP_DIRECTORIES,
        ".cache",
        ".obsidian",
        ".hypothesis",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "out",
        "site",
        "target",
    }
)
RELATIONS = frozenset(
    {"contains", "requires", "supports", "history_of", "supersedes", "verify_live", "references"}
)
VERIFICATION_STATES = frozenset({"PROVEN", "STALE", "PROPOSED"})
TOKEN_PATTERN = re.compile(r"[\w-]+", re.UNICODE)
MARKDOWN_LINK = re.compile(r"!??\[([^\]]+)\]\(([^)]+)\)")
WIKI_LINK = re.compile(r"\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|[^\]]+)?\]\]")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise KnowledgeError(f"JSON contains a duplicate field: {key}.")
        value[key] = item
    return value


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
            if name not in ADOPTION_SKIP_DIRECTORIES and not (current_path / name).is_symlink()
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


def _decode_text(data: bytes) -> tuple[str, str]:
    """Decode common Unicode text encodings without changing source bytes."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-bom"
    return data.decode("utf-8"), "utf-8"


def _read_source(root: Path, path: Path, maximum: int = 25_000_000) -> tuple[str, bytes, str]:
    relative = _relative(root, path)
    try:
        data = bounded_read(root, relative, maximum)
        text, _encoding = _decode_text(data)
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
        if re.match(r"^\s*(?:[-*]\s+)?" + re.escape(relation) + r"\s*:", lowered):
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
                _relation(text[text.rfind("\n", 0, match.start()) + 1 : match.end()]),
            )
    for match in WIKI_LINK.finditer(text):
        path, anchor = match.groups()
        yield (
            path.strip().replace("\\", "/"),
            (anchor or "").strip(),
            _relation(text[text.rfind("\n", 0, match.start()) + 1 : match.end()]),
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
    _snapshot: list[tuple[str, str, int, str]] | None = None,
    _publish: bool = True,
) -> dict[str, Any]:
    """Build a deterministic index without changing any source file."""
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in (max_files, max_bytes, max_depth)
    ):
        raise KnowledgeError("Index budgets must be positive integers.")
    selected_root = _root(root)
    root_id = _root_id(selected_root)
    records = _snapshot
    if records is None:
        records = []
        remaining = max_bytes
        for path in _source_paths(selected_root, max_files, max_depth):
            relative = _relative(selected_root, path)
            data = bounded_read(selected_root, relative, remaining)
            remaining -= len(data)
            try:
                text, _encoding = _decode_text(data)
            except UnicodeDecodeError:
                text = ""
            records.append((relative, _digest(data), len(data), text))
    nodes: list[dict[str, Any]] = []
    texts: dict[str, str] = {}
    total_bytes = 0
    for relative, digest, size, text in records:
        total_bytes += size
        if total_bytes > max_bytes or len(nodes) >= max_files:
            raise KnowledgeError("Index snapshot exceeds its source budget.")
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
                "digest": digest,
                "bytes": size,
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
    from .knowledge_io import safe_output

    destination = safe_output(output or selected_root / ".opencntx" / "index-v1.json")
    if _publish and (
        not destination.is_file() or destination.read_bytes() != _canonical_json(result)
    ):
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
    check_delivery(
        "search-result.json", json.dumps(basis, ensure_ascii=False), _digest(_canonical_json(basis))
    )
    return basis | {"result_digest": _digest(_canonical_json(basis))}


def _technique_basis(card: Mapping[str, Any], *, legacy_read: bool = False) -> dict[str, Any]:
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
    identifier = _text(card["technique_id"], "technique_id", 120)
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(10)),
        *(f"LPT{i}" for i in range(10)),
    }
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", identifier)
        or identifier.endswith(".")
        or identifier.split(".")[0].upper() in reserved
    ):
        raise KnowledgeError("technique_id must be a portable single file identifier.")
    _text(card["name"], "name", 300)
    _text(card["trigger"], "trigger", 500)
    for field in ("preconditions", "steps", "tools", "risks", "outputs"):
        _bounded_strings(card[field], field, 50)
    digests = card["source_digests"]
    if not isinstance(digests, list) or any(
        not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item) for item in digests
    ):
        raise KnowledgeError("source_digests must contain SHA-256 values.")
    if card["verification_state"] == "PROVEN" and not digests and not legacy_read:
        raise KnowledgeError("PROVEN requires non-empty source digest evidence.")
    if card["verification_state"] not in VERIFICATION_STATES:
        raise KnowledgeError("verification_state is unsupported.")
    basis = {key: value for key, value in card.items() if key != "card_digest"}
    if card["card_digest"] != _digest(_canonical_json(basis)):
        raise KnowledgeError("Technique card digest does not match its content.")
    return dict(card)


def _stale_technique(card: Mapping[str, Any]) -> dict[str, Any]:
    basis = {key: value for key, value in card.items() if key != "card_digest"}
    basis["verification_state"] = "STALE"
    return basis | {"card_digest": _digest(_canonical_json(basis))}


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


def save_technique(
    root: Path, card: Mapping[str, Any], *, expected_digest: str | None = None
) -> Path:
    """Create once, or update with the exact previously observed card digest."""
    from .integrity import IntegrityError, writer_transaction

    selected_root = _root(root)
    valid = _technique_basis(card)
    try:
        with writer_transaction(selected_root, "knowledge-technique") as transaction:
            store = safe_path(selected_root, ".opencntx/techniques", directory=True)
            store.mkdir(exist_ok=True)
            relative = f".opencntx/techniques/{valid['technique_id']}.json"
            destination = safe_path(selected_root, relative)
            if destination.exists():
                current = _technique_basis(
                    json.loads(bounded_read(selected_root, relative, 100_000)), legacy_read=True
                )
                if expected_digest is None and current == valid:
                    return destination
                accepted_digests = {current["card_digest"]}
                if current["verification_state"] == "PROVEN":
                    # Recall can project PROVEN to STALE without rewriting disk.
                    # Bind the update to either view of these exact card fields.
                    accepted_digests.add(_stale_technique(current)["card_digest"])
                if expected_digest not in accepted_digests:
                    raise KnowledgeError("Technique update requires the current expected digest.")
            elif expected_digest is not None:
                raise KnowledgeError("Technique update target does not exist.")
            transaction.track_target(destination)
            _atomic_json(destination, valid)
            transaction.mark_target_published(destination)
            return destination
    except (IntegrityError, OSError, json.JSONDecodeError) as exc:
        raise KnowledgeError("Technique write failed; existing state was preserved.") from exc


def list_techniques(root: Path, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    selected_root = _root(root)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise KnowledgeError("Technique limit must be between 1 and 1000.")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise KnowledgeError("Technique offset must be non-negative.")
    if not (selected_root / ".opencntx").exists():
        return []
    directory = safe_path(selected_root, ".opencntx/techniques", directory=True)
    if not directory.is_dir():
        return []
    cards: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"))[offset : offset + limit]:
        try:
            value = json.loads(bounded_read(selected_root, _relative(selected_root, path), 100_000))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeError(f"Technique card cannot be read: {path.name}") from exc
        if not isinstance(value, dict):
            raise KnowledgeError(f"Technique card is not an object: {path.name}")
        cards.append(_technique_basis(value, legacy_read=True))
    if any(card["verification_state"] == "PROVEN" for card in cards):
        current_digests: set[str] = set()
        remaining = 25_000_000
        for path in _source_paths(selected_root, 10_000, 32):
            data = bounded_read(selected_root, _relative(selected_root, path), remaining)
            remaining -= len(data)
            current_digests.add(_digest(data))
        for card in cards:
            if card["verification_state"] == "PROVEN" and (
                not card["source_digests"] or not set(card["source_digests"]) <= current_digests
            ):
                card.update(_stale_technique(card))
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


def _adoption_scope(relative: str) -> str:
    """Classify archive boundaries without treating them as active project content."""
    for part in PurePosixPath(relative).parts:
        upper = part.upper()
        if upper == "BACKUP":
            return "BACKUP"
        if upper in {"ARCHIVE", bytes.fromhex("41524348494546").decode("ascii")}:
            return "ARCHIVE"
        if upper == "HISTORICAL":
            return "HISTORICAL"
    return "ACTIVE"


def _adoption_finding(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def _adoption_candidates(root: Path, findings: list[dict[str, str]]) -> list[Path]:
    candidates: list[Path] = []
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_directories: list[str] = []
        for name in sorted(directories):
            path = current_path / name
            if path.is_symlink():
                findings.append(
                    _adoption_finding(
                        "LINK_PRESENT",
                        _relative(root, path),
                        "A symlink or junction needs explicit owner review.",
                    )
                )
            elif name not in ADOPTION_SKIP_DIRECTORIES or name == ".opencntx":
                kept_directories.append(name)
        directories[:] = kept_directories
        for name in sorted(names):
            path = current_path / name
            relative = _relative(root, path)
            if path.is_symlink():
                findings.append(
                    _adoption_finding(
                        "LINK_PRESENT",
                        relative,
                        "A symlink or junction needs explicit owner review.",
                    )
                )
            elif path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                candidates.append(path)
    return candidates


def _adoption_project_state(root: Path, records: list[dict[str, Any]]) -> tuple[str, str]:
    if not records:
        return "EMPTY_NEW_PROJECT", "BOOTSTRAP_PROJECT"
    managed_roots = {"CONTROL", "TASKS", "PLAYBOOKS", "ROLES", "CHAPTERS", "INBOX"}
    managed = False
    for record in records:
        path = PurePosixPath(str(record["path"]))
        first = path.parts[0].upper() if path.parts else ""
        if first in managed_roots or str(record["kind"]) != "source":
            managed = True
            break
    if (root / "opencntx.toml").is_file() or (root / ".opencntx" / "adoption-v1.json").is_file():
        managed = True
    return (
        ("EXISTING_MANAGED", "BIND_READ_ONLY")
        if managed
        else ("EXISTING_UNMANAGED_PARTIAL", "AUDIT_THEN_BIND")
    )


def build_adoption_manifest(root: Path, *, max_files: int = 5_000) -> dict[str, Any]:
    selected_root = _root(root)
    records: list[dict[str, Any]] = []
    texts: dict[str, str] = {}
    findings: list[dict[str, str]] = []
    candidates = _adoption_candidates(selected_root, findings)
    for path in sorted(set(candidates), key=lambda item: _relative(selected_root, item)):
        relative = _relative(selected_root, path)
        if relative in {
            ".opencntx/index-v1.json",
            ".opencntx/adoption-v1.json",
            ".opencntx/search-v2.json",
        }:
            continue
        if relative.startswith(".opencntx/transactions/"):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            findings.append(_adoption_finding("UNREADABLE_SOURCE", relative, str(exc)))
            continue
        encoding = "unknown"
        try:
            texts[relative], encoding = _decode_text(data)
        except UnicodeDecodeError:
            findings.append(
                _adoption_finding(
                    "UNSUPPORTED_ENCODING", relative, "The source encoding is not supported."
                )
            )
            texts[relative] = ""
        records.append(
            {
                "path": relative,
                "kind": _adoption_kind(relative),
                "scope": _adoption_scope(relative),
                "bytes": len(data),
                "digest": _digest(data),
                "encoding": encoding,
                "ownership": "EXISTING_LOCAL",
                "state": "DISCOVERED",
                "proposed_action": "BIND_READ_ONLY",
            }
        )
        if len(records) > max_files:
            raise KnowledgeError(f"Adoption inventory exceeds max_files={max_files}.")
    by_casefold: dict[str, list[str]] = {}
    by_ordinal: dict[tuple[str, str], list[str]] = {}
    ordinal_pattern = re.compile(r"^(\d+(?:\.\d+)*)(?:\s*[-_.]\s*|\s+)")
    for record in records:
        relative = str(record["path"])
        by_casefold.setdefault(relative.casefold(), []).append(relative)
        pure = PurePosixPath(relative)
        match = ordinal_pattern.match(pure.name)
        if match:
            key = (pure.parent.as_posix().casefold(), match.group(1))
            by_ordinal.setdefault(key, []).append(relative)
    for paths in by_casefold.values():
        if len(paths) > 1:
            for conflict_path in sorted(paths):
                findings.append(
                    _adoption_finding(
                        "CASE_COLLISION",
                        conflict_path,
                        "Another discovered path differs only by case.",
                    )
                )
    for paths in by_ordinal.values():
        if len(paths) > 1:
            for ordinal_path in sorted(paths):
                findings.append(
                    _adoption_finding(
                        "DUPLICATE_ORDINAL",
                        ordinal_path,
                        "Sibling items share one numeric ordinal.",
                    )
                )
    root_id = _root_id(selected_root)
    nodes = [
        {
            "format": SOURCE_NODE_FORMAT,
            "format_version": 1,
            "ocx_id": _node_id(root_id, str(record["path"])),
            "path": record["path"],
            "digest": record["digest"],
        }
        for record in records
    ]
    links = _links(nodes, texts)
    for link in links:
        if link["target_id"] is None:
            findings.append(
                _adoption_finding(
                    "UNRESOLVED_LINK",
                    str(link["source_id"]),
                    f"Target is not present: {link['target_path']}",
                )
            )
    try:
        _cycle_check(nodes, links)
    except KnowledgeError:
        findings.append(
            _adoption_finding(
                "CONTAINS_CYCLE", "", "The discovered contains graph contains a cycle."
            )
        )
    findings.sort(key=lambda item: (item["code"], item["path"], item["detail"]))
    project_state, proposed_action = _adoption_project_state(selected_root, records)
    audit = {
        "status": (
            "BLOCKED"
            if findings
            else "PARTIAL"
            if project_state == "EXISTING_UNMANAGED_PARTIAL"
            else "READY"
        ),
        "project_state": project_state,
        "coverage": "FULL_SUPPORTED_TEXT_SCOPE",
        "findings": findings,
        "records": len(records),
        "links": len(links),
    }
    basis = {
        "format": ADOPTION_FORMAT,
        "format_version": 1,
        "project_id": "OCX-PROJECT-" + _digest(str(selected_root).casefold().encode("utf-8"))[:20],
        "root_path_digest": _digest(str(selected_root).casefold().encode("utf-8")),
        "ownership": "EXISTING_LOCAL",
        "state": "DISCOVERED",
        "proposed_action": proposed_action,
        "records": records,
        "audit": audit,
        "source_tree_digest": _digest(_canonical_json({"records": records, "audit": audit})),
    }
    return basis | {"manifest_digest": _digest(_canonical_json(basis))}


def write_adoption_manifest(
    root: Path,
    output: Path | None = None,
    *,
    expected_manifest_digest: str | None = None,
) -> dict[str, Any]:
    selected_root = _root(root)
    manifest = build_adoption_manifest(selected_root)
    if manifest["proposed_action"] == "AUDIT_THEN_BIND" and expected_manifest_digest is None:
        raise KnowledgeError(
            "An existing unmanaged project requires a reviewed preview digest before binding."
        )
    if (
        expected_manifest_digest is not None
        and manifest["manifest_digest"] != expected_manifest_digest
    ):
        raise KnowledgeError("The adoption source changed after its preview digest was approved.")
    store = selected_root / ".opencntx"
    if store.is_symlink() or (store.exists() and not store.is_dir()):
        raise KnowledgeError("The project metadata store is not a safe product-owned directory.")
    destination = (output or store / "adoption-v1.json").expanduser().absolute()
    try:
        destination.relative_to(store.absolute())
    except ValueError as exc:
        raise KnowledgeError("The adoption manifest must remain inside .opencntx.") from exc
    if destination.is_symlink() or destination.parent.is_symlink():
        raise KnowledgeError("The adoption manifest path must not follow a symlink.")
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
        "task_note": _fallback(task_note, "no assignment note"),
        "status": _fallback(status, "unknown"),
        "now": _fallback(now, "not determined"),
        "thereafter": _fallback(thereafter, "not determined"),
        "chat": _fallback(chat, "not measured"),
        "tokens": _fallback(tokens, "not measured"),
        "model": _fallback(model, "unknown"),
        "proposal": _fallback(proposal, "Luna/Max"),
        "profile": profile,
    }
    return basis | {"contract_digest": _digest(_canonical_json(basis))}


def _host_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise KnowledgeError(f"{field} must be a lowercase SHA-256 digest.")
    return value


def _optional_host_metric(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise KnowledgeError(f"{field} must be a non-negative finite number or null.")
    if not math.isfinite(float(value)) or value < 0:
        raise KnowledgeError(f"{field} must be a non-negative finite number or null.")
    return float(value)


def _optional_host_tokens(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise KnowledgeError("total_tokens must be a non-negative integer or null.")
    return value


def validate_footer_host_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one session-bound, digest-protected host footer envelope."""
    if not isinstance(envelope, Mapping) or set(envelope) != HOST_FOOTER_FIELDS:
        raise KnowledgeError("Footer host envelope fields differ from its closed v1 contract.")
    value = dict(envelope)
    if (
        value["format"] != HOST_FOOTER_FORMAT
        or isinstance(value["format_version"], bool)
        or value["format_version"] != 1
    ):
        raise KnowledgeError("Footer host envelope format is unsupported.")
    adapter = _text(value["adapter"], "adapter", 200)
    session_id = _text(value["session_id"], "session_id", 256)
    source_session_id = _text(value["source_session_id"], "source_session_id", 256)
    if session_id != source_session_id:
        raise KnowledgeError("Footer host envelope session identities differ.")
    if not isinstance(value["status"], str) or value["status"] not in {
        "OK",
        "UNAVAILABLE",
    }:
        raise KnowledgeError("Footer host envelope status is unsupported.")
    chat_megabytes = _optional_host_metric(value["chat_megabytes"], "chat_megabytes")
    total_tokens = _optional_host_tokens(value["total_tokens"])
    model = None if value["model"] is None else _text(value["model"], "model", 200)
    proposal = None if value["proposal"] is None else _text(value["proposal"], "proposal", 200)
    source_digest = _host_digest(value["source_digest"], "source_digest")
    envelope_digest = _host_digest(value["envelope_digest"], "envelope_digest")
    if value["status"] == "OK" and (
        chat_megabytes is None or total_tokens is None or model is None
    ):
        raise KnowledgeError("An OK footer host envelope must contain complete telemetry.")
    if value["status"] == "UNAVAILABLE" and (
        chat_megabytes is not None or total_tokens is not None or model is not None
    ):
        raise KnowledgeError(
            "An unavailable footer host envelope cannot contain partial telemetry."
        )
    basis = {key: item for key, item in value.items() if key != "envelope_digest"}
    if envelope_digest != _digest(_canonical_json(basis)):
        raise KnowledgeError("Footer host envelope digest does not match its content.")
    return {
        "format": HOST_FOOTER_FORMAT,
        "format_version": 1,
        "adapter": adapter,
        "session_id": session_id,
        "source_session_id": source_session_id,
        "status": value["status"],
        "chat_megabytes": chat_megabytes,
        "total_tokens": total_tokens,
        "model": model,
        "proposal": proposal,
        "source_digest": source_digest,
        "envelope_digest": envelope_digest,
    }


def load_footer_envelope(path: Path, *, max_bytes: int = 65_536) -> dict[str, Any]:
    """Load one bounded UTF-8 host envelope without following a symlink."""
    selected = path.expanduser().resolve()
    if path.is_symlink() or not selected.is_file():
        raise KnowledgeError(f"Footer host envelope is not a regular file: {path}")
    try:
        if selected.stat().st_size > max_bytes:
            raise KnowledgeError("Footer host envelope exceeds its bounded size.")
        value = json.loads(selected.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except KnowledgeError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError(f"Footer host envelope cannot be read: {path}") from exc
    if not isinstance(value, dict):
        raise KnowledgeError("Footer host envelope must contain one JSON object.")
    return validate_footer_host_envelope(value)


def _format_host_chat(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " MB"


def _format_host_tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"≈{value / 1_000_000:.1f}".replace(".", ",") + "M"
    if value >= 1_000:
        return f"≈{value / 1_000:.1f}".replace(".", ",") + "k"
    return str(value)


def make_footer_contract_from_host_envelope(
    envelope: Mapping[str, Any],
    *,
    task_note: str | None = None,
    status: str | None = None,
    now: str | None = None,
    thereafter: str | None = None,
    profile: str = "commonmark",
) -> dict[str, Any]:
    """Compile a footer from exact host telemetry or explicit unavailable fallbacks."""
    value = validate_footer_host_envelope(envelope)
    chat: str | None
    tokens: str | None
    model: str | None
    if value["status"] == "OK":
        chat = _format_host_chat(value["chat_megabytes"])
        tokens = _format_host_tokens(value["total_tokens"])
        model = value["model"]
    else:
        chat = tokens = model = None
    return make_footer_contract(
        task_note=task_note,
        status=status,
        now=now,
        thereafter=thereafter,
        chat=chat,
        tokens=tokens,
        model=model,
        proposal=value["proposal"],
        profile=profile,
    )


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
        f"**Assignment:** {contract['task_note']}",
        f"**Status:** {contract['status']}",
        f"**Now:** {contract['now']}",
        f"**Then:** {contract['thereafter']}",
        "",
        "---",
        "",
        (
            f"**Chat:** {contract['chat']} · **Tokens:** {contract['tokens']} · "
            f"**Model:** {contract['model']} · **Proposal:** {contract['proposal']}"
        ),
        "",
    ]
    if contract["profile"] == "plain":
        lines = [
            "---",
            f"Assignment: {contract['task_note']}",
            f"Status: {contract['status']}",
            f"Now: {contract['now']}",
            f"Then: {contract['thereafter']}",
            "---",
            f"Chat: {contract['chat']} · Tokens: {contract['tokens']} · Model: {contract['model']} · Proposal: {contract['proposal']}",
            "",
        ]
    return "\n".join(lines)


def footer_output(contract: Mapping[str, Any]) -> dict[str, Any]:
    valid = dict(contract)
    rendered = render_footer(valid)
    return valid | {"rendered": rendered, "rendered_digest": _digest(rendered.encode("utf-8"))}

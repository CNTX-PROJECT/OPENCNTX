"""Small deterministic local secret-signal policy for core context packages."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass

POLICY_VERSION = 1
CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_WARNING = "WARNING"


@dataclass(frozen=True)
class SecretFinding:
    finding_id: str
    rule_id: str
    confidence: str
    path: str
    line: int
    column: int


@dataclass(frozen=True)
class SecretAssessment:
    warnings: tuple[SecretFinding, ...]
    blocked: tuple[SecretFinding, ...]
    overrides: tuple[SecretFinding, ...]


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    confidence: str
    expression: re.Pattern[str]


_HIGH_RULES = (
    _Rule(
        rule_id="private-key-header",
        confidence=CONFIDENCE_HIGH,
        expression=re.compile(
            r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----",
        ),
    ),
    _Rule(
        rule_id="github-classic-token",
        confidence=CONFIDENCE_HIGH,
        expression=re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
    ),
    _Rule(
        rule_id="github-fine-grained-token",
        confidence=CONFIDENCE_HIGH,
        expression=re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,255}\b"),
    ),
    _Rule(
        rule_id="aws-secret-access-key",
        confidence=CONFIDENCE_HIGH,
        expression=re.compile(
            r"\bAWS_SECRET_ACCESS_KEY\b[ \t]*[:=][ \t]*[\"']?"
            r"[A-Za-z0-9/+=]{40}[\"']?",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
)

_WARNING_RULES = (
    _Rule(
        rule_id="credential-like-assignment",
        confidence=CONFIDENCE_WARNING,
        expression=re.compile(
            r"\b(?:password|passwd|db[_-]?password|database[_-]?password|"
            r"app[_-]?secret|token|api[_-]?key|client[_-]?secret|authorization)"
            r"\b[\"']?"
            r"[ \t]*[:=][ \t]*"
            r"(?:"
            r"\\\"[^\"\r\n]{8,}\\\"|"
            r"\"[^\"\r\n]{8,}\"|"
            r"'[^'\r\n]{8,}'|"
            r"(?![A-Za-z_][A-Za-z0-9_]*\()[^\s\"'#]{8,}"
            r")",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    _Rule(
        rule_id="basic-auth-url",
        confidence=CONFIDENCE_WARNING,
        expression=re.compile(
            r"(?:https?|postgres(?:ql)?|mysql(?:\+[a-z0-9._-]+)?|"
            r"mariadb(?:\+[a-z0-9._-]+)?|mongodb(?:\+srv)?|rediss?)://"
            r"[^/\s:@]+:[^@\s/]+@",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        rule_id="bearer-credential",
        confidence=CONFIDENCE_WARNING,
        expression=re.compile(
            r"\bBearer[ \t]+[A-Za-z0-9._~+/\-]{8,}={0,2}",
            re.IGNORECASE,
        ),
    ),
)


def _position(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    previous_newline = text.rfind("\n", 0, offset)
    column = offset + 1 if previous_newline < 0 else offset - previous_newline
    return line, column


def _finding_id(
    *,
    rule_id: str,
    path: str,
    line: int,
    column: int,
    source_sha256: str,
) -> str:
    identity = "\0".join(
        (
            f"opencntx-secret-finding-v{POLICY_VERSION}",
            rule_id,
            path,
            str(line),
            str(column),
            source_sha256,
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def scan_text(*, path: str, text: str, source_sha256: str) -> tuple[SecretFinding, ...]:
    """Return safe finding metadata without retaining matched source text."""
    candidates: list[tuple[SecretFinding, tuple[int, int]]] = []
    high_spans: list[tuple[int, int]] = []
    for rule in _HIGH_RULES:
        for match in rule.expression.finditer(text):
            line, column = _position(text, match.start())
            finding = SecretFinding(
                finding_id=_finding_id(
                    rule_id=rule.rule_id,
                    path=path,
                    line=line,
                    column=column,
                    source_sha256=source_sha256,
                ),
                rule_id=rule.rule_id,
                confidence=rule.confidence,
                path=path,
                line=line,
                column=column,
            )
            candidates.append((finding, match.span()))
            high_spans.append(match.span())

    for rule in _WARNING_RULES:
        for match in rule.expression.finditer(text):
            if any(
                match.start() < high_end and high_start < match.end()
                for high_start, high_end in high_spans
            ):
                continue
            line, column = _position(text, match.start())
            candidates.append(
                (
                    SecretFinding(
                        finding_id=_finding_id(
                            rule_id=rule.rule_id,
                            path=path,
                            line=line,
                            column=column,
                            source_sha256=source_sha256,
                        ),
                        rule_id=rule.rule_id,
                        confidence=rule.confidence,
                        path=path,
                        line=line,
                        column=column,
                    ),
                    match.span(),
                )
            )

    findings = {candidate.finding_id: candidate for candidate, _ in candidates}
    return tuple(
        sorted(
            findings.values(),
            key=lambda finding: (
                finding.path,
                finding.line,
                finding.column,
                finding.rule_id,
                finding.finding_id,
            ),
        )
    )


def scan_sources(
    sources: Iterable[tuple[str, str, str]],
) -> tuple[SecretFinding, ...]:
    findings: list[SecretFinding] = []
    for path, text, source_sha256 in sources:
        findings.extend(scan_text(path=path, text=text, source_sha256=source_sha256))
    return tuple(
        sorted(
            findings,
            key=lambda finding: (
                finding.path,
                finding.line,
                finding.column,
                finding.rule_id,
                finding.finding_id,
            ),
        )
    )


def assess_findings(
    findings: tuple[SecretFinding, ...],
    allowed_finding_ids: Iterable[str],
) -> SecretAssessment:
    requested = tuple(allowed_finding_ids)
    if len(requested) != len(set(requested)):
        raise ValueError("Each secret finding ID may be specified only once.")
    for finding_id in requested:
        if re.fullmatch(r"[0-9a-f]{64}", finding_id) is None:
            raise ValueError(
                f"Invalid secret finding ID; expected 64 lowercase hexadecimal characters: {finding_id}"
            )

    by_id = {finding.finding_id: finding for finding in findings}
    for finding_id in requested:
        finding = by_id.get(finding_id)
        if finding is None:
            raise ValueError(f"Unknown or stale secret finding ID: {finding_id}")
        if finding.confidence != CONFIDENCE_HIGH:
            raise ValueError(
                f"Only a high-confidence block can be overridden exactly: {finding_id}"
            )

    allowed = set(requested)
    warnings = tuple(finding for finding in findings if finding.confidence == CONFIDENCE_WARNING)
    blocked = tuple(
        finding
        for finding in findings
        if finding.confidence == CONFIDENCE_HIGH and finding.finding_id not in allowed
    )
    overrides = tuple(
        finding
        for finding in findings
        if finding.confidence == CONFIDENCE_HIGH and finding.finding_id in allowed
    )
    return SecretAssessment(
        warnings=warnings,
        blocked=blocked,
        overrides=overrides,
    )


def finding_record(finding: SecretFinding, *, disposition: str) -> dict[str, object]:
    return {
        "finding_id": finding.finding_id,
        "rule_id": finding.rule_id,
        "confidence": finding.confidence,
        "path": finding.path,
        "line": finding.line,
        "column": finding.column,
        "disposition": disposition,
    }


def format_finding(finding: SecretFinding) -> str:
    return (
        f"{finding.finding_id} {finding.path}:{finding.line}:{finding.column} "
        f"{finding.rule_id} {finding.confidence}"
    )

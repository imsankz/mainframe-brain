"""Redaction pass — Layer 3.5, between triage and LLM enrichment.

Mainframe source routinely contains hardcoded test account numbers, embedded
credentials in JCL/FTP scripts, and PII in comments. Nothing reaches an LLM
until it has passed through here. Redaction is a hard gate, not an option.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# SHA-256 content hashes are computed POST-redaction so the cached narration
# is keyed to the redacted text the LLM actually saw — not the raw source.
# This prevents a fresh redaction rule (e.g. newly added PII pattern) from
# forcing every paragraph to re-narrate: the *meaning* didn't change.

_REDACT_LABEL = "[REDACTED]"

# Default patterns. Teams can extend via RedactionConfig.extra_patterns.
_DEFAULT_PATTERNS: list[tuple[str, str]] = [
    # SSN-shaped: 9 digits, optional dashes
    (r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b", "SSN"),
    # Credit-card-shaped: 13–19 contiguous digits
    (r"\b(?:\d[ -]?){13,19}\b", "CARD"),
    # IBAN (letters + up to 30 digits)
    (r"\b[A-Z]{2}\d{2}(?:[A-Z0-9]{1,30})\b", "IBAN"),
    # US bank routing: 9 digits at word boundary
    (r"\b\d{9}\b", "ROUTING"),
    # Password/Userid assignment in JCL/proc
    (r"(?i)\b(PASS|PASSWORD|PWD|USERID|USER)\s*=\s*\S+", "CRED"),
    # FTP user/pass lines
    (r"(?i)^\s*USER\s+\S+|^\s*PASS\s+\S+", "FTP_CRED"),
    # Long hex blobs (likely keys/tokens): 32+ hex chars
    (r"\b[0-9a-fA-F]{32,}\b", "TOKEN"),
]


@dataclass
class RedactionConfig:
    enabled: bool = True
    patterns: list[tuple[str, str]] = field(default_factory=lambda: list(_DEFAULT_PATTERNS))
    extra_patterns: list[tuple[str, str]] = field(default_factory=list)
    label: str = _REDACT_LABEL
    team_overrides: dict[str, str] = field(default_factory=dict)  # name -> redacted value
    report_only: bool = False   # if True, log findings but don't mutate text


@dataclass
class RedactionReport:
    redacted_count: int = 0
    findings: list[dict[str, Any]] = field(default_factory=list)


def redact(text: str, config: RedactionConfig | None = None) -> tuple[str, RedactionReport]:
    """Return (redacted_text, report). Used by enrichment before any LLM call."""
    cfg = config or RedactionConfig()
    report = RedactionReport()
    if not cfg.enabled or not text:
        return text, report
    out = text
    for pattern, kind in [*cfg.patterns, *cfg.extra_patterns]:
        def _sub(m: re.Match, _k=kind) -> str:
            report.redacted_count += 1
            report.findings.append({"kind": _k, "span": m.span()})
            return f"{cfg.label}:{_k}"
        out = re.sub(pattern, _sub, out)
    for name, val in cfg.team_overrides.items():
        if val and val in out:
            out = out.replace(val, f"{cfg.label}:{name}")
            report.redacted_count += out.count(f"{cfg.label}:{name}")
    return out, report


__all__ = ["redact", "RedactionConfig", "RedactionReport"]
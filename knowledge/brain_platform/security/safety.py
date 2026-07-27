"""Pre-index safety scanning: secrets, credentials, PII heuristics → quarantine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SafetyFinding:
    kind: str
    detail: str
    severity: str  # high|medium|low


@dataclass
class SafetyReport:
    findings: list[SafetyFinding] = field(default_factory=list)

    @property
    def has_credentials(self) -> bool:
        return any(f.kind in CREDENTIAL_KINDS for f in self.findings)

    @property
    def should_quarantine(self) -> bool:
        return self.has_credentials or any(f.severity == "high" for f in self.findings)


CREDENTIAL_KINDS = frozenset(
    {
        "api_key",
        "jwt",
        "password",
        "private_key",
        "connection_string",
    }
)

_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "high"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "high"),
    ("api_key", re.compile(r"(?i)\b(sk-[A-Za-z0-9]{20,}|api[_-]?key\s*[:=]\s*\S+)"), "high"),
    ("password", re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S+"), "high"),
    (
        "connection_string",
        re.compile(r"(?i)\b(postgres|mysql|mongodb|redis)://\S+"),
        "high",
    ),
    ("bank_account", re.compile(r"(?i)\b(р/?с|расчётный счёт|iban)\b.{0,40}\d{10,}"), "medium"),
    ("card_number", re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "medium"),
    ("phone", re.compile(r"(?:\+7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}"), "low"),
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "low"),
    ("passport", re.compile(r"(?i)\bпаспорт\b.{0,20}\d{4}\s?\d{6}"), "medium"),
]


def scan_document_text(text: str) -> SafetyReport:
    report = SafetyReport()
    for kind, pattern, severity in _PATTERNS:
        if pattern.search(text):
            report.findings.append(
                SafetyFinding(kind=kind, detail=f"matched pattern for {kind}", severity=severity)
            )
    return report


def decide_index_action(report: SafetyReport) -> str:
    """Return 'index' or 'quarantine'."""
    if report.should_quarantine:
        return "quarantine"
    return "index"

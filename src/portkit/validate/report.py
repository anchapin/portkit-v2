from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    message: str
    severity: str = "error"  # error | warning
    pointer: str = ""  # RFC 6901 pointer into the file, when the rule knows one


@dataclass
class ValidationReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, path: str, rule: str, message: str, severity: str = "error", pointer: str = "") -> None:
        self.findings.append(Finding(path, rule, message, severity, pointer))

    def to_dict(self) -> dict:
        """What the agent loop actually sees. Keep it small and specific."""
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "findings": [
                {
                    "path": f.path,
                    "rule": f.rule,
                    "message": f.message,
                    "severity": f.severity,
                    **({"pointer": f.pointer} if f.pointer else {}),
                }
                for f in self.findings
            ],
        }

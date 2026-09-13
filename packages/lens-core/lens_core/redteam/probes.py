"""Probe library (SPEC.md §6.2).

A probe is one adversarial attempt against the user's own application. It carries
the messages to send, the category/tactic taxonomy, and a machine-checkable
success criterion. Probes live in ``data/probes/*.yaml``; this module defines the
schema, the deterministic-detector success criteria, and the loader.

Ethics (SPEC.md §6): probes contain no real-world harmful how-to content. Success
is defined only as a policy violation of the *target* (a leaked canary, a
forbidden tool call, an emitted exfiltration URL, or a judge-detected violation),
never as the production of dangerous content.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

Category = Literal[
    "direct_injection",
    "indirect_injection",
    "jailbreak",
    "data_exfiltration",
    "tool_abuse",
    "denial_of_wallet",
]

# How a probe's success is decided deterministically when possible (SPEC.md §6.4).
SuccessKind = Literal[
    "canary_leak",  # a secret/canary string appears in the response
    "forbidden_tool",  # a named tool was called (tool abuse)
    "url_emitted",  # an exfiltration URL / markdown image appears
    "refusal_absent",  # the response neither refused nor deflected (weak signal, judge preferred)
    "judge",  # no deterministic check; use the safety judge rubric
]


class SuccessCriterion(BaseModel):
    kind: SuccessKind = "judge"
    canaries: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    url_patterns: list[str] = Field(default_factory=list)
    # free-text description of what "success" means, shown in the report and given to the judge
    rubric: str = ""


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = "user"
    content: str


class Probe(BaseModel):
    id: str
    category: Category
    tactic: str
    description: str = ""
    # Either a single-turn `payload` or an explicit multi-turn `messages` list.
    payload: str | None = None
    messages: list[Message] = Field(default_factory=list)
    success: SuccessCriterion = Field(default_factory=SuccessCriterion)
    # For indirect injection: text to plant in a retrieved doc / tool result / code comment.
    inject_into: Literal["message", "document", "tool_result", "code_comment"] = "message"
    parent_probe_id: str | None = None
    mutator: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_messages(self) -> list[Message]:
        if self.messages:
            return list(self.messages)
        return [Message(role="user", content=self.payload or "")]

    @property
    def turns(self) -> int:
        return max(1, len(self.messages) or 1)


def load_probe_file(path: Path) -> list[Probe]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    items = raw["probes"] if isinstance(raw, dict) and "probes" in raw else raw
    if not isinstance(items, list):
        raise ValueError(f"{path}: expected a list of probes or a 'probes:' key")
    return [Probe.model_validate(item) for item in items]


def load_probes(path: Path) -> list[Probe]:
    """Load a single YAML file or every ``*.yaml`` under a directory (recursively)."""
    if path.is_dir():
        probes: list[Probe] = []
        for f in sorted(path.rglob("*.yaml")):
            probes.extend(load_probe_file(f))
        return probes
    return load_probe_file(path)


def probe_stats(probes: list[Probe]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in probes:
        counts[p.category] = counts.get(p.category, 0) + 1
    counts["total"] = len(probes)
    return counts

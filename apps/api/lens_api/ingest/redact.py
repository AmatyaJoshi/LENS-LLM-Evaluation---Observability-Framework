"""PII redaction processor (SPEC.md §4): regex-based, optional Presidio hook.

Applied to every string attribute and event attribute of spans belonging to an
app for which redaction is enabled (``LENS_REDACT_APPS``). Presidio is *not* a
dependency; if ``presidio_analyzer`` is importable it is used in addition to the
regexes, otherwise the regex pass runs alone.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from lens_core.trace.model import Span, SpanEvent

_PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "PHONE": re.compile(r"(?<!\d)(?:\+?\d{1,3}[ -]?)?(?:\(?\d{3}\)?[ -]?)\d{3}[ -]?\d{4}(?!\d)"),
    "CREDIT_CARD": re.compile(r"(?<!\d)(?:\d[ -]?){13,16}(?!\d)"),
    "SSN": re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
    "IPV4": re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"),
}

Redactor = Callable[[str], str]


def regex_redact(text: str) -> str:
    for label, pattern in _PATTERNS.items():
        text = pattern.sub(f"<{label}>", text)
    return text


def _presidio_redactor() -> Redactor | None:  # pragma: no cover - optional dependency
    try:
        from presidio_analyzer import AnalyzerEngine  # type: ignore[import-not-found]
        from presidio_anonymizer import AnonymizerEngine  # type: ignore[import-not-found]
    except ImportError:
        return None
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()

    def _redact(text: str) -> str:
        results = analyzer.analyze(text=text, language="en")
        return str(anonymizer.anonymize(text=text, analyzer_results=results).text)

    return _redact


def build_redactor(use_presidio: bool = True) -> Redactor:
    presidio = _presidio_redactor() if use_presidio else None
    if presidio is None:
        return regex_redact

    def _both(text: str) -> str:
        return regex_redact(presidio(text))

    return _both


def _redact_mapping(values: dict[str, Any], redactor: Redactor) -> dict[str, Any]:
    return {k: (redactor(v) if isinstance(v, str) else v) for k, v in values.items()}


def redact_span(span: Span, redactor: Redactor = regex_redact) -> Span:
    return span.model_copy(
        update={
            "attributes": _redact_mapping(span.attributes, redactor),
            "events": [
                SpanEvent(
                    name=e.name,
                    time_ns=e.time_ns,
                    attributes=_redact_mapping(e.attributes, redactor),
                )
                for e in span.events
            ],
        }
    )

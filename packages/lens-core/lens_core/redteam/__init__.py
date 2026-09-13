"""Red teaming (SPEC.md §6): probes, mutators, targets, runner, scoring, live detector."""

from lens_core.redteam.detector import (
    DetectionResult,
    HeuristicDetector,
    InjectionDetector,
    get_detector,
)

__all__ = ["DetectionResult", "HeuristicDetector", "InjectionDetector", "get_detector"]

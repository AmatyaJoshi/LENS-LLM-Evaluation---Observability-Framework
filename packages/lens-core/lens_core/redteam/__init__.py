"""Red teaming (SPEC.md §6): probes, mutators, targets, runner, scoring, live detector."""

from lens_core.redteam.detector import (
    DetectionResult,
    HeuristicDetector,
    InjectionDetector,
    get_detector,
)
from lens_core.redteam.mutators import ALL_MUTATORS, DETERMINISTIC, apply_deterministic
from lens_core.redteam.probes import Category, Probe, SuccessCriterion, load_probes, probe_stats
from lens_core.redteam.runner import ProbeOutcome, RedteamRunner, RunReport, aggregate
from lens_core.redteam.scoring import ProbeScore, score_probe
from lens_core.redteam.targets import (
    CallableTarget,
    HttpTarget,
    Target,
    TargetResponse,
    ToolInvocation,
)

__all__ = [
    "ALL_MUTATORS",
    "DETERMINISTIC",
    "CallableTarget",
    "Category",
    "DetectionResult",
    "HeuristicDetector",
    "HttpTarget",
    "InjectionDetector",
    "Probe",
    "ProbeOutcome",
    "ProbeScore",
    "RedteamRunner",
    "RunReport",
    "SuccessCriterion",
    "Target",
    "TargetResponse",
    "ToolInvocation",
    "aggregate",
    "apply_deterministic",
    "get_detector",
    "load_probes",
    "probe_stats",
    "score_probe",
]

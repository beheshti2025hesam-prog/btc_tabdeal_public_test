"""Execution-free paper-validation contracts."""

from .oos import PaperOOS, PaperOOSFold, PaperOOSResult
from .performance import PaperPerformance, PaperPerformanceResult, PaperTrade
from .robustness import PaperRobustness, PaperRobustnessResult
from .session import PaperAction, PaperExit, PaperObservation, PaperSession, PaperState
from .validation import PaperValidation, PaperValidationResult

__all__ = [
    "PaperAction", "PaperExit", "PaperObservation", "PaperSession", "PaperState",
    "PaperPerformance", "PaperPerformanceResult", "PaperTrade",
    "PaperRobustness", "PaperRobustnessResult",
    "PaperOOS", "PaperOOSFold", "PaperOOSResult",
    "PaperValidation", "PaperValidationResult",
]

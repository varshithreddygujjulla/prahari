"""
evidence — provenance for everything the system asserts.

Specification §8: every node, edge and insight must be traceable to its source
records. This package is the single chokepoint that makes that enforceable:
producers build assertions through `EvidenceLedger`, which refuses to record a
relationship with no supporting records. An unsupported relationship cannot be
expressed, rather than merely being discouraged by convention.
"""
from backend.evidence.provenance import (
    EvidenceLedger,
    Assertion,
    score_confidence,
    UnsupportedAssertionError,
)

__all__ = ["EvidenceLedger", "Assertion", "score_confidence",
           "UnsupportedAssertionError"]

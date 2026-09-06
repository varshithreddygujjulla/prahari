"""
anomaly — configurable, explainable deviation detection.

Replaces the original single fixed rule ("5+ calls in a day") with a suite of
detectors driven by `config.ANOMALY_CONFIG`. Every finding states the baseline
it deviated from and by how much, cites the records behind it, and carries the
human-verification notice. None of them label a person; they describe an
observation.
"""
from backend.anomaly.detectors import detect_all, DETECTORS

__all__ = ["detect_all", "DETECTORS"]

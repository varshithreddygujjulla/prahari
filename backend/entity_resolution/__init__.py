"""
entity_resolution — do two records refer to the same real-world entity?

The answer is never a bare yes. Every candidate pair carries a confidence, the
reasons behind it, and the source records, and nothing is ever merged
automatically. Wrongly fusing two people who share a surname is the single most
damaging failure this system could produce, so the scorer weighs *identifiers*
far more heavily than name similarity, and actively penalises pairs whose
identifiers disagree.
"""
from backend.entity_resolution.resolver import (
    resolve,
    normalize_name,
    soundex,
    name_similarity,
)

__all__ = ["resolve", "normalize_name", "soundex", "name_similarity"]

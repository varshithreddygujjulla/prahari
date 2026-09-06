"""
ingestion — turns the raw files in data/ into typed, ID-bearing records.

This is the only layer that knows about file formats. Everything downstream
(graph, anomaly, entity resolution) works on Record objects and can therefore
be repointed at a message queue or secure API without touching analytics code.

Each record gets a stable, deterministic record_id (CDR-0007, TXN-0012, ...)
because §8 of the specification requires every node, edge and insight to be
traceable back to the exact source record it came from. The raw CSVs carry no
identifiers of their own, so we mint them here from source name + row order.
"""
from backend.ingestion.loaders import (
    Record,
    load_all,
    SOURCES,
)

__all__ = ["Record", "load_all", "SOURCES"]

"""
graph — time-aware, evidence-backed network construction.

The schema here maps 1:1 onto a property graph, so the NetworkX prototype can be
swapped for Neo4j without touching the analytics layer: nodes carry `kind`,
edges carry `rel` plus a temporal envelope and a provenance citation list.
"""
from backend.graph.builder import build, GraphBundle
from backend.graph.temporal import (
    case_clock,
    window_bounds,
    filter_edges,
    build_events,
)

__all__ = ["build", "GraphBundle", "case_clock", "window_bounds",
           "filter_edges", "build_events"]

"""
engine.py — compatibility shim.

The analysis stack that used to live in this file now lives in focused modules
(§22). This module keeps the original public surface working so that anything
importing `run_pipeline`, `AuditChain` or `build_graph` — including
`python -m backend.engine` — behaves as before.

    backend/
      ingestion/          file formats -> Record objects with stable IDs
      evidence/           provenance ledger and the confidence model
      graph/              temporal graph construction and time windows
      entity_resolution/  candidate identity matching
      analytics/          centrality, communities, lead scoring
      anomaly/            the configurable detector suite
      audit/              SHA-256 hash chain
      api/                FastAPI routes
      pipeline.py         orchestration and caching
"""
import json
import os
import sys

# `python backend/engine.py` puts backend/ (not the package root) on sys.path,
# so the `backend.*` imports below would fail. Add the root explicitly.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                  # pragma: no cover
        pass

from backend.audit import AuditChain                         # noqa: E402,F401
from backend.graph.builder import build                      # noqa: E402
from backend.pipeline import build_payload, invalidate       # noqa: E402,F401


def run_pipeline(window: str = "all"):
    """The original entry point: the full analysed payload."""
    return build_payload(window=window)


def build_graph():
    """Original signature: (G, call_times, firs).

    Retained for callers and tests written against the previous structure.
    """
    bundle = build()
    return bundle.G, bundle.call_times, bundle.records.get("fir", [])


if __name__ == "__main__":
    result = run_pipeline()
    print(json.dumps(result["stats"], indent=2))
    print("\n--- INVESTIGATOR BRIEF ---")
    for line in result["insights"]:
        print(" •", line)
    print(f"\n--- {len(result['anomalies'])} ANOMALY FINDINGS ---")
    for a in result["anomalies"][:6]:
        print(f" [{a['severity']}/{a['confidence']}%] {a['explanation']}")
    print("\n--- TOP INVESTIGATIVE LEADS ---")
    for l in result["leads"][:5]:
        print(f" {l['lead_score']:3d}/100  {l['band']:16s}  {l['entity']}")
        for f in l["factors"]:
            print(f"          +{f['points']:<3d} {f['factor']}: {f['reason']}")

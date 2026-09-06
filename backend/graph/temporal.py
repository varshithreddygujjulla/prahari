"""
temporal.py — time windows and the case timeline.

The case clock
--------------
Relative windows ("last 7 days") are anchored to the most recent observed event
in the corpus, not to the wall clock. The synthetic case runs Jan-Mar 2026; a
wall-clock anchor would make every relative window empty and the graph would
render blank. The API returns the anchor alongside the data and the UI states
it, so the window is never mistaken for live coverage.

Edges with no event time at all (vehicle registration, subscriber registry) are
`timeless` and survive every filter — dropping a vehicle's owner because the
registration has no date would be a bug, not a filter.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend import config
from backend.ingestion import Record


def _dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- case clock
def case_clock(records: Dict[str, List[Record]]) -> Dict[str, Any]:
    """Earliest and latest observed event across every source."""
    stamps: List[datetime] = []
    for rs in records.values():
        for r in rs:
            for s in (r.timestamp, r.end_timestamp):
                d = _dt(s)
                if d:
                    stamps.append(d)
    if not stamps:
        now = datetime.now()
        return {"first_observed": None, "last_observed": None,
                "anchor": now.isoformat(timespec="seconds"),
                "anchor_source": "wall clock (no dated records found)",
                "span_days": 0}
    lo, hi = min(stamps), max(stamps)
    return {
        "first_observed": lo.isoformat(timespec="seconds"),
        "last_observed": hi.isoformat(timespec="seconds"),
        "anchor": hi.isoformat(timespec="seconds"),
        "anchor_source": "latest observed event in the case record",
        "span_days": (hi - lo).days,
        "observation_count": len(stamps),
    }


def window_bounds(window: str, clock: Dict[str, Any],
                  start: Optional[str] = None,
                  end: Optional[str] = None) -> Dict[str, Any]:
    """Resolve a window key (or explicit range) to concrete bounds."""
    anchor = _dt(clock.get("anchor")) or datetime.now()

    if window == "custom" and (start or end):
        lo = _dt(start) or _dt(clock.get("first_observed"))
        hi = _dt(end) or anchor
        return {"window": "custom", "from": lo.isoformat(timespec="seconds") if lo else None,
                "to": hi.isoformat(timespec="seconds") if hi else None,
                "label": f"{start or 'start'} → {end or 'anchor'}",
                "anchored_to": clock.get("anchor")}

    days = config.TIME_WINDOWS.get(window, None)
    if days is None:
        return {"window": "all", "from": None, "to": None,
                "label": "All recorded activity",
                "anchored_to": clock.get("anchor")}
    lo = anchor - timedelta(days=days)
    return {"window": window, "from": lo.isoformat(timespec="seconds"),
            "to": anchor.isoformat(timespec="seconds"),
            "label": f"Last {window} to {clock.get('anchor')}",
            "anchored_to": clock.get("anchor")}


def edge_in_window(edge: Dict[str, Any], bounds: Dict[str, Any]) -> bool:
    """True when the edge's observation envelope intersects the window."""
    if bounds.get("from") is None and bounds.get("to") is None:
        return True
    if edge.get("timeless"):
        return True                     # registry facts have no event time
    lo, hi = _dt(bounds.get("from")), _dt(bounds.get("to"))
    s = _dt(edge.get("start_time"))
    e = _dt(edge.get("end_time")) or s
    if s is None:
        return True                     # undated: keep rather than silently drop
    if hi and s > hi:
        return False
    if lo and (e or s) < lo:
        return False
    return True


def filter_edges(edges: List[Dict[str, Any]],
                 bounds: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [e for e in edges if edge_in_window(e, bounds)]


# ---------------------------------------------------------------- timeline
EVENT_TYPES = ["FIR", "CALL_ACTIVITY", "TRANSACTION", "TRAVEL",
               "VEHICLE_REGISTRATION", "CUSTODY_OVERLAP"]


def build_events(records: Dict[str, List[Record]],
                 call_records: Dict[tuple, List[Record]]) -> List[Dict[str, Any]]:
    """Build the case timeline.

    Individual calls are aggregated to one event per day: 118 separate dots
    would bury the transactions and travel legs that matter. The per-call
    records remain available to the anomaly engine and the evidence drawer.
    """
    events: List[Dict[str, Any]] = []

    for r in records.get("fir", []):
        if not r.timestamp:
            continue
        events.append({
            "event_id": f"EV-FIR-{r.record_id}",
            "type": "FIR",
            "timestamp": r.timestamp,
            "entities": list(r.fields.get("names", [])),
            "summary": f'{r.record_id} registered at {r.fields.get("police_station","?")}'
                       f' · {r.fields.get("sections","")}',
            "source_records": [r.record_id],
            "source_type": r.source_type,
        })

    for r in records.get("bank", []):
        if not r.timestamp:
            continue
        amt = float(r.fields.get("_amount", 0) or 0)
        events.append({
            "event_id": f"EV-TXN-{r.record_id}",
            "type": "TRANSACTION",
            "timestamp": r.timestamp,
            "entities": [],
            "amount_inr": amt,
            "summary": f'₹{amt:,.0f} · {r.fields.get("from_account","?")} → '
                       f'{r.fields.get("to_account","?")}',
            "source_records": [r.record_id],
            "source_type": r.source_type,
        })

    for r in records.get("travel", []):
        if not r.timestamp:
            continue
        events.append({
            "event_id": f"EV-TRV-{r.record_id}",
            "type": "TRAVEL",
            "timestamp": r.timestamp,
            "entities": [r.fields.get("passenger_name", "")],
            "summary": f'{r.fields.get("passenger_name","?")} · '
                       f'{r.fields.get("from_city","?")} → {r.fields.get("to_city","?")} '
                       f'({r.fields.get("flight","?")})',
            "source_records": [r.record_id],
            "source_type": r.source_type,
        })

    for r in records.get("prison", []):
        if not r.timestamp:
            continue
        events.append({
            "event_id": f"EV-PRS-{r.record_id}",
            "type": "CUSTODY_OVERLAP",
            "timestamp": r.timestamp,
            "end_timestamp": r.end_timestamp,
            "entities": [r.fields.get("prisoner_name", "")],
            "summary": f'{r.fields.get("prisoner_name","?")} in custody · '
                       f'{r.fields.get("jail","?")} {r.fields.get("cell_block","?")}',
            "source_records": [r.record_id],
            "source_type": r.source_type,
        })

    # Daily call aggregate.
    per_day: Dict[str, Dict[str, Any]] = {}
    for pair, rs in call_records.items():
        for r in rs:
            if not r.timestamp:
                continue
            day = r.timestamp[:10]
            slot = per_day.setdefault(day, {"count": 0, "pairs": set(),
                                            "records": []})
            slot["count"] += 1
            slot["pairs"].add(pair)
            slot["records"].append(r.record_id)
    for day, slot in per_day.items():
        entities = sorted({e for pair in slot["pairs"] for e in pair})
        events.append({
            "event_id": f"EV-CALL-{day}",
            "type": "CALL_ACTIVITY",
            "timestamp": f"{day}T00:00:00",
            "entities": entities,
            "call_count": slot["count"],
            "pair_count": len(slot["pairs"]),
            "summary": f'{slot["count"]} calls across {len(slot["pairs"])} contact pairs',
            "source_records": slot["records"][:40],
            "source_record_count": len(slot["records"]),
            "source_type": "COMMUNICATION_METADATA",
        })

    # Registrations are timeless; surface them as a single grouped marker so the
    # timeline stays honest about the fact they have no event date.
    veh = records.get("vehicles", [])
    if veh:
        events.append({
            "event_id": "EV-VEH-REGISTRY",
            "type": "VEHICLE_REGISTRATION",
            "timestamp": None,
            "timeless": True,
            "entities": sorted({r.fields.get("owner_name", "") for r in veh}),
            "summary": f"{len(veh)} vehicle registrations on file (no event date "
                       f"in registry records)",
            "source_records": [r.record_id for r in veh],
            "source_type": "VEHICLE_REGISTRY",
        })

    events.sort(key=lambda e: (e["timestamp"] is None, e["timestamp"] or ""))
    return events


def filter_events(events: List[Dict[str, Any]],
                  bounds: Dict[str, Any]) -> List[Dict[str, Any]]:
    if bounds.get("from") is None and bounds.get("to") is None:
        return events
    lo, hi = _dt(bounds.get("from")), _dt(bounds.get("to"))
    out = []
    for e in events:
        if e.get("timeless") or not e.get("timestamp"):
            out.append(e)
            continue
        t = _dt(e["timestamp"])
        end = _dt(e.get("end_timestamp")) or t
        if hi and t > hi:
            continue
        if lo and end < lo:
            continue
        out.append(e)
    return out

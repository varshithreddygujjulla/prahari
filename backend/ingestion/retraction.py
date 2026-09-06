"""
retraction.py — undo for ADD DATA, done the way an evidence system must.

Nothing is ever deleted from a store file. Record ids are positional (the
loader numbers rows 1..n), so physically removing a row would renumber every
row after it and silently re-point decisions, audit entries and citations at
different records. Instead:

  * every commit is recorded as an ingestion BATCH (who, when, which ids);
  * retracting a batch writes TOMBSTONES for its record ids, with a reason;
  * the loaders drop tombstoned records after numbering, so everything else
    keeps its id; the rows stay in the file for the audit trail;
  * a retraction can be restored; both actions are audited by the caller.

Only records that arrived through ADD DATA (i.e. appear in a batch) can be
retracted. The shipped corpus has no batch and is therefore untouchable here —
`reset_demo_data.py` is the only way to change it.
"""
import hashlib
import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from backend.ingestion import loaders

_LOCK = threading.Lock()


# Resolved at call time from loaders.BASE (not copied at import), so whatever
# repoints the data directory — the test isolation fixture, a deployment —
# repoints these files with it.
def _ingest_path() -> str:
    return os.path.join(loaders.BASE, "ingestions.json")


def _tomb_path() -> str:
    return os.path.join(loaders.BASE, "retracted.json")


def _load(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _save(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


class RetractionError(ValueError):
    """A retraction request that cannot be honoured (unknown batch, already
    retracted, corpus record, missing reason)."""


# ---------------------------------------------------------------- batches
def record_batch(source_type: str, record_ids: List[str], officer: str,
                 staged: bool = False, note: Optional[str] = None) -> Dict[str, Any]:
    """Register one ADD DATA commit. Returns the batch entry (with its id)."""
    now = datetime.now().replace(microsecond=0)
    digest = hashlib.sha1(("|".join(record_ids) + now.isoformat()).encode()).hexdigest()[:6]
    batch = {
        "batch_id": f"ING-{now.strftime('%Y%m%d-%H%M%S')}-{digest}",
        "timestamp": now.isoformat(),
        "officer": officer,
        "source_type": source_type,
        "staged": bool(staged),
        "record_ids": list(record_ids),
        "note": note or "",
    }
    with _LOCK:
        batches = _load(_ingest_path(), [])
        batches.append(batch)
        _save(_ingest_path(), batches)
    return batch


def retracted_ids() -> Set[str]:
    """Every record id currently tombstoned. Cheap; called once per load."""
    return set(_load(_tomb_path(), {}).keys())


def tombstones() -> Dict[str, Dict[str, Any]]:
    return _load(_tomb_path(), {})


def list_batches() -> List[Dict[str, Any]]:
    """Batches newest first, each annotated with its retraction state."""
    tomb = tombstones()
    out = []
    for b in _load(_ingest_path(), []):
        ids = b.get("record_ids", [])
        gone = [i for i in ids if i in tomb]
        entry = dict(b, retracted=bool(ids) and len(gone) == len(ids),
                     retracted_count=len(gone))
        if entry["retracted"] and gone:
            t = tomb[gone[0]]
            entry["retraction"] = {"officer": t.get("officer"), "reason": t.get("reason"),
                                   "timestamp": t.get("timestamp")}
        out.append(entry)
    out.sort(key=lambda b: b["timestamp"], reverse=True)
    return out


def _find(batch_id: str, batches: List[Dict[str, Any]]) -> Dict[str, Any]:
    for b in batches:
        if b.get("batch_id") == batch_id:
            return b
    raise RetractionError(f"no ingestion batch {batch_id!r} — only records added "
                          "through ADD DATA can be retracted; the shipped corpus "
                          "is restored with reset_demo_data.py")


def retract(batch_id: str, officer: str, reason: str) -> Dict[str, Any]:
    """Tombstone every record of a batch. The reason is mandatory: a retraction
    is an evidentiary act and the audit trail must say why."""
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise RetractionError("a reason is required to retract records")
    with _LOCK:
        batch = _find(batch_id, _load(_ingest_path(), []))
        tomb = _load(_tomb_path(), {})
        ids = batch.get("record_ids", [])
        if ids and all(i in tomb for i in ids):
            raise RetractionError(f"batch {batch_id} is already retracted")
        stamp = datetime.now().isoformat(timespec="seconds")
        for rid in ids:
            tomb[rid] = {"batch_id": batch_id, "officer": officer,
                         "reason": reason, "timestamp": stamp}
        _save(_tomb_path(), tomb)
    return {"batch_id": batch_id, "retracted_ids": ids, "reason": reason,
            "officer": officer, "timestamp": stamp}


def restore(batch_id: str, officer: str) -> Dict[str, Any]:
    """Lift the tombstones of a retracted batch (the rows never left the file)."""
    with _LOCK:
        batch = _find(batch_id, _load(_ingest_path(), []))
        tomb = _load(_tomb_path(), {})
        ids = [i for i in batch.get("record_ids", []) if i in tomb]
        if not ids:
            raise RetractionError(f"batch {batch_id} is not retracted")
        for rid in ids:
            tomb.pop(rid, None)
        _save(_tomb_path(), tomb)
    return {"batch_id": batch_id, "restored_ids": ids, "officer": officer}

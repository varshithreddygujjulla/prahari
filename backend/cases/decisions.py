"""
decisions.py — the investigator decision store.

Each decision is keyed by (kind, target) so the latest verdict on a given lead
or identity match wins, and every decision is appended to a JSON file so it
survives a reload. The caller (the API layer) also writes an audit block, so
the tamper-evident chain and this store agree.

Decisions are human judgements. Nothing here is produced by an algorithm; the
system only records what an investigator decided and when.
"""
import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional

_LOCK = threading.Lock()


class DecisionStoreError(RuntimeError):
    """The store on disk is unreadable; refuse to overwrite it silently."""

BASE = os.path.join(os.path.dirname(__file__), "..", "..", "data")
PATH = os.path.join(BASE, "decisions.json")

# What an investigator may decide, per target kind.
ACTIONS = {
    "lead": ["VERIFIED", "DISMISSED", "NEEDS_REVIEW"],
    "identity": ["CONFIRMED", "REJECTED", "NEEDS_REVIEW"],
    "anomaly": ["VERIFIED", "DISMISSED", "NEEDS_REVIEW"],
}

# Map a decision to the audit-chain action vocabulary (§16).
DECISION_TO_AUDIT = {
    "VERIFIED": "LEAD_VERIFIED",
    "DISMISSED": "LEAD_DISMISSED",
    "CONFIRMED": "LEAD_VERIFIED",
    "REJECTED": "LEAD_DISMISSED",
    "NEEDS_REVIEW": "DATA_ACCESSED",
}


def _load() -> Dict[str, Any]:
    if os.path.exists(PATH):
        try:
            with open(PATH, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # A corrupt store must NOT be silently replaced by an empty one on
            # the next verdict — that would erase every earlier decision.
            raise DecisionStoreError(
                f"decision store {PATH} is unreadable ({e}); fix or move it "
                f"before recording new verdicts")
        except OSError:
            return {}
    return {}


def _save(store: Dict[str, Any]):
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=1)
    os.replace(tmp, PATH)


def _key(kind: str, target: str) -> str:
    return f"{kind}:{target}"


def record_decision(kind: str, target: str, action: str, officer: str,
                    note: Optional[str] = None) -> Dict[str, Any]:
    kind = (kind or "").lower().strip()
    action = (action or "").upper().strip()
    if kind not in ACTIONS:
        raise ValueError(f"unknown decision kind '{kind}' "
                         f"(expected {list(ACTIONS)})")
    if action not in ACTIONS[kind]:
        raise ValueError(f"action '{action}' not valid for {kind} "
                         f"(expected {ACTIONS[kind]})")
    entry = {
        "kind": kind,
        "target": target,
        "action": action,
        "officer": officer,
        "note": (note or "").strip() or None,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    # read-modify-write under one lock: two concurrent verdicts must not
    # overwrite each other's entry
    with _LOCK:
        store = _load()
        store[_key(kind, target)] = entry
        _save(store)
    return entry


def get_decisions() -> Dict[str, Any]:
    return _load()

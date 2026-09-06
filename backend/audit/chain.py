"""
chain.py — SHA-256 hash chain over investigator actions.

Unchanged from the original in its cryptography and on-disk format, so existing
audit_chain.json files keep verifying. What is new is structure: blocks may now
carry role, case_id and target alongside the free-text action, and filtering is
supported. Old blocks without those fields still verify, because the hash is
computed over whatever fields the block actually has.

In production this would be a permissioned ledger (Hyperledger Fabric or
equivalent) with the write path behind an HSM-held key; the verification
property being demonstrated here is the same one.
"""
import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

BASE = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# The action vocabulary from §16.
ACTIONS = [
    "LOGIN", "CASE_CREATED", "DATA_ACCESSED", "ENTITY_SEARCHED", "GRAPH_QUERY",
    "LEAD_GENERATED", "LEAD_DISMISSED", "LEAD_VERIFIED", "EXPORT",
    "ADMIN_ACTION", "QUERY", "ACTION",
]


class AuditChain:
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.path.join(BASE, "audit_chain.json")
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.chain = json.load(f)
        else:
            self.chain = [{
                "index": 0, "timestamp": "2026-01-01T00:00:00",
                "officer": "SYSTEM", "action": "GENESIS",
                "prev_hash": "0" * 64,
                "hash": hashlib.sha256(b"GENESIS").hexdigest(),
            }]

    # ------------------------------------------------------------ writing
    # FastAPI serves requests from a threadpool; two audit writes interleaving
    # could both read the same `prev` and fork the chain. One lock covers the
    # read-append-flush sequence.
    _lock = threading.Lock()

    def record(self, officer: str, action: str,
               action_type: Optional[str] = None,
               role: Optional[str] = None,
               case_id: Optional[str] = None,
               target: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            return self._record(officer, action, action_type, role, case_id, target)

    def _record(self, officer, action, action_type, role, case_id, target) -> Dict[str, Any]:
        prev = self.chain[-1]
        block: Dict[str, Any] = {
            "index": prev["index"] + 1,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "officer": officer,
            "action": action,
            "prev_hash": prev["hash"],
        }
        # Only add the newer fields when supplied, so blocks written by the
        # original build keep the exact shape they had.
        if action_type:
            block["action_type"] = action_type
        if role:
            block["role"] = role
        if case_id:
            block["case_id"] = case_id
        if target:
            block["target"] = target

        payload = json.dumps(block, sort_keys=True).encode()
        block["hash"] = hashlib.sha256(payload).hexdigest()
        self.chain.append(block)
        self._flush()
        return block

    def _flush(self):
        if not self.path:                       # in-memory copy (tamper demo)
            return
        # unique temp file per writer, then atomic replace
        fd, tmp = tempfile.mkstemp(prefix=".audit-", suffix=".tmp",
                                   dir=os.path.dirname(self.path) or ".")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.chain, f, indent=1)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------ reading
    def verify(self):
        for i in range(1, len(self.chain)):
            b = dict(self.chain[i])
            h = b.pop("hash")
            recomputed = hashlib.sha256(
                json.dumps(b, sort_keys=True).encode()).hexdigest()
            if recomputed != h or b["prev_hash"] != self.chain[i - 1]["hash"]:
                return False, i
        return True, None

    def filter(self, officer: Optional[str] = None,
               action_type: Optional[str] = None,
               case_id: Optional[str] = None,
               since: Optional[str] = None,
               until: Optional[str] = None,
               limit: int = 100) -> List[Dict[str, Any]]:
        out = []
        for b in self.chain:
            if officer and b.get("officer") != officer:
                continue
            if action_type and b.get("action_type") != action_type:
                continue
            if case_id and b.get("case_id") != case_id:
                continue
            if since and b.get("timestamp", "") < since:
                continue
            if until and b.get("timestamp", "") > until:
                continue
            out.append(b)
        return out[-limit:]

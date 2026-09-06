"""
loaders.py — read data/ into Record objects with stable IDs and parsed times.

Design notes
------------
* Record IDs are minted as "<PREFIX>-<row number>" in file order. They are
  stable across runs for unchanged files, which is what provenance needs.
* Every record exposes `timestamp` as an ISO-8601 string or None. Registry
  records (subscriber, account, vehicle) are genuinely timeless — a vehicle
  registration has no event time — and are marked `timeless=True` so the
  temporal layer can include them in every window instead of dropping them.
* FIR dates were previously parsed and thrown away. They are the only signal
  in the corpus from before March, so the timeline needs them.
"""
import csv
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

BASE = os.path.join(os.path.dirname(__file__), "..", "..", "data")
FIRS = os.path.join(BASE, "firs")

# source key -> (filename, record-id prefix, source_type)
SOURCES = {
    "fir":               ("firs/",              "FIR",     "FIR"),
    "cdr":               ("cdr.csv",            "CDR",     "COMMUNICATION_METADATA"),
    "bank":              ("bank.csv",           "TXN",     "FINANCIAL"),
    "phone_directory":   ("phone_directory.csv", "PHD",    "SUBSCRIBER_REGISTRY"),
    "accounts":          ("accounts.csv",       "ACR",     "ACCOUNT_REGISTRY"),
    "vehicles":          ("vehicles.csv",       "VEH",     "VEHICLE_REGISTRY"),
    "travel":            ("travel.csv",         "TRV",     "TRAVEL"),
    "prison":            ("prison.csv",         "PRS",     "CUSTODY"),
    "identity_variants": ("identity_variants.csv", "IDV",  "IDENTITY_ASSERTION"),
}


@dataclass
class Record:
    """One row of one source, with everything provenance needs to cite it."""
    record_id: str
    source: str                      # logical source key, e.g. "cdr"
    source_file: str                 # file it came from
    source_type: str                 # taxonomy key from config.SOURCE_TYPES
    fields: Dict[str, Any]           # the parsed row
    timestamp: Optional[str] = None  # ISO-8601, or None
    end_timestamp: Optional[str] = None   # for records covering a span (custody)
    timeless: bool = False           # True for registries with no event time
    summary: str = ""                # one-line human description for the UI
    issues: List[str] = field(default_factory=list)  # parse problems, if any

    def cite(self) -> Dict[str, Any]:
        """The provenance citation form used in API payloads."""
        return {
            "record_id": self.record_id,
            "source": self.source,
            "source_file": self.source_file,
            "source_type": self.source_type,
            "timestamp": self.timestamp,
            "detail": self.summary,
        }


# ---------------------------------------------------------------- time parsing
def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec="seconds") if dt else None


def parse_dt(value: str, formats=("%Y-%m-%d %H:%M", "%Y-%m-%d",
                                  "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S")):
    """Parse the several date shapes present across the corpus."""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- shared patterns
# ONE definition, imported by both the loader and the intake preview, so the
# ADD DATA preview shows exactly what the graph builder will extract.
#
# Trigger words are case-insensitive (the `(?i:...)` group) so a sentence-
# initial "Accused Sunil Kumar ..." is captured, not just the lowercase
# "named associate Deepak Singh" later in the same line. The captured name
# itself stays case-sensitive: "Capitalised Two Words" only, so ordinary prose
# ("named associate") is never mistaken for a person.
FIR_NAME_RE = re.compile(r"(?i:accused|associate|named|by|consignee\.?|co-accused|links accused to)\s+"
                         r"([A-Z][a-z]+ [A-Z][a-z]+)")
# An Indian mobile number: ten digits, first digit 6-9. Used both to extract
# numbers from FIR prose and to validate the subscriber registry on load.
MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
FIR_PHONE_RE = re.compile(r"\b([6-9]\d{9})\b")
# Backward-compatible aliases (older callers import these names).
NAME_RE = FIR_NAME_RE
PHONE_RE = FIR_PHONE_RE

# ---------------------------------------------------------------- FIR parsing
FIR_DATE_RE = re.compile(r"^Date:\s*(.+)$", re.MULTILINE)
FIR_PS_RE = re.compile(r"^Police Station:\s*(.+)$", re.MULTILINE)
FIR_SEC_RE = re.compile(r"^Sections:\s*(.+)$", re.MULTILINE)
FIR_NARR_RE = re.compile(r"NARRATIVE:\s*(.+)", re.DOTALL)


def load_firs() -> List[Record]:
    out = []
    if not os.path.isdir(FIRS):
        return out
    for fn in sorted(os.listdir(FIRS)):
        if not fn.endswith(".txt"):
            continue
        path = os.path.join(FIRS, fn)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        fir_id = fn.replace(".txt", "")
        names = list(dict.fromkeys(FIR_NAME_RE.findall(text)))   # ordered unique
        phones = list(dict.fromkeys(FIR_PHONE_RE.findall(text)))
        dm = FIR_DATE_RE.search(text)
        dt = parse_dt(dm.group(1)) if dm else None
        psm = FIR_PS_RE.search(text)
        secm = FIR_SEC_RE.search(text)
        narrm = FIR_NARR_RE.search(text)
        issues = []
        if not dt:
            issues.append("FIR date missing or unparseable")
        if not names:
            issues.append("no person names extracted from narrative")
        rec = Record(
            record_id=fir_id,
            source="fir",
            source_file=f"data/firs/{fn}",
            source_type="FIR",
            fields={
                "names": names,
                "phones": phones,
                "police_station": psm.group(1).strip() if psm else "",
                "sections": secm.group(1).strip() if secm else "",
                "narrative": (narrm.group(1).strip() if narrm else "").replace("\n", " "),
            },
            timestamp=_iso(dt),
            summary=f"{fir_id} · {psm.group(1).strip() if psm else 'unknown PS'} · "
                    f"{secm.group(1).strip() if secm else 'no sections'}",
            issues=issues,
        )
        out.append(rec)
    return out


# ---------------------------------------------------------------- CSV loading
def _read_csv(filename: str) -> List[Dict[str, str]]:
    path = os.path.join(BASE, filename)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        # a short row gives DictReader None for the trailing columns; every
        # caller does `.strip()` on cells, so normalise to "" here
        return [{k: ("" if v is None else v) for k, v in row.items() if k is not None}
                for row in csv.DictReader(f)]


def _mk(source: str, idx: int, row: Dict[str, str], **kw) -> Record:
    filename, prefix, stype = SOURCES[source]
    return Record(
        record_id=f"{prefix}-{idx:04d}",
        source=source,
        source_file=f"data/{filename}",
        source_type=stype,
        fields=row,
        **kw,
    )


def load_cdr() -> List[Record]:
    out = []
    for i, row in enumerate(_read_csv("cdr.csv"), start=1):
        dt = parse_dt(row.get("timestamp", ""))
        issues = [] if dt else ["unparseable timestamp"]
        dur = row.get("duration_sec", "")
        out.append(_mk("cdr", i, row, timestamp=_iso(dt),
                       summary=f'{row.get("caller","?")} → {row.get("receiver","?")} · '
                               f'{dur}s · tower {row.get("tower_id","?")}',
                       issues=issues))
    return out


def load_bank() -> List[Record]:
    out = []
    for i, row in enumerate(_read_csv("bank.csv"), start=1):
        dt = parse_dt(row.get("date", ""))
        issues = [] if dt else ["unparseable date"]
        try:
            amt = float(row.get("amount_inr", 0) or 0)
        except ValueError:
            amt = 0.0
            issues.append("non-numeric amount")
        row = dict(row, _amount=amt)
        out.append(_mk("bank", i, row, timestamp=_iso(dt),
                       summary=f'{row.get("from_account","?")} → {row.get("to_account","?")} · '
                               f'₹{amt:,.0f}',
                       issues=issues))
    return out


def load_phone_directory() -> List[Record]:
    """Subscriber registry. A row whose `phone` is not a valid mobile number
    (an account id pasted into the wrong file, a landline, a typo) is kept for
    the record listing but flagged, and the graph builder / entity resolver
    skip flagged rows — so a bad row can never assign a handset to anyone."""
    out = []
    for i, row in enumerate(_read_csv("phone_directory.csv"), start=1):
        ph = (row.get("phone") or "").strip()
        issues = []
        if ph and not MOBILE_RE.match(ph):
            issues.append(f"phone '{ph}' is not a 10-digit Indian mobile number")
        out.append(_mk("phone_directory", i, row, timeless=True,
                       summary=f'{ph or "?"} registered to {row.get("registered_name","?")}',
                       issues=issues))
    return out


def load_accounts() -> List[Record]:
    return [_mk("accounts", i, row, timeless=True,
                summary=f'{row.get("account","?")} held by {row.get("holder_name","?")}')
            for i, row in enumerate(_read_csv("accounts.csv"), start=1)]


def load_vehicles() -> List[Record]:
    return [_mk("vehicles", i, row, timeless=True,
                summary=f'{row.get("vehicle_number","?")} ({row.get("vehicle_type","?")}) '
                        f'registered to {row.get("owner_name","?")}')
            for i, row in enumerate(_read_csv("vehicles.csv"), start=1)]


def load_travel() -> List[Record]:
    out = []
    for i, row in enumerate(_read_csv("travel.csv"), start=1):
        dt = parse_dt(row.get("date", ""))
        out.append(_mk("travel", i, row, timestamp=_iso(dt),
                       summary=f'{row.get("passenger_name","?")}: {row.get("from_city","?")} '
                               f'→ {row.get("to_city","?")} · {row.get("flight","?")}',
                       issues=[] if dt else ["unparseable date"]))
    return out


def load_prison() -> List[Record]:
    out = []
    for i, row in enumerate(_read_csv("prison.csv"), start=1):
        a = parse_dt(row.get("from_date", ""))
        b = parse_dt(row.get("to_date", ""))
        issues = []
        if not a or not b:
            issues.append("unparseable custody dates")
        elif b < a:
            issues.append("custody end precedes start")
        out.append(_mk("prison", i, row, timestamp=_iso(a), end_timestamp=_iso(b),
                       summary=f'{row.get("prisoner_name","?")} · {row.get("jail","?")} '
                               f'{row.get("cell_block","?")} · {row.get("from_date","?")} '
                               f'to {row.get("to_date","?")}',
                       issues=issues))
    return out


def load_identity_variants() -> List[Record]:
    """Alternate name spellings observed in legacy records.

    Consumed ONLY by the entity-resolution layer — deliberately never fed to the
    graph builder, so adding it leaves the board's node/edge counts untouched.

    The file carries its own `record_id` column (IDV-A1, IDV-B2, ...) because
    the demo script and docs refer to variants by those ids; a row without one
    falls back to the positional id every other source uses.
    """
    out = []
    for i, row in enumerate(_read_csv("identity_variants.csv"), start=1):
        rec = _mk("identity_variants", i, row, timeless=True,
                  summary=f'"{row.get("observed_name","?")}" recorded in '
                          f'{row.get("source_hint","?")}')
        own = (row.get("record_id") or "").strip()
        if own:
            rec.record_id = own
        out.append(rec)
    return out


# ---------------------------------------------------------------- entry point
def load_all() -> Dict[str, List[Record]]:
    """Load every source. Returns {source_key: [Record, ...]}.

    Records retracted through the ADD DATA undo are dropped HERE, after every
    row has been numbered, so ids never shift when something is withdrawn.
    The rows stay in the files for the audit trail."""
    from backend.ingestion.retraction import retracted_ids   # avoids an import cycle
    out = {
        "fir":               load_firs(),
        "cdr":               load_cdr(),
        "bank":              load_bank(),
        "phone_directory":   load_phone_directory(),
        "accounts":          load_accounts(),
        "vehicles":          load_vehicles(),
        "travel":            load_travel(),
        "prison":            load_prison(),
        "identity_variants": load_identity_variants(),
    }
    tomb = retracted_ids()
    if tomb:
        out = {k: [r for r in v if r.record_id not in tomb] for k, v in out.items()}
    return out

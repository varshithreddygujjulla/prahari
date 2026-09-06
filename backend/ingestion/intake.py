"""
intake.py — the ADD DATA pipeline: validate → quality-score → detect conflicts
→ (commit) append to the data store → rebuild → audit.

Principles from the ingestion specification, enforced here rather than merely
documented:

  * A missing OPTIONAL field never rejects a record — it becomes null and the
    record is marked PARTIAL and retained.
  * Nothing is ever fabricated — absent values stay absent.
  * The raw submitted value is preserved verbatim alongside the parsed one.
  * Every record carries a source and a proposed unique id.
  * A malformed value (bad date, non-numeric amount, out-of-range coordinate)
    is never silently corrected — the row is marked INVALID, kept for review,
    and NOT written to the store, because writing it would corrupt the loader.
  * Conflicts against existing data (a phone/account/vehicle already tied to a
    different holder) are surfaced, never silently overwritten.

Only the eight source types that already have a home in the graph are wired to
the store. CCTV/ANPR, GPS and SOCIAL validate and persist to their own files
but are flagged `staged` — they do not appear on the board until the Phase 2
map and OSINT views exist. That is deliberate: rendering them now would mean
inventing a view for data the board cannot yet honestly show.
"""
import csv
import io
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.ingestion.loaders import BASE, FIRS, FIR_NAME_RE, FIR_PHONE_RE

# ---------------------------------------------------------------- validators
# Each returns (normalized_value, ok, issue). ok=False means the value is
# present but malformed; the row becomes INVALID and is not written.

def v_phone(x: str):
    s = (x or "").strip()
    if not s:
        return None, True, None
    digits = re.sub(r"\D", "", s)
    if len(digits) == 10 and digits[0] in "6789":
        return digits, True, None
    return s, False, f"phone '{s}' is not a 10-digit Indian mobile number"


def v_account(x: str):
    s = (x or "").strip()
    if not s:
        return None, True, None
    if re.fullmatch(r"[A-Za-z0-9\-]{3,20}", s):
        return s, True, None
    return s, False, f"account id '{s}' has an unexpected format"


def v_amount(x):
    if x is None or str(x).strip() == "":
        return None, True, None
    try:
        val = float(str(x).replace(",", "").replace("₹", "").strip())
    except ValueError:
        return x, False, f"amount '{x}' is not numeric"
    if val < 0:
        return x, False, "amount is negative"
    return int(val) if val == int(val) else val, True, None


def _parse_date(s: str):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_dt(s: str):
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def v_date(x: str):
    """Normalise a valid date to YYYY-MM-DD; refuse to guess a bad one."""
    s = (x or "").strip()
    if not s:
        return None, True, None
    d = _parse_date(s)
    if d:
        return d.strftime("%Y-%m-%d"), True, None
    return s, False, f"date '{s}' is not a recognised date"


def v_datetime(x: str):
    """Normalise to 'YYYY-MM-DD HH:MM' (the CDR store format)."""
    s = (x or "").strip()
    if not s:
        return None, True, None
    d = _parse_dt(s)
    if d:
        return d.strftime("%Y-%m-%d %H:%M"), True, None
    if _parse_date(s):
        # a bare date would be stored as 00:00 — that is an invented time,
        # and it would put the event in the wrong window on the timeline
        return s, False, (f"timestamp '{s}' has no time component; this source "
                          f"needs 'YYYY-MM-DD HH:MM'")
    return s, False, f"timestamp '{s}' is not a recognised date/time"


def v_int(x):
    if x is None or str(x).strip() == "":
        return None, True, None
    try:
        return int(float(str(x).strip())), True, None
    except ValueError:
        return x, False, f"'{x}' is not a whole number"


def v_vehicle(x: str):
    s = (x or "").strip().upper().replace(" ", "")
    if not s:
        return None, True, None
    # Deliberately loose — enough to catch junk, not to reject regional formats.
    if re.fullmatch(r"[A-Z0-9?]{4,12}", s):
        return s, True, None
    return s, False, f"registration '{s}' has an unexpected format"


def v_text(x):
    s = (x or "")
    s = s.strip() if isinstance(s, str) else s
    return (s or None), True, None


def v_lat(x):
    if x is None or str(x).strip() == "":
        return None, True, None
    try:
        val = float(x)
    except (ValueError, TypeError):
        return x, False, f"latitude '{x}' is not numeric"
    return (val, True, None) if -90 <= val <= 90 else (x, False, "latitude out of range")


def v_lon(x):
    if x is None or str(x).strip() == "":
        return None, True, None
    try:
        val = float(x)
    except (ValueError, TypeError):
        return x, False, f"longitude '{x}' is not numeric"
    return (val, True, None) if -180 <= val <= 180 else (x, False, "longitude out of range")


# ---------------------------------------------------------------- field spec
# (canonical_name, aliases, required, identifier, validator)
class F:
    def __init__(self, name, aliases, required, identifier, validator):
        self.name = name
        self.aliases = [name] + aliases
        self.required = required
        self.identifier = identifier
        self.validate = validator


SOURCES: Dict[str, Dict[str, Any]] = {
    "cdr": {
        "label": "Call Detail Records (CDR)", "store": "cdr.csv", "prefix": "CDR",
        "staged": False,
        "columns": ["caller", "receiver", "timestamp", "duration_sec", "tower_id"],
        "fields": [
            F("caller", ["caller_number", "from", "a_party"], True, True, v_phone),
            F("receiver", ["receiver_number", "to", "b_party"], False, False, v_phone),
            F("timestamp", ["time", "datetime", "date"], True, False, v_datetime),
            F("duration_sec", ["duration"], False, False, v_int),
            F("tower_id", ["tower", "cell_id"], False, False, v_text),
        ],
    },
    "bank": {
        "label": "Bank transfers (FIU-IND)", "store": "bank.csv", "prefix": "TXN",
        "staged": False,
        "columns": ["from_account", "to_account", "amount_inr", "date"],
        "fields": [
            F("from_account", ["from", "debit_account", "source_account"], True, True, v_account),
            F("to_account", ["to", "credit_account", "beneficiary_account"], True, True, v_account),
            F("amount_inr", ["amount"], False, False, v_amount),
            F("date", ["timestamp", "txn_date"], True, False, v_date),
        ],
    },
    "accounts": {
        "label": "Account directory", "store": "accounts.csv", "prefix": "ACR",
        "staged": False,
        "columns": ["account", "holder_name"],
        "fields": [
            F("account", ["account_id", "acc", "account_number"], True, True, v_account),
            F("holder_name", ["holder", "name"], False, False, v_text),
        ],
    },
    "phone_directory": {
        "label": "Phone / subscriber directory", "store": "phone_directory.csv", "prefix": "PHD",
        "staged": False,
        "columns": ["phone", "registered_name"],
        "fields": [
            F("phone", ["number", "msisdn", "mobile"], True, True, v_phone),
            F("registered_name", ["name", "holder", "subscriber"], False, False, v_text),
        ],
    },
    "vehicles": {
        "label": "Vehicle registry (VAHAN)", "store": "vehicles.csv", "prefix": "VEH",
        "staged": False,
        "columns": ["vehicle_number", "owner_name", "vehicle_type"],
        "fields": [
            F("vehicle_number", ["registration_number", "reg", "plate", "vehicle_no"], True, True, v_vehicle),
            F("owner_name", ["registered_owner", "owner"], False, False, v_text),
            F("vehicle_type", ["type", "make_model"], False, False, v_text),
        ],
    },
    "travel": {
        "label": "Travel manifests", "store": "travel.csv", "prefix": "TRV",
        "staged": False,
        "columns": ["passenger_name", "from_city", "to_city", "date", "flight"],
        "fields": [
            F("passenger_name", ["name", "person", "passenger"], True, True, v_text),
            F("from_city", ["origin", "from"], True, False, v_text),
            F("to_city", ["destination", "to"], True, False, v_text),
            F("date", ["departure", "timestamp"], True, False, v_date),
            F("flight", ["flight_no", "mode", "carrier"], False, False, v_text),
        ],
    },
    "prison": {
        "label": "Custody roster (e-Prisons)", "store": "prison.csv", "prefix": "PRS",
        "staged": False,
        "columns": ["prisoner_name", "jail", "cell_block", "from_date", "to_date"],
        "fields": [
            F("prisoner_name", ["person", "name", "inmate"], True, True, v_text),
            F("jail", ["prison", "facility"], True, False, v_text),
            F("cell_block", ["block", "cell"], False, False, v_text),
            F("from_date", ["from", "admission", "admitted"], True, False, v_date),
            F("to_date", ["to", "release", "released"], True, False, v_date),
        ],
    },
    # ---- staged: validated & stored, not yet rendered on the board ----------
    "cctv": {
        "label": "CCTV / ANPR (staged — Phase 2 map)", "store": "cctv.csv", "prefix": "CCTV",
        "staged": True,
        "columns": ["timestamp", "camera_id", "location", "vehicle_number",
                    "vehicle_match_confidence"],
        "fields": [
            F("timestamp", ["time", "datetime"], True, False, v_datetime),
            F("camera_id", ["camera", "cam"], True, True, v_text),
            F("location", ["place", "site"], False, False, v_text),
            F("vehicle_number", ["registration_number", "plate"], False, False, v_vehicle),
            F("vehicle_match_confidence", ["confidence", "match_confidence"], False, False, v_int),
        ],
    },
    "gps": {
        "label": "GPS location (staged — Phase 2 map)", "store": "gps.csv", "prefix": "LOC",
        "staged": True,
        "columns": ["vehicle_id", "timestamp", "latitude", "longitude", "speed_kmh"],
        "fields": [
            F("vehicle_id", ["vehicle", "vehicle_number", "reg"], True, True, v_text),
            F("timestamp", ["time", "datetime"], True, False, v_datetime),
            F("latitude", ["lat"], False, False, v_lat),
            F("longitude", ["lon", "lng", "long"], False, False, v_lon),
            F("speed_kmh", ["speed"], False, False, v_int),
        ],
    },
    "social": {
        "label": "Social OSINT (staged — Phase 2 OSINT)", "store": "social.csv", "prefix": "POST",
        "staged": True,
        "columns": ["account_id", "account_name", "timestamp", "text",
                    "mentioned_locations", "hashtags"],
        "fields": [
            F("account_id", ["account", "handle"], True, True, v_text),
            F("account_name", ["name", "display_name"], False, False, v_text),
            F("timestamp", ["time", "datetime", "date"], True, False, v_datetime),
            F("text", ["post", "content", "body"], False, False, v_text),
            F("mentioned_locations", ["locations", "places"], False, False, v_text),
            F("hashtags", ["tags"], False, False, v_text),
        ],
    },
}

# Aliases the UI / spec use for a source type.
SOURCE_ALIASES = {
    "fir": "fir", "cdr": "cdr", "call": "cdr", "calls": "cdr",
    "bank": "bank", "transaction": "bank", "financial": "bank",
    "account": "accounts", "accounts": "accounts",
    "phone": "phone_directory", "phone_directory": "phone_directory", "subscriber": "phone_directory",
    "vehicle": "vehicles", "vehicles": "vehicles",
    "travel": "travel", "prison": "prison", "custody": "prison",
    "cctv": "cctv", "anpr": "cctv", "gps": "gps", "location": "gps",
    "social": "social", "osint": "social",
}


def resolve_source(source_type: str) -> Optional[str]:
    return SOURCE_ALIASES.get((source_type or "").strip().lower())


# ---------------------------------------------------------------- field mapping
def _pick(row: Dict[str, Any], field: F, mapping: Dict[str, str]):
    """Find this field's value in a submitted row.

    Honours an explicit column mapping first (CSV import, §19), then the field's
    own aliases, case-insensitively.
    """
    if field.name in mapping:
        src = mapping[field.name]
        return row.get(src), src
    lower = {str(k).lower(): k for k in row}
    for alias in field.aliases:
        if alias.lower() in lower:
            key = lower[alias.lower()]
            return row.get(key), key
    return None, None


# ---------------------------------------------------------------- quality
def _quality(present: int, total: int, missing_required: bool,
             missing_identifier: bool, invalid: bool) -> Dict[str, Any]:
    completeness = round(present / total * 100) if total else 0
    if invalid:
        status, level = "INVALID", "LOW"
    elif missing_identifier:
        status, level = "PARTIAL", "LOW"
    elif missing_required:
        status, level = "PARTIAL", "MEDIUM"
    elif completeness == 100:
        status, level = "VALID", "HIGH"
    else:
        status, level = "PARTIAL", "MEDIUM"
    return {"completeness": completeness, "validation_status": status, "level": level}


# ---------------------------------------------------------------- existing data
def _read_store(filename: str) -> List[Dict[str, str]]:
    path = os.path.join(BASE, filename)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _conflicts(skey: str, parsed: Dict[str, Any],
               existing: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Directory-style conflicts: an identifier already tied to another holder."""
    out = []
    checks = {
        "phone_directory": ("phone", "registered_name"),
        "accounts": ("account", "holder_name"),
        "vehicles": ("vehicle_number", "owner_name"),
    }
    if skey not in checks:
        return out
    id_field, name_field = checks[skey]
    new_id = parsed.get(id_field)
    new_name = parsed.get(name_field)
    if not new_id or not new_name:
        return out
    for row in existing:
        if row.get(id_field) == new_id and row.get(name_field) and \
           row.get(name_field) != new_name:
            out.append({
                "type": "CONFLICTING",
                "field": name_field,
                "existing": row.get(name_field),
                "incoming": new_name,
                "detail": f"{id_field} {new_id} is already recorded against "
                          f"'{row.get(name_field)}' — incoming record says "
                          f"'{new_name}'. Not overwritten; needs investigator review.",
            })
    return out


def _row_key(skey: str, values: Dict[str, Any]) -> Tuple:
    """The stored shape of a row, for duplicate comparison."""
    return tuple((str(values.get(c)).strip() if values.get(c) not in (None, "")
                  else None) for c in SOURCES[skey]["columns"])


def _is_duplicate(skey: str, parsed: Dict[str, Any],
                  existing: List[Dict[str, str]]) -> bool:
    key = _row_key(skey, parsed)
    return any(_row_key(skey, row) == key for row in existing)


# ---------------------------------------------------------------- one record
def _process_row(skey: str, row: Dict[str, Any], mapping: Dict[str, str],
                 idx: int, existing: Optional[List[Dict[str, str]]] = None
                 ) -> Dict[str, Any]:
    spec = SOURCES[skey]
    fields = spec["fields"]
    if existing is None:
        existing = _read_store(spec["store"])
    parsed: Dict[str, Any] = {}
    raw: Dict[str, Any] = {}
    issues: List[str] = []
    present = 0
    missing_required = False
    missing_identifier = False
    invalid = False

    for f in fields:
        val, src_key = _pick(row, f, mapping)
        raw[f.name] = val
        norm, ok, issue = f.validate(val if val is not None else "")
        if val not in (None, ""):
            if ok:
                parsed[f.name] = norm
                present += 1
            else:
                parsed[f.name] = None
                invalid = True
                issues.append(issue)
        else:
            parsed[f.name] = None
            if f.required:
                missing_required = True
                issues.append(f"required field '{f.name}' is missing (kept as null)")
            if f.identifier:
                missing_identifier = True
                issues.append(f"identifier '{f.name}' is missing — the record "
                              f"cannot be attached to any entity on the board")

    quality = _quality(present, len(fields), missing_required,
                       missing_identifier, invalid)
    conflicts = _conflicts(skey, parsed, existing) if not invalid else []
    duplicate = _is_duplicate(skey, parsed, existing) if not invalid else False
    if conflicts:
        quality["level"] = "LOW"
    if duplicate:
        issues.append("an identical record already exists in the store")

    return {
        # provisional: commit() renumbers by the position actually written
        "record_id": f"{spec['prefix']}-{len(existing) + idx + 1:04d}",
        "source_type": skey.upper(),
        "staged": spec["staged"],
        "parsed": parsed,
        "raw": raw,
        "quality": quality,
        "issues": issues,
        "conflicts": conflicts,
        "duplicate": duplicate,
        # committable = safe to write: not malformed AND has the identifier
        # that links it to the graph. PARTIAL on optional fields is fine; a
        # row with no identifier would be stored but never surface anywhere.
        "committable": not invalid and not missing_identifier,
    }


# ---------------------------------------------------------------- FIR (text)
# FIR_NAME_RE / FIR_PHONE_RE are imported from loaders.py: one definition, so
# the preview shows exactly what the graph builder will extract on rebuild.


def _next_fir_id() -> str:
    n = 0
    if os.path.isdir(FIRS):
        for fn in os.listdir(FIRS):
            m = re.match(r"FIR_(\d+)\.txt$", fn)
            if m:
                n = max(n, int(m.group(1)))
    return f"FIR_{n + 1:03d}"


def _process_fir_text(text: str) -> Dict[str, Any]:
    names = list(dict.fromkeys(FIR_NAME_RE.findall(text)))
    phones = list(dict.fromkeys(FIR_PHONE_RE.findall(text)))
    has_date = bool(re.search(r"^Date:\s*\S", text, re.MULTILINE))
    has_narr = "NARRATIVE:" in text.upper()
    issues = []
    if not names:
        issues.append("no person names matched the extractor "
                      "(needs 'Capitalised Two Words' after accused / associate / "
                      "named / by / consignee / co-accused)")
    if not has_date:
        issues.append("no 'Date: DD-MM-YYYY' line — record will not appear on the timeline")
    if not has_narr:
        issues.append("no 'NARRATIVE:' section found")
    status = "VALID" if names and has_date and has_narr else \
             ("PARTIAL" if names else "INVALID")
    level = "HIGH" if status == "VALID" else ("MEDIUM" if names else "LOW")
    return {
        "record_id": _next_fir_id(),
        "source_type": "FIR",
        "staged": False,
        "parsed": {"names_extracted": names, "phones_extracted": phones},
        "raw": {"text": text},
        "quality": {"completeness": 100 if status == "VALID" else 60 if names else 20,
                    "validation_status": status, "level": level},
        "issues": issues,
        "conflicts": [],
        "duplicate": False,
        "committable": bool(names),      # need at least one extractable person
    }


# ---------------------------------------------------------------- parse input
def _rows_from_payload(fmt: str, payload: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Return (rows, error). Malformed JSON/CSV yields a clear error, never a guess."""
    if fmt == "json":
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            return [], f"malformed JSON: {e}"
        if isinstance(data, dict):
            # allow {"records":[...]} or a single record object
            data = data.get("records", data) if "records" in data else data
            if isinstance(data, dict):
                data = [data]
        if not isinstance(data, list):
            return [], "JSON must be a record object or an array of records"
        return data, None
    if fmt == "csv":
        try:
            reader = csv.DictReader(io.StringIO(payload))
            rows = list(reader)
        except csv.Error as e:
            return [], f"malformed CSV: {e}"
        if not rows:
            return [], "CSV has no data rows"
        return rows, None
    return [], f"unsupported format '{fmt}'"


# ---------------------------------------------------------------- preview
def preview(source_type: str, fmt: str, payload: str,
            mapping: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    skey = resolve_source(source_type)
    if not skey:
        return {"error": f"unknown source type '{source_type}'",
                "known": sorted(set(SOURCE_ALIASES.values()))}

    if skey == "fir":
        if fmt not in ("text", "json"):
            return {"error": "FIR upload accepts raw text (format=text)"}
        text = payload
        if fmt == "json":
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                return {"error": f"malformed JSON: {e}"}
            text = data.get("narrative", data.get("text")) if isinstance(data, dict) else None
            if not isinstance(text, str):
                return {"error": "FIR JSON must be an object with a 'narrative' string"}
        rec = _process_fir_text(text)
        return {"source_type": "fir", "staged": False, "records": [rec],
                "summary": _summarise([rec])}

    rows, err = _rows_from_payload(fmt, payload)
    if err:
        return {"error": err}
    if not all(isinstance(r, dict) for r in rows):
        return {"error": "every record must be a JSON object"}
    existing = _read_store(SOURCES[skey]["store"])       # once, not per row
    records = [_process_row(skey, r, mapping or {}, i, existing)
               for i, r in enumerate(rows)]
    # duplicates within the batch itself: the second copy is flagged
    seen = set()
    for rec in records:
        if not rec["committable"]:
            continue
        key = _row_key(skey, rec["parsed"])
        if key in seen:
            rec["duplicate"] = True
            rec["issues"].append("identical to an earlier row in this batch")
        seen.add(key)
    return {
        "source_type": skey,
        "label": SOURCES[skey]["label"],
        "staged": SOURCES[skey]["staged"],
        "columns": SOURCES[skey]["columns"],
        "records": records,
        "summary": _summarise(records),
    }


def _summarise(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    def c(pred):
        return sum(1 for r in records if pred(r))
    return {
        "total": len(records),
        "valid": c(lambda r: r["quality"]["validation_status"] == "VALID"),
        "partial": c(lambda r: r["quality"]["validation_status"] == "PARTIAL"),
        "invalid": c(lambda r: r["quality"]["validation_status"] == "INVALID"),
        "conflicts": c(lambda r: bool(r["conflicts"])),
        "duplicates": c(lambda r: r["duplicate"]),
        "committable": c(lambda r: r["committable"]),
    }


# ---------------------------------------------------------------- commit
def _append_csv(skey: str, records: List[Dict[str, Any]]) -> int:
    spec = SOURCES[skey]
    path = os.path.join(BASE, spec["store"])
    cols = spec["columns"]
    exists = os.path.exists(path)
    written = 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(cols)
        for rec in records:
            p = rec["parsed"]
            w.writerow(["" if p.get(c) is None else p.get(c) for c in cols])
            written += 1
    return written


def _write_fir(rec: Dict[str, Any]) -> str:
    os.makedirs(FIRS, exist_ok=True)
    fid = rec["record_id"]
    path = os.path.join(FIRS, f"{fid}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(rec["raw"]["text"].strip() + "\n")
    return fid


def commit(source_type: str, fmt: str, payload: str,
           mapping: Optional[Dict[str, str]] = None,
           include_conflicts: bool = False) -> Dict[str, Any]:
    """Validate again, then append committable records to the store.

    Conflicting rows are skipped by default (never overwrite); pass
    include_conflicts=True to add them anyway for later investigator review.
    INVALID rows are never written. Returns what was written and what was held.
    """
    pv = preview(source_type, fmt, payload, mapping)
    if "error" in pv:
        return pv
    skey = pv["source_type"]
    records = pv["records"]

    to_write, held = [], []
    for r in records:
        if not r["committable"]:
            tag = ("INVALID" if r["quality"]["validation_status"] == "INVALID"
                   else "NO IDENTIFIER")
            held.append({"record_id": r["record_id"], "reason": f"{tag} — "
                         + "; ".join(r["issues"][:2])})
        elif r["duplicate"]:
            held.append({"record_id": r["record_id"],
                         "reason": "DUPLICATE — an identical record already "
                                   "exists; not written twice"})
        elif r["conflicts"] and not include_conflicts:
            held.append({"record_id": r["record_id"],
                         "reason": "CONFLICT held for review — "
                         + r["conflicts"][0]["detail"]})
        else:
            to_write.append(r)

    written_ids = []
    if skey == "fir":
        for r in to_write:
            r["record_id"] = _next_fir_id()          # numbered at write time
            written_ids.append(_write_fir(r))
    else:
        # ids are positional (the loader numbers rows 1..n), so number by the
        # rows that are actually appended, not by the preview index
        spec = SOURCES[skey]
        base = len(_read_store(spec["store"]))
        for i, r in enumerate(to_write):
            r["record_id"] = f"{spec['prefix']}-{base + i + 1:04d}"
            written_ids.append(r["record_id"])
        if to_write:
            _append_csv(skey, to_write)

    return {
        "source_type": skey,
        "staged": pv.get("staged", False),
        "written": len(written_ids),
        "written_ids": written_ids,
        "held": held,
        "summary": pv["summary"],
        "note": ("Stored, but this source type is not yet rendered on the board "
                 "(needs the Phase 2 map/OSINT views)." if pv.get("staged")
                 else "Rebuild the graph to see these records on the board."),
    }

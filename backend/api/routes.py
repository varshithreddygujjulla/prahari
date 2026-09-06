"""
routes.py — the HTTP surface.

Every read is written to the audit chain before it is served, so the log
reflects what was actually asked for. Inputs are constrained at the signature
(enumerated windows, bounded lengths, pattern-checked identifiers) rather than
being trusted and sanitised later.
"""
import copy
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query
from pydantic import BaseModel, Field

from backend import config
from backend.assistant import answer as ask_answer, EXAMPLES as ASK_EXAMPLES
from backend.audit import AuditChain, ACTIONS as AUDIT_ACTIONS
from backend.cases import record_decision, get_decisions, ACTIONS as DECISION_ACTIONS, DECISION_TO_AUDIT
from backend.cases.decisions import DecisionStoreError
from backend.ingestion import intake
from backend.ingestion import retraction
from backend.pipeline import analysis, build_payload, invalidate

router = APIRouter()
audit = AuditChain()

WINDOW_VALUES = list(config.TIME_WINDOWS) + ["custom"]
_ISO = r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?$"
_OFFICER = r"^[A-Za-z0-9 ._\-]{1,64}$"


def _entity_index() -> Dict[str, Any]:
    return analysis()


# ---------------------------------------------------------------- intake (ADD DATA)
class IntakeBody(BaseModel):
    """Payload for the ADD DATA pipeline. Bounded so a paste cannot be huge."""
    source_type: str = Field(..., max_length=32)
    format: str = Field("json", pattern=r"^(json|csv|text)$")
    payload: str = Field(..., max_length=500_000)
    mapping: Optional[Dict[str, str]] = None
    include_conflicts: bool = False
    officer: str = Field("Officer-101", max_length=64)


@router.get("/api/intake/schema")
def intake_schema():
    """The source types the ADD DATA form offers, with their fields."""
    out = {}
    for key, spec in intake.SOURCES.items():
        out[key] = {
            "label": spec["label"], "staged": spec["staged"],
            "columns": spec["columns"],
            "fields": [{"name": f.name, "required": f.required,
                        "identifier": f.identifier, "aliases": f.aliases}
                       for f in spec["fields"]],
        }
    out["fir"] = {"label": "First Information Report (raw text)", "staged": False,
                  "columns": [], "fields": [], "text_only": True}
    return {"sources": out}


@router.post("/api/intake/preview")
def intake_preview(body: IntakeBody):
    """Validate, quality-score and conflict-check — WITHOUT writing anything."""
    audit.record(body.officer, f"DATA_ACCESSED: intake preview ({body.source_type})",
                 action_type="DATA_ACCESSED")
    result = intake.preview(body.source_type, body.format, body.payload, body.mapping)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/api/intake/commit")
def intake_commit(body: IntakeBody):
    """Append committable records to the store, then rebuild the graph."""
    result = intake.commit(body.source_type, body.format, body.payload,
                           body.mapping, body.include_conflicts)
    if "error" in result:
        raise HTTPException(400, result["error"])
    # Every commit is a batch, so it can be retracted later as one unit.
    if result["written"]:
        batch = retraction.record_batch(result["source_type"], result["written_ids"],
                                        body.officer, staged=bool(result.get("staged")))
        result["batch_id"] = batch["batch_id"]
    audit.record(body.officer,
                 f"DATA_INGESTED: {result['written']} {result['source_type']} "
                 f"record(s) [{', '.join(result['written_ids'][:8])}]"
                 + (f" batch {result['batch_id']}" if result.get("batch_id") else ""),
                 action_type="ADMIN_ACTION", target=result.get("batch_id") or result["source_type"])
    # Only a graph-backed source changes the board; staged sources do not.
    if result["written"] and not result.get("staged"):
        invalidate()
        result["stats"] = build_payload(force=True)["stats"]
    return result


# ---------------------------------------------------------------- retraction (undo ADD DATA)
class RetractBody(BaseModel):
    batch_id: str = Field(..., max_length=64, pattern=r"^ING-[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")
    reason: Optional[str] = Field(None, max_length=500)
    officer: str = Field("Officer-101", max_length=64)


@router.get("/api/intake/batches")
def intake_batches():
    """Every ADD DATA commit, newest first, with its retraction state. The
    shipped corpus is not a batch and therefore cannot be retracted here."""
    return {"batches": retraction.list_batches(),
            "note": "Retracting hides a batch from the board and keeps its rows on "
                    "file for the audit trail; record ids never change."}


@router.post("/api/intake/retract")
def intake_retract(body: RetractBody):
    """Withdraw one batch (e.g. records pasted from the wrong case). Needs a
    reason; audited; reversible with /api/intake/restore."""
    try:
        res = retraction.retract(body.batch_id, body.officer, body.reason or "")
    except retraction.RetractionError as e:
        raise HTTPException(400, str(e))
    audit.record(body.officer,
                 f"DATA_RETRACTED: batch {body.batch_id} ({len(res['retracted_ids'])} "
                 f"record(s)) — {res['reason']}",
                 action_type="ADMIN_ACTION", target=body.batch_id)
    invalidate()
    res["stats"] = build_payload(force=True)["stats"]
    return res


@router.post("/api/intake/restore")
def intake_restore(body: RetractBody):
    """Reinstate a retracted batch — the rows never left the file."""
    try:
        res = retraction.restore(body.batch_id, body.officer)
    except retraction.RetractionError as e:
        raise HTTPException(400, str(e))
    audit.record(body.officer,
                 f"DATA_RESTORED: batch {body.batch_id} ({len(res['restored_ids'])} record(s))",
                 action_type="ADMIN_ACTION", target=body.batch_id)
    invalidate()
    res["stats"] = build_payload(force=True)["stats"]
    return res


# ---------------------------------------------------------------- ask (assistant)
@router.get("/api/ask")
def ask(q: str = Query(..., max_length=300),
        context: Optional[str] = Query(None, max_length=120),
        officer: str = Query("Officer-101", pattern=_OFFICER)):
    """Grounded natural-language query — answered only from the case records,
    with no external model. `context` carries the last entity discussed so
    follow-ups ('what about his money') resolve. Every answer cites its sources."""
    a = _entity_index()
    audit.record(officer, f"ENTITY_SEARCHED: ask '{q[:80]}'",
                 action_type="ENTITY_SEARCHED", target=q[:80])
    result = ask_answer(q, a, context=context)
    result["examples"] = ASK_EXAMPLES
    return result


# ---------------------------------------------------------------- decisions
class DecisionBody(BaseModel):
    """An investigator's verdict on a lead or identity match."""
    kind: str = Field(..., max_length=16)          # lead | identity | anomaly
    target: str = Field(..., max_length=200)        # entity name / match id
    action: str = Field(..., max_length=24)         # VERIFIED | REJECTED | ...
    note: Optional[str] = Field(None, max_length=1000)
    officer: str = Field("Officer-101", max_length=64)


@router.get("/api/decisions")
def decisions():
    """Every recorded investigator verdict, keyed by kind:target."""
    return {"decisions": get_decisions(), "actions": DECISION_ACTIONS}


@router.post("/api/decision")
def decide(body: DecisionBody):
    """Record a human verdict and commit it to the audit chain.

    'Verified' means an investigator confirmed it — never the system.
    """
    try:
        entry = record_decision(body.kind, body.target, body.action,
                                body.officer, body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except DecisionStoreError as e:
        # refuse rather than overwrite a corrupt store with an empty one
        raise HTTPException(500, str(e))
    audit.record(
        body.officer,
        f"{entry['action']}: {entry['kind']} '{entry['target']}'"
        + (f" — {entry['note']}" if entry["note"] else ""),
        action_type=DECISION_TO_AUDIT.get(entry["action"], "DATA_ACCESSED"),
        target=entry["target"])
    return {"status": "recorded", "decision": entry}


# ---------------------------------------------------------------- graph
@router.get("/api/graph")
def graph(officer: str = Query("Officer-101", pattern=_OFFICER),
          window: str = Query(config.DEFAULT_TIME_WINDOW),
          start: Optional[str] = Query(None, pattern=_ISO),
          end: Optional[str] = Query(None, pattern=_ISO)):
    """The analysed graph with provenance, leads, anomalies and timeline."""
    if window not in WINDOW_VALUES:
        raise HTTPException(400, f"window must be one of {WINDOW_VALUES}")
    audit.record(officer, f"QUERY: network graph (window={window})",
                 action_type="GRAPH_QUERY")
    return build_payload(window=window, start=start, end=end)


@router.api_route("/api/rebuild", methods=["POST", "GET"])
def rebuild(officer: str = Query("Officer-101", pattern=_OFFICER)):
    # POST is the intended verb (state-changing); GET is kept only for the
    # documented curl one-liner and is CORS-restricted like everything else.
    """Force re-ingestion. Use after changing files in data/."""
    audit.record(officer, "ACTION: re-ingested all data sources",
                 action_type="ADMIN_ACTION")
    invalidate()
    payload = build_payload(force=True)
    return {"status": "rebuilt", "stats": payload["stats"]}


# ---------------------------------------------------------------- timeline
@router.get("/api/timeline")
def timeline(officer: str = Query("Officer-101", pattern=_OFFICER),
             window: str = Query(config.DEFAULT_TIME_WINDOW),
             start: Optional[str] = Query(None, pattern=_ISO),
             end: Optional[str] = Query(None, pattern=_ISO),
             event_type: Optional[str] = Query(None, max_length=40)):
    if window not in WINDOW_VALUES:
        raise HTTPException(400, f"window must be one of {WINDOW_VALUES}")
    audit.record(officer, f"QUERY: timeline (window={window})",
                 action_type="DATA_ACCESSED")
    tl = build_payload(window=window, start=start, end=end)["timeline"]
    if event_type:
        tl = dict(tl, events=[e for e in tl["events"]
                              if e["type"] == event_type])
    return tl


# ---------------------------------------------------------------- provenance
@router.get("/api/evidence/{record_id}")
def evidence(record_id: str = Path(..., max_length=64,
                                   pattern=r"^[A-Za-z0-9_\-]{1,64}$"),
             officer: str = Query("Officer-101", pattern=_OFFICER)):
    """Everything one source record supports — reverse provenance."""
    a = _entity_index()
    audit.record(officer, f"DATA_ACCESSED: source record {record_id}",
                 action_type="DATA_ACCESSED", target=record_id)
    rec = None
    for rs in a["records"].values():
        for r in rs:
            if r.record_id == record_id:
                rec = r
                break
        if rec:
            break
    if not rec:
        raise HTTPException(404, f"no such record: {record_id}")
    index = a["bundle"].ledger.record_index()
    # Identifiers in the raw row resolved to the registered holder, so a CDR
    # row reads "9822000004 · Javed Ansari" instead of a bare number. A phone
    # with no subscriber on file is stated as such (None), never guessed.
    owner: Dict[str, str] = {}
    for ent, ids in a["bundle"].entity_identifiers.items():
        for ph in ids.get("phones", []):
            owner[ph] = ent
        for ac in ids.get("accounts", []):
            owner[ac] = ent
    resolved: Dict[str, Optional[str]] = {}
    for k, v in rec.fields.items():
        if k.startswith("_") or not isinstance(v, str):
            continue
        if v.strip() in owner:
            resolved[k] = owner[v.strip()]
        elif k in ("caller", "receiver") and v.strip():
            resolved[k] = None
    return {
        "record": {**rec.cite(), "fields": {k: v for k, v in rec.fields.items()
                                            if not k.startswith("_")},
                   "resolved": resolved,
                   "issues": rec.issues, "timeless": rec.timeless},
        "supports": index.get(record_id, []),
        "source_type_description": config.SOURCE_TYPES.get(rec.source_type, ""),
    }


@router.get("/api/relationship")
def relationship(a: str = Query(..., max_length=120),
                 b: str = Query(..., max_length=120),
                 officer: str = Query("Officer-101", pattern=_OFFICER)):
    """The evidence drawer for one relationship: why these two are linked."""
    data = _entity_index()
    G = data["bundle"].G
    if a not in G or b not in G:
        raise HTTPException(404, "unknown entity")
    edge = G.get_edge_data(a, b)
    if not edge:
        raise HTTPException(404, f"no recorded relationship between {a} and {b}")
    audit.record(officer, f"DATA_ACCESSED: relationship {a} <-> {b}",
                 action_type="DATA_ACCESSED", target=f"{a}|{b}")
    return {"from": a, "to": b, **edge}


# ---------------------------------------------------------------- entities
@router.get("/api/entity/{name}")
def entity(name: str = Path(..., max_length=120),
           officer: str = Query("Officer-101", pattern=_OFFICER)):
    """Full dossier: identifiers, relationships, lead score, ER candidates."""
    a = _entity_index()
    G = a["bundle"].G
    if name not in G:
        raise HTTPException(404, f"unknown entity: {name}")
    audit.record(officer, f"ENTITY_SEARCHED: {name}",
                 action_type="ENTITY_SEARCHED", target=name)
    d = G.nodes[name]
    rels = []
    for nbr in G.neighbors(name):
        e = G.get_edge_data(name, nbr) or {}
        rels.append({
            "with": nbr, "kind": G.nodes[nbr].get("kind"),
            "rel": e.get("rel"), "rel_types": e.get("rel_types", []),
            "confidence": e.get("confidence"),
            "source_types": e.get("source_types", []),
            "source_records": e.get("source_records", []),
            "start_time": e.get("start_time"), "end_time": e.get("end_time"),
            "money_inr": e.get("money_inr"), "calls": e.get("calls"),
            "uncertainty": e.get("uncertainty", []),
            "algorithm": e.get("algorithm"),
        })
    rels.sort(key=lambda r: -(r["confidence"] or 0))
    lead = next((l for l in a["leads"] if l["entity"] == name), None)
    er = a["resolution"]
    return {
        "entity": name,
        "kind": d.get("kind"),
        "in_fir": bool(d.get("in_fir")),
        "fir_ids": d.get("fir_ids", []),
        "money_in": d.get("money_in", 0),
        "money_out": d.get("money_out", 0),
        "community": a["structure"]["community_of"].get(name, -1),
        "pagerank": round(a["structure"]["pagerank"].get(name, 0), 4),
        "betweenness": round(a["structure"]["betweenness"].get(name, 0), 4),
        "identifiers": a["bundle"].entity_identifiers.get(name, {}),
        "relationships": rels,
        "lead": lead,
        "identity_candidates": [m for m in er["matches"] if m["entity"] == name],
        "identity_cluster": next((c for c in er["clusters"]
                                  if name in c["members"]), None),
        "anomalies": [x for x in a["anomalies"]
                      if name in x["entities_involved"]],
        "verification_notice": config.HUMAN_VERIFICATION_NOTICE,
    }


@router.get("/api/entity/{name}/casefile")
def entity_casefile(name: str = Path(..., max_length=120),
                    officer: str = Query("Officer-101", pattern=_OFFICER)):
    """The FIR(s) a person is named in, broken into bullet points, plus their
    dated recent moves — so an investigator can read the case narrative next to
    what the entity has been doing. Everything cites its source record."""
    a = _entity_index()
    G = a["bundle"].G
    if name not in G:
        raise HTTPException(404, f"unknown entity: {name}")
    audit.record(officer, f"DATA_ACCESSED: case file {name}",
                 action_type="DATA_ACCESSED", target=name)

    # --- FIRs the person appears in, structured into bullets -----------------
    firs = []
    for r in a["records"].get("fir", []):
        names = r.fields.get("names", [])
        if name not in names:
            continue
        raw_sections = r.fields.get("sections", "") or ""
        # split only on list separators — a citation like "NDPS Act 8/20" is one item
        sections = [s.strip() for s in re.split(r"[,;]| and ", raw_sections) if s.strip()]
        narrative = r.fields.get("narrative", "") or ""
        points = [s.strip() for s in re.split(r"(?<=[.!?])\s+", narrative) if s.strip()]
        firs.append({
            "fir_id": r.record_id,
            "date": r.timestamp,
            "police_station": r.fields.get("police_station") or "unknown",
            "sections": sections or ([raw_sections] if raw_sections else []),
            "co_accused": [n for n in names if n != name],
            "phones_recovered": r.fields.get("phones", []),
            "narrative": narrative,
            "narrative_points": points,
            "source_file": r.source_file,
        })
    firs.sort(key=lambda f: f["date"] or "")

    # --- recent moves: dated events + money movements involving this entity ---
    moves = []
    for ev in a["events"]:
        if ev.get("type") == "CALL_ACTIVITY":
            continue        # the corpus-wide daily aggregate; replaced below
        if ev.get("timestamp") and name in (ev.get("entities") or []):
            moves.append({"date": ev["timestamp"], "type": ev["type"],
                          "summary": ev["summary"],
                          "records": ev.get("source_records", [])[:1]})
    # Calls: per day, WHO this entity spoke to, how often, in which direction.
    # The timeline's "19 calls across 11 pairs" counts everyone's calls that
    # day; an investigator reading a case file needs this person's contacts.
    own_phones = set(a["bundle"].entity_identifiers.get(name, {}).get("phones", []))
    by_day: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for (x, y), rs in a["bundle"].call_records.items():
        if name not in (x, y):
            continue
        other = y if x == name else x
        for r in rs:
            if not r.timestamp:
                continue
            slot = by_day.setdefault(r.timestamp[:10], {})
            c = slot.setdefault(other, {"with": other, "calls": 0, "outgoing": 0,
                                        "incoming": 0, "duration_sec": 0, "records": []})
            c["calls"] += 1
            if (r.fields.get("caller") or "").strip() in own_phones:
                c["outgoing"] += 1
            else:
                c["incoming"] += 1
            try:
                c["duration_sec"] += int(float(r.fields.get("duration_sec") or 0))
            except (TypeError, ValueError):
                pass
            c["records"].append(r.record_id)
    for day, slot in by_day.items():
        contacts = sorted(slot.values(), key=lambda c: (-c["calls"], c["with"]))
        total = sum(c["calls"] for c in contacts)
        head = ", ".join(f'{c["with"]} ×{c["calls"]}' for c in contacts[:3])
        more = f" +{len(contacts) - 3} more" if len(contacts) > 3 else ""
        moves.append({"date": f"{day}T00:00:00", "type": "CALL_ACTIVITY",
                      "summary": f"{total} call{'s' if total != 1 else ''} with "
                                 f"{len(contacts)} contact{'s' if len(contacts) != 1 else ''}: {head}{more}",
                      "records": [rid for c in contacts for rid in c["records"]],
                      "contacts": contacts})
    d = G.nodes[name]
    # Transactions come straight from the bank rows this person is party to,
    # so each move carries its own date and its own record — not the edge's
    # aggregate date and an arbitrary citation.
    acct_owner = {r.fields.get("account", ""): r.fields.get("holder_name", "")
                  for r in a["records"].get("accounts", [])}
    for r in a["records"].get("bank", []):
        if not r.timestamp:
            continue
        frm = acct_owner.get(r.fields.get("from_account", ""), r.fields.get("from_account", ""))
        to = acct_owner.get(r.fields.get("to_account", ""), r.fields.get("to_account", ""))
        if name not in (frm, to):
            continue
        amt = float(r.fields.get("_amount", 0) or 0)
        other = to if frm == name else frm
        verb = "sent to" if frm == name else "received from"
        moves.append({"date": r.timestamp, "type": "TRANSACTION",
                      "summary": f"₹{amt:,.0f} {verb} {other}",
                      "records": [r.record_id]})
    # dedupe by (date,summary), newest first
    seen, uniq = set(), []
    for m in sorted(moves, key=lambda m: m["date"], reverse=True):
        key = (m["date"], m["summary"])
        if key not in seen:
            seen.add(key)
            uniq.append(m)

    anomalies = [{"type": x["anomaly_type"], "severity": x["severity"],
                  "explanation": x["explanation"]}
                 for x in a["anomalies"] if name in x["entities_involved"]][:4]

    lead = next((l for l in a["leads"] if l["entity"] == name), None)
    return {
        "entity": name,
        "in_fir": bool(d.get("in_fir")),
        "kind": d.get("kind"),
        "firs": firs,
        "recent_moves": uniq[:20],
        "anomalies": anomalies,
        "lead_band": lead["band"] if lead else None,
        "no_fir_note": (None if d.get("in_fir") else
                        "Not named in any FIR in this corpus. Surfaced through "
                        "the financial and communication trail — itself a lead "
                        "worth examining."),
        "verification_notice": config.HUMAN_VERIFICATION_NOTICE,
    }


# ---------------------------------------------------------------- findings
@router.get("/api/leads")
def leads(officer: str = Query("Officer-101", pattern=_OFFICER),
          min_score: int = Query(0, ge=0, le=100),
          limit: int = Query(40, ge=1, le=200)):
    a = _entity_index()
    audit.record(officer, f"LEAD_GENERATED: {len(a['leads'])} leads scored",
                 action_type="LEAD_GENERATED")
    items = [l for l in a["leads"] if l["lead_score"] >= min_score][:limit]
    return {"leads": items, "caps": config.LEAD_SCORE_CAPS,
            "bands": config.LEAD_SCORE_BANDS,
            "network_controllers": a["controllers"],
            "notice": config.HUMAN_VERIFICATION_NOTICE,
            "disclaimer": ("Lead scores rank what to examine next. They are "
                           "not a determination of guilt.")}


@router.get("/api/anomalies")
def anomalies(officer: str = Query("Officer-101", pattern=_OFFICER),
              severity: Optional[str] = Query(None, max_length=16),
              anomaly_type: Optional[str] = Query(None, max_length=64)):
    a = _entity_index()
    audit.record(officer, "QUERY: anomaly findings", action_type="DATA_ACCESSED")
    items: List[Dict[str, Any]] = a["anomalies"]
    if severity:
        sev = severity.upper()
        if sev not in config.SEVERITY_ORDER:
            raise HTTPException(400, f"severity must be one of "
                                     f"{list(config.SEVERITY_ORDER)}")
        items = [x for x in items if x["severity"] == sev]
    if anomaly_type:
        items = [x for x in items if x["anomaly_type"] == anomaly_type]
    return {"anomalies": items, "count": len(items),
            "detectors": config.ANOMALY_CONFIG,
            "notice": config.HUMAN_VERIFICATION_NOTICE}


@router.get("/api/entity-resolution")
def entity_resolution(officer: str = Query("Officer-101", pattern=_OFFICER),
                      min_confidence: int = Query(0, ge=0, le=100)):
    a = _entity_index()
    audit.record(officer, "QUERY: entity resolution candidates",
                 action_type="DATA_ACCESSED")
    er = a["resolution"]
    return {
        "matches": [m for m in er["matches"]
                    if m["confidence"] >= min_confidence],
        "clusters": er["clusters"],
        "correlations": er["correlations"],
        "stats": er["stats"],
        "policy": er["policy"],
        "config": config.ER_CONFIG,
    }


# ---------------------------------------------------------------- audit
@router.get("/api/audit")
def audit_log(officer: Optional[str] = Query(None, pattern=_OFFICER),
              action_type: Optional[str] = Query(None, max_length=32),
              case_id: Optional[str] = Query(None, max_length=64),
              limit: int = Query(25, ge=1, le=500)):
    ok, bad = audit.verify()
    blocks = audit.filter(officer=officer, action_type=action_type,
                          case_id=case_id, limit=limit)
    return {"chain_valid": ok, "tampered_block": bad, "blocks": blocks,
            "total_blocks": len(audit.chain), "actions": AUDIT_ACTIONS}


@router.get("/api/audit/tamper-demo")
def tamper_demo():
    """Corrupt a block in memory, show verification catches it, restore."""
    if len(audit.chain) < 2:
        return {"error": "make a query first"}
    # Run the demonstration on a COPY. Mutating the live chain in memory raced
    # with concurrent writes and could persist the tampered block.
    demo = AuditChain.__new__(AuditChain)
    demo.path = None
    demo.chain = copy.deepcopy(audit.chain)
    demo.chain[1]["action"] = "TAMPERED: query deleted by rogue admin"
    ok, bad = demo.verify()
    return {"demo": "block 1 was modified on an in-memory copy",
            "chain_valid_after_tampering": ok, "first_broken_block": bad,
            "conclusion": "Hash chain detects any edit to past queries — live chain untouched",
            "chain_valid_after_restore": audit.verify()[0]}


# ---------------------------------------------------------------- meta
@router.get("/api/config")
def configuration():
    """The thresholds behind every finding, exposed for scrutiny."""
    return {
        "source_types": config.SOURCE_TYPES,
        "edge_base_confidence": config.EDGE_BASE_CONFIDENCE,
        "confidence_model": {
            "corroboration_bonus_per_extra_source_type": config.CORROBORATION_BONUS,
            "max_corroboration_bonus": config.MAX_CORROBORATION_BONUS,
            "repeat_observation_cap": config.REPEAT_OBSERVATION_BONUS_CAP,
            "ceiling": config.CONFIDENCE_CEILING,
            "floor": config.CONFIDENCE_FLOOR,
        },
        "anomaly_detectors": config.ANOMALY_CONFIG,
        "lead_score_caps": config.LEAD_SCORE_CAPS,
        "lead_score_bands": config.LEAD_SCORE_BANDS,
        "entity_resolution": config.ER_CONFIG,
        "time_windows": config.TIME_WINDOWS,
        "notices": {
            "verification": config.HUMAN_VERIFICATION_NOTICE,
            "ai_brief": config.AI_BRIEF_NOTICE,
        },
    }

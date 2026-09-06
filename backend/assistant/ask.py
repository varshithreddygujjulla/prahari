"""
ask.py — intent detection and grounded answers.

Understands (by keyword + entity/date/identifier extraction, with fuzzy matching
and one-turn conversation memory):

  * person summary   "summary of Ramesh Yadav", "who is Vikram Rathore"
  * by identifier    "who owns KA01AB1234", "whose number is 9990001111", "ACC9002"
  * date summary     "what happened on 2026-03-18", "activity on 18 march"
  * connection       "how are Ramesh and Salim connected", "link between A and B"
  * network head     "who is the network controller"
  * broker           "who is the broker"
  * money            "money trail", "who received the most money", "biggest transfer"
  * calls            "who did Ramesh call", "call spikes"
  * leads            "top leads", "leads above 60"
  * anomalies        "what looks unusual", "flags"
  * case overview    "case summary", "brief me", "overview"
  * counts           "how many FIRs", "how many entities"
  * follow-ups       "what about his money" (remembers the last entity)

Every answer is built from the analysis dict and cites the source records behind
each statement. Nothing is invented; unknown questions get an honest
"here's what I can answer" reply.
"""
import re
from datetime import datetime
from difflib import get_close_matches
from typing import Any, Dict, List, Optional

import networkx as nx

from backend import config

EXAMPLES = [
    "Summary of Ramesh Yadav",
    "What happened on 2026-03-18",
    "Who is the network controller",
    "How are Ramesh Yadav and Salim Qureshi connected",
    "Who received the most money",
    "Who owns DL01AB4455",
    "Case summary",
]

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
           "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_STOP = {"the", "of", "is", "who", "what", "show", "me", "tell", "about", "for",
         "and", "give", "a", "an", "on", "in", "to", "how", "was", "were", "did",
         "does", "do", "with", "his", "her", "their", "its", "he", "she", "they"}


def _fmt_inr(n) -> str:
    try:
        return "₹{:,.0f}".format(float(n))
    except (TypeError, ValueError):
        return "₹0"


# ---------------------------------------------------------------- indexes
def _identifier_index(a: Dict[str, Any]) -> Dict[str, str]:
    """Map every phone / account / vehicle id to the entity that holds it."""
    idx = {}
    for name, ids in a["bundle"].entity_identifiers.items():
        for group in ("phones", "accounts", "vehicles"):
            for v in ids.get(group, []):
                idx[v.upper()] = name
    # unresolved numbers and bare account/vehicle nodes resolve to themselves
    for n, d in a["bundle"].G.nodes(data=True):
        if d.get("kind") in ("unresolved_number", "account", "vehicle"):
            idx.setdefault(n.upper(), n)
    return idx


# ---------------------------------------------------------------- extraction
def _find_entities(q: str, a: Dict[str, Any],
                   fuzzy_out: Optional[Dict[str, str]] = None) -> List[str]:
    """Names or identifiers mentioned in the query.

    Order: exact name substring → identifier (phone/account/vehicle) → fuzzy
    name match on capitalised phrases and leftover tokens. Fuzzy hits are
    recorded in `fuzzy_out` (typed text → matched name) so the answer can say
    it guessed.
    """
    G = a["bundle"].G
    names = list(G.nodes())
    ql = q.lower()
    hits: List[str] = []

    # identifiers first (phone / account / vehicle) so "who owns DL01AB4455"
    # resolves straight to the registered owner rather than the plate node.
    idx = _identifier_index(a)
    for tok in re.findall(r"[A-Za-z]{1,3}\d[\w]*|\b9\d{9}\b|\bACC\w+\b", q):
        owner = idx.get(tok.upper())
        if owner and owner not in hits:
            hits.append(owner)

    for name in sorted(names, key=len, reverse=True):
        nl = name.lower()
        if nl in ql and not any(nl in h.lower() for h in hits):
            hits.append(name)

    if hits:
        return hits

    # fuzzy: compare each candidate phrase/token to known names
    lname = {n.lower(): n for n in names}
    cands = re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?", q) or \
        [t for t in re.findall(r"[a-z]{4,}", ql) if t not in _STOP]
    for c in cands:
        m = get_close_matches(c.lower(), list(lname), n=1, cutoff=0.82)
        if m and lname[m[0]] not in hits:
            hits.append(lname[m[0]])
            if fuzzy_out is not None:
                fuzzy_out[c] = lname[m[0]]
    return hits


def _case_year(a: Dict[str, Any]) -> int:
    """Year of the case clock anchor — never the wall clock."""
    anchor = (a.get("clock") or {}).get("anchor") or ""
    return int(anchor[:4]) if anchor[:4].isdigit() else datetime.now().year


def _case_span(a: Dict[str, Any]) -> str:
    c = a.get("clock") or {}
    lo, hi = (c.get("first_observed") or "")[:10], (c.get("last_observed") or "")[:10]
    return f"{lo} to {hi}" if lo and hi else "unknown (no dated records)"


def _find_date(q: str, year: int = 2026) -> Optional[str]:
    ql = q.lower()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", ql)
    if m:
        return m.group(0)
    m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", ql)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.search(r"\b(\d{1,2})\s+([a-z]{3,})", ql)
    if m and m.group(2)[:3] in _MONTHS:
        return f"{year}-{_MONTHS[m.group(2)[:3]]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"\b([a-z]{3,})\s+(\d{1,2})\b", ql)
    if m and m.group(1)[:3] in _MONTHS:
        return f"{year}-{_MONTHS[m.group(1)[:3]]:02d}-{int(m.group(2)):02d}"
    return None


def _bullet(text, entity=None, record=None):
    b = {"text": text}
    if entity:
        b["entity"] = entity
    if record:
        b["record"] = record
    return b


def _wrap(intent, title, summary, bullets, entities=None, records=None, focus=None):
    return {
        "intent": intent,
        "title": title,
        "summary": summary,
        "bullets": bullets or [],
        "entities": entities or [],
        "records": records or [],
        "focus": focus,                 # the primary entity, for follow-up memory
        "disclaimer": config.HUMAN_VERIFICATION_NOTICE,
        "grounded": "Answered from the case's structured records — no external "
                    "model, no invented facts.",
    }


def _controller_name(a):
    c = a.get("controllers") or []
    return c[0]["entity"] if c else None


# ---------------------------------------------------------------- answers
def _answer_person(name: str, a: Dict[str, Any]) -> Dict[str, Any]:
    G = a["bundle"].G
    d = G.nodes[name]
    kind = d.get("kind", "person")
    bullets, records = [], []

    lead = next((l for l in a["leads"] if l["entity"] == name), None)
    if lead:
        bullets.append(_bullet(
            f"Investigative Lead Score {lead['lead_score']}/100 ({lead['band']}) — "
            f"top factors: " + ", ".join(f["factor"] for f in lead["factors"][:3])))

    fir_recs = [r for r in a["records"].get("fir", []) if name in r.fields.get("names", [])]
    if fir_recs:
        for r in fir_recs:
            bullets.append(_bullet(
                f"Named in {r.record_id} — {r.fields.get('police_station','?')}, "
                f"{(r.timestamp or '')[:10]}, {r.fields.get('sections','')}",
                record=r.record_id))
            records.append(r.record_id)
    elif kind == "person":
        bullets.append(_bullet("Not named in any FIR in this corpus — surfaced "
                               "through the financial / communication trail."))

    mi, mo = d.get("money_in", 0), d.get("money_out", 0)
    if mi or mo:
        bullets.append(_bullet(f"Funds: {_fmt_inr(mi)} received, {_fmt_inr(mo)} sent "
                               f"(net {_fmt_inr(mi - mo)})."))

    ids = a["bundle"].entity_identifiers.get(name, {})
    idbits = []
    if ids.get("phones"):
        idbits.append(f"phone {', '.join(ids['phones'])}")
    if ids.get("vehicles"):
        idbits.append(f"vehicle {', '.join(ids['vehicles'])}")
    if ids.get("accounts"):
        idbits.append(f"account {', '.join(ids['accounts'])}")
    if idbits:
        bullets.append(_bullet("Identifiers: " + "; ".join(idbits) + "."))

    nbrs = []
    for nbr in G.neighbors(name):
        e = G.get_edge_data(name, nbr) or {}
        nbrs.append((nbr, e.get("confidence", 0), e.get("rel", ""), e))
    nbrs.sort(key=lambda x: -(x[1] or 0))
    for nbr, conf, rel, e in nbrs[:4]:
        extra = ""
        if e.get("money_inr"):
            extra = f" · {_fmt_inr(e['money_inr'])}"
        elif e.get("calls"):
            extra = f" · {e['calls']} calls"
        bullets.append(_bullet(f"{rel} with {nbr} ({conf}% confidence){extra}", entity=nbr))

    moves = [ev for ev in a["events"] if ev.get("timestamp") and name in (ev.get("entities") or [])]
    moves.sort(key=lambda e: e["timestamp"], reverse=True)
    for ev in moves[:3]:
        bullets.append(_bullet(f"{ev['timestamp'][:10]}: {ev['summary']}"))

    anos = [x for x in a["anomalies"] if name in x["entities_involved"]]
    for x in anos[:2]:
        bullets.append(_bullet(f"[{x['severity']}] {x['explanation']}"))

    cands = [m for m in a["resolution"]["matches"]
             if m["entity"] == name and m["confidence"] >= 55]
    if cands:
        bullets.append(_bullet("Possible alternate identities (unconfirmed): "
                               + ", ".join(m["candidate"] for m in cands)))

    label = "Potential Network Controller" if name == _controller_name(a) else kind.replace("_", " ")
    summary = f"{name} — {label}. " + (
        f"Lead score {lead['lead_score']}/100. " if lead else "") + \
        (f"Named in {len(fir_recs)} FIR(s). " if fir_recs else
         ("Named in no FIR. " if kind == "person" else ""))
    return _wrap("person_summary", name, summary, bullets, [name], records, focus=name)


def _answer_owner(name: str, ident: str, a: Dict[str, Any]) -> Dict[str, Any]:
    """A direct 'who owns X' — lead with the ownership, then the full profile."""
    G = a["bundle"].G
    # identifier that resolves to itself = no registered holder (unresolved number)
    if ident.upper() == name.upper():
        kind = G.nodes[name].get("kind") if name in G else None
        contacts = list(G.neighbors(name)) if name in G else []
        bullets = [_bullet(f"{ident} has no registered subscriber/owner in the "
                           f"registry — the holder is unresolved.")]
        for c in contacts[:6]:
            bullets.append(_bullet(f"Appears with {c}", entity=c))
        return _wrap("owner", f"{ident} — unregistered",
                     f"{ident} is not registered to anyone; it is an unresolved "
                     f"{('number' if kind == 'unresolved_number' else 'identifier')}.",
                     bullets, [name] + contacts[:6], focus=name)
    res = _answer_person(name, a)
    res["title"] = f"{ident} → {name}"
    res["summary"] = f"{ident} is associated with {name}. " + res["summary"]
    res["intent"] = "owner"
    res["bullets"] = [_bullet(f"{ident} is associated with {name}.", entity=name)] + res["bullets"]
    return res


def _answer_date(date: str, a: Dict[str, Any]) -> Dict[str, Any]:
    evs = [e for e in a["events"] if (e.get("timestamp") or "").startswith(date)]
    if not evs:
        return _wrap("date_summary", date,
                     f"No dated activity recorded on {date}.",
                     [_bullet(f"Dated records in this case span {_case_span(a)}; "
                              f"try a date in that range.")])
    by_type: Dict[str, int] = {}
    bullets, records = [], []
    for e in sorted(evs, key=lambda e: e["timestamp"]):
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        rec = (e.get("source_records") or [None])[0]
        bullets.append(_bullet(f"{e['type'].replace('_', ' ')}: {e['summary']}", record=rec))
        if rec:
            records.append(rec)
    counts = ", ".join(f"{v} {k.replace('_', ' ').lower()}" for k, v in by_type.items())
    return _wrap("date_summary", f"Activity on {date}",
                 f"{len(evs)} recorded event(s) on {date}: {counts}.",
                 bullets, [], records)


def _answer_connection(a_name: str, b_name: str, a: Dict[str, Any]) -> Dict[str, Any]:
    G = a["bundle"].G
    direct = G.get_edge_data(a_name, b_name)
    if direct:
        rels = direct.get("rel_types", [direct.get("rel")])
        bullets = [_bullet(f"Directly linked: {', '.join(rels)} "
                           f"({direct.get('confidence')}% confidence).")]
        for rid in (direct.get("source_records") or [])[:6]:
            bullets.append(_bullet(f"Evidence: {rid}", record=rid))
        return _wrap("connection", f"{a_name} ↔ {b_name}",
                     f"{a_name} and {b_name} are directly linked ("
                     f"{', '.join(rels)}).", bullets, [a_name, b_name],
                     direct.get("source_records", [])[:6])
    try:
        path = nx.shortest_path(G, a_name, b_name)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        path = None
    if not path:
        return _wrap("connection", f"{a_name} ↔ {b_name}",
                     f"No path connects {a_name} and {b_name} in the current data.",
                     [_bullet("They may be linked through records not yet ingested.")],
                     [a_name, b_name])
    bullets = []
    for i in range(len(path) - 1):
        e = G.get_edge_data(path[i], path[i + 1]) or {}
        bullets.append(_bullet(f"{path[i]} —{e.get('rel','?')}→ {path[i+1]} "
                               f"({e.get('confidence','?')}%)", entity=path[i + 1]))
    return _wrap("connection", f"{a_name} ↔ {b_name}",
                 f"{a_name} connects to {b_name} through {len(path) - 2} "
                 f"intermediary(ies): " + " → ".join(path) + ".",
                 bullets, path)


def _answer_controller(a: Dict[str, Any]) -> Dict[str, Any]:
    ctrl = (a.get("controllers") or [])
    if not ctrl:
        return _wrap("controller", "Potential network controller",
                     "No potential network controller stands out in this data.", [])
    c = ctrl[0]
    bullets = [
        _bullet(f"{c['entity']} receives {_fmt_inr(c['net_inflow_inr'])} in net "
                f"consolidated transfers.", entity=c["entity"]),
        _bullet(f"Named in {c['fir_mentions']} FIRs — financially central, absent "
                f"from the case record."),
        _bullet(c["basis"]),
    ]
    for u in c.get("uncertainty", [])[:1]:
        bullets.append(_bullet("Caveat: " + u))
    return _wrap("controller", "Potential Network Controller",
                 f"{c['entity']} is the strongest potential network controller — "
                 f"financially central, in no FIR. An investigative lead, not a "
                 f"conclusion.", bullets, [c["entity"]], c.get("source_records", []),
                 focus=c["entity"])


def _answer_broker(a: Dict[str, Any]) -> Dict[str, Any]:
    G = a["bundle"].G
    comm = a["structure"]["community_of"]
    best = None
    for n, d in G.nodes(data=True):
        if d.get("kind") != "unresolved_number":
            continue
        touched = {comm.get(x) for x in G.neighbors(n)}
        touched.discard(None)
        if len(touched) >= 2:
            contacts = list(G.neighbors(n))
            if not best or len(contacts) > len(best[1]):
                best = (n, contacts, touched)
    if not best:
        return _wrap("broker", "Potential broker",
                     "No unresolved number bridges clusters in the current data.", [])
    n, contacts, touched = best
    records = []
    bullets = [_bullet(f"Unresolved number {n} contacts entities across "
                       f"{len(touched)} clusters — no subscriber is registered to it, "
                       f"so the handset holder is unknown.", entity=n)]
    for c in contacts[:6]:
        e = G.get_edge_data(n, c) or {}
        rid = (e.get("source_records") or [None])[0]
        bullets.append(_bullet(f"Contacts {c}" + (f" · {e['calls']} calls" if e.get("calls") else ""),
                               entity=c, record=rid))
        if rid:
            records.append(rid)
    return _wrap("broker", "Potential broker",
                 f"{n} looks like a broker — an unregistered number linking "
                 f"{len(touched)} clusters. Attribution of the handset is unproven.",
                 bullets, [n] + contacts[:6], records, focus=n)


def _answer_money(name: Optional[str], a: Dict[str, Any]) -> Dict[str, Any]:
    G = a["bundle"].G
    if name:                                    # money picture for one entity
        d = G.nodes[name]
        bullets, records = [], []
        bullets.append(_bullet(f"Received {_fmt_inr(d.get('money_in', 0))}, sent "
                               f"{_fmt_inr(d.get('money_out', 0))} (net "
                               f"{_fmt_inr(d.get('money_in', 0) - d.get('money_out', 0))})."))
        for nbr in G.neighbors(name):
            e = G.get_edge_data(name, nbr) or {}
            if e.get("money_inr"):
                rid = next((r for r in (e.get("source_records") or []) if r.startswith("TXN")), None)
                bullets.append(_bullet(f"{_fmt_inr(e['money_inr'])} with {nbr}", entity=nbr, record=rid))
                if rid:
                    records.append(rid)
        return _wrap("money", "Money — " + name,
                     f"Financial movement involving {name}.", bullets, [name], records, focus=name)

    # case-wide money picture, computed from bank records
    acct_owner = {}
    for r in a["records"].get("accounts", []):
        acct_owner[r.fields.get("account", "")] = r.fields.get("holder_name", "")
    net = {}
    biggest = None
    for r in a["records"].get("bank", []):
        amt = float(r.fields.get("_amount", 0) or 0)
        frm = acct_owner.get(r.fields.get("from_account", ""), r.fields.get("from_account", ""))
        to = acct_owner.get(r.fields.get("to_account", ""), r.fields.get("to_account", ""))
        net[to] = net.get(to, 0) + amt
        net[frm] = net.get(frm, 0) - amt
        if not biggest or amt > biggest[0]:
            biggest = (amt, frm, to, r.record_id)
    top = sorted(net.items(), key=lambda kv: -kv[1])[:5]
    bullets = [_bullet(f"{nm}: net {_fmt_inr(v)}", entity=(nm if nm in G else None))
               for nm, v in top if v > 0]
    records = []
    if biggest:
        bullets.append(_bullet(f"Biggest single transfer: {_fmt_inr(biggest[0])} "
                               f"{biggest[1]} → {biggest[2]}", record=biggest[3]))
        records.append(biggest[3])
    shells = [n for n, d in G.nodes(data=True) if d.get("kind") == "shell_company"]
    if shells:
        bullets.append(_bullet(f"Funds consolidate through {shells[0]} — the layering "
                               f"pattern.", entity=shells[0]))
    return _wrap("money", "Money trail",
                 "Largest net fund receivers in the case, and the biggest single "
                 "transfer.", bullets, [nm for nm, _ in top], records)


def _answer_calls(name: Optional[str], a: Dict[str, Any]) -> Dict[str, Any]:
    G = a["bundle"].G
    if name:
        bullets = []
        for nbr in G.neighbors(name):
            e = G.get_edge_data(name, nbr) or {}
            if e.get("calls"):
                rid = next((r for r in (e.get("source_records") or []) if r.startswith("CDR")), None)
                bullets.append(_bullet(f"{e['calls']} calls with {nbr}", entity=nbr, record=rid))
        bullets.sort(key=lambda b: -int(re.match(r"(\d+)", b["text"]).group(1)))
        if not bullets:
            bullets = [_bullet("No call records for this entity.")]
        return _wrap("calls", "Calls — " + name,
                     f"Call activity involving {name}.", bullets, [name], focus=name)
    spikes = [x for x in a["anomalies"] if x["anomaly_type"] == "COMMUNICATION_VOLUME_SPIKE"]
    bullets = [_bullet(f"[{x['severity']}] {x['explanation']}",
                       record=(x.get("source_records") or [None])[0]) for x in spikes[:5]]
    if not bullets:
        bullets = [_bullet("No call-volume spikes above baseline in the window.")]
    return _wrap("calls", "Call spikes",
                 f"{len(spikes)} call-volume spike(s) detected against per-pair "
                 f"baselines.", bullets)


def _answer_leads(q: str, a: Dict[str, Any]) -> Dict[str, Any]:
    m = re.search(r"above\s+(\d{1,3})", q)
    floor = int(m.group(1)) if m else 0
    leads = [l for l in a["leads"] if l["lead_score"] >= floor][:8]
    bullets = [_bullet(f"{l['entity']} — {l['lead_score']}/100 ({l['band']})",
                       entity=l["entity"]) for l in leads]
    summ = (f"{len(leads)} lead(s) scoring {floor} or above." if floor
            else f"Top {len(leads)} investigative leads.") + \
        " Scores are a triage aid, not a determination of guilt."
    return _wrap("leads", "Investigative leads", summ, bullets,
                 [l["entity"] for l in leads])


def _answer_anomalies(a: Dict[str, Any]) -> Dict[str, Any]:
    anos = a["anomalies"][:6]
    bullets = [_bullet(f"[{x['severity']}] {x['explanation']}",
                       record=(x.get("source_records") or [None])[0]) for x in anos]
    return _wrap("anomalies", "Anomaly findings",
                 f"{len(a['anomalies'])} anomaly finding(s); showing the strongest "
                 f"{len(anos)}. Each is a lead requiring verification.", bullets)


def _answer_overview(a: Dict[str, Any]) -> Dict[str, Any]:
    s = a["bundle"].G
    stats_people = sum(1 for _n, d in s.nodes(data=True) if d.get("kind") == "person")
    ctrl = (a.get("controllers") or [{}])[0]
    top = a["leads"][:3]
    bullets = [
        _bullet(f"{stats_people} people, {s.number_of_edges()} links, "
                f"{a['structure']['community_count']} clusters, "
                f"{len(a['records'].get('fir', []))} FIRs."),
    ]
    if ctrl:
        bullets.append(_bullet(f"Potential network controller: {ctrl.get('entity')} "
                               f"({_fmt_inr(ctrl.get('net_inflow_inr', 0))} net in, "
                               f"no FIR).", entity=ctrl.get("entity")))
    if top:
        bullets.append(_bullet("Top leads: " + ", ".join(
            f"{l['entity']} ({l['lead_score']})" for l in top)))
    sev = {}
    for x in a["anomalies"]:
        sev[x["severity"]] = sev.get(x["severity"], 0) + 1
    bullets.append(_bullet("Anomalies: " + ", ".join(f"{v} {k.lower()}" for k, v in sev.items())))
    er = a["resolution"]["stats"]
    bullets.append(_bullet(f"Identity resolution: {er.get('candidate_clusters', 0)} "
                           f"candidate clusters, {er.get('auto_merged', 0)} auto-merged."))
    return _wrap("overview", "Case OP-SANGAM — overview",
                 "A quick brief of the case, from the current records.", bullets)


def _answer_counts(q: str, a: Dict[str, Any]) -> Dict[str, Any]:
    G = a["bundle"].G
    people = sum(1 for _n, d in G.nodes(data=True) if d.get("kind") == "person")
    table = {
        "fir": ("FIRs", len(a["records"].get("fir", []))),
        "entit": ("entities (people)", people),
        "people": ("people", people),
        "person": ("people", people),
        "link": ("links", G.number_of_edges()),
        "edge": ("links", G.number_of_edges()),
        "cluster": ("clusters", a["structure"]["community_count"]),
        "lead": ("investigative leads", len([l for l in a["leads"] if l["lead_score"] >= 25])),
        "anomal": ("anomaly findings", len(a["anomalies"])),
        "vehicle": ("vehicles", len(a["records"].get("vehicles", []))),
        "transaction": ("transactions", len(a["records"].get("bank", []))),
        "call": ("call records", len(a["records"].get("cdr", []))),
    }
    for key, (label, val) in table.items():
        if key in q:
            return _wrap("count", "Count", f"There are {val} {label} in the case.",
                         [_bullet(f"{val} {label}.")])
    return _answer_overview(a)


def _answer_help() -> Dict[str, Any]:
    return _wrap("help", "Ask PRAHARI",
                 "I answer from the case's own records — no outside AI. Try one of these:",
                 [_bullet(x) for x in EXAMPLES])


# ---------------------------------------------------------------- router
def answer(query: str, a: Dict[str, Any], context: Optional[str] = None) -> Dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return _answer_help()
    ql = q.lower()
    G = a["bundle"].G
    fuzzy: Dict[str, str] = {}
    ents = _find_entities(q, a, fuzzy)

    # one-turn memory: a pronoun (or a topic-only follow-up) refers to the last entity
    pronoun = bool(re.search(r"\b(his|her|their|its|him|he|she|they)\b", ql))
    if not ents and context and context in G and (pronoun or len(q.split()) <= 4):
        ents = [context]

    res = _route(q, ql, ents, a)
    if fuzzy:
        # the answer is about a guessed entity — say so, up front
        res["matched_via"] = "fuzzy"
        res["bullets"] = [_bullet(f"Interpreted '{typed}' as '{name}' (closest "
                                  f"known name — confirm this is who you meant).",
                                  entity=name)
                          for typed, name in fuzzy.items()] + res["bullets"]
    return res


def _route(q: str, ql: str, ents: List[str], a: Dict[str, Any]) -> Dict[str, Any]:
    date = _find_date(q, _case_year(a))
    ident_used = None
    for tok in re.findall(r"[A-Za-z]{1,3}\d[\w]*|\b9\d{9}\b|\bACC\w+\b", q):
        ident_used = tok
        break

    # --- routing (most specific first) ---
    if len(ents) >= 2 and re.search(r"connect|link|between|related|\bpath\b|route", ql):
        return _answer_connection(ents[0], ents[1], a)
    if re.search(r"controller|kingpin|mastermind|ringleader|\bhead\b", ql):
        return _answer_controller(a)
    if re.search(r"broker|middl?man|intermediar", ql):
        return _answer_broker(a)
    if re.search(r"how many|number of|count of|\bcount\b", ql):
        return _answer_counts(ql, a)
    if re.search(r"money|fund|transfer|transaction|paid|payment|financial|rupee|lakh|₹", ql):
        return _answer_money(ents[0] if ents else None, a)
    if re.search(r"\bcalls?\b|called|phoned|cdr|communicat", ql):
        return _answer_calls(ents[0] if ents else None, a)
    if re.search(r"anomal|unusual|suspicious|spike|\bflag", ql):
        return _answer_anomalies(a)
    if re.search(r"lead|investigat|priorit|who should|top suspect", ql):
        return _answer_leads(ql, a)
    if re.search(r"overview|case summary|summary of the case|brief|whole case|everything", ql):
        return _answer_overview(a)
    if date and re.search(r"happen|on |activity|move|events?|that day|\d", ql):
        return _answer_date(date, a)
    if ents and ident_used and re.search(r"own|whose|belong|registered", ql):
        return _answer_owner(ents[0], ident_used, a)
    if ents:
        return _answer_person(ents[0], a)
    if date:
        return _answer_date(date, a)
    return _answer_help()

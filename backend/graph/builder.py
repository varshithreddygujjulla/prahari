"""
builder.py — construct the entity graph from ingested records.

Preserves the original graph semantics exactly (registered phones resolve to
their subscriber, unregistered ones become their own node, bank counterparties
resolve to account holders) and adds three things the specification requires:

  * every edge is created through the evidence ledger, so it cites the exact
    source records behind it and carries a derived confidence;
  * every edge has a temporal envelope, so the graph can be filtered by time;
  * the two previously-unused sources (VAHAN vehicles, travel manifests) are
    wired in, closing a gap where the README advertised sources the code
    never read.

One deliberate design decision: community detection runs on the *interaction*
subgraph (calls, money, co-accusation, custody) rather than the full graph.
Registry attachments such as a vehicle registration are pendant nodes that say
nothing about who associates with whom, and letting them vote on cluster
boundaries would distort the result. Pendants inherit their owner's community.
"""
import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import networkx as nx

from backend import config
from backend.evidence import EvidenceLedger
from backend.ingestion import Record, load_all

# Relations that represent actual interaction between people, as opposed to a
# registry fact about one person. Only these shape community structure.
INTERACTION_RELS = {"co-accused", "calls", "money", "jailed-together",
                    "phone-linked", "co-travel"}

CORPORATE_TOKENS = ("PVT LTD", "LTD", "LLP", "TRADERS", "ENTERPRISES",
                    "EXPORTS", "IMPEX", "LOGISTICS")


def _is_corporate(name: str) -> bool:
    up = (name or "").upper()
    return any(tok in up for tok in CORPORATE_TOKENS)


@dataclass
class GraphBundle:
    """Everything downstream layers need, computed once."""
    G: nx.Graph
    ledger: EvidenceLedger
    records: Dict[str, List[Record]]
    call_times: Dict[tuple, List[str]] = field(default_factory=dict)
    call_records: Dict[tuple, List[Record]] = field(default_factory=dict)
    node_meta: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    entity_identifiers: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)


def build(records: Optional[Dict[str, List[Record]]] = None) -> GraphBundle:
    recs = records if records is not None else load_all()
    G = nx.Graph()
    ledger = EvidenceLedger()

    # ------------------------------------------------------------ registries
    phone_owner: Dict[str, str] = {}
    phone_record: Dict[str, Record] = {}
    for r in recs["phone_directory"]:
        if r.issues:            # malformed number — never let it resolve a handset
            continue
        ph = r.fields.get("phone", "").strip()
        nm = r.fields.get("registered_name", "").strip()
        if ph and nm:
            phone_owner[ph] = nm
            phone_record[ph] = r

    acct_owner: Dict[str, str] = {}
    acct_record: Dict[str, Record] = {}
    for r in recs["accounts"]:
        ac = r.fields.get("account", "").strip()
        nm = r.fields.get("holder_name", "").strip()
        if ac and nm:
            acct_owner[ac] = nm
            acct_record[ac] = r

    # identifiers held by each entity — used by entity resolution and the UI
    ident: Dict[str, Dict[str, List[str]]] = defaultdict(
        lambda: {"phones": [], "accounts": [], "vehicles": []})
    for ph, nm in phone_owner.items():
        ident[nm]["phones"].append(ph)
    for ac, nm in acct_owner.items():
        ident[nm]["accounts"].append(ac)

    def person(name: str) -> str:
        if name not in G:
            G.add_node(name, kind="corporate_entity" if _is_corporate(name) else "person")
        return name

    def resolve_phone(ph: str) -> str:
        """Registered number resolves to its subscriber; otherwise it stands
        alone as an unresolved number — we do not know who held the handset."""
        if ph in phone_owner:
            return person(phone_owner[ph])
        if ph not in G:
            G.add_node(ph, kind="unresolved_number")
        return ph

    # ------------------------------------------------------------ 1. FIRs
    for r in recs["fir"]:
        names = r.fields["names"]
        for a, b in itertools.combinations(names, 2):
            ledger.assert_link(person(a), person(b), "co-accused", [r],
                               algorithm="regex entity extraction over FIR narrative",
                               source=r.record_id, weight=3)
            G.nodes[a]["in_fir"] = True
            G.nodes[b]["in_fir"] = True
        for n in names:
            G.nodes[person(n)]["in_fir"] = True
            G.nodes[n].setdefault("fir_ids", []).append(r.record_id)
        # Phone recovered from the primary accused, per the narrative wording.
        for n in names[:1]:
            for ph in r.fields["phones"]:
                if ph in phone_owner and phone_owner[ph] != n:
                    ledger.assert_link(
                        person(n), person(phone_owner[ph]), "phone-linked",
                        [r, phone_record[ph]],
                        algorithm="handset recovered in FIR cross-referenced "
                                  "against subscriber registry",
                        uncertainty=["Recovery of a handset does not establish "
                                     "that the accused is its subscriber."],
                        weight=1)

    # ------------------------------------------------------------ 2. CDR
    call_records: Dict[tuple, List[Record]] = defaultdict(list)
    call_times: Dict[tuple, List[str]] = defaultdict(list)
    for r in recs["cdr"]:
        caller = r.fields.get("caller", "").strip()
        receiver = r.fields.get("receiver", "").strip()
        if not caller or not receiver:
            continue
        a, b = resolve_phone(caller), resolve_phone(receiver)
        if a == b:
            continue
        key = tuple(sorted((a, b)))
        call_records[key].append(r)
        if r.timestamp:
            call_times[key].append(r.timestamp)

    for (a, b), rs in call_records.items():
        unresolved = [x for x in (a, b)
                      if G.nodes[x].get("kind") == "unresolved_number"]
        unc = []
        for u in unresolved:
            unc.append(f"Subscriber identity for {u} is unresolved — the handset "
                       f"holder is not established by these records.")
        ledger.assert_link(
            a, b, "calls", rs,
            algorithm="CDR aggregation over subscriber-resolved endpoints",
            observation_count=len(rs),
            confidence_key="calls-unresolved" if unresolved else "calls",
            uncertainty=unc,
            calls=len(rs), weight=min(len(rs), 10))

    # ------------------------------------------------------------ 3. Banking
    money_records: Dict[tuple, List[Record]] = defaultdict(list)
    money_total: Dict[tuple, float] = defaultdict(float)
    for r in recs["bank"]:
        fa = r.fields.get("from_account", "").strip()
        ta = r.fields.get("to_account", "").strip()
        a = acct_owner.get(fa, fa)
        b = acct_owner.get(ta, ta)
        for x, raw in ((a, fa), (b, ta)):
            if x not in G:
                G.add_node(x, kind="corporate_entity" if _is_corporate(x)
                           else ("account" if x == raw else "person"))
        amt = float(r.fields.get("_amount", 0) or 0)
        key = tuple(sorted((a, b)))
        money_records[key].append(r)
        money_total[key] += amt
        G.nodes[b]["money_in"] = G.nodes[b].get("money_in", 0) + amt
        G.nodes[a]["money_out"] = G.nodes[a].get("money_out", 0) + amt
        G.nodes[a].setdefault("accounts", set()).add(fa)
        G.nodes[b].setdefault("accounts", set()).add(ta)

    for key, rs in money_records.items():
        a, b = key
        supporting = list(rs)
        # Include the account-registry rows that mapped the counterparties, so
        # the evidence drawer can show how an account became a person.
        for r in rs:
            for acc_field in ("from_account", "to_account"):
                ac = r.fields.get(acc_field, "").strip()
                if ac in acct_record and acct_record[ac] not in supporting:
                    supporting.append(acct_record[ac])
        ledger.assert_link(
            a, b, "money", supporting,
            algorithm="account-to-account transfers aggregated and mapped "
                      "through the account-holder registry",
            observation_count=len(rs),
            money_inr=round(money_total[key], 2),
            transfer_count=len(rs),
            weight=4)

    # Corporate entities that take money from many parties and pass it onward.
    for n, d in list(G.nodes(data=True)):
        if d.get("kind") == "corporate_entity":
            d["layering_candidate"] = (d.get("money_in", 0) > 0
                                       and d.get("money_out", 0) > 0)
            # Preserved for frontend compatibility with the existing board.
            d["kind"] = "shell_company"

    # ------------------------------------------------------------ 4. Custody
    prison_rows = recs["prison"]
    for r1, r2 in itertools.combinations(prison_rows, 2):
        f1, f2 = r1.fields, r2.fields
        if f1.get("jail") != f2.get("jail"):
            continue
        if f1.get("cell_block") != f2.get("cell_block"):
            continue
        if f1.get("to_date", "") < f2.get("from_date", "") or \
           f2.get("to_date", "") < f1.get("from_date", ""):
            continue
        ledger.assert_link(
            person(f1["prisoner_name"]), person(f2["prisoner_name"]),
            "jailed-together", [r1, r2],
            algorithm="custody roster overlap on jail + cell block + date range",
            uncertainty=[
                "Shared cell block establishes physical proximity, not association.",
                "Custody period predates the case activity window.",
            ],
            source=f'{f1["jail"]} {f1["cell_block"]}', weight=5)

    # ------------------------------------------------------------ 5. Vehicles
    # Previously ingested but never used. Registration is a strong documentary
    # link between a person and a vehicle.
    for r in recs["vehicles"]:
        vnum = r.fields.get("vehicle_number", "").strip()
        owner = r.fields.get("owner_name", "").strip()
        if not vnum or not owner:
            continue
        G.add_node(vnum, kind="vehicle",
                   vehicle_type=r.fields.get("vehicle_type", ""))
        ledger.assert_link(
            person(owner), vnum, "registered-to", [r],
            algorithm="vehicle registration registry lookup",
            uncertainty=["Registered ownership does not establish who was "
                         "operating the vehicle at any given time."],
            weight=2)
        ident[owner]["vehicles"].append(vnum)

    # ------------------------------------------------------------ 6. Travel
    # Two people on the same route on the same date. None occur in the current
    # corpus; the detector is in place for data that does contain them.
    by_leg: Dict[tuple, List[Record]] = defaultdict(list)
    for r in recs["travel"]:
        leg = (r.fields.get("from_city", ""), r.fields.get("to_city", ""),
               r.fields.get("date", ""))
        by_leg[leg].append(r)
        nm = r.fields.get("passenger_name", "").strip()
        if nm:
            G.nodes[person(nm)].setdefault("travel", []).append(r.record_id)
    for leg, rs in by_leg.items():
        if len(rs) < 2:
            continue
        for r1, r2 in itertools.combinations(rs, 2):
            n1 = r1.fields.get("passenger_name", "").strip()
            n2 = r2.fields.get("passenger_name", "").strip()
            if n1 and n2 and n1 != n2:
                ledger.assert_link(
                    person(n1), person(n2), "co-travel", [r1, r2],
                    algorithm="passenger manifest match on route and date",
                    uncertainty=["Travelling the same route on the same date "
                                 "may be coincidental."],
                    source=f"{leg[0]}→{leg[1]} {leg[2]}", weight=2)

    # ------------------------------------------------------------ materialise
    # One NetworkX edge per pair, carrying every relation observed on that pair.
    for edge in ledger.merged_edges():
        attrs = {k: v for k, v in edge.items() if k not in ("from", "to")}
        G.add_edge(edge["from"], edge["to"], **attrs)

    # sets are not JSON-serialisable; normalise
    for n, d in G.nodes(data=True):
        if isinstance(d.get("accounts"), set):
            d["accounts"] = sorted(d["accounts"])

    return GraphBundle(G=G, ledger=ledger, records=recs,
                       call_times=dict(call_times),
                       call_records=dict(call_records),
                       entity_identifiers={k: v for k, v in ident.items()})


def interaction_subgraph(G: nx.Graph) -> nx.Graph:
    """The graph restricted to edges that represent interaction between people.

    An edge qualifies if *any* of its relations is an interaction, since one
    edge can carry several.
    """
    keep = [(a, b) for a, b, d in G.edges(data=True)
            if set(d.get("rel_types") or [d.get("rel")]) & INTERACTION_RELS]
    return G.edge_subgraph(keep).copy()

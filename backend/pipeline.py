"""
pipeline.py — orchestration and caching.

Runs ingestion → graph → structure → anomalies → entity resolution → scoring,
and assembles the API payload. Results are cached against a fingerprint of the
data directory, so repeated queries are free and a rebuild only happens when
the underlying files actually change (§21).

The payload deliberately keeps the original field names (`nodes`, `edges`,
`insights`, `anomalies`, `link_predictions`, `stats`) so an older frontend
still renders, and adds the new structures alongside them.
"""
import os
from typing import Any, Dict, List, Optional

from backend import config
from backend.analytics import analyze_structure, score_leads
from backend.analytics.lead_scoring import network_controller_candidates
from backend.anomaly import detect_all
from backend.entity_resolution import resolve
from backend.graph import build, case_clock, build_events, window_bounds
from backend.graph.temporal import filter_edges, filter_events
from backend.ingestion import load_all
from backend.ingestion.loaders import BASE

_CACHE: Dict[str, Any] = {}


# ---------------------------------------------------------------- caching
def data_fingerprint() -> str:
    """Cheap change detector: names, sizes and mtimes under data/."""
    parts: List[str] = []
    for root, _dirs, files in os.walk(BASE):
        for fn in sorted(files):
            # retracted.json changes what the loaders return, so it is part of
            # the data revision; the other json files (audit, decisions) are not
            if fn.endswith((".csv", ".txt")) or fn == "retracted.json":
                p = os.path.join(root, fn)
                try:
                    st = os.stat(p)
                    parts.append(f"{fn}:{st.st_size}:{int(st.st_mtime)}")
                except OSError:
                    continue
    return "|".join(parts)


def analysis(force: bool = False) -> Dict[str, Any]:
    """The full analysis, computed once per data revision."""
    fp = data_fingerprint()
    if not force and _CACHE.get("fingerprint") == fp and "analysis" in _CACHE:
        return _CACHE["analysis"]

    records = load_all()
    bundle = build(records)
    structure = analyze_structure(bundle.G)
    clock = case_clock(records)
    anomalies = detect_all(bundle, structure, clock)
    resolution = resolve(bundle)
    leads = score_leads(bundle, structure, anomalies, resolution)
    controllers = network_controller_candidates(bundle, structure, leads)
    events = build_events(records, bundle.call_records)

    result = {
        "bundle": bundle,
        "structure": structure,
        "clock": clock,
        "anomalies": anomalies,
        "resolution": resolution,
        "leads": leads,
        "controllers": controllers,
        "events": events,
        "records": records,
    }
    # Insights are derived ONCE per data revision. Generating them inside
    # build_payload appended to the cached ledger on every request, so reverse
    # provenance grew duplicates without bound.
    result["insights"] = generate_insights(result)
    _CACHE["fingerprint"] = fp
    _CACHE["analysis"] = result
    _CACHE.pop("payload", None)
    return result


def invalidate():
    _CACHE.clear()


# ---------------------------------------------------------------- insights
def generate_insights(a: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Plain-language findings, each tied to the records behind it.

    Wording follows §25: nothing here labels a person. "Potential Network
    Controller" describes a position in the records; "kingpin" would be a
    claim about an organisation that these records cannot support.
    """
    bundle, structure = a["bundle"], a["structure"]
    G, ledger = bundle.G, bundle.ledger
    pr, bc = structure["pagerank"], structure["betweenness"]
    comm = structure["community_of"]
    out: List[Dict[str, Any]] = []

    def records_for(entity: str, limit: int = 8):
        seen, recs = set(), []
        by_id = {r.record_id: r for rs in bundle.records.values() for r in rs}
        for nbr in G.neighbors(entity):
            for rid in (G.get_edge_data(entity, nbr) or {}).get("source_records", []):
                if rid not in seen and rid in by_id:
                    seen.add(rid)
                    recs.append(by_id[rid])
                if len(recs) >= limit:
                    return recs
        return recs

    # -- potential network controller ------------------------------------
    for c in a["controllers"][:1]:
        recs = records_for(c["entity"])
        if not recs:
            continue
        out.append(ledger.assert_insight(
            "POTENTIAL_NETWORK_CONTROLLER",
            f"POTENTIAL NETWORK CONTROLLER — '{c['entity']}'",
            f"'{c['entity']}' receives ₹{c['net_inflow_inr']:,.0f} in net "
            f"consolidated transfers yet is named in no FIR narrative in this "
            f"corpus. Financially central, operationally absent from the case "
            f"record — a position worth examining, not a conclusion.",
            recs, algorithm="net inflow ranking among entities absent from FIRs",
            entities=[c["entity"]], uncertainty=c["uncertainty"]))

    # -- unresolved number bridging clusters ------------------------------
    for n, d in G.nodes(data=True):
        if d.get("kind") != "unresolved_number":
            continue
        touched = {comm.get(x) for x in G.neighbors(n)}
        if len(touched) < 2:
            continue
        top = sorted(pr, key=pr.get, reverse=True)[:5]
        leaders = [x for x in G.neighbors(n) if x in top]
        recs = records_for(n)
        if not recs:
            continue
        out.append(ledger.assert_insight(
            "POTENTIAL_BROKER",
            f"POTENTIAL BROKER — unresolved number {n}",
            f"Unresolved number {n} contacts entities in {len(touched)} "
            f"separate clusters"
            + (f", including {', '.join(leaders)}. " if leaders else ". ")
            + "No subscriber is registered to this number, so the handset "
              "holder is not established by these records.",
            recs, algorithm="cluster reach of unattributed subscriber numbers",
            entities=[n] + leaders,
            uncertainty=["Subscriber identity is unresolved; attribution of "
                         "this handset to any person is unproven."]))

    # -- influence --------------------------------------------------------
    top_pr = sorted(pr, key=pr.get, reverse=True)[:3]
    top_bc = max(bc, key=bc.get) if bc else None
    if top_pr and top_bc:
        recs = records_for(top_pr[0])
        if recs:
            out.append(ledger.assert_insight(
                "NETWORK_INFLUENCE",
                "NETWORK INFLUENCE",
                f"Highest PageRank: {', '.join(top_pr)}. Highest betweenness: "
                f"'{top_bc}' — more cross-cluster paths run through it than any "
                f"other entity, making it a high-connectivity entity in this "
                f"network.",
                recs, algorithm="PageRank (weighted) and betweenness centrality",
                entities=top_pr))

    # -- cluster structure -------------------------------------------------
    sizes: Dict[int, int] = {}
    for n, c in comm.items():
        if G.nodes[n].get("kind") == "person":
            sizes[c] = sizes.get(c, 0) + 1
    big = sorted(sizes.items(), key=lambda kv: -kv[1])[:2]
    if len(big) >= 2:
        recs = [r for r in bundle.records.get("fir", [])][:6]
        if recs:
            out.append(ledger.assert_insight(
                "CLUSTER_STRUCTURE",
                "CLUSTER STRUCTURE",
                f"Community detection separates the network into "
                f"{len(sizes)} clusters; the two largest hold {big[0][1]} and "
                f"{big[1][1]} entities. Clusters are statistical groupings of "
                f"observed interaction, not established organisations.",
                recs, algorithm="greedy modularity maximisation",
                entities=[]))

    # -- potential associations (link prediction) --------------------------
    by_id = {r.record_id: r for rs in bundle.records.values() for r in rs}
    for p in structure["link_predictions"][:2]:
        recs = [by_id[r] for r in p["source_records"][:8] if r in by_id]
        if not recs:
            continue
        out.append(ledger.assert_insight(
            "POTENTIAL_ASSOCIATION",
            f"POTENTIAL ASSOCIATION — {p['a']} and {p['b']}",
            f"{p['a']} and {p['b']} have no recorded direct contact but share "
            f"{p['shared_contacts']} common associates "
            f"({', '.join(p['via'][:3])}). A relationship may exist that these "
            f"records do not document.",
            recs, algorithm=p["algorithm"], entities=[p["a"], p["b"]],
            uncertainty=["Shared associates can arise without any direct "
                         "relationship between the two parties."]))

    # -- money trail -------------------------------------------------------
    for n, d in G.nodes(data=True):
        if d.get("kind") != "shell_company" or not d.get("layering_candidate"):
            continue
        nbrs = list(G.neighbors(n))
        recs = records_for(n)
        if not recs:
            continue
        out.append(ledger.assert_insight(
            "MONEY_TRAIL",
            f"MONEY TRAIL — '{n}'",
            f"'{n}' receives funds from {max(len(nbrs) - 1, 1)}+ parties and "
            f"forwards consolidated amounts onward — the movement pattern "
            f"associated with layering.",
            recs, algorithm="inflow/outflow analysis on corporate entities",
            entities=[n],
            uncertainty=["Consolidation of funds through a company is also "
                         "ordinary commercial behaviour."]))

    # -- top anomalies -----------------------------------------------------
    for an in a["anomalies"][:3]:
        recs = [by_id[r] for r in an["source_records"][:8] if r in by_id]
        if not recs:
            continue
        out.append(ledger.assert_insight(
            an["anomaly_type"], f"ANOMALY — {an['anomaly_type'].replace('_',' ').title()}",
            an["explanation"], recs, algorithm=an["algorithm"],
            entities=an["entities_involved"], confidence=an["confidence"]))

    return out


# ---------------------------------------------------------------- payload
def build_payload(window: str = config.DEFAULT_TIME_WINDOW,
                  start: Optional[str] = None,
                  end: Optional[str] = None,
                  force: bool = False) -> Dict[str, Any]:
    a = analysis(force=force)
    bundle, structure = a["bundle"], a["structure"]
    G = bundle.G
    pr, bc = structure["pagerank"], structure["betweenness"]
    comm = structure["community_of"]

    insights = a["insights"]
    bounds = window_bounds(window, a["clock"], start, end)

    lead_by_entity = {l["entity"]: l for l in a["leads"]}
    ident = bundle.entity_identifiers

    nodes = []
    for n, d in G.nodes(data=True):
        lead = lead_by_entity.get(n)
        ids = ident.get(n, {})
        nodes.append({
            "id": n, "label": n,
            "kind": d.get("kind", "person"),
            "pagerank": round(pr.get(n, 0), 4),
            "betweenness": round(bc.get(n, 0), 4),
            "community": comm.get(n, -1),
            "in_fir": bool(d.get("in_fir")),
            "fir_ids": d.get("fir_ids", []),
            "money_in": d.get("money_in", 0),
            "money_out": d.get("money_out", 0),
            "phones": ids.get("phones", []),
            "accounts": ids.get("accounts", []),
            "vehicles": ids.get("vehicles", []),
            "vehicle_type": d.get("vehicle_type"),
            "layering_candidate": d.get("layering_candidate", False),
            "lead_score": lead["lead_score"] if lead else 0,
            "lead_band": lead["band"] if lead else None,
        })

    all_edges = [dict(d, **{"from": u, "to": v}) for u, v, d in G.edges(data=True)]
    edges = filter_edges(all_edges, bounds)
    visible = {e["from"] for e in edges} | {e["to"] for e in edges}

    events = filter_events(a["events"], bounds)
    call_spikes = [x for x in a["anomalies"]
                   if x["anomaly_type"] == "COMMUNICATION_VOLUME_SPIKE"]

    severity_counts: Dict[str, int] = {}
    for x in a["anomalies"]:
        severity_counts[x["severity"]] = severity_counts.get(x["severity"], 0) + 1

    return {
        # -- original contract, preserved -------------------------------
        "nodes": nodes,
        "edges": edges,
        "insights": [i["headline"] + " — " + i["detail"] for i in insights],
        "anomalies": a["anomalies"],
        "link_predictions": structure["link_predictions"][:5],
        "stats": {
            "people": sum(1 for x in nodes if x["kind"] == "person"),
            "edges": len(edges),
            "communities": structure["community_count"],
            "firs_parsed": len(bundle.records.get("fir", [])),
            "edges_total": len(all_edges),
            "nodes_total": len(nodes),
            "records_ingested": sum(len(v) for v in bundle.records.values()),
            "anomalies": len(a["anomalies"]),
            "severity": severity_counts,
        },
        # -- new structures ---------------------------------------------
        "insight_records": insights,
        "call_spikes": call_spikes,
        "leads": a["leads"],
        "network_controllers": a["controllers"],
        "entity_resolution": {
            "stats": a["resolution"]["stats"],
            "matches": a["resolution"]["matches"],
            "clusters": a["resolution"]["clusters"],
            "correlations": a["resolution"]["correlations"],
            "policy": a["resolution"]["policy"],
        },
        "timeline": {
            "events": events,
            "event_types": sorted({e["type"] for e in events}),
            "clock": a["clock"],
            "window": bounds,
            "windows_available": list(config.TIME_WINDOWS),
        },
        "provenance": {
            "source_types": config.SOURCE_TYPES,
            "record_counts": {k: len(v) for k, v in bundle.records.items()},
            "visible_nodes_in_window": len(visible),
        },
        "notices": {
            "verification": config.HUMAN_VERIFICATION_NOTICE,
            "scoring": ("Investigative lead scores rank what to examine next. "
                        "They are not a determination of guilt."),
            "clock": (f"Relative time windows are anchored to the latest "
                      f"observed record ({a['clock'].get('anchor')}), not to "
                      f"the current date."),
        },
    }

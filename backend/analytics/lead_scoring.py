"""
lead_scoring.py — the INVESTIGATIVE LEAD SCORE.

What this is
------------
A triage aid. It ranks which entities an investigator should look at first,
given what the records contain. It is explicitly NOT a measure of guilt, a
criminality index, or a prediction, and nothing here should ever be presented
as one.

What makes it defensible
------------------------
Every point is attributable. A score is the sum of independent signals, each
with its own cap (config.LEAD_SCORE_CAPS), each carrying the evidence that
earned it. The API returns the breakdown alongside the total, so the answer to
"why is this 82?" is always six lines of arithmetic and their source records —
never "the model said so".

Absence of evidence scores zero rather than penalising: an entity with no
financial records is not thereby cleared, it is simply unscored on that signal.
The uncertainty list makes that visible.
"""
from collections import defaultdict
from typing import Any, Dict, List, Optional

import networkx as nx

from backend import config


def _band(score: int) -> str:
    for threshold, label in config.LEAD_SCORE_BANDS:
        if score >= threshold:
            return label
    return config.LEAD_SCORE_BANDS[-1][1]


def _norm(value: float, values: List[float]) -> float:
    """Scale a value to 0..1 against the observed maximum."""
    hi = max(values) if values else 0
    return (value / hi) if hi > 0 else 0.0


def score_leads(bundle, structure, anomalies: List[Dict[str, Any]],
                resolution: Optional[Dict[str, Any]] = None,
                limit: int = 40) -> List[Dict[str, Any]]:
    G = bundle.G
    pr = structure["pagerank"]
    bc = structure["betweenness"]
    comm = structure["community_of"]
    caps = config.LEAD_SCORE_CAPS

    persons = [n for n, d in G.nodes(data=True) if d.get("kind") == "person"]
    if not persons:
        return []

    pr_values = [pr.get(n, 0) for n in persons]
    bc_values = [bc.get(n, 0) for n in persons]

    # Index anomalies by entity so each contributes to the right lead.
    by_entity: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for a in anomalies:
        for e in a.get("entities_involved", []):
            by_entity[e].append(a)

    FINANCIAL_TYPES = {"UNUSUAL_TRANSACTION_AMOUNT", "RAPID_MONEY_MOVEMENT",
                       "STRUCTURED_TRANSACTION_PATTERN"}
    COMMS_TYPES = {"COMMUNICATION_VOLUME_SPIKE", "ENTITY_COMMUNICATION_SURGE",
                   "NEW_COMMUNICATION_RELATIONSHIP", "CONNECTIVITY_SURGE"}
    # Each anomaly type feeds exactly one factor — a new communication
    # relationship is a communication signal, not also a temporal one.
    TEMPORAL_TYPES = {"PRE_EVENT_ACTIVITY_CLUSTER"}
    LOCATION_TYPES = {"TRAVEL_FOLLOWING_LARGE_CREDIT"}

    # Entity-resolution confidence, if the resolver has run.
    er_by_entity: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for m in (resolution or {}).get("matches", []):
        er_by_entity[m["entity"]].append(m)

    leads: List[Dict[str, Any]] = []
    for n in persons:
        factors: List[Dict[str, Any]] = []
        evidence: List[str] = []
        uncertainty: List[str] = []

        anos = by_entity.get(n, [])

        def _anomaly_factor(name: str, types: set, cap: int, phrasing: str):
            hits = [a for a in anos if a["anomaly_type"] in types]
            if not hits:
                return
            # Strongest hit sets the level; additional ones add a little.
            best = max(hits, key=lambda a: config.SEVERITY_ORDER.get(a["severity"], 0))
            level = (config.SEVERITY_ORDER.get(best["severity"], 0) + 1) / 4
            pts = int(round(cap * min(1.0, level + 0.12 * (len(hits) - 1))))
            if pts <= 0:
                return
            factors.append({
                "factor": name,
                "points": pts,
                "max_points": cap,
                "reason": phrasing.format(n=len(hits),
                                          s=best["severity"].lower()),
                "anomaly_ids": [a["anomaly_id"] for a in hits],
                "source_records": sorted({r for a in hits
                                          for r in a["source_records"]})[:20],
            })
            for a in hits:
                evidence.extend(a["source_records"])

        _anomaly_factor("Financial anomaly", FINANCIAL_TYPES,
                        caps["financial_anomaly"],
                        "{n} financial anomaly finding(s), strongest rated {s}")
        _anomaly_factor("Communication anomaly", COMMS_TYPES,
                        caps["communication_anomaly"],
                        "{n} communication anomaly finding(s), strongest rated {s}")
        _anomaly_factor("Temporal correlation", TEMPORAL_TYPES,
                        caps["temporal_correlation"],
                        "{n} finding(s) correlating activity with dated events")
        _anomaly_factor("Location correlation", LOCATION_TYPES,
                        caps["location_correlation"],
                        "{n} movement finding(s) tied to financial activity")

        # -- cross-community reach ---------------------------------------
        own = comm.get(n, -1)
        bridges = []
        for nbr in G.neighbors(n):
            if G.nodes[nbr].get("kind") not in ("person", "unresolved_number",
                                                "shell_company"):
                continue
            if comm.get(nbr, -1) != own and comm.get(nbr, -1) >= 0:
                bridges.append(nbr)
        if bridges:
            reach = len({comm.get(b) for b in bridges})
            pts = int(round(min(caps["cross_community"],
                                caps["cross_community"] * min(1.0, reach / 2)
                                + 2 * (len(bridges) - 1))))
            pts = min(pts, caps["cross_community"])
            factors.append({
                "factor": "Cross-community connection",
                "points": pts, "max_points": caps["cross_community"],
                "reason": f"connected to {len(bridges)} entit(ies) across "
                          f"{reach} other cluster(s)",
                "entities": bridges[:6],
                "source_records": sorted({r for b in bridges for r in
                                          (G.get_edge_data(n, b) or {})
                                          .get("source_records", [])})[:20],
            })
            for b in bridges:
                evidence.extend((G.get_edge_data(n, b) or {}).get("source_records", []))

        # -- multi-source corroboration ----------------------------------
        stypes = set()
        for nbr in G.neighbors(n):
            stypes.update((G.get_edge_data(n, nbr) or {}).get("source_types", []))
        if len(stypes) >= 2:
            pts = min(caps["multi_source"], (len(stypes) - 1) * 4)
            factors.append({
                "factor": "Multi-source confirmation",
                "points": pts, "max_points": caps["multi_source"],
                "reason": f"relationships evidenced by {len(stypes)} independent "
                          f"source types: {', '.join(sorted(stypes))}",
                "source_types": sorted(stypes),
            })
        elif len(stypes) == 1:
            uncertainty.append(
                f"All relationships for this entity rest on a single source "
                f"type ({next(iter(stypes))}). No independent corroboration.")

        # -- network centrality ------------------------------------------
        cen = 0.6 * _norm(pr.get(n, 0), pr_values) + 0.4 * _norm(bc.get(n, 0), bc_values)
        if cen > 0.05:
            pts = int(round(caps["network_centrality"] * cen))
            if pts:
                factors.append({
                    "factor": "Network centrality",
                    "points": pts, "max_points": caps["network_centrality"],
                    "reason": f"PageRank {pr.get(n,0):.4f}, betweenness "
                              f"{bc.get(n,0):.4f} (weighted blend "
                              f"{cen:.2f} of observed maximum)",
                    "algorithm": "PageRank + betweenness, normalised to the "
                                 "observed maximum",
                })

        # -- entity-resolution confidence --------------------------------
        er = er_by_entity.get(n, [])
        strong = [m for m in er if m["confidence"] >= 55]
        if strong:
            pts = min(caps["entity_resolution"], 2 + len(strong) * 2)
            factors.append({
                "factor": "Entity resolution",
                "points": pts, "max_points": caps["entity_resolution"],
                "reason": f"{len(strong)} unresolved identity candidate(s) may "
                          f"refer to this entity — records may be under-counted",
                "candidates": [m["candidate"] for m in strong][:5],
            })
            uncertainty.append(
                "Alternate name spellings may refer to this entity; record "
                "counts could be incomplete until an investigator confirms.")

        total = sum(f["points"] for f in factors)
        total = int(max(0, min(100, total)))
        if total <= 0:
            continue

        node = G.nodes[n]
        if not node.get("in_fir"):
            uncertainty.append("Entity is not named in any FIR narrative in "
                               "this corpus.")

        leads.append({
            "entity": n,
            "lead_score": total,
            "band": _band(total),
            "factors": sorted(factors, key=lambda f: -f["points"]),
            "source_records": sorted(set(evidence))[:40],
            "uncertainty": uncertainty,
            "community": own,
            "in_fir": bool(node.get("in_fir")),
            "money_in": node.get("money_in", 0),
            "money_out": node.get("money_out", 0),
            "status": "OPEN",
            "verification_notice": config.HUMAN_VERIFICATION_NOTICE,
            "disclaimer": ("Investigative lead score is a triage aid derived "
                           "from record correlation. It is not a measure of "
                           "guilt and carries no evidentiary weight."),
        })

    leads.sort(key=lambda x: -x["lead_score"])
    return leads[:limit]


def network_controller_candidates(bundle, structure,
                                  leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Entities that are financially central but operationally absent.

    The pattern the original board called a "hidden kingpin": substantial net
    inflow, no FIR naming them. Renamed per specification §25 — the records
    support "receives money and is not charged", which is a lead worth pulling,
    not a conclusion about rank in an organisation.
    """
    G = bundle.G
    out = []
    for n, d in G.nodes(data=True):
        if d.get("kind") != "person" or d.get("in_fir"):
            continue
        net = d.get("money_in", 0) - d.get("money_out", 0)
        if net <= 0:
            continue
        lead = next((l for l in leads if l["entity"] == n), None)
        conduits = [x for x in G.neighbors(n)
                    if G.nodes[x].get("kind") == "shell_company"]
        out.append({
            "entity": n,
            "net_inflow_inr": net,
            "money_in": d.get("money_in", 0),
            "money_out": d.get("money_out", 0),
            "fir_mentions": 0,
            "via": conduits,
            "lead_score": lead["lead_score"] if lead else 0,
            "label": "Potential Network Controller",
            "basis": ("Receives consolidated transfers but appears in no FIR "
                      "narrative in this corpus."),
            "source_records": sorted({r for x in G.neighbors(n) for r in
                                      (G.get_edge_data(n, x) or {})
                                      .get("source_records", [])})[:20],
            "uncertainty": [
                "Absence from FIR narratives may reflect gaps in the corpus "
                "rather than non-involvement.",
                "Financial centrality alone does not establish control of a "
                "network.",
            ],
            "verification_notice": config.HUMAN_VERIFICATION_NOTICE,
        })
    out.sort(key=lambda x: -x["net_inflow_inr"])
    return out

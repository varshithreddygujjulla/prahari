"""
centrality.py — network structure metrics.

Carries over the original PageRank / betweenness / community / link-prediction
logic unchanged in substance, with two corrections:

  * community detection runs on the interaction subgraph, so a vehicle
    registration cannot vote on which cluster a person belongs to;
  * link predictions are emitted as evidence-backed insights, citing the
    records behind each shared associate rather than asserting a bare pair.
"""
import itertools
from typing import Any, Dict, List

import networkx as nx

from backend.graph.builder import interaction_subgraph


def analyze_structure(G: nx.Graph) -> Dict[str, Any]:
    pr = nx.pagerank(G, weight="weight")
    bc = nx.betweenness_centrality(G, weight=None)

    # Cluster on interaction only; registry pendants inherit their neighbour's
    # community afterwards.
    H = interaction_subgraph(G)
    comms = list(nx.community.greedy_modularity_communities(H, weight="weight"))
    community_of: Dict[str, int] = {}
    for i, c in enumerate(comms):
        for n in c:
            community_of[n] = i
    for n in G.nodes():
        if n in community_of:
            continue
        nbr_comms = [community_of[x] for x in G.neighbors(n)
                     if x in community_of]
        community_of[n] = nbr_comms[0] if nbr_comms else -1

    preds = predict_links(G, community_of)

    return {
        "pagerank": pr,
        "betweenness": bc,
        "community_of": community_of,
        "communities": comms,
        "community_count": len(comms),
        "link_predictions": preds,
        "algorithms": {
            "influence": "PageRank (weighted)",
            "brokerage": "betweenness centrality (unweighted)",
            "clustering": "greedy modularity maximisation on the interaction "
                          "subgraph",
            "link_prediction": "common-neighbour scoring across community "
                               "boundaries, weighted for tradecraft indicators",
        },
    }


def predict_links(G: nx.Graph, community_of: Dict[str, int]) -> List[Dict[str, Any]]:
    """Candidate undocumented relationships.

    Restricted to cross-community pairs: a missing link *inside* a cluster whose
    members already all know each other is not news. Shared unresolved numbers
    and shared corporate entities count triple — sharing a handset nobody is
    registered to is a much stronger signal than sharing a common acquaintance.
    """
    persons = [n for n, d in G.nodes(data=True) if d.get("kind") == "person"]
    preds: List[Dict[str, Any]] = []
    for a, b in itertools.combinations(persons, 2):
        if G.has_edge(a, b) or community_of.get(a) == community_of.get(b):
            continue
        shared = list(nx.common_neighbors(G, a, b))
        if not shared:
            continue
        score = 0
        weighted: List[Dict[str, Any]] = []
        for s in shared:
            kind = G.nodes[s].get("kind")
            pts = 3 if kind in ("unresolved_number", "shell_company") else 1
            score += pts
            weighted.append({"via": s, "kind": kind, "points": pts})
        if score < 2:
            continue
        # Provenance: the records behind each hop through a shared associate.
        support: List[str] = []
        for s in shared:
            for end in (a, b):
                d = G.get_edge_data(s, end) or {}
                support.extend(d.get("source_records", []))
        preds.append({
            "a": a, "b": b,
            "shared_contacts": len(shared),
            "score": score,
            "via": [w["via"] for w in weighted[:4]],
            "via_detail": weighted,
            "source_records": sorted(set(support)),
            "algorithm": "common-neighbour scoring across community boundaries",
        })
    preds.sort(key=lambda x: -x["score"])
    return preds

"""
engine.py — The brain of the system.
  1. Entity extraction from FIR narratives (regex NER — swap for spaCy in production)
  2. Graph construction (NetworkX; same schema ports to Neo4j)
  3. Network analytics: PageRank, betweenness, community detection, link prediction
  4. Anomaly detection: call-volume spikes
  5. Blockchain-style tamper-proof audit log (SHA-256 hash chain)
  6. Plain-language investigator insights
"""
import csv, os, re, json, hashlib, itertools, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime
from collections import defaultdict
import networkx as nx

BASE = os.path.join(os.path.dirname(__file__), "..", "data")
FIRS = os.path.join(BASE, "firs")

# ---------------------------------------------------------------- entity extraction
NAME_RE = re.compile(r"(?:accused|associate|named|by|consignee\.?|Co-accused|links accused to)\s+"
                     r"([A-Z][a-z]+ [A-Z][a-z]+)")
PHONE_RE = re.compile(r"\b(9\d{9})\b")

def extract_entities_from_firs():
    """Pull (person, person, fir_id) and (person, phone) links out of FIR text."""
    edges, phone_links, firs = [], [], []
    for fn in sorted(os.listdir(FIRS)):
        if not fn.endswith(".txt"):
            continue
        text = open(os.path.join(FIRS, fn)).read()
        names = list(dict.fromkeys(NAME_RE.findall(text)))  # ordered unique
        phones = PHONE_RE.findall(text)
        fir_id = fn.replace(".txt", "")
        firs.append({"id": fir_id, "names": names, "phones": phones})
        for a, b in itertools.combinations(names, 2):
            edges.append((a, b, fir_id))
        for n in names[:1]:          # phone recovered from the primary accused
            for ph in phones:
                phone_links.append((n, ph))
    return edges, phone_links, firs

# ---------------------------------------------------------------- graph build
def load_csv(name):
    with open(os.path.join(BASE, name)) as f:
        return list(csv.DictReader(f))

def build_graph():
    G = nx.Graph()
    phone_owner = {r["phone"]: r["registered_name"] for r in load_csv("phone_directory.csv")}
    acct_owner = {r["account"]: r["holder_name"] for r in load_csv("accounts.csv")}

    def person(name):
        G.add_node(name, kind="person")
        return name

    def resolve_phone(ph):
        """Registered phone -> its owner node; unregistered -> burner node."""
        if ph in phone_owner:
            return person(phone_owner[ph])
        G.add_node(ph, kind="burner_phone")
        return ph

    # 1. FIR co-accusation edges
    fir_edges, phone_links, firs = extract_entities_from_firs()
    for a, b, fir in fir_edges:
        G.add_edge(person(a), person(b), rel="co-accused", source=fir, weight=3)
        G.nodes[a]["in_fir"] = True
        G.nodes[b]["in_fir"] = True
    for n, ph in phone_links:
        if ph in phone_owner and phone_owner[ph] != n:
            G.add_edge(person(n), person(phone_owner[ph]), rel="phone-linked", weight=1)

    # 2. CDR edges (aggregate call counts)
    call_count = defaultdict(int)
    call_times = defaultdict(list)
    for r in load_csv("cdr.csv"):
        a, b = resolve_phone(r["caller"]), resolve_phone(r["receiver"])
        if a == b:
            continue
        key = tuple(sorted((a, b)))
        call_count[key] += 1
        call_times[key].append(r["timestamp"])
    for (a, b), n in call_count.items():
        G.add_edge(a, b, rel="calls", calls=n, weight=min(n, 10))

    # 3. Bank edges (graph is undirected, so keep true direction in node attrs)
    money = defaultdict(float)
    for r in load_csv("bank.csv"):
        a = acct_owner.get(r["from_account"], r["from_account"])
        b = acct_owner.get(r["to_account"], r["to_account"])
        for x in (a, b):
            if x not in G:
                G.add_node(x, kind="person" if not x.startswith("ACC") else "account")
        amt = float(r["amount_inr"])
        money[tuple(sorted((a, b)))] += amt
        G.nodes[b]["money_in"] = G.nodes[b].get("money_in", 0) + amt
        G.nodes[a]["money_out"] = G.nodes[a].get("money_out", 0) + amt
    for (a, b), amt in money.items():
        if G.has_edge(a, b):
            G[a][b]["money_inr"] = amt
            G[a][b]["weight"] = G[a][b].get("weight", 1) + 4
        else:
            G.add_edge(a, b, rel="money", money_inr=amt, weight=4)
        if "PVT LTD" in a or "PVT LTD" in b or "TRADERS" in a or "TRADERS" in b:
            G.nodes[a if "TRADERS" in a else b]["kind"] = "shell_company"

    # 4. Prison co-location (overlapping stay in the same cell block)
    rows = load_csv("prison.csv")
    for r1, r2 in itertools.combinations(rows, 2):
        if r1["jail"] == r2["jail"] and r1["cell_block"] == r2["cell_block"]:
            if not (r1["to_date"] < r2["from_date"] or r2["to_date"] < r1["from_date"]):
                G.add_edge(person(r1["prisoner_name"]), person(r2["prisoner_name"]),
                           rel="jailed-together", source=f'{r1["jail"]} {r1["cell_block"]}',
                           weight=5)
    return G, call_times, firs

# ---------------------------------------------------------------- analytics
def analyze(G):
    pr = nx.pagerank(G, weight="weight")
    bc = nx.betweenness_centrality(G, weight=None)
    comms = list(nx.community.greedy_modularity_communities(G, weight="weight"))
    community_of = {}
    for i, c in enumerate(comms):
        for n in c:
            community_of[n] = i
    # link prediction on person nodes: shared neighbours but no direct edge.
    # Cross-community pairs only — a hidden link BETWEEN gangs is the interesting one.
    # Shared burner phones / shell companies count triple (strong tradecraft signal).
    persons = [n for n, d in G.nodes(data=True) if d.get("kind") == "person"]
    preds = []
    for a, b in itertools.combinations(persons, 2):
        if G.has_edge(a, b) or community_of.get(a) == community_of.get(b):
            continue
        shared = list(nx.common_neighbors(G, a, b))
        if not shared:
            continue
        score = sum(3 if G.nodes[s].get("kind") in ("burner_phone", "shell_company")
                    else 1 for s in shared)
        if score >= 2:
            preds.append({"a": a, "b": b, "shared_contacts": len(shared),
                          "score": score, "via": shared[:4]})
    preds.sort(key=lambda x: -x["score"])
    return pr, bc, community_of, preds[:5], len(comms)

def detect_anomalies(call_times):
    """Flag pairs whose calls bunch into a short burst (spike)."""
    out = []
    for (a, b), times in call_times.items():
        if len(times) < 8:
            continue
        days = defaultdict(int)
        for t in times:
            days[t[:10]] += 1
        peak_day, peak = max(days.items(), key=lambda kv: kv[1])
        if peak >= 5:
            out.append({"pair": f"{a} ↔ {b}", "date": peak_day,
                        "calls_that_day": peak, "total_calls": len(times)})
    return sorted(out, key=lambda x: -x["calls_that_day"])

# ---------------------------------------------------------------- insights
def generate_insights(G, pr, bc, community_of, preds, anomalies):
    """Template-based briefs. In production, feed the same facts to an LLM API."""
    lines = []
    # --- hidden kingpin: big money inflow, but named in ZERO FIRs (stays invisible)
    named_in_fir = {n for n, d in G.nodes(data=True) if d.get("in_fir")}
    hidden = [(n, d.get("money_in", 0) - d.get("money_out", 0))
              for n, d in G.nodes(data=True)
              if d.get("kind") == "person" and n not in named_in_fir
              and d.get("money_in", 0) > 0]
    hidden.sort(key=lambda kv: -kv[1])
    if hidden:
        n, amt = hidden[0]
        lines.append(f"HIDDEN KINGPIN — '{n}' receives ₹{amt:,.0f} in consolidated "
                     f"transfers yet is named in ZERO FIRs. Financially central, "
                     f"operationally invisible: the profile of a network head.")
    # --- broker: unregistered burner connected to leaders of multiple communities
    ldr_pr = sorted(pr, key=pr.get, reverse=True)[:5]
    for n, d in G.nodes(data=True):
        if d.get("kind") == "burner_phone":
            comms_touched = {community_of.get(x) for x in G.neighbors(n)}
            leaders = [x for x in G.neighbors(n) if x in ldr_pr]
            if len(comms_touched) >= 2:
                lines.append(f"BROKER SIGNAL — Unregistered number {n} contacts nodes in "
                             f"{len(comms_touched)} separate clusters, including "
                             f"{', '.join(leaders) if leaders else 'cluster leaders'}. "
                             f"Classic broker burner phone.")
    top_pr = sorted(pr, key=pr.get, reverse=True)[:3]
    top_bc = max(bc, key=bc.get)
    lines.append(f"INFLUENCE — Highest PageRank: {', '.join(top_pr)}. "
                 f"Highest betweenness: '{top_bc}' — most cross-cluster paths run through it.")
    gang_sizes = defaultdict(int)
    for n, c in community_of.items():
        gang_sizes[c] += 1
    big = sorted(gang_sizes.items(), key=lambda kv: -kv[1])[:2]
    lines.append(f"GANG STRUCTURE — Community detection found {len(gang_sizes)} clusters; "
                 f"the two largest have {big[0][1]} and {big[1][1]} members — consistent "
                 f"with two organised groups operating under one financial umbrella.")
    for p in preds[:2]:
        lines.append(f"HIDDEN LINK — {p['a']} and {p['b']} have no recorded contact but share "
                     f"{p['shared_contacts']} common associates. Probable undocumented relationship.")
    shells = [n for n, d in G.nodes(data=True) if d.get("kind") == "shell_company"]
    for s in shells:
        nbrs = list(G.neighbors(s))
        lines.append(f"MONEY TRAIL — '{s}' receives funds from {len(nbrs)-1}+ parties and "
                     f"forwards consolidated amounts onward: classic layering pattern.")
    for a in anomalies[:2]:
        lines.append(f"ANOMALY — Call spike between {a['pair']}: {a['calls_that_day']} calls "
                     f"on {a['date']} (vs normal 1–2/day). Spikes often precede an operation.")
    return lines

# ---------------------------------------------------------------- blockchain audit
class AuditChain:
    """SHA-256 hash chain: each block commits to the previous one, so any
    tampering with past queries breaks every later hash. Swap the file store
    for a permissioned chain (Hyperledger Fabric) in production."""
    def __init__(self, path=os.path.join(BASE, "audit_chain.json")):
        self.path = path
        self.chain = json.load(open(path)) if os.path.exists(path) else [
            {"index": 0, "timestamp": "2026-01-01T00:00:00", "officer": "SYSTEM",
             "action": "GENESIS", "prev_hash": "0"*64,
             "hash": hashlib.sha256(b"GENESIS").hexdigest()}]

    def record(self, officer, action):
        prev = self.chain[-1]
        block = {"index": prev["index"] + 1,
                 "timestamp": datetime.now().isoformat(timespec="seconds"),
                 "officer": officer, "action": action, "prev_hash": prev["hash"]}
        payload = json.dumps(block, sort_keys=True).encode()
        block["hash"] = hashlib.sha256(payload).hexdigest()
        self.chain.append(block)
        json.dump(self.chain, open(self.path, "w"), indent=1)
        return block

    def verify(self):
        for i in range(1, len(self.chain)):
            b = dict(self.chain[i]); h = b.pop("hash")
            if hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest() != h \
               or b["prev_hash"] != self.chain[i-1]["hash"]:
                return False, i
        return True, None

# ---------------------------------------------------------------- full pipeline
def run_pipeline():
    G, call_times, firs = build_graph()
    pr, bc, community_of, preds, n_comms = analyze(G)
    anomalies = detect_anomalies(call_times)
    insights = generate_insights(G, pr, bc, community_of, preds, anomalies)
    nodes = [{"id": n, "label": n, "kind": d.get("kind", "person"),
              "pagerank": round(pr.get(n, 0), 4),
              "betweenness": round(bc.get(n, 0), 4),
              "community": community_of.get(n, -1)} for n, d in G.nodes(data=True)]
    edges = [{"from": a, "to": b, "rel": d.get("rel", ""),
              "calls": d.get("calls"), "money_inr": d.get("money_inr"),
              "source": d.get("source", "")} for a, b, d in G.edges(data=True)]
    return {"nodes": nodes, "edges": edges, "insights": insights,
            "anomalies": anomalies, "link_predictions": preds,
            "stats": {"people": sum(1 for x in nodes if x["kind"] == "person"),
                      "edges": len(edges), "communities": n_comms,
                      "firs_parsed": len(firs)}}

if __name__ == "__main__":
    result = run_pipeline()
    print(json.dumps(result["stats"], indent=2))
    print("\n--- INVESTIGATOR BRIEF ---")
    for line in result["insights"]:
        print(" •", line)

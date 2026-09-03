# 🏗 Architecture — SIH 26189

## Prototype pipeline (what runs in the demo)

```
 data/firs/*.txt   data/cdr.csv   data/bank.csv   prison/travel/vehicles.csv
        │               │              │                    │
        ▼               ▼              ▼                    ▼
 ┌───────────────────────────────────────────────────────────────┐
 │ 1. INGESTION + ENTITY EXTRACTION (backend/engine.py)          │
 │    regex-NER over FIR narratives → names, phones, relations   │
 └───────────────────────────────────────────────────────────────┘
        ▼
 ┌───────────────────────────────────────────────────────────────┐
 │ 2. GRAPH CONSTRUCTION (NetworkX)                              │
 │    nodes: person / burner_phone / shell_company / account     │
 │    edges: co-accused · calls · money · jailed-together        │
 └───────────────────────────────────────────────────────────────┘
        ▼
 ┌───────────────────────────────────────────────────────────────┐
 │ 3. ANALYTICS                                                  │
 │    PageRank (influence) · Betweenness (brokers)               │
 │    Greedy-modularity communities (gangs)                      │
 │    Cross-community link prediction (hidden ties)              │
 │    Burst detection on call timestamps (anomalies)             │
 │    Hidden-kingpin heuristic (money-in, zero FIR mentions)     │
 └───────────────────────────────────────────────────────────────┘
        ▼
 ┌──────────────────────────────┐   ┌────────────────────────────┐
 │ 4. INSIGHTS LAYER            │   │ 5. AUDIT BLOCKCHAIN        │
 │ template briefs (prototype)  │   │ SHA-256 hash chain of      │
 │ → LLM API in production      │   │ every officer query        │
 └──────────────────────────────┘   └────────────────────────────┘
        ▼
 ┌───────────────────────────────────────────────────────────────┐
 │ 6. FastAPI (backend/main.py) → vis-network dashboard          │
 │    /api/graph  /api/audit  /api/audit/tamper-demo  /api/rebuild│
 └───────────────────────────────────────────────────────────────┘
```

## Prototype → Production mapping (say this to judges)

| Prototype component | Production replacement |
|---|---|
| CSV/TXT loaders | Secure REST/queue connectors to CCTNS, telecom CDR feeds, FIU-IND |
| Regex NER | Fine-tuned IndicBERT/spaCy transformer NER (multi-lingual FIRs) |
| NetworkX in-memory graph | Neo4j cluster (same node/edge schema — drop-in) |
| Template insight strings | LLM (on-prem, air-gapped) fed the same graph facts |
| JSON hash-chain file | Permissioned Hyperledger Fabric across NCRB data centres |
| Fuzzy name matching | Aadhaar-linked identity resolution (govt-side only) |
| Single server | Kubernetes on NIC cloud (MeghRaj), role-based access control |

## Why these choices win
- **Zero licence cost** — full FOSS stack.
- **Explainable** — every insight cites its source edge (FIR no., call count, ₹).
  No black-box accusations; the AI *suggests*, officers *decide*.
- **Privacy by design** — audit chain + RBAC addresses DPDP Act 2023 concerns
  head-on; the theme (Blockchain & Cybersecurity) is structural, not bolted on.
- **Same-schema mocking** — swap data source, not code, for deployment.

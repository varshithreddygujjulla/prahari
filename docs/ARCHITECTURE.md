# Architecture — SIH 26189 PRAHARI

Everything below runs locally, from files, with no external service and no
language model. Every number a judge can see on screen is inspectable at
`GET /api/config`, and every finding cites the source records it rests on.

## What runs in the demo

```
 data/firs/*.txt   cdr.csv   bank.csv   phone_directory / accounts / vehicles
 travel.csv        prison.csv           identity_variants.csv (resolver only)
        │              │          │                 │
        ▼              ▼          ▼                 ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 1. INGESTION            backend/ingestion/loaders.py                    │
 │    every row -> Record with a stable id (FIR_003, CDR-0007, TXN-0012)   │
 │    one shared FIR extractor (FIR_NAME_RE / FIR_PHONE_RE); malformed     │
 │    registry rows are flagged and never resolve a handset                │
 │    ADD DATA intake      backend/ingestion/intake.py                     │
 │    validate -> quality-score -> conflict/duplicate check -> commit      │
 └────────────────────────────────────────────────────────────────────────┘
        ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 2. EVIDENCE LEDGER      backend/evidence/provenance.py                  │
 │    an Assertion cannot exist without supporting records (raises)        │
 │    confidence = base(relation) + corroboration + repeat, capped at 97   │
 └────────────────────────────────────────────────────────────────────────┘
        ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 3. TEMPORAL GRAPH       backend/graph/  (NetworkX)                      │
 │    nodes: person · corporate_entity · unresolved_number · vehicle       │
 │    relations: co-accused · calls · calls-unresolved · money ·           │
 │               registered-to · jailed-together · co-travel               │
 │    windows all/30d/7d/24h/custom anchored to the CASE CLOCK             │
 └────────────────────────────────────────────────────────────────────────┘
        ▼
 ┌──────────────────────────┐ ┌──────────────────────┐ ┌──────────────────┐
 │ 4a. ANALYTICS            │ │ 4b. ANOMALY ENGINE   │ │ 4c. ENTITY       │
 │ PageRank · betweenness   │ │ 10 detectors, each   │ │ RESOLUTION       │
 │ greedy-modularity        │ │ quantified against   │ │ scored candidate │
 │ clusters · link          │ │ a baseline, all in   │ │ matches, banded, │
 │ prediction · 8-factor    │ │ config.ANOMALY_CONFIG│ │ NEVER auto-merged│
 │ Investigative Lead Score │ │                      │ │                  │
 └──────────────────────────┘ └──────────────────────┘ └──────────────────┘
        ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 5. GROUNDED ASSISTANT   backend/assistant/ask.py                        │
 │    routes a question to the records (entity, date, money, vehicle,      │
 │    relationship, case summary); fuzzy name hits are labelled as such;   │
 │    every bullet cites a record id. No LLM, nothing generated.           │
 │    DECISIONS            backend/cases/decisions.py                      │
 │    VERIFIED / DISMISSED / NEEDS_REVIEW recorded per lead, identity      │
 │    match or anomaly — by a person, never by the system                  │
 └────────────────────────────────────────────────────────────────────────┘
        ▼
 ┌──────────────────────────────────┐   ┌────────────────────────────────┐
 │ 6. FastAPI  backend/api/routes.py│   │ 7. AUDIT CHAIN backend/audit/  │
 │ /api/graph  /api/timeline        │   │ SHA-256 hash chain, one block  │
 │ /api/entity/{name}[/casefile]    │◄──┤ per request, atomic writes,    │
 │ /api/leads  /api/anomalies       │   │ verify() + live tamper demo    │
 │ /api/entity-resolution           │   └────────────────────────────────┘
 │ /api/ask  /api/intake/*          │
 │ /api/decision(s)  /api/audit     │
 │ /api/evidence/{id} /api/config   │
 └──────────────────────────────────┘
        ▼
   frontend/app.html + dashboard.js  (vis-network, vendored — works offline)
   frontend/index.html               (the original corkboard, at /classic)
```

## Guarantees that are enforced in code, not prose

| Guarantee | Where | How it is enforced |
|---|---|---|
| No relationship without evidence | `evidence/provenance.py` | `Assertion` with zero records raises; tests construct one and expect the exception |
| Confidence never reaches 100 | `config.CONFIDENCE_CEILING = 97` | asserted over every edge, lead and identity match |
| Identities are never merged automatically | `entity_resolution/resolver.py` | `auto_merged` is emitted and asserted to be 0 |
| Every algorithmic finding carries the notice | `config.HUMAN_VERIFICATION_NOTICE` | attached to leads, anomalies, dossiers; asserted |
| Replaced terms never ship | `config.APPROVED_TERMS` | tests scan the API payload and every frontend file |
| Malformed input is held, never corrected | `ingestion/intake.py` | INVALID rows are previewed but not written |
| Nothing fabricated | intake + assistant | missing optional fields stay `null`; assistant answers only from records |
| Audit writes cannot fork | `audit/chain.py` | one lock around read-append-flush; temp file + `os.replace` |
| The corpus the tests use is a copy | `tests/conftest.py` | every data path is pointed at a temp copy for the session |

## The FIR extractor

One compiled regex, `FIR_NAME_RE` in `backend/ingestion/loaders.py`, is
imported by both the loader and the ADD DATA preview, so the preview shows
exactly what the board will build. Trigger words (`accused`, `associate`,
`named`, `by`, `consignee`, `co-accused`, `links accused to`) are
case-insensitive; the captured name must be two capitalised words. That
combination is what lets a sentence-initial "Accused Sunil Kumar" be captured
while ordinary prose such as "named associate" is not.

## Data lifecycle

| Action | Effect |
|---|---|
| Start server | `pipeline.analysis()` loads `data/`, builds everything, caches by a fingerprint of file names/sizes/mtimes |
| ADD DATA → Add to case | committable rows appended to the CSV / a new FIR file written; cache invalidated; audit block written |
| Investigator decision | `data/decisions.json` updated under a lock; audit block written |
| Any request | one block appended to `data/audit_chain.json` |
| `python backend/reset_demo_data.py` | restores every corpus file from `data/seed/`, removes staged files, decisions and the audit chain (`--keep-audit` to keep it) |

## Prototype → production mapping

| Prototype component | Production replacement |
|---|---|
| CSV/TXT loaders | Secure connectors to CCTNS, telecom CDR feeds, FIU-IND — same `Record` shape |
| Regex extractor | Trained NER (IndicBERT / MuRIL) for multilingual FIRs, same trigger-and-name contract |
| NetworkX in memory | Neo4j with the same node/relation schema |
| Grounded assistant (templates) | Optional on-prem model that only phrases facts the pipeline computed |
| JSON hash-chain file | Permissioned ledger (Hyperledger Fabric) across NCRB nodes, HSM-held keys |
| Self-asserted `officer` | RBAC behind an authenticating gateway (Phase 2 §15) |
| Single server | Kubernetes on NIC MeghRaj |

## Why these choices

- **Explainable by construction.** The evidence ledger is the only way to
  create an edge; `/api/evidence/{record_id}` answers "what does this record
  support?" in reverse.
- **Conservative on identity.** Names alone cannot reach the LIKELY band;
  conflicting identifiers apply −35. The dangerous error is a false merge.
- **Honest about time.** Relative windows anchor to the latest record in the
  case, and the UI says so, because the corpus is synthetic and dated 2026.
- **Zero licence cost.** FastAPI, NetworkX, vis-network, pytest — all FOSS.
- **Accountability is structural.** The audit chain records every request
  before it is served; the tamper demo runs on a copy so it can never damage
  the live chain.

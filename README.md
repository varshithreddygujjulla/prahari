# PRAHARI Evidence Board — SIH 26189
### Investigative Intelligence & Evidence Correlation Platform
**Ministry of Home Affairs · NCRB · Theme: Blockchain & Cybersecurity**

> **PHASE 1 IS IMPLEMENTED.** The backend has been refactored into modules and
> five P0 capabilities added: evidence provenance, entity resolution,
> investigative lead scoring, a temporal graph, and a configurable anomaly
> engine — plus the terminology pass and false-positive safeguards.
> **Read [docs/PHASE1.md](docs/PHASE1.md) first**; it supersedes this document
> wherever the two disagree.
>
> Sections below marked *(pre-Phase 1)* describe the original build and are kept
> for history. In particular: the backend is no longer three files, anomaly
> detection is no longer a single fixed rule, and the terms "Hidden Kingpin",
> "Prime Suspect" and "Burner Phone" have been replaced throughout
> (see PHASE1 §8).

**Quick facts after Phase 1**

| | |
|---|---|
| Backend | 8 packages + `pipeline.py`, behind a compatibility shim (`engine.py`) |
| Tests | 182 passing (`python -m pytest tests -q`), against a temporary copy of `data/` |
| Graph | 39 nodes · 78 edges · 3 clusters · 28 people |
| Records ingested | 271 across 9 sources, each with a stable ID |
| Anomaly findings | 24 (4 critical / 5 high / 14 medium / 1 low) |
| Identity candidates | 9 matches, 4 clusters, **0 auto-merged** |
| Time windows | all · 30d · 7d · 24h · custom, anchored to the case clock |
| Also | ADD DATA intake, grounded assistant (`/api/ask`, no LLM), investigator decisions, demo reset script |

---

> **For AI assistants reading this repo:** This document is intentionally comprehensive. Every file, module, data schema, API endpoint, algorithm, and design decision is documented here so you can understand and work with this codebase without needing external context.

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [Quick Start](#3-quick-start)
4. [The Hidden Crime Story (Demo Narrative)](#4-the-hidden-crime-story-demo-narrative)
5. [Backend — Deep Dive](#5-backend--deep-dive)
6. [Data Layer](#6-data-layer)
7. [Frontend — Deep Dive](#7-frontend--deep-dive)
8. [API Reference](#8-api-reference)
9. [Algorithms Used](#9-algorithms-used)
10. [Blockchain Audit Chain](#10-blockchain-audit-chain)
11. [Architecture: Prototype vs Production](#11-architecture-prototype-vs-production)
12. [Adding New Data](#12-adding-new-data)
13. [Troubleshooting](#13-troubleshooting)
14. [Team & Demo Script Summary](#14-team--demo-script-summary)

---

## 1. Project Overview

PRAHARI ("guardian/sentinel" in Hindi) is an investigative intelligence dashboard that automatically ingests raw law-enforcement data (FIR text, call records, bank transactions, prison rosters, travel logs, vehicle registrations) and builds an interactive **criminal network graph** on top of it.

The system answers the question: *"Given scattered data across multiple agencies, who is at the center of a criminal network — especially people who never appear in any FIR?"*

### Core capabilities *(pre-Phase 1 — see docs/PHASE1.md for current)*
| Capability | What it does |
|---|---|
| **NER / Entity Extraction** | Regex-based Named Entity Recognition over raw FIR text. Pulls names, phone numbers, co-accusation relationships. |
| **Graph Construction** | Builds a multi-relational NetworkX graph. Four node types, four edge types. |
| **Network Analytics** | PageRank (influence), Betweenness Centrality (brokers), Greedy Modularity Community Detection (gang clustering), Cross-community Link Prediction (hidden ties). |
| **Anomaly Detection** | Detects call-volume spikes: a burst of calls between two parties on a single day (>=5 calls vs. a baseline of 1-2/day). |
| **Hidden Kingpin Detection** | Heuristic: any person with high net money inflow who is *not* named in any FIR is flagged as a likely network head. |
| **Blockchain Audit Chain** | Every officer query is recorded in a SHA-256 hash chain. Tampering with any past block breaks all subsequent hashes. |
| **Cinematic UI** | A "detective's corkboard" dashboard (vis-network) with a boot sequence, guided investigation mode, entity dossiers, filter chips, and a live tamper test. |

---

## 2. Repository Structure

```
sih-package/               <- Root. Run ALL commands from here.
|
+-- README.md              <- This file (comprehensive)
+-- README_START_HERE.md   <- Short quickstart for demo day
+-- requirements.txt       <- Python dependencies
|
+-- backend/
|   +-- config.py          <- every threshold, weight and notice
|   +-- pipeline.py        <- orchestration + fingerprint-keyed cache
|   +-- main.py            <- FastAPI app (routes live in api/routes.py)
|   +-- engine.py          <- compatibility shim; `python backend/engine.py` self-test
|   +-- reset_demo_data.py <- restore data/ from data/seed/
|   +-- generate_data.py   <- original synthetic data generator (historical; the
|   |                         shipped corpus has since been curated by hand)
|   +-- ingestion/         <- loaders.py (stable ids, shared FIR extractor), intake.py (ADD DATA)
|   +-- evidence/          <- provenance ledger + confidence model
|   +-- graph/             <- temporal graph, windows, timeline
|   +-- entity_resolution/ <- candidate identity matching
|   +-- analytics/         <- centrality, clusters, lead scoring
|   +-- anomaly/           <- 10 detectors
|   +-- assistant/         <- grounded /api/ask
|   +-- cases/             <- investigator decisions store
|   +-- audit/             <- SHA-256 hash chain
|   +-- api/               <- HTTP routes
|
+-- frontend/
|   +-- app.html, dashboard.js  <- the dashboard (default at /)
|   +-- index.html, phase1.*    <- the original corkboard (at /classic)
|   +-- vendor/vis-network.min.js <- vendored graph library (offline)
|
+-- data/
|   +-- firs/              <- 21 synthetic FIR text files (FIR_001.txt to FIR_021.txt)
|   +-- cdr.csv            <- Call Detail Records
|   +-- bank.csv           <- Bank transactions
|   +-- prison.csv         <- Prison stay records
|   +-- travel.csv         <- Air travel records
|   +-- vehicles.csv       <- Vehicle registration
|   +-- phone_directory.csv <- Phone -> registered owner mapping (9990001111 is absent)
|   +-- accounts.csv       <- Bank account -> holder name mapping
|   +-- identity_variants.csv <- alternate spellings for the resolver (own record_id column)
|   +-- seed/              <- pristine copy of the corpus, used by reset_demo_data.py
|   +-- audit_chain.json   <- Persisted audit log (created on first request)
|   +-- decisions.json     <- investigator verdicts (created on first decision)
|
+-- tests/                 <- 182 tests
|
+-- docs/
|   +-- PHASE1.md          <- What Phase 1 changed and why
|   +-- ARCHITECTURE.md    <- System design + prototype-to-production mapping
|   +-- DEMO_SCRIPT_6_MEMBERS.md <- Line-by-line 7-minute demo script
|   +-- JUDGE_QA.md        <- 20 anticipated judge questions with answers
|
+-- ppt/
    +-- SIH_Idea_Submission.pptx
    +-- SIH_Idea_Submission.pdf
    +-- make_ppt.js        <- Script that generated the PPT
```

---

## 3. Quick Start

### Prerequisites
- Python 3.10+ (must be on PATH)
- Internet connection for first page load (vis-network + Google Fonts from CDN)

### Install & Run
```bash
# From inside the sih-package/ directory:
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload
```

Open **http://localhost:8000** in Chrome.

### Alternative port
```bash
python -m uvicorn backend.main:app --port 8080 --reload
```

### Terminal-only self-test (no server needed)
```bash
python backend/engine.py
# Prints stats + full investigator brief in the terminal
```

### Reset the demo corpus
```bash
python backend/reset_demo_data.py
# Restores data/ from data/seed/; removes rows/FIRs added via ADD DATA,
# staged files, decisions and the audit chain. Stop the server first.
```

`generate_data.py` is the original generator and is kept for history. The
shipped corpus has been curated since (identity variants, registry fixes), so
regenerating would produce a different dataset — use the reset script instead.

---

## 4. The Hidden Crime Story (Demo Narrative)

> **This is the story the graph will surface, live, during the demo.**

The synthetic datasets encode a real criminal network structure. The system uncovers it automatically.

### The Characters

| Person / Entity | Role | In FIRs? | Key detail |
|---|---|---|---|
| **Vikram Rathore** | **Hidden Kingpin** | NEVER | Receives Rs.7 lakh via shell company. Flies to Dubai day after payout. |
| **Ramesh Yadav** | Gang A Leader (Delhi drugs) | Yes | Phone: 9811000002. Bank: ACC9002. Jailed in Tihar Block-4 (2022). |
| **Salim Qureshi** | Gang B Leader (Mumbai smuggling) | Yes | Phone: 9822000001. Bank: ACC8001. Also jailed in Tihar Block-4 (overlapping dates). |
| **9990001111** | Broker Burner Phone | Unregistered | Calls both gang leaders AND the kingpin. Never registered, so it appears as a yellow sticky-note node. |
| **OM TRADERS PVT LTD** | Shell Company | N/A | Receives money from both gang leaders, forwards Rs.7 lakh to Vikram. |
| Gang A members (6) | Delhi street dealers | Yes | Sunil Kumar, Deepak Singh, Ajay Verma, Mohit Sharma, Rakesh Gupta, Pawan Mishra |
| Gang B members (4) | Mumbai smugglers | Yes | Irfan Shaikh, Anwar Khan, Javed Ansari, Faisal Sayyed |
| Noise population (15) | Innocent civilians | Some | Added to make the graph realistic; don't form meaningful clusters |

### The 6 Reveals (in order during demo)
1. **Two gangs** — Community detection separates Delhi (blue) from Mumbai (green).
2. **Broker burner** — Unregistered number `9990001111` has edges to both gang leaders. Betweenness centrality flags it.
3. **Money trail** — Street dealers -> Ramesh -> OM TRADERS -> Vikram Rathore.
4. **Hidden kingpin** — Vikram has the highest net money inflow yet zero FIR mentions. The system flags him in 1 second.
5. **Jail origin link** — Ramesh and Salim were in Tihar Block-4 at the same time (May-Nov 2022). That's how the inter-gang connection formed.
6. **Anomaly spike** — 48 hours before the (fictional) Mundra Port seizure (Mar 20), call volume between the gangs spikes 8x.

---

## 5. Backend — Deep Dive *(pre-Phase 1 layout; see docs/PHASE1.md §2)*

### `engine.py`

**File:** `backend/engine.py` | **268 lines** | **No external ML dependencies**

This is the entire analytical brain. It runs in 6 clearly-commented stages:

#### Stage 1 — Entity Extraction (`extract_entities_from_firs`)
- Reads every `.txt` file from `data/firs/`
- **Regex patterns:**
  - `NAME_RE`: Matches names following trigger words like `accused`, `associate`, `named`, `by`, `consignee`, `Co-accused`, `links accused to`. Expects `Firstname Lastname` (capital first letters).
  - `PHONE_RE`: Matches 10-digit numbers starting with `9` (`\b(9\d{9})\b`).
- Returns:
  - `edges`: List of `(person_A, person_B, fir_id)` — every pair of co-accused in each FIR.
  - `phone_links`: `(primary_accused, phone_number)` pairs.
  - `firs`: Metadata list for stats.

#### Stage 2 — Graph Construction (`build_graph`)
Returns `(G, call_times, firs)` where `G` is an undirected `networkx.Graph`.

**Node types** (stored in `node["kind"]`):

| `kind` value | Meaning | Visual in UI |
|---|---|---|
| `person` | A human entity (named in FIR, CDR, bank, or prison) | Polaroid photo card |
| `burner_phone` | Unregistered phone number (not in phone_directory.csv) | Yellow sticky note |
| `shell_company` | Entity whose name contains "PVT LTD" or "TRADERS" | Manila evidence tag |
| `account` | Bank account with no named holder | Plain card |

**Edge types** (stored in `edge["rel"]`):

| `rel` value | Source | Visual in UI | Weight |
|---|---|---|---|
| `co-accused` | FIR text | Solid red string | 3 |
| `phone-linked` | CDR + phone directory | Solid red string | 1 |
| `calls` | CDR (cdr.csv) | Solid red string | min(call_count, 10) |
| `money` | bank.csv | Amber twine | 4 |
| `jailed-together` | prison.csv (overlap detection) | Dashed purple | 5 |

**Graph build logic:**
1. FIR edges: every `combinations(names, 2)` pair in a FIR gets a `co-accused` edge.
2. Phone resolution: if a phone in CDR is in `phone_directory.csv`, it resolves to the registered owner node. If not, a `burner_phone` node is created with the raw number as ID.
3. CDR edges: aggregated call counts per `(caller, receiver)` pair. Stored in `edge["calls"]`.
4. Bank edges: aggregated money flows. Shell companies detected by name substring. Stored in `edge["money_inr"]`.
5. Prison overlap: pairwise comparison of all prison records. Overlap = same jail + same cell block + date ranges intersect. Adds `jailed-together` edge.

#### Stage 3 — Analytics (`analyze`)
- **PageRank** (`nx.pagerank`, weight=`"weight"`): Measures overall influence. Higher = more central.
- **Betweenness Centrality** (`nx.betweenness_centrality`, weight=None): Measures brokerage. Higher = more paths pass through this node.
- **Community Detection** (`nx.community.greedy_modularity_communities`, weight=`"weight"`): Groups nodes into clusters (gangs). Returns a list of frozensets.
- **Link Prediction**: Cross-community pairs only. Common-neighbour scoring. Neighbours that are `burner_phone` or `shell_company` score 3x (shared covert infrastructure is a stronger signal). Threshold: score >= 2. Returns top 5 predictions.

#### Stage 4 — Anomaly Detection (`detect_anomalies`)
- Only considers pairs with >= 8 total calls.
- Groups calls by day (`timestamp[:10]`).
- Flags any pair where a single day has >= 5 calls (the "spike").
- Returns sorted by `calls_that_day` descending.

#### Stage 5 — Insight Generation (`generate_insights`)
Template-based plain-language briefs. In production, the same data would be fed to an on-prem LLM API. Current templates generate:
- **HIDDEN KINGPIN** — Identifies the person with highest net money inflow (money_in - money_out) who is not named in any FIR.
- **BROKER SIGNAL** — Identifies burner phones connected to nodes in >= 2 communities.
- **INFLUENCE** — Top 3 PageRank, top 1 betweenness centrality.
- **GANG STRUCTURE** — Number of communities and sizes of the two largest.
- **HIDDEN LINK** — Top 2 link prediction results.
- **MONEY TRAIL** — For each shell company, lists how many parties funnel money through it.
- **ANOMALY** — Top 2 call spikes with dates and counts.

#### Stage 6 — Full Pipeline (`run_pipeline`)
Calls all stages in order. Returns a single JSON-serializable dict:
```json
{
  "nodes": [...],
  "edges": [...],
  "insights": ["HIDDEN KINGPIN — 'Vikram Rathore' receives Rs.700000 ..."],
  "anomalies": [{"pair": "Ramesh Yadav <-> 9990001111", "date": "2026-03-18", "calls_that_day": 11, "total_calls": 24}],
  "link_predictions": [{"a": "Ramesh Yadav", "b": "Salim Qureshi", "shared_contacts": 2, "score": 6, "via": ["9990001111", "OM TRADERS PVT LTD"]}],
  "stats": {"people": 28, "edges": 67, "communities": 4, "firs_parsed": 21}
}
```
This result is **cached** in memory after the first call (`_cache` in `main.py`). Use `/api/rebuild` to force a refresh.

---

### `main.py`

**File:** `backend/main.py` | **56 lines**

A minimal FastAPI application with four routes:

| Route | Method | Description |
|---|---|---|
| `/` | GET | Serves `frontend/index.html` |
| `/api/graph` | GET | Returns full analyzed graph. Accepts `?officer=Officer-101`. Every call is recorded to audit chain. Result is cached. |
| `/api/rebuild` | GET | Clears cache, re-runs pipeline. Use after adding new FIR files. |
| `/api/audit` | GET | Returns audit chain verification status and last 25 blocks. |
| `/api/audit/tamper-demo` | GET | Demo only. Corrupts block 1 in memory, verifies chain breaks, restores. |

**CORS:** Wildcard (`*`) — intentional for hackathon; restrict in production.

---

### `generate_data.py`

**File:** `backend/generate_data.py` | **207 lines**

Creates all synthetic datasets. Run only if you want to reset:
```bash
python backend/generate_data.py
```

**Fixed seed:** `random.seed(26189)` — the SIH problem ID. Output is 100% reproducible.

**Key engineered facts baked into the data:**
- Ramesh Yadav (Tihar Block-4, 2022-02-10 to 2022-11-30) overlaps with Salim Qureshi (2022-05-01 to 2023-01-15) -> creates `jailed-together` edge.
- Burner `9990001111` calls Gang A leader (x6), Gang B leader (x6), and Kingpin (x9).
- Call spike: 11 calls from Gang A leader to burner on March 18, 13 from burner to Gang B leader on March 18 — 48h before fictional March 20 Mundra seizure.
- Money trail: ACC9002 (Ramesh) -> ACC7777 (OM TRADERS) Rs.7.75 lakh; ACC8001 (Salim) -> ACC7777 Rs.5.1 lakh; ACC7777 -> ACC9001 (Vikram) Rs.7 lakh.
- Vikram Rathore flies Delhi -> Dubai on March 19 (day after payout).

---

## 6. Data Layer

All data lives in `data/`. The engine reads directly from disk via `csv.DictReader`.

### `data/firs/FIR_NNN.txt` format
```
FIRST INFORMATION REPORT
FIR No: 001/2026
Police Station: Delhi
Date: 05-01-2026
Sections: NDPS Act 8/20
NARRATIVE:
Accused Ramesh Yadav was apprehended near Seelampur in possession of 250g contraband.
During interrogation accused named associate Sunil Kumar.
Mobile number 9811000002 recovered from accused.
```
The NER regex requires trigger words: `accused`, `associate`, `named`, `by`, `consignee`, `Co-accused`, `links accused to`. Names must be `Firstname Lastname` (both words capitalized).

### `data/cdr.csv` columns
```
caller, receiver, timestamp, duration_sec, tower_id
9811000002, 9811000003, 2026-03-01 08:23, 342, TWR415
```
Phone numbers, not names. Engine resolves via `phone_directory.csv`.

### `data/bank.csv` columns
```
from_account, to_account, amount_inr, date
ACC9003, ACC9002, 65000, 2026-03-03
```
Account IDs, not names. Resolved via `accounts.csv`.

### `data/phone_directory.csv` columns
```
phone, registered_name
9811000001, Vikram Rathore
```
`9990001111` is deliberately absent — it therefore appears as an `unresolved_number`
node. A `phone` that is not a 10-digit Indian mobile number (first digit 6–9)
is flagged on load and ignored by the graph builder and the resolver.

### `data/accounts.csv` columns
```
account, holder_name
ACC9001, Vikram Rathore
ACC7777, OM TRADERS PVT LTD
```

### `data/prison.csv` columns
```
prisoner_name, jail, cell_block, from_date, to_date
Ramesh Yadav, Tihar Jail, Block-4, 2022-02-10, 2022-11-30
```

### `data/audit_chain.json`
A JSON array of blocks:
```json
{
  "index": 1,
  "timestamp": "2026-09-03T10:30:00",
  "officer": "Officer-101",
  "action": "QUERY: full network graph + insights",
  "prev_hash": "<sha256 of previous block>",
  "hash": "<sha256 of this block minus the hash field>"
}
```
Block 0 is the genesis block with `prev_hash: "0" * 64`.

---

## 7. Frontend — Deep Dive

**File:** `frontend/index.html` | **716 lines** | **Zero build step — pure HTML/CSS/JS**

### Libraries (CDN)
- **vis-network v9.1.9** (`unpkg.com`) — Interactive network graph rendering
- **Google Fonts** — Special Elite (typewriter), Caveat (handwriting), IBM Plex Mono (mono)

### Design Language
The UI is a detective's corkboard:
- **Background:** Cork-textured radial gradient (`#C29A66` to `#8F6C40`) with SVG noise overlay and spotlight lamps.
- **Node styles by type:**
  - `person` -> Polaroid photo card (cream background, typewriter font)
  - `burner_phone` -> Yellow sticky note
  - `shell_company` -> Manila evidence tag
- **Edge styles by type:**
  - `co-accused` / `calls` -> Solid red string
  - `money` -> Amber twine
  - `jailed-together` -> Dashed purple

### UI Sections
| Element | Function |
|---|---|
| `#boot` | Full-screen cover shown on load. Shows typewriter ingestion log. Fades out when data ready. |
| `header` | Brand, case number, live stats, search box, filter chips, action buttons |
| `#graph` | The vis-network canvas (fills viewport minus header/footer) |
| `#notepad` (left panel) | Detective's notepad. AI insights typed with typewriter effect. |
| `#casefile` (right panel) | Manila case file. Entity dossier when a node is clicked. |
| `#chainstrip` (bottom) | Blockchain strip. Shows last 5 audit blocks. Turns red/BROKEN during tamper test. |

### Key Interactive Features
- **Boot sequence:** Loads -> calls `/api/graph` -> shows typewriter log -> fades to graph.
- **Crack the Case:** 6-step guided cinematic investigation. Each step highlights specific nodes, dims others, flies camera, types findings.
- **Node click -> Entity Dossier:** Shows PageRank, betweenness, community ID, and all evidence edges with source citations.
- **Filter chips:** Toggle edge type visibility. "Money only" isolates the financial trail.
- **Search (press `/`):** Type a name, Enter -> camera flies to that node.
- **Tamper Test:** Calls `/api/audit/tamper-demo`. Chain strip turns red. Auto-restores after 3 seconds.

---

## 8. API Reference *(pre-Phase 1; 12 endpoints now — see docs/PHASE1.md §9)*

**Base URL:** `http://localhost:8000`

### `GET /api/graph?officer=Officer-101`
Returns the full analyzed graph (cached after first call).
- `nodes`: `[{id, label, kind, pagerank, betweenness, community}]`
- `edges`: `[{from, to, rel, calls, money_inr, source}]`
- `insights`: `[string]`
- `anomalies`: `[{pair, date, calls_that_day, total_calls}]`
- `link_predictions`: `[{a, b, shared_contacts, score, via}]`
- `stats`: `{people, edges, communities, firs_parsed}`

### `GET /api/rebuild?officer=Officer-101`
Clears cache, re-runs pipeline.
- Returns: `{status: "rebuilt", stats: {...}}`

### `GET /api/audit`
- Returns: `{chain_valid: bool, tampered_block: int|null, blocks: [...]}`

### `GET /api/audit/tamper-demo`
Demo only. Corrupts block 1, verifies, restores.
- Returns: `{demo, chain_valid_after_tampering, first_broken_block, conclusion, chain_valid_after_restore}`

---

## 9. Algorithms Used

### PageRank
- `networkx.pagerank(G, weight="weight")`
- Measures overall *influence*. A node scores high if it is connected to many other high-scoring nodes.
- Edge weights amplify the effect.

### Betweenness Centrality
- `networkx.betweenness_centrality(G, weight=None)`
- Fraction of all shortest paths passing through a node. High = structural *broker*.
- `weight=None` because we want structural brokerage, not just proximity.

### Greedy Modularity Community Detection
- `networkx.community.greedy_modularity_communities(G, weight="weight")`
- Maximizes modularity (ratio of within-cluster edges vs. random expectation).
- Finds "gangs". Each node gets a `community` integer ID.

### Link Prediction (Custom)
- Cross-community pairs only. Common-neighbour scoring.
- Burner phone or shell company as shared neighbour -> 3x score (shared covert infrastructure is a stronger signal).
- Threshold: score >= 2. Returns top 5.

### Anomaly Detection (Burst Detection)
- Per-pair call-volume spike detection.
- Flag if any single day has >= 5 calls for a pair with >= 8 total calls.

### Hidden Kingpin Heuristic
- For every person NOT in any FIR: compute `money_in - money_out`.
- Highest positive net inflow + zero FIR mentions = kingpin pattern.

---

## 10. Blockchain Audit Chain

**Class:** `AuditChain` in `backend/engine.py`

### How it works
Each query:
1. Creates a block: `{index, timestamp, officer, action, prev_hash}`
2. JSON-serializes (sorted keys) and SHA-256 hashes it.
3. Stores hash in block as `hash`.
4. Persists to `data/audit_chain.json`.

### Verification
Re-compute each block's hash from fields and check:
1. Computed hash matches stored `hash`.
2. Block's `prev_hash` matches previous block's `hash`.

`verify()` returns `(True, None)` or `(False, broken_block_index)`.

### Production upgrade
Replace JSON file with Hyperledger Fabric across NCRB data centres. Each node holds a replica; consensus prevents single-admin history rewriting.

---

## 11. Architecture: Prototype vs Production

| Prototype component | Production replacement |
|---|---|
| CSV / TXT file loaders | Secure REST/queue connectors to CCTNS, telecom CDR feeds, FIU-IND |
| Regex NER | Fine-tuned IndicBERT / spaCy NER (12+ languages) |
| NetworkX in-memory graph | Neo4j cluster (same node/edge schema — drop-in) |
| Template insight strings | On-prem, air-gapped LLM |
| JSON hash-chain file | Permissioned Hyperledger Fabric |
| Single FastAPI server | Kubernetes on NIC MeghRaj cloud, RBAC |

**Why this design wins:**
- **Zero licence cost** — full open-source stack.
- **Explainable** — every insight cites its source (FIR number, Rs. amount, call count).
- **Privacy by design** — audit chain + RBAC addresses DPDP Act 2023 concerns structurally.
- **Same-schema mocking** — swap data *source*, not *code*, for deployment.

---

## 12. Adding New Data

### Through the UI (preferred)
**＋ Add Data** → pick a source → paste JSON / CSV or raw FIR text →
**Validate & preview** → **Add to case**. Malformed values are held, conflicts
with existing holders are flagged, duplicates are detected, and the graph
rebuilds with an audit block. `python backend/reset_demo_data.py` undoes it all.

### Add new FIRs by file
1. Drop a `.txt` into `data/firs/` following the FIR format (Section 6).
2. Names must follow a trigger word (case-insensitive) in `Firstname Lastname` format.
3. Hit `http://localhost:8000/api/rebuild`.

### Add CDR rows
Edit `data/cdr.csv`. Format: `caller_phone, receiver_phone, YYYY-MM-DD HH:MM, duration_sec, tower_id`

### Add people to phone directory
Edit `data/phone_directory.csv`: `phone, registered_name`. Absent phones appear as unresolved-number nodes; invalid phones are flagged and ignored.

### Add bank transactions
Edit `data/bank.csv`: `from_account, to_account, amount_inr, date`. Accounts must exist in `data/accounts.csv`.

---

## 13. Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: backend` | Run `uvicorn` from inside `sih-package/`, not from inside `backend/`. |
| Port 8000 busy | `python -m uvicorn backend.main:app --port 8080` |
| Graph blank / vis-network error | Offline — CDN didn't load. Download `vis-network.min.js` locally and update `<script src>` in `index.html`. |
| Fonts look wrong | Same CDN issue — cosmetic only, demo still works. |
| `pip` not found | Use `pip3` or reinstall Python 3.10+ with "Add to PATH" ticked. |
| Graph unchanged after adding data | Call `/api/rebuild` to clear the cache. |
| `UnicodeEncodeError` on Windows | Run in Windows Terminal (not CMD). Engine already calls `sys.stdout.reconfigure(encoding="utf-8")`. |

---

## 14. Team & Demo Script Summary

The demo is designed for a **6-member team** with a 7-minute slot:

| # | Role | Speaks about |
|---|---|---|
| M1 | Team Lead / Opener | Problem statement, closing, Q&A routing |
| M2 | Driver | Operates laptop; presses **Next** at each cue |
| M3 | Data & NLP Engineer | Ingestion, entity extraction, FIR parsing |
| M4 | Graph Scientist | PageRank, community detection, link prediction, anomaly |
| M5 | Blockchain & Security | Audit chain, tamper test, DPDP Act compliance |
| M6 | Product & Impact | Deployment path, cost, NATGRID analogy |

**Full script:** `docs/DEMO_SCRIPT_6_MEMBERS.md`
**Judge Q&A prep (20 questions):** `docs/JUDGE_QA.md`
**System design:** `docs/ARCHITECTURE.md`

### Critical demo driver timings (M2)
- **Reload the page** at start so judges see the boot sequence.
- Click **Crack the Case** after M3 finishes.
- Press **Next** when M4 says: "two gangs", "broker", "OM Traders", "zero FIRs" (TARGET LOCKED stamp slams here), "Tihar", "spike".
- Click **Tamper Test** when M5 says "We just simulated...".
- After Exit, click **Vikram Rathore's node** if judges ask for proof.

### Backup plan (if WiFi fails)
```bash
python backend/engine.py
# Prints full stats + investigator brief. Narrate from terminal.
```

---

*Built for Smart India Hackathon 2026 — Problem 26189*
*Stack: Python · FastAPI · NetworkX · vis-network · SHA-256 Blockchain*

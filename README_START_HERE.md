# SIH 26189 — PRAHARI
## Investigative Intelligence & Evidence Correlation Platform
### Ministry of Home Affairs · NCRB · Theme: Blockchain & Cybersecurity

**Read this file first. Setup takes about five minutes.**

---

## What's in this package

```
sih-package/
├── README_START_HERE.md         ← you are here
├── README.md                    ← comprehensive reference (data schemas, API, algorithms)
├── requirements.txt             ← Python dependencies
├── backend/
│   ├── config.py                ← every threshold, weight and notice, in one file
│   ├── pipeline.py              ← orchestration + fingerprint-keyed caching
│   ├── main.py                  ← FastAPI app
│   ├── engine.py                ← compatibility shim / terminal self-test
│   ├── reset_demo_data.py       ← restore data/ to the shipped corpus
│   ├── ingestion/               ← loaders (stable ids) + the ADD DATA intake pipeline
│   ├── evidence/                ← provenance ledger + confidence model
│   ├── graph/                   ← temporal graph, windows, timeline
│   ├── entity_resolution/       ← candidate identity matching (never auto-merged)
│   ├── analytics/               ← centrality, clusters, Investigative Lead Score
│   ├── anomaly/                 ← 10 configurable detectors
│   ├── assistant/               ← grounded question answering over the records
│   ├── cases/                   ← investigator decisions store
│   ├── audit/                   ← SHA-256 hash chain
│   └── api/                     ← HTTP routes
├── frontend/
│   ├── app.html + dashboard.js  ← the dashboard (default at /)
│   ├── index.html               ← the original corkboard (at /classic)
│   └── vendor/vis-network.min.js← graph library, vendored — no CDN needed
├── data/                        ← 21 FIRs + CSVs; data/seed/ is the pristine copy
├── tests/                       ← 182 tests, run against a temporary copy of data/
└── docs/
    ├── PHASE1.md                ← what Phase 1 changed and why
    ├── DEMO_SCRIPT_6_MEMBERS.md ← who says what, with the driver's cue sheet
    ├── ARCHITECTURE.md          ← pipeline, guarantees, production path
    └── JUDGE_QA.md              ← 20 likely judge questions with answers
```

## Setup (once, on the demo laptop)

1. Open a terminal **inside** the `sih-package` folder.
2. Install Python 3.10+ if needed (tick "Add to PATH" on Windows).
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the server:
   ```bash
   python -m uvicorn backend.main:app
   ```
5. Open **http://localhost:8000** in Chrome.

Only Google Fonts come from the internet; without them the board still works.

### Run the tests

```bash
python -m pytest tests -q
```

Expect **182 passed** in about two seconds. The suite runs against a
temporary copy of `data/`, so it never changes the shipped corpus. It covers
the adversarial identity cases, the no-evidence-no-edge guarantee, tamper
detection, temporal windows, the intake validator, the assistant, the reset
script, terminology, and the HTTP contract end to end.

### Reset before a demo

```bash
python backend/reset_demo_data.py
```

Stop the server first. This restores every corpus file from `data/seed/`,
removes rows and FIRs added through ADD DATA, staged files, recorded decisions
and the audit chain (add `--keep-audit` to keep it; `--dry-run` to preview).
Start the server again afterwards.

## The dashboard — what each control does

| Control | What it does |
|---|---|
| **⦿ Crack the Case** | Six guided steps: two clusters → the broker → follow the money → potential network controller → shared custody → the anomaly. Press **Next ▶** on each speaker's cue. |
| **Click any node** | Entity dossier: identifiers, every relationship with its confidence and source records, lead score breakdown, identity candidates, anomalies, and the FIR case file. |
| **Click any string** | Evidence drawer: which records, which algorithm, and the confidence arithmetic. |
| **Window** (All / 30d / 7d / 24h) | Narrows relationships to those observed in the window. Anchored to the latest record in the case, and labelled as such. |
| **Leads** | Investigative Lead Score, ranked, with all eight factors. Record VERIFIED / DISMISSED / NEEDS_REVIEW on each. |
| **Entity Search** | Search by name, phone, vehicle or account; identity candidates with reasons; auto-merged is always 0. |
| **Timeline** | 96 dated events on the case clock: FIRs, daily call activity, transactions, travel, custody. |
| **Chat bubble** | Ask a question in plain words — every bullet cites a record id. Try the examples it offers. |
| **＋ Add Data** | Paste JSON / CSV / raw FIR text → **Validate & preview** → **Add to case**. Bad values are held, conflicts flagged, nothing corrected silently. |
| **🔒 Tamper Test** | Edits an audit block on a copy; the chain reports itself broken and the live chain stays valid. |
| **Audit** | The hash chain, filterable by officer and action. |
| **Generate Report** | A printable brief of the current findings, all cited. |

Map & Location is a Phase 2 placeholder and says so.

## The demo story

The records contain a network the system surfaces live, with sources:

1. **Three clusters.** Community detection separates the network; the two most central figures lead the two largest clusters.
2. **An unresolved number** contacts entities in both clusters. No subscriber is registered to it, and the system says the holder is not established.
3. **Money converges** on a corporate entity from several parties and moves on.
4. **It exits to Vikram Rathore**, named in zero FIRs — flagged as a Potential Network Controller for review, with the uncertainty stated.
5. **The two leaders overlapped in custody** in 2022 — proximity, not association, and four years before the case window.
6. **A communication spike**, measured against that pair's own median day.
7. **Tamper Test** shows the audit chain catching an edit.

Every step names its evidence. Nothing on screen claims guilt.

## Terminal self-test

```bash
python backend/engine.py
```

Prints stats, findings, leads and the brief. If this works, everything works.

## Troubleshooting

| Problem | Fix |
|---|---|
| `pip` not found | Use `pip3`, or reinstall Python with "Add to PATH" ticked |
| Port 8000 busy | `python -m uvicorn backend.main:app --port 8080` |
| `ModuleNotFoundError: backend` | Run from the `sih-package` folder, not from `backend/` |
| Board unchanged after editing files in `data/` | Open http://localhost:8000/api/rebuild, or restart the server |
| Laptop has leftover rows / decisions | Stop the server, run `python backend/reset_demo_data.py`, start again |
| Fonts look plain | Google Fonts did not load; cosmetic only |

## Team roles → `docs/DEMO_SCRIPT_6_MEMBERS.md`
## Judge questions → `docs/JUDGE_QA.md`

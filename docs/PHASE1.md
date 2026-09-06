# PRAHARI Phase 1 — Evidence, Identity, Time, Anomalies, Leads

Phase 1 implements the **P0** block of the development specification:
evidence provenance, entity resolution, investigative lead scoring, the
temporal graph, and the advanced anomaly engine — plus the terminology pass
(§25) and false-positive safeguards (§14), which are cross-cutting and apply to
everything P0 produces.

Everything is synthetic. Nothing here performs surveillance, interception, or
access to private accounts, and no output determines guilt.

---

## 1. What changed, in one table

| Area | Before | After |
|---|---|---|
| Backend layout | 3 files, one 267-line module | 8 packages behind a compatibility shim |
| Edge evidence | none | every edge cites its source records + derived confidence |
| Time | no timestamps anywhere | every edge has a temporal envelope; 4 windows + custom |
| Anomalies | 1 fixed rule (`>=5 calls/day`) | 10 configurable detectors, severity + baselines |
| Identity | exact string equality | scored candidate matching, clustering, never auto-merged |
| Lead ranking | none | 8-factor explainable score |
| `travel.csv`, `vehicles.csv` | **read by nothing** | ingested, on the graph, on the timeline |
| FIR `Date:` | parsed, discarded | drives the timeline and pre-event correlation |
| Tests | none | 182 tests, run against a temporary copy of `data/` |

---

## 2. Architecture

```
backend/
  config.py              every threshold, weight and notice in one file
  pipeline.py            orchestration + fingerprint-keyed caching
  engine.py              compatibility shim (run_pipeline, AuditChain, build_graph)
  ingestion/             file formats -> Record objects with stable IDs
  evidence/              provenance ledger + the confidence model
  graph/                 temporal graph construction, windows, timeline
  entity_resolution/     candidate identity matching
  analytics/             centrality, communities, link prediction, lead scoring
  anomaly/               the configurable detector suite
  audit/                 SHA-256 hash chain
  api/                   FastAPI routes
  assistant/             grounded question answering over the records
  cases/                 investigator decisions store
  reset_demo_data.py     restore data/ from data/seed/
frontend/
  app.html + dashboard.js  the dashboard (default at /)
  index.html               the original corkboard (kept, at /classic)
  phase1.css/.js           window picker, timeline, leads, identity, evidence drawer
tests/                   182 tests
```

The old entry points still work. `python -m backend.engine` prints stats, the
brief, findings and leads; `from backend.engine import run_pipeline, AuditChain`
resolves as before.

### Data flow

```
data/*.csv, data/firs/*.txt
   |
   v  ingestion/   assigns CDR-0007, TXN-0012, FIR_003 ... parses every date
Record objects
   |
   v  graph/       every edge created through the evidence ledger
NetworkX graph  ──> evidence/  derives confidence, refuses unsupported claims
   |
   +--> analytics/          PageRank, betweenness, clusters, link prediction
   +--> anomaly/            10 detectors, each citing records
   +--> entity_resolution/  candidate identities, never merged
   |
   v  analytics/lead_scoring
INVESTIGATIVE LEAD SCORE (explainable, capped, evidence-linked)
   |
   v  pipeline.build_payload  -> api/  -> frontend
```

---

## 3. Evidence provenance (§8)

**The guarantee is structural, not editorial.** An `Assertion` cannot be
constructed without at least one supporting `Record`; `EvidenceLedger` refuses
unsupported links and insights. "Never allow the AI to generate an unsupported
relationship" is therefore enforced by the type, not by convention.

```python
>>> Assertion(subject="A", obj="B", rel="calls", records=[], algorithm="guess")
UnsupportedAssertionError: assertion A --calls--> B has no supporting records
```

Every edge carries `source_records`, `evidence[]`, `algorithm`,
`confidence_breakdown`, `uncertainty[]` and the verification notice.

### The confidence model

Confidence is derived, never hand-written:

```
confidence = base(relation type)
           + 8 per additional independent SOURCE TYPE   (max 16)
           + log₃(observations) × 2                     (max 6)
           capped at 97, floored at 5
```

| Relation | Base | Why |
|---|---|---|
| `money` | 90 | explicit account-to-account record |
| `registered-to` | 88 | registry document |
| `co-accused` | 85 | both named in one FIR narrative |
| `calls` | 80 | both endpoints registered subscribers |
| `phone-linked` | 75 | registry ties handset to person |
| `calls-unresolved` | 60 | one endpoint unattributed — holder unknown |
| `jailed-together` | 55 | proximity in a cell block, not association |
| `co-travel` | 50 | same route and date could be coincidence |

Corroboration counts *distinct source types*, not record count: forty CDR rows
for one pair are one kind of evidence seen forty times. **Nothing ever reaches
100%** — correlated records cannot establish certainty.

Worked example, `Ramesh Yadav ↔ Sunil Kumar`:

```
+90   observation method   money — base for this evidence type
+16   corroboration        5 source types: ACCOUNT_REGISTRY, COMMUNICATION_METADATA,
                           FINANCIAL, FIR, SUBSCRIBER_REGISTRY
+2.8  repeat observation   8 observations (log-scaled, capped)
-11.8 ceiling applied      capped at 97%
────
 97%
```

### A real bug this surfaced

The original builder used `G.add_edge()` for each relation, so a pair connected
by *both* a transfer and a call history silently lost one — `add_edge`
overwrites. **11 of 69 pairs were affected.** Edges now carry `relations[]` with
every relation, its own evidence and its own confidence, plus `rel_types[]`.
Board filters match on any relation, so a link that is both a call and a
transfer appears under both chips.

---

## 4. Entity resolution (§2)

### Method

1. Build an identity profile per observed name across all sources.
2. Block candidates by phonetic surname (Soundex) or shared identifier.
3. Score positive evidence (name form, shared identifiers) against negative
   evidence (identifiers that disagree).
4. Band the result and recommend an action. **Never merge.**

### Why identifiers outrank names

"Ramesh Yadav" and "Ramesh Yadava" are one character apart — and so are two
unrelated people in any city of ten million. A shared phone number is evidence
about the world; a shared surname is evidence about the language. Name signals
alone cannot reach the LIKELY band, and conflicting identifiers apply **−35**.

### Test corpus

`data/identity_variants.csv` supplies the messy inputs the clean synthetic data
lacks. It is consumed **only** by the resolver — never by the graph builder — so
the board's node and edge counts are unchanged by its presence
(`test_identity_variants_do_not_reach_the_graph`).

### Results on the adversarial cases (§26)

| Case | Pair | Score | Decision |
|---|---|---|---|
| A — spelling variants | `Ramesh Yadav` ~ `Ramesh Yadhav` | 97 | LIKELY_SAME |
| A — abbreviation | `Vikram Rathore` ~ `V. Rathore` | 97 | LIKELY_SAME |
| A — case variant | `Ramesh Yadav` ~ `RAMESH YADAV` | 80 | LIKELY_SAME |
| **B — different people** | `Ramesh Yadav` ~ `Ramesh Yadava` | **12** | UNLIKELY_SAME |
| **B — different people** | `Amit Patel` ~ `Amit Patil` | **10** | UNLIKELY_SAME |
| **C — reassigned phone** | `Naveen Kaul` ~ `Pooja Mehra` | **12** | UNLIKELY_SAME |
| **D — vehicle used by non-owner** | `Ramesh Yadav` ~ `Deepak Singh` | **7** | UNLIKELY_SAME |

Case B is the important one: 96% name similarity *and* a phonetic match, and the
system still refuses, because the identifiers conflict.

Cases C and D share an identifier with no name support. Rather than merging,
the resolver applies **−18** and states the alternative explanation: *"consistent
with the identifier being reassigned to a different holder."*

Four candidate clusters are produced. No decoy appears in any of them.
`auto_merged` is `0` and is asserted to stay `0`.

---

## 5. Temporal graph (§3)

### The case clock

The corpus runs January–March 2026. Anchoring "last 7 days" to the wall clock
would return an **empty graph**. Relative windows are therefore anchored to the
**latest observed record** (`2026-03-31T19:00`), and the UI states this in
words: *"anchored to latest record 2026-03-31 (not today's date)"*.

| Window | Edges visible |
|---|---|
| All | 78 |
| 30d | 62 |
| 7d | 17 |

Registry facts (vehicle registration, subscriber registry) have no event date
and are marked `timeless` — they survive every window, because dropping a
vehicle's owner for lack of a registration date would be a bug, not a filter.

Custody records are from 2021–2023 and correctly fall out of a 30-day view.
**The default window is "All", so the walkthrough's custody step still works.**

Switching windows swaps only the edge set — node positions, roles, lead scores
and identity candidates stay anchored to the full record set, so narrowing the
view never silently changes who the system considers central.

### Timeline

96 events: 35 transactions, 23 daily call aggregates, 21 FIRs, 8 custody spans,
8 travel legs, 1 registration group. Calls are aggregated per day — 118
individual dots would bury the transfers and travel legs that matter.

---

## 6. Anomaly detection (§6)

Ten detectors, all driven by `config.ANOMALY_CONFIG`, all switchable.

| Detector | Method |
|---|---|
| `COMMUNICATION_VOLUME_SPIKE` | peak day vs that pair's median active day |
| `ENTITY_COMMUNICATION_SURGE` | entity's peak day vs its own median |
| `NEW_COMMUNICATION_RELATIONSHIP` | first contact late in the window |
| `CONNECTIVITY_SURGE` | several new contacts late in the window |
| `CROSS_COMMUNITY_COMMUNICATION` | sustained contact bridging clusters |
| `UNUSUAL_TRANSACTION_AMOUNT` | median + MAD outlier detection |
| `RAPID_MONEY_MOVEMENT` | inflow/outflow ratio with temporal lag |
| `STRUCTURED_TRANSACTION_PATTERN` | beneficiary fan-in, amount similarity |
| `TRAVEL_FOLLOWING_LARGE_CREDIT` | travel manifests joined to large credits |
| `PRE_EVENT_ACTIVITY_CLUSTER` | activity density before a dated FIR |

**Robust statistics throughout.** Amount outliers use median + median absolute
deviation, not mean + standard deviation: a single ₹7,00,000 transfer would drag
a mean-based threshold far enough to hide itself.

**Every explanation quantifies against a baseline.** Not "suspicious activity"
but:

> Communication volume between 9990001111 and Salim Qureshi reached 9 calls on
> 2026-03-18 — 4.5× this pair's median active day of 2. Observed across 24
> calls in total.

Current output: **24 findings — 4 CRITICAL, 5 HIGH, 14 MEDIUM, 1 LOW.**

Two calibration decisions worth recording:

- **Severity thresholds.** At the default MAD multiplier, 9 of 35 transfers
  rated CRITICAL, which makes the rating meaningless. Detection now begins at
  the consolidation tier (₹55k–85k) and only the payout tier (₹350k–700k)
  reaches CRITICAL.
- **The communication window.** Comms detectors originally inherited the corpus
  window, which starts at the **2021 custody records** — so every call in March
  2026 counted as "late", producing 18 spurious connectivity surges. Comms
  detectors now use the CDR window. Findings fell from 54 to 27, and to 24
  once the FIR extractor captured the primary accused (below): the three
  findings that vanished were built on mis-attributed handsets.

Detectors that could not be built on this corpus, and why:

- **Location convergence via cell towers** — `tower_id` is near-unique (113
  distinct values across 118 rows); only one tower/day pair has more than one
  caller. A detector would never fire. This needs the Phase 2 GPS feed.
- **Co-travel edges** — implemented, but no two passengers share a route and
  date in the current corpus, so it yields nothing today.

---

## 7. Investigative lead score (§7)

A **triage aid** that ranks what to examine next. Not a criminality index, not a
prediction, and it carries no evidentiary weight — asserted in tests.

Eight capped factors summing to 100:

| Factor | Cap |
|---|---|
| Financial anomaly | 18 |
| Cross-community connection | 16 |
| Communication anomaly | 14 |
| Temporal correlation | 12 |
| Location correlation | 12 |
| Multi-source confirmation | 12 |
| Network centrality | 10 |
| Entity resolution | 6 |

No single factor can carry a lead (asserted: every cap ≤ 20). Every point is
attributable, and the factor points are asserted to sum exactly to the score.

```
Ramesh Yadav — 67/100 · REVIEW
  +18  Financial anomaly          10 findings, strongest rated critical
  +12  Cross-community connection connected to 3 entities across 1 other cluster
  +12  Multi-source confirmation  7 independent source types
  +10  Network centrality         PageRank 0.1102, betweenness 0.1171
   +9  Communication anomaly      2 findings, strongest rated medium
   +6  Entity resolution          3 unresolved identity candidates
```

Absence of evidence scores zero rather than penalising — an entity with no
financial records is not thereby cleared, and the uncertainty list says so.

### "Potential Network Controller"

The pattern the original board called a *hidden kingpin*: substantial net inflow,
named in no FIR. The records support *"receives money and is not charged"* —
which is a lead worth pulling, not a conclusion about rank in an organisation.
Renamed per §25, and shipped with its own uncertainty list:

- absence from FIR narratives may reflect gaps in the corpus, not non-involvement
- financial centrality alone does not establish control of a network

---

## 8. Terminology and false-positive safety (§14, §25)

| Removed | Now |
|---|---|
| Hidden Kingpin | Potential Network Controller |
| Prime Suspect | Investigative Lead |
| Burner phone | Unresolved Number |
| Shell company (label) | Corporate Entity |
| Criminal / gang cluster | Cluster (statistical grouping) |
| Person / suspect | Person / entity |

Enforced by tests over the API payload *and* the shipped frontend, and by a
banned-word list applied to every anomaly explanation and lead band.

Three unsupported claims in the walkthrough were corrected:

1. **Step 4** stamped **Ramesh Yadav** "named in ZERO FIRs" with a hardcoded
   ₹7,00,000 — but he appears in FIR_007 and FIR_008. Those facts belong to
   Vikram Rathore. The frontend picked by betweenness, which finds an
   *already-charged* leader — the opposite of a hidden one. Now derived by the
   same rule the backend uses, with the figure computed from the data.
2. **Step 6** claimed the call spike fell *"48 hours before the Mundra
   seizure"*. FIR_021 (the only record mentioning Mundra Port) is dated
   09-03-2026; the spike is 18–19 March — **nine days after**, and FIR_021 is a
   fraud complaint, not a seizure. Replaced with the measured ratio.
3. **Step 5** asserted "the criminal alliance was forged inside prison". Now:
   shared custody establishes proximity, not association — and it predates the
   case window by four years.

---

## 8a. UI refinement pass

Applied after the first Phase 1 build, from a measured audit of the right rail.

**The rail budget.** Filters (136px) plus the legend card (122px) consumed 46% of
the rail before any content showed; the active panel got 241px.

| Block | Before | After |
|---|---|---|
| Filter chips | 136px, 3 ragged rows | 92px, 3×2 grid |
| Board legend card | 122px | **removed** |
| Active panel | 241px | 454–669px (viewport-dependent) |

**Where the legend went.** Its eight rows were two different things. The four
*string* rows duplicated the filter chips, which already carry colour and a
glyph — so they are simply gone. The four *node* rows (person, unresolved
number, corporate entity, investigative lead — plus vehicle, which the old
legend lacked) now sit in the Profile panel's default "How to use this board"
view: the first thing a judge sees, and zero cost once a profile is open.
Nodes also carry a hover title naming their type.

**Two chips had no colour.** `registered-to` and `phone-linked` had no `.on`
background rule and rendered as if disabled. Fixed, and the board's strings
now follow one grammar that the chips state exactly: **solid** interaction,
**dotted** registry attachment, **dashed** shared custody. Co-accused strings
were drawing brown while both the chip and the old legend said blue.

**The timeline was unreadable.** A single linear axis over 2021–2026 put 8
custody records on the left and crushed 87 case events into a sliver on the
right, with month labels overprinting each other ("20262026-2026-03"). It now
uses a **broken axis**: the range splits at its single largest gap when that
gap is both >40% of the span *and* ≥120 days, each segment stays linear
inside itself, and the break is drawn (`//`) and labelled ("prior history ·
2021-01 → 2023-03", "case window · 2026-01 → 2026-03"). Narrow windows (7d,
24h) never meet the absolute threshold and render one continuous axis. Events
sit in three lanes (documents / communication / money & movement) so same-day
records do not stack on a pixel, and tick labels are placed only when they
have 46px of room. The layout re-runs on window resize.

**A latent bug this surfaced.** `phase1.css` was linked *before* the inline
`<style>`, so its equal-specificity overrides (`#graph` inset, `#rail`/`#intel`
bottom) never applied — the rails had been sliding under the timeline strip
since Phase 1 shipped. The link now follows the inline stylesheet, with a
comment saying why.

**Density.** Leads below 25 fold behind one expander line (19 of 28 in the
current data). Identity matches show their three strongest reasons inline,
with negative reasons always kept — they are the ones that stop a false merge.

## 8b. Data intake — the ADD DATA system

An ingestion pipeline and an in-board **Add Data** modal, built to the input
specification. Header button → pick a source → paste JSON, paste/upload CSV, or
raw FIR text → **Validate & preview** → **Add to case**.

**Guarantees, enforced in code not prose** ([intake.py](../backend/ingestion/intake.py)):

- A missing *optional* field never rejects a record — it becomes `null` and the
  row is marked PARTIAL and kept.
- Nothing is fabricated; the raw submitted value is preserved beside the parsed one.
- A *malformed* value (bad date, non-numeric amount, out-of-range coordinate) is
  marked INVALID, held back, and never silently corrected or written.
- Conflicts (a phone/account/vehicle already tied to a different holder) are
  flagged for review, never overwritten. Duplicates are detected.
- Every record gets a source and a proposed id; every row carries a quality
  block (completeness %, VALID/PARTIAL/INVALID, HIGH/MEDIUM/LOW).

**Flow:** `preview` validates and conflict-checks without writing; `commit`
appends only committable rows to the store, then rebuilds the graph and writes
an audit block. Conflicting rows are held unless the reviewer ticks "add anyway".

**Sources wired to the graph:** FIR (raw text), CDR, Bank, Account, Phone,
Vehicle, Travel, Prison — CSV column aliases and explicit mapping both supported.

**Staged (validated + stored, not yet on the board):** CCTV/ANPR, GPS, Social
OSINT. They accept and persist per the spec, but need the Phase 2 map/OSINT
views to render — faking a view for them would violate the spec's own
never-invent rule.

**Endpoints:** `GET /api/intake/schema`, `POST /api/intake/preview`,
`POST /api/intake/commit`. CORS now allows POST from the named localhost origins;
the body is length-bounded and the format is enumerated.

**The extractor is one object, and it now reads the whole sentence.**
`FIR_NAME_RE` lives in `loaders.py` and is imported by the intake preview, so
the two cannot drift (`test_intake_and_loader_share_one_fir_regex` asserts
identity, not equality). Its trigger words are case-insensitive while the
captured name stays "Capitalised Two Words". Before this, a sentence-initial
"Accused Sunil Kumar … named associate Deepak Singh" yielded only *Deepak
Singh* — so the handset "recovered from accused" was attributed to the
associate, and 13 FIRs produced a `phone-linked` edge to the wrong person
instead of a `co-accused` edge between the right two. The fix turned those 13
edges into co-accused edges over the same pairs; 28 people / 69 interaction
edges / 3 clusters did not move, and no `phone-linked` edge remains on the
shipped corpus.

**Registry hygiene.** `phone_directory.csv` carried an account id
(`ACC7777`) in its phone column. The row is gone, the loader now flags any
phone that is not a 10-digit Indian mobile number, and both the graph builder
and the resolver skip flagged rows — a malformed registry row can never assign
a handset. `identity_variants.csv` keeps its own `record_id` column
(IDV-A1 …) because the docs refer to variants by those ids.

**Demo reset.** `python backend/reset_demo_data.py` restores every corpus
file from `data/seed/`, removes rows and FIRs added through ADD DATA, staged
files, decisions and the audit chain (`--keep-audit`, `--dry-run`,
`--snapshot` to re-seed).

## 9. API

| Endpoint | Purpose |
|---|---|
| `GET /api/graph` | full payload; `window`, `start`, `end` |
| `GET /api/ask?q=` | grounded answer from the records; `context` carries the last entity |
| `GET /api/intake/schema` · `POST /api/intake/preview` · `POST /api/intake/commit` | the ADD DATA pipeline |
| `GET /api/decisions` · `POST /api/decision` | investigator verdicts on leads, identity matches, anomalies |
| `GET /api/entity/{name}/casefile` | FIR bullets and dated moves for one entity |
| `GET`/`POST /api/rebuild` | re-ingest `data/` |
| `GET /api/timeline` | events; `window`, `event_type` |
| `GET /api/evidence/{record_id}` | one record + everything it supports (reverse provenance) |
| `GET /api/relationship?a=&b=` | the evidence drawer for one link |
| `GET /api/entity/{name}` | dossier: identifiers, relationships, lead, identity candidates |
| `GET /api/leads` | ranked leads; `min_score`, `limit` |
| `GET /api/anomalies` | findings; `severity`, `anomaly_type` |
| `GET /api/entity-resolution` | matches, clusters, correlations |
| `GET /api/audit` | chain state; filter by `officer`, `action_type`, `case_id` |
| `GET /api/audit/tamper-demo` | tamper-detection demonstration |
| `GET /api/config` | **every threshold behind every finding** |
| `GET /healthz` | liveness |

`/api/config` is deliberate: any number that influences a finding is
inspectable at runtime, so "why 82?" is always answerable.

**Security (§23, prototype scope).** CORS restricted to named localhost origins
(was `*`) and to `GET`; inputs constrained at the signature — enumerated
windows, regex-checked officer and record IDs, bounded lengths, `ge`/`le` on
numerics. Audit writes are atomic (temp file + `os.replace`).

---

## 10. Test results

**182 passed, 0 failed** (`python -m pytest tests -q`, ~1.6s). The suite
runs against a temporary copy of `data/` (an autouse fixture in
`conftest.py` repoints every store path), so commits, decisions and audit
blocks written by tests never touch the shipped corpus.

| File | Tests | Covers |
|---|---|---|
| `test_entity_resolution.py` | 18 | §26 Cases A–D, no-auto-merge policy, primitives |
| `test_graph_and_temporal.py` | 24 | ingestion, IDs, structure, windows, timeline |
| `test_anomaly_and_scoring.py` | 23 | detectors, calibration, lead scoring, terminology |
| `test_provenance.py` | 19 | the unsupported-assertion guarantee, confidence model |
| `test_audit_and_api.py` | 21 | tamper/delete/reorder detection, payload, terminology, case file |
| `test_http_api.py` | 21 | every endpoint over HTTP: validation codes, CORS, isolation proof |
| `test_intake.py` | 19 | validators, aliases, duplicates, conflicts, FIR text, staged commits |
| `test_assistant.py` | 19 | routing, fuzzy interpretation, citations, no fabrication |
| `test_data_integrity.py` | 12 | shared extractor, registry validation, record ids, reset script |
| `test_decisions.py` | 6 | decision store, corrupt-store refusal, audit mapping |

Regression guards pin the numbers the demo narrative rests on: 28 people,
69 interaction edges, 3 clusters.

---

## 11. Known limitations

- **Extraction is regex-based.** Names must match `Firstname Lastname` after a
  trigger word (trigger words are case-insensitive). A production system needs
  a trained NER model; the FIR corpus is written to suit the pattern.
- **Communities are not ground truth.** Greedy modularity on 30 nodes is
  sensitive to weights; clusters are statistical groupings, labelled as such.
- **`travel.csv` yields no co-travel edges** — no two passengers share a route
  and date. The detector exists but is silent on this corpus.
- **Tower-based location analysis is not viable here** (see §6).
- **Lead scores are not calibrated against outcomes.** No ground truth exists
  for synthetic data, so the weights are reasoned, not fitted. They should be
  validated against closed cases before any real use.
- **Entity resolution has no transitive guarantee.** Clusters link only through
  pairs scoring ≥ 55, which is deliberately conservative: it can leave a true
  variant out, and that is the safer error.
- **The audit chain is local and unsigned.** It detects tampering; it does not
  prevent it. Production needs a permissioned ledger and HSM-held keys.
- **No authentication.** The `officer` parameter is self-asserted. RBAC is §15,
  scheduled for Phase 2.

---

## 12. What Phase 1 does not include

Deferred by the specification's own priority order:

- **P1** — simulated location intelligence and the map (§4), geo-fencing (§5),
  multi-hop exploration (§9), path finder (§10), case management (§13),
  data-quality engine (§1)
- **P2** — synthetic OSINT (§11), network evolution animation (§12), the
  investigator dashboard (§17), RBAC demo (§15)
- **P3** — further performance work, the production-architecture document
  (§23), extended testing

The module layout already reserves the seams: `geospatial/`, `osint/`,
`cases/`, `auth/` and `validation/` are the packages Phase 2 adds, and the
ingestion layer is the only code that knows about file formats, so repointing
it at a queue or graph database does not touch analytics.

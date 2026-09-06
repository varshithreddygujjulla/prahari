# Judge Q&A Prep — 20 likely questions

Answer with what the software does. Where a capability is a production plan,
say so. Never describe an output as a finding of guilt.

**1. Where does your data come from?**
Fully synthetic, generated with a fixed seed, matching the shapes of CCTNS
FIRs, telecom CDRs, FIU-IND transaction reports and the subscriber, account
and vehicle registries. 271 records across 9 sources, each with a stable id
that the UI cites. In deployment the loaders become connectors; the `Record`
shape and everything downstream stay the same.

**2. Why not real data?**
Real case data is legally restricted, and rightly so. The schemas mirror the
real ones so integration is a connector change, not a rewrite.

**3. How is blockchain actually used — is it just a buzzword?**
It solves one concrete problem: accountability for access. Every request is a
block in a SHA-256 hash chain written *before* the response is served. Editing,
deleting or reordering any past block breaks verification — we demo it live
on a copy of the chain. Production: a permissioned ledger across NCRB nodes with
HSM-held keys, so no single administrator can rewrite history.

**4. Can this falsely accuse innocent people?**
It does not accuse. Every output is labelled an investigative lead that
requires human verification, every relationship cites its source records, and
no confidence ever reaches 100 — the ceiling is 97 in `config.py`. The lead
score is a triage aid whose eight factors are capped and attributable; absence
of evidence scores zero rather than penalising. Investigators record VERIFIED,
DISMISSED or NEEDS_REVIEW on each lead, and that decision is audited.

**5. Privacy / DPDP Act 2023?**
Purpose limitation and accountability are structural: every access is logged
immutably, communication data is metadata only (never content), and nothing
leaves the machine — there is no external API call anywhere in the prototype.
Production adds role-based access behind an authenticating gateway; the
`officer` field is self-asserted today and we say so.

**6. Scalability — this is 30 people; real data is millions.**
NetworkX is the prototype engine; the node/relation schema ports to Neo4j,
where PageRank and community detection run in the graph data science library.
Ingestion parallelises per district. The evidence ledger and the confidence
model are pure functions over records and do not change.

**7. Hindi / regional-language FIRs?**
The prototype extractor is a regex with a stated contract: a trigger word
followed by a capitalised two-word name. Production swaps in a trained NER
model (IndicBERT / MuRIL) behind the same contract, so the preview-equals-board
guarantee survives the swap.

**8. How do you find someone who is in no FIR?**
The Potential Network Controller heuristic: substantial net money inflow with
zero FIR mentions. In the demo that is Vikram Rathore, ₹7,00,000 in. The
dossier ships with its own uncertainty list — absence from FIRs may reflect a
gap in the corpus, and financial centrality alone does not establish control.
That is why it is a lead, not a finding.

**9. What is your anomaly detection?**
Ten configurable detectors, each quantified against a baseline: per-pair call
spikes versus that pair's median active day, entity surges, new and
cross-cluster relationships, transaction outliers by median + MAD (robust to
the very outliers being hunted), rapid pass-through, structured fan-in, travel
after a large credit, and activity clustering before a dated FIR. 24 findings
on this corpus, 4 critical. Every threshold is at `/api/config`.

**10. Do you use an LLM? What about hallucination?**
No model at all in the prototype. The assistant is a grounded query router:
it resolves the entity, date or identifier you asked about, reads the records,
and returns bullets that each cite a record id. If it has to interpret a
misspelt name it says "Interpreted X as Y". A production model would only
phrase facts the pipeline has already computed.

**11. Difference from i2 Analyst's Notebook / Palantir?**
Those are licensed, foreign, and analyst-driven. This is open source, ingests
Indian FIR text directly, enforces evidence provenance in the type system,
refuses automatic identity merges, and audits every access by construction.

**12. How does entity resolution work, and can it merge two different people?**
Profiles per observed name; candidates blocked by phonetic surname or a shared
identifier; positive evidence (name form, shared phone/account/vehicle) scored
against negative evidence (identifiers that conflict, −35). Names alone cannot
reach the LIKELY band. "Ramesh Yadav" and "Ramesh Yadava" score 12 — kept
apart — because their identifiers disagree. Auto-merged is zero and a test
asserts it stays zero; a person confirms each match.

**13. What if offenders stop using phones and banks?**
The graph is source-agnostic: any dated relationship becomes an edge with the
same provenance. Custody rosters, travel manifests and vehicle registries are
already ingested; CCTV/ANPR, GPS and social records validate and are stored
today and get their views in Phase 2.

**14. Deployment cost?**
FOSS end to end — FastAPI, NetworkX, vis-network, pytest. Cost is compute on
NIC cloud plus integration engineering; no per-seat licences.

**15. Security of the system itself?**
CORS restricted to named origins, inputs constrained at the API signature
(enumerated windows, pattern-checked ids, bounded lengths), atomic audit
writes under a lock, and no outbound calls. Air-gapped deployment is viable
because nothing depends on the internet except optional web fonts.

**16. Can it work in real time?**
Ingestion is incremental: ADD DATA validates, previews, commits and rebuilds
in one round trip, and `/api/rebuild` re-ingests the folder. The analysis is
cached on a fingerprint of the data files, so unchanged data costs nothing.

**17. Who are the users?**
District cyber cells, SP-level investigators, state CID and NCRB analysts. No
data-science training: paste or upload → preview → add to case → read the
cited dossier.

**18. What did each team member build?**
Answer honestly per your split — ingestion and intake, evidence ledger and
graph, analytics and anomalies, audit chain, frontend, tests and docs. Decide
before judging.

**19. What is next after the hackathon?**
Pilot on one district's anonymised historical data; measure time-to-lead
against manual work; validate lead-score weights against closed cases (they
are reasoned, not fitted — we say so); then Neo4j and a trained NER model.

**20. Show me the code for X.**
`backend/config.py` for any number; `backend/evidence/provenance.py` for the
no-evidence-no-edge guarantee; `backend/ingestion/intake.py` for validation;
`backend/audit/chain.py` for the chain. 182 tests in `tests/` run in under two
seconds against a temporary copy of the data. Practise opening these fast.

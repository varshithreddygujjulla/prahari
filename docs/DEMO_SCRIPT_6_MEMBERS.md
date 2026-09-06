# 6-Member Demo Script — SIH 26189 PRAHARI
**~7 minutes of talk + Q&A. Rehearse at least three full runs on the venue laptop.**

Every sentence below is something the software actually shows. Do not add
claims the screen does not support: the system surfaces *leads with evidence*,
it does not name offenders, and every confidence is below 100.

## Before the slot (M2, 10 minutes before)

```bash
python backend/reset_demo_data.py          # pristine corpus, fresh audit chain
python -m uvicorn backend.main:app         # from inside sih-package/
```

Open http://localhost:8000, wait for the board, and leave the tab open. The
graph library is vendored, so only Google Fonts need internet.

## Role assignment

| # | Role | Owns |
|---|------|------|
| M1 | **Team lead / opener** | Problem statement, closing, routes judge questions |
| M2 | **Driver** | Laptop; presses **Next ▶** exactly on each speaker's cue |
| M3 | **Data & ingestion** | Record ids, ADD DATA, the FIR extractor |
| M4 | **Graph & analytics** | Clusters, lead score, anomalies, entity resolution |
| M5 | **Audit & security** | Hash chain, tamper test, DPDP Act framing |
| M6 | **Product & deployment** | Production path, cost, who uses it |

---

## MINUTE 0–1 · M1 (opening, while the board is on screen)

> "Problem 26189 asks how an investigator connects an FIR in Delhi, call
> records at a telecom, and a bank trail in Mumbai — today that is done by
> hand, across weeks. PRAHARI ingests those records, correlates them into an
> evidence graph, and ranks what to look at next. Two rules run through
> everything you will see: nothing is asserted without a source record, and
> nothing is ever a finding of guilt — every output is an investigative lead
> that requires human verification. Let me show you the case."

## MINUTE 1–2 · M3 (data in) — M2 stays on **Overview**

> "Twenty-one FIRs as raw text, 118 call-detail rows, 35 bank transfers, the
> subscriber and account registries, vehicles, travel and custody — 271
> records, all synthetic, each with a stable id you will see cited on screen.
> The FIR extractor is one regex shared by the loader and the ADD DATA
> preview, so what the preview shows is exactly what lands on the board."

*(M2 clicks **⦿ Crack the Case**. Step 1 appears.)*

## MINUTE 2–4 · M4 (the six steps) — M2 presses **Next ▶** at each cue

**Step 1 · Two clusters**
> "Community detection separates the network into three clusters. The two most
> central figures are the cluster leaders. Clusters are statistical groupings,
> not proven organisations — the panel says so."

**Step 2 · The broker**
> "This unresolved number contacts entities in both clusters. No subscriber is
> registered to it, so the records do not tell us who held the handset — and
> the system says exactly that instead of guessing."

**Step 3 · Follow the money**
> "Funds from several parties converge on one corporate entity and move on —
> the shape associated with layering. The panel also notes consolidation is
> ordinary commerce; the pattern is a lead, not a conclusion."

**Step 4 · Potential network controller**
> "Money exits to Vikram Rathore, who is named in zero FIRs in this corpus.
> Financially central, absent from the paperwork. He is flagged for review —
> and the dossier lists the uncertainty: absence from FIRs may be a gap in the
> corpus, not non-involvement."

**Step 5 · Shared custody**
> "Both leaders overlapped in custody in 2022. Shared custody establishes
> proximity, not association, and it predates the case window by four years —
> the system labels it that way."

**Step 6 · The anomaly**
> "A communication spike, quantified against that pair's own median day —
> the ratio is on screen. A deviation is a lead to examine, not proof."

*(M2 clicks **Done ✓**, then clicks the string between **Ramesh Yadav** and
**Sunil Kumar**.)*

> "Click any relationship and you get the evidence drawer: which records, which
> algorithm, and the arithmetic behind the confidence — base for the relation,
> plus corroboration per independent source type, capped at 97. Nothing in
> this system reaches 100."

## MINUTE 4–5 · M4 (leads & identity) — M2 opens **Leads**, then **Entity Search**

> "The Investigative Lead Score ranks entities on eight capped factors that
> sum to 100, every point attributable to records. Ramesh Yadav tops the list
> at 67 — REVIEW band — and you can read exactly which findings put him there.
> Then identity: the resolver scores 'R. Yadav', 'RAMESH YADAV' and 'Ramesh
> Yadhav' as likely the same person, but 'Ramesh Yadava' — one letter away —
> is kept separate because its phone and account conflict. Auto-merged: zero.
> A person confirms or rejects each match, and that decision is recorded."

*(M2 clicks the chat bubble, types **Who received the most money**, then
**What happened on 2026-03-18**.)*

> "The assistant answers only from the case records — every bullet cites its
> record id, and if it has to interpret a misspelt name it says so. There is
> no language model in this prototype, so it cannot invent a connection."

## MINUTE 5–6 · M5 (accountability) — M2 clicks **Tamper Test**, then opens **Audit**

> "Every request you just saw was written to a SHA-256 hash chain before it was
> served. The tamper test edits block 1 on a copy — the chain reports itself
> broken at block 1, and the live chain verifies intact. Officers' access is
> logged immutably; that is the accountability the Blockchain & Cybersecurity
> theme asks for, and the basis for DPDP Act purpose limitation."

## MINUTE 6–7 · M3 (ADD DATA) + M6 + M1 (close)

*(M2 clicks **＋ Add Data**, chooses **bank**, **Load example**, **Validate & preview**.)*

M3:
> "Two rows pasted: the first is valid, the second has a null amount. Nothing
> is corrected silently — the bad row is held as INVALID, the good one is
> committable, and a conflict against an existing holder would be flagged, not
> overwritten. Add to case rebuilds the graph and writes an audit block."

M6:
> "Deployment replaces the CSV loaders with connectors to CCTNS, telecom and
> FIU-IND — the record shape is the same. NetworkX today, Neo4j at scale; the
> stack is entirely open source, so the cost is compute and integration, not
> licences."

M1:
> "From scattered records to a ranked, cited, human-verified set of leads,
> with a tamper-evident audit trail. That is our answer to 26189. Questions?"

---

## Cue sheet for M2

| Speaker says | M2 does |
|---|---|
| M3 "…lands on the board" | click **⦿ Crack the Case** |
| M4 each step heading | **Next ▶** (six times), then **Done ✓** |
| M4 "Click any relationship…" | click the Ramesh Yadav ↔ Sunil Kumar string |
| M4 "The Investigative Lead Score…" | nav **Leads**; click Ramesh Yadav |
| M4 "Then identity…" | nav **Entity Search** → identity candidates |
| M4 "The assistant…" | chat bubble → the two questions above |
| M5 "The tamper test…" | click **🔒 Tamper Test**, then nav **Audit** |
| M3 "Two rows pasted…" | **＋ Add Data** → bank → Load example → Validate & preview |

## Q&A protocol
- All questions to **M1 first**, who routes: data → M3, algorithms → M4,
  audit/privacy → M5, deployment/cost → M6. M2 drives any "show me".
- If unsure, say what the software does and does not do; never claim a
  capability that is not on screen. `docs/JUDGE_QA.md` has the prepared answers.
- **Proof on demand:** click any node → dossier with every relationship cited;
  `/api/evidence/FIR_007` shows what one record supports; `/api/config` shows
  every threshold.

## Backup plans
- Board will not load: `python backend/engine.py` prints stats, leads and the
  brief in the terminal — narrate from that.
- Wrong state on the laptop (stray rows, decisions): stop the server and run
  `python backend/reset_demo_data.py`, then start it again.
- Fonts look plain: Google Fonts did not load; cosmetic only.

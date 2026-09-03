# 🎬 6-Member Demo Script — SIH 26189
**Total time: ~7 minutes talk + Q&A. Rehearse at least 3 full runs.**

## Role assignment

| # | Role | Owns |
|---|------|------|
| M1 | **Team Lead / Opener** | Problem statement, closing, judge Q&A traffic control |
| M2 | **Driver** | Laptop; presses **Next ▶** in Crack-the-Case mode exactly on each speaker's cue |
| M3 | **Data & NLP Engineer** | Ingestion + entity extraction slide/explanation |
| M4 | **Graph Scientist** | Algorithms: PageRank, Louvain, link prediction, anomaly |
| M5 | **Blockchain & Security** | Audit chain, privacy, DPDP Act compliance |
| M6 | **Product & Impact** | Govt deployment path, feasibility, business slide |

---

## MINUTE 0–1 · M1 (Opening — while M2 gets the dashboard up)

> "Good morning judges. Problem 26189 from the Ministry of Home Affairs asks a
> simple question with a hard answer: India's investigators are drowning in
> disconnected data. An FIR in Delhi, call records in a telecom database, a bank
> trail in Mumbai — today a human has to connect those dots by hand, across
> states, across weeks. Our system does it in seconds. We call it a map of the
> criminal world. Let me show you a case being cracked — live."

## MINUTE 1–3 · M3 (Data in) — M2 reloads the page so judges see the BOOT SEQUENCE, then clicks **⦿ Crack the Case**

> "We've loaded 21 FIRs as raw text, plus call detail records, bank transfers,
> prison rosters, travel logs and vehicle registrations — all synthetic, all
> matching the real schemas of CCTNS, telecom CDRs and FIU data. Watch the left
> panel: our NLP layer just read every FIR narrative and pulled out names,
> phone numbers and relationships — no human tagging. Every person becomes a
> node. Every call, payment, co-accusation or shared jail cell becomes an edge."

*(M2 presses **Next ▶** → Step 1 highlights the two gangs as M4 begins.)*

## MINUTE 3–5 · M4 (The reveal) — M2 presses **Next ▶** on each paragraph: Step 2 broker → Step 3 money → Step 4 **TARGET LOCKED** → Step 5 jail → Step 6 anomaly

> "Now the graph algorithms. Community detection instantly separates two gangs —
> blue is a Delhi drug network, green a Mumbai smuggling ring. But look at this
> red node: an **unregistered burner phone** talking to BOTH gang leaders. Our
> betweenness analysis flags it as the broker.
>
> Follow the yellow edges — money. Both leaders pay the same shell company, OM
> Traders. And the shell forwards ₹7 lakh to this man: **Vikram Rathore**.
> Here's the thing, judges — *Vikram appears in zero FIRs*. No investigator
> reading paperwork would ever find him. Our AI flags him in one second:
> financially central, operationally invisible — the hidden kingpin.
>
> Two more things. The dashed purple edge: our system found the two gang leaders
> shared a cell block in Tihar in 2022 — that's how the network formed. And the
> anomaly panel: an 8x spike in calls on 18 March — exactly 48 hours before the
> seizure in our case data. Spikes like this can trigger proactive alerts."

## MINUTE 5–6 · M5 (Blockchain) + M2 clicks **Tamper Test**

> "Power like this needs accountability. The theme is Blockchain & Cybersecurity,
> and here's why it matters: every single query an officer runs is written to a
> SHA-256 hash chain — each block sealed by the previous block's hash.
> [M2 clicks Tamper Test] We just simulated a rogue admin editing a past record
> to hide a search — and the chain instantly reports itself broken. No one can
> spy on innocent citizens and erase the evidence. In production this chain sits
> on a permissioned Hyperledger network across NCRB nodes."

## MINUTE 6–7 · M6 + M1 (Deployment & close)

M6:
> "Deployment is realistic: in production these CSV loaders are replaced by
> secure APIs to CCTNS, telecom providers and FIU — same schema, which is why we
> mocked it this way. The stack — FastAPI, NetworkX today, Neo4j at scale,
> React — is entirely open source: zero licensing cost to the government. It's
> effectively a mini-NATGRID for street-level crime investigation."

M1:
> "From a pile of paperwork to a prime suspect in seconds, with a tamper-proof
> audit trail protecting citizens' rights. That's our answer to problem 26189.
> Happy to take questions."

---

## Q&A protocol
- ALL questions go to **M1 first**, who routes: data→M3, algorithms→M4,
  security/privacy→M5, deployment/cost→M6. M2 drives any "show me" requests.
- Never talk over each other. If unsure, M1 says: "Great question — our
  production roadmap covers that" and gives the honest partial answer.
- Rehearse the **Next ▶ timing** — the TARGET LOCKED overlay must land exactly when M4 says "Vikram appears in zero FIRs".
- After Exit, click **Vikram Rathore's node** if judges ask for proof: the dossier shows every rupee and call, cited.
- The **Tamper Test** is your safety "wow" if judges look bored.

## Backup plans
- If WiFi dies and the graph won't load: run `python backend/engine.py` in the
  terminal — the full investigator brief prints as text. Narrate from that.
- Keep screenshots of the loaded dashboard in `ppt/` folder open in a tab.
- M2 should do a full dry run on the venue machine BEFORE judging starts.

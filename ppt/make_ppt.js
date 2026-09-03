const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5

const BG = "0D1117", PANEL = "161B22", TXT = "E6EDF3", SUB = "9DA7B3",
      ACC = "E3623B", BLUE = "4F8FF7", GREEN = "3FB950", YELLOW = "D29922", RED = "F85149";

function base(s, title, subtitle) {
  s.background = { color: BG };
  if (title) s.addText(title, { x: 0.6, y: 0.3, w: 12.1, h: 0.6, fontSize: 25,
    bold: true, color: TXT, fontFace: "Segoe UI", margin: 0 });
  if (subtitle) s.addText(subtitle, { x: 0.6, y: 0.95, w: 12.1, h: 0.4, fontSize: 14,
    color: ACC, fontFace: "Segoe UI", margin: 0 });
}
function card(s, x, y, w, h, head, body, headColor) {
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.08,
    fill: { color: PANEL }, line: { color: "30363D", width: 1 } });
  s.addText(head, { x: x + 0.25, y: y + 0.18, w: w - 0.5, h: 0.4, fontSize: 15,
    bold: true, color: headColor || ACC, fontFace: "Segoe UI", margin: 0 });
  s.addText(body, { x: x + 0.25, y: y + 0.62, w: w - 0.5, h: h - 0.8, fontSize: 12,
    color: TXT, fontFace: "Segoe UI", margin: 0, valign: "top" });
}

// ---------------- Slide 1: Title
let s = pres.addSlide();
s.background = { color: BG };
s.addText("AI-Powered Criminal Network Analysis System", { x: 0.8, y: 2.2, w: 11.7,
  h: 1.5, fontSize: 40, bold: true, color: TXT, fontFace: "Segoe UI", margin: 0 });
s.addText("From piles of paperwork to a map of the criminal world — in seconds.",
  { x: 0.8, y: 3.6, w: 11.7, h: 0.6, fontSize: 20, color: ACC, fontFace: "Segoe UI", margin: 0 });
s.addText([
  { text: "Smart India Hackathon 2026   ·   Problem 26189\n", options: { fontSize: 16, color: TXT, bold: true } },
  { text: "Ministry of Home Affairs — NCRB, Women Safety Division   ·   Theme: Blockchain & Cybersecurity",
    options: { fontSize: 13, color: SUB } },
], { x: 0.8, y: 5.4, w: 11.7, h: 1.0, fontFace: "Segoe UI", margin: 0 });

// ---------------- Slide 2: Problem
s = pres.addSlide();
base(s, "The Problem: Investigators Are Drowning in Disconnected Data",
     "Evidence exists — the connections don't");
card(s, 0.6, 1.7, 3.9, 2.3, "Scattered sources",
  "FIRs, call detail records, bank transfers, prison rosters, travel logs and vehicle data live in separate silos across states and agencies.", BLUE);
card(s, 4.7, 1.7, 3.9, 2.3, "Manual cross-checking",
  "An investigator must read every file and connect dots mentally. Cross-state links take weeks of correspondence — or are simply never found.", YELLOW);
card(s, 8.8, 1.7, 3.9, 2.3, "Networks stay hidden",
  "Kingpins deliberately keep their names out of FIRs. Brokers use unregistered burner phones. Paper-based analysis cannot see them.", RED);
card(s, 0.6, 4.3, 12.1, 2.4, "The cost",
  "Organised crime operates as a network; investigation happens case-by-case. A Delhi arrest and a Mumbai seizure that share a phone number are treated as unrelated events. The result: street-level dealers are caught, the network above them survives.\n\nProblem 26189 asks for an AI system that analyzes large volumes of criminal and intelligence data to uncover these networks — with accountability built in.");

// ---------------- Slide 3: Solution
s = pres.addSlide();
base(s, "Our Solution: A Six-Stage Intelligence Pipeline", "Working prototype — every stage runs live");
const stages = [
  ["1 · Ingest", "FIR text, CDR, bank, prison, travel, vehicle files (CSV/TXT/PDF)", BLUE],
  ["2 · Extract", "NLP pulls names, phones and relationships out of raw FIR narratives", BLUE],
  ["3 · Graph", "People become nodes; calls, money, co-accusations, shared cells become edges", GREEN],
  ["4 · Analyze", "PageRank finds influence · community detection finds gangs · link prediction finds hidden ties · burst detection finds anomalies", GREEN],
  ["5 · Explain", "AI writes plain-language briefs: \"X appears to be the broker between Group A and B\"", YELLOW],
  ["6 · Audit", "Every officer query sealed in a blockchain hash chain — tamper-proof by construction", ACC],
];
stages.forEach((st, i) => {
  const col = i % 3, row = Math.floor(i / 3);
  card(s, 0.6 + col * 4.1, 1.7 + row * 2.5, 3.9, 2.3, st[0], st[1], st[2]);
});
s.addText("Open-source end to end: Python · FastAPI · NetworkX → Neo4j · React/vis-network",
  { x: 0.6, y: 6.7, w: 12.1, h: 0.4, fontSize: 13, color: SUB, fontFace: "Segoe UI", margin: 0, align: "center" });

// ---------------- Slide 4: Demo story
s = pres.addSlide();
base(s, "What the Prototype Reveals — Live", "One click cracks a two-state case");
card(s, 0.6, 1.7, 5.95, 1.55, "Two gangs surface instantly",
  "Community detection separates a Delhi drug network and a Mumbai smuggling ring from 21 raw FIRs — no manual tagging.", BLUE);
card(s, 6.75, 1.7, 5.95, 1.55, "The broker: a burner phone",
  "One unregistered number talks to both gang leaders. Betweenness centrality flags it as the bridge between the groups.", RED);
card(s, 0.6, 3.45, 5.95, 1.55, "The hidden kingpin",
  "₹7,00,000 flows through a shell company to a man named in ZERO FIRs. Financially central, operationally invisible — the system flags him in one second.", YELLOW);
card(s, 6.75, 3.45, 5.95, 1.55, "The origin story",
  "Prison records show the two gang leaders shared Tihar Block-4 in 2022 — the system surfaces how the alliance formed.", GREEN);
card(s, 0.6, 5.2, 12.1, 1.55, "Proactive alerting",
  "Anomaly detection catches an 8x spike in calls between the groups — 48 hours before the seizure in the case data. In deployment, spikes near watched nodes trigger real-time alerts to investigators.", ACC);

// ---------------- Slide 5: Blockchain
s = pres.addSlide();
base(s, "Blockchain Where It Actually Matters: Accountability",
     "Theme fit: Blockchain & Cybersecurity — structural, not bolted on");
card(s, 0.6, 1.7, 5.95, 2.4, "The risk of powerful tools",
  "A system that can map anyone's connections could be misused to surveil innocent citizens. Trust requires that every use of the system is permanently on the record.", RED);
card(s, 6.75, 1.7, 5.95, 2.4, "Our answer: an immutable audit chain",
  "Every officer query becomes a SHA-256 block sealed by the previous block's hash. Editing ANY past record breaks every later hash. We demonstrate this live with a \"Tamper Test\" button — the chain instantly reports itself broken.", GREEN);
card(s, 0.6, 4.4, 12.1, 2.2, "Production design",
  "Permissioned Hyperledger Fabric replicated across NCRB data centres — no single administrator can rewrite history. Combined with role-based access control and purpose-limited queries, this addresses DPDP Act 2023 obligations head-on. The AI suggests leads with evidence attached; human officers decide. Nothing is a black-box accusation.");

// ---------------- Slide 6: Feasibility
s = pres.addSlide();
base(s, "Feasibility: Prototype Today, NATGRID-Grade Tomorrow",
     "Every mock maps to a real government source with the same schema");
s.addShape(pres.ShapeType.roundRect, { x: 0.6, y: 1.7, w: 12.1, h: 3.6, rectRadius: 0.08,
  fill: { color: PANEL }, line: { color: "30363D", width: 1 } });
const rows = [
  ["Prototype (runs now)", "Production (swap connectors, not code)"],
  ["Synthetic FIR text files", "CCTNS — secure API to national FIR/chargesheet database"],
  ["CDR / bank CSVs", "Telecom CDR feeds · FIU-IND suspicious transaction reports"],
  ["Regex entity extraction", "IndicBERT NER — FIRs in 12+ Indian languages"],
  ["NetworkX in-memory graph", "Neo4j cluster — billions of edges, same schema"],
  ["Template AI briefs", "On-prem LLM (air-gapped) fed identical graph facts"],
  ["JSON hash chain", "Hyperledger Fabric across NCRB nodes"],
];
rows.forEach((r, i) => {
  const bold = i === 0, color = i === 0 ? ACC : TXT;
  s.addText(r[0], { x: 0.95, y: 1.85 + i * 0.47, w: 5.3, h: 0.45, fontSize: bold ? 13 : 12,
    bold, color, fontFace: "Segoe UI", margin: 0 });
  s.addText(r[1], { x: 6.6, y: 1.85 + i * 0.47, w: 5.8, h: 0.45, fontSize: bold ? 13 : 12,
    bold, color: i === 0 ? ACC : SUB, fontFace: "Segoe UI", margin: 0 });
});
card(s, 0.6, 5.6, 12.1, 1.3, "Cost & rollout",
  "100% open-source stack — zero licence cost vs foreign tools (i2, Palantir). Pilot: one district's anonymized historical data, measuring time-to-lead vs manual investigation. Hosted on NIC MeghRaj cloud.");

// ---------------- Slide 7: Uniqueness & Impact
s = pres.addSlide();
base(s, "Why This Wins: Uniqueness & Impact", "");
card(s, 0.6, 1.5, 5.95, 1.6, "Hidden-kingpin detection",
  "Novel heuristic: high net money inflow + zero FIR mentions + shared covert infrastructure. Finds exactly the people paper-based investigation structurally cannot.", YELLOW);
card(s, 6.75, 1.5, 5.95, 1.6, "Evidence-cited AI, zero hallucination",
  "Every insight cites its source edge — FIR number, call count, rupee amount. The LLM phrases deterministic graph facts; it never invents connections.", GREEN);
card(s, 0.6, 3.3, 5.95, 1.6, "Live tamper-proof audit demo",
  "Judges see the blockchain catch a rogue edit in real time — accountability you can watch working, not a buzzword on a slide.", ACC);
card(s, 6.75, 3.3, 5.95, 1.6, "Weeks → seconds",
  "Cross-state link discovery that takes weeks of file correspondence happens in one click, with the reasoning shown in plain language any officer can act on.", BLUE);
card(s, 0.6, 5.1, 12.1, 1.7, "Impact",
  "Investigators stop at street dealers because the network above them is invisible. Making it visible changes what is prosecutable: brokers, financiers and kingpins instead of foot soldiers. For NCRB and the Women Safety Division, the same engine maps trafficking networks — where speed of connection-finding directly protects victims.");

pres.writeFile({ fileName: __dirname + "/SIH_Idea_Submission.pptx" })
  .then(() => console.log("PPT written"));

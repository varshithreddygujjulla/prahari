/* PRAHARI — SIH 2026 idea-submission deck, six slides in the winner's structure. */
const pptxgen = require("pptxgenjs");
const path = require("path");
const SHOTS = path.join(__dirname, "shots");
const OUT = process.argv[2] || path.join(__dirname, "PRAHARI_SIH2026_Idea.pptx");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";            // 13.333 x 7.5 in
pres.author = "Team PRAHARI";
pres.title = "PRAHARI — SIH 2026 · PS 26189";

// palette: the dashboard's navy for the cover, white content slides, the
// board's string colours as accents (blue co-accused, amber money, red calls)
const C = {
  navy: "0D1117", panel: "161B22", panel2: "1C2128", white: "FFFFFF",
  text: "1B2430", muted: "5C6773", line: "D0D7DE", tint: "F3F5F8",
  blue: "1F6FEB", blueT: "E8F0FE", amber: "B7791F", amberT: "FFF4DE",
  red: "C0392B", redT: "FDECEA", green: "1F8A4C", greenT: "E6F4EA",
  purple: "6F42C1", purpleT: "F0EAFB", teal: "0B7285", tealT: "E3F5F8",
};
const F = "Calibri";

// ------------------------------------------------------------ helpers
function header(s, title, right) {
  s.background = { color: C.white };
  s.addText([{ text: "PRAHARI", options: { bold: true, color: C.navy } },
             { text: "  ·  Team PRAHARI", options: { color: C.muted } }],
    { x: 0.45, y: 0.22, w: 4.5, h: 0.32, fontFace: F, fontSize: 12, margin: 0, isTextBox: true });
  s.addText(right || "SMART INDIA HACKATHON 2026  ·  PS 26189", {
    x: 8.4, y: 0.22, w: 4.5, h: 0.32, align: "right", fontFace: F, fontSize: 11,
    bold: true, color: C.blue, margin: 0, isTextBox: true });
  s.addText(title, { x: 0.45, y: 0.5, w: 12.4, h: 0.6, fontFace: F, fontSize: 28,
    bold: true, color: C.navy, margin: 0, isTextBox: true });
}
function circle(s, x, y, d, fill, glyph, fs) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill } });
  s.addText(glyph, { x, y, w: d, h: d, align: "center", valign: "middle",
    fontFace: "Segoe UI Emoji", fontSize: fs || 14, color: C.white, margin: 0, isTextBox: true });
}
function card(s, x, y, w, h, fill, radius) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill },
    line: { color: fill }, rectRadius: radius == null ? 0.08 : radius,
    shadow: { type: "outer", blur: 4, offset: 1, angle: 90, color: "000000", opacity: 0.12 } });
}
function box(s, x, y, w, h, fill, lineColor, title, lines, opts) {
  opts = opts || {};
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill },
    line: { color: lineColor, width: 1 }, rectRadius: 0.07 });
  const runs = [{ text: title, options: { bold: true, color: opts.titleColor || C.navy, fontSize: opts.ts || 11, breakLine: true } }];
  lines.forEach((t, i) => runs.push({ text: t, options: { color: opts.bodyColor || C.text, fontSize: opts.bs || 9, bullet: { indent: 8 }, breakLine: i < lines.length - 1 } }));
  s.addText(runs, { x: x + 0.08, y: y + 0.05, w: w - 0.16, h: h - 0.1, fontFace: F, valign: "top",
    margin: 0, isTextBox: true, paraSpaceAfter: 1 });
}
function arrow(s, x, y, w) {
  s.addShape(pres.shapes.RIGHT_ARROW, { x, y, w, h: 0.28, fill: { color: C.blue }, line: { color: C.blue } });
}

// ============================================================ 1 · cover
{
  const s = pres.addSlide();
  s.background = { color: C.navy };
  s.addText([{ text: "SMART INDIA HACKATHON 2026", options: { bold: true, color: C.white, fontSize: 18, breakLine: true } },
             { text: "Internal round  ·  idea submission", options: { color: "8B949E", fontSize: 11 } }],
    { x: 0.6, y: 0.45, w: 6, h: 0.8, fontFace: F, margin: 0, isTextBox: true });

  const kv = [
    ["Problem Statement ID", "26189"],
    ["Problem Statement Title", "AI-Powered Criminal Network Analysis System"],
    ["Organisation", "Ministry of Home Affairs · National Crime Records Bureau (NCRB), Women Safety Division"],
    ["Theme", "Blockchain & Cybersecurity"],
    ["PS Category", "Software"],
    ["Team ID", "to be allotted"],
    ["Team Name", "PRAHARI"],
  ];
  let y = 1.75;
  kv.forEach(([k, v]) => {
    s.addText(k, { x: 0.6, y, w: 2.6, h: 0.5, fontFace: F, fontSize: 12, color: "8B949E", valign: "middle", margin: 0, isTextBox: true });
    s.addText(v, { x: 3.2, y, w: 4.4, h: 0.5, fontFace: F, fontSize: 13, bold: k === "Team Name" || k === "Problem Statement ID",
      color: C.white, valign: "middle", margin: 0, isTextBox: true });
    s.addShape(pres.shapes.LINE, { x: 0.6, y: y + 0.52, w: 7.0, h: 0, line: { color: "30363D", width: 0.75 } });
    y += 0.58;
  });

  // brand block
  card(s, 8.3, 1.55, 4.5, 4.55, C.panel, 0.12);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 10.05, y: 1.95, w: 1.0, h: 1.0, rectRadius: 0.2,
    fill: { color: C.blue }, line: { color: C.blue } });
  s.addText("🛡", { x: 10.05, y: 1.95, w: 1.0, h: 1.0, align: "center", valign: "middle",
    fontFace: "Segoe UI Emoji", fontSize: 34, color: C.white, margin: 0, isTextBox: true });
  s.addText("PRAHARI", { x: 8.3, y: 3.05, w: 4.5, h: 0.8, align: "center", fontFace: F, fontSize: 40,
    bold: true, color: C.white, charSpacing: 4, margin: 0, isTextBox: true });
  s.addText("Investigative Intelligence & Evidence Correlation Platform", { x: 8.5, y: 3.85, w: 4.1, h: 0.6,
    align: "center", fontFace: F, fontSize: 13, color: "C9D1D9", margin: 0, isTextBox: true });
  s.addText([
    { text: "Evidence-cited leads", options: { color: "4A9EFF", bold: true } }, { text: "  ·  ", options: { color: "6E7681" } },
    { text: "identities never auto-merged", options: { color: "D29922", bold: true } }, { text: "  ·  ", options: { color: "6E7681" } },
    { text: "every action on a hash chain", options: { color: "3FB950", bold: true } },
  ], { x: 8.45, y: 4.55, w: 4.2, h: 0.8, align: "center", fontFace: F, fontSize: 11, margin: 0, isTextBox: true });
  s.addText("“Data connects what others overlook.”", { x: 8.3, y: 5.45, w: 4.5, h: 0.4, align: "center",
    fontFace: F, fontSize: 11, italic: true, color: "8B949E", margin: 0, isTextBox: true });

  s.addText("Working prototype  ·  28 people · 78 evidence links · 3 clusters · 24 anomaly findings · 0 auto-merged identities · 190 automated tests",
    { x: 0.6, y: 6.55, w: 12.1, h: 0.4, fontFace: F, fontSize: 11, color: "8B949E", margin: 0, isTextBox: true });
  s.addNotes("Cover. Team ID is left as 'to be allotted' for the internal round. Every number on the footer is produced by the running code, not estimated.");
}

// ============================================================ 2 · problems & uniqueness
{
  const s = pres.addSlide();
  header(s, "Problems & Solution Uniqueness");
  const probs = [
    ["📂", C.blue, "Evidence lives in silos", "FIRs in CCTNS, call records at telecoms, transfers at FIU-IND, registries, custody and travel logs sit apart. Cross-state links surface weeks late, or never."],
    ["🧠", C.amber, "Connections are made in an officer's head", "Hundreds of rows are cross-checked by hand. Nothing records why two people were linked, so nothing can be re-checked."],
    ["👤", C.purple, "Same person, three spellings", "“R. Yadav”, “RAMESH YADAV”, “Ramesh Yadhav” split one trail three ways, while a look-alike name can be wrongly merged into it."],
    ["🗣", C.red, "Tools that overclaim", "“Kingpin”, “risk score” and unsourced AI summaries create leads that no officer or court can trace back to a record."],
    ["⏱", C.teal, "Time is flattened", "A 2021 custody overlap and a March 2026 call spike look alike without a case clock and time windows anchored to the records."],
    ["🔒", C.green, "No accountability for access", "A system that can map anyone's contacts can be misused. Without an immutable log, misuse is invisible."],
  ];
  const gx = 0.45, gy = 1.3, cw = 3.95, ch = 1.75, gap = 0.18;
  probs.forEach((p, i) => {
    const x = gx + (i % 2) * (cw + gap), y = gy + Math.floor(i / 2) * (ch + gap);
    card(s, x, y, cw, ch, C.tint);
    circle(s, x + 0.15, y + 0.17, 0.5, p[1], p[0], 15);
    s.addText(p[2], { x: x + 0.78, y: y + 0.15, w: cw - 0.9, h: 0.5, fontFace: F, fontSize: 13, bold: true, color: C.navy, valign: "middle", margin: 0, isTextBox: true });
    s.addText(p[3], { x: x + 0.15, y: y + 0.72, w: cw - 0.3, h: ch - 0.82, fontFace: F, fontSize: 10.5, color: C.text, valign: "top", margin: 0, isTextBox: true });
  });

  // uniqueness column
  const ux = 8.75, uy = 1.3, uw = 4.15, uh = 5.6;
  card(s, ux, uy, uw, uh, C.navy, 0.1);
  s.addText("What makes PRAHARI different", { x: ux + 0.25, y: uy + 0.18, w: uw - 0.5, h: 0.45, fontFace: F, fontSize: 15, bold: true, color: C.white, margin: 0, isTextBox: true });
  const uniq = [
    ["Provenance by construction", "An edge cannot exist without a source record: the ledger raises instead. Every finding cites its record ids, and /api/evidence answers what any record supports."],
    ["Confidence is derived, capped at 97", "Base by evidence type plus corroboration across independent source types. Nothing is ever 100%."],
    ["Identities are never merged", "Scored and banded; conflicting identifiers apply −35; the investigator confirms. Auto-merged is asserted to be 0."],
    ["A lead score, not a guilt score", "Investigative Lead Score: 8 capped factors, every point explained and cited. VERIFIED / DISMISSED are human verdicts."],
    ["Audited, reversible, no LLM", "A SHA-256 block per request; wrong batches are retracted with a reason, never deleted; the assistant answers only from records."],
  ];
  let y = uy + 0.75;
  uniq.forEach(u => {
    s.addText([{ text: u[0], options: { bold: true, color: "4A9EFF", fontSize: 11.5, breakLine: true } },
               { text: u[1], options: { color: "C9D1D9", fontSize: 10 } }],
      { x: ux + 0.25, y, w: uw - 0.5, h: 0.93, fontFace: F, valign: "top", margin: 0, isTextBox: true });
    y += 0.96;
  });
  s.addNotes("Six problems on the left mirror the winner's structure. The right column is the pitch: every claim is enforced in code and covered by tests, not just described.");
}

// ============================================================ 3 · architecture + stack
{
  const s = pres.addSlide();
  header(s, "System Architecture");
  const top = 1.3;
  // sources
  s.addText("DATA SOURCES", { x: 0.45, y: top, w: 1.9, h: 0.3, fontFace: F, fontSize: 9, bold: true, color: C.muted, margin: 0, isTextBox: true });
  const src = ["FIR narratives (CCTNS)", "Call detail records", "Bank transfers (FIU-IND)", "Subscriber · account · vehicle registries", "Custody rosters · travel manifests", "ADD DATA: JSON · CSV · FIR text"];
  src.forEach((t, i) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.45, y: top + 0.35 + i * 0.62, w: 1.9, h: 0.52, rectRadius: 0.06, fill: { color: C.tint }, line: { color: C.line } });
    s.addText(t, { x: 0.53, y: top + 0.35 + i * 0.62, w: 1.75, h: 0.52, fontFace: F, fontSize: 9, color: C.text, valign: "middle", margin: 0, isTextBox: true });
  });
  arrow(s, 2.42, 3.3, 0.28);
  const mid = top + 0.35, mh = 3.6;
  box(s, 2.75, mid, 1.85, mh, C.blueT, C.blue, "1 · INGESTION", [
    "stable record ids: FIR_003, CDR-0007, TXN-0012", "one shared FIR extractor for loader and preview",
    "validate → quality score → duplicate & holder-conflict checks", "malformed values held, never corrected",
    "batches retractable with a reason; ids never shift"]);
  arrow(s, 4.66, 3.3, 0.28);
  box(s, 5.0, mid, 1.85, mh, C.amberT, C.amber, "2 · EVIDENCE LEDGER", [
    "an Assertion with zero records raises", "confidence = base(relation) + corroboration per independent source type + repeat",
    "capped at 97, floored at 5", "uncertainty list on every edge", "reverse provenance per record"]);
  arrow(s, 6.91, 3.3, 0.28);
  box(s, 7.25, mid, 1.85, mh, C.purpleT, C.purple, "3 · TEMPORAL GRAPH", [
    "NetworkX; person · unresolved number · corporate entity · vehicle",
    "co-accused · calls · money · custody · registry relations",
    "windows all / 30d / 7d / 24h anchored to the case clock", "timeless registries survive every window"]);
  arrow(s, 9.16, 3.3, 0.28);
  const ax = 9.5, aw = 1.85;
  box(s, ax, mid, aw, 1.1, C.greenT, C.green, "4a · ANALYTICS", ["PageRank · betweenness · clusters", "Investigative Lead Score: 8 capped factors"], { bs: 8.5, ts: 10 });
  box(s, ax, mid + 1.25, aw, 1.1, C.redT, C.red, "4b · ANOMALY ENGINE", ["10 detectors, each quantified against a baseline", "median + MAD outliers, spikes, layering"], { bs: 8.5, ts: 10 });
  box(s, ax, mid + 2.5, aw, 1.1, C.tealT, C.teal, "4c · ENTITY RESOLUTION", ["phonetic + identifier scoring, banded", "never auto-merged; −35 on conflicts"], { bs: 8.5, ts: 10 });
  arrow(s, 11.41, 3.3, 0.28);
  box(s, 11.75, mid, 1.15, 1.7, C.tint, C.line, "5 · API", ["FastAPI", "graph · entity · case file · leads · anomalies · ask · intake · decisions · audit"], { bs: 8, ts: 10 });
  box(s, 11.75, mid + 1.85, 1.15, 1.75, C.navy, C.navy, "6 · BOARD", ["Case Board · Case File", "Ask PRAHARI (grounded)", "Add Data · Retract", "Audit · Report"], { bs: 8, ts: 10, titleColor: "FFFFFF", bodyColor: "C9D1D9" });
  // audit chain band
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 2.75, y: 5.42, w: 10.15, h: 0.52, rectRadius: 0.06, fill: { color: C.panel }, line: { color: C.panel } });
  s.addText([{ text: "AUDIT CHAIN  ", options: { bold: true, color: "3FB950" } },
             { text: "every request becomes a SHA-256 block before it is served · atomic writes under a lock · edits, deletions and reordering detected · tamper demo runs on a copy · decisions and retractions carry their reason", options: { color: "C9D1D9" } }],
    { x: 2.9, y: 5.42, w: 9.9, h: 0.52, fontFace: F, fontSize: 9.5, valign: "middle", margin: 0, isTextBox: true });
  // tech stack strip
  s.addText("TECH STACK", { x: 0.45, y: 6.08, w: 2, h: 0.3, fontFace: F, fontSize: 9, bold: true, color: C.muted, margin: 0, isTextBox: true });
  const stack = [
    ["Backend", "Python 3 · FastAPI · NetworkX · pytest (190 tests on an isolated data copy)", C.blue],
    ["Frontend", "vis-network (vendored, offline) · HTML / CSS / JS · printable report", C.purple],
    ["Integrity", "SHA-256 hash chain · JSON stores with atomic writes · seed snapshot + reset", C.green],
    ["Principle", "no LLM · no external calls · synthetic data · every number at /api/config", C.amber],
  ];
  stack.forEach((t, i) => {
    const x = 0.45 + i * 3.12;
    card(s, x, 6.38, 2.98, 0.8, C.tint);
    s.addText([{ text: t[0], options: { bold: true, color: t[2], fontSize: 10, breakLine: true } }, { text: t[1], options: { color: C.text, fontSize: 9 } }],
      { x: x + 0.12, y: 6.42, w: 2.75, h: 0.72, fontFace: F, valign: "middle", margin: 0, isTextBox: true });
  });
  s.addNotes("Read left to right: sources, ingestion with stable ids, the evidence ledger that refuses unsupported edges, the temporal graph, three analysis engines, the API and the board. The audit chain sits under everything. Stack is entirely open source; there is no language model anywhere.");
}

// ============================================================ 4 · challenges vs mitigations
{
  const s = pres.addSlide();
  header(s, "Potential Challenges  →  How We Tackle Them");
  const rows = [
    ["👥", C.red, "False identity merges", "One character separates “Ramesh Yadav” from “Ramesh Yadava”; a naive match fuses two people and taints every downstream finding.",
     "✔", C.green, "Identifier-weighted resolution", "Names alone cannot reach LIKELY; conflicting phone/account apply −35; the look-alike scores 12 and stays separate. Auto-merged = 0, asserted by tests; a person confirms each match."],
    ["📣", C.red, "Overclaiming and false positives", "“Kingpin”, “burner”, “prime suspect” and a 100% badge turn correlation into accusation.",
     "✔", C.green, "Approved terminology, enforced", "Potential Network Controller, Unresolved Number, Investigative Lead. Confidence capped at 97; every finding carries the human-verification notice; tests scan the API and the UI for banned terms."],
    ["🧾", C.amber, "Messy, malformed input", "Real feeds carry bad dates, non-numeric amounts, missing ids, duplicates and a phone registered to two holders.",
     "✔", C.green, "Validate, hold, never correct", "INVALID rows are held and shown, optional gaps stay null, duplicates and holder conflicts are flagged for review. The preview is the same extractor the board uses."],
    ["🛡", C.purple, "Misuse and privacy (DPDP Act 2023)", "A contact-mapping tool without accountability can surveil anyone, and nobody would know.",
     "✔", C.green, "Accountability by construction", "Each request is a SHA-256 block before it is served; call data is metadata only; no outbound calls; a live tamper test shows the chain break and recover."],
    ["↩", C.blue, "Wrong data enters a case", "Rows from another case get pasted in; deleting them would renumber every later record and corrupt citations.",
     "✔", C.green, "Audited, reversible retraction", "Batches are tombstoned with a mandatory reason; ids never shift; restore is one click; the shipped corpus is protected and a reset script exists."],
    ["📈", C.teal, "Scale and language", "Regex extraction and an in-memory graph will not carry 12 languages or millions of edges.",
     "✔", C.green, "Same contracts, swappable engines", "Trained NER (IndicBERT) replaces the regex behind the same trigger-and-name contract; Neo4j takes the same node/relation schema; analytics code does not change."],
  ];
  const y0 = 1.36, rh = 0.93, lx = 0.45, lw = 6.05, rx = 6.85, rw = 6.05;
  s.addText("POTENTIAL CHALLENGES", { x: lx, y: y0 - 0.28, w: lw, h: 0.25, fontFace: F, fontSize: 9, bold: true, color: C.red, margin: 0, isTextBox: true });
  s.addText("HOW WE TACKLE THEM", { x: rx, y: y0 - 0.28, w: rw, h: 0.25, fontFace: F, fontSize: 9, bold: true, color: C.green, margin: 0, isTextBox: true });
  rows.forEach((r, i) => {
    const y = y0 + i * rh;
    card(s, lx, y, lw, rh - 0.1, C.tint);
    circle(s, lx + 0.12, y + 0.17, 0.46, r[1], r[0], 13);
    s.addText([{ text: r[2], options: { bold: true, color: C.navy, fontSize: 11, breakLine: true } }, { text: r[3], options: { color: C.text, fontSize: 9.5 } }],
      { x: lx + 0.7, y: y + 0.06, w: lw - 0.82, h: rh - 0.22, fontFace: F, valign: "middle", margin: 0, isTextBox: true });
    card(s, rx, y, rw, rh - 0.1, C.greenT);
    circle(s, rx + 0.12, y + 0.17, 0.46, r[5], r[4], 13);
    s.addText([{ text: r[6], options: { bold: true, color: C.navy, fontSize: 11, breakLine: true } }, { text: r[7], options: { color: C.text, fontSize: 9.5 } }],
      { x: rx + 0.7, y: y + 0.06, w: rw - 0.82, h: rh - 0.22, fontFace: F, valign: "middle", margin: 0, isTextBox: true });
    s.addShape(pres.shapes.RIGHT_ARROW, { x: lx + lw + 0.1, y: y + 0.28, w: 0.2, h: 0.25, fill: { color: C.line }, line: { color: C.line } });
  });
  s.addNotes("Each challenge on the left has a mitigation that exists in the code today, not on a roadmap. The last row is the honest scaling story: the contracts stay, the engines swap.");
}

// ============================================================ 5 · prototype, future plans, links
{
  const s = pres.addSlide();
  header(s, "Prototype  ·  Future Plans");
  // hero: full board (1920x1028)
  const hx = 0.45, hy = 1.25, hw = 6.3, hh = hw * 1028 / 1920;
  s.addImage({ path: path.join(SHOTS, "board_hero.png"), x: hx, y: hy, w: hw, h: hh, rounding: false });
  s.addText("Case Board — 28 people, 3 clusters, strings coloured by evidence type; amounts and call counts on the links", { x: hx, y: hy + hh + 0.04, w: hw, h: 0.3, fontFace: F, fontSize: 8.5, color: C.muted, margin: 0, isTextBox: true });
  // case file panel (342x692)
  const cx = 6.95, cw = 1.62, chh = cw * 692 / 342;
  s.addImage({ path: path.join(SHOTS, "casefile_panel.png"), x: cx, y: hy, w: cw, h: chh });
  s.addText("Case file: FIR bullets, co-accused, phone recovered", { x: cx, y: hy + chh + 0.04, w: cw + 0.3, h: 0.3, fontFace: F, fontSize: 8.5, color: C.muted, margin: 0, isTextBox: true });
  // leads card (1327x302) + audit (1327x575)
  const rx = 8.75, rw = 4.15;
  const lh = rw * 302 / 1327, ah = rw * 575 / 1327;
  s.addImage({ path: path.join(SHOTS, "leads_card.png"), x: rx, y: hy, w: rw, h: lh });
  s.addText("Investigative Lead Score: every point explained and cited, human verdict buttons", { x: rx, y: hy + lh + 0.03, w: rw, h: 0.28, fontFace: F, fontSize: 8.5, color: C.muted, margin: 0, isTextBox: true });
  s.addImage({ path: path.join(SHOTS, "audit_panel.png"), x: rx, y: hy + lh + 0.36, w: rw, h: ah });
  s.addText("Audit log: 460 sealed blocks, live Tamper Test", { x: rx, y: hy + lh + 0.36 + ah + 0.03, w: rw, h: 0.28, fontFace: F, fontSize: 8.5, color: C.muted, margin: 0, isTextBox: true });

  // future plans chevrons
  const fy = 5.2;
  s.addText("FUTURE PLANS AND IMPROVEMENTS", { x: 0.45, y: fy, w: 6, h: 0.28, fontFace: F, fontSize: 9, bold: true, color: C.muted, margin: 0, isTextBox: true });
  const plans = [
    ["Map & geo-fencing", "CCTV/ANPR and GPS already ingest and stage", C.blue],
    ["OSINT & documents", "social records, FIR browser, multi-hop explore", C.purple],
    ["RBAC + multilingual NER", "IndicBERT behind the same extractor contract", C.amber],
    ["Neo4j + live connectors", "CCTNS, telecom CDR, FIU-IND, e-Prisons, VAHAN", C.teal],
    ["Permissioned ledger", "Hyperledger across NCRB nodes, HSM keys", C.green],
  ];
  plans.forEach((p, i) => {
    const x = 0.45 + i * 2.5;
    s.addShape(pres.shapes.CHEVRON, { x, y: fy + 0.32, w: 2.45, h: 0.55, fill: { color: p[2] }, line: { color: p[2] } });
    s.addText(p[0], { x: x + 0.28, y: fy + 0.32, w: 1.95, h: 0.55, fontFace: F, fontSize: 10, bold: true, color: C.white, valign: "middle", margin: 0, isTextBox: true });
    s.addText(p[1], { x: x + 0.05, y: fy + 0.9, w: 2.35, h: 0.5, fontFace: F, fontSize: 8.5, color: C.text, valign: "top", margin: 0, isTextBox: true });
  });
  // links
  const ly = 6.62;
  s.addText([{ text: "Project Repo:  ", options: { color: C.muted } },
             { text: "github.com/varshithreddygujjulla/prahari", options: { color: C.blue, underline: { style: "sng" }, hyperlink: { url: "https://github.com/varshithreddygujjulla/prahari" } } }],
    { x: 0.45, y: ly, w: 4.6, h: 0.35, fontFace: F, fontSize: 10.5, bold: true, margin: 0, isTextBox: true });
  s.addText([{ text: "Prototype:  ", options: { color: C.muted } },
             { text: "runs offline — python -m uvicorn backend.main:app → localhost:8000", options: { color: C.navy } }],
    { x: 5.1, y: ly, w: 5.2, h: 0.35, fontFace: F, fontSize: 10.5, bold: true, margin: 0, isTextBox: true });
  s.addText([{ text: "Prototype Video:  ", options: { color: C.muted } }, { text: "in preparation", options: { color: C.navy } }],
    { x: 10.4, y: ly, w: 2.5, h: 0.35, fontFace: F, fontSize: 10.5, bold: true, margin: 0, isTextBox: true });
  s.addNotes("All four screenshots are from the running prototype on the synthetic case. Future plans follow the specification's own priority order. Add the video link when it exists.");
}

// ============================================================ 6 · references, impact
{
  const s = pres.addSlide();
  header(s, "Resources & References");
  const refs = [
    ["Criminal network analysis", "Sparrow, M. K. (1991). The application of network analysis to criminal intelligence. Social Networks 13(3). · Morselli, C. (2009). Inside Criminal Networks. Springer."],
    ["Centrality and communities", "Brin, S. & Page, L. (1998). The anatomy of a large-scale hypertextual web search engine. · Clauset, Newman & Moore (2004). Finding community structure in very large networks. Phys. Rev. E 70."],
    ["Entity resolution", "Fellegi, I. P. & Sunter, A. B. (1969). A theory for record linkage. JASA 64(328). · Christen, P. (2012). Data Matching. Springer."],
    ["Robust anomaly detection", "Leys, C. et al. (2013). Detecting outliers: use absolute deviation around the median. J. Exp. Soc. Psych. 49(4)."],
    ["Tamper-evident logs", "Haber, S. & Stornetta, W. S. (1991). How to time-stamp a digital document. J. Cryptology 3. · Hyperledger Fabric documentation."],
    ["Law and data shapes", "Digital Personal Data Protection Act, 2023 · CCTNS (NCRB) FIR/charge-sheet schema · FIU-IND suspicious-transaction reporting · e-Prisons · VAHAN."],
  ];
  card(s, 0.45, 1.3, 7.55, 5.7, C.tint);
  s.addText("RESEARCH AND STANDARDS BEHIND THE DESIGN", { x: 0.7, y: 1.45, w: 7, h: 0.3, fontFace: F, fontSize: 9, bold: true, color: C.muted, margin: 0, isTextBox: true });
  let y = 1.85;
  refs.forEach((r, i) => {
    circle(s, 0.7, y + 0.03, 0.34, C.blue, String(i + 1), 10);
    s.addText([{ text: r[0], options: { bold: true, color: C.navy, fontSize: 11, breakLine: true } }, { text: r[1], options: { color: C.text, fontSize: 9.5 } }],
      { x: 1.2, y, w: 6.6, h: 0.8, fontFace: F, valign: "top", margin: 0, isTextBox: true });
    y += 0.84;
  });
  // impact cards
  const ix = 8.25, iw = 4.65;
  card(s, ix, 1.3, iw, 2.75, C.blueT);
  circle(s, ix + 0.2, 1.48, 0.46, C.blue, "₹", 14);
  s.addText("Economic impact", { x: ix + 0.8, y: 1.48, w: 3.6, h: 0.46, fontFace: F, fontSize: 14, bold: true, color: C.navy, valign: "middle", margin: 0, isTextBox: true });
  s.addText([
    { text: "Zero licence cost: fully open-source stack against per-seat foreign tools (i2 Analyst's Notebook, Palantir).", options: { bullet: true, breakLine: true } },
    { text: "Weeks of cross-state file correspondence become one query with the reasoning attached.", options: { bullet: true, breakLine: true } },
    { text: "Runs on a laptop today; the same schema scales on NIC MeghRaj with Neo4j. Pilot metric: time-to-lead versus manual work.", options: { bullet: true } },
  ], { x: ix + 0.2, y: 2.05, w: iw - 0.4, h: 1.9, fontFace: F, fontSize: 10, color: C.text, valign: "top", margin: 0, isTextBox: true, paraSpaceAfter: 4 });
  card(s, ix, 4.25, iw, 2.75, C.greenT);
  circle(s, ix + 0.2, 4.43, 0.46, C.green, "🤝", 13);
  s.addText("Social benefits", { x: ix + 0.8, y: 4.43, w: 3.6, h: 0.46, fontFace: F, fontSize: 14, bold: true, color: C.navy, valign: "middle", margin: 0, isTextBox: true });
  s.addText([
    { text: "Investigation reaches the financiers and brokers above street level, not only the foot soldiers.", options: { bullet: true, breakLine: true } },
    { text: "Citizens are protected by design: no guilt scores, no automatic identity merges, human verdicts, an audit chain no administrator can rewrite.", options: { bullet: true, breakLine: true } },
    { text: "For NCRB's Women Safety Division the same engine maps trafficking networks, where speed of connection-finding protects victims.", options: { bullet: true } },
  ], { x: ix + 0.2, y: 5.0, w: iw - 0.4, h: 1.9, fontFace: F, fontSize: 10, color: C.text, valign: "top", margin: 0, isTextBox: true, paraSpaceAfter: 4 });
  s.addNotes("References are the actual methods used: network analysis, PageRank and greedy modularity, Fellegi–Sunter record linkage, MAD outliers, hash-chained timestamps. Impact is framed as accountability plus reach, never as automated accusation.");
}

pres.writeFile({ fileName: OUT }).then(f => console.log("wrote", f));

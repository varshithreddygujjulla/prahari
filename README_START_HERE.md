# 🏆 SIH 26189 — AI-Powered Criminal Network Analysis System
### Ministry of Home Affairs · NCRB · Theme: Blockchain & Cybersecurity

**READ THIS FILE FIRST. Total setup time: ~5 minutes.**

---

## 📦 What's in this package

```
sih-package/
├── README_START_HERE.md        ← you are here
├── requirements.txt            ← python dependencies
├── backend/
│   ├── generate_data.py        ← creates all synthetic datasets (already run once)
│   ├── engine.py               ← NER + graph + analytics + audit blockchain
│   └── main.py                 ← FastAPI server
├── frontend/
│   └── index.html              ← interactive graph dashboard (vis-network)
├── data/                       ← 21 synthetic FIRs, CDR/bank/prison/travel/vehicle CSVs
├── ppt/
│   └── SIH_Idea_Submission.pptx ← your idea-submission deck
└── docs/
    ├── DEMO_SCRIPT_6_MEMBERS.md ← who says what, line by line
    ├── ARCHITECTURE.md          ← system design + production upgrade path
    └── JUDGE_QA.md              ← 20 likely judge questions with answers
```

## 🚀 Setup (do this once, on the laptop)

1. **Unzip** this folder anywhere (e.g. Desktop). Open a terminal **inside** the
   `sih-package` folder.
2. **Install Python 3.10+** if not present → https://python.org (tick "Add to PATH" on Windows).
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the server:
   ```bash
   uvicorn backend.main:app --reload
   ```
   (Windows alternative if uvicorn isn't found: `python -m uvicorn backend.main:app --reload`)
5. Open **http://localhost:8000** in Chrome. Watch the boot sequence, then hit
   **⦿ Crack the Case**. Done. 🎉

> Internet is needed the first time the page loads (graph library + fonts from
> CDN). At the venue, load the page once on hotel WiFi and keep the tab open,
> or download vis-network.min.js into `frontend/` and change the `<script src>`
> line to point at it — then it's fully offline.

## 🎛 The PRAHARI Evidence Board — what each control does

The UI is a detective's corkboard under spotlights: every person is a **pinned
polaroid** (leaders labelled CELL A/B — LEADER), the burner phone is a **yellow
sticky note**, the shell company a **manila evidence tag**, and every
relationship is **string** — red for calls, amber twine for money, dashed
purple for shared jail time. Panels are a detective's notepad (left) and a
manila case file (right).

- **Boot sequence** — a CONFIDENTIAL case-file cover opens with a live typewriter
  ingestion log, then the board is revealed. Let judges watch it.
- **⦿ Crack the Case** — THE demo feature. A guided 6-step cinematic
  investigation: gangs → broker burner → money trail → **TARGET LOCKED**
  (a red PRIME SUSPECT stamp slams onto the board) → jail-origin link → anomaly spike. Press **Next ▶**
  at each speaker's cue; the camera flies, everything else dims, and the AI
  case log types each finding with its evidence source. **Exit** restores the
  full graph and prints the complete investigator brief.
- **Click any node** — opens its Entity Dossier: influence/broker scores plus
  every evidence edge cited to its source (FIR no., ₹ amount, call count).
- **Filter chips** (top-right) — toggle Calls / Money / Co-accused / Jail edges.
  Turning on only Money makes the ₹ trail to the kingpin pop for judges.
- **Search (press /)** — type a name, Enter → camera flies to the entity.
- **Tamper Test** — simulates a rogue admin editing a past audit record: the
  chain strip at the bottom snaps red/BROKEN, an alert fires, then the record
  restores. Blockchain accountability, visible in 5 seconds.

## 🔁 Regenerating / editing the data

All demo data is synthetic and reproducible:
```bash
python backend/generate_data.py     # rebuilds data/ from scratch (fixed seed)
```
Want to add your own FIRs? Drop `.txt` files into `data/firs/` following the same
format, then open http://localhost:8000/api/rebuild and refresh — the graph updates.

## 🎬 The demo story (memorize this!)

The datasets hide a crime network the system uncovers **live**:
1. Two gangs — Delhi drugs (blue) and Mumbai smuggling (green) — appear as two clusters.
2. A **red burner phone** (9990001111, unregistered) talks to BOTH gang leaders → broker.
3. A **yellow shell company** (OM TRADERS) collects money from both leaders.
4. The money exits to **Vikram Rathore** — a man named in **ZERO FIRs**. The AI flags
   him as the hidden kingpin. That's your "wow" moment.
5. A dashed purple edge shows Ramesh & Salim were **jailed together in Tihar Block-4** —
   how the gangs first connected.
6. Anomaly panel: call spike on 18–19 March = 48h before the (fictional) Mundra seizure.
7. Click **Tamper Test** → shows the blockchain audit chain catching a rogue edit.

## 🧪 Quick self-test without the server

```bash
python backend/engine.py
```
Prints the stats + full investigator brief in the terminal. If this works, everything works.

## 🆘 Troubleshooting

| Problem | Fix |
|---|---|
| `pip` not found | Use `pip3` / reinstall Python with PATH ticked |
| Port 8000 busy | `uvicorn backend.main:app --port 8080` |
| Graph is blank | You're offline and CDN didn't load — see offline note above |
| Fonts look plain | Same CDN issue — cosmetic only, demo still works |
| `ModuleNotFoundError: backend` | You must run uvicorn from the `sih-package` folder root |

## 👥 Team roles → see `docs/DEMO_SCRIPT_6_MEMBERS.md`
## 🎤 Judge questions → see `docs/JUDGE_QA.md`

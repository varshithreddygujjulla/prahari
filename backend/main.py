"""
main.py — FastAPI server.
Run:  uvicorn backend.main:app --reload
Open: http://localhost:8000
"""
import os
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.engine import run_pipeline, AuditChain

app = FastAPI(title="AI-Powered Criminal Network Analysis System — SIH 26189")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")
audit = AuditChain()
_cache = {}

@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND, "index.html"))

@app.get("/api/graph")
def graph(officer: str = Query("Officer-101")):
    """Full analyzed graph + insights. Every call is written to the audit chain."""
    audit.record(officer, "QUERY: full network graph + insights")
    if "result" not in _cache:
        _cache["result"] = run_pipeline()
    return _cache["result"]

@app.get("/api/rebuild")
def rebuild(officer: str = Query("Officer-101")):
    """Force re-ingestion (use after adding new data files)."""
    audit.record(officer, "ACTION: re-ingested all data sources")
    _cache["result"] = run_pipeline()
    return {"status": "rebuilt", "stats": _cache["result"]["stats"]}

@app.get("/api/audit")
def audit_log():
    ok, bad = audit.verify()
    return {"chain_valid": ok, "tampered_block": bad, "blocks": audit.chain[-25:]}

@app.get("/api/audit/tamper-demo")
def tamper_demo():
    """DEMO ONLY: corrupt block 1 in memory, show verification catches it, restore."""
    if len(audit.chain) < 2:
        return {"error": "make a query first"}
    original = audit.chain[1]["action"]
    audit.chain[1]["action"] = "TAMPERED: query deleted by rogue admin"
    ok, bad = audit.verify()
    audit.chain[1]["action"] = original
    return {"demo": "block 1 was modified in memory",
            "chain_valid_after_tampering": ok, "first_broken_block": bad,
            "conclusion": "Hash chain detects any edit to past queries — restored now",
            "chain_valid_after_restore": audit.verify()[0]}

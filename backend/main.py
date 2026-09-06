"""
main.py — FastAPI application.

Run:  uvicorn backend.main:app --reload
Open: http://localhost:8000
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import router

app = FastAPI(
    title="PRAHARI — Investigative Intelligence & Evidence Correlation Platform",
    description="SIH 26189 prototype. All data is synthetic. Findings are "
                "investigative leads requiring human verification.",
    version="0.4.0-phase1",
)

# The prototype is served to a browser on the same host. A wildcard origin
# would let any page on the analyst's machine read case data, so the allowed
# origins are named explicitly (§23). Production would terminate at an
# authenticating gateway and this list would name that gateway only.
ALLOWED_ORIGINS = [
    "http://localhost:8000", "http://127.0.0.1:8000",
    "http://localhost:5173", "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")


@app.middleware("http")
async def no_store_frontend(request, call_next):
    """Never serve a cached board.

    The browser will happily keep index.html and the phase1 assets, which means
    an edit made minutes before a demo silently does not appear. The dataset is
    tiny and the server is local, so there is nothing to gain from caching here.
    """
    response = await call_next(request)
    path = request.url.path
    if path in ("/", "/classic") or path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


app.include_router(router)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
def index():
    """The dark-dashboard shell is the default face now."""
    return FileResponse(os.path.join(FRONTEND, "app.html"))


@app.get("/classic")
def classic():
    """The original detective corkboard, kept intact and reachable."""
    return FileResponse(os.path.join(FRONTEND, "index.html"))


@app.get("/healthz")
def healthz():
    return {"status": "ok"}

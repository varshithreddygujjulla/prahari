"""Shared fixtures. The analysis is expensive, so build it once per session.

Data isolation: the whole suite runs against a COPY of data/ in a temp
directory. Intake commits, decisions and audit blocks written by tests land
in that copy, never in the shipped corpus, and the copy is discarded when the
session ends. The autouse fixture below is what makes that true; every module
that holds a data path is pointed at the copy before any other fixture runs.
"""
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import pipeline, reset_demo_data                    # noqa: E402
from backend.analytics import analyze_structure, score_leads   # noqa: E402
from backend.anomaly import detect_all                          # noqa: E402
from backend.api import routes                                  # noqa: E402
from backend.audit import AuditChain                            # noqa: E402
from backend.cases import decisions                             # noqa: E402
from backend.entity_resolution import resolve                   # noqa: E402
from backend.graph import build, case_clock                     # noqa: E402
from backend.ingestion import intake, load_all, loaders         # noqa: E402
from backend.pipeline import build_payload                      # noqa: E402

# Session-created state that must not leak into the copy either.
_NOT_COPIED = ("audit_chain.json", "decisions.json", "cctv.csv", "gps.csv",
               "social.csv", "__pycache__")


@pytest.fixture(scope="session", autouse=True)
def isolated_data(tmp_path_factory):
    """Point every data path at a scratch copy of data/ for the whole session."""
    src = os.path.abspath(loaders.BASE)
    dst = str(tmp_path_factory.mktemp("data"))
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(*_NOT_COPIED))
    firs = os.path.join(dst, "firs")

    mp = pytest.MonkeyPatch()
    for mod in (loaders, intake, pipeline, reset_demo_data):
        mp.setattr(mod, "BASE", dst)
    for mod in (loaders, intake, reset_demo_data):
        mp.setattr(mod, "FIRS", firs)
    mp.setattr(reset_demo_data, "SEED", os.path.join(dst, "seed"))
    mp.setattr(reset_demo_data, "SEED_FIRS", os.path.join(dst, "seed", "firs"))
    mp.setattr(decisions, "PATH", os.path.join(dst, "decisions.json"))
    mp.setattr(routes, "audit", AuditChain(path=os.path.join(dst, "audit_chain.json")))
    pipeline.invalidate()
    yield dst
    mp.undo()
    pipeline.invalidate()


@pytest.fixture(scope="session")
def records():
    return load_all()


@pytest.fixture(scope="session")
def bundle(records):
    return build(records)


@pytest.fixture(scope="session")
def structure(bundle):
    return analyze_structure(bundle.G)


@pytest.fixture(scope="session")
def clock(records):
    return case_clock(records)


@pytest.fixture(scope="session")
def anomalies(bundle, structure, clock):
    return detect_all(bundle, structure, clock)


@pytest.fixture(scope="session")
def resolution(bundle):
    return resolve(bundle)


@pytest.fixture(scope="session")
def leads(bundle, structure, anomalies, resolution):
    return score_leads(bundle, structure, anomalies, resolution)


@pytest.fixture(scope="session")
def payload():
    return build_payload()

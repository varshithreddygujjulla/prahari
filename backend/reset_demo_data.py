"""
reset_demo_data.py - put data/ back to the shipped demo corpus.

The ADD DATA flow appends rows to the CSVs, writes new FIR files, and creates
staged files (cctv.csv, gps.csv, social.csv); the decision store and the audit
chain grow with every click. Before a demo run you want the exact corpus the
narrative was written against. This script restores it from data/seed/.

    python backend/reset_demo_data.py                # restore data/ from data/seed/
    python backend/reset_demo_data.py --dry-run      # show what would change
    python backend/reset_demo_data.py --keep-audit   # restore, but keep audit_chain.json
    python backend/reset_demo_data.py --snapshot     # (re)create data/seed/ from data/

Stop the API server before restoring: it holds the audit chain in memory and
would write the old chain back on its next request. After a restore, start the
server again (or POST /api/rebuild if it was left running with --keep-audit).

Nothing here touches the seed unless you pass --snapshot, and --snapshot
refuses to overwrite an existing seed without --force.
"""
import argparse
import os
import shutil
import sys

# `python backend/reset_demo_data.py` puts backend/ on sys.path, not the root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.ingestion.loaders import BASE, FIRS  # noqa: E402

SEED = os.path.normpath(os.path.join(BASE, "seed"))
SEED_FIRS = os.path.join(SEED, "firs")

# The corpus proper: every file the loaders read.
CORPUS_FILES = [
    "accounts.csv", "bank.csv", "cdr.csv", "identity_variants.csv",
    "phone_directory.csv", "prison.csv", "travel.csv", "vehicles.csv",
]
# Derived state that a demo session creates. Removed on restore.
DERIVED_FILES = ["decisions.json", "cctv.csv", "gps.csv", "social.csv"]
AUDIT_FILE = "audit_chain.json"


def _fir_files(folder: str):
    if not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder) if f.endswith(".txt"))


def snapshot(force: bool, dry_run: bool) -> int:
    if os.path.isdir(SEED) and not force:
        print(f"seed already exists at {SEED}; pass --force to overwrite it")
        return 1
    print(f"snapshot: data/ -> {SEED}")
    for fn in CORPUS_FILES:
        src = os.path.join(BASE, fn)
        if not os.path.exists(src):
            print(f"  missing {fn} - corpus is incomplete, aborting")
            return 1
        print(f"  copy {fn}")
        if not dry_run:
            os.makedirs(SEED, exist_ok=True)
            shutil.copy2(src, os.path.join(SEED, fn))
    firs = _fir_files(FIRS)
    print(f"  copy firs/ ({len(firs)} files)")
    if not dry_run:
        if os.path.isdir(SEED_FIRS):
            shutil.rmtree(SEED_FIRS)
        os.makedirs(SEED_FIRS)
        for fn in firs:
            shutil.copy2(os.path.join(FIRS, fn), os.path.join(SEED_FIRS, fn))
    print("done" if not dry_run else "dry run - nothing written")
    return 0


def restore(keep_audit: bool, dry_run: bool) -> int:
    if not os.path.isdir(SEED):
        print(f"no seed at {SEED}; run with --snapshot first (from a clean data/)")
        return 1
    changed = 0
    print(f"restore: {SEED} -> data/")
    for fn in CORPUS_FILES:
        src, dst = os.path.join(SEED, fn), os.path.join(BASE, fn)
        if not os.path.exists(src):
            print(f"  seed is missing {fn} - aborting before touching anything")
            return 1
    for fn in CORPUS_FILES:
        src, dst = os.path.join(SEED, fn), os.path.join(BASE, fn)
        same = os.path.exists(dst) and open(src, "rb").read() == open(dst, "rb").read()
        print(f"  {'keep ' if same else 'reset'} {fn}")
        if not same:
            changed += 1
            if not dry_run:
                shutil.copy2(src, dst)

    seed_firs, live_firs = _fir_files(SEED_FIRS), _fir_files(FIRS)
    extra = [f for f in live_firs if f not in seed_firs]
    for fn in extra:
        print(f"  remove firs/{fn} (added during a session)")
        changed += 1
        if not dry_run:
            os.remove(os.path.join(FIRS, fn))
    for fn in seed_firs:
        src, dst = os.path.join(SEED_FIRS, fn), os.path.join(FIRS, fn)
        same = os.path.exists(dst) and open(src, "rb").read() == open(dst, "rb").read()
        if not same:
            print(f"  reset firs/{fn}")
            changed += 1
            if not dry_run:
                os.makedirs(FIRS, exist_ok=True)
                shutil.copy2(src, dst)

    derived = list(DERIVED_FILES) + ([] if keep_audit else [AUDIT_FILE])
    for fn in derived:
        path = os.path.join(BASE, fn)
        if os.path.exists(path):
            print(f"  remove {fn}")
            changed += 1
            if not dry_run:
                os.remove(path)
    if keep_audit:
        print(f"  keep  {AUDIT_FILE} (--keep-audit)")

    if dry_run:
        print(f"dry run - {changed} change(s) would be made, nothing written")
    elif changed:
        print(f"done - {changed} change(s). Start the server again so it reloads "
              "the corpus and begins a fresh audit chain.")
    else:
        print("done - data/ already matched the seed")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--snapshot", action="store_true",
                    help="create data/seed/ from the current data/ instead of restoring")
    ap.add_argument("--force", action="store_true",
                    help="with --snapshot: overwrite an existing seed")
    ap.add_argument("--keep-audit", action="store_true",
                    help="do not delete audit_chain.json on restore")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan without writing anything")
    a = ap.parse_args(argv)
    if a.snapshot:
        return snapshot(a.force, a.dry_run)
    return restore(a.keep_audit, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())

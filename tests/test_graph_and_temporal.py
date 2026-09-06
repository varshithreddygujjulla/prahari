"""
Graph construction, temporal filtering and ingestion.

Includes a regression guard for the original board's numbers: the interaction
graph must stay at 28 people / 69 interaction edges / 3 clusters, because the
demo narrative is built on those.
"""
import pytest

from backend import config
from backend.graph.builder import interaction_subgraph
from backend.graph.temporal import (
    build_events, edge_in_window, filter_events, window_bounds,
)
from backend.ingestion.loaders import parse_dt


# ---------------------------------------------------------------- ingestion
def test_every_record_has_a_unique_stable_id(records):
    seen = set()
    for source, rs in records.items():
        for r in rs:
            assert r.record_id, f"{source} produced a record with no id"
            assert r.record_id not in seen, f"duplicate id {r.record_id}"
            seen.add(r.record_id)


def test_all_original_sources_are_ingested(records):
    for key in ("fir", "cdr", "bank", "phone_directory", "accounts",
                "vehicles", "travel", "prison"):
        assert records[key], f"{key} ingested nothing"


def test_previously_unused_sources_are_now_wired_in(records):
    """travel.csv and vehicles.csv were read by nothing before Phase 1."""
    assert len(records["vehicles"]) == 9
    assert len(records["travel"]) == 8


def test_fir_dates_are_parsed(records):
    dated = [r for r in records["fir"] if r.timestamp]
    assert len(dated) == len(records["fir"]), "every FIR carries a Date: line"


def test_registry_records_are_marked_timeless(records):
    for key in ("phone_directory", "accounts", "vehicles"):
        assert all(r.timeless for r in records[key])


def test_date_parser_handles_every_corpus_format():
    assert parse_dt("2026-03-18 11:00") is not None
    assert parse_dt("2026-03-18") is not None
    assert parse_dt("14-01-2026") is not None
    assert parse_dt("not a date") is None
    assert parse_dt("") is None


# ---------------------------------------------------------------- structure
def test_interaction_graph_matches_the_original_board(bundle):
    """Regression guard on the numbers the demo narrative depends on."""
    H = interaction_subgraph(bundle.G)
    assert H.number_of_edges() == 69
    people = [n for n, d in bundle.G.nodes(data=True) if d.get("kind") == "person"]
    assert len(people) == 28


def test_cluster_count_is_stable(structure):
    assert structure["community_count"] == 3


def test_registry_pendants_do_not_shape_clusters(bundle, structure):
    """Vehicles attach to one owner; they must not vote on cluster boundaries."""
    H = interaction_subgraph(bundle.G)
    for n, d in bundle.G.nodes(data=True):
        if d.get("kind") == "vehicle":
            assert n not in H, "vehicle leaked into the interaction subgraph"
            # but it still receives a community, inherited from its owner
            assert structure["community_of"].get(n, -1) >= 0


def test_vehicles_are_linked_to_their_registered_owner(bundle):
    veh = [n for n, d in bundle.G.nodes(data=True) if d.get("kind") == "vehicle"]
    assert len(veh) == 9
    for v in veh:
        nbrs = list(bundle.G.neighbors(v))
        assert len(nbrs) == 1
        assert bundle.G[v][nbrs[0]]["rel"] == "registered-to"


def test_registered_phones_resolve_to_their_subscriber(bundle):
    """A registered number must not appear as its own node."""
    registered = {r.fields["phone"] for r in bundle.records["phone_directory"]}
    for ph in registered:
        assert ph not in bundle.G, f"{ph} should have resolved to its subscriber"


def test_unresolved_numbers_stand_alone(bundle):
    unresolved = [n for n, d in bundle.G.nodes(data=True)
                  if d.get("kind") == "unresolved_number"]
    assert unresolved, "expected at least one unattributed number"
    registered = {r.fields["phone"] for r in bundle.records["phone_directory"]}
    for n in unresolved:
        assert n not in registered


def test_financial_relationships_map_accounts_to_holders(bundle):
    holders = {r.fields["holder_name"] for r in bundle.records["accounts"]}
    money_edges = [(a, b) for a, b, d in bundle.G.edges(data=True)
                   if "money" in d.get("rel_types", [])]
    assert money_edges
    for a, b in money_edges:
        assert a in holders or b in holders


def test_money_totals_are_conserved(bundle):
    from_csv = sum(float(r.fields["_amount"]) for r in bundle.records["bank"])
    on_edges = sum(d.get("money_inr", 0) or 0
                   for _a, _b, d in bundle.G.edges(data=True))
    assert on_edges == pytest.approx(from_csv, rel=1e-6)


# ---------------------------------------------------------------- temporal
def test_case_clock_anchors_to_the_latest_record_not_today(clock):
    assert clock["anchor"].startswith("2026-03-31")
    assert "latest observed" in clock["anchor_source"]


def test_all_window_keeps_everything(bundle, clock):
    bounds = window_bounds("all", clock)
    edges = [dict(d, **{"from": a, "to": b})
             for a, b, d in bundle.G.edges(data=True)]
    assert all(edge_in_window(e, bounds) for e in edges)


def test_narrower_windows_are_subsets(clock, bundle):
    edges = [dict(d, **{"from": a, "to": b})
             for a, b, d in bundle.G.edges(data=True)]
    counts = {}
    for win in ("24h", "7d", "30d", "all"):
        b = window_bounds(win, clock)
        counts[win] = sum(1 for e in edges if edge_in_window(e, b))
    assert counts["24h"] <= counts["7d"] <= counts["30d"] <= counts["all"]
    assert counts["7d"] < counts["all"], "filtering must actually filter"


def test_timeless_edges_survive_every_window(bundle, clock):
    bounds = window_bounds("24h", clock)
    timeless = [dict(d, **{"from": a, "to": b})
                for a, b, d in bundle.G.edges(data=True) if d.get("timeless")]
    assert timeless, "vehicle registrations have no event date"
    for e in timeless:
        assert edge_in_window(e, bounds), \
            "a registration must not vanish because it has no timestamp"


def test_custody_edges_fall_outside_the_recent_window(bundle, clock):
    """The 2022 custody link should drop out of a 30-day view."""
    bounds = window_bounds("30d", clock)
    for a, b, d in bundle.G.edges(data=True):
        if d.get("rel_types") == ["jailed-together"]:
            assert not edge_in_window(dict(d, **{"from": a, "to": b}), bounds)


def test_custom_window_bounds():
    clock = {"anchor": "2026-03-31T19:00:00", "first_observed": "2026-01-01T00:00:00"}
    b = window_bounds("custom", clock, start="2026-03-01", end="2026-03-10")
    assert b["window"] == "custom"
    assert b["from"].startswith("2026-03-01")
    assert b["to"].startswith("2026-03-10")


# ---------------------------------------------------------------- timeline
def test_timeline_covers_every_event_type(records, bundle):
    events = build_events(records, bundle.call_records)
    types = {e["type"] for e in events}
    for expected in ("FIR", "TRANSACTION", "TRAVEL", "CUSTODY_OVERLAP",
                     "CALL_ACTIVITY", "VEHICLE_REGISTRATION"):
        assert expected in types, f"{expected} missing from the timeline"


def test_calls_are_aggregated_per_day(records, bundle):
    events = build_events(records, bundle.call_records)
    call_days = [e for e in events if e["type"] == "CALL_ACTIVITY"]
    assert call_days
    assert len(call_days) < len(records["cdr"]), "calls should be aggregated"
    assert sum(e["call_count"] for e in call_days) == len(records["cdr"])


def test_timeline_events_cite_records(records, bundle):
    for e in build_events(records, bundle.call_records):
        assert e["source_records"], f"{e['event_id']} cites nothing"


def test_timeline_filtering_respects_the_window(records, bundle, clock):
    events = build_events(records, bundle.call_records)
    narrow = filter_events(events, window_bounds("7d", clock))
    assert len(narrow) < len(events)

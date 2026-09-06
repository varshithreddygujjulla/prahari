"""
Ask PRAHARI — the grounded query layer.

Every answer must come from the case records (no invention) and carry the
verification notice. These tests pin the intent routing and the grounding.
"""
from backend.assistant import answer
from backend.pipeline import analysis


def _a():
    return analysis()


def test_person_summary_is_grounded():
    r = answer("summary of Ramesh Yadav", _a())
    assert r["intent"] == "person_summary"
    assert r["title"] == "Ramesh Yadav"
    assert r["bullets"]
    assert r["disclaimer"]                      # human-verification notice present
    assert "no external model" in r["grounded"].lower()


def test_date_summary_lists_that_days_events():
    r = answer("what happened on 2026-03-18", _a())
    assert r["intent"] == "date_summary"
    assert "2026-03-18" in r["title"]
    assert r["bullets"]


def test_natural_date_phrase_is_parsed():
    r = answer("activity on 18 march", _a())
    assert r["intent"] == "date_summary"
    assert "2026-03-18" in r["title"]


def test_controller_intent():
    r = answer("who is the network controller", _a())
    assert r["intent"] == "controller"
    assert "Vikram Rathore" in r["summary"]
    # never overclaims — it's a lead, not a verdict
    assert "not a" in r["summary"].lower() or "lead" in r["summary"].lower()


def test_connection_between_two_entities():
    r = answer("how are Ramesh Yadav and Salim Qureshi connected", _a())
    assert r["intent"] == "connection"
    assert "Ramesh Yadav" in r["title"] and "Salim Qureshi" in r["title"]


def test_broker_computed_from_graph():
    r = answer("who is the broker", _a())
    assert r["intent"] == "broker"
    assert "9990001111" in r["summary"]


def test_leads_with_threshold():
    r = answer("leads above 50", _a())
    assert r["intent"] == "leads"
    assert r["bullets"]


def test_anomalies_intent():
    r = answer("what looks unusual", _a())
    assert r["intent"] == "anomalies"


def test_unknown_query_offers_help_not_a_guess():
    r = answer("what is the weather", _a())
    assert r["intent"] == "help"
    assert r["bullets"]


def test_empty_query_is_safe():
    r = answer("", _a())
    assert r["intent"] == "help"


def test_answers_never_fabricate_records():
    """Every record an answer cites must be a real record id in the corpus."""
    a = _a()
    known = {r.record_id for rs in a["records"].values() for r in rs}
    for q in ("summary of Ramesh Yadav", "what happened on 2026-03-18",
              "who is the network controller"):
        r = answer(q, a)
        for rid in r["records"]:
            assert rid in known, f"answer to '{q}' cites unknown record {rid}"


# ---- expanded capabilities ----
def test_identifier_lookup_resolves_to_owner():
    r = answer("who owns DL01AB4455", _a())
    assert r["intent"] == "owner"
    assert "Ramesh Yadav" in r["title"]


def test_phone_number_resolves():
    r = answer("whose number is 9990001111", _a())
    assert r["intent"] == "owner"
    # unresolved number → stated as unregistered, not invented owner
    assert "unregist" in r["summary"].lower() or "unresolved" in r["summary"].lower()


def test_money_trail_intent():
    r = answer("who received the most money", _a())
    assert r["intent"] == "money"
    assert r["bullets"]


def test_case_overview_intent():
    r = answer("case summary", _a())
    assert r["intent"] == "overview"
    assert r["bullets"]


def test_count_intent():
    r = answer("how many FIRs", _a())
    assert r["intent"] == "count"
    assert "21" in r["summary"]


def test_fuzzy_name_tolerates_typo():
    r = answer("summry of Rmesh Yadav", _a())
    assert r["intent"] == "person_summary"
    assert r["title"] == "Ramesh Yadav"


def test_followup_context_pronoun():
    a = _a()
    r = answer("what about his money", a, context="Ramesh Yadav")
    assert r["intent"] == "money"
    assert "Ramesh Yadav" in r["title"]


def test_focus_is_returned_for_memory():
    r = answer("summary of Vikram Rathore", _a())
    assert r.get("focus") == "Vikram Rathore"

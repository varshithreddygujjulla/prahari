"""
detectors.py — the anomaly suite.

Every detector returns findings in one shape so the UI, the lead scorer and the
brief generator can consume them uniformly:

    anomaly_type, severity, confidence, timestamp, entities_involved,
    evidence[], source_records[], explanation, baseline{}, algorithm

Two rules shape the wording of every `explanation`:

  * state the deviation against a baseline ("8.2x this pair's median day"),
    never a bare adjective like "suspicious";
  * describe the observation, not the person. "Communication volume rose"
    is a fact in the records; "X is a trafficker" is not.

Robust statistics are used throughout (median and MAD rather than mean and
standard deviation), because a single 7-lakh transfer would drag a mean-based
threshold far enough to hide itself.
"""
import hashlib
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from backend import config
from backend.ingestion import Record

DETECTORS: List[str] = []


def _register(fn):
    DETECTORS.append(fn.__name__)
    return fn


def _dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _severity(value: float, high: float, critical: Optional[float] = None) -> str:
    if critical is not None and value >= critical:
        return "CRITICAL"
    if value >= high:
        return "HIGH"
    if value >= high * 0.6:
        return "MEDIUM"
    return "LOW"


def _confidence(effect: float, sample: int, ceiling: int = 92) -> int:
    """How sure we are the pattern is not noise.

    Grows with both effect size and how much data supports it. Deliberately
    capped below 100 — a statistical deviation is never proof.
    """
    effect_part = min(45.0, effect * 7.0)
    sample_part = min(35.0, sample * 2.2)
    return int(max(20, min(ceiling, 20 + effect_part + sample_part)))


def _finding(kind: str, severity: str, confidence: int,
             timestamp: Optional[str], entities: List[str],
             records: List[Record], explanation: str,
             algorithm: str, baseline: Dict[str, Any],
             **extra) -> Dict[str, Any]:
    return {
        # Deterministic id: Python's hash() is salted per process, which made
        # ids change on every restart and broke anything that referenced them.
        "anomaly_id": "AN-" + kind + "-" + hashlib.sha1(
            (kind + "|" + "|".join(sorted(entities)) + "|" + str(timestamp)).encode("utf-8")
        ).hexdigest()[:8],
        "anomaly_type": kind,
        "severity": severity,
        "confidence": confidence,
        "timestamp": timestamp,
        "entities_involved": entities,
        "evidence": [r.cite() for r in records[:12]],
        "source_records": [r.record_id for r in records],
        "evidence_truncated": max(0, len(records) - 12),
        "source_types": sorted({r.source_type for r in records}),
        "explanation": explanation,
        "algorithm": algorithm,
        "baseline": baseline,
        "verification_notice": config.HUMAN_VERIFICATION_NOTICE,
        **extra,
    }


# ================================================================ communication
@_register
def communication_volume_spike(ctx) -> List[Dict[str, Any]]:
    """A contact pair's busiest day against that pair's own typical day."""
    cfg = config.ANOMALY_CONFIG["comm_spike"]
    if not cfg["enabled"]:
        return []
    out = []
    for pair, recs in ctx["call_records"].items():
        dated = [r for r in recs if r.timestamp]
        if len(dated) < cfg["min_total_calls"]:
            continue
        per_day: Dict[str, List[Record]] = defaultdict(list)
        for r in dated:
            per_day[r.timestamp[:10]].append(r)
        counts = sorted(len(v) for v in per_day.values())
        peak_day, peak_recs = max(per_day.items(), key=lambda kv: len(kv[1]))
        peak = len(peak_recs)
        if peak < cfg["min_peak_calls"]:
            continue
        # Baseline is the median active day excluding the peak itself.
        others = counts[:-1] or [1]
        baseline = statistics.median(others)
        ratio = peak / baseline if baseline else float(peak)
        if ratio < cfg["min_ratio"]:
            continue
        a, b = pair
        out.append(_finding(
            "COMMUNICATION_VOLUME_SPIKE",
            _severity(ratio, cfg["severity_ratio_high"], cfg["severity_ratio_critical"]),
            _confidence(ratio, len(dated)),
            f"{peak_day}T00:00:00", [a, b], peak_recs,
            explanation=(f"Communication volume between {a} and {b} reached "
                         f"{peak} calls on {peak_day} — {ratio:.1f}x this pair's "
                         f"median active day of {baseline:g}. Observed across "
                         f"{len(dated)} calls in total."),
            algorithm="per-pair daily volume vs pair-specific median baseline",
            baseline={"metric": "calls per active day", "baseline": baseline,
                      "observed": peak, "ratio": round(ratio, 2),
                      "active_days": len(per_day), "total_calls": len(dated)},
            pair=f"{a} ↔ {b}", date=peak_day, calls_that_day=peak,
            total_calls=len(dated),
        ))
    return sorted(out, key=lambda x: -x["baseline"]["ratio"])


@_register
def entity_communication_surge(ctx) -> List[Dict[str, Any]]:
    """One entity's total daily volume against its own baseline."""
    cfg = config.ANOMALY_CONFIG["entity_surge"]
    if not cfg["enabled"]:
        return []
    by_entity: Dict[str, List[Record]] = defaultdict(list)
    for pair, recs in ctx["call_records"].items():
        for node in pair:
            by_entity[node].extend(r for r in recs if r.timestamp)

    out = []
    for entity, recs in by_entity.items():
        if len(recs) < cfg["min_total_calls"]:
            continue
        per_day: Dict[str, List[Record]] = defaultdict(list)
        for r in recs:
            per_day[r.timestamp[:10]].append(r)
        if len(per_day) < 3:
            continue
        counts = sorted(len(v) for v in per_day.values())
        peak_day, peak_recs = max(per_day.items(), key=lambda kv: len(kv[1]))
        baseline = statistics.median(counts[:-1] or [1])
        ratio = len(peak_recs) / baseline if baseline else float(len(peak_recs))
        if ratio < cfg["min_ratio"]:
            continue
        out.append(_finding(
            "ENTITY_COMMUNICATION_SURGE",
            _severity(ratio, cfg["severity_ratio_high"]),
            _confidence(ratio, len(recs)),
            f"{peak_day}T00:00:00", [entity], peak_recs,
            explanation=(f"Total communication activity for {entity} rose to "
                         f"{len(peak_recs)} calls on {peak_day} — {ratio:.1f}x "
                         f"this entity's median daily volume of {baseline:g}."),
            algorithm="per-entity daily volume vs entity-specific median baseline",
            baseline={"metric": "calls per active day", "baseline": baseline,
                      "observed": len(peak_recs), "ratio": round(ratio, 2),
                      "active_days": len(per_day)},
        ))
    return sorted(out, key=lambda x: -x["baseline"]["ratio"])


@_register
def new_communication_relationship(ctx) -> List[Dict[str, Any]]:
    """A contact pair whose first-ever call falls late in the window."""
    cfg = config.ANOMALY_CONFIG["new_relationship"]
    if not cfg["enabled"]:
        return []
    lo, hi = ctx["window_start"], ctx["window_end"]
    if not lo or not hi or hi <= lo:
        return []
    span = (hi - lo).total_seconds()
    cutoff = lo + timedelta(seconds=span * cfg["late_fraction"])

    out = []
    for pair, recs in ctx["call_records"].items():
        dated = sorted((r for r in recs if r.timestamp), key=lambda r: r.timestamp)
        if len(dated) < cfg["min_calls_after"]:
            continue
        first = _dt(dated[0].timestamp)
        if not first or first < cutoff:
            continue
        a, b = pair
        frac = (first - lo).total_seconds() / span
        out.append(_finding(
            "NEW_COMMUNICATION_RELATIONSHIP",
            "MEDIUM" if len(dated) < 6 else "HIGH",
            _confidence(len(dated) / 2.0, len(dated)),
            dated[0].timestamp, [a, b], dated,
            explanation=(f"No contact was recorded between {a} and {b} for the "
                         f"first {frac:.0%} of the observation window. The "
                         f"relationship first appears on {dated[0].timestamp[:10]} "
                         f"and then accounts for {len(dated)} calls."),
            algorithm="first-contact timestamp vs observation window position",
            baseline={"metric": "window position of first contact",
                      "observed": round(frac, 3),
                      "threshold": cfg["late_fraction"],
                      "calls_after_first_contact": len(dated)},
        ))
    return out


@_register
def cross_community_communication(ctx) -> List[Dict[str, Any]]:
    """Sustained contact bridging two detected clusters."""
    cfg = config.ANOMALY_CONFIG["cross_community_comm"]
    if not cfg["enabled"]:
        return []
    comm = ctx["community_of"]
    out = []
    for pair, recs in ctx["call_records"].items():
        if len(recs) < cfg["min_calls"]:
            continue
        a, b = pair
        ca, cb = comm.get(a, -1), comm.get(b, -1)
        if ca == cb or ca < 0 or cb < 0:
            continue
        ts = sorted(r.timestamp for r in recs if r.timestamp)
        out.append(_finding(
            "CROSS_COMMUNITY_COMMUNICATION",
            "HIGH" if len(recs) >= 6 else "MEDIUM",
            _confidence(len(recs) / 3.0, len(recs)),
            ts[-1] if ts else None, [a, b], recs,
            explanation=(f"{len(recs)} calls connect {a} (cluster {ca}) with "
                         f"{b} (cluster {cb}). Contact that crosses cluster "
                         f"boundaries is structurally uncommon — most traffic "
                         f"stays inside a cluster."),
            algorithm="community membership comparison over CDR pairs",
            baseline={"metric": "calls bridging clusters", "observed": len(recs),
                      "threshold": cfg["min_calls"],
                      "clusters": [ca, cb]},
        ))
    return sorted(out, key=lambda x: -x["baseline"]["observed"])


@_register
def connectivity_surge(ctx) -> List[Dict[str, Any]]:
    """An entity acquiring several new contacts late in the window."""
    cfg = config.ANOMALY_CONFIG["connectivity_surge"]
    if not cfg["enabled"]:
        return []
    lo, hi = ctx["window_start"], ctx["window_end"]
    if not lo or not hi or hi <= lo:
        return []
    span = (hi - lo).total_seconds()
    cutoff = lo + timedelta(seconds=span * cfg["late_fraction"])

    first_contact: Dict[str, Dict[str, Any]] = defaultdict(dict)
    for pair, recs in ctx["call_records"].items():
        dated = sorted((r for r in recs if r.timestamp), key=lambda r: r.timestamp)
        if not dated:
            continue
        a, b = pair
        first_contact[a][b] = dated[0]
        first_contact[b][a] = dated[0]

    out = []
    for entity, contacts in first_contact.items():
        new = {c: r for c, r in contacts.items() if _dt(r.timestamp) >= cutoff}
        if len(new) < cfg["min_new_contacts"]:
            continue
        recs = list(new.values())
        out.append(_finding(
            "CONNECTIVITY_SURGE",
            "HIGH" if len(new) >= 3 else "MEDIUM",
            _confidence(len(new), len(contacts)),
            max(r.timestamp for r in recs), [entity] + sorted(new),
            recs,
            explanation=(f"{entity} established contact with {len(new)} new "
                         f"parties in the final {1 - cfg['late_fraction']:.0%} of "
                         f"the observation window, against {len(contacts)} "
                         f"contacts overall."),
            algorithm="count of first-contact timestamps in the late window",
            baseline={"metric": "new contacts in late window",
                      "observed": len(new), "total_contacts": len(contacts),
                      "threshold": cfg["min_new_contacts"]},
        ))
    return sorted(out, key=lambda x: -x["baseline"]["observed"])


# ==================================================================== financial
@_register
def unusual_transaction_amount(ctx) -> List[Dict[str, Any]]:
    """Transfer amounts far from the corpus median, by median absolute deviation."""
    cfg = config.ANOMALY_CONFIG["transaction_amount"]
    if not cfg["enabled"]:
        return []
    bank = [r for r in ctx["records"].get("bank", [])
            if float(r.fields.get("_amount", 0) or 0) > 0]
    if len(bank) < cfg["min_records"]:
        return []
    amounts = [float(r.fields["_amount"]) for r in bank]
    med = statistics.median(amounts)
    mad = statistics.median([abs(a - med) for a in amounts]) or 1.0
    out = []
    for r in bank:
        amt = float(r.fields["_amount"])
        dev = (amt - med) / mad
        if dev < cfg["mad_multiplier"]:
            continue
        holder = ctx["acct_owner"].get(r.fields.get("to_account", ""),
                                       r.fields.get("to_account", ""))
        sender = ctx["acct_owner"].get(r.fields.get("from_account", ""),
                                       r.fields.get("from_account", ""))
        out.append(_finding(
            "UNUSUAL_TRANSACTION_AMOUNT",
            _severity(dev, cfg["severity_multiplier_high"],
                      cfg["severity_multiplier_critical"]),
            _confidence(dev / 2.0, len(bank)),
            r.timestamp, [sender, holder], [r],
            explanation=(f"A transfer of ₹{amt:,.0f} to {holder} sits "
                         f"{dev:.1f} median-absolute-deviations above the "
                         f"corpus median of ₹{med:,.0f}. Median-based bounds "
                         f"are used so a single large transfer cannot raise "
                         f"the threshold that would catch it."),
            algorithm="robust outlier detection (median + median absolute deviation)",
            baseline={"metric": "transfer amount (INR)", "baseline": med,
                      "observed": amt, "deviations": round(dev, 2),
                      "mad": mad, "sample": len(bank)},
            amount_inr=amt,
        ))
    return sorted(out, key=lambda x: -x["baseline"]["deviations"])


@_register
def rapid_money_movement(ctx) -> List[Dict[str, Any]]:
    """Funds arriving and leaving the same entity inside a short window."""
    cfg = config.ANOMALY_CONFIG["rapid_money_movement"]
    if not cfg["enabled"]:
        return []
    inflow: Dict[str, List[Record]] = defaultdict(list)
    outflow: Dict[str, List[Record]] = defaultdict(list)
    for r in ctx["records"].get("bank", []):
        fa, ta = r.fields.get("from_account", ""), r.fields.get("to_account", "")
        outflow[ctx["acct_owner"].get(fa, fa)].append(r)
        inflow[ctx["acct_owner"].get(ta, ta)].append(r)

    out = []
    for entity, ins in inflow.items():
        outs = outflow.get(entity, [])
        if not outs:
            continue
        total_in = sum(float(r.fields.get("_amount", 0) or 0) for r in ins)
        total_out = sum(float(r.fields.get("_amount", 0) or 0) for r in outs)
        if total_in < cfg["min_amount_inr"]:
            continue
        # A pass-through share above 100% is impossible; outflow beyond the
        # inflow came from elsewhere. Cap, and say so in the baseline.
        ratio = min(1.0, total_out / total_in) if total_in else 0
        if ratio < cfg["min_pass_through_ratio"]:
            continue
        # Do the outbound transfers follow the inbound ones closely in time?
        in_times = sorted(t for t in (_dt(r.timestamp) for r in ins) if t)
        out_times = sorted(t for t in (_dt(r.timestamp) for r in outs) if t)
        if not in_times or not out_times:
            continue
        lag_days = (out_times[-1] - in_times[0]).days
        if lag_days > cfg["window_days"] * 3:
            continue
        recs = ins + outs
        out.append(_finding(
            "RAPID_MONEY_MOVEMENT",
            "HIGH" if ratio >= 0.85 else "MEDIUM",
            _confidence(ratio * 4, len(recs)),
            out_times[-1].isoformat(timespec="seconds"), [entity], recs,
            explanation=(f"{entity} received ₹{total_in:,.0f} across "
                         f"{len(ins)} transfers and forwarded ₹{total_out:,.0f} "
                         f"across {len(outs)} transfers — {ratio:.0%} of the "
                         f"inflow moved on again within {max(lag_days, 0)} days. "
                         f"Funds passing straight through an account is the "
                         f"shape layering takes."),
            algorithm="inflow/outflow ratio with temporal lag over a rolling window",
            baseline={"metric": "pass-through ratio", "observed": round(ratio, 3),
                      "threshold": cfg["min_pass_through_ratio"],
                      "total_in_inr": total_in, "total_out_inr": total_out,
                      "lag_days": max(lag_days, 0)},
        ))
    return sorted(out, key=lambda x: -x["baseline"]["observed"])


@_register
def structured_transactions(ctx) -> List[Dict[str, Any]]:
    """Several similar-sized transfers converging on one beneficiary."""
    cfg = config.ANOMALY_CONFIG["structured_transactions"]
    if not cfg["enabled"]:
        return []
    by_target: Dict[str, List[Record]] = defaultdict(list)
    for r in ctx["records"].get("bank", []):
        ta = r.fields.get("to_account", "")
        by_target[ctx["acct_owner"].get(ta, ta)].append(r)

    out = []
    for target, recs in by_target.items():
        senders = {r.fields.get("from_account", "") for r in recs}
        if len(senders) < cfg["min_senders"]:
            continue
        amounts = [float(r.fields.get("_amount", 0) or 0) for r in recs]
        if not amounts:
            continue
        med = statistics.median(amounts)
        if med <= 0:
            continue
        similar = [a for a in amounts
                   if abs(a - med) / med <= cfg["amount_similarity"]]
        if len(similar) < cfg["min_senders"]:
            continue
        times = sorted(t for t in (_dt(r.timestamp) for r in recs) if t)
        span_days = (times[-1] - times[0]).days if len(times) > 1 else 0
        if span_days > cfg["window_days"]:
            continue
        out.append(_finding(
            "STRUCTURED_TRANSACTION_PATTERN",
            "HIGH" if len(similar) >= 5 else "MEDIUM",
            _confidence(len(similar), len(recs)),
            times[-1].isoformat(timespec="seconds") if times else None,
            [target], recs,
            explanation=(f"{len(similar)} transfers of comparable size "
                         f"(median ₹{med:,.0f}, within "
                         f"±{cfg['amount_similarity']:.0%}) reached {target} "
                         f"from {len(senders)} different accounts inside "
                         f"{span_days} days. Splitting a sum across similar "
                         f"transfers is consistent with structuring."),
            algorithm="beneficiary fan-in with amount-similarity clustering",
            baseline={"metric": "similar-sized inbound transfers",
                      "observed": len(similar), "senders": len(senders),
                      "median_amount_inr": med, "span_days": span_days},
        ))
    return sorted(out, key=lambda x: -x["baseline"]["observed"])


# ==================================================================== movement
@_register
def travel_after_inflow(ctx) -> List[Dict[str, Any]]:
    """International departure shortly after a large credit."""
    cfg = config.ANOMALY_CONFIG["travel_after_inflow"]
    if not cfg["enabled"]:
        return []
    credits: Dict[str, List[Record]] = defaultdict(list)
    for r in ctx["records"].get("bank", []):
        ta = r.fields.get("to_account", "")
        credits[ctx["acct_owner"].get(ta, ta)].append(r)

    out = []
    for r in ctx["records"].get("travel", []):
        name = r.fields.get("passenger_name", "").strip()
        dest = r.fields.get("to_city", "").strip()
        tdt = _dt(r.timestamp)
        if not name or not tdt:
            continue
        international = dest in cfg["international_cities"]
        recent = []
        for c in credits.get(name, []):
            cdt = _dt(c.timestamp)
            amt = float(c.fields.get("_amount", 0) or 0)
            if not cdt or amt < cfg["min_amount_inr"]:
                continue
            gap = (tdt - cdt).days
            if 0 <= gap <= cfg["window_days"]:
                recent.append((c, amt, gap))
        if not recent:
            continue
        total = sum(a for _, a, _ in recent)
        gap = min(g for _, _, g in recent)
        recs = [r] + [c for c, _, _ in recent]
        out.append(_finding(
            "TRAVEL_FOLLOWING_LARGE_CREDIT",
            "HIGH" if international else "MEDIUM",
            _confidence(3.0 if international else 1.5, len(recs)),
            r.timestamp, [name], recs,
            explanation=(f"{name} travelled {r.fields.get('from_city','?')} → "
                         f"{dest} on {r.timestamp[:10]}, {gap} day(s) after "
                         f"receiving ₹{total:,.0f} across {len(recent)} "
                         f"credit(s)."
                         + (f" {dest} is an international destination."
                            if international else "")),
            algorithm="temporal join of travel manifests against large credits",
            baseline={"metric": "days between credit and departure",
                      "observed": gap, "threshold": cfg["window_days"],
                      "credit_total_inr": total,
                      "international": international},
        ))
    return sorted(out, key=lambda x: (not x["baseline"]["international"],
                                      x["baseline"]["observed"]))


@_register
def pre_event_activity_cluster(ctx) -> List[Dict[str, Any]]:
    """Activity concentrated in the hours before a dated FIR.

    Reference events are the FIRs themselves — actual records with actual
    dates. The system does not invent an incident to correlate against.
    """
    cfg = config.ANOMALY_CONFIG["pre_event_cluster"]
    if not cfg["enabled"]:
        return []
    timed: List[Record] = []
    for key in ("cdr", "bank", "travel"):
        timed.extend(r for r in ctx["records"].get(key, []) if r.timestamp)

    # Who is a record about? Only activity by the FIR-named people counts,
    # otherwise everyone else's calls in those 72 hours get charged to them.
    phone_owner, acct_owner = ctx.get("phone_owner", {}), ctx.get("acct_owner", {})
    def parties(r: Record) -> set:
        f = r.fields
        if r.source == "cdr":
            return {phone_owner.get(f.get("caller", ""), f.get("caller", "")),
                    phone_owner.get(f.get("receiver", ""), f.get("receiver", ""))}
        if r.source == "bank":
            return {acct_owner.get(f.get("from_account", ""), f.get("from_account", "")),
                    acct_owner.get(f.get("to_account", ""), f.get("to_account", ""))}
        if r.source == "travel":
            return {f.get("passenger_name", "")}
        return set()

    out = []
    for fir in ctx["records"].get("fir", []):
        fdt = _dt(fir.timestamp)
        if not fdt:
            continue
        named = set(fir.fields.get("names", []))
        lo = fdt - timedelta(hours=cfg["lookback_hours"])
        window = [r for r in timed
                  if lo <= (_dt(r.timestamp) or fdt) <= fdt and (parties(r) & named)]
        if len(window) < cfg["min_events"]:
            continue
        by_source = defaultdict(int)
        for r in window:
            by_source[r.source_type] += 1
        breakdown = ", ".join(f"{v} {k.lower().replace('_', ' ')}"
                              for k, v in sorted(by_source.items()))
        out.append(_finding(
            "PRE_EVENT_ACTIVITY_CLUSTER",
            "MEDIUM" if len(window) < cfg["min_events"] * 2 else "HIGH",
            _confidence(len(window) / 3.0, len(window)),
            fir.timestamp, list(fir.fields.get("names", [])),
            [fir] + window,
            explanation=(f"{len(window)} recorded activities fall in the "
                         f"{cfg['lookback_hours']} hours before {fir.record_id} "
                         f"was registered on {fir.timestamp[:10]} "
                         f"({breakdown}). Temporal proximity is a lead to "
                         f"examine, not evidence of a connection to the offence."),
            algorithm="fixed-lookback event density around dated FIR records",
            baseline={"metric": f"activity in {cfg['lookback_hours']}h before FIR",
                      "observed": len(window), "threshold": cfg["min_events"],
                      "reference_event": fir.record_id},
        ))
    return sorted(out, key=lambda x: -x["baseline"]["observed"])


# ==================================================================== runner
def detect_all(bundle, structure, clock) -> List[Dict[str, Any]]:
    """Run every enabled detector and return findings ranked by severity."""
    acct_owner: Dict[str, str] = {}
    for r in bundle.records.get("accounts", []):
        ac = r.fields.get("account", "").strip()
        nm = r.fields.get("holder_name", "").strip()
        if ac and nm:
            acct_owner[ac] = nm
    phone_owner: Dict[str, str] = {}
    for r in bundle.records.get("phone_directory", []):
        ph = r.fields.get("phone", "").strip()
        nm = r.fields.get("registered_name", "").strip()
        if ph and nm:
            phone_owner[ph] = nm

    # Communication detectors must measure against the window the CDR data
    # actually covers (March 2026), not the whole corpus — the custody roster
    # reaches back to 2021, and anchoring to that would make every call in the
    # case look like a brand-new relationship in the "late" window.
    comm_stamps = sorted(r.timestamp for rs in bundle.call_records.values()
                         for r in rs if r.timestamp)
    ctx = {
        "G": bundle.G,
        "records": bundle.records,
        "call_records": bundle.call_records,
        "community_of": structure["community_of"],
        "acct_owner": acct_owner,
        "phone_owner": phone_owner,
        "window_start": _dt(comm_stamps[0]) if comm_stamps
        else _dt(clock.get("first_observed")),
        "window_end": _dt(comm_stamps[-1]) if comm_stamps
        else _dt(clock.get("last_observed")),
        "corpus_start": _dt(clock.get("first_observed")),
        "corpus_end": _dt(clock.get("last_observed")),
    }

    findings: List[Dict[str, Any]] = []
    for name in DETECTORS:
        fn = globals()[name]
        try:
            findings.extend(fn(ctx))
        except Exception as exc:                      # pragma: no cover
            # A failing detector must not take the whole board down.
            findings.append({
                "anomaly_id": f"AN-ERROR-{name}",
                "anomaly_type": "DETECTOR_ERROR",
                "severity": "LOW", "confidence": 0, "timestamp": None,
                "entities_involved": [], "evidence": [], "source_records": [],
                "explanation": f"Detector '{name}' failed: {exc}",
                "algorithm": name, "baseline": {},
                "verification_notice": config.HUMAN_VERIFICATION_NOTICE,
            })

    findings.sort(key=lambda f: (-config.SEVERITY_ORDER.get(f["severity"], 0),
                                 -f["confidence"]))
    return findings

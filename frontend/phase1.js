/* ===========================================================================
   phase1.js — Phase 1 behaviour: observation window, timeline, lead scores,
   entity resolution, evidence drawer.

   Loaded as a second classic script, so it shares the global lexical scope
   with index.html and can read DATA / network / edgesDS and call openDossier,
   dimExcept, focusOn and toast directly.

   Window filtering changes which RELATIONSHIPS are drawn, not which entities
   exist. Rebuilding the whole network on every window change would scatter the
   board's layout and lose the investigator's mental map, so only the edge
   DataSet is swapped and node positions stay put. Roles, leads and identity
   candidates stay computed over the full record set — narrowing the view
   should not silently change who the system considers central.
   =========================================================================== */
(function () {
  "use strict";

  var FULL = null;          // payload for window=all
  var CURRENT_WINDOW = "all";
  var $$ = function (id) { return document.getElementById(id); };

  var FACTOR_CLASS = {
    "Financial anomaly": "f-financial",
    "Cross-community connection": "f-cross",
    "Communication anomaly": "f-comms",
    "Temporal correlation": "f-temporal",
    "Location correlation": "f-location",
    "Multi-source confirmation": "f-multi",
    "Network centrality": "f-centrality",
    "Entity resolution": "f-er"
  };

  function esc(s) {
    return String(s === undefined || s === null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function inr(n) { return "₹" + Number(n || 0).toLocaleString("en-IN"); }
  function shortTime(t) { return t ? String(t).slice(0, 16).replace("T", " ") : "—"; }

  /* ===================================================== evidence drawer */
  function openDrawer(title, html) {
    $$("dwTitle").textContent = title;
    $$("dwBody").innerHTML = html;
    $$("drawer").hidden = false;
  }
  window.closeDrawer = function () { $$("drawer").hidden = true; };

  function sec(label, body) {
    return '<div class="dw-sec"><div class="dw-lbl">' + esc(label) + "</div>" + body + "</div>";
  }
  function recordList(records, truncated) {
    if (!records || !records.length) return '<div class="dw-txt">No source records.</div>';
    var html = records.map(function (r) {
      return '<div class="rec" data-record="' + esc(r.record_id) + '">' +
        '<span class="rec-src">' + esc(r.source_type || "") + "</span>" +
        '<span class="rec-id">' + esc(r.record_id) + "</span>" +
        '<div class="rec-detail">' + esc(r.detail || "") +
        (r.timestamp ? '  ·  ' + esc(shortTime(r.timestamp)) : "") + "</div></div>";
    }).join("");
    if (truncated) {
      html += '<div class="dw-txt" style="font-size:11px;color:#8A7550">+ ' +
        truncated + " further record(s) not shown</div>";
    }
    return html;
  }
  function uncertaintyBlock(list) {
    if (!list || !list.length) return "";
    return sec("Uncertainty", list.map(function (u) {
      return '<div class="unc">' + esc(u) + "</div>";
    }).join(""));
  }
  function confidenceBlock(conf, breakdown) {
    var html = '<div class="dw-kv"><span>Confidence</span><b>' + esc(conf) + "%</b></div>";
    if (breakdown && breakdown.length) {
      html += breakdown.map(function (b) {
        return '<div class="conf-row"><span>' + esc(b.factor) + " — " +
          esc(b.detail) + "</span><b>" + (b.points > 0 ? "+" : "") +
          esc(b.points) + "</b></div>";
      }).join("");
    }
    return sec("How this number was derived", html);
  }

  /* -- relationship: why are these two linked? -------------------------- */
  function openRelationshipDrawer(a, b) {
    fetch("/api/relationship?a=" + encodeURIComponent(a) + "&b=" + encodeURIComponent(b))
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (e) {
        var html = sec("Why flagged",
          '<div class="dw-txt">A relationship between <b>' + esc(a) + "</b> and <b>" +
          esc(b) + "</b> is asserted because the source records below place them " +
          "together. Relations observed: " +
          esc((e.rel_types || [e.rel]).join(", ")) + ".</div>");

        html += sec("Relationship", '<div class="dw-kv"><span>Type</span>' +
          esc((e.rel_types || []).join(", ") || e.rel) + "</div>" +
          '<div class="dw-kv"><span>First observed</span>' + esc(shortTime(e.start_time)) + "</div>" +
          '<div class="dw-kv"><span>Last observed</span>' + esc(shortTime(e.last_observed)) + "</div>" +
          '<div class="dw-kv"><span>Observations</span>' + esc(e.observation_count) + "</div>" +
          (e.money_inr ? '<div class="dw-kv"><span>Value moved</span>' + inr(e.money_inr) + "</div>" : "") +
          (e.calls ? '<div class="dw-kv"><span>Calls</span>' + esc(e.calls) + "</div>" : "") +
          '<div class="dw-kv"><span>Source types</span>' + esc((e.source_types || []).join(", ")) + "</div>");

        html += sec("Algorithm", '<div class="dw-txt">' + esc(e.algorithm) + "</div>");
        html += confidenceBlock(e.confidence, e.confidence_breakdown);

        if (e.relations && e.relations.length > 1) {
          html += sec("Relations on this link", e.relations.map(function (r) {
            return '<div class="conf-row"><span>' + esc(r.rel) + " · " +
              esc(r.observation_count) + " observation(s) · " +
              esc(shortTime(r.start_time)) + "</span><b>" + esc(r.confidence) + "%</b></div>";
          }).join(""));
        }
        html += sec("Evidence (" + (e.source_records || []).length + " records)",
          recordList(e.evidence, e.evidence_truncated));
        html += uncertaintyBlock(e.uncertainty);
        html += '<div class="notice">' + esc(e.verification_notice || "") + "</div>";
        openDrawer(a + "  ↔  " + b, html);
      })
      .catch(function () { toast("No recorded relationship between those entities."); });
  }

  /* -- one source record ------------------------------------------------- */
  function openRecordDrawer(recordId) {
    fetch("/api/evidence/" + encodeURIComponent(recordId))
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (d) {
        var rec = d.record;
        var fields = Object.keys(rec.fields || {}).map(function (k) {
          var v = rec.fields[k];
          if (Array.isArray(v)) v = v.join(", ");
          return '<div class="dw-kv"><span>' + esc(k) + "</span>" + esc(v) + "</div>";
        }).join("");
        var html = sec("Source", '<div class="dw-kv"><span>Record</span>' + esc(rec.record_id) + "</div>" +
          '<div class="dw-kv"><span>File</span>' + esc(rec.source_file) + "</div>" +
          '<div class="dw-kv"><span>Type</span>' + esc(rec.source_type) + "</div>" +
          '<div class="dw-kv"><span>Timestamp</span>' +
          esc(rec.timeless ? "no event time (registry record)" : shortTime(rec.timestamp)) + "</div>");
        html += sec("Record contents", fields);
        html += sec("Description", '<div class="dw-txt">' + esc(d.source_type_description) + "</div>");
        if (d.supports && d.supports.length) {
          html += sec("What this record supports", d.supports.map(function (s) {
            return '<div class="conf-row"><span>' +
              (s.type === "edge"
                ? esc(s.subject) + " ↔ " + esc(s.object) + " (" + esc(s.rel) + ")"
                : esc(s.headline)) + "</span><b>" + esc(s.type) + "</b></div>";
          }).join(""));
        }
        if (rec.issues && rec.issues.length) html += uncertaintyBlock(rec.issues);
        openDrawer("Record " + recordId, html);
      })
      .catch(function () { toast("Record not found: " + recordId); });
  }

  /* -- a lead's score breakdown ------------------------------------------ */
  function openLeadDrawer(entity) {
    var lead = (FULL.leads || []).filter(function (l) { return l.entity === entity; })[0];
    if (!lead) { toast("No lead score for " + entity); return; }
    var html = sec("Why flagged",
      '<div class="dw-txt"><b>' + esc(entity) + "</b> scores <b>" + lead.lead_score +
      "/100</b> (" + esc(lead.band) + "). The score is the sum of the independent " +
      "signals below; each one is capped, so no single signal can carry a lead " +
      "on its own.</div>");

    html += sec("Score breakdown", lead.factors.map(function (f) {
      return '<div class="conf-row"><span>' + esc(f.factor) + " — " +
        esc(f.reason) + '</span><b>+' + f.points + "/" + f.max_points + "</b></div>";
    }).join(""));

    html += sec("Entity", '<div class="dw-kv"><span>Named in FIR</span>' +
      (lead.in_fir ? "yes" : "no") + "</div>" +
      '<div class="dw-kv"><span>Funds in</span>' + inr(lead.money_in) + "</div>" +
      '<div class="dw-kv"><span>Funds out</span>' + inr(lead.money_out) + "</div>" +
      '<div class="dw-kv"><span>Cluster</span>#' + esc(lead.community) + "</div>");

    var anos = (FULL.anomalies || []).filter(function (a) {
      return (a.entities_involved || []).indexOf(entity) >= 0;
    });
    if (anos.length) {
      html += sec("Supporting findings (" + anos.length + ")", anos.slice(0, 6).map(function (a) {
        return '<div class="rec" data-anomaly="' + esc(a.anomaly_id) + '">' +
          '<span class="rec-src">' + esc(a.severity) + "</span>" +
          '<span class="rec-id">' + esc(a.anomaly_type) + "</span>" +
          '<div class="rec-detail">' + esc(a.explanation) + "</div></div>";
      }).join(""));
    }
    html += uncertaintyBlock(lead.uncertainty);
    html += '<div class="notice">' + esc(lead.disclaimer) + "<br>" +
      esc(lead.verification_notice) + "</div>";
    openDrawer("Lead · " + entity, html);
  }

  /* -- an anomaly finding ------------------------------------------------- */
  function openAnomalyDrawer(id) {
    var a = (FULL.anomalies || []).filter(function (x) { return x.anomaly_id === id; })[0];
    if (!a) return;
    var b = a.baseline || {};
    var html = sec("Why flagged", '<div class="dw-txt">' + esc(a.explanation) + "</div>");
    html += sec("Measurement", Object.keys(b).map(function (k) {
      return '<div class="dw-kv"><span>' + esc(k.replace(/_/g, " ")) + "</span>" +
        esc(Array.isArray(b[k]) ? b[k].join(", ") : b[k]) + "</div>";
    }).join(""));
    html += sec("Detail", '<div class="dw-kv"><span>Severity</span><b class="pill p-' +
      esc(a.severity) + '">' + esc(a.severity) + "</b></div>" +
      '<div class="dw-kv"><span>Confidence</span>' + esc(a.confidence) + "%</div>" +
      '<div class="dw-kv"><span>Observed</span>' + esc(shortTime(a.timestamp)) + "</div>" +
      '<div class="dw-kv"><span>Entities</span>' + esc((a.entities_involved || []).join(", ")) + "</div>");
    html += sec("Algorithm", '<div class="dw-txt">' + esc(a.algorithm) + "</div>");
    html += sec("Evidence (" + (a.source_records || []).length + " records)",
      recordList(a.evidence, a.evidence_truncated));
    html += '<div class="notice">' + esc(a.verification_notice) + "</div>";
    openDrawer("Finding · " + a.anomaly_type.replace(/_/g, " "), html);
  }

  /* -- a timeline event ---------------------------------------------------- */
  function openEventDrawer(ev) {
    var html = sec("Event", '<div class="dw-kv"><span>Type</span>' + esc(ev.type) + "</div>" +
      '<div class="dw-kv"><span>When</span>' +
      esc(ev.timeless ? "no event time in the source records" : shortTime(ev.timestamp)) + "</div>" +
      '<div class="dw-kv"><span>Source</span>' + esc(ev.source_type) + "</div>" +
      (ev.entities && ev.entities.length
        ? '<div class="dw-kv"><span>Entities</span>' + esc(ev.entities.slice(0, 8).join(", ")) + "</div>"
        : ""));
    html += sec("Summary", '<div class="dw-txt">' + esc(ev.summary) + "</div>");
    var recs = (ev.source_records || []).map(function (r) {
      return { record_id: r, source_type: ev.source_type, detail: "" };
    });
    html += sec("Source records (" +
      (ev.source_record_count || (ev.source_records || []).length) + ")",
      recordList(recs.slice(0, 20),
        Math.max(0, (ev.source_record_count || recs.length) - 20)));
    openDrawer(ev.type.replace(/_/g, " "), html);
  }

  /* ===================================================== panels */
  function renderLeads() {
    var leads = FULL.leads || [];
    var ctrl = FULL.network_controllers || [];
    var html = "";
    if (ctrl.length) {
      html += '<div class="cluster"><h4>★ Potential Network Controller</h4>' +
        ctrl.slice(0, 2).map(function (c) {
          return '<div class="dw-kv"><span>' + esc(c.entity) + "</span>" +
            inr(c.net_inflow_inr) + " net inflow · " + c.fir_mentions + " FIR mentions</div>" +
            '<div class="reason">' + esc(c.basis) + "</div>";
        }).join("") + "</div>";
    }
    // 28 cards at ~110px each is a 3,000px scroll. Leads below the MONITOR band
    // are still available, but folded behind one line so the ones worth a
    // judge's attention are on screen without scrolling.
    var LOW = 25;
    function card(l) {
      var bars = l.factors.map(function (f) {
        return '<i class="' + (FACTOR_CLASS[f.factor] || "f-centrality") +
          '" style="width:' + f.points + '%"></i>';
      }).join("");
      return '<div class="lead" data-lead="' + esc(l.entity) + '">' +
        '<div class="lead-top"><span class="lead-name">' + esc(l.entity) + "</span>" +
        '<span class="lead-score">' + l.lead_score + '</span></div>' +
        '<div class="lead-band">' + esc(l.band) + "</div>" +
        '<div class="bar">' + bars + "</div>" +
        l.factors.slice(0, 3).map(function (f) {
          return '<div class="fac"><b>+' + f.points + "</b><span>" + esc(f.factor) + "</span></div>";
        }).join("") +
        (l.factors.length > 3
          ? '<div class="fac"><b></b><span style="color:#8A7550">+ ' + (l.factors.length - 3) +
            " more signal(s) — click for full breakdown</span></div>"
          : "") + "</div>";
    }
    var primary = leads.filter(function (l) { return l.lead_score >= LOW; });
    var low = leads.filter(function (l) { return l.lead_score < LOW; });
    html += primary.map(card).join("");
    if (low.length) {
      html += '<div class="more" data-more="lowLeads">▸ ' + low.length +
        " low-signal lead(s) below " + LOW + " — show</div>" +
        '<div class="hidden-leads" id="lowLeads" hidden>' + low.map(card).join("") + "</div>";
    }
    html += '<div class="notice">' + esc((FULL.notices || {}).scoring || "") + "</div>";
    $$("leadsBody").innerHTML = html;
  }

  function renderER() {
    var er = FULL.entity_resolution || {};
    var s = er.stats || {};
    var html = '<div class="dw-kv"><span>Names observed</span>' + esc(s.names_observed) + "</div>" +
      '<div class="dw-kv"><span>Pairs compared</span>' + esc(s.pairs_compared) + "</div>" +
      '<div class="dw-kv"><span>Likely same</span>' + esc(s.likely_same) + "</div>" +
      '<div class="dw-kv"><span>Possible same</span>' + esc(s.possible_same) + "</div>" +
      '<div class="dw-kv"><span>Auto-merged</span><b>' + esc(s.auto_merged) + "</b></div>";

    html += '<div class="dw-lbl" style="margin-top:12px">CANDIDATE IDENTITIES</div>';
    html += (er.clusters || []).map(function (c) {
      return '<div class="cluster"><h4>' + esc(c.anchor_entity) +
        '  <span class="pill p-MEDIUM">' + esc(c.status) + "</span></h4>" +
        c.members.map(function (m) {
          return '<span class="member' + (m === c.anchor_entity ? " anchor" : "") +
            '">' + esc(m) + "</span>";
        }).join("") +
        '<div class="reason" style="margin-top:5px">Weakest link in this group: ' +
        esc(c.linking_confidence_min) + "%. " + esc(c.recommended_action) + "</div></div>";
    }).join("");

    html += '<div class="dw-lbl" style="margin-top:12px">PAIRWISE MATCHES</div>';
    html += (er.matches || []).map(function (m) {
      return '<div class="match" data-match="' + esc(m.entity) + "||" + esc(m.candidate) + '">' +
        '<div class="match-hd"><b>' + esc(m.confidence) + "%</b>" +
        '<span class="pill p-' + esc(m.decision) + '">' +
        esc(m.decision.replace(/_/g, " ")) + "</span></div>" +
        '<div class="reason">' + esc(m.entity) + "  ↔  " + esc(m.candidate) + "</div>" +
        // Strongest three reasons inline; the full scoring is one click away
        // in the drawer. Negative reasons are always kept — they are the ones
        // that stop a false merge, and must never be the ones that get hidden.
        m.reasons.slice().sort(function (a, b) {
          return (a.points < 0 ? -1 : 0) - (b.points < 0 ? -1 : 0) ||
                 Math.abs(b.points) - Math.abs(a.points);
        }).slice(0, 3).map(function (r) {
          return '<div class="reason' + (r.points < 0 ? " neg" : "") + '"><em>' +
            (r.points > 0 ? "+" : "") + r.points + "</em> " + esc(r.reason) + "</div>";
        }).join("") +
        (m.reasons.length > 3
          ? '<div class="reason" style="color:#8A7550">+ ' + (m.reasons.length - 3) + " more — click</div>"
          : "") + "</div>";
    }).join("");

    html += '<div class="notice">' + esc(er.policy || "") + "</div>";
    $$("erBody").innerHTML = html;
  }

  function openMatchDrawer(entity, candidate) {
    var er = FULL.entity_resolution || {};
    var m = (er.matches || []).filter(function (x) {
      return x.entity === entity && x.candidate === candidate;
    })[0];
    if (!m) return;
    var html = sec("Why these were linked",
      '<div class="dw-txt">"' + esc(m.entity) + '" and "' + esc(m.candidate) +
      '" score <b>' + m.confidence + "%</b> — " + esc(m.decision.replace(/_/g, " ")) +
      ". " + esc(m.recommended_action) + "</div>");
    html += sec("Scoring", m.reasons.map(function (r) {
      return '<div class="conf-row"><span>' + esc(r.reason) + " — " +
        esc(r.detail) + "</span><b>" + (r.points > 0 ? "+" : "") + r.points + "</b></div>";
    }).join(""));
    [["entity_profile", m.entity], ["candidate_profile", m.candidate]].forEach(function (pair) {
      var p = m[pair[0]];
      html += sec("Identifiers · " + pair[1],
        '<div class="dw-kv"><span>Phones</span>' + esc(p.phones.join(", ") || "—") + "</div>" +
        '<div class="dw-kv"><span>Accounts</span>' + esc(p.accounts.join(", ") || "—") + "</div>" +
        '<div class="dw-kv"><span>Vehicles</span>' + esc(p.vehicles.join(", ") || "—") + "</div>" +
        '<div class="dw-kv"><span>Sources</span>' + esc(p.source_types.join(", ")) + "</div>" +
        (p.notes && p.notes.length ? '<div class="reason">' + esc(p.notes.join("; ")) + "</div>" : ""));
    });
    html += sec("Algorithm", '<div class="dw-txt">' + esc(m.algorithm) + "</div>");
    html += uncertaintyBlock(m.uncertainty);
    html += '<div class="notice">Auto-merged: <b>no</b>. ' + esc(m.verification_notice) + "</div>";
    openDrawer("Identity · " + entity, html);
  }

  /* ===================================================== timeline */
  var LAST_TL = null;                    // last payload, for re-render on resize
  var LANE_OF = { FIR: 0, CUSTODY_OVERLAP: 0, CALL_ACTIVITY: 1,
                  TRANSACTION: 2, TRAVEL: 2, VEHICLE_REGISTRATION: 2 };
  var LANE_Y = [9, 20, 31];              // px from track top, one per lane
  var MIN_LABEL_GAP = 46;                // px between tick labels
  var BREAK_FRACTION = 0.40;             // a gap this large (of total span) breaks the axis...
  var MIN_BREAK_MS = 120 * 86400000;     // ...but only if it is also at least 120 days. A
                                         // 3-day lull inside a 7-day window is not "prior
                                         // history", and must not be drawn as if it were.
  var PRIOR_WIDTH = 18;                  // % of track given to the compressed early segment

  function monthLabel(ms) {
    var d = new Date(ms);
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
  }

  /* Split the time range at its single largest gap when that gap dominates the
     span. Each segment keeps linear time inside itself; the break between them
     is drawn, so compression is visible rather than silent. With a narrow
     window (7d / 24h) no gap dominates and the axis is a single segment. */
  function segmentsFor(sortedTimes) {
    var lo = sortedTimes[0], hi = sortedTimes[sortedTimes.length - 1];
    var span = (hi - lo) || 1;
    var bestGap = 0, cut = -1;
    for (var k = 1; k < sortedTimes.length; k++) {
      var g = sortedTimes[k] - sortedTimes[k - 1];
      if (g > bestGap) { bestGap = g; cut = k; }
    }
    if (cut > 0 && bestGap > span * BREAK_FRACTION && bestGap >= MIN_BREAK_MS &&
        sortedTimes.length > 3) {
      return [
        { from: lo, to: sortedTimes[cut - 1], x0: 0, x1: PRIOR_WIDTH, label: "prior history" },
        { from: sortedTimes[cut], to: hi, x0: PRIOR_WIDTH + 4, x1: 100, label: "case window" }
      ];
    }
    return [{ from: lo, to: hi, x0: 0, x1: 100, label: null }];
  }

  function renderTimeline(payload) {
    LAST_TL = payload;
    var tl = payload.timeline || {};
    var events = (tl.events || []).filter(function (e) { return e.timestamp; });
    var track = $$("tlTrack");
    $$("tlWindow").textContent = (tl.window ? tl.window.label : "") +
      "   ·   anchored to latest record " +
      ((tl.clock && tl.clock.anchor) ? tl.clock.anchor.slice(0, 10) : "—") +
      " (not today's date)";
    if (!events.length) {
      track.innerHTML = '<div class="tl-empty">No dated events in this window.</div>';
      track._events = [];
      return;
    }

    var times = events.map(function (e) { return Date.parse(e.timestamp); });
    var sorted = times.slice().sort(function (a, b) { return a - b; });
    var segs = segmentsFor(sorted);

    function xOf(t) {
      for (var s = 0; s < segs.length; s++) {
        var seg = segs[s];
        if (t >= seg.from && t <= seg.to) {
          var w = (seg.to - seg.from) || 1;
          return seg.x0 + ((t - seg.from) / w) * (seg.x1 - seg.x0);
        }
      }
      return 0;
    }

    var html = LANE_Y.map(function (y) {
      return '<div class="tl-lane" style="top:' + y + 'px"></div>';
    }).join("");

    // events, each in its lane
    html += events.map(function (e, i) {
      var lane = LANE_OF[e.type] === undefined ? 2 : LANE_OF[e.type];
      var big = (e.type === "FIR") ||
        (e.type === "TRANSACTION" && e.amount_inr >= 100000) ||
        (e.type === "CALL_ACTIVITY" && e.call_count >= 8);
      return '<div class="tl-ev t-' + e.type + (big ? " big" : "") +
        '" style="left:' + xOf(times[i]).toFixed(3) + '%;top:' + LANE_Y[lane] +
        'px" data-ev="' + i + '" title="' +
        esc(shortTime(e.timestamp) + " · " + e.summary) + '"></div>';
    }).join("");

    // break marker between segments
    if (segs.length > 1) {
      var bx = (segs[0].x1 + segs[1].x0) / 2;
      html += '<div class="tl-break" style="left:' + bx.toFixed(3) + '%" title="' +
        'Axis break: ' + monthLabel(segs[0].to) + ' → ' + monthLabel(segs[1].from) +
        ' compressed. Each side is linear in time."></div>';
    }

    // ticks: a labelled caption at each segment start, then month ticks that
    // only render when they have room — no more "20262026-2026-03".
    var width = track.clientWidth || 800;
    var placed = [];
    function fits(px) {
      for (var p = 0; p < placed.length; p++) {
        if (Math.abs(placed[p] - px) < MIN_LABEL_GAP) return false;
      }
      placed.push(px);
      return true;
    }
    segs.forEach(function (seg) {
      var px = seg.x0 / 100 * width;
      placed.push(px);
      var range = seg.label
        ? seg.label + " · " + monthLabel(seg.from) +
          (monthLabel(seg.to) !== monthLabel(seg.from) ? " → " + monthLabel(seg.to) : "")
        : monthLabel(seg.from);
      html += '<div class="tl-tick seg" style="left:' + seg.x0.toFixed(3) + '%">' +
        esc(range) + "</div>";
      // reserve the caption's own width so month ticks do not overprint it
      placed.push(px + Math.min(range.length * 5.2, 160));
    });
    var seenMonth = {};
    sorted.forEach(function (t) {
      var key = monthLabel(t);
      if (seenMonth[key]) return;
      seenMonth[key] = true;
      var x = xOf(t), px = x / 100 * width;
      if (!fits(px)) return;
      html += '<div class="tl-tick" style="left:' + x.toFixed(3) + '%">' + key + "</div>";
    });

    track.innerHTML = html;
    track._events = events;
  }

  /* ===================================================== window switching */
  function applyWindow(win) {
    CURRENT_WINDOW = win;
    fetch("/api/graph?window=" + encodeURIComponent(win))
      .then(function (r) { return r.json(); })
      .then(function (p) {
        // Only the edges and the timeline follow the window. Node positions,
        // roles and scores stay anchored to the full record set.
        var keep = {};
        edgesDS.forEach(function (e) { keep[e.from + "|" + e.to] = e; });
        edgesDS.clear();
        edgesDS.add(p.edges.map(function (e, i) {
          var base = edgeStyle(e);
          return {
            id: "e" + i, from: e.from, to: e.to,
            color: base.color, width: base.width, dashes: base.dashes,
            smooth: base.smooth, shadow: base.shadow,
            _rel: e.rel, _rels: e.rel_types || [e.rel], _money: e.money_inr,
            _calls: e.calls, _src: e.source, _conf: e.confidence
          };
        }));
        DATA.edges = p.edges;
        DATA.timeline = p.timeline;
        applyFilters();
        renderTimeline(p);
        $$("statline").textContent =
          DATA.stats.people + " entities · " + p.edges.length + " links in window · " +
          DATA.stats.communities + " clusters · " + DATA.stats.firs_parsed + " FIRs";
        toast(win === "all"
          ? "Showing all recorded activity"
          : "Window: last " + win + " before " +
            (p.timeline.clock.anchor || "").slice(0, 10) + " — " +
            p.edges.length + " of " + p.stats.edges_total + " links");
      })
      .catch(function () { toast("Could not apply window filter."); });
  }

  /* ===================================================== wiring */
  function wire() {
    // window picker
    Array.prototype.forEach.call(document.querySelectorAll(".win"), function (el) {
      el.onclick = function () {
        Array.prototype.forEach.call(document.querySelectorAll(".win"), function (x) {
          x.classList.remove("on");
        });
        el.classList.add("on");
        applyWindow(el.dataset.window);
      };
    });

    // panel tabs
    Array.prototype.forEach.call(document.querySelectorAll(".ptab"), function (el) {
      el.onclick = function () {
        Array.prototype.forEach.call(document.querySelectorAll(".ptab"), function (x) {
          x.classList.remove("on");
        });
        el.classList.add("on");
        ["dossierCard", "leadsCard", "erCard"].forEach(function (id) {
          $$(id).hidden = (id !== el.dataset.panel);
        });
      };
    });

    // delegated clicks for every drawer entry point
    document.addEventListener("click", function (ev) {
      var t = ev.target.closest ? ev.target.closest("[data-more],[data-lead],[data-match],[data-record],[data-anomaly],[data-ev]") : null;
      if (!t) return;
      if (t.dataset.more) {
        var box = $$(t.dataset.more);
        if (!box) return;
        box.hidden = !box.hidden;
        t.textContent = (box.hidden ? "▸ " : "▾ ") +
          t.textContent.replace(/^[▸▾]\s*/, "").replace(/ — (show|hide)$/, "") +
          (box.hidden ? " — show" : " — hide");
        return;
      }
      if (t.dataset.lead) return openLeadDrawer(t.dataset.lead);
      if (t.dataset.match) {
        var parts = t.dataset.match.split("||");
        return openMatchDrawer(parts[0], parts[1]);
      }
      if (t.dataset.record) return openRecordDrawer(t.dataset.record);
      if (t.dataset.anomaly) return openAnomalyDrawer(t.dataset.anomaly);
      if (t.dataset.ev !== undefined) {
        var evs = $$("tlTrack")._events || [];
        var e = evs[Number(t.dataset.ev)];
        if (e) return openEventDrawer(e);
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrawer();
    });
  }

  /* Poll for the board to finish booting, then attach. index.html's boot() is
     an async IIFE we do not control, so waiting on DATA is the reliable hook. */
  function start() {
    if (typeof DATA === "undefined" || !DATA || !network) {
      return setTimeout(start, 120);
    }
    FULL = DATA;
    wire();
    renderLeads();
    renderER();
    renderTimeline(DATA);

    // Tick-label collision avoidance is computed in pixels, so a resize (or
    // the demo laptop being plugged into a projector) needs a re-layout.
    var resizeTimer = null;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () { if (LAST_TL) renderTimeline(LAST_TL); }, 120);
    });

    // Clicking a string on the board opens its evidence.
    network.on("click", function (p) {
      if (p.edges && p.edges.length && (!p.nodes || !p.nodes.length)) {
        var e = edgesDS.get(p.edges[0]);
        if (e) openRelationshipDrawer(e.from, e.to);
      }
    });
    window.openRelationshipDrawer = openRelationshipDrawer;
    window.openLeadDrawer = openLeadDrawer;
    wireAddData();
  }

  /* ===================================================== ADD DATA modal */
  var EXAMPLES = {
    fir: {text:"FIRST INFORMATION REPORT\nFIR No: 099/2026\nPolice Station: Delhi\nDate: 15-04-2026\nSections: NDPS Act 8/20\nNARRATIVE:\nAccused Arjun Mehta was apprehended near Azadpur and named associate Ravi Malhotra. Mobile number 9811000099 recovered from accused."},
    cdr: {json:'[\n  {"caller":"9811000002","receiver":"9822000001","timestamp":"2026-03-22T14:32:00","duration_sec":342,"tower_id":"TWR415"},\n  {"caller":"9811000002","receiver":null,"timestamp":"2026-03-22T14:40:00","duration_sec":null,"tower_id":"TWR415"}\n]', csv:'caller,receiver,timestamp,duration_sec,tower_id\n9811000002,9822000001,2026-03-22 14:32,342,TWR415'},
    bank: {json:'[\n  {"from_account":"ACC9003","to_account":"ACC7777","amount_inr":65000,"date":"2026-03-22"},\n  {"from_account":"ACC9003","to_account":"ACC7777","amount_inr":null,"date":"2026-03-22"}\n]', csv:'from_account,to_account,amount_inr,date\nACC9003,ACC7777,65000,2026-03-22'},
    accounts: {json:'[{"account":"ACC9200","holder_name":"New Person"}]', csv:'account,holder_name\nACC9200,New Person'},
    phone_directory: {json:'[{"phone":"9811000200","registered_name":"New Person"}]', csv:'phone,registered_name\n9811000200,New Person'},
    vehicles: {json:'[{"registration_number":"MH12AB0007","registered_owner":"New Person","vehicle_type":"Truck"}]', csv:'vehicle_number,owner_name,vehicle_type\nMH12AB0007,New Person,Truck'},
    travel: {json:'[{"passenger_name":"Vikram Rathore","from_city":"Delhi","to_city":"Dubai","date":"2026-03-25","flight":"EK511"}]', csv:'passenger_name,from_city,to_city,date,flight\nVikram Rathore,Delhi,Dubai,2026-03-25,EK511'},
    prison: {json:'[{"prisoner_name":"New Person","jail":"Tihar Jail","cell_block":"Block-4","from_date":"2022-02-10","to_date":"2022-11-30"}]', csv:'prisoner_name,jail,cell_block,from_date,to_date\nNew Person,Tihar Jail,Block-4,2022-02-10,2022-11-30'},
    cctv: {json:'[{"timestamp":"2026-03-18T19:10:00","camera_id":"CAM-042","location":"Mundra Port Gate 2","vehicle_number":"KA01AB1234","vehicle_match_confidence":94}]'},
    gps: {json:'[{"vehicle_id":"KA01AB1234","timestamp":"2026-03-18T18:42:00","latitude":17.4485,"longitude":78.3908,"speed_kmh":42}]'},
    social: {json:'[{"account_id":"ACC_SOC_001","account_name":"user_example","timestamp":"2026-03-18T20:10:00","text":"Big shipment arriving tomorrow at the port.","mentioned_locations":"Mundra Port","hashtags":"#shipment"}]'},
  };
  var LEVEL_CLASS = {HIGH:"ok", MEDIUM:"warn", LOW:"bad"};
  var STATUS_CLASS = {VALID:"ok", PARTIAL:"warn", INVALID:"bad"};

  window.closeAddData = function () { $$("addModal").hidden = true; };
  function openAddData() {
    $$("addModal").hidden = false;
    $$("amResult").innerHTML = "";
    $$("amCommit").disabled = true;
  }

  function loadSources() {
    fetch("/api/intake/schema").then(function (r) { return r.json(); }).then(function (d) {
      var sel = $$("amSource");
      var order = ["fir","cdr","bank","accounts","phone_directory","vehicles","travel","prison","cctv","gps","social"];
      sel.innerHTML = order.filter(function(k){return d.sources[k];}).map(function (k) {
        return '<option value="' + k + '">' + esc(d.sources[k].label) + "</option>";
      }).join("");
      syncFormat();
    }).catch(function(){ toast("Could not load intake schema"); });
  }

  function syncFormat() {
    var src = $$("amSource").value, fmt = $$("amFormat");
    // FIR is raw text only; staged/CCTV-style sources are JSON only.
    var textOnly = src === "fir";
    [...fmt.options].forEach(function (o) {
      o.disabled = (textOnly && o.value !== "text") || (!textOnly && o.value === "text");
    });
    if (textOnly) fmt.value = "text";
    else if (fmt.value === "text") fmt.value = "json";
  }

  function loadExample() {
    var src = $$("amSource").value, fmt = $$("amFormat").value;
    var ex = EXAMPLES[src] || {};
    $$("amPayload").value = ex[fmt] || ex.json || ex.text || "";
  }

  function renderPreview(d) {
    var s = d.summary;
    function stat(n, label, cls) { return n ? '<span class="am-stat ' + cls + '">' + n + " " + label + "</span>" : ""; }
    var html = '<div class="am-summary">' +
      '<span class="am-stat mut">' + s.total + " record(s)</span>" +
      stat(s.valid, "valid", "ok") + stat(s.partial, "partial", "warn") +
      stat(s.invalid, "invalid", "bad") + stat(s.conflicts, "conflict", "bad") +
      stat(s.duplicates, "duplicate", "warn") + "</div>";
    if (d.staged) html += '<div class="notice">This source is stored but not yet drawn on the board — it needs the Phase 2 map/OSINT view.</div>';

    html += d.records.map(function (r) {
      var q = r.quality;
      var fields = r.parsed ? Object.keys(r.parsed).map(function (k) {
        var v = r.parsed[k];
        if (v === null || v === undefined || v === "")
          return '<b>' + esc(k) + '</b>=<span class="nul">null</span>';
        if (Array.isArray(v)) v = v.join(", ") || "—";
        return "<b>" + esc(k) + "</b>=" + esc(v);
      }).join(" &middot; ") : "";
      return '<div class="am-rec"><div class="am-rec-top">' +
        '<span class="am-rec-id">' + esc(r.record_id) + "</span>" +
        '<span class="pill p-' + (STATUS_CLASS[q.validation_status] === "ok" ? "LOW" : STATUS_CLASS[q.validation_status] === "warn" ? "MEDIUM" : "CRITICAL") + '">' + esc(q.validation_status) + "</span>" +
        '<span class="am-stat ' + (LEVEL_CLASS[q.level]) + '">' + q.level + " · " + q.completeness + "%</span>" +
        (r.committable ? "" : '<span class="am-stat bad">held back</span>') + "</div>" +
        '<div class="am-fields">' + fields + "</div>" +
        (r.issues && r.issues.length ? '<div class="am-issue">! ' + r.issues.map(esc).join("<br>! ") + "</div>" : "") +
        (r.conflicts && r.conflicts.length ? '<div class="am-conflict">CONFLICT — ' + esc(r.conflicts[0].detail) + "</div>" : "") +
        "</div>";
    }).join("");
    $$("amResult").innerHTML = html;
    $$("amCommit").disabled = s.committable === 0;
  }

  function body() {
    return {
      source_type: $$("amSource").value,
      format: $$("amFormat").value,
      payload: $$("amPayload").value,
      include_conflicts: $$("amConflicts").checked,
    };
  }
  function post(path, b) {
    return fetch(path, {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(b)}).then(function (r) {
        return r.json().then(function (j) { return r.ok ? j : Promise.reject(j.detail || "request failed"); });
      });
  }

  function validate() {
    var p = $$("amPayload").value.trim();
    if (!p) { toast("Paste a record or load an example first"); return; }
    $$("amResult").innerHTML = '<div class="am-issue">Validating…</div>';
    post("/api/intake/preview", body()).then(renderPreview)
      .catch(function (e) { $$("amResult").innerHTML = '<div class="am-conflict">' + esc(String(e)) + "</div>"; $$("amCommit").disabled = true; });
  }

  function commit() {
    $$("amCommit").disabled = true;
    post("/api/intake/commit", body()).then(function (d) {
      var held = (d.held || []).map(function (h) { return h.record_id + ": " + h.reason; });
      $$("amResult").innerHTML = '<div class="am-done">Added <b>' + d.written + "</b> record(s)" +
        (d.written_ids && d.written_ids.length ? " (" + d.written_ids.slice(0, 8).join(", ") + ")" : "") + ". " +
        esc(d.note || "") + "</div>" +
        (held.length ? '<div class="am-held">Held for review:<br>' + held.map(esc).join("<br>") + "</div>" : "");
      if (d.written && !d.staged) {
        toast("Rebuilding board with " + d.written + " new record(s)…");
        setTimeout(function () { window.location.reload(); }, 1400);
      }
    }).catch(function (e) {
      $$("amResult").innerHTML = '<div class="am-conflict">' + esc(String(e)) + "</div>";
      $$("amCommit").disabled = false;
    });
  }

  function wireAddData() {
    var btn = $$("addDataBtn");
    if (!btn) return;
    btn.onclick = function () { openAddData(); };
    loadSources();
    $$("amSource").onchange = function () { syncFormat(); };
    $$("amFormat").onchange = function () {};
    $$("amExample").onclick = loadExample;
    $$("amValidate").onclick = validate;
    $$("amCommit").onclick = commit;
    $$("amFile").onchange = function (ev) {
      var f = ev.target.files && ev.target.files[0];
      if (!f) return;
      var reader = new FileReader();
      reader.onload = function () {
        $$("amPayload").value = reader.result;
        if (/\.csv$/i.test(f.name)) $$("amFormat").value = "csv";
        else if (/\.json$/i.test(f.name)) $$("amFormat").value = "json";
        else if (/\.txt$/i.test(f.name) && $$("amSource").value === "fir") $$("amFormat").value = "text";
      };
      reader.readAsText(f);
    };
    // Esc closes the modal (drawer handler already listens; add modal too)
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !$$("addModal").hidden) closeAddData();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else { start(); }
})();

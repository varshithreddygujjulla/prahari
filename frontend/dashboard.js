/* ===========================================================================
   dashboard.js — PRAHARI dark-dashboard shell.

   A new front-end over the SAME backend as the classic corkboard (served at
   /classic). Every finding stays evidence-backed: Investigative Lead Score
   (never a "risk"/guilt score), aliases shown as UNCONFIRMED candidates, AI
   insights carry a verification notice, and the audit chain is front and centre.
   =========================================================================== */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var DATA = null, NET = null, NET2 = null, nodesDS = null, edgesDS = null;
  var CUR = null, WINDOW = "all", DECISIONS = {};
  // Officer identity is per-browser and editable (topbar chip); it is sent on
  // every API call so the audit chain names a person, not a default.
  var OFFICER = (function () { try { return localStorage.getItem("prahari.officer") || "Officer-101"; } catch (x) { return "Officer-101"; } })();
  var DEBUG = /[?&]debug\b/.test(location.search);   // exposes window.__NET for inspection

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function inr(n) { return "₹" + Number(n || 0).toLocaleString("en-IN"); }
  // FastAPI 422s return detail as an array; flatten it to a readable string.
  function errText(j, r) {
    var d = j && j.detail;
    if (Array.isArray(d)) d = d.map(function (x) { return ((x.loc || []).slice(-1)[0] || "") + ": " + x.msg; }).join("; ");
    return d || (r && (r.status + " " + r.statusText)) || "request failed";
  }
  // Every GET to the API carries the officer identity so the audit log names
  // the person, not a default. Non-OK responses reject instead of rendering.
  function api(p) {
    if (p.indexOf("/api/") === 0) p += (p.indexOf("?") >= 0 ? "&" : "?") + "officer=" + encodeURIComponent(OFFICER);
    return fetch(p).then(function (r) {
      return r.ok ? r.json() : r.json().catch(function () { return {}; }).then(function (j) { return Promise.reject(errText(j, r)); });
    });
  }
  function post(p, b) {
    if (b && b.officer === undefined) b.officer = OFFICER;
    return fetch(p, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(b) }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { return r.ok ? j : Promise.reject(errText(j, r)); });
    });
  }
  var toastT;
  function toast(m) { var t = $("toast"); t.textContent = m; t.classList.add("show");
    clearTimeout(toastT); toastT = setTimeout(function () { t.classList.remove("show"); }, 2600); }

  /* -------- node / edge styling -------- */
  var KIND = {
    person: { c: "#4a9eff", i: "👤", label: "Person" },
    unresolved_number: { c: "#3fb950", i: "📞", label: "Unresolved number" },
    shell_company: { c: "#a371f7", i: "🏢", label: "Organization" },
    vehicle: { c: "#f85149", i: "🚗", label: "Vehicle" },
    account: { c: "#d29922", i: "🏦", label: "Account" },
  };
  var LEGEND = [
    ["#4a9eff", "Person"], ["#3fb950", "Phone / number"], ["#d29922", "Account"],
    ["#f85149", "Vehicle"], ["#a371f7", "Organization"],
  ];
  var RELLABEL = {
    money: "Financial Transfer", calls: "Calls", "co-accused": "Co-accused",
    "registered-to": "Owns", "phone-linked": "Handset", "jailed-together": "Custody",
    "co-travel": "Travelled",
  };
  function edgeColor(rel) {
    return rel === "money" ? "#d29922" : rel === "calls" ? "#f85149"
      : rel === "co-accused" ? "#4a9eff" : rel === "jailed-together" ? "#a371f7"
      : rel === "phone-linked" ? "#3fb950" : "#6e7681";
  }

  /* ==================================================== boot */
  function boot() {
    // Visible loading state: the strip and the graph card say what is happening
    // instead of sitting blank until the first payload lands.
    $("statStrip").innerHTML = '<span class="stat-i"><span class="ic">⏳</span>Loading case data — building the evidence graph…</span>';
    $("graph").innerHTML = '<div class="ent-empty">Loading graph…</div>';
    Promise.all([
      api("/api/graph?window=" + WINDOW),
      api("/api/decisions").catch(function () { return { decisions: {} }; }),
    ]).then(function (r) {
      DATA = r[0]; DECISIONS = (r[1] && r[1].decisions) || {};
      renderStats();
      populateFilters();
      buildGraph("graph", function (n) { return n; });
      renderLegend();
      renderActivity();
      renderMiniTimeline();
      renderInsights();
      renderLeads();
      renderER();
      renderFullTimeline();
      renderAlerts();
      applyDeepLink();
    }).catch(function (e) {
      $("statStrip").innerHTML = '<span class="stat-i" style="color:var(--red)">Could not load case data: ' + esc(String(e)) + " — is the server running?</span>";
      toast("Failed to load case data: " + e); console.error(e);
    });
  }

  // Deep links: /?view=leads · /?entity=Ramesh%20Yadav&tab=casefile — so a
  // view or dossier can be shared, bookmarked, or opened straight from a doc.
  function applyDeepLink() {
    var q = new URLSearchParams(location.search);
    var view = q.get("view"), ent = q.get("entity"), tab = q.get("tab");
    if (view && VIEW_TITLE[view]) showView(view);
    if (q.get("full") === "1" && NET) setTimeout(toggleGraphFull, 400);   // /?full=1 → graph fills the window
    if (ent && DATA.nodes.some(function (n) { return n.id === ent; })) {
      if (tab) ENT_TAB = tab;
      api("/api/entity/" + encodeURIComponent(ent)).then(function (e) {
        CUR = e; if (tab) ENT_TAB = tab;
        renderEntity(e, "entityPanel"); renderEntity(e, "entityPanel2");
        if (NET) { NET.selectNodes([ent]); NET.focus(ent, { scale: 0.9, animation: false }); }
      });
    }
  }

  function decisionOf(kind, target) { return DECISIONS[kind + ":" + target]; }
  function verdictBadge(kind, target) {
    var d = decisionOf(kind, target);
    return d ? '<span class="verdict ' + d.action + '">' +
      (d.action === "VERIFIED" || d.action === "CONFIRMED" ? "✓ " :
       d.action === "DISMISSED" || d.action === "REJECTED" ? "✕ " : "◐ ") +
      d.action.replace("_", " ") + "</span>" : "";
  }
  function decisionBar(kind, target, acts) {
    var cls = { VERIFIED: "ok", CONFIRMED: "ok", DISMISSED: "no", REJECTED: "no", NEEDS_REVIEW: "rev" };
    var lbl = { VERIFIED: "✓ Verify", CONFIRMED: "✓ Confirm", DISMISSED: "✕ Dismiss",
      REJECTED: "✕ Reject", NEEDS_REVIEW: "◐ Needs review" };
    return '<div class="decide" data-decide="' + kind + "|" + esc(target) + '">' +
      acts.map(function (a) { return '<button class="dbtn ' + cls[a] + '" data-act="' + a + '">' +
        lbl[a] + "</button>"; }).join("") + "</div>";
  }
  function wireDecide(root) {
    (root || document).querySelectorAll("[data-decide]").forEach(function (bar) {
      var parts = bar.dataset.decide.split("|"), kind = parts[0], target = parts.slice(1).join("|");
      bar.querySelectorAll("[data-act]").forEach(function (b) {
        b.onclick = function (ev) {
          ev.stopPropagation();
          var note = window.prompt("Optional note for the audit log (" + b.dataset.act.replace("_", " ").toLowerCase() + " · " + target + "):", "");
          if (note === null) return;                        // cancelled
          post("/api/decision", { kind: kind, target: target, action: b.dataset.act, note: note || null, officer: OFFICER })
            .then(function (res) {
              DECISIONS[kind + ":" + target] = res.decision;
              toast(res.decision.action.replace("_", " ") + " recorded to audit log");
              renderLeads(); renderER(); renderActivity(); renderAlerts();
              if ($("view-audit").classList.contains("on")) renderAudit();
              if (CUR && CUR.entity === target) openEntity(target);
            }).catch(function (e) { toast("Could not record: " + e); });
        };
      });
    });
  }

  function renderStats() {
    var s = DATA.stats;
    var leads = (DATA.leads || []).filter(function (l) { return l.lead_score >= 25; }).length;
    var cells = [
      ["👥", s.people, "people", ""],
      ["🗂", s.nodes_total || DATA.nodes.length, "nodes on board", ""],
      ["🔗", s.edges, "links in window", ""],
      ["🕸", s.communities, "clusters", ""],
      ["📄", s.firs_parsed, "FIRs", ""],
      ["⚠", leads, "investigative leads", "lead"],
      ["🕐", (DATA.timeline.clock.anchor || "").slice(0, 10), "last record", ""],
    ];
    $("statStrip").innerHTML = cells.map(function (c) {
      return '<span class="stat-i ' + c[3] + '"><span class="ic">' + c[0] + "</span><b>" +
        esc(c[1]) + "</b> " + c[2] + "</span>";
    }).join('<span class="stat-sep">·</span>');
  }

  function populateFilters() {
    var kinds = {}, rels = {};
    DATA.nodes.forEach(function (n) { kinds[n.kind] = 1; });
    DATA.edges.forEach(function (e) { rels[e.rel] = 1; });
    $("filterKind").innerHTML = '<option value="">All Entities</option>' +
      Object.keys(kinds).map(function (k) {
        return '<option value="' + k + '">' + ((KIND[k] || {}).label || k) + "</option>";
      }).join("");
    $("filterRel").innerHTML = '<option value="">All Links</option>' +
      Object.keys(rels).map(function (r) {
        return '<option value="' + r + '">' + (RELLABEL[r] || r) + "</option>";
      }).join("");
  }

  // Legend is built from the node kinds actually on the board, so it never
  // advertises a type (e.g. "Account") that the data does not contain.
  function renderLegend() {
    var present = {};
    DATA.nodes.forEach(function (n) { present[n.kind] = 1; });
    $("glegend").innerHTML = Object.keys(KIND).filter(function (k) { return present[k]; }).map(function (k) {
      return '<div class="lr"><span class="ld" style="background:' + KIND[k].c + '"></span>' + KIND[k].label + "</div>";
    }).join("");
  }

  // Bell badge = findings that still need a human decision: CRITICAL/HIGH
  // anomalies plus PRIORITY REVIEW leads with no verdict recorded.
  function renderAlerts() {
    var open = (DATA.leads || []).filter(function (l) {
      return l.band === "PRIORITY REVIEW" && !decisionOf("lead", l.entity);
    }).length;
    var crit = (DATA.anomalies || []).filter(function (a) {
      return a.severity === "CRITICAL" || a.severity === "HIGH";
    }).length;
    var n = open + crit, dot = $("notifCount");
    if (dot) { dot.textContent = n; dot.hidden = n === 0; }
  }

  /* ==================================================== graph */
  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  function silhouette(ctx, cx, top, w, h, tint) {
    // head + shoulders, evidence-photo style, on a dark plate
    ctx.fillStyle = "#20293a";
    ctx.fillRect(cx - w / 2, top, w, h);
    ctx.fillStyle = tint;
    var hr = h * 0.24;
    ctx.beginPath(); ctx.arc(cx, top + h * 0.36, hr, 0, 7); ctx.fill();
    ctx.beginPath();
    ctx.ellipse(cx, top + h * 1.02, w * 0.42, h * 0.42, 0, Math.PI, 2 * Math.PI);
    ctx.fill();
  }
  /* Photo-card nodes: a dark evidence card carrying a silhouette (people) or a
     type glyph (phones, accounts, vehicles, organisations) with the name in a
     bar at the bottom. Reads like a case-board photo rather than a bare dot. */
  function nodeRenderer(n, view) {
    var k = KIND[n.kind] || KIND.person;
    var isLead = n.lead_band === "PRIORITY REVIEW" || n.id === controllerName();
    var isPerson = n.kind === "person";
    var accent = isLead ? "#f85149" : k.c;
    var w = isPerson ? 58 : 80, cardH = isPerson ? 62 : 42, labelH = 18;
    var h = cardH + labelH;                 // full node box incl. name below
    return function (p) {
      var ctx = p.ctx, x = p.x, y = p.y, sel = p.state.selected || p.state.hover;
      return {
        drawNode: function () {
          var rx = x - w / 2, ry = y - h / 2;
          ctx.save();
          // card + a tight drop shadow (a wide blur reads as fuzz at small zoom)
          ctx.shadowColor = "rgba(0,0,0,.55)"; ctx.shadowBlur = 6; ctx.shadowOffsetY = 3;
          roundRect(ctx, rx, ry, w, cardH, 7);
          ctx.fillStyle = "#141a24"; ctx.fill();
          ctx.shadowColor = "transparent";
          // top accent strip (colour by type / lead)
          ctx.save(); roundRect(ctx, rx, ry, w, cardH, 7); ctx.clip();
          ctx.fillStyle = accent; ctx.fillRect(rx, ry, w, 4); ctx.restore();
          // border (glows only when selected / lead)
          if (sel || isLead) { ctx.shadowColor = accent; ctx.shadowBlur = 10; }
          ctx.lineWidth = sel ? 2.5 : isLead ? 2 : 1.2;
          ctx.strokeStyle = sel ? "#ffffff" : isLead ? accent : "#3a4556";
          roundRect(ctx, rx, ry, w, cardH, 7); ctx.stroke();
          ctx.shadowColor = "transparent";

          var pad = 6, photoTop = ry + 7, photoH = cardH - 12;
          if (isPerson) {
            silhouette(ctx, x, photoTop, w - 2 * pad, photoH, "#39445a");
          } else {
            ctx.fillStyle = "#20293a"; ctx.fillRect(rx + pad, photoTop, w - 2 * pad, photoH);
            ctx.textAlign = "center"; ctx.textBaseline = "middle";
            ctx.font = "20px system-ui,'Segoe UI Emoji'";
            ctx.fillText(k.i, x, photoTop + photoH / 2);
          }
          // Full name BELOW the card, never truncated. The label grows as the
          // view zooms out (up to 1.6x) so names stay readable when the whole
          // network is on screen, and shrinks back to normal when zoomed in.
          var grow = Math.min(1.6, Math.max(1, 0.9 / (view.scale || 1)));
          var fs = Math.round(13 * grow);
          ctx.font = "700 " + fs + "px Inter,sans-serif";
          ctx.textAlign = "center"; ctx.textBaseline = "middle";
          ctx.lineWidth = Math.max(2.5, fs * 0.22); ctx.lineJoin = "round"; ctx.strokeStyle = "#0a0d12";
          var ly = ry + cardH + (labelH * grow) / 2;
          ctx.strokeText(n.id, x, ly);
          ctx.fillStyle = sel ? "#ffffff" : "#e6edf3";
          ctx.fillText(n.id, x, ly);
          // pin
          ctx.beginPath(); ctx.arc(x, ry + 3, 2.6, 0, 7);
          ctx.fillStyle = accent; ctx.fill();
          ctx.restore();
        },
        // hit box = the card only, so names below don't overlap-catch clicks
        nodeDimensions: { width: w, height: cardH },
      };
    };
  }
  // Nodes with no relationship inside the current window are hidden rather than
  // left floating as orphans — a card with no strings misleads more than it informs.
  function nodesInWindow() {
    var s = {};
    DATA.edges.forEach(function (e) { s[e.from] = 1; s[e.to] = 1; });
    return s;
  }
  function buildGraph(container, opts) {
    opts = opts || {};
    // The overview graph honours its own filter selects; the Network view
    // (graph2) has none and must not silently inherit them.
    var kf = container === "graph" && $("filterKind") ? $("filterKind").value : "";
    var rf = container === "graph" && $("filterRel") ? $("filterRel").value : "";
    var old = container === "graph" ? NET : NET2;
    if (old) { try { old.destroy(); } catch (x) {} }
    var active = nodesInWindow();
    var view = { scale: 1 };      // shared with the node renderer: current zoom
    var nodes = DATA.nodes.map(function (n) {
      return {
        id: n.id, _kind: n.kind,
        shape: "custom", ctxRenderer: nodeRenderer(n, view),
        hidden: !!((kf && n.kind !== kf) || !active[n.id]),   // MUST be boolean
      };
    });
    var edges = DATA.edges.map(function (e, i) {
      // Only labels that carry a number: the relation type is already the
      // string's colour (see legend / filter), repeating it on every edge is noise.
      var lbl = "";
      if (e.rel === "calls" && e.calls) lbl = e.calls + (e.calls === 1 ? " call" : " calls");
      else if (e.rel === "money" && e.money_inr) lbl = inr(e.money_inr);
      var col = edgeColor(e.rel);
      var registry = e.rel === "registered-to" || e.rel === "phone-linked";
      return {
        id: "e" + i, from: e.from, to: e.to, _rel: e.rel, _i: i,
        // Crisp, solid "strings": no glow shadow (it smears into a haze when
        // dozens of edges cross), a touch thicker and fully opaque instead.
        color: { color: col, highlight: "#ffffff", hover: "#ffffff", opacity: registry ? 0.6 : 1 },
        width: e.money_inr ? 3.4 : registry ? 1.3 : e.calls ? Math.min(2.2 + e.calls / 6, 4.2) : 2.4,
        shadow: false,
        dashes: e.rel === "jailed-together" ? [7, 6] : registry ? [2, 4] : false,
        label: lbl, font: { color: "#c9d1d9", size: 12, face: "Inter", bold: { mod: "600" },
          strokeWidth: 4, strokeColor: "#0a0d12", align: "middle" },
        smooth: { type: "continuous", roundness: 0.15 },
        hidden: !!(rf && e.rel !== rf),
      };
    });
    var nd = new vis.DataSet(nodes), ed = new vis.DataSet(edges);
    if (container === "graph") { nodesDS = nd; edgesDS = ed; }
    var net = new vis.Network($(container), { nodes: nd, edges: ed }, {
      // Tighter springs than before: the whole network then fits the card at a
      // higher zoom, which is the single biggest legibility win.
      physics: { barnesHut: { gravitationalConstant: -15000, springLength: 165,
        springConstant: 0.03, avoidOverlap: 0.8 }, stabilization: { iterations: 300 } },
      interaction: { hover: true, tooltipDelay: 150, hideEdgesOnDrag: true },
      edges: { hoverWidth: 1.5, selectionWidth: 2 },
    });
    // Keep the renderer's zoom in step with the view so labels can compensate.
    net.on("zoom", function (p) { view.scale = p.scale; });
    net.on("click", function (p) {
      if (p.nodes && p.nodes.length) { openEntity(p.nodes[0]); return; }
      if (p.edges && p.edges.length) {
        var e = (container === "graph" ? edgesDS : ed).get(p.edges[0]);
        if (e) openRelationshipDrawer(e.from, e.to);
      }
    });
    net.once("stabilizationIterationsDone", function () {
      net.fit({ animation: false });
      // fit() can zoom out too far when a few pendant nodes sit on the edge;
      // clamp to a readable minimum so labels stay legible on load.
      if (net.getScale() < 0.58) net.moveTo({ scale: 0.62 });
      view.scale = net.getScale();
      net.setOptions({ physics: false });
      net.redraw();
    });
    if (container === "graph") { NET = net; if (DEBUG) window.__NET = net; }
    else NET2 = net;
    return net;
  }

  /* Full-screen graph: lift the card to cover the window, then let vis fill the
     new space. autoResize handles most of it; we nudge redraw + fit to be sure. */
  function toggleGraphFull() {
    var c = $("graphCard");
    var full = c.classList.toggle("fullscreen");
    document.body.classList.toggle("graph-full", full);
    $("graphExpand").innerHTML = full ? "&#10005; Exit full screen" : "&#9974; Full screen";
    setTimeout(function () {
      if (!NET) return;
      var box = $("graph").getBoundingClientRect();     // size vis to the real box
      NET.setSize(Math.round(box.width) + "px", Math.round(box.height) + "px");
      NET.redraw();
      NET.fit({ animation: false });
      if (NET.getScale() < 0.58) NET.moveTo({ scale: 0.62 });
    }, 80);
  }

  function controllerName() {
    return (DATA.network_controllers && DATA.network_controllers[0]) ?
      DATA.network_controllers[0].entity : null;
  }

  /* ==================================================== entity panel */
  var ENT_TAB = "overview";
  function openEntity(name) {
    api("/api/entity/" + encodeURIComponent(name)).then(function (e) {
      CUR = e; ENT_TAB = "overview";
      renderEntity(e, "entityPanel");
      renderEntity(e, "entityPanel2");
      if (NET) NET.selectNodes([name]);
      if (NET2 && NET2.body.nodes[name]) NET2.selectNodes([name]);
    }).catch(function () { toast("Could not load " + name); });
  }

  function renderEntity(e, mount) {
    var el = $(mount); if (!el) return;
    var k = KIND[e.kind] || KIND.person;
    var lead = e.lead;
    var tags = '<span class="tag blue">' + esc(k.label) + "</span>";
    if (e.in_fir) tags += '<span class="tag amber">Accused (FIR)</span>';
    if (lead) tags += '<span class="tag ' + (lead.lead_score >= 50 ? "red" : "mut") +
      '">Lead ' + lead.lead_score + "/100</span>";
    if (e.entity === controllerName()) tags += '<span class="tag red">Potential Controller</span>';

    var showCase = e.kind === "person";
    var tabDefs = ["overview"].concat(showCase ? ["casefile"] : [])
      .concat(["connections", "evidence", "notes"]);
    var LBL = { overview: "Overview", casefile: "📁 Case File", connections: "Connections",
      evidence: "Evidence", notes: "Notes" };
    if (ENT_TAB === "casefile" && !showCase) ENT_TAB = "overview";
    var tabs = tabDefs.map(function (t) {
      return '<div class="ent-tab' + (t === ENT_TAB ? " on" : "") + '" data-etab="' + t + '">' +
        LBL[t] +
        (t === "connections" ? " (" + (e.relationships || []).length + ")" : "") +
        (t === "evidence" ? " (" + evidenceCount(e) + ")" : "") + "</div>";
    }).join("");

    el.innerHTML =
      '<div class="ent-head"><div class="ent-top"><div class="ent-av">' + k.i + "</div><div>" +
        '<div class="ent-name">' + esc(e.entity) + "</div>" +
        '<div class="ent-tags">' + tags + "</div></div></div></div>" +
      '<div class="ent-tabs">' + tabs + "</div>" +
      '<div class="ent-body" id="' + mount + '-body"></div>';
    renderEntBody(e, mount);
    el.querySelectorAll("[data-etab]").forEach(function (t) {
      t.setAttribute("role", "tab"); t.tabIndex = 0;
      t.onclick = function () { ENT_TAB = t.dataset.etab; renderEntity(e, mount); };
      t.onkeydown = function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); t.click(); } };
    });
  }

  function evidenceCount(e) {
    var s = {};
    (e.relationships || []).forEach(function (r) {
      (r.source_records || []).forEach(function (x) { s[x] = 1; });
    });
    return Object.keys(s).length;
  }

  function renderEntBody(e, mount) {
    var b = $(mount + "-body"); if (!b) return;
    if (ENT_TAB === "overview") b.innerHTML = entOverview(e);
    else if (ENT_TAB === "casefile") { entCaseFile(e, b); return; }
    else if (ENT_TAB === "connections") b.innerHTML = entConnections(e);
    else if (ENT_TAB === "evidence") b.innerHTML = entEvidence(e);
    else b.innerHTML = entNotes(e);
    if (ENT_TAB === "notes") {
      var ta = b.querySelector("textarea");
      ta.oninput = function () { try { localStorage.setItem("note:" + e.entity, ta.value); } catch (x) {} };
    }
    b.querySelectorAll("[data-goto]").forEach(function (x) {
      x.onclick = function () { openEntity(x.dataset.goto); };
    });
    b.querySelectorAll("[data-rel-with]").forEach(function (x) {
      x.onclick = function () { openRelationshipDrawer(e.entity, x.dataset.relWith); };
      x.onkeydown = function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); x.click(); } };
    });
    b.querySelectorAll("[data-rec]").forEach(function (x) {
      x.onclick = function (ev) { ev.stopPropagation(); openRecordDrawer(x.dataset.rec); };
    });
    var jump = b.querySelector("[data-jump]");
    if (jump) jump.onclick = function () { ENT_TAB = jump.dataset.jump; renderEntity(e, mount); };
    wireDecide(b);
  }

  function entOverview(e) {
    var ids = e.identifiers || {};
    var orgs = (e.relationships || []).filter(function (r) { return r.kind === "shell_company"; })
      .map(function (r) { return r.with; });
    var cands = (e.identity_candidates || []).filter(function (m) { return m.confidence >= 55; });
    var kv = function (k, v, cls) { return '<div class="kv"><span class="k">' + k + '</span><span class="v ' +
      (cls || "") + '">' + v + "</span></div>"; };
    var html = '<div class="sec-h">Basic information</div>';
    html += kv("Name", esc(e.entity));
    if (cands.length) {
      html += kv("Aliases", cands.map(function (m) {
        return esc(m.candidate) + ' <span style="color:var(--amber)">(' + m.confidence + "% candidate)</span>";
      }).join("<br>"));
    }
    if (ids.phones && ids.phones.length) html += kv("Phone", esc(ids.phones.join(", ")));
    if (ids.accounts && ids.accounts.length) html += kv("Linked accounts", esc(ids.accounts.join(", ")));
    if (ids.vehicles && ids.vehicles.length) html += kv("Linked vehicles", esc(ids.vehicles.join(", ")));
    if (orgs.length) html += kv("Associated with", esc(orgs.join(", ")));
    if (e.fir_ids && e.fir_ids.length) html += kv("FIRs", e.fir_ids.length + " (" + esc(e.fir_ids.slice(0, 2).join(", ")) + (e.fir_ids.length > 2 ? "…" : "") + ")");
    if (e.money_in) html += kv("Funds received", inr(e.money_in));
    if (e.money_out) html += kv("Funds sent", inr(e.money_out));
    html += kv("Cluster", "#" + e.community);
    html += kv("PageRank / betweenness", e.pagerank + " / " + e.betweenness);

    if (e.lead) {
      html += '<div class="sec-h" style="margin-top:16px">Investigative Lead Score ' +
        verdictBadge("lead", e.entity) + "</div>" +
        '<div class="kv"><span class="k">' + e.lead.band + '</span><span class="v" style="color:var(--red);font-weight:700">' +
        e.lead.lead_score + '/100</span></div>' +
        '<div class="scorebar"><i style="width:' + e.lead.lead_score + '%"></i></div>' +
        decisionBar("lead", e.entity, ["VERIFIED", "DISMISSED", "NEEDS_REVIEW"]) +
        '<div class="disc">A triage aid derived from record correlation — not a measure of guilt and no evidentiary weight. Your verdict is recorded to the audit log.</div>';
    }
    if (cands.length) {
      html += '<div class="disc">Aliases are <b>unconfirmed candidate</b> identities. No records are merged until an investigator confirms them (Entity Resolution).</div>';
    }
    html += '<a class="btn-full" data-jump="connections">View connections &amp; evidence &rarr;</a>';
    return html;
  }

  function entConnections(e) {
    if (!(e.relationships || []).length) return '<div class="ent-empty">No recorded relationships.</div>';
    return '<div class="dw-txt" style="color:var(--muted);margin-bottom:8px;font-size:12px">Click a connection to open its evidence.</div>' +
      e.relationships.map(function (r) {
      return '<div class="conn" data-rel-with="' + esc(r.with) + '">' +
        '<span class="cdot" style="background:' + edgeColor(r.rel) + '"></span>' +
        '<span class="cn">' + esc(r.with) + '<div class="cr">' + (RELLABEL[r.rel] || r.rel) +
        (r.money_inr ? " · " + inr(r.money_inr) : "") + (r.calls ? " · " + r.calls + " calls" : "") +
        '</div></span><span class="cc">' + (r.confidence || "?") + "%</span></div>";
    }).join("");
  }

  // Evidence tab: each row opens the relationship drawer (why + confidence
  // derivation), and the individual record chips open the raw source record.
  function entEvidence(e) {
    var rows = (e.relationships || []).map(function (r) {
      var recs = (r.source_records || []);
      return '<div class="rec" data-rel-with="' + esc(r.with) + '" role="button" tabindex="0">' +
        '<span class="rt">' + esc((r.source_types || []).join(", ")) + "</span>" +
        '<span class="rid">' + esc(r.with) + "</span>" +
        '<div class="rd">' + esc(RELLABEL[r.rel] || r.rel) + " · " + recs.length +
        " record(s) · " + esc(r.confidence || "?") + "% confidence — click for derivation</div>" +
        '<div class="rd" style="margin-top:4px">' + recs.slice(0, 5).map(function (id) {
          return '<span class="chip-r" data-rec="' + esc(id) + '" onclick="event.stopPropagation()">[' + esc(id) + "]</span>";
        }).join(" ") + (recs.length > 5 ? " +" + (recs.length - 5) + " more" : "") + "</div></div>";
    }).join("");
    return (rows || '<div class="ent-empty">No evidence records.</div>') +
      '<div class="disc">Every relationship is traceable to the records that produced it. Click a row for the confidence derivation, or a record id for the raw source.</div>';
  }

  var MOVE_ICON = { FIR: ["📄", "#4a9eff"], CALL_ACTIVITY: ["📞", "#f85149"],
    TRANSACTION: ["💰", "#d29922"], TRAVEL: ["✈", "#3fb950"],
    CUSTODY_OVERLAP: ["🔒", "#a371f7"], VEHICLE_REGISTRATION: ["🚗", "#6e7681"] };
  function entCaseFile(e, b) {
    b.innerHTML = '<div class="dw-txt" style="color:var(--muted)">Loading case file…</div>';
    api("/api/entity/" + encodeURIComponent(e.entity) + "/casefile").then(function (cf) {
      var html = "";
      if (cf.no_fir_note) {
        html += '<div class="disc" style="margin-top:0">' + esc(cf.no_fir_note) + "</div>";
      }
      // ---- FIRs as bullet points ----
      (cf.firs || []).forEach(function (f) {
        html += '<div class="casefir">' +
          '<div class="cf-h"><span class="cf-id" data-rec="' + esc(f.fir_id) + '">' + esc(f.fir_id) + "</span>" +
          '<span class="cf-meta">' + esc((f.date || "").slice(0, 10)) + " · " + esc(f.police_station) + "</span></div>" +
          (f.sections.length ? '<div class="cf-secs">' + f.sections.map(function (s) {
            return '<span class="cf-sec">' + esc(s) + "</span>"; }).join("") + "</div>" : "") +
          "<ul class=\"cf-points\">" +
          f.narrative_points.map(function (p) { return "<li>" + esc(p) + "</li>"; }).join("") +
          (f.co_accused.length ? '<li><b>Co-accused:</b> ' + f.co_accused.map(function (n) {
            return '<a data-goto="' + esc(n) + '">' + esc(n) + "</a>"; }).join(", ") + "</li>" : "") +
          (f.phones_recovered.length ? "<li><b>Phone recovered:</b> " + esc(f.phones_recovered.join(", ")) + "</li>" : "") +
          "</ul></div>";
      });
      if (!(cf.firs || []).length && !cf.no_fir_note) {
        html += '<div class="ent-empty">No FIR on file for this entity.</div>';
      }
      // ---- anomalies as clues ----
      if ((cf.anomalies || []).length) {
        html += '<div class="sec-h" style="margin-top:16px">⚠ Flags on this entity</div>';
        cf.anomalies.forEach(function (a) {
          html += '<div class="cf-flag"><span class="pill p-' + esc(a.severity) + '">' + esc(a.severity) +
            "</span> " + esc(a.explanation) + "</div>";
        });
      }
      // ---- recent moves ----
      html += '<div class="sec-h" style="margin-top:16px">🕐 Recent moves</div>';
      if ((cf.recent_moves || []).length) {
        html += '<div class="cf-moves">' + cf.recent_moves.map(function (m, i) {
          var ic = MOVE_ICON[m.type] || ["•", "#8b949e"];
          // A call day opens the contact breakdown (who, how often, which
          // direction); any other move opens its source record.
          var attr = m.contacts ? ' data-calls="' + i + '"' :
            (m.records && m.records[0] ? ' data-rec="' + esc(m.records[0]) + '"' : "");
          return '<div class="cf-move"' + attr + ' title="' + (m.contacts ? "Show who was called" : "Open source record") + '">' +
            '<span class="cf-dot" style="background:' + ic[1] + '">' + ic[0] + "</span>" +
            '<span class="cf-date">' + esc((m.date || "").slice(0, 10)) + "</span>" +
            '<span class="cf-sum">' + esc(m.summary) + "</span></div>";
        }).join("") + "</div>";
      } else {
        html += '<div class="dw-txt" style="color:var(--muted)">No dated activity on record.</div>';
      }
      html += '<div class="disc">Case file assembled from source records. An investigative aid — requires human verification.</div>';
      b.innerHTML = html;
      b.querySelectorAll("[data-goto]").forEach(function (x) { x.onclick = function () { openEntity(x.dataset.goto); }; });
      b.querySelectorAll("[data-rec]").forEach(function (x) { x.onclick = function () { openRecordDrawer(x.dataset.rec); }; });
      b.querySelectorAll("[data-calls]").forEach(function (x) {
        x.onclick = function () { openCallsDrawer(e.entity, cf.recent_moves[+x.dataset.calls]); };
      });
    }).catch(function () { b.innerHTML = '<div class="ent-empty">Could not load case file.</div>'; });
  }

  // "Who did he talk to?" — one day's calls for one entity, by counterparty,
  // with direction, total duration and every underlying CDR row as a chip.
  function fmtDur(s) {
    s = Number(s || 0); if (s < 60) return s + "s";
    var m = Math.floor(s / 60); return m >= 60 ? Math.floor(m / 60) + "h " + (m % 60) + "m" : m + "m " + (s % 60) + "s";
  }
  function openCallsDrawer(entity, m) {
    var day = (m.date || "").slice(0, 10);
    var total = m.contacts.reduce(function (n, c) { return n + c.calls; }, 0);
    var html = dwSec("Summary", '<div class="dw-txt"><b>' + esc(entity) + "</b> had <b>" + total +
      " call" + (total === 1 ? "" : "s") + "</b> with <b>" + m.contacts.length + " contact" +
      (m.contacts.length === 1 ? "" : "s") + "</b> on " + esc(day) + ". Each row is a registered subscriber " +
      "or, where no subscriber is on file, the bare number.</div>");
    html += dwSec("Contacts (most calls first)", m.contacts.map(function (c) {
      var known = DATA.nodes.some(function (n) { return n.id === c.with; });
      return '<div class="dw-rec" style="cursor:default"><span class="rt">' + c.calls + " call" + (c.calls === 1 ? "" : "s") +
        " · " + c.outgoing + " out / " + c.incoming + " in · " + fmtDur(c.duration_sec) + "</span>" +
        '<span class="rid">' + (known ? '<span class="chip-e" data-ent="' + esc(c.with) + '">' + esc(c.with) + " ↗</span>" : esc(c.with)) + "</span>" +
        '<div class="rd">' + c.records.map(function (id) {
          return '<span class="chip-r" data-rec="' + esc(id) + '">[' + esc(id) + "]</span>"; }).join(" ") + "</div></div>";
    }).join(""));
    html += '<div class="disc">Call detail records are metadata only — who called whom, when, for how long. No call content exists in this system.</div>';
    $("dwTitle").textContent = "Calls · " + day;
    $("dwBody").innerHTML = html; $("drawer").hidden = false; wireRecs();
    $("dwBody").querySelectorAll("[data-ent]").forEach(function (x) {
      x.onclick = function () { closeDrawer(); openEntity(x.dataset.ent); }; });
  }

  function entNotes(e) {
    var v = "";
    try { v = localStorage.getItem("note:" + e.entity) || ""; } catch (x) {}
    return '<div class="sec-h">Investigator notes</div>' +
      '<textarea style="width:100%;height:180px;background:#0b0f14;border:1px solid var(--border);' +
      'border-radius:8px;color:var(--text);font:13px var(--ui);padding:10px;resize:vertical;outline:none" ' +
      'placeholder="Notes are saved locally in this browser…">' + esc(v) + "</textarea>" +
      '<div class="disc">Notes are the investigator\'s own. Marking a lead verified is a human decision, recorded to the audit log — never an automated conclusion.</div>';
  }

  /* ==================================================== widgets */
  function renderActivity() {
    api("/api/audit?limit=8").then(function (a) {
      var blocks = (a.blocks || []).slice().reverse();
      var ic = { GRAPH_QUERY: ["b", "🔗"], DATA_ACCESSED: ["b", "🔎"], ADMIN_ACTION: ["a", "⚙"],
        ENTITY_SEARCHED: ["b", "👤"], LEAD_GENERATED: ["r", "⚠"], GENESIS: ["m", "🔒"] };
      $("activityList").innerHTML = blocks.map(function (bk) {
        var t = ic[bk.action_type] || ic[bk.action] || ["m", "•"];
        return '<div class="wi"><div class="wic si ' + t[0] + '">' + t[1] + "</div><div>" +
          '<div class="wt">' + esc((bk.action || "").split(":")[0]) + "</div>" +
          '<div class="wd">' + esc((bk.action || "").split(":").slice(1).join(":").trim() || bk.officer) + "</div></div>" +
          '<div class="wtime">' + esc((bk.timestamp || "").slice(11, 16)) + "</div></div>";
      }).join("");
    });
  }

  function renderMiniTimeline() {
    var evs = (DATA.timeline.events || []).filter(function (e) { return e.timestamp && !e.timeless; });
    // pick the 6 "milestone" events: FIRs, big transfers, travel, first/last
    var mile = evs.filter(function (e) {
      return e.type === "FIR" || (e.type === "TRANSACTION" && e.amount_inr >= 100000) ||
        e.type === "TRAVEL" || (e.type === "CALL_ACTIVITY" && e.call_count >= 8);
    });
    // dedupe by day, keep up to 6 spread across the case window
    var byDay = {}; mile.forEach(function (e) { byDay[e.timestamp.slice(0, 10)] = e; });
    var days = Object.keys(byDay).sort();
    if (days.length > 6) { var step = (days.length - 1) / 5; var pick = [];
      for (var i = 0; i < 6; i++) pick.push(days[Math.round(i * step)]); days = pick; }
    var col = { FIR: "#4a9eff", TRANSACTION: "#d29922", TRAVEL: "#3fb950", CALL_ACTIVITY: "#f85149" };
    var tl = $("mtlTrack");
    if (!days.length) { tl.innerHTML = '<div style="color:var(--muted);font-size:12px;text-align:center">No milestone events in window.</div>'; return; }
    $("tlSub").textContent = "anchored to " + (DATA.timeline.clock.anchor || "").slice(0, 10);
    tl.innerHTML = days.map(function (d, i) {
      var e = byDay[d]; var pct = days.length === 1 ? 50 : (i / (days.length - 1)) * 100;
      var lbl = e.type === "FIR" ? "FIR" : e.type === "TRANSACTION" ? inr(e.amount_inr).replace("₹", "₹") :
        e.type === "TRAVEL" ? "Travel" : e.call_count + " calls";
      return '<div class="mtl-ev" style="left:' + pct + "%;background:" + (col[e.type] || "#8b949e") + '" title="' +
        esc(e.summary) + '"></div><div class="mtl-lb" style="left:' + pct + '%"><div class="d">' +
        d.slice(5) + '</div><div class="t">' + esc(lbl) + "</div></div>";
    }).join("");
  }

  // Every insight shows the records behind it and opens a drawer with its
  // algorithm + uncertainty — a confidence number with no citation is not
  // something this board is allowed to show.
  function renderInsights() {
    var items = (DATA.insight_records || []).slice(0, 6);
    $("insightList").innerHTML = items.map(function (it, i) {
      var recs = (it.source_records || []).slice(0, 3);
      return '<div class="insight" data-ins="' + i + '" role="button" tabindex="0"><div class="in-n">' + (i + 1) + "</div><div>" +
        esc(it.detail) +
        '<div style="margin-top:4px;font:11px var(--mono);color:var(--muted)">' +
        recs.map(function (r) { return '<span class="chip-r" data-rec="' + esc(r) + '">[' + esc(r) + "]</span>"; }).join(" ") +
        ((it.source_records || []).length > 3 ? " +" + ((it.source_records || []).length - 3) : "") +
        (it.confidence ? ' <span class="in-c">' + esc(it.confidence) + "% conf.</span>" : "") +
        "</div></div></div>";
    }).join("");
    $("insightList").querySelectorAll("[data-rec]").forEach(function (x) {
      x.onclick = function (ev) { ev.stopPropagation(); openRecordDrawer(x.dataset.rec); };
    });
    $("insightList").querySelectorAll("[data-ins]").forEach(function (x) {
      x.onclick = function () { openInsightDrawer(items[x.dataset.ins]); };
      x.onkeydown = function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); x.click(); } };
    });
  }
  function openInsightDrawer(it) {
    var html = dwSec("Why flagged", '<div class="dw-txt">' + esc(it.detail) + "</div>");
    html += dwSec("Algorithm", '<div class="dw-txt">' + esc(it.algorithm || "—") + "</div>");
    if (it.confidence != null) html += dwSec("Confidence", '<div class="dw-kv"><span>Confidence</span>' + esc(it.confidence) + "%</div>" +
      '<div class="dw-txt" style="color:var(--muted);font-size:12px">Derived from the cited records; a structural observation, not a probability of guilt.</div>');
    if (it.entities && it.entities.length) html += dwSec("Entities", it.entities.map(function (n) {
      return '<div class="dw-kv"><span>Entity</span><span class="chip-e" data-ent="' + esc(n) + '">' + esc(n) + " ↗</span></div>"; }).join(""));
    html += dwSec("Evidence (" + (it.source_records || []).length + " records)", recList(it.evidence || [], it.evidence_truncated));
    if (it.uncertainty && it.uncertainty.length) html += dwSec("Uncertainty", it.uncertainty.map(function (u) {
      return '<div class="rp-disc" style="background:rgba(210,153,34,.08);color:#d29922;border-color:#9e6a03">' + esc(u) + "</div>"; }).join(""));
    html += '<div class="disc">' + esc(it.verification_notice || "Investigative lead — requires human verification.") + "</div>";
    $("dwTitle").textContent = it.headline || "Insight";
    $("dwBody").innerHTML = html; $("drawer").hidden = false; wireRecs();
    $("dwBody").querySelectorAll("[data-ent]").forEach(function (x) { x.onclick = function () { closeDrawer(); openEntity(x.dataset.ent); }; });
  }

  /* ==================================================== leads / ER / audit */
  var FCLASS = { "Financial anomaly": "#d29922", "Cross-community connection": "#4a9eff",
    "Communication anomaly": "#f85149", "Temporal correlation": "#a371f7",
    "Location correlation": "#3fb950", "Multi-source confirmation": "#8a6e22",
    "Network centrality": "#6e7681", "Entity resolution": "#a8874c" };
  function bandColor(b) { return b === "PRIORITY REVIEW" ? "#f85149" : b === "REVIEW" ? "#d29922" :
    b === "MONITOR" ? "#4a9eff" : "#6e7681"; }
  function renderLeads() {
    $("leadsList").innerHTML = (DATA.leads || []).map(function (l) {
      var bars = l.factors.map(function (f) { return '<i style="width:' + f.points + "%;background:" +
        (FCLASS[f.factor] || "#6e7681") + '"></i>'; }).join("");
      var bc = bandColor(l.band);
      return '<div class="leadcard"><div class="lc-top">' +
        '<span class="lc-name" data-lead="' + esc(l.entity) + '">' + esc(l.entity) + "</span>" +
        verdictBadge("lead", l.entity) +
        '<span class="lc-band" style="color:' + bc + ';background:' + bc + '22;border:1px solid ' + bc + '55">' + esc(l.band) + "</span>" +
        '<span class="lc-score" style="color:' + bc + '">' + l.lead_score + "</span></div>" +
        '<div class="lc-bar">' + bars + "</div>" +
        // "Every point is explained": one row per factor with its reason and the
        // records that earned it, not just a coloured chip.
        l.factors.map(function (f) {
          var recs = (f.source_records || []).slice(0, 3);
          return '<div class="fac-row"><b style="color:' + (FCLASS[f.factor] || "#6e7681") + '">+' + f.points +
            "</b><span><span class=\"fac-name\">" + esc(f.factor) + "</span> — " + esc(f.reason || "") +
            (recs.length ? " " + recs.map(function (r) { return '<span class="chip-r" data-rec="' + esc(r) + '">[' + esc(r) + "]</span>"; }).join(" ") : "") +
            "</span></div>";
        }).join("") +
        (l.uncertainty && l.uncertainty.length ? '<div class="disc" style="margin-top:8px">' + esc(l.uncertainty[0]) + "</div>" : "") +
        decisionBar("lead", l.entity, ["VERIFIED", "DISMISSED", "NEEDS_REVIEW"]) + "</div>";
    }).join("") + '<div class="disc" style="margin-top:14px">Lead scores rank what to examine next. They are not a determination of guilt. Verifying a lead records your decision to the audit log.</div>';
    $("leadsList").querySelectorAll("[data-lead]").forEach(function (x) {
      x.onclick = function () { showView("network"); openEntity(x.dataset.lead); };
    });
    $("leadsList").querySelectorAll("[data-rec]").forEach(function (x) {
      x.onclick = function (ev) { ev.stopPropagation(); openRecordDrawer(x.dataset.rec); };
    });
    wireDecide($("leadsList"));
  }

  function renderER() {
    var er = DATA.entity_resolution || {};
    var html = (er.clusters || []).map(function (c) {
      return '<div class="card" style="padding:14px 16px;margin-bottom:12px"><div style="font:600 14px var(--ui);margin-bottom:8px">' +
        esc(c.anchor_entity) + ' <span class="tag amber" style="margin-left:6px">' + esc(c.status) + "</span></div>" +
        c.members.map(function (m) { return '<span class="lc-fac" style="margin:2px 4px 2px 0;display:inline-block">' + esc(m) + "</span>"; }).join("") +
        '<div class="disc" style="margin-top:8px">Weakest link ' + c.linking_confidence_min + "%. " + esc(c.recommended_action) + "</div></div>";
    }).join("");
    html += '<div class="card" style="padding:14px 16px"><div style="font:600 13px var(--ui);color:var(--muted);margin-bottom:10px">PAIRWISE MATCHES</div>' +
      (er.matches || []).map(function (m) {
        var bc = m.decision === "LIKELY_SAME_ENTITY" ? "#f85149" : m.decision === "POSSIBLE_SAME_ENTITY" ? "#d29922" : "#6e7681";
        var mid = m.entity + " ↔ " + m.candidate;
        return '<div style="padding:8px 0;border-bottom:1px solid #21262d"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">' +
          '<b style="font:600 13px var(--mono);color:' + bc + '">' + m.confidence + "%</b> " +
          '<span class="tag mut" style="color:' + bc + '">' + esc(m.decision.replace(/_/g, " ")) + "</span>" +
          '<span style="font-size:13px">' + esc(mid) + "</span>" + verdictBadge("identity", mid) + "</div>" +
          // "How do you know it's the same person?" — every scored reason, with
          // the negatives kept (they are what prevent a false merge).
          (m.reasons || []).map(function (r) {
            return '<div class="fac-row"><b style="color:' + (r.points < 0 ? "#f85149" : "#3fb950") + '">' +
              (r.points > 0 ? "+" : "") + r.points + "</b><span><span class=\"fac-name\">" + esc(r.reason) + "</span> — " + esc(r.detail || "") + "</span></div>";
          }).join("") +
          (m.uncertainty && m.uncertainty.length ? '<div class="disc" style="margin-top:6px">' + esc(m.uncertainty[0]) + "</div>" : "") +
          decisionBar("identity", mid, ["CONFIRMED", "REJECTED", "NEEDS_REVIEW"]) + "</div>";
      }).join("") + "</div>";
    $("erList").innerHTML = html;
    wireDecide($("erList"));
  }

  function renderFullTimeline() {
    var evs = (DATA.timeline.events || []).filter(function (e) { return e.timestamp; })
      .sort(function (a, b) { return a.timestamp < b.timestamp ? -1 : 1; });
    var col = { FIR: "#4a9eff", TRANSACTION: "#d29922", TRAVEL: "#3fb950", CALL_ACTIVITY: "#f85149",
      CUSTODY_OVERLAP: "#a371f7", VEHICLE_REGISTRATION: "#6e7681" };
    $("tlSub2").textContent = "anchored to latest record " + (DATA.timeline.clock.anchor || "").slice(0, 10) + " (not today's date)";
    $("fullTimeline").innerHTML = evs.map(function (e) {
      return '<div style="display:flex;gap:12px;padding:9px 0;border-bottom:1px solid #21262d">' +
        '<div style="width:96px;flex-shrink:0;font:500 11px var(--mono);color:var(--muted)">' + esc((e.timestamp || "").slice(0, 10)) + "</div>" +
        '<div style="width:9px;height:9px;border-radius:50%;margin-top:4px;flex-shrink:0;background:' + (col[e.type] || "#8b949e") + '"></div>' +
        '<div><div style="font:500 13px var(--ui)">' + esc(e.type.replace(/_/g, " ")) + "</div>" +
        '<div style="font:12px var(--ui);color:var(--muted)">' + esc(e.summary) + "</div></div></div>";
    }).join("");
  }

  function renderAudit() {
    api("/api/audit?limit=40").then(function (a) {
      $("auditState").textContent = a.chain_valid ? "● SEALED · " + a.total_blocks + " blocks" : "● BROKEN at block " + a.tampered_block;
      $("auditState").style.color = a.chain_valid ? "var(--green)" : "var(--red)";
      $("auditList").innerHTML = a.blocks.slice().reverse().map(function (b) {
        return '<div style="display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #21262d;font-size:12.5px">' +
          '<span style="font:600 11px var(--mono);color:var(--accent2);width:44px">#' + b.index + "</span>" +
          '<span style="font:11px var(--mono);color:var(--muted);width:130px">' + esc((b.timestamp || "").replace("T", " ")) + "</span>" +
          '<span style="width:110px;color:var(--muted)">' + esc(b.officer) + "</span>" +
          '<span style="flex:1">' + esc(b.action) + "</span>" +
          '<span style="font:11px var(--mono);color:var(--dim)">' + esc((b.hash || "").slice(0, 10)) + "</span></div>";
      }).join("");
    });
  }

  /* ==================================================== ingestion batches (undo) */
  // "How do I delete what I added?" — you don't delete evidence, you retract
  // it: the batch is hidden from the board, its rows stay on file, the reason
  // goes to the audit log, and it can be restored. The shipped corpus has no
  // batch and so cannot be retracted from here.
  function renderIngestion() {
    var el = $("batchList"); if (!el) return;
    el.innerHTML = '<div class="dw-txt" style="color:var(--muted)">Loading batches…</div>';
    api("/api/intake/batches").then(function (d) {
      var bs = d.batches || [];
      if (!bs.length) {
        el.innerHTML = '<div class="card"><div class="ent-empty">Nothing has been added through Add Data yet. ' +
          "The shipped corpus is not a batch — it is restored with <code>python backend/reset_demo_data.py</code>.</div></div>";
        return;
      }
      el.innerHTML = bs.map(function (b) {
        var ids = b.record_ids || [];
        return '<div class="card" style="padding:14px 16px;margin-bottom:12px' + (b.retracted ? ";opacity:.75" : "") + '">' +
          '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">' +
          '<b style="font:600 13px var(--mono);color:var(--accent2)">' + esc(b.batch_id) + "</b>" +
          '<span class="tag blue">' + esc(b.source_type) + "</span>" +
          (b.staged ? '<span class="tag mut">staged</span>' : "") +
          (b.retracted ? '<span class="tag red">RETRACTED</span>' : '<span class="tag green">on board</span>') +
          '<span style="margin-left:auto;font:11px var(--mono);color:var(--muted)">' + esc((b.timestamp || "").replace("T", " ")) + " · " + esc(b.officer) + "</span></div>" +
          '<div style="margin-top:8px;font:12px var(--ui);color:var(--text2)">' + ids.length + " record(s): " +
          ids.slice(0, 10).map(function (id) { return '<span class="chip-r" data-rec="' + esc(id) + '">[' + esc(id) + "]</span>"; }).join(" ") +
          (ids.length > 10 ? " +" + (ids.length - 10) + " more" : "") + "</div>" +
          (b.retracted && b.retraction ? '<div class="disc" style="margin-top:8px">Retracted by ' + esc(b.retraction.officer) + " on " +
            esc((b.retraction.timestamp || "").replace("T", " ")) + ": " + esc(b.retraction.reason) + "</div>" : "") +
          '<div class="decide">' + (b.retracted
            ? '<button class="dbtn ok" data-restore="' + esc(b.batch_id) + '">↺ Restore to board</button>'
            : '<button class="dbtn no" data-retract="' + esc(b.batch_id) + '">✕ Retract batch</button>') + "</div></div>";
      }).join("") + '<div class="disc">' + esc(d.note || "") + "</div>";
      el.querySelectorAll("[data-rec]").forEach(function (x) { x.onclick = function () { openRecordDrawer(x.dataset.rec); }; });
      el.querySelectorAll("[data-retract]").forEach(function (x) {
        x.onclick = function () {
          var reason = window.prompt("Why is batch " + x.dataset.retract + " being retracted? (recorded in the audit log)", "");
          if (reason === null) return;
          if (reason.trim().length < 3) { toast("A reason is required to retract records"); return; }
          post("/api/intake/retract", { batch_id: x.dataset.retract, reason: reason, officer: OFFICER })
            .then(function (r) { toast(r.retracted_ids.length + " record(s) retracted — board rebuilt"); renderIngestion(); window.refreshCase(); })
            .catch(function (e) { toast("Could not retract: " + e); });
        };
      });
      el.querySelectorAll("[data-restore]").forEach(function (x) {
        x.onclick = function () {
          if (!window.confirm("Restore batch " + x.dataset.restore + " to the board?")) return;
          post("/api/intake/restore", { batch_id: x.dataset.restore, officer: OFFICER })
            .then(function (r) { toast(r.restored_ids.length + " record(s) restored — board rebuilt"); renderIngestion(); window.refreshCase(); })
            .catch(function (e) { toast("Could not restore: " + e); });
        };
      });
    }).catch(function (e) { el.innerHTML = '<div class="ent-empty">Could not load batches: ' + esc(String(e)) + "</div>"; });
  }

  /* ==================================================== views */
  var VIEW_TITLE = { overview: "Case Board", network: "Network Graph", timeline: "Timeline",
    map: "Map & Location", analytics: "Analytics", reports: "Reports", leads: "Investigative Leads",
    entitysearch: "Entity Resolution", audit: "Audit Log", ingestion: "Data Ingestion",
    documents: "Documents", settings: "Settings" };
  function showView(name) {
    document.querySelectorAll(".view").forEach(function (v) { v.classList.toggle("on", v.id === "view-" + name); });
    document.querySelectorAll(".navitem").forEach(function (t) { t.classList.remove("on"); });
    var nav = document.querySelector('.navitem[data-view="' + name + '"]'); if (nav) nav.classList.add("on");
    var vt = $("viewTitle"); if (vt) vt.textContent = VIEW_TITLE[name] || name;
    if (name === "network" && !NET2) buildGraph("graph2");
    if (name === "audit") renderAudit();
    if (name === "ingestion") renderIngestion();
    if ((name === "network" || name === "overview") && NET) setTimeout(function () { NET.redraw(); }, 60);
  }

  /* ==================================================== window filter */
  function applyWindow(w) {
    WINDOW = w;
    document.querySelectorAll("#gwin span").forEach(function (s) { s.classList.toggle("on", s.dataset.window === w); });
    api("/api/graph?window=" + w).then(function (d) {
      DATA = d; renderStats(); renderMiniTimeline(); renderInsights(); renderFullTimeline(); renderAlerts();
      buildGraph("graph"); if (NET2) buildGraph("graph2");
      toast(w === "all" ? "Showing all recorded activity" : "Window: last " + w);
    }).catch(function (e) { toast("Window filter failed: " + e); });
  }
  window.refreshCase = function () { applyWindow(WINDOW); };

  /* ==================================================== global search */
  function wireSearch() {
    var inp = $("gsearchInput"), res = $("gresults");
    function run() {
      var q = inp.value.toLowerCase().trim();
      if (!q) { res.classList.add("hidden"); return; }
      var hits = DATA.nodes.filter(function (n) {
        return n.id.toLowerCase().indexOf(q) >= 0 ||
          (n.phones || []).some(function (p) { return p.indexOf(q) >= 0; }) ||
          (n.accounts || []).some(function (a) { return a.toLowerCase().indexOf(q) >= 0; }) ||
          (n.vehicles || []).some(function (v) { return v.toLowerCase().indexOf(q) >= 0; });
      }).slice(0, 8);
      res.innerHTML = hits.length ? hits.map(function (n) {
        var k = KIND[n.kind] || KIND.person;
        return '<div class="gr" data-hit="' + esc(n.id) + '"><span>' + k.i + "</span><div><div>" + esc(n.id) +
          '</div><div style="font:11px var(--ui);color:var(--muted)">' + k.label +
          (n.lead_score ? " · lead " + n.lead_score : "") + "</div></div></div>";
      }).join("") : '<div class="gr" style="color:var(--muted)">No match</div>';
      res.classList.remove("hidden");
      res.querySelectorAll("[data-hit]").forEach(function (x) {
        x.onclick = function () { res.classList.add("hidden"); inp.value = ""; showView("overview"); openEntity(x.dataset.hit); };
      });
    }
    inp.oninput = run;
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") { e.preventDefault(); inp.focus(); }
      if (e.key === "Escape") res.classList.add("hidden");
    });
    document.addEventListener("click", function (e) { if (!$("gsearch").contains(e.target)) res.classList.add("hidden"); });
  }

  /* ==================================================== crack the case */
  var crack = { step: 0, steps: [] };
  function roles() {
    var byComm = {};
    DATA.nodes.filter(function (n) { return n.kind === "person"; }).forEach(function (p) {
      if (!byComm[p.community] || p.pagerank > byComm[p.community].pagerank) byComm[p.community] = p;
    });
    var leaders = Object.values(byComm).sort(function (a, b) { return b.pagerank - a.pagerank; }).slice(0, 2).map(function (p) { return p.id; });
    var burner = (DATA.nodes.find(function (n) { return n.kind === "unresolved_number"; }) || {}).id;
    var shell = (DATA.nodes.find(function (n) { return n.kind === "shell_company"; }) || {}).id;
    var ctrl = controllerName();
    return { leaders: leaders, burner: burner, shell: shell, ctrl: ctrl };
  }
  // Every walkthrough sentence is derived from the payload and cites the
  // records behind the edges it talks about — no hardcoded years, counts or
  // names, so the story cannot drift from the data it claims to describe.
  function edgeBetween(a, b) {
    return (DATA.edges || []).find(function (e) {
      return (e.from === a && e.to === b) || (e.from === b && e.to === a); });
  }
  function citeEdges(pairs, extra) {
    var seen = {}, out = [];
    var add = function (r) { if (r && !seen[r]) { seen[r] = 1; out.push(r); } };
    pairs.forEach(function (p) { var e = edgeBetween(p[0], p[1]); if (e) (e.source_records || []).forEach(add); });
    (extra || []).forEach(add);
    return out;
  }
  function buildCrackSteps() {
    var r = roles();
    var spike = (DATA.call_spikes || [])[0];
    var ctrl = (DATA.network_controllers || [])[0] || {};
    var jail = r.leaders.length === 2 ? edgeBetween(r.leaders[0], r.leaders[1]) : null;
    if (jail && (jail.rel_types || [jail.rel]).indexOf("jailed-together") < 0) jail = null;
    var jailYear = jail && jail.start_time ? jail.start_time.slice(0, 4) : "";
    var caseYear = (DATA.timeline.clock.anchor || "").slice(0, 4);
    var gap = jailYear && caseYear ? Number(caseYear) - Number(jailYear) : 0;
    var pairsWith = function (x, list) { return list.filter(Boolean).map(function (y) { return [x, y]; }); };
    crack.steps = [
      { t: "The clusters", nodes: r.leaders, recs: [],
        b: "Community detection separates the network into " + DATA.stats.communities + " clusters. The two most central figures are <b>" + esc(r.leaders[0]) + "</b> and <b>" + esc(r.leaders[1]) + "</b>. Clusters are statistical groupings, not proven organisations.",
        s: "algorithm: greedy modularity community detection" },
      { t: "The broker", nodes: [r.burner].concat(r.leaders), recs: citeEdges(pairsWith(r.burner, r.leaders)),
        b: "Unresolved number <b>" + esc(r.burner) + "</b> contacts entities in both clusters. No subscriber is registered to it, so the handset holder is not established by these records.",
        s: "evidence: call detail records" },
      { t: "Follow the money", nodes: [r.shell].concat(r.leaders), recs: citeEdges(pairsWith(r.shell, r.leaders)),
        b: "Funds converge on <b>" + esc(r.shell) + "</b> from multiple parties and are forwarded onward — the movement pattern associated with layering. Consolidation is also ordinary commerce.",
        s: "evidence: FIU-IND transaction records" },
      { t: "Potential network controller", nodes: [r.ctrl, r.shell],
        recs: citeEdges([[r.ctrl, r.shell]], (ctrl.source_records || []).slice(0, 3)),
        b: "Money exits to <b>" + esc(r.ctrl) + "</b>" + (ctrl.net_inflow_inr ? " (" + inr(ctrl.net_inflow_inr) + " net)" : "") +
          ", who is named in <b>" + (ctrl.fir_mentions || 0) + " FIRs</b> in this corpus — financially central, absent from the case record. Flagged as an investigative lead for review, not a finding of involvement." +
          (ctrl.uncertainty && ctrl.uncertainty[0] ? " " + esc(ctrl.uncertainty[0]) : ""),
        s: "heuristic: net inflow, no FIR mention" },
      { t: "Shared custody", nodes: r.leaders, recs: jail ? (jail.source_records || []) : [],
        b: jail ? "Both cluster leaders overlapped in custody" + (jailYear ? " in " + esc(jailYear) : "") +
            (jail.source ? " (" + esc(jail.source) + ")" : "") + ". Shared custody establishes proximity, not association" +
            (gap > 0 ? " — and it predates the case window by " + gap + " years." : ".")
          : "No shared custody is recorded between the cluster leaders in this corpus.",
        s: "evidence: e-Prisons roster" },
      { t: "The anomaly", nodes: spike ? [r.burner].concat(r.leaders) : r.leaders, recs: spike ? (spike.source_records || []) : [],
        b: spike ? "Communication spike: <b>" + esc(spike.pair) + "</b> reached <b>" + spike.calls_that_day + " calls</b> on " + esc(spike.date) + " — " + (spike.baseline.ratio) + "× this pair's median day. A deviation is a lead to examine, not proof of an offence."
          : "No communication spike exceeded baseline in the current window.",
        s: "algorithm: per-pair volume vs baseline" },
    ];
  }
  function showCrack() {
    var st = crack.steps[crack.step];
    var recs = (st.recs || []).slice(0, 5);
    $("ckStep").textContent = "STEP " + (crack.step + 1) + " / " + crack.steps.length;
    $("ckTitle").textContent = st.t;
    $("ckBody").innerHTML = st.b + '<span class="src">' + esc(st.s) +
      (recs.length ? " · " + recs.map(function (id) { return '<span class="chip-r" data-rec="' + esc(id) + '">[' + esc(id) + "]</span>"; }).join(" ") +
        ((st.recs || []).length > 5 ? " +" + ((st.recs || []).length - 5) + " more" : "") : "") + "</span>";
    $("ckBody").querySelectorAll("[data-rec]").forEach(function (x) {
      x.onclick = function () { openRecordDrawer(x.dataset.rec); };
    });
    $("ckPrev").disabled = crack.step === 0;
    $("ckNext").textContent = crack.step === crack.steps.length - 1 ? "Done ✓" : "Next ▶";
    // highlight
    if (NET && nodesDS) {
      NET.selectNodes((st.nodes || []).filter(function (n) { return n; }));
      NET.fit({ nodes: (st.nodes || []).filter(function (n) { return n; }), animation: { duration: 700 } });
    }
  }
  function startCrack() {
    showView("overview"); buildCrackSteps(); crack.step = 0; $("crack").hidden = false; showCrack();
  }
  window.endCrack = function () { $("crack").hidden = true; if (NET) { NET.unselectAll(); NET.fit({ animation: true }); } };

  /* ==================================================== add data modal */
  var EX = {
    fir: { text: "FIRST INFORMATION REPORT\nFIR No: 099/2026\nPolice Station: Delhi\nDate: 15-04-2026\nSections: NDPS Act 8/20\nNARRATIVE:\nAccused Arjun Mehta was apprehended and named associate Ravi Malhotra. Mobile number 9811000099 recovered." },
    bank: { json: '[{"from_account":"ACC9003","to_account":"ACC7777","amount_inr":65000,"date":"2026-03-22"},{"from_account":"ACC9003","to_account":"ACC7777","amount_inr":null,"date":"2026-03-22"}]' },
    cdr: { json: '[{"caller":"9811000002","receiver":"9822000001","timestamp":"2026-03-22T14:32:00","duration_sec":342,"tower_id":"TWR415"}]' },
    vehicles: { json: '[{"registration_number":"MH12AB0007","registered_owner":"New Person","vehicle_type":"Truck"}]' },
    phone_directory: { json: '[{"phone":"9811000200","registered_name":"New Person"}]' },
    accounts: { json: '[{"account":"ACC9200","holder_name":"New Person"}]' },
    travel: { json: '[{"passenger_name":"Vikram Rathore","from_city":"Delhi","to_city":"Dubai","date":"2026-03-25","flight":"EK511"}]' },
    prison: { json: '[{"prisoner_name":"New Person","jail":"Tihar Jail","cell_block":"Block-4","from_date":"2022-02-10","to_date":"2022-11-30"}]' },
    cctv: { json: '[{"timestamp":"2026-03-18T19:10:00","camera_id":"CAM-042","location":"Mundra Port","vehicle_number":"KA01AB1234","vehicle_match_confidence":94}]' },
    gps: { json: '[{"vehicle_id":"KA01AB1234","timestamp":"2026-03-18T18:42:00","latitude":17.4485,"longitude":78.3908,"speed_kmh":42}]' },
    social: { json: '[{"account_id":"ACC_SOC_001","account_name":"user_example","timestamp":"2026-03-18T20:10:00","text":"Big shipment tomorrow at the port.","mentioned_locations":"Mundra Port","hashtags":"#shipment"}]' },
  };
  window.closeAddData = function () { $("addModal").hidden = true; };
  function amBody() { return { source_type: $("amSource").value, format: $("amFormat").value,
    payload: $("amPayload").value, include_conflicts: $("amConflicts").checked }; }
  function amSyncFormat() {
    var fir = $("amSource").value === "fir";
    [].forEach.call($("amFormat").options, function (o) {
      o.disabled = (fir && o.value !== "text") || (!fir && o.value === "text");
    });
    $("amFormat").value = fir ? "text" : ($("amFormat").value === "text" ? "json" : $("amFormat").value);
  }
  function amRenderPreview(d) {
    var s = d.summary, st = function (n, l, c) { return n ? '<span class="am-stat ' + c + '">' + n + " " + l + "</span>" : ""; };
    var h = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin:10px 0"><span class="am-stat mut">' + s.total + " record(s)</span>" +
      st(s.valid, "valid", "ok") + st(s.partial, "partial", "warn") + st(s.invalid, "invalid", "bad") +
      st(s.conflicts, "conflict", "bad") + st(s.duplicates, "duplicate", "warn") + "</div>";
    if (d.staged) h += '<div class="am-issue">Stored but not drawn on the board yet — needs the Phase 2 map/OSINT view.</div>';
    h += d.records.map(function (r) {
      var q = r.quality, sc = q.validation_status === "VALID" ? "ok" : q.validation_status === "PARTIAL" ? "warn" : "bad";
      var flds = r.parsed ? Object.keys(r.parsed).map(function (k) { var v = r.parsed[k];
        if (v == null || v === "") return "<b>" + esc(k) + '</b>=<span class="nul">null</span>';
        if (Array.isArray(v)) v = v.join(", ") || "—"; return "<b>" + esc(k) + "</b>=" + esc(v); }).join(" · ") : "";
      return '<div class="am-rec"><div class="am-rec-top"><span>' + esc(r.record_id) + "</span>" +
        '<span class="am-stat ' + sc + '">' + q.validation_status + "</span>" +
        '<span class="am-stat mut">' + q.level + " · " + q.completeness + "%</span>" +
        (r.committable ? "" : '<span class="am-stat bad">held</span>') + "</div>" +
        '<div class="am-fields">' + flds + "</div>" +
        (r.issues && r.issues.length ? '<div class="am-issue">! ' + r.issues.map(esc).join("<br>! ") + "</div>" : "") +
        (r.conflicts && r.conflicts.length ? '<div class="am-conflict">CONFLICT — ' + esc(r.conflicts[0].detail) + "</div>" : "") + "</div>";
    }).join("");
    $("amResult").innerHTML = h; $("amCommit").disabled = s.committable === 0;
  }
  function wireAddData() {
    api("/api/intake/schema").then(function (d) {
      var order = ["fir", "cdr", "bank", "accounts", "phone_directory", "vehicles", "travel", "prison", "cctv", "gps", "social"];
      $("amSource").innerHTML = order.filter(function (k) { return d.sources[k]; }).map(function (k) {
        return '<option value="' + k + '">' + esc(d.sources[k].label) + "</option>"; }).join("");
      amSyncFormat();
    });
    $("addDataBtn").onclick = function () { $("addModal").hidden = false; $("amResult").innerHTML = ""; $("amCommit").disabled = true; };
    $("amSource").onchange = amSyncFormat;
    $("amExample").onclick = function () { var ex = EX[$("amSource").value] || {}; var f = $("amFormat").value;
      $("amPayload").value = ex[f] || ex.json || ex.text || ""; };
    $("amValidate").onclick = function () {
      if (!$("amPayload").value.trim()) { toast("Paste a record or load an example"); return; }
      $("amResult").innerHTML = '<div class="am-issue">Validating…</div>';
      post("/api/intake/preview", amBody()).then(amRenderPreview)
        .catch(function (e) { $("amResult").innerHTML = '<div class="am-conflict">' + esc(String(e)) + "</div>"; });
    };
    $("amCommit").onclick = function () {
      $("amCommit").disabled = true;
      post("/api/intake/commit", amBody()).then(function (d) {
        var held = (d.held || []).map(function (h) { return h.record_id + ": " + h.reason; });
        // No forced reload: keep the held-record reasons on screen and refresh
        // the board in place when the user is done reading them.
        $("amResult").innerHTML = '<div class="am-done">Added <b>' + d.written + "</b> record(s)" +
          (d.written_ids && d.written_ids.length ? " (" + esc(d.written_ids.slice(0, 8).join(", ")) + ")" : "") + ". " + esc(d.note || "") +
          (d.batch_id ? '<div style="margin-top:6px;font:11px var(--mono);color:var(--muted)">Batch ' + esc(d.batch_id) +
            ' — added in error? <a data-batches style="color:var(--accent2);cursor:pointer">Data Ingestion → Retract batch</a></div>' : "") + "</div>" +
          (held.length ? '<div class="am-issue" style="margin-top:6px">Held for review:<br>' + held.map(esc).join("<br>") + "</div>" : "") +
          (d.written && !d.staged ? '<button class="abtn blue" id="amRefresh" style="margin-top:10px">Close &amp; refresh board</button>' : "");
        var rb = $("amRefresh");
        if (rb) rb.onclick = function () { closeAddData(); toast("Refreshing board with new data…"); window.refreshCase(); };
        var gb = $("amResult").querySelector("[data-batches]");
        if (gb) gb.onclick = function () { closeAddData(); showView("ingestion"); };
      }).catch(function (e) { $("amResult").innerHTML = '<div class="am-conflict">' + esc(String(e)) + "</div>"; $("amCommit").disabled = false; });
    };
    $("amFile").onchange = function (ev) { var f = ev.target.files && ev.target.files[0]; if (!f) return;
      var rd = new FileReader(); rd.onload = function () { $("amPayload").value = rd.result;
        if (/\.csv$/i.test(f.name)) $("amFormat").value = "csv"; else if (/\.json$/i.test(f.name)) $("amFormat").value = "json";
        else if (/\.txt$/i.test(f.name) && $("amSource").value === "fir") $("amFormat").value = "text"; }; rd.readAsText(f); };
  }

  /* ==================================================== tamper + report */
  function wireMisc() {
    // Tamper demo: SHOW the chain broken for a moment — the audit "wow" is
    // the red state, not a toast that disappears in two seconds.
    $("tamperBtn").onclick = function () {
      api("/api/audit/tamper-demo").then(function (d) {
        var st = $("auditState");
        if (d.chain_valid_after_tampering === false) {
          st.textContent = "● BROKEN at block " + d.first_broken_block + " — hash mismatch detected";
          st.style.color = "var(--red)";
          $("auditList").style.opacity = ".45";
          toast("Block " + d.first_broken_block + " was edited in memory — verification failed");
          setTimeout(function () { $("auditList").style.opacity = ""; renderAudit(); toast("Chain restored and re-verified"); }, 3200);
        } else { toast("Chain intact"); renderAudit(); }
      }).catch(function (e) { toast("Tamper demo failed: " + e); });
    };
    $("reportBtn").onclick = function () { buildReport(); };
    $("crackBtn").onclick = startCrack;
    $("ckNext").onclick = function () { if (crack.step >= crack.steps.length - 1) return endCrack();
      crack.step++; showCrack(); };
    $("ckPrev").onclick = function () { if (crack.step > 0) { crack.step--; showCrack(); } };
    document.querySelectorAll("#gwin span").forEach(function (s) {
      s.setAttribute("role", "button"); s.tabIndex = 0;
      s.onclick = function () { applyWindow(s.dataset.window); };
      s.onkeydown = function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); s.click(); } };
    });
    // Filter changes toggle visibility in place — no rebuild, no re-randomised layout.
    function applyGraphFilters() {
      if (!nodesDS || !edgesDS) return;
      var kf = $("filterKind").value, rf = $("filterRel").value, active = nodesInWindow();
      nodesDS.update(DATA.nodes.map(function (n) { return { id: n.id, hidden: !!((kf && n.kind !== kf) || !active[n.id]) }; }));
      edgesDS.update(edgesDS.get().map(function (e) { return { id: e.id, hidden: !!(rf && e._rel !== rf) }; }));
    }
    $("filterKind").onchange = applyGraphFilters;
    $("filterRel").onchange = applyGraphFilters;
    $("graphExpand").onclick = toggleGraphFull;
    $("graphSearch").oninput = function () {
      var q = this.value.toLowerCase().trim(); if (!q || !NET) return;
      var hit = DATA.nodes.find(function (n) { return n.id.toLowerCase().indexOf(q) >= 0; });
      if (hit) { NET.focus(hit.id, { scale: 1.1, animation: true }); NET.selectNodes([hit.id]); }
    };
    // Officer identity: click the chip to change; persisted per browser.
    var chip = $("officerChip");
    if (chip) {
      $("officerName").textContent = OFFICER;
      chip.onclick = function () {
        var v = window.prompt("Officer identity to record in the audit log:", OFFICER);
        if (!v || !/^[A-Za-z0-9 ._\-]{1,64}$/.test(v)) return;
        OFFICER = v; $("officerName").textContent = v;
        try { localStorage.setItem("prahari.officer", v); } catch (x) {}
        toast("Audit entries will be recorded as " + v);
      };
    }
    // Bell: jump to what needs a human decision.
    var bell = $("alertsBtn");
    if (bell) bell.onclick = function () { showView("leads"); };
    // Escape closes whichever overlay is open, innermost first.
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (!$("report").hidden) return closeReport();
      if (!$("addModal").hidden) return closeAddData();
      if (!$("drawer").hidden) return closeDrawer();
      if (!$("askPanel").hidden) return closeAsk();
      if (!$("crack").hidden) return endCrack();
      if ($("graphCard").classList.contains("fullscreen")) toggleGraphFull();
    });
  }

  /* ==================================================== nav wiring */
  function wireNav() {
    document.querySelectorAll(".navitem[data-view]").forEach(function (t) {
      t.setAttribute("role", "button"); t.tabIndex = 0;      // keyboard reachable
      t.onclick = function () { showView(t.dataset.view); };
      t.onkeydown = function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); t.click(); } };
    });
  }

  /* ==================================================== evidence drawer */
  window.closeDrawer = function () { $("drawer").hidden = true; };
  function dwSec(lbl, body) { return '<div class="dw-sec"><div class="dw-lbl">' + esc(lbl) + "</div>" + body + "</div>"; }
  function recList(records, truncated) {
    if (!records || !records.length) return '<div class="dw-txt">No source records.</div>';
    return records.map(function (r) {
      return '<div class="dw-rec" data-rec="' + esc(r.record_id) + '"><span class="rt">' +
        esc(r.source_type || "") + '</span><span class="rid">' + esc(r.record_id) + "</span>" +
        '<div class="rd">' + esc(r.detail || "") + (r.timestamp ? " · " + esc(String(r.timestamp).slice(0, 16).replace("T", " ")) : "") + "</div></div>";
    }).join("") + (truncated ? '<div class="dw-txt" style="color:var(--muted);margin-top:4px">+ ' + truncated + " more record(s)</div>" : "");
  }
  function wireRecs() {
    $("dwBody").querySelectorAll("[data-rec]").forEach(function (x) {
      x.onclick = function () { openRecordDrawer(x.dataset.rec); };
    });
  }
  function openRelationshipDrawer(a, b) {
    api("/api/relationship?a=" + encodeURIComponent(a) + "&b=" + encodeURIComponent(b))
      .then(function (e) {
        if (e.detail) { toast(e.detail); return; }
        var html = dwSec("Why this link exists",
          '<div class="dw-txt"><b>' + esc(a) + "</b> and <b>" + esc(b) +
          "</b> are linked because the records below place them together. Relations observed: " +
          esc((e.rel_types || [e.rel]).join(", ")) + ".</div>");
        html += dwSec("Relationship",
          '<div class="dw-kv"><span>Type</span>' + esc((e.rel_types || []).join(", ") || e.rel) + "</div>" +
          '<div class="dw-kv"><span>First observed</span>' + esc((e.start_time || "—").slice(0, 16).replace("T", " ")) + "</div>" +
          '<div class="dw-kv"><span>Last observed</span>' + esc((e.last_observed || "—").slice(0, 16).replace("T", " ")) + "</div>" +
          '<div class="dw-kv"><span>Observations</span>' + esc(e.observation_count) + "</div>" +
          (e.money_inr ? '<div class="dw-kv"><span>Value moved</span>' + inr(e.money_inr) + "</div>" : "") +
          '<div class="dw-kv"><span>Source types</span>' + esc((e.source_types || []).join(", ")) + "</div>");
        html += dwSec("Confidence " + e.confidence + "% — how it was derived",
          (e.confidence_breakdown || []).map(function (r) {
            return '<div class="confrow' + (r.points < 0 ? " neg" : "") + '"><span>' + esc(r.factor) + " · " +
              esc(r.detail) + "</span><b>" + (r.points > 0 ? "+" : "") + esc(r.points) + "</b></div>";
          }).join("") || '<div class="dw-txt">' + e.confidence + "%</div>");
        html += dwSec("Algorithm", '<div class="dw-txt">' + esc(e.algorithm) + "</div>");
        html += dwSec("Evidence (" + (e.source_records || []).length + " records)", recList(e.evidence, e.evidence_truncated));
        if (e.uncertainty && e.uncertainty.length)
          html += dwSec("Uncertainty", e.uncertainty.map(function (u) { return '<div class="rp-disc" style="background:rgba(210,153,34,.08);color:#d29922;border-color:#9e6a03">' + esc(u) + "</div>"; }).join(""));
        html += '<div class="disc">' + esc(e.verification_notice || "Investigative lead — requires human verification.") + "</div>";
        $("dwTitle").textContent = a + "  ↔  " + b;
        $("dwBody").innerHTML = html; $("drawer").hidden = false; wireRecs();
      }).catch(function () { toast("No recorded relationship between those two."); });
  }
  window.openRelationshipDrawer = openRelationshipDrawer;
  function openRecordDrawer(id) {
    api("/api/evidence/" + encodeURIComponent(id)).then(function (d) {
      if (d.detail) { toast(d.detail); return; }
      var rec = d.record, res = rec.resolved || {};
      // Identifiers show the registered holder beside the raw value, so an
      // officer reads "9822000004 · Javed Ansari", and a number with no
      // subscriber on file says so instead of standing bare.
      var fields = Object.keys(rec.fields || {}).map(function (k) {
        var v = rec.fields[k]; if (Array.isArray(v)) v = v.join(", ");
        var who = "";
        if (k in res) {
          who = res[k] === null
            ? ' <span style="color:var(--muted)">· no subscriber on file</span>'
            : ' <span class="chip-e" data-ent="' + esc(res[k]) + '" style="color:var(--accent2);cursor:pointer">· ' + esc(res[k]) + " ↗</span>";
        }
        return '<div class="dw-kv"><span>' + esc(k) + "</span><span style=\"color:var(--text2);text-align:right\">" + esc(v) + who + "</span></div>";
      }).join("");
      var html = dwSec("Source", '<div class="dw-kv"><span>Record</span>' + esc(rec.record_id) + "</div>" +
        '<div class="dw-kv"><span>File</span>' + esc(rec.source_file) + "</div>" +
        '<div class="dw-kv"><span>Type</span>' + esc(rec.source_type) + "</div>" +
        '<div class="dw-kv"><span>Timestamp</span>' + esc(rec.timeless ? "no event time (registry)" : (rec.timestamp || "—")) + "</div>");
      html += dwSec("Record contents", fields);
      html += dwSec("Description", '<div class="dw-txt">' + esc(d.source_type_description) + "</div>");
      if (d.supports && d.supports.length)
        html += dwSec("What this record supports", d.supports.map(function (s) {
          return '<div class="confrow"><span>' + (s.type === "edge" ? esc(s.subject) + " ↔ " + esc(s.object) + " (" + esc(s.rel) + ")" : esc(s.headline)) + "</span><b>" + esc(s.type) + "</b></div>";
        }).join(""));
      $("dwTitle").textContent = "Record " + id;
      $("dwBody").innerHTML = html; $("drawer").hidden = false; wireRecs();
      $("dwBody").querySelectorAll("[data-ent]").forEach(function (x) {
        x.onclick = function () { closeDrawer(); openEntity(x.dataset.ent); }; });
    }).catch(function () { toast("Record not found: " + id); });
  }

  /* ==================================================== report */
  window.closeReport = function () { $("report").hidden = true; };
  function buildReport() {
    var s = DATA.stats, clock = DATA.timeline.clock;
    var ctrl = (DATA.network_controllers || [])[0];
    var leads = (DATA.leads || []).filter(function (l) { return l.lead_score >= 25; });
    var when = new Date().toString().slice(0, 24);
    function rowLead(l) {
      var d = decisionOf("lead", l.entity);
      return '<div class="rp-lead"><div class="h"><span>' + esc(l.entity) + " — " + l.band +
        "</span><span>" + l.lead_score + "/100" + (d ? " · " + d.action.replace("_", " ") + " by " + esc(d.officer) : "") + "</span></div>" +
        "<p>" + l.factors.map(function (f) { return "+" + f.points + " " + esc(f.factor); }).join(" · ") + "</p>" +
        (l.uncertainty && l.uncertainty.length ? '<p style="color:#7a5a00">Uncertainty: ' + esc(l.uncertainty[0]) + "</p>" : "") + "</div>";
    }
    var evs = (DATA.timeline.events || []).filter(function (e) { return e.timestamp && (e.type === "FIR" || (e.type === "TRANSACTION" && e.amount_inr >= 100000) || e.type === "TRAVEL"); })
      .sort(function (a, b) { return a.timestamp < b.timestamp ? -1 : 1; });
    var html =
      '<h1><span class="rp-emblem">🛡</span>PRAHARI — Case Report</h1>' +
      '<div class="rp-meta">Case OP-SANGAM · Delhi–Mumbai Network · MHA / NCRB · SIH 2026</div>' +
      '<div class="rp-meta">Generated ' + esc(when) + " · by " + esc(OFFICER) + "</div>" +
      '<div class="rp-disc">This is a rule-based analytical brief assembled from the case records (no language model). Every finding is an investigative lead requiring human verification and carries no evidentiary weight. All data is synthetic.</div>' +
      "<h2>1. Case summary</h2><table><tr><th>Entities</th><td>" + s.people + "</td><th>Links</th><td>" + s.edges +
      "</td></tr><tr><th>Clusters</th><td>" + s.communities + "</td><th>FIRs parsed</th><td>" + s.firs_parsed +
      "</td></tr><tr><th>Anomaly findings</th><td>" + (s.anomalies || 0) + "</td><th>Records ingested</th><td>" + (s.records_ingested || "—") +
      "</td></tr><tr><th>Observation window</th><td colspan=3>anchored to latest record " + esc((clock.anchor || "").slice(0, 10)) + " (not today's date)</td></tr></table>";
    if (ctrl) html += "<h2>2. Potential network controller</h2><p><b>" + esc(ctrl.entity) + "</b> receives " + inr(ctrl.net_inflow_inr) +
      " in net consolidated transfers yet is named in " + ctrl.fir_mentions + " FIRs. " + esc(ctrl.basis) +
      '</p><p style="color:#7a5a00">' + esc((ctrl.uncertainty || [])[0] || "") + "</p>";
    html += "<h2>3. Investigative leads (" + leads.length + ")</h2>" + leads.map(rowLead).join("");
    html += "<h2>4. Key findings</h2><ul>" + (DATA.insight_records || []).slice(0, 6).map(function (i) {
      return "<li>" + esc(i.detail) + " <i>(" + (i.confidence || "?") + "% · " + (i.source_records || []).length + " records)</i></li>";
    }).join("") + "</ul>";
    html += "<h2>5. Timeline (milestones)</h2><table><tr><th>Date</th><th>Event</th><th>Detail</th></tr>" +
      evs.map(function (e) { return "<tr><td>" + esc(e.timestamp.slice(0, 10)) + "</td><td>" + esc(e.type.replace(/_/g, " ")) + "</td><td>" + esc(e.summary) + "</td></tr>"; }).join("") + "</table>";
    var decs = Object.values(DECISIONS);
    html += "<h2>6. Investigator decisions (" + decs.length + ")</h2>" + (decs.length ?
      "<table><tr><th>Target</th><th>Verdict</th><th>Officer</th><th>When</th></tr>" + decs.map(function (d) {
        return "<tr><td>" + esc(d.target) + "</td><td>" + esc(d.action.replace("_", " ")) + "</td><td>" + esc(d.officer) + "</td><td>" + esc(d.timestamp.replace("T", " ")) + "</td></tr>";
      }).join("") + "</table>" : "<p>No investigator verdicts recorded yet.</p>");
    html += '<div class="rp-disc">Rule-based analytical summary generated from cited records. Requires investigator verification. Lead scores are a triage aid, not a determination of guilt.</div>';
    $("reportBody").innerHTML = html;
    $("report").hidden = false;
  }

  /* ==================================================== ask PRAHARI */
  var askSeeded = false, askFocus = null;   // askFocus = last entity discussed
  window.closeAsk = function () { $("askPanel").hidden = true; };
  function askAppendUser(text) {
    var d = document.createElement("div"); d.className = "msg user"; d.textContent = text;
    $("askLog").appendChild(d); $("askLog").scrollTop = 1e9;
  }
  function askBubble(r) {
    var d = document.createElement("div"); d.className = "msg bot";
    var html = '<div class="b-title">' + esc(r.title || "PRAHARI") + "</div>" +
      '<div class="b-sum">' + esc(r.summary || "") + "</div>";
    if (r.bullets && r.bullets.length) {
      html += "<ul>" + r.bullets.map(function (b) {
        var t = esc(b.text);
        if (b.entity) t += ' <span class="chip-e" data-ent="' + esc(b.entity) + '">↗</span>';
        if (b.record) t += ' <span class="chip-r" data-rec="' + esc(b.record) + '">[' + esc(b.record) + "]</span>";
        return "<li>" + t + "</li>";
      }).join("") + "</ul>";
    }
    if (r.intent === "help" && r.examples) {
      html += '<div class="ask-ex">' + r.examples.map(function (x) {
        return '<span data-ex="' + esc(x) + '">' + esc(x) + "</span>"; }).join("") + "</div>";
    }
    html += '<div class="b-disc">' + esc(r.grounded || "") + " " + esc(r.disclaimer || "") + "</div>";
    d.innerHTML = html;
    d.querySelectorAll("[data-ent]").forEach(function (x) {
      x.onclick = function () { closeAsk(); showView("network"); openEntity(x.dataset.ent); }; });
    d.querySelectorAll("[data-rec]").forEach(function (x) {
      x.onclick = function () { openRecordDrawer(x.dataset.rec); }; });
    d.querySelectorAll("[data-ex]").forEach(function (x) {
      x.onclick = function () { askSend(x.dataset.ex); }; });
    $("askLog").appendChild(d); $("askLog").scrollTop = 1e9;
  }
  function askSend(q) {
    q = (q || $("askInput").value).trim(); if (!q) return;
    $("askInput").value = "";
    askAppendUser(q);
    var wait = document.createElement("div"); wait.className = "msg bot"; wait.textContent = "…";
    $("askLog").appendChild(wait); $("askLog").scrollTop = 1e9;
    var url = "/api/ask?q=" + encodeURIComponent(q) +
      (askFocus ? "&context=" + encodeURIComponent(askFocus) : "");
    api(url).then(function (r) {
      wait.remove(); askBubble(r);
      if (r.focus) askFocus = r.focus;      // remember for follow-ups
    }).catch(function () { wait.remove(); toast("Ask failed"); });
  }
  function openAsk() {
    $("askPanel").hidden = false;
    if (!askSeeded) {
      askSeeded = true;
      askBubble({ title: "Ask PRAHARI", intent: "help",
        summary: "I answer from this case's own records — no outside AI, nothing invented. Try:",
        examples: ["Summary of Ramesh Yadav", "What happened on 2026-03-18",
          "Who is the network controller", "Who received the most money",
          "Who owns DL01AB4455", "Case summary"],
        grounded: "", disclaimer: "" });
    }
    setTimeout(function () { $("askInput").focus(); }, 60);
  }
  function wireAsk() {
    $("askFab").onclick = openAsk;
    $("askSend").onclick = function () { askSend(); };
    $("askInput").addEventListener("keydown", function (e) { if (e.key === "Enter") askSend(); });
  }

  /* ==================================================== go */
  function start() {
    wireNav(); wireMisc(); wireSearch(); wireAddData(); wireAsk();
    boot();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();

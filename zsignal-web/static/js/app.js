function $(sel) { return document.querySelector(sel); }

function setupTabs() {
  document.querySelectorAll("#tabs li").forEach(function (li) {
    li.addEventListener("click", function () {
      document.querySelectorAll("#tabs li").forEach(function (x) { x.classList.remove("is-active"); });
      li.classList.add("is-active");
      document.querySelectorAll(".tab-panel").forEach(function (p) { p.classList.remove("is-active"); });
      document.getElementById("panel-" + li.dataset.tab).classList.add("is-active");
    });
  });
}

function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString();
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderSentLog(entries) {
  var box = $("#sent-log");
  box.textContent = entries.map(function (e) {
    return "[" + fmtTime(e.ts) + "] (" + e.duration.toFixed(2) + "s) " + e.text;
  }).join("\n");
  box.scrollTop = box.scrollHeight;
}

// Classic mainframe/ISPF-style 3-line hex dump: text row, then high-nibble
// row, then low-nibble row, one column per byte (e.g. "DAN" / "444" / "41E").
// Each column is colored per-byte: green if that byte decoded cleanly, red
// if decoder.py flagged a bit/inverse mismatch on it.
function hexNibbleRows(hexStr) {
  var hi = "", lo = "";
  for (var i = 0; i < hexStr.length; i += 2) {
    hi += hexStr[i].toUpperCase();
    lo += hexStr[i + 1].toUpperCase();
  }
  return [hi, lo];
}

function textRow(hexStr) {
  var out = "";
  for (var i = 0; i < hexStr.length; i += 2) {
    var b = parseInt(hexStr.substr(i, 2), 16);
    out += (b >= 32 && b <= 126) ? String.fromCharCode(b) : ".";
  }
  return out;
}

function corruptedByteSet(corrupted) {
  var s = {};
  (corrupted || []).forEach(function (pair) { s[pair[0]] = true; });
  return s;
}

function coloredRowHtml(rowStr, badSet) {
  var out = "";
  for (var i = 0; i < rowStr.length; i++) {
    var cls = badSet[i] ? "tone-bad" : "tone-ok";
    out += '<span class="' + cls + '">' + escapeHtml(rowStr[i]) + "</span>";
  }
  return out;
}

function renderListenLog(entries) {
  var box = $("#listen-log");
  var html = "";
  entries.forEach(function (e) {
    html += "[" + fmtTime(e.ts) + "]\n";
    if (e.ok) {
      var hex = e.result.hex;
      var badSet = corruptedByteSet(e.result.corrupted);
      var rows = hexNibbleRows(hex);
      html += coloredRowHtml(textRow(hex), badSet) + "\n";
      html += coloredRowHtml(rows[0], badSet) + "\n";
      html += coloredRowHtml(rows[1], badSet) + "\n";
      if (e.result.corrupted && e.result.corrupted.length) {
        html += "  (corrupted bits: " + escapeHtml(JSON.stringify(e.result.corrupted)) + ")\n";
      }
      if (!e.result.found_end) {
        html += "  (no end-of-frame marker found -- possibly truncated)\n";
      }
    } else {
      html += "  DECODE FAILED: " + escapeHtml(e.error) + "\n";
    }
    html += "\n";
  });
  box.innerHTML = html;
  box.scrollTop = box.scrollHeight;
}

function loadSettingsIntoForm(s) {
  $("#set-device").value = s.device || "";
  $("#set-ptt-serial").value = s.ptt_serial || "";
  $("#set-ptt-pin").value = (s.ptt_pin === null || s.ptt_pin === undefined) ? "" : s.ptt_pin;
  $("#set-ptt-delay").value = (s.ptt_delay === null || s.ptt_delay === undefined) ? 0.5 : s.ptt_delay;
  $("#set-ptt-tail-delay").value = (s.ptt_tail_delay === null || s.ptt_tail_delay === undefined) ? 0.5 : s.ptt_tail_delay;
  $("#sc-sender").value = s.station_sender || "";
  $("#sc-receiver").value = s.station_receiver || "";
  $("#vb-station").value = s.volleyball_station || "";
}

function refreshSentLog() {
  fetch("/api/sent-log").then(function (r) { return r.json(); }).then(renderSentLog);
}

function postJson(url, body) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  }).then(function (r) { return r.json(); });
}

// ---- Shared listening state --------------------------------------------
// There is exactly one physical receiver, so "listening" is one boolean
// shared by the Listen tab, Station COMS, and Volleyball -- whichever
// button is clicked updates all three so they never show conflicting state.

var isListening = false;

function setListeningUI(listening) {
  isListening = listening;
  [$("#listen-btn"), $("#sc-listen-btn"), $("#vb-listen-btn")].forEach(function (btn) {
    if (!btn) return;
    btn.dataset.listening = listening ? "true" : "false";
    btn.textContent = listening ? "Stop" : "Listen";
    btn.classList.toggle("is-danger", listening);
    btn.classList.toggle("is-primary", !listening);
  });
}

function toggleListen() {
  if (isListening) {
    return fetch("/api/listen/stop", { method: "POST" }).then(function (r) { return r.json(); })
      .then(function () { setListeningUI(false); });
  }
  return fetch("/api/listen/start", { method: "POST" }).then(function (r) { return r.json(); })
    .then(function (result) {
      if (result.error) { alert(result.error); return; }
      setListeningUI(true);
    });
}

// Stop listening (ignored if already stopped), send `text`, and optionally
// restart listening afterward. Shared by Station COMS's Transmit and
// Volleyball's Start/auto-reply -- both need "stop, send, resume" so the
// transmitter and receiver never fight over the same audio device.
function txCycle(text, restart) {
  return fetch("/api/listen/stop", { method: "POST" })
    .then(function () { return postJson("/api/send", { text: text }); })
    .then(function (result) {
      if (restart) {
        return fetch("/api/listen/start", { method: "POST" }).then(function () {
          setListeningUI(true);
          return result;
        });
      }
      setListeningUI(false);
      return result;
    });
}

// ---- Station COMS --------------------------------------------------------
// Wire format: "SENDER>RECEIVER:MESSAGE" (one zsignal text payload carrying
// all three UI fields; RECEIVER may be "CQ" for all-stations).

function parseStationMessage(text) {
  var gt = text.indexOf(">");
  if (gt < 0) return null;
  var sender = text.slice(0, gt);
  var rest = text.slice(gt + 1);
  var colon = rest.indexOf(":");
  if (colon < 0) return null;
  var receiver = rest.slice(0, colon);
  var message = rest.slice(colon + 1);
  if (!sender || !receiver) return null;
  return { sender: sender, receiver: receiver, message: message };
}

function addLogRow(tbody, ts, sender, receiver, message) {
  var tr = document.createElement("tr");
  [fmtTime(ts), sender || "", receiver || "", message].forEach(function (text) {
    var td = document.createElement("td");
    td.textContent = text;
    tr.appendChild(td);
  });
  tbody.appendChild(tr);
  var wrap = tbody.closest(".log-table-wrap");
  if (wrap) wrap.scrollTop = wrap.scrollHeight;
}

function cleanDecode(e) {
  return e.ok && e.result.found_end && !(e.result.corrupted && e.result.corrupted.length);
}

function handleStationComsEntry(e) {
  if (!cleanDecode(e)) return;
  var text = e.result.text;
  var parsed = parseStationMessage(text);
  addLogRow($("#sc-log-body"), e.ts,
    parsed ? parsed.sender : "", parsed ? parsed.receiver : "", parsed ? parsed.message : text);
}

function saveStationComsFields() {
  postJson("/api/settings", {
    station_sender: $("#sc-sender").value,
    station_receiver: $("#sc-receiver").value
  });
}

// ---- Volleyball -----------------------------------------------------------
// "{station}: serves." / "{station}: Good Game." / "{A}:{B}: bump. set. spike."
// The bump/set/spike reply is a verbatim echo of whatever was received --
// the two station names inside it never change after the first reply, which
// is what makes it bounce back and forth unchanged, like a volleyball
// rally, until someone clicks Stop.

var SERVE_RE = /^(\S+): serves\.$/;
var BUMP_RE = /^(\S+):(\S+): bump\. set\. spike\.$/;

var vbPendingTimer = null;

function volleyballRowFields(text) {
  var m;
  if ((m = text.match(SERVE_RE))) return { sender: m[1], receiver: "" };
  if ((m = text.match(BUMP_RE))) return { sender: m[1], receiver: m[2] };
  return { sender: "", receiver: "" };
}

function handleVolleyballEntry(e) {
  if (!cleanDecode(e)) return;
  var text = e.result.text;
  var fields = volleyballRowFields(text);
  addLogRow($("#vb-log-body"), e.ts, fields.sender, fields.receiver, text);

  if (vbPendingTimer) return; // a reply is already scheduled -- don't stack another
  var station = ($("#vb-station").value || "").toUpperCase();
  var m;
  if ((m = text.match(SERVE_RE)) && m[1] !== station) {
    var served = m[1];
    vbPendingTimer = setTimeout(function () {
      vbPendingTimer = null;
      txCycle(station + ":" + served + ": bump. set. spike.", true);
    }, 2000);
  } else if (BUMP_RE.test(text)) {
    vbPendingTimer = setTimeout(function () {
      vbPendingTimer = null;
      txCycle(text, true); // echo back unchanged
    }, 2000);
  }
}

function saveVolleyballField() {
  postJson("/api/settings", { volleyball_station: $("#vb-station").value });
}

// ---- Shared decode-log poll ------------------------------------------------
// One poller feeds the raw hex dump (Listen tab), Station COMS's table, and
// Volleyball's table/auto-reply -- all three read the same decoded stream,
// and this keeps running regardless of which tab is currently visible so a
// Volleyball rally or a Station COMS listen session survives a tab switch.

var scLastIndex = 0;
var vbLastIndex = 0;

function pollListenLog() {
  fetch("/api/listen/log").then(function (r) { return r.json(); }).then(function (entries) {
    renderListenLog(entries);
    for (; scLastIndex < entries.length; scLastIndex++) {
      handleStationComsEntry(entries[scLastIndex]);
    }
    for (; vbLastIndex < entries.length; vbLastIndex++) {
      handleVolleyballEntry(entries[vbLastIndex]);
    }
  });
}

function forceUppercase(el) {
  el.addEventListener("input", function () {
    var pos = el.selectionStart;
    el.value = el.value.toUpperCase();
    el.selectionStart = el.selectionEnd = pos;
  });
}

document.addEventListener("DOMContentLoaded", function () {
  setupTabs();
  refreshSentLog();
  setInterval(pollListenLog, 1000);

  fetch("/api/settings").then(function (r) { return r.json(); }).then(loadSettingsIntoForm);
  fetch("/api/listen/status").then(function (r) { return r.json(); }).then(function (s) {
    setListeningUI(!!s.listening);
  });

  ["sc-sender", "sc-receiver", "vb-station"].forEach(function (id) {
    forceUppercase(document.getElementById(id));
  });

  $("#send-btn").addEventListener("click", function () {
    var text = $("#send-text").value;
    if (!text) return;
    var btn = $("#send-btn");
    btn.classList.add("is-loading");
    postJson("/api/send", { text: text }).then(function (result) {
      btn.classList.remove("is-loading");
      if (result.error) { alert("Send failed: " + result.error); }
      refreshSentLog();
    }).catch(function (err) {
      btn.classList.remove("is-loading");
      alert("Send failed: " + err);
    });
  });

  $("#listen-btn").addEventListener("click", toggleListen);
  $("#sc-listen-btn").addEventListener("click", toggleListen);
  $("#vb-listen-btn").addEventListener("click", toggleListen);

  $("#sc-clear-btn").addEventListener("click", function () { $("#sc-log-body").innerHTML = ""; });
  $("#vb-clear-btn").addEventListener("click", function () { $("#vb-log-body").innerHTML = ""; });

  $("#sc-transmit-btn").addEventListener("click", function () {
    var sender = ($("#sc-sender").value || "").toUpperCase();
    var receiver = ($("#sc-receiver").value || "").toUpperCase();
    var message = $("#sc-message").value || "";
    if (!sender || !receiver || !message) {
      alert("Sender, Receiver, and Message are all required.");
      return;
    }
    saveStationComsFields();
    var btn = $("#sc-transmit-btn");
    btn.classList.add("is-loading");
    txCycle(sender + ">" + receiver + ":" + message, true).then(function (result) {
      btn.classList.remove("is-loading");
      if (result && result.error) alert("Transmit failed: " + result.error);
    }).catch(function (err) {
      btn.classList.remove("is-loading");
      alert("Transmit failed: " + err);
    });
  });

  $("#vb-start-btn").addEventListener("click", function () {
    var station = ($("#vb-station").value || "").toUpperCase();
    if (!station) { alert("Station is required."); return; }
    saveVolleyballField();
    txCycle(station + ": serves.", true).catch(function (err) { alert("Start failed: " + err); });
  });

  $("#vb-stop-btn").addEventListener("click", function () {
    var station = ($("#vb-station").value || "").toUpperCase();
    if (!station) { alert("Station is required."); return; }
    if (vbPendingTimer) { clearTimeout(vbPendingTimer); vbPendingTimer = null; }
    txCycle(station + ": Good Game.", false).catch(function (err) { alert("Stop failed: " + err); });
  });

  $("#save-settings-btn").addEventListener("click", function () {
    var body = {
      device: $("#set-device").value || null,
      ptt_serial: $("#set-ptt-serial").value || null,
      ptt_pin: $("#set-ptt-pin").value ? parseInt($("#set-ptt-pin").value, 10) : null,
      ptt_delay: parseFloat($("#set-ptt-delay").value) || 0.5,
      ptt_tail_delay: parseFloat($("#set-ptt-tail-delay").value) || 0.5
    };
    postJson("/api/settings", body).then(function (s) {
      loadSettingsIntoForm(s);
      var msg = $("#settings-saved");
      msg.style.display = "block";
      setTimeout(function () { msg.style.display = "none"; }, 1500);
    });
  });
});

function $(sel) { return document.querySelector(sel); }
function $all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }

// ---- Navigation -------------------------------------------------------------

function showScreen(name) {
  $all(".nav-btn[data-screen]").forEach(function (b) {
    b.classList.toggle("is-active", b.dataset.screen === name);
  });
  $all(".screen").forEach(function (s) {
    s.classList.toggle("is-active", s.id === "screen-" + name);
  });
}

function setupNav() {
  $all(".nav-btn[data-screen]").forEach(function (b) {
    b.addEventListener("click", function () { showScreen(b.dataset.screen); });
  });
}

// ---- Helpers ----------------------------------------------------------------

function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour12: false });
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function getJson(url) {
  return fetch(url).then(function (r) { return r.json(); });
}

function postJson(url, body) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  }).then(function (r) { return r.json(); });
}

function mySender() {
  return ($("#sc-sender").value || "").trim().toUpperCase();
}

// ---- Station message wire format -------------------------------------------
// "SENDER>RECEIVER:MESSAGE" (one zsignal text payload carrying all three
// fields; RECEIVER may be "CQ" for all stations).

function parseStationMessage(text) {
  var gt = text.indexOf(">");
  if (gt < 0) return null;
  var sender = text.slice(0, gt);
  var rest = text.slice(gt + 1);
  var colon = rest.indexOf(":");
  if (colon < 0) return null;
  var receiver = rest.slice(0, colon);
  if (!sender || !receiver) return null;
  return { sender: sender, receiver: receiver, message: rest.slice(colon + 1) };
}

function cleanDecode(e) {
  return e.ok && e.result.found_end && !(e.result.corrupted && e.result.corrupted.length);
}

// ---- Listening state ----------------------------------------------------------
// One physical receiver, so one shared boolean; every RX toggle reflects it.

var isListening = false;

function setListeningUI(listening) {
  isListening = listening;
  $all(".listen-toggle").forEach(function (btn) {
    btn.textContent = listening ? "RX OFF" : "RX ON";
    btn.classList.toggle("is-on", listening);
  });
  var st = $("#status-rx");
  st.textContent = listening ? "RX" : "RX OFF";
  st.classList.toggle("on", listening);
}

function startListening() {
  return postJson("/api/listen/start").then(function (r) {
    if (r.error && r.error !== "already listening") throw new Error(r.error);
    setListeningUI(true);
  });
}

function stopListening() {
  return postJson("/api/listen/stop").then(function () { setListeningUI(false); });
}

function toggleListen() {
  (isListening ? stopListening() : startListening()).catch(function (err) {
    alert("Listen failed: " + err.message);
  });
}

// ---- Transmit queue -----------------------------------------------------------
// Every transmission (Transmit button, Echo Mode replies) goes through one
// queue so two sends never overlap. Each one stops the receiver, sends, and
// restarts the receiver if it was on (or if `keepListening` is set), so the
// transmitter and receiver never fight over the sound card.

var txChain = Promise.resolve();

function setTxUI(on) { $("#status-tx").hidden = !on; }

function queueTx(text, keepListening) {
  var job = txChain.then(function () {
    var resume = isListening || keepListening;
    setTxUI(true);
    return postJson("/api/listen/stop")
      .then(function () { return postJson("/api/send", { text: text }); })
      .then(function (result) {
        var after = resume ? startListening() : (setListeningUI(false), Promise.resolve());
        return after.then(function () { return result; });
      })
      .finally(function () { setTxUI(false); pollLogs(); });
  });
  txChain = job.catch(function () {}); // keep the queue alive after a failure
  return job;
}

// ---- Echo Mode --------------------------------------------------------------
// While on, each clean received message addressed to SENDER (or CQ) is sent
// back to whoever sent it as "ME>THEM:ECHO: <message>" after a short pause.
// Never echoes our own messages or anything already starting "ECHO: ", so two
// stations both in Echo Mode can't bounce messages back and forth forever.

var ECHO_PREFIX = "ECHO: ";
var ECHO_DELAY_MS = 2000;   // give the other station time to drop PTT
var echoOn = false;
var echoTimers = [];

function setEchoUI(on) {
  echoOn = on;
  var b = $("#echo-btn");
  b.setAttribute("aria-pressed", on ? "true" : "false");  // amber when on
}

function toggleEcho() {
  if (echoOn) {
    echoTimers.forEach(clearTimeout);
    echoTimers = [];
    setEchoUI(false);
    return;
  }
  if (!mySender()) {
    alert("Set SENDER (your callsign) before turning on Echo Mode.");
    showScreen("station");
    $("#sc-sender").focus();
    return;
  }
  saveStationFields();
  setEchoUI(true);
  if (!isListening) {
    startListening().catch(function (err) {
      setEchoUI(false);
      alert("Echo Mode needs the receiver: " + err.message);
    });
  }
}

function echoReplyFor(e) {
  if (!cleanDecode(e)) return null;
  var me = mySender();
  var text = e.result.text;
  var p = parseStationMessage(text);
  if (!p) {
    // A raw (non-station-format) payload: echo it as-is with the prefix.
    return text.indexOf(ECHO_PREFIX) === 0 ? null : ECHO_PREFIX + text;
  }
  var from = p.sender.toUpperCase(), to = p.receiver.toUpperCase();
  if (from === me) return null;
  if (to !== me && to !== "CQ") return null;
  if (p.message.indexOf(ECHO_PREFIX) === 0) return null;
  return me + ">" + p.sender + ":" + ECHO_PREFIX + p.message;
}

function handleEcho(e) {
  if (!echoOn) return;
  var reply = echoReplyFor(e);
  if (!reply) return;
  var t = setTimeout(function () {
    echoTimers = echoTimers.filter(function (x) { return x !== t; });
    if (!echoOn) return;
    queueTx(reply, true).then(function (r) {
      if (r && r.error) console.warn("echo failed:", r.error);
    });
  }, ECHO_DELAY_MS);
  echoTimers.push(t);
}

// ---- Station log ------------------------------------------------------------
// One merged log: sent (orange) and clean received (green) messages, newest
// on top. Built from the server's sent and received logs, so it survives a
// page reload. CLEAR hides everything up to now (in this browser only).

var CLEAR_KEY = "zsignal.logClearedAt";
var clearedAt = 0;
try { clearedAt = parseFloat(localStorage.getItem(CLEAR_KEY)) || 0; } catch (e) { /* storage blocked */ }

function logLineHtml(item) {
  var body, tag = item.kind.toUpperCase(), cls = item.kind;
  if (item.damaged) {
    // Show the payload byte-for-byte with flagged bytes in red -- splitting
    // out SENDER>RECEIVER could be wrong when those bytes are the bad ones.
    var e = item.entry, badSet = corruptedByteSet(e.result.corrupted);
    var row = textRow(e.result.hex), out = "";
    for (var i = 0; i < row.length; i++) {
      out += badSet[i] ? '<span class="bad">' + escapeHtml(row[i]) + "</span>" : escapeHtml(row[i]);
    }
    var notes = [];
    var n = Object.keys(badSet).length;
    if (n) notes.push(n + " BAD BYTE" + (n === 1 ? "" : "S"));
    if (!e.result.found_end) notes.push("TRUNCATED?");
    body = out + ' <span class="note">[' + notes.join(", ") + "]</span>";
    tag = "RX?";
    cls += " damaged";
  } else {
    var p = parseStationMessage(item.text);
    body = p
      ? '<span class="tag">' + escapeHtml(p.sender + ">" + p.receiver) + "</span> " + escapeHtml(p.message)
      : escapeHtml(item.text);
  }
  return '<div class="log-line ' + cls + '"><span class="ts">' + fmtTime(item.ts) + "</span> " +
         '<span class="tag">' + tag + "</span> " + body + "</div>";
}

var lastStationKey = "";

function renderStationLog(sent, received) {
  var items = [];
  sent.forEach(function (e) { items.push({ kind: "tx", ts: e.ts, text: e.text }); });
  received.forEach(function (e) {
    // Damaged decodes are shown (marked RX?); outright failures are just noise.
    if (e.ok) items.push({ kind: "rx", ts: e.ts, text: e.result.text, entry: e, damaged: !cleanDecode(e) });
  });
  items = items.filter(function (i) { return i.ts > clearedAt; });
  items.sort(function (a, b) { return b.ts - a.ts; });

  var key = items.length + ":" + (items.length ? items[0].ts : 0) + ":" + clearedAt;
  if (key === lastStationKey) return;   // unchanged -- don't disturb scroll position
  lastStationKey = key;

  var box = $("#sc-log");
  box.innerHTML = items.length
    ? items.map(logLineHtml).join("")
    : '<div class="log-empty">-- NO TRAFFIC --</div>';
}

// ---- Send screen log --------------------------------------------------------

var lastSentCount = -1;

function renderSentLog(entries) {
  if (entries.length === lastSentCount) return;
  lastSentCount = entries.length;
  $("#sent-log").textContent = entries.slice().reverse().map(function (e) {
    return fmtTime(e.ts) + " (" + e.duration.toFixed(2) + "s) " + e.text;
  }).join("\n") || "-- NOTHING SENT --";
}

// ---- Listen screen hex dump -------------------------------------------------
// Mainframe-style 3-line dump per message: text row, high-nibble row,
// low-nibble row, one column per byte; green if the byte decoded cleanly,
// red if decoder.py flagged a mismatch on it. Newest on top.

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
    out += '<span class="' + (badSet[i] ? "tone-bad" : "tone-ok") + '">' + escapeHtml(rowStr[i]) + "</span>";
  }
  return out;
}

var lastListenCount = -1;

function renderListenLog(entries) {
  if (entries.length === lastListenCount) return;
  lastListenCount = entries.length;
  var html = "";
  entries.slice().reverse().forEach(function (e) {
    html += '<span class="ts">' + fmtTime(e.ts) + "</span>\n";
    if (e.ok) {
      var hex = e.result.hex;
      var badSet = corruptedByteSet(e.result.corrupted);
      var rows = hexNibbleRows(hex);
      html += coloredRowHtml(textRow(hex), badSet) + "\n";
      html += coloredRowHtml(rows[0], badSet) + "\n";
      html += coloredRowHtml(rows[1], badSet) + "\n";
      if (e.result.corrupted && e.result.corrupted.length) {
        html += '<span class="tone-bad">  (corrupted bits: ' + escapeHtml(JSON.stringify(e.result.corrupted)) + ")</span>\n";
      }
      if (!e.result.found_end) {
        html += '<span class="tone-bad">  (no end-of-frame marker -- possibly truncated)</span>\n';
      }
    } else {
      html += '<span class="tone-bad">  DECODE FAILED: ' + escapeHtml(e.error) + "</span>\n";
    }
    html += "\n";
  });
  $("#listen-log").innerHTML = html || '<span class="log-empty">-- NO SIGNALS --</span>';
}

// ---- Shared poll ------------------------------------------------------------
// One poll feeds every view and Echo Mode, whichever screen is showing.

var rxSeen = null;   // index into the received log already handled by Echo Mode
var polling = false;

function pollLogs() {
  if (polling) return;
  polling = true;
  Promise.all([getJson("/api/sent-log"), getJson("/api/listen/log")]).then(function (res) {
    var sent = res[0], received = res[1];
    // Only react to messages that arrive after the page loaded.
    if (rxSeen === null) rxSeen = received.length;
    for (; rxSeen < received.length; rxSeen++) handleEcho(received[rxSeen]);
    renderStationLog(sent, received);
    renderSentLog(sent);
    renderListenLog(received);
  }).catch(function () { /* server restarting -- try again next tick */ })
    .finally(function () { polling = false; });
}

// ---- Settings ---------------------------------------------------------------

function loadSettingsIntoForm(s) {
  var num = function (v, d) { return (v === null || v === undefined) ? d : v; };
  $("#set-device").value = s.device || "";
  $("#set-ptt-serial").value = s.ptt_serial || "";
  $("#set-ptt-pin").value = num(s.ptt_pin, "");
  $("#set-ptt-delay").value = num(s.ptt_delay, 0.5);
  $("#set-ptt-tail-delay").value = num(s.ptt_tail_delay, 0.5);
  if (document.activeElement !== $("#sc-sender")) $("#sc-sender").value = s.station_sender || "";
  if (document.activeElement !== $("#sc-receiver")) $("#sc-receiver").value = s.station_receiver || "";
}

function saveStationFields() {
  return postJson("/api/settings", {
    station_sender: $("#sc-sender").value.toUpperCase(),
    station_receiver: $("#sc-receiver").value.toUpperCase()
  });
}

function forceUppercase(el) {
  el.addEventListener("input", function () {
    var pos = el.selectionStart;
    el.value = el.value.toUpperCase();
    el.selectionStart = el.selectionEnd = pos;
  });
}

function busy(btn, on) {
  btn.classList.toggle("is-busy", on);
  btn.disabled = on;
}

// ---- Wire up ----------------------------------------------------------------

document.addEventListener("DOMContentLoaded", function () {
  setupNav();
  getJson("/api/settings").then(loadSettingsIntoForm);
  getJson("/api/listen/status").then(function (s) { setListeningUI(!!s.listening); });
  pollLogs();
  setInterval(pollLogs, 1000);

  ["sc-sender", "sc-receiver"].forEach(function (id) {
    var el = document.getElementById(id);
    forceUppercase(el);
    el.addEventListener("change", saveStationFields);
  });

  $all(".listen-toggle").forEach(function (b) { b.addEventListener("click", toggleListen); });
  $("#echo-btn").addEventListener("click", toggleEcho);

  $("#sc-clear-btn").addEventListener("click", function () {
    clearedAt = Date.now() / 1000;
    try { localStorage.setItem(CLEAR_KEY, String(clearedAt)); } catch (e) { /* storage blocked */ }
    pollLogs();
  });

  $("#sc-transmit-btn").addEventListener("click", function () {
    var sender = mySender();
    var receiver = ($("#sc-receiver").value || "").trim().toUpperCase();
    var message = $("#sc-message").value || "";
    if (!sender || !receiver || !message.trim()) {
      alert("SENDER, RECEIVER and MESSAGE are all required.");
      return;
    }
    saveStationFields();
    var btn = $("#sc-transmit-btn");
    busy(btn, true);
    queueTx(sender + ">" + receiver + ":" + message, true).then(function (r) {
      if (r && r.error) alert("Transmit failed: " + r.error);
      else $("#sc-message").value = "";
    }).catch(function (err) {
      alert("Transmit failed: " + err.message);
    }).finally(function () { busy(btn, false); });
  });

  $("#send-btn").addEventListener("click", function () {
    var text = $("#send-text").value;
    if (!text) return;
    var btn = $("#send-btn");
    busy(btn, true);
    queueTx(text, false).then(function (r) {
      if (r && r.error) alert("Send failed: " + r.error);
    }).catch(function (err) {
      alert("Send failed: " + err.message);
    }).finally(function () { busy(btn, false); });
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
      msg.hidden = false;
      setTimeout(function () { msg.hidden = true; }, 1500);
    });
  });
});

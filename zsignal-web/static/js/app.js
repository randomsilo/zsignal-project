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

function renderSentLog(entries) {
  var box = $("#sent-log");
  box.textContent = entries.map(function (e) {
    return "[" + fmtTime(e.ts) + "] (" + e.duration.toFixed(2) + "s) " + e.text;
  }).join("\n");
  box.scrollTop = box.scrollHeight;
}

// Classic mainframe/ISPF-style 3-line hex dump: text row, then high-nibble
// row, then low-nibble row, one column per byte (e.g. "DAN" / "444" / "41E").
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

function renderListenLog(entries) {
  var box = $("#listen-log");
  var lines = [];
  entries.forEach(function (e) {
    lines.push("[" + fmtTime(e.ts) + "]");
    if (e.ok) {
      var hex = e.result.hex;
      var rows = hexNibbleRows(hex);
      lines.push(textRow(hex));
      lines.push(rows[0]);
      lines.push(rows[1]);
      if (e.result.corrupted && e.result.corrupted.length) {
        lines.push("  (corrupted bits: " + JSON.stringify(e.result.corrupted) + ")");
      }
      if (!e.result.found_end) {
        lines.push("  (no end-of-frame marker found -- possibly truncated)");
      }
    } else {
      lines.push("  DECODE FAILED: " + e.error);
    }
    lines.push("");
  });
  box.textContent = lines.join("\n");
  box.scrollTop = box.scrollHeight;
}

function loadSettingsIntoForm(s) {
  $("#set-device").value = s.device || "";
  $("#set-ptt-serial").value = s.ptt_serial || "";
  $("#set-ptt-pin").value = (s.ptt_pin === null || s.ptt_pin === undefined) ? "" : s.ptt_pin;
  $("#set-ptt-delay").value = (s.ptt_delay === null || s.ptt_delay === undefined) ? 0.5 : s.ptt_delay;
  $("#set-ptt-tail-delay").value = (s.ptt_tail_delay === null || s.ptt_tail_delay === undefined) ? 0.5 : s.ptt_tail_delay;
}

function refreshSentLog() {
  fetch("/api/sent-log").then(function (r) { return r.json(); }).then(renderSentLog);
}

var listenPoll = null;

function startListenPolling() {
  if (listenPoll) return;
  listenPoll = setInterval(function () {
    fetch("/api/listen/log").then(function (r) { return r.json(); }).then(renderListenLog);
  }, 1000);
}

function stopListenPolling() {
  if (listenPoll) { clearInterval(listenPoll); listenPoll = null; }
}

document.addEventListener("DOMContentLoaded", function () {
  setupTabs();
  refreshSentLog();

  fetch("/api/settings").then(function (r) { return r.json(); }).then(loadSettingsIntoForm);

  $("#send-btn").addEventListener("click", function () {
    var text = $("#send-text").value;
    if (!text) return;
    var btn = $("#send-btn");
    btn.classList.add("is-loading");
    fetch("/api/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text })
    }).then(function (r) { return r.json(); }).then(function (result) {
      btn.classList.remove("is-loading");
      if (result.error) { alert("Send failed: " + result.error); }
      refreshSentLog();
    }).catch(function (err) {
      btn.classList.remove("is-loading");
      alert("Send failed: " + err);
    });
  });

  $("#listen-btn").addEventListener("click", function () {
    var btn = $("#listen-btn");
    var listening = btn.dataset.listening === "true";
    var url = listening ? "/api/listen/stop" : "/api/listen/start";
    fetch(url, { method: "POST" }).then(function (r) { return r.json(); }).then(function (result) {
      if (result.error) { alert(result.error); return; }
      btn.dataset.listening = listening ? "false" : "true";
      btn.textContent = listening ? "Listen" : "Stop";
      btn.classList.toggle("is-danger", !listening);
      btn.classList.toggle("is-primary", listening);
      if (listening) { stopListenPolling(); } else { startListenPolling(); }
    });
  });

  $("#save-settings-btn").addEventListener("click", function () {
    var body = {
      device: $("#set-device").value || null,
      ptt_serial: $("#set-ptt-serial").value || null,
      ptt_pin: $("#set-ptt-pin").value ? parseInt($("#set-ptt-pin").value, 10) : null,
      ptt_delay: parseFloat($("#set-ptt-delay").value) || 0.5,
      ptt_tail_delay: parseFloat($("#set-ptt-tail-delay").value) || 0.5
    };
    fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (s) {
      loadSettingsIntoForm(s);
      var msg = $("#settings-saved");
      msg.style.display = "block";
      setTimeout(function () { msg.style.display = "none"; }, 1500);
    });
  });
});

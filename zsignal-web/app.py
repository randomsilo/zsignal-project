"""zsignal-web: a small Flask UI over the zsignal CLI (send / listen / settings)."""

import os
import queue
import sys
import time

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from zsignal import cli as zcli  # send_text()
from zsignal import live_listen, protocol

import settings_store

app = Flask(__name__)

settings = settings_store.load()
sent_log = []
listen_log = []
listener = None


def _ptt_kwargs():
    return dict(
        device=settings.get("device") or None,
        ptt_pin=settings.get("ptt_pin"),
        ptt_serial=settings.get("ptt_serial") or None,
        ptt_delay=settings.get("ptt_delay", 0.5),
        ptt_tail_delay=settings.get("ptt_tail_delay", 0.5),
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    global settings
    if request.method == "POST":
        settings.update(request.get_json(force=True) or {})
        settings_store.save(settings)
    return jsonify(settings)


@app.route("/api/send", methods=["POST"])
def api_send():
    text = (request.get_json(force=True) or {}).get("text", "")
    if not text:
        return jsonify({"error": "empty message"}), 400
    try:
        payload, duration = zcli.send_text(text, **_ptt_kwargs())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    entry = {"ts": time.time(), "text": text,
              "hex": protocol.bytes_to_hex(payload), "duration": duration}
    sent_log.append(entry)
    return jsonify(entry)


@app.route("/api/sent-log")
def api_sent_log():
    return jsonify(sent_log)


@app.route("/api/listen/start", methods=["POST"])
def api_listen_start():
    global listener
    if listener is not None:
        return jsonify({"error": "already listening"}), 400
    try:
        listener = live_listen.LiveListener(device=settings.get("device") or None)
        listener.start()
    except Exception as e:
        listener = None
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "listening"})


@app.route("/api/listen/stop", methods=["POST"])
def api_listen_stop():
    global listener
    if listener is not None:
        listener.stop()
        listener = None
    return jsonify({"status": "stopped"})


@app.route("/api/listen/log")
def api_listen_log():
    if listener is not None:
        while True:
            try:
                listen_log.append(listener.events.get_nowait())
            except queue.Empty:
                break
    return jsonify(listen_log)


if __name__ == "__main__":
    # Local-only by default. ZSIGNAL_WEB_HOST=0.0.0.0 exposes it on the LAN; the
    # Werkzeug debugger allows remote code execution, so debug stays off then.
    host = os.environ.get("ZSIGNAL_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("ZSIGNAL_WEB_PORT", "5055"))
    app.run(host=host, port=port, debug=host in ("0.0.0.0", "localhost"))

"""song_of_the_day_bot.py
================================
GroupMe Song‑of‑the‑Day bot – queue management, daily pings, and quick help.

Commands (users send these in chat)
----------------------------------
!signup   – join the queue
!signout  – leave the queue
!queue    – show current order
!help     – display this command list

Automatic ping
--------------
Every day at `PING_AT` (HH:MM, 24‑hour, server local‑time – default **09:00**) the
bot tags the next user, then moves them to the back of the queue.

Configuration
-------------
BOT_ID     – **required** GroupMe Bot ID
PING_AT    – optional daily ping time, default "09:00"
QUEUE_FILE – optional path for queue persistence, default "queue.json"
PORT       – optional HTTP port for Flask, default 5000
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
import time
from typing import Dict, List


import flask
import requests
import schedule  # pip install schedule
from dotenv import load_dotenv

###############################################################################
# Configuration
###############################################################################
load_dotenv()  
BOT_ID: str = os.environ.get("BOT_ID") 
PING_AT: str = os.environ.get("PING_AT", "13:45")
QUEUE_FILE = pathlib.Path(os.environ.get("QUEUE_FILE", "queue.json"))
API_ENDPOINT = "https://api.groupme.com/v3/bots/post"

app = flask.Flask(__name__)

###############################################################################
# Persistence helpers
###############################################################################

def _load_queue() -> List[Dict[str, str]]:
    if QUEUE_FILE.exists():
        with QUEUE_FILE.open("r", encoding="utf-8") as fp:
            return json.load(fp)
    return []


def _save_queue(q: List[Dict[str, str]]) -> None:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(q, fp, indent=2)
    tmp.replace(QUEUE_FILE)

###############################################################################
# GroupMe helpers (send messages + mentions)
###############################################################################

def _post(text: str, mention: Dict[str, str] | None = None) -> None:
    payload: Dict = {"bot_id": BOT_ID, "text": text}
    if mention:
        tag = f"@{mention['name']}"
        start = text.find(tag)
        if start != -1:
            payload["attachments"] = [{
                "type": "mentions",
                "user_ids": [mention["user_id"]],
                "loci": [[start, len(tag)]]
            }]
    res = requests.post(API_ENDPOINT, json=payload, timeout=10)
    res.raise_for_status()

###############################################################################
# Command handlers
###############################################################################

def _signup(user_id: str, name: str) -> None:
    q = _load_queue()
    if any(e["user_id"] == user_id for e in q):
        _post(f"{name}, you’re already in the queue ✋")
        return
    q.append({"user_id": user_id, "name": name})
    _save_queue(q)
    _post(f"{name} joined the Song‑of‑the‑Day queue! 🎶")


def _signout(user_id: str, name: str) -> None:
    q = _load_queue()
    new_q = [e for e in q if e["user_id"] != user_id]
    if len(new_q) == len(q):
        _post(f"{name}, you weren’t in the queue 🤔")
        return
    _save_queue(new_q)
    _post(f"{name} left the queue. See you next time! 👋")


def _show_queue() -> None:
    q = _load_queue()
    if not q:
        _post("Queue is empty. Use !signup to claim a spot!")
        return
    listing = "\n".join(f"{i + 1}. {e['name']}" for i, e in enumerate(q))
    _post(f"Current Song‑of‑the‑Day queue:\n{listing}")


def _help() -> None:
    _post(
        "Commands:\n"
        "!signup  – join the queue\n"
        "!signout – leave the queue\n"
        "!queue   – display current order\n"
        "!help    – show command list\n\n"
        "I’ll automatically tag the next person every day at the scheduled time."
    )

###############################################################################
# Daily ping scheduler
###############################################################################

def _daily_ping() -> None:
    q = _load_queue()
    if not q:
        return
    current = q.pop(0)
    _post(
        f"@{current['name']} it’s your turn to share today’s song! 🎵",
        mention=current,
    )
    q.append(current)
    _save_queue(q)


def _scheduler_thread() -> None:
    schedule.every().day.at(PING_AT).do(_daily_ping)
    while True:
        schedule.run_pending()
        time.sleep(15)

###############################################################################
# Flask webhook
###############################################################################

@app.route("/callback", methods=["POST"])
def callback():
    data = flask.request.get_json(force=True, silent=True) or {}
    if data.get("sender_type") != "user":
        return "OK", 200

    text = (data.get("text") or "").strip().lower()
    user_id = data.get("sender_id")
    name = data.get("name") or "Unknown"

    match text:
        case "!signup":
            _signup(user_id, name)
        case "!signout":
            _signout(user_id, name)
        case "!queue":
            _show_queue()
        case "!help":
            _help()
    return "OK", 200

@app.route("/healthz", methods=["GET","HEAD"])
def health():
    return "OK", 200
###############################################################################
# Entry point
###############################################################################

if __name__ == "__main__":
    threading.Thread(target=_scheduler_thread, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

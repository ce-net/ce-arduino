#!/usr/bin/env python3
"""ce-arduino — the arduino port authority + connectivity-layout aggregator.

The "arduino app" Leif asked for: module ceapps coordinate through it so they never occupy the
same port, and you query it for the whole connectivity layout (which module is on which port and
exactly how to wire it). Nothing hardcoded to a node; runs beside the board's ce node.

Cap-gated mesh API on `ce.arduino/ctl` (JSON request/reply, every request carries `{"cap":...}`):
- `board`   (read)    -> the board's ports and their GPIO pins.
- `claim`   (control) -> `{module,instance,node,ctl_topic[,port]}` allocates a free port, returns
                          the port + exact pin wiring. Never double-allocates.
- `release` (control) -> `{instance}` frees a claim.
- `layout`  (read)    -> the whole connectivity map; live-pings each claimed module.

Config: `CE_ARDUINO_BOARD` (8port|14port, default 8port), `CE_ARDUINO_INSTANCE`, `CE_ARDUINO_CAP`
(cap presented when live-pinging modules), `CE_SENSOR_AUTH` (how this app's API is gated).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time

import ce

from atech_hw import HwError
from capauth import authorizer_from_env
from coordinator import PortRegistry

CTL_TOPIC = "ce.arduino/ctl"
ANNOUNCE_TOPIC = "ce.arduino/announce"
ACTION_READ = "arduino:read"
ACTION_CTL = "arduino:port"

log = logging.getLogger("ce-arduino")


def _err(m: str) -> bytes:
    return json.dumps({"error": m}).encode("utf-8")


def build_handler(registry: PortRegistry, authorizer, node_id: str, client, present_cap: str):
    def handle(msg):
        try:
            req = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _err("bad request: expected JSON")
        if not isinstance(req, dict):
            return _err("bad request: expected object")
        op = req.get("op")
        action = ACTION_READ if op in ("board", "layout") else ACTION_CTL
        if not authorizer.authorize(req.get("cap", ""), action, msg.sender, node_id):
            return _err(f"unauthorized: need {action}")

        if op == "board":
            return json.dumps({"ok": True, "board": registry.board_id,
                               "ports": registry.board_ports()}).encode("utf-8")
        if op == "claim":
            if not req.get("module") or not req.get("instance"):
                return _err("claim needs module + instance")
            try:
                entry = registry.claim(req["module"], req["instance"],
                                       node=req.get("node", ""), ctl_topic=req.get("ctl_topic", ""),
                                       port=req.get("port"))
            except HwError as e:
                return _err(str(e))
            return json.dumps({"ok": True, **entry}).encode("utf-8")
        if op == "release":
            return json.dumps({"ok": True, "released": registry.release(req.get("instance", ""))}).encode("utf-8")
        if op == "layout":
            lay = registry.layout()
            for m in lay["modules"]:
                m["live"] = _ping_module(client, m, present_cap)
            return json.dumps(lay).encode("utf-8")
        return _err(f"unknown op: {op!r}")

    return handle


def _ping_module(client, m: dict, cap: str) -> bool:
    """Best-effort: ask a claimed module to self-report its wiring, confirming it is running."""
    if not m.get("node") or not m.get("ctl_topic"):
        return False
    try:
        client.request(m["node"], m["ctl_topic"],
                       json.dumps({"op": "wiring", "cap": cap}).encode("utf-8"), timeout_ms=1500)
        return True
    except ce.CeError:
        return False


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    client = ce.connect().wait_ready()
    node_id = client.node_id
    board = os.environ.get("CE_ARDUINO_BOARD", "8port")
    instance = os.environ.get("CE_ARDUINO_INSTANCE", "arduino")
    present_cap = os.environ.get("CE_ARDUINO_CAP", "")
    authorizer = authorizer_from_env()
    registry = PortRegistry(board)
    log.info("ce-arduino up on node %s; board=%s (port authority + layout)", node_id[:16], board)

    def announce_loop():
        while True:
            try:
                client.publish(ANNOUNCE_TOPIC, json.dumps({
                    "schema": "ce.arduino.announce/1", "service": "ce-arduino",
                    "node": node_id, "instance": instance, "ctl_topic": CTL_TOPIC,
                    "board": board, "action_read": ACTION_READ, "action_ctl": ACTION_CTL,
                }, separators=(",", ":")).encode("utf-8"))
            except ce.CeError as e:
                log.warning("announce failed: %s", e)
            time.sleep(3)

    threading.Thread(target=announce_loop, name="announce", daemon=True).start()
    client.serve([CTL_TOPIC], build_handler(registry, authorizer, node_id, client, present_cap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

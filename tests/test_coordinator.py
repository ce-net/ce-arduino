"""Unit tests for PortRegistry: conflict-free allocation + the layout."""

from __future__ import annotations

import pytest

from atech_hw import HwError
from coordinator import PortRegistry


def _clock():
    t = {"v": 1000.0}
    return t, (lambda: t["v"])


def test_two_modules_get_different_ports_no_collision():
    reg = PortRegistry("8port")
    a = reg.claim("aht20", "thermo", node="n1", ctl_topic="ce.sensor/climate/ctl")
    b = reg.claim("neopixel", "led1", node="n1", ctl_topic="ce.sensor/led/ctl")
    assert a["port"] != b["port"]
    assert a["port"] == 1 and b["port"] == 2
    # exact wiring is returned with the claim
    assert a["wiring"][0]["role"] == "SDA" and a["wiring"][0]["gpio"] == 5


def test_claim_is_idempotent_per_instance():
    reg = PortRegistry("8port")
    first = reg.claim("aht20", "thermo")
    again = reg.claim("aht20", "thermo")
    assert first["port"] == again["port"]
    assert len(reg.claims) == 1


def test_explicit_port_conflict_is_rejected():
    reg = PortRegistry("8port")
    reg.claim("aht20", "thermo", port=1)
    with pytest.raises(HwError):
        reg.claim("neopixel", "led1", port=1)  # already taken


def test_layout_reports_whole_connectivity_map():
    reg = PortRegistry("8port")
    reg.claim("aht20", "thermo", node="n1", ctl_topic="a")
    reg.claim("neopixel", "led1", node="n1", ctl_topic="b")
    lay = reg.layout()
    assert lay["board"] == "8port" and lay["count"] == 2
    mods = {m["module"]: m for m in lay["modules"]}
    assert set(mods) == {"aht20", "neopixel"}
    assert mods["aht20"]["port"] != mods["neopixel"]["port"]
    # the board's usable ports are listed with their GPIO pins (reserved 6/8 are not slots)
    listed = {p["port"] for p in lay["ports"]}
    assert {1, 2, 3, 4} <= listed and 6 not in listed


def test_release_frees_the_port_for_reuse():
    reg = PortRegistry("8port")
    reg.claim("aht20", "thermo")          # port 1
    reg.claim("neopixel", "led1")         # port 2
    assert reg.release("thermo") is True
    # a new claim now reuses the freed lowest port
    assert reg.claim("pir", "motion")["port"] == 1


def test_expired_lease_frees_the_port():
    t, now = _clock()
    reg = PortRegistry("8port", lease=60.0, now=now)
    reg.claim("aht20", "thermo")  # port 1 until t=1060
    t["v"] += 61.0
    reg.prune()
    assert reg.claims == {}
    assert reg.claim("neopixel", "led1")["port"] == 1  # port 1 reusable

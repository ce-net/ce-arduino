"""Unit tests for the atech hardware model: wiring + free-port allocation."""

from __future__ import annotations

import pytest

from atech_hw import HwError, free_port, module_spec, wiring


def test_aht20_wiring_on_8port_port1_is_sda_scl_on_the_right_gpios():
    w = wiring("8port", "aht20", 1)  # port_1 -> (gpio5 A, gpio4 B)
    assert w == [{"port": 1, "line": "A", "gpio": 5, "role": "SDA"},
                 {"port": 1, "line": "B", "gpio": 4, "role": "SCL"}]


def test_neopixel_wiring_uses_line_a_data_pin():
    w = wiring("8port", "neopixel", 2)  # port_2 -> (gpio7 A, gpio6 B)
    assert w[0]["gpio"] == 7 and "DIN" in w[0]["role"]


def test_speaker_is_double_width_and_spans_adjacent_port():
    w = wiring("8port", "speaker", 1)  # size 2, adjacent pair (1,2)
    ports = {e["port"] for e in w}
    assert ports == {1, 2}
    roles = {e["role"] for e in w}
    assert {"LRCLK", "BCLK", "DIN"} <= roles


def test_free_port_picks_lowest_and_skips_taken():
    assert free_port("8port", "aht20", set()) == 1
    assert free_port("8port", "aht20", {1}) == 2
    assert free_port("8port", "aht20", {1, 2, 3}) == 4


def test_free_port_double_width_needs_adjacent_pair():
    # taking port 2 breaks the [1,2] pair, so a speaker must land on [3,4]
    assert free_port("8port", "speaker", {2}) == 3


def test_reserved_ports_are_never_allocated():
    board_full = {1, 2, 3, 4, 5, 7}
    assert free_port("8port", "aht20", board_full) is None  # 6 and 8 reserved, rest taken


def test_unknown_board_or_module_raises():
    with pytest.raises(HwError):
        wiring("999port", "aht20", 1)
    with pytest.raises(HwError):
        module_spec("nonesuch")

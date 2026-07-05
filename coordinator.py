"""PortRegistry — the atech port authority (pure, testable).

Module ceapps `claim` a port; the registry allocates the lowest free compatible port and
records it, so two apps can never occupy the same port. `layout` returns the whole
connectivity map (every claimed module, its port(s), and the exact pin wiring). Claims carry
a lease and are pruned when a module stops heartbeating, so the layout reflects live state.
"""

from __future__ import annotations

import time
from typing import Optional

from atech_hw import HwError, board_map, free_port, module_spec, ports_used, wiring

DEFAULT_LEASE = 90.0


class PortRegistry:
    def __init__(self, board_id: str = "8port", *, lease: float = DEFAULT_LEASE,
                 now=time.time) -> None:
        board_map(board_id)  # validate
        self.board_id = board_id
        self.lease = lease
        self._now = now
        self.claims: dict = {}  # instance -> claim dict

    def _taken(self, exclude: Optional[str] = None) -> set:
        now = self._now()
        taken = set()
        for inst, c in self.claims.items():
            if inst == exclude or c["expires"] <= now:
                continue
            taken.update(c["ports"])
        return taken

    def claim(self, module: str, instance: str, *, node: str = "", ctl_topic: str = "",
              port: Optional[int] = None) -> dict:
        """Claim a port for `module`/`instance`. Idempotent per instance (renews the lease).
        Allocates the lowest free compatible port unless a specific `port` is requested."""
        module_spec(module)  # validate module id
        now = self._now()
        existing = self.claims.get(instance)
        if existing and existing["module"] == module and existing["expires"] > now \
                and (port is None or port == existing["port"]):
            existing.update(expires=now + self.lease,
                            node=node or existing["node"],
                            ctl_topic=ctl_topic or existing["ctl_topic"])
            return self._entry(existing)

        taken = self._taken(exclude=instance)
        if port is not None:
            used = ports_used(self.board_id, module, port)
            if any(u in taken for u in used):
                raise HwError(f"port {port} already occupied on {self.board_id}")
            chosen = port
        else:
            chosen = free_port(self.board_id, module, taken)
            if chosen is None:
                raise HwError(f"no free port for {module} on {self.board_id} (board full)")
        claim = {"module": module, "instance": instance, "node": node, "ctl_topic": ctl_topic,
                 "port": chosen, "ports": ports_used(self.board_id, module, chosen),
                 "expires": now + self.lease}
        self.claims[instance] = claim
        return self._entry(claim)

    def release(self, instance: str) -> bool:
        return self.claims.pop(instance, None) is not None

    def prune(self) -> None:
        now = self._now()
        for inst in [i for i, c in self.claims.items() if c["expires"] <= now]:
            del self.claims[inst]

    def _entry(self, c: dict) -> dict:
        return {
            "module": c["module"], "instance": c["instance"], "node": c["node"],
            "ctl_topic": c["ctl_topic"], "port": c["port"], "ports": list(c["ports"]),
            "wiring": wiring(self.board_id, c["module"], c["port"]),
        }

    def board_ports(self) -> list:
        """Usable slots and their two GPIO pins (reserved ports are not slots, so excluded)."""
        board = board_map(self.board_id)
        return [{"port": p, "line_a_gpio": a, "line_b_gpio": b}
                for p, (a, b) in sorted(board["ports"].items())]

    def layout(self) -> dict:
        """The whole connectivity layout: board + every claimed module with its wiring."""
        self.prune()
        return {
            "schema": "ce.arduino.layout/1",
            "board": self.board_id,
            "ports": self.board_ports(),
            "modules": [self._entry(c) for c in self.claims.values()],
            "count": len(self.claims),
        }

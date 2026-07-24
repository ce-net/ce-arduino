# ce-arduino

The **arduino port authority + connectivity-layout aggregator** — the "arduino app". Module
ceapps (sensors, LED, …) coordinate their board ports through it so they never occupy the same
port, and you query it for the whole connectivity layout: which module is on which port and
exactly how to wire it. A Python `script`-tier ceapp that runs on each board node.

Hardware model + specs come exactly from the atech SDK catalog (`ce-atech/sdk/catalog`), vendored
as `atech_hw.py`. See `docs/atech-modules.md` in github.com/ce-net/ce-sensor-climate.

## API (`ce.arduino/ctl`, cap-gated request/reply, JSON — every request carries `{"cap":..}`)

| op | level | effect |
|---|---|---|
| `board` | read | the board's ports and their GPIO pins |
| `claim` | control | `{module,instance,node,ctl_topic[,port]}` → allocate a free port; returns the port + exact pin wiring. Never double-allocates. |
| `release` | control | `{instance}` → free a claim |
| `layout` | read | the whole connectivity map; live-pings each claimed module |

Caps: `arduino:read` (board/layout), `arduino:port` (claim/release). Board via `CE_ARDUINO_BOARD`
(`8port` | `14port`, default `8port`).

## How coordination works

A module calls `claim {module:"aht20"}` at startup; `PortRegistry` allocates the lowest free
compatible port (respecting reserved ports and double-width adjacency) and records it under a lease.
The next module's claim gets a different port — no collisions. `layout` returns every claim with its
wiring and live status; claims expire if a module stops, so the layout reflects what is actually
running.

## Example layout (`layout`)

```json
{"schema":"ce.arduino.layout/1","board":"8port","count":2,
 "modules":[
   {"module":"aht20","instance":"thermo","port":1,"live":true,
    "wiring":[{"port":1,"line":"A","gpio":5,"role":"SDA"},{"port":1,"line":"B","gpio":4,"role":"SCL"}]},
   {"module":"neopixel","instance":"led1","port":2,"live":true,
    "wiring":[{"port":2,"line":"A","gpio":7,"role":"DIN (data / RGB)"}, ...]}]}
```

## Develop & test

```bash
python3 test.py    # instant, zero-install: hardware model (wiring, allocation) + registry (no collisions)
```

# Why Start Light needs Pico 2 W for competition cloud

Application `.py` files run on both **Pico W** (RP2040) and **Pico 2 W** (RP2350). Wiring is identical. For **paired** rcdrift.ro events (HTTPS poll / claim / sync), **Pico 2 W is required in production**. Pico W remains fine for unpaired local HTTP/BLE start trees.

Flash the matching UF2 (`RPI_PICO2_W` vs `RPI_PICO_W`) — images are not interchangeable. See [DEPLOY.md](DEPLOY.md).

## What failed on Pico W in the field

Production logs on Pico W showed a repeating pattern during qualifications:

1. Device syncs and claims START successfully.
2. Countdown phase starts with **all lamps dark**.
3. Cooperative ticks open a new HTTPS poll (TLS handshake) on every sleep slice.
4. TLS wrap hits **errno 110** (`ETIMEDOUT`) under low RAM / CYW43 load.
5. Firmware treats the failed lease as “server stopped” and **aborts before red ever turns on**.
6. Separate failure mode: idle Preparation keeps `control.stop` true → naive firmware POSTed `ack_off` every ~1 s → TLS allocation storm → **OOM / soft reboot** → device looks offline.

Standalone local starts (no cloud) did not show this; the radio only has to serve one short HTTP accept loop.

## What Pico 2 W changes

| Constraint | Pico W (RP2040) | Pico 2 W (RP2350) |
|------------|-----------------|-------------------|
| SRAM | ~264 KB shared | Larger / dual-core RP2350 headroom |
| HTTPS + WiFi + JSON | Frequently times out or OOMs under 1 s poll + TLS retry | Stable for short-poll protocol 2 |
| Same `.py` app | Yes | Yes (preferred) |
| Same lamp GPIO | GP2–GP5 active-low | Same |

More RAM and a newer MicroPython port make concurrent TLS (ISRG Root X1 verify + hostname) and CYW43 WiFi survivable at competition poll rates. That is a **platform** fix, not a lease-protocol trick alone.

## Firmware mitigations (still required)

Even on Pico 2 W we keep Pico-W-hostile patterns out of the hot path:

- **No HTTPS poll while a claimed sequence is active** — hold the lease locally after claim; observe STOP/pause once at green (`report('go')`).
- **No mid-sequence phase telemetry** — claim carries the exact lamp **plan** so the site animates the same delay/red/random_wait/yellow/green without status POSTs during countdown.
- **`resume_poll` only after `all_off()`** — next competition step can sync immediately without leaving the radio busy while lamps still run.
- **Idle polls are GET-only** after boot sync — do not POST `ack_off` every second merely because Preparation sets `stop`.
- **Claim immediately after sync ack** (`force_poll_soon`) — avoids HTTP 409 “lease expired” when the site arms START right after sync.
- **Local HTTP accept before/after cloud tick** — a slow TLS poll must not starve Settings / unpair.
- Longer poll TLS timeout (~2.5 s) and backoff on transport failure — fewer false “link dead” loops.

Protocol mind map: [STARTLIGHT_SYNC_MINDMAP.md](STARTLIGHT_SYNC_MINDMAP.md).

## Recommendation

| Use case | Board |
|----------|--------|
| Paired event / Race Director / shared START | **Pico 2 W** |
| Unpaired club tree, BLE WiFi setup, local PIN UI | Pico W or Pico 2 W |
| New hardware purchases | Pico 2 W only |

Moving W → 2 W: flash `RPI_PICO2_W`, copy the same `firmware/*.py`, re-pair or restore `cloud_creds.json` only from a trusted backup (never commit tokens). Pinout unchanged.

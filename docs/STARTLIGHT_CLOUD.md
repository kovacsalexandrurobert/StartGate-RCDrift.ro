# Start Light ↔ rcdrift.ro (protocol 2)

Optional cloud overlay. **Standalone local HTTP/BLE starts always work while unpaired.** Pairing is opt-in from the device Settings page or organizer **Configurare semafor**.

Default API base when enabling cloud: `https://staging.rcdrift.ro` (does not auto-switch to production).

## Standalone (unpaired)

- Local `GET /start`, web UI, and BLE `START` / `GO` / `RUN` run `run_start_sequence` only.
- No cloud poll, claim, or events.
- Unpair explicitly to leave cloud mode; after unpair the device is standalone again.
- When **paired**, local/BLE start does **not** fall back to a private sequence if the site cannot confirm — use **Dezleagă** / unpair for independent use.

## Organizer flow (paired)

1. Save prep and start qualifications in RCDrift. Pair the Pico with the code from **Configurare semafor**. Install all new `.py` modules before pairing; old protocol is blocked for synchronized control.
2. One main button shows **START**, then waits for green/off confirmation and judges’ scores. After all scores, the same button becomes **Următorul pilot**. The next driver does not auto-start.
3. Qualifying: all drivers run 1, then run 2. Battles: presentation → START first run → swap sides → START second run → vote → next duel.
4. Local page START and optional GPIO use the same revision-bound command. The device cannot publish points, manage roles, or resume a paused event alone.

## Pause, lease, reboot

- Pause invalidates unused STARTs. During a sequence the firmware re-checks step/permission and stops lamps on pause, session change, or a lost 5 s lease. Network latency is not a hard e-stop.
- `stopped` is acknowledged only after `all_off()`. Resume does not auto-start a new sequence.
- On reboot, Pico persists a boot counter in `cloud_state.json`, runs the normal lamp self-test (even when paired), then turns lamps off and syncs before claims. Stale counters / already-claimed commands cannot replay START.
- `done` means **lamps off**, not car arrival. IR finish sensor stays optional and off by default.

## Physical button

`PHYSICAL_BUTTON_PIN = None` until wiring is known. For a button to GND, set a free pin (not GP2–GP5, GP6/GP7, or the finish pin). Pull-up, debounce, release-after-boot. Local web START works without extra GPIO.

## Device API (paired)

Auth: `Authorization: Bearer <deviceToken>` except pair.

| Call | Role |
|------|------|
| `POST /api/startlight/pair` | One-shot code → token; site stores hash only. `apiBase` must be a public `https://` origin (firmware ignores localhost/loopback) |
| `GET /api/startlight/poll` | Control revision, STOP/sync, pending START, lease (~1 s poll). After boot sync, idle polls are GET-only — `control.stop` while not in a sequence (e.g. Preparation) must not trigger a POST every second |
| `POST /api/startlight/claim` | Atomic claim; require `claimed: true` |
| `POST /api/startlight/events` | `sync` / `stopped` / `go` / `done` (+ optional sensor) |
| `POST /api/startlight/button` | Stable `requestId` for retries |

HTTPS verifies public CA + hostname (`root_ca.py` ISRG Root X1, `ntptime.py` for UTC). No `CERT_NONE` fallback.

## Organizer manage API

`POST /api/startlight/manage` (session + event manage): `createPairing`, `list` / `unbind` / `revokeDevice`, queue helpers, cue start/cancel as implemented on the site.

## Finish sensor (phase 4)

Anonymous IR break-beam after green: break #1 = exit, break #2 (after min run) = finish. No car ID yet. Does not advance drivers or scores alone.

## Install / tests

Copy only `firmware/*.py` to the Pico root. Keep on-device WiFi/timing/token JSON; do not commit them. See [DEPLOY](DEPLOY.md).

`python -m unittest discover -s tests -v` uses simulated GPIO/clock/transport. `python tests/staging_tls_smoke.py` checks public staging HTTPS only. Neither replaces physical acceptance on wired Pico + SSR + lamps.

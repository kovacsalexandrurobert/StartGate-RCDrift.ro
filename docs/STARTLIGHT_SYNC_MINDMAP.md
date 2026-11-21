# Start Light sync — mind map (protocol 2)

rcdrift.ro is authoritative when the Pico is **paired**. The device polls, syncs lamps-off, claims START, then runs the local GPIO sequence. Unpaired devices stay fully local (HTTP/BLE) and never need this flow.

Companion protocol notes: [STARTLIGHT_CLOUD.md](STARTLIGHT_CLOUD.md). Why competition WiFi needs Pico 2 W: [PICO_2W.md](PICO_2W.md).

## Happy path (left → right)

```mermaid
flowchart LR
  pair["1. Pair<br/>POST /pair → token"]
  boot["2. Boot<br/>bootId + bootCounter"]
  poll1["3. Poll<br/>GET /poll"]
  sync["4. Sync<br/>POST sync, lampsOff"]
  ready["5. Ready<br/>synced, canPress"]
  press["6. Press START<br/>site or local button"]
  armed["7. Cue armed<br/>revision++, armed cue"]
  sync2["8. Sync rev<br/>syncRequired → ack"]
  pending["9. Pending<br/>pendingCommand visible"]
  claim["10. Claim<br/>POST /claim + plan → starting"]
  seq["11. Sequence<br/>red → yellow → green"]
  go["12. go / done<br/>POST events"]

  pair --> boot --> poll1 --> sync --> ready --> press --> armed --> sync2 --> pending --> claim --> seq --> go
```

1. **Pair** — one-shot code from Configurare semafor; token stays on-device in `cloud_creds.json`.
2. **Boot** — monotonic `bootId` / counter so a reboot cannot replay an old START.
3. **Poll** — short GET (~1 s when healthy). Idle Preparation `stop` must not trigger TLS POSTs every second.
4. **Sync** — device reports lamps off; site clears `syncRequired`.
5. **Ready** — organizer may press START (`canPress`).
6. **Press** — site or local HTTP/GPIO (same revision-bound command).
7. **Armed cue** — site bumps revision and arms the START.
8. **Sync rev** — Pico acks the new revision, then **force-polls** so claim happens before the short lease dies.
9. **Pending** — `pendingCommand` appears only when synced + lamps off.
10. **Claim** — `claimed: true` required; body may include the exact lamp **plan** for the site preview. After claim, **HTTPS poll pauses** for the whole sequence.
11. **Sequence** — local GPIO only (countdown → red → random wait → yellows → green). No mid-sequence status POSTs.
12. **go / done** — `go` at green (also re-checks pause/STOP once); `done` only after all outputs are off; then **resume_poll** for the next step.

## Why sync exists

- New `bootId` → no replay of an old START after reboot.
- Revision match → correct race step (qualifying / battle / pause).
- `lamp_state=off` → safe to arm the next cue.
- Site is authority for the shared competition button.

## Poll fields that matter

| Field | Meaning |
|-------|---------|
| `syncRequired` | Must POST sync/stopped before claim |
| `canPress` | Organizer UI may request START |
| `permitted` | Device may run / keep a claimed sequence |
| `pendingCommand` | Claimable START (when synced + lamps off) |
| `cue.status` | `starting` / `go` / `done` / … |

## Failure paths

| Symptom | Cause / fix |
|---------|-------------|
| HTTP **409** on claim | Lease expired because sync ran too late — claim immediately after sync ack (`force_poll_soon`) |
| `tls:110` / ETIMEDOUT | HTTPS wrap timeout on Pico W RAM; backoff poll; prefer **Pico 2 W** for paired events |
| Pause mid-cue | Site cancels unused START; during sequence STOP is observed at green via `report('go')` |
| Lease lost while running (legacy) | Older firmware polled every sleep tick and aborted before red — current firmware holds lease locally after claim |
| Idle POST storm | Do not `ack_off` every poll merely because Preparation sets `stop` |

## Who does what

**rcdrift.ro** — creates pairing · owns revision · arms cue on START · exposes `pendingCommand` only when synced + lamps off · accepts claim (+ optional plan) · receives go/done · cancels on pause.

**Pico** — polls ~1 s when idle · ack sync/stopped · claim (with plan) before/after sync · runs GPIO sequence with poll paused · signals go/done · `resume_poll` only after all lamps off.

## Related site work

Race Director shows each sync step and an animated lamp tree driven by the claim **plan** (same timings the Pico rolled for that run). Those UI pieces live in the rcdrift.ro repo, not on the device.

# Start Light ↔ rcdrift.ro protocol

Optional cloud overlay. **Standalone local HTTP/BLE starts always work** with no pairing.

## Defaults

| Setting | Value |
|---------|--------|
| Cloud | Off until paired |
| API base (when enabled) | `https://staging.rcdrift.ro` until production promote |
| Poll | 1 s short poll (long-poll only if Pico TLS proves stable) |
| Auth | Device bearer token after pairing code |

## Device endpoints

All device calls use `Authorization: Bearer <deviceToken>` except pair.

### `POST /api/startlight/pair`

Body: `{ "code": "ABC123", "devicePublicId": "optional-stable-id", "label": "Gate 1", "firmwareVersion": "…" }`

Returns once: `{ "ok": true, "deviceId", "deviceToken", "eventId", "apiBase" }`. Store token on device; site keeps hash only.

### `GET /api/startlight/poll`

Returns `{ "queue", "pendingCommand", "cue", "serverTime", "bound" }`. Empty `pendingCommand` when idle. Short-poll every ~1 s from firmware.

### `POST /api/startlight/claim`

Body: `{ "commandId": "…" }` — atomic claim of a START command.

### `POST /api/startlight/events`

Body: `{ "commandId"?, "type": "starting"|"go"|"done"|"error"|"local_start"|"exit"|"finish", "at": ISO8601, "detail"? }`

## Organizer (session)

`POST /api/startlight/manage` with `sameOrigin` + event manage permission:

- `createPairing` → short-lived code
- `list` / `unbind` / `revokeDevice`
- `setQueue` / `suggestQueue`
- `startCue` / `cancelCue`

## Standalone

Unpaired devices never call these APIs. Local `/start` and BLE `START` run `run_start_sequence` only. When paired, local start also emits `local_start` + sequence events if the site is reachable.

## Finish sensor (phase 4)

Anonymous IR break-beam: after green, break #1 = exit, break #2 (after min run time) = finish. No car ID until a later phase.

## TLS note (spike)

MicroPython on Pico W / Pico 2 W should use short HTTPS GET/POST with small JSON. Prefer 1 s poll over multi-second long-poll until a device soak test confirms TLS sockets stay healthy under CYW43 + SoftI2C OLED.

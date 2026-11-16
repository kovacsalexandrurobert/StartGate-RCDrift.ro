# Agent guide — Start Light (RC drift)

Firmware for a **Raspberry Pi Pico 2 W** (preferred; MicroPython **RPI_PICO2_W** 1.26+) that runs a drift/F1-style start lamp tree. The same `.py` modules also run on the original **Pico W** (**RPI_PICO_W** 1.22+). Four GPIO outputs drive solid-state relays. Operators start a run from a phone browser on WiFi, or from BLE when WiFi is down.

UF2 images are **not** interchangeable between Pico W and Pico 2 W. Application code is. Human setup lives in `README.md`. Wiring lives in `docs/SCHEMATIC.md`. This file is the behavior contract. Repo layout keeps docs off the device: only `firmware/*.py` is flashed.

## Git workflow (trunk-based)

`main` is protected. **Never commit or push directly to `main`.** Every change uses a short-lived branch and a PR (squash or rebase). See `docs/CONTRIBUTING.md`.

```text
git checkout main && git pull
git checkout -b feature/<short-name>
# …edit, commit…
git push -u origin HEAD
# open PR → merge → delete branch
```

## Repo layout

| Path | On the Pico? | Role |
|------|--------------|------|
| `firmware/` | Yes — copy `.py` only | Deployable MicroPython (Pico 2 W / Pico W) |
| `docs/` | No | Schematic, deploy, contributing, examples |
| `AGENTS.md`, `README.md`, `LICENSE` | No | Agents, humans, license |
| `.cursor/rules/` | No | Cursor agent constraints |

## Deploy

Copy **only** the `.py` files from `firmware/` to the Pico root. Example: `mpremote cp firmware/*.py :`. Do not copy `docs/` or this file. Full steps: `docs/DEPLOY.md`.

`firmware/boot.py` is intentionally empty; `firmware/main.py` is the program. Imports stay flat (`from lights import …`) because files land at the Pico root, not inside a `firmware` package.

Do **not** copy JSON files from a dev PC onto the device, and do not commit them. They are created on the Pico and hold WiFi passwords plus local timing overrides. `firmware/config.py` ships with `WIFI_SSID` and `WIFI_PASSWORD` empty so first boot falls through to BLE provisioning.

Runtime is MicroPython: `%` formatting, `machine` / `network` / `bluetooth`, no `pip`, no `asyncio`, no type-checking imports.

## Module map

| File | Role |
|------|------|
| `firmware/main.py` | Boot, WiFi retry loop, BLE fallback, IP handoff, start loop |
| `firmware/board.py` | Pico 2 W / Pico W detection for boot logs |
| `firmware/boot.py` | Empty. MicroPython runs it before `main.py` |
| `firmware/config.py` | Compile-time defaults: GPIO, timing, display, BLE PIN, country, scan flag |
| `firmware/settings.py` | Load/save `startlight_config.json`, merge onto defaults, compute start delay |
| `firmware/lights.py` | Active-low GPIO. Self-test, status blink, start sequence |
| `firmware/webserver.py` | One-shot HTTP server, inline UI, `/start`, LED test API |
| `firmware/wifi_config.py` | Known networks, last SSID, country, BLE-IP-pending flag, legacy creds migration |
| `firmware/ble_uart.py` | Nordic UART peripheral: PIN, credentials, `START`, IP beacon |
| `firmware/ble_advertising.py` | Advertising payload helper (MicroPython sample). Leave it alone |
| `firmware/display.py` | Optional SSD1306 status screens. Failures are swallowed |
| `firmware/ssd1306.py` | Vendored I2C driver from micropython-ssd1306. Do not restyle |
| `firmware/onboard_led.py` | `Pin("LED")` via CYW43. No-op if the LED pin is missing |
| `firmware/cloud.py` | Optional rcdrift.ro client (off until paired). Standalone otherwise |
| `firmware/http_client.py` | Minimal HTTPS JSON for Pico |
| `firmware/finish_sensor.py` | Anonymous IR break-beam dual-pass (exit then finish) |

Cloud protocol: `docs/STARTLIGHT_CLOUD.md`. Default API base when enabling cloud: `https://staging.rcdrift.ro`.

`docs/schematic.svg` matches `docs/SCHEMATIC.md`.

## Boot flow (`firmware/main.py`)

1. Set the WiFi country from `wifi_country.json` or `config.WIFI_COUNTRY` (default `RO`) via `rp2.country` and `network.country` **before** WLAN init.
2. `settings.load()` then `LightController()`.
3. Self-test (`show_boot`, `lights.run_self_test`).
4. WiFi loop:
   - No stored SSID: skip connect and enter BLE immediately.
   - Stored SSID: up to 3 full attempts (`WIFI_RETRY_BEFORE_BLE`). Each attempt tries every saved network (`WIFI_TIMEOUT_MS` = 15000).
   - Attempt 3 failure blinks red on the lamps and runs `status_not_connected` (onboard LED 3 blinks, then 3 s), then BLE.
   - BLE success (`ssid` returned) blinks green and `machine.reset()`.
   - BLE timeout or error: loop retries WiFi.
5. If `ble_pending_ip.json` says pending and the station has an IP: WiFi off, advertise `StartLight-IP` for 30 s, then reconnect with `load_credentials()` (last successful SSID first).
6. Ready loop: if `is_start_requested()`, run the lamp sequence, else `run_server` once, then sleep 50 ms.

`KeyboardInterrupt` calls `_cleanup`: all lamps off, onboard LED off, WLAN off, so a host tool can re-upload.

## Lamp sequence

`LightController.run_start_sequence` is the only sequence. Lamps **stack** (earlier colors stay on) until the end.

| Phase | What happens |
|-------|----------------|
| 1 | All off. Countdown of `int(start_delay)` whole seconds. Fractional seconds are dropped |
| 2 | Red ON for `red_duration` |
| 3 | Red stays on. Sleep `random.uniform(random_wait_min, random_wait_max)` |
| 4 | Yellow 1 ON, sleep `yellow_interval` |
| 5 | Yellow 2 ON, sleep `yellow_interval` again |
| 6 | Green ON for `green_off_delay`, optional `callback("go", 0)` |
| 7 | All off, optional `callback("done", 0)` |

`config.GREEN_AFTER_LAST_YELLOW` is **not** read. The gap from yellow 2 to green is `yellow_interval`.

Indices: `0` red GP2, `1` yellow 1 GP3, `2` yellow 2 GP4, `3` green GP5. Active-low. `run_self_test` turns each lamp on in order and leaves the earlier ones on, then `all_off`. `blink_status` clears all lamps, then blinks green, yellow 1, or red.

Web and BLE both compute the pre-start delay with `settings.get_start_delay`:

- `start_delay_mode == 1`: fixed `start_delay_fixed` seconds
- else: `random.uniform(start_delay_random_min, start_delay_random_max)`

Defaults in `config.py`: red 1.0 s, random wait 1–3 s, yellow interval 0.5 s, green hold 3.0 s, start delay mode 0 with random 5–20 s (fixed 5 s if mode is 1). A `startlight_config.json` on the Pico overrides these key by key. Missing or invalid JSON falls back to `settings.DEFAULTS`.

## HTTP (`firmware/webserver.py`, port 80)

`run_server` binds, listens for **one** client with a 1 s accept timeout, handles it, closes the socket, returns. `SO_REUSEADDR` is set. Bind failure (port in use) returns immediately. The start sequence blocks the ready loop, so HTTP is dead for the whole sequence.

Responses use `_send_all` (looped 1 KiB `socket.send` + `Content-Length`). A single `conn.send(big_buffer)` on Pico often truncates mid-page; there is no separate “raise the HTTP limit” knob.

No authentication. The server is only as private as the LAN.

| Route | Behavior |
|-------|----------|
| `GET /`, `GET /control` | Remote page. `?saved=1` shows a “Settings saved” banner |
| `GET /settings` | Timing + WiFi form, plus per-channel LED test checkboxes |
| `POST /settings` | Saves fields, responds `303` to `/?saved=1` |
| `GET /start` | Builds a timing **plan** (delay, red, random wait, yellow interval, green hold), sets `start_requested`, returns that plan as JSON |
| `GET /api/settings` | Current settings JSON. No WiFi password |
| `GET /api/led?n=0..3&on=0\|1` | Holds that output on or off. `n` outside 0–3 returns `{"ok": false}` |
| anything else | HTML 404 |

POST `/settings` WiFi: a non-empty SSID is written with `wifi_config.save_credentials`. A blank password keeps the stored password. This does **not** reconnect or reboot; the new network is used on the next boot. Timing fields use `_safe_float` / `_safe_int` and fall back to the hardcoded defaults inside the handler (red 1, wait 1–3, yellow 0.5, green 3, delay mode 0, fixed 5, random 5–20), then `settings.save`.

The remote page animates a **lamp tree** from the `/start` plan (same `random_wait` the Pico uses). Countdown matches `int(delay)` 1 s ticks, then red → hold → yellow 1 → yellow 2 → green/`GO!` → off. HTTP is still blocked on the Pico for the whole sequence; the browser does not poll lamp state.

UI language is **client-side RO/EN** (`localStorage` key `sl_lang`, default `ro`). The language switcher in the header applies to Remote, Settings, and 404. Keep copy in `_i18n_js()` dictionaries; mark strings with `data-i18n` / `data-i18n-html` / `data-i18n-placeholder`.

The settings page label “Random (5–20 sec)” is fixed text. The real range is `start_delay_random_min` / `start_delay_random_max`. LED test checkboxes are not synced back from the device; a sequence can turn lamps off while the boxes stay checked.

`/api/settings` returns the settings dict only. Do not add passwords to that payload.

## BLE (only when WiFi is off)

Advertised name `StartLight-WiFi`. Nordic UART:

- Service `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
- RX write `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` (write and write-without-response)
- TX notify `6E400003-B5A3-F393-E0A9-E50E24DCCA9E`

`wait_for_credentials` times out after 300 s. On connect the peripheral writes a prompt.

If `BLE_PIN_ENABLED` (default True): a random 6-digit PIN is drawn on the OLED (`display.show_ble_pin`) and also sent as `Enter PIN: NNNNNN (on display)`. The next write must equal `str(pin)` or the zero-padded form. Wrong PIN replies `Wrong PIN` and does not consume the rest of the command. The PIN confirms the operator can see the board; it is not withheld from the BLE link.

After the PIN (or immediately, if PIN is disabled), a write is one of:

| Payload | Result |
|---------|--------|
| `START`, `GO`, `RUN` (any case) | Same `run_start_sequence` as the web button. Stays in BLE mode |
| `{"cmd":"start"}` or `{"cmd":"go"}` | Same sequence |
| `SSID,password` | Save network, set pending-IP flag, return so `main` reboots |
| `SSID,password,CC` | Same, plus country when `CC` is exactly 2 letters |
| `{"ssid","password","country"?}` | Same. Country saved only when length is 2 |

Empty password is stored for comma and JSON forms, but `connect_wifi` skips any network whose password is empty. Open networks do not connect.

`save_credentials` updates or appends `wifi_networks.json` and also rewrites legacy `wifi_creds.json`. On load, if `wifi_networks.json` is missing, `wifi_creds.json` is migrated once, else `config.WIFI_SSID` is used.

After reboot, `send_ip_via_ble` advertises `StartLight-IP` for 30 s and, on connect, writes `IP: http://<ip>`.

Onboard LED during the BLE wait: on 2 s, off 1 s (`status_ble_tick`). During WiFi connect: 200 ms on each second (`status_connecting_tick`). After WiFi success: on 1 s, blink 5×, off (`status_connected`).

## WiFi selection

`get_networks_to_try(scan_results)`:

- Last successful SSID (`last_wifi.json`) is tried first when it is in the saved list.
- `config.WIFI_SCAN_ENABLED` defaults to **False** because `wlan.scan()` can hang on some Pico W builds. With scanning off, `scan_results` is `None` and the last SSID is still tried first, then the others.
- `record_successful_connection` runs only after `STAT_GOT_IP`.

`has_credentials` is true when the preferred saved SSID is non-empty.

## OLED

`display.py` uses I2C bus 1, SDA GP6, SCL GP7, 400 kHz, SSD1306 128×64 at address **0x3C only**. `SCHEMATIC.md` also mentions 0x3D; the code never probes it. `DISPLAY_ENABLED = False` or a missing panel makes every `show_*` call a no-op. Text is 4 lines × 21 characters. After WLAN is turned off for BLE, `reset_oled_cache` drops the cached I2C object before the PIN screen is drawn.

## Persistence

| File | Writer | Contents |
|------|--------|----------|
| `startlight_config.json` | `settings.save` | Timing keys listed in `settings.DEFAULTS` |
| `wifi_networks.json` | `wifi_config._save_networks` | `{"networks": [{"ssid", "password"}, ...]}` |
| `wifi_creds.json` | `save_credentials` | Legacy `{"ssid", "password"}` of the network just saved |
| `last_wifi.json` | `record_successful_connection` | `{"ssid"}` |
| `wifi_country.json` | `save_wifi_country` | `{"country": "RO"}` |
| `ble_pending_ip.json` | `set_pending_ip_via_ble` | `{"pending": true/false}` |

All of these are gitignored. Sanitized templates (placeholders only) live in `docs/examples/*.json.example`.

## Status outputs (keep in sync)

| Moment | Lamps | Onboard LED | OLED |
|--------|-------|-------------|------|
| Self-test | Each color on in order, then off | unchanged | `Start Light` / `Self-test...` |
| Connecting | Yellow 1 once | 200 ms flash per second | `WiFi` / `Connecting...` / SSID |
| WiFi OK | Green ×5 | on, blink ×5, off | `WiFi OK` / SSID, later `Ready!` + IP |
| Retry after 3 failures | Red ×2 | blink ×3, wait 3 s | `WiFi failed` |
| BLE wait | Red ×2 then yellow ×1 on entry | on 2 s, off 1 s | PIN, then `BLE mode` |
| BLE creds saved | Green ×3, then reset | BLE pattern until reset | `BLE OK` / `Rebooting...` |
| Ready | all off | off | `Ready!` and `http://` + IP |

## Safe change recipes

**Change a default delay.** Edit the constant in `firmware/config.py` and the matching key in `settings.DEFAULTS` (it already imports the constants). Existing Picos keep `startlight_config.json` until the web form saves again.

**Change a pin.** Edit `config.GPIO_PINS` order `[red, yellow1, yellow2, green]` and the matching table in `README.md` / `docs/SCHEMATIC.md`. Update the settings-page checkbox labels in `firmware/webserver.py`. Do not invert active-low in software unless the SSR input is rewired.

**Add a start command.** Call `get_start_delay` + `lights.run_start_sequence` with the same five timing fields the web path uses. Do not duplicate the phase sleeps.

**Add a web field.** Add the default in `firmware/config.py` and `settings.DEFAULTS`, an input in `serve_settings`, and a `_safe_float` / `_safe_int` assignment in the POST branch before `save`.

**Add an OLED screen.** Add a `show_*` function in `firmware/display.py` that only calls `show_lines`. Catch nothing in callers beyond what `show_lines` already swallows. Never let display init failure break WiFi or the lamps.

**Never put docs on the Pico.** Keep new markdown, SVG, and large assets under `docs/` or the repo root. Only add or edit `.py` under `firmware/` for device deploy.

## Out of scope unless the hardware changes

- Running WiFi and BLE together (one CYW43 on Pico W and Pico 2 W).
- Flashing the wrong MicroPython UF2 for the physical board.
- Driving more than the four color channels. Extra lamp trees are wired in parallel on the same SSR, not extra GPIOs.
- Authenticating the HTTP server. Anyone on the LAN can start a run and can rewrite WiFi credentials.
- Treating the BLE PIN as a secret. The connect notification repeats it.

# Start Light - Wireless Race Start System

Wireless remote-controlled start light system for F1/drift racing, built for **Raspberry Pi Pico W** with MicroPython.

Agents changing this firmware should follow **AGENTS.md** (behavior contract) before editing.

## Features

- **Single set of 4 outputs** (Red, Yellow1, Yellow2, Green) — wire multiple light sets in parallel per color
- **WiFi control** – web interface for settings and remote start
- **BLE fallback** – send WiFi credentials via Bluetooth when connection fails; **START / GO** over BLE runs the same race sequence when WiFi is unavailable
- **Drift-style sequence**: Red → random wait → Yellow 1 → Yellow 2 → Green (GO)
- **Configurable timing** – delays, random/fixed countdown
- **Self-test on boot** – cycles all lights, then status blinks (green=OK, yellow=connecting, red=error)
- **Optional status display** – SSD1306 128×64 I2C OLED shows BLE steps, WiFi status, IP address

## Hardware

- Raspberry Pi Pico W
- 4–16 Solid State Relays (logic-level, 3.3V compatible)
- LED strips/lights (5–12V, powered via SSR)
- 220Ω resistors (one per GPIO)
- Optional: SSD1306 128×64 I2C OLED (GP6 SDA, GP7 SCL) – see schematic

See **SCHEMATIC.md** for wiring.

## Firmware

Use **MicroPython 1.22+** with **Bluetooth support** for Pico W:

1. Download: https://micropython.org/download/RPI_PICO_W/
2. Flash with `mpremote` or Thonny

## Installation

1. Flash MicroPython (with BLE) to Pico W
2. Copy all `.py` files to the Pico
3. Edit `config.py` – set `WIFI_SSID` and `WIFI_PASSWORD` for your network (or leave blank and use BLE on first boot)
4. Power on – self-test runs, then WiFi connects

## First-Time Setup (No WiFi Credentials)

1. Power on – lights self-test, then yellow blinks (connecting)
2. After 3 failed attempts – red blinks, then BLE starts
3. Open a BLE serial app (see **BLE WiFi Setup** below)
4. Connect to **StartLight-WiFi**
5. Send credentials (see formats below)
6. Pico saves credentials and reboots
7. After WiFi connects, Pico briefly advertises as **StartLight-IP** – reconnect within 30 sec to receive the IP address (e.g. `IP: http://192.168.1.10`)

---

## BLE WiFi Setup (Detailed)

### How BLE Advertising Works

The Pico W advertises as **StartLight-WiFi** using the **Nordic UART Service (NUS)**:

| Item | Value |
|------|-------|
| Advertised name | `StartLight-WiFi` |
| Service UUID | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| RX (write) | `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` |
| TX (notify) | `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` |

When in BLE mode (onboard LED: ON 2 sec, OFF 1 sec), the Pico acts as a BLE peripheral. You connect from your phone and write to the RX characteristic to send data.

### PIN Confirmation (with display)

If `BLE_PIN_ENABLED = True` in `config.py` and you have an OLED connected:

1. On entering BLE mode, the display shows a **6-digit PIN** (e.g. `123456`)
2. After connecting via nRF Connect, the Pico sends: `Enter PIN: 123456 (on display)`
3. **Type the PIN** and send it first
4. Pico replies `PIN OK. Send: SSID,password...`
5. Then send your WiFi credentials

Set `BLE_PIN_ENABLED = False` to skip PIN (e.g. if no display).

### BLE start (no WiFi)

When the Pico is in **BLE mode** (WiFi failed or no credentials), you can trigger the full start sequence from the phone without the web UI:

1. Connect to **StartLight-WiFi** (same Nordic UART service as credentials).
2. If PIN is enabled: enter the PIN first.
3. Send the text **`START`**, **`GO`**, or **`RUN`** (or JSON `{"cmd":"start"}`).
4. The same timing as **Settings** (red delay, random gap, yellows, green) is used.

**Note:** On Pico W, **WiFi and BLE cannot run at the same time** (one radio). While WiFi is connected and the web server is running, use **http://&lt;IP&gt;/** for START. Use BLE **START** only when the device is in BLE mode (no WiFi).

### How to Send WiFi SSID and Password via BLE

**Format 1 (simple):**
```
MyNetworkName,MyPassword
```
Comma separates SSID from password. No spaces unless your SSID/password have them.

**Format 2 (JSON, with optional country):**
```json
{"ssid":"MyNetworkName","password":"MyPassword","country":"RO"}
```

**Format 3 (simple + country):**
```
MyNetworkName,MyPassword,RO
```

**Examples:**
- `HomeWiFi,secret123`
- `HomeWiFi,secret123,RO` – also sets WiFi country to Romania
- `{"ssid":"HomeWiFi","password":"secret123","country":"RO"}`

### Step-by-Step: nRF Connect (Android/iOS)

1. Install **nRF Connect** from Play Store / App Store
2. Scan for devices – find **StartLight-WiFi**
3. Tap **Connect**
4. Expand the service `6E400001-...`
5. Tap the **down arrow** (write) on `6E400002-...` (RX)
6. If PIN is enabled: look at the OLED display, type the 6-digit PIN, tap **Send**. Wait for "PIN OK."
7. In the write box, type: `YourSSID,YourPassword` (or `YourSSID,YourPassword,RO`)
8. Tap **Send**
9. Pico replies "OK: ..." and reboots

### Step-by-Step: Serial Bluetooth Terminal (Android)

1. Install **Serial Bluetooth Terminal**
2. Menu → **Devices** → Scan
3. Connect to **StartLight-WiFi**
4. In the text input, type: `YourSSID,YourPassword`
5. Send (Enter or Send button)
6. Pico replies and reboots

### Step-by-Step: LightBlue (iOS)

1. Install **LightBlue**
2. Scan – find **StartLight-WiFi**
3. Connect
4. Find the characteristic with UUID `6E400002-...` (write)
5. Write value: type your `SSID,password` as UTF-8 text

## Web Interface

Once connected to WiFi:

- **http://&lt;Pico-IP&gt;/** – Remote control (START button)
- **http://&lt;Pico-IP&gt;/settings** – Configure lights, timing, WiFi

### Settings

| Setting | Description |
|---------|-------------|
| Red duration | How long red stays on (sec) |
| Random wait | Min/max between red and yellow (sec) |
| Yellow interval | Time between yellow lights |
| Green off delay | How long green stays on after GO |
| Start delay | Random (5–20s) or fixed countdown after button press |

## Start Sequence

1. Press **START** on web page
2. Countdown (random or fixed)
3. Red lights ON
4. Random wait (1–3 sec)
5. Yellow 1 → Yellow 2 → Green
6. Green = GO – lights off after 3 sec

## Boot Status (External Lights + Onboard LED)

| State | External | Onboard LED |
|-------|----------|-------------|
| WiFi connected | Green 5× | ON, blink 5×, then OFF |
| Connecting | Yellow | Blink every second |
| Not connected (retry) | Red 2× | Blink 3×, wait 3 sec |
| BLE awaiting credentials | Yellow | ON 2 sec, OFF 1 sec (repeat) |

## Storage (JSON files on device)

| File | Purpose |
|------|---------|
| `startlight_config.json` | Light settings (timing, delays) |
| `wifi_networks.json` | Known WiFi networks (SSID + password) |
| `wifi_country.json` | WiFi country code (from BLE or default RO) |
| `last_wifi.json` | Last successfully connected network |
| `wifi_creds.json` | Legacy single-network (auto-migrated) |

On boot, the device scans for WiFi. If the last successful network is in range, it connects to that first.

## File Structure

```
AGENTS.md        - Behavior contract for future changes
config.py        - Default settings, GPIO map
wifi_config.py   - WiFi credential storage (networks + last successful)
settings.py      - Light settings (startlight_config.json)
lights.py        - LED/GPIO control
webserver.py     - HTTP server
ble_uart.py      - BLE UART for credentials
ble_advertising.py - BLE helper
display.py       - Status display (OLED)
ssd1306.py       - SSD1306 I2C driver
main.py          - Entry point
boot.py          - Startup (minimal)
```

WiFi passwords and on-device JSON (`wifi_creds.json`, `wifi_networks.json`, `startlight_config.json`, and the other files in `.gitignore`) stay on the Pico. They are not part of this repository.

## GPIO Pinout (4 pins)

| Color    | GPIO |
|----------|------|
| Red      | GP2  |
| Yellow 1 | GP3  |
| Yellow 2 | GP4  |
| Green    | GP5  |

## License

MIT

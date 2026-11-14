# Deploy to Pico 2 W (or Pico W)

The preferred board is **Raspberry Pi Pico 2 W** (RP2350). The same `firmware/*.py` files also run on the original **Pico W** (RP2040). Flash the **matching** MicroPython UF2 for the board you hold — the UF2s are not interchangeable.

The Pico has little flash. Copy **only** MicroPython modules from `firmware/`. Never copy `docs/`, `AGENTS.md`, `README.md`, SVG, or local `.json` credential files.

## 1. Flash MicroPython

| Board | UF2 download | Notes |
|-------|--------------|--------|
| **Pico 2 W** (preferred) | [RPI_PICO2_W](https://micropython.org/download/RPI_PICO2_W/) | Use **1.26+** with BLE (latest stable recommended). Arm image, not RISC-V, unless you know you need RISC-V. |
| Pico W | [RPI_PICO_W](https://micropython.org/download/RPI_PICO_W/) | **1.22+** with Bluetooth |

Hold **BOOTSEL**, plug USB, copy the `.uf2` onto the mass-storage drive. The board reboots into MicroPython.

Do **not** install `RPI_PICO_W` firmware on a Pico 2 W, or `RPI_PICO2_W` on a Pico W.

## 2. Copy application files

Copy every `.py` file from `firmware/` to the **Pico root** (not into a `firmware/` folder on the device):

```text
mpremote cp firmware/*.py :
```

In Thonny: open each `firmware/*.py` and save it to the Pico.

## 3. Boot

Soft-reset or power-cycle. `boot.py` is empty; `main.py` starts the program. The serial log should show `[Board] Pico 2 W` or `[Board] Pico W`.

Imports are flat (`from lights import …`) because files sit at the Pico root after copy.

## Moving from Pico W → Pico 2 W

1. Flash **RPI_PICO2_W** MicroPython on the new board (empty flash — old WiFi JSON does not transfer automatically).
2. Copy the same `firmware/*.py` set.
3. Re-provision WiFi via BLE or the settings page (or copy JSON from the old board only if you intend to).
4. Wiring is unchanged: GP2–GP5 lamps, GP6/GP7 OLED, same active-low SSR drive. Drop-in pin headers.

WiFi and BLE still share one CYW43 radio on both boards — never run them at the same time.

## What stays on the PC

| Path | Why |
|------|-----|
| `docs/` | Schematic and this guide — too large / unused on device |
| `AGENTS.md`, root `README.md` | Agent and human docs |
| `*.json` WiFi / settings files | Created on the Pico; do not overwrite from a PC dump |

After first use the Pico creates its own `wifi_networks.json`, `startlight_config.json`, and related files. Leave those on the device.

Placeholder JSON shapes (for documentation only) are in [`examples/`](examples/). Do not commit real passwords; do not copy example files onto the Pico unless you rename them and fill in real values yourself.

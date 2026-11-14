# Deploy to Pico W

The Pico has little flash. Copy **only** MicroPython modules from `firmware/`. Never copy `docs/`, `AGENTS.md`, `README.md`, SVG, or local `.json` credential files.

## Steps

1. Flash [MicroPython for RPI_PICO_W](https://micropython.org/download/RPI_PICO_W/) with Bluetooth support.
2. Copy every `.py` file from `firmware/` to the **Pico root** (not into a `firmware/` folder on the device):

   ```text
   mpremote cp firmware/*.py :
   ```

   In Thonny: open each `firmware/*.py` and save it to the Pico.

3. Soft-reset or power-cycle. `boot.py` is empty; `main.py` starts the program.

Imports are flat (`from lights import …`) because files sit at the Pico root after copy.

## What stays on the PC

| Path | Why |
|------|-----|
| `docs/` | Schematic and this guide — too large / unused on device |
| `AGENTS.md`, root `README.md` | Agent and human docs |
| `*.json` WiFi / settings files | Created on the Pico; do not overwrite from a PC dump |

After first use the Pico creates its own `wifi_networks.json`, `startlight_config.json`, and related files. Leave those on the device.

Placeholder JSON shapes (for documentation only) are in [`examples/`](examples/). Do not commit real passwords; do not copy example files onto the Pico unless you rename them and fill in real values yourself.

# Documentation

Human and agent docs live here. **Do not copy this folder to the Pico.** Flash only the files in [`../firmware/`](../firmware/).

GitHub Pages is served from this folder (`index.html` + `schematic.svg`). Site: https://kovacsalexandrurobert.github.io/StartGate-RCDrift.ro/

| File | Audience |
|------|----------|
| [index.html](index.html) | Public schematic page (GitHub Pages) |
| [assets/startlight-logo.svg](assets/startlight-logo.svg) | Brand lockup (+ powered by rcdrift.ro) |
| [assets/startlight-logo-mark.svg](assets/startlight-logo-mark.svg) | Compact // mark + lamp dots |
| [assets/startlight-logo.jpg](assets/startlight-logo.jpg) | Raster lockup for social / previews |
| [schematic.svg](schematic.svg) | Wiring diagram embedded on the page |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Trunk-based workflow: feature branch → PR → `main` |
| [DEPLOY.md](DEPLOY.md) | Flash Pico 2 W / Pico W and copy `.py` only |
| [PICO_2W.md](PICO_2W.md) | Why paired cloud needs Pico 2 W (TLS/RAM) |
| [STARTLIGHT_CLOUD.md](STARTLIGHT_CLOUD.md) | Protocol 2 pair / poll / claim / events |
| [STARTLIGHT_SYNC_MINDMAP.md](STARTLIGHT_SYNC_MINDMAP.md) | Sync happy path + failure branches |
| [examples/](examples/) | Placeholder shapes for on-device JSON (no real passwords) |
| [SCHEMATIC.md](SCHEMATIC.md) | Wiring, GPIO, SSR, optional OLED |
| [../AGENTS.md](../AGENTS.md) | Behavior contract for AI agents |
| [../README.md](../README.md) | Setup, BLE apps, web UI overview |

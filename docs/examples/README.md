# On-device JSON examples

These files show the shape of runtime JSON the Pico creates. They are **not** deployed with `firmware/*.py`.

Real credentials live only on the Pico (or in gitignored copies on your PC). Never commit files named without `.example`.

| Example | Created by | Purpose |
|---------|------------|---------|
| `wifi_networks.json.example` | BLE / web settings / `save_credentials` | Known SSIDs and passwords |
| `wifi_creds.json.example` | Same (legacy single-network mirror) | Last saved SSID + password |
| `last_wifi.json.example` | Successful `STAT_GOT_IP` | Preferred SSID to try first |
| `wifi_country.json.example` | BLE country field / default `RO` | 2-letter ISO country for WLAN |
| `ble_pending_ip.json.example` | After BLE credential save | If `true`, advertise IP over BLE once |
| `startlight_config.json.example` | Web settings save | Lamp timing overrides |

## Manual use (optional)

Normally leave these alone — the firmware creates them. To seed a device by hand:

1. Copy an example, drop the `.example` suffix.
2. Replace placeholders with real values (passwords never go in git).
3. Copy that file to the **Pico root** only, not into this repo’s tracked tree.

Empty WiFi passwords are stored by some paths but `connect_wifi` skips networks with an empty password. Open networks are not supported.

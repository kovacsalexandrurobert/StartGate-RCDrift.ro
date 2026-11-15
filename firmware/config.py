"""
Start Light Configuration
Store settings and WiFi credentials
"""

# Default WiFi - edit these before first upload, or use BLE to configure
# Leave empty to use BLE on first boot
WIFI_SSID = ""
WIFI_PASSWORD = ""

# Network to search (leave empty to use WIFI_SSID)
PREFERRED_NETWORK = ""

# Light configuration - single set, wire multiple lights in parallel per color
# GPIO: Red, Yellow1, Yellow2, Green (all lights of same color share one SSR)
GPIO_PINS = [2, 3, 4, 5]  # GP2=Red, GP3=Yellow1, GP4=Yellow2, GP5=Green

# Sequence timing (seconds)
RED_DURATION = 1.0
RANDOM_WAIT_MIN = 1.0
RANDOM_WAIT_MAX = 3.0
YELLOW_INTERVAL = 0.5  # Between yellow lights
GREEN_AFTER_LAST_YELLOW = 0.5
GREEN_OFF_DELAY = 3.0

# Start button delay: 0 = random (5-20 sec), else fixed seconds
START_DELAY_MODE = 0  # 0=random, 1=fixed
START_DELAY_FIXED = 5  # Used when START_DELAY_MODE=1
START_DELAY_RANDOM_MIN = 5
START_DELAY_RANDOM_MAX = 20

# Config file path
CONFIG_FILE = "startlight_config.json"

# WiFi country code (set before WLAN init on Pico W / Pico 2 W)
# Default for Romania; can be overridden via BLE on first init
# Use 2-letter ISO code: "RO", "US", "GB", "DE", etc.
WIFI_COUNTRY = "RO"

# Set False if wlan.scan() hangs on your board (connect will still work)
WIFI_SCAN_ENABLED = False

# Optional status display (SSD1306 128x64 I2C OLED)
DISPLAY_ENABLED = True
DISPLAY_SDA = 6   # GP6 - I2C1 SDA
DISPLAY_SCL = 7   # GP7 - I2C1 SCL

# BLE PIN confirmation: show 6-digit PIN on display, user must enter before sending credentials
BLE_PIN_ENABLED = True

# Optional rcdrift.ro cloud (off until paired — see cloud.py / cloud_creds.json)
CLOUD_API_BASE = "https://staging.rcdrift.ro"

# Anonymous IR finish beam (phase 4). Set FINISH_SENSOR_ENABLED True when wired.
FINISH_SENSOR_ENABLED = False
FINISH_SENSOR_PIN = 10  # GP10 active-low break-beam
FINISH_MIN_RUN_S = 8.0
FINISH_DEBOUNCE_MS = 40

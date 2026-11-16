"""
BLE UART for WiFi credential input when WiFi connection fails.
Use any BLE serial app (nRF Connect, Serial Bluetooth Terminal, etc.)
With BLE_PIN_ENABLED: enter 6-digit PIN (shown on display) first, then credentials.
Send: SSID,password  or  SSID,password,RO  or  {"ssid":"...","password":"...","country":"RO"}
"""

import bluetooth
from ble_advertising import advertising_payload
from micropython import const

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_FLAG_WRITE = const(0x0008)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_NOTIFY = const(0x0010)
_ADV_APPEARANCE_GENERIC_COMPUTER = const(128)

_UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_TX = (bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_NOTIFY)
# RX: support both write types (many apps use Write without response)
_UART_RX = (bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE)
_UART_SERVICE = (_UART_UUID, (_UART_TX, _UART_RX))


class BLEUART:
    def __init__(self, ble, name="StartLight-Cfg", rxbuf=256, on_connect=None):
        self._ble = ble
        self._ble.active(True)
        self._ble.irq(self._irq)
        ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services((_UART_SERVICE,))
        self._ble.gatts_set_buffer(self._rx_handle, rxbuf, True)
        self._connections = set()
        self._rx_buffer = bytearray()
        self._handler = None
        self._on_connect = on_connect
        self._payload = advertising_payload(name=name, appearance=_ADV_APPEARANCE_GENERIC_COMPUTER)
        self._advertise()

    def irq(self, handler):
        self._handler = handler

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self._connections.add(conn_handle)
            print("[BLE] Client connected")
            if self._on_connect:
                try:
                    self._on_connect()
                except Exception:
                    pass
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            if conn_handle in self._connections:
                self._connections.remove(conn_handle)
            print("[BLE] Client disconnected")
            self._advertise()
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if conn_handle in self._connections and value_handle == self._rx_handle:
                self._rx_buffer += self._ble.gatts_read(self._rx_handle)
                if self._handler:
                    self._handler()

    def any(self):
        return len(self._rx_buffer)

    def read(self, sz=None):
        if sz is None:
            sz = len(self._rx_buffer)
        result = self._rx_buffer[0:sz]
        self._rx_buffer = self._rx_buffer[sz:]
        return result

    def write(self, data):
        if isinstance(data, str):
            data = data.encode()
        for conn_handle in self._connections:
            self._ble.gatts_notify(conn_handle, self._tx_handle, data)

    def close(self):
        self._ble.active(False)

    def _advertise(self, interval_us=500000):
        self._ble.gap_advertise(interval_us, adv_data=self._payload)


def _gen_pin():
    """Generate random 6-digit PIN."""
    import os
    r = os.urandom(2)
    return (r[0] * 256 + r[1]) % 1000000


def _run_start_sequence(uart, lights, settings):
    """Run the full start light sequence (same as web /start)."""
    from cloud import is_paired
    if is_paired():
        uart.write("RCDrift paired: reconnect WiFi before START.\r\n")
        return
    from settings import get_start_delay
    delay = get_start_delay(settings)
    uart.write("Sequence running...\r\n")
    try:
        from display import show_lines
        show_lines("START!", "Sequence...", "", "")
    except Exception:
        pass
    lights.run_start_sequence(
        start_delay=delay,
        red_dur=settings["red_duration"],
        rand_min=settings["random_wait_min"],
        rand_max=settings["random_wait_max"],
        yellow_interval=settings["yellow_interval"],
        green_off_delay=settings["green_off_delay"],
    )
    uart.write("Done. Send START, or SSID,password\r\n")


def wait_for_credentials(timeout_sec=300, tick_callback=None, lights=None, settings=None):
    """
    Run BLE UART and wait for WiFi credentials.
    If BLE_PIN_ENABLED: user must enter the 6-digit PIN (shown on display) first.
    After PIN: send START or GO to run the start sequence (needs lights + settings).
    Returns (ssid, password) or (None, None) on timeout.
    tick_callback(elapsed_ms) called every 100ms for LED status (e.g. BLE: ON 2s, OFF 1s).
    """
    import json
    import time
    from wifi_config import save_credentials

    try:
        from config import BLE_PIN_ENABLED
    except Exception:
        BLE_PIN_ENABLED = True

    pin = _gen_pin() if BLE_PIN_ENABLED else None
    pin_confirmed = [False]  # Use list for closure

    print("[BLE] Initializing BLE UART...")
    if pin is not None:
        print("[BLE] PIN: %06d (enter via BLE to continue)" % pin)
        try:
            from display import reset_oled_cache, show_ble_pin
            # Fresh I2C after wlan.active(False) — stale cache can leave wrong image
            reset_oled_cache()
            show_ble_pin(pin)
        except Exception as e:
            print("[Display] show_ble_pin:", e)

    received = [None]  # Use list to allow closure to modify

    def on_rx():
        try:
            data = uart.read().decode().strip()
            if not data:
                return
            # PIN check first (if enabled)
            if pin is not None and not pin_confirmed[0]:
                if data == str(pin) or data == "%06d" % pin:
                    pin_confirmed[0] = True
                    uart.write("PIN OK. Send SSID,password or START\r\n")
                    try:
                        from display import show_ble_waiting
                        show_ble_waiting()
                    except Exception:
                        pass
                else:
                    uart.write("Wrong PIN. Try again.\r\n")
                return
            # START / GO — run sequence when WiFi is down (after PIN if used)
            up = data.strip().upper()
            if up in ("START", "GO", "RUN"):
                if lights is not None and settings is not None:
                    try:
                        _run_start_sequence(uart, lights, settings)
                    except Exception as e:
                        uart.write("ERR: " + str(e) + "\r\n")
                else:
                    uart.write("ERR: START unavailable\r\n")
                return
            uart.write("OK: " + data[:20] + "...\r\n")
            # Try JSON first: {"ssid":"...","password":"...","country":"RO"} or {"cmd":"start"}
            if data.startswith("{"):
                d = json.loads(data)
                cmd = (d.get("cmd") or "").strip().lower()
                if cmd in ("start", "go"):
                    if lights is not None and settings is not None:
                        try:
                            _run_start_sequence(uart, lights, settings)
                        except Exception as e:
                            uart.write("ERR: " + str(e) + "\r\n")
                    else:
                        uart.write("ERR: START unavailable\r\n")
                    return
                received[0] = (d.get("ssid", ""), d.get("password", ""))
                country = d.get("country", "").strip()
                if country and len(country) == 2:
                    from wifi_config import save_wifi_country
                    save_wifi_country(country)
            else:
                # Format: SSID,password  or  SSID,password,country
                parts = data.split(",", 2)
                if len(parts) >= 2:
                    received[0] = (parts[0].strip(), parts[1].strip())
                    if len(parts) >= 3 and len(parts[2].strip()) == 2:
                        from wifi_config import save_wifi_country
                        save_wifi_country(parts[2].strip())
        except Exception as e:
            uart.write("ERR: " + str(e) + "\r\n")

    def on_connect():
        if pin is not None:
            uart.write("Enter PIN: %06d (on display)\r\n" % pin)
        else:
            uart.write("SSID,password or START\r\n")

    ble = bluetooth.BLE()
    uart = BLEUART(ble, name="StartLight-WiFi", on_connect=on_connect)
    uart.irq(handler=on_rx)

    if pin is not None:
        try:
            time.sleep_ms(80)
            from display import show_ble_pin
            show_ble_pin(pin)
        except Exception as e:
            print("[Display] PIN refresh after BLE:", e)
    else:
        try:
            from display import show_ble_waiting
            show_ble_waiting()
        except Exception:
            pass

    try:
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_sec * 1000:
            elapsed = time.ticks_diff(time.ticks_ms(), start)
            if tick_callback:
                tick_callback(elapsed)
            if received[0] is not None:
                ssid, pwd = received[0]
                if ssid:
                    print("[BLE] Received: SSID='%s'" % ssid[:20])
                    try:
                        from display import show_ble_received
                        show_ble_received()
                    except Exception:
                        pass
                    save_credentials(ssid, pwd)
                    from wifi_config import set_pending_ip_via_ble
                    set_pending_ip_via_ble(True)  # Send IP via BLE after WiFi connects
                    uart.write("Saved! Rebooting...\r\n")
                    uart.close()
                    return ssid, pwd
            time.sleep_ms(100)

        uart.close()
        print("[BLE] Credential timeout")
        return None, None
    except KeyboardInterrupt:
        uart.close()
        print("[BLE] Interrupted")
        raise


def send_ip_via_ble(ip, timeout_sec=30):
    """
    Briefly enable BLE, wait for connection, send IP address, then close.
    Call after WiFi connects if credentials were set via BLE.
    WiFi must be disabled before calling; caller re-enables WiFi after.
    """
    import time

    print("[BLE] Advertising as 'StartLight-IP' - connect within %d sec to get IP" % timeout_sec)
    ble = bluetooth.BLE()
    uart = BLEUART(ble, name="StartLight-IP")

    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < timeout_sec * 1000:
        if len(uart._connections) > 0:
            print("[BLE] Client connected, sending IP...")
            uart.write("IP: http://%s\r\n" % ip)
            uart.write("Open in browser for Start Light control.\r\n")
            time.sleep(3)  # Give user time to read
            print("[BLE] IP sent to connected device")
            break
        time.sleep_ms(200)
    else:
        print("[BLE] No connection within timeout")

    uart.close()

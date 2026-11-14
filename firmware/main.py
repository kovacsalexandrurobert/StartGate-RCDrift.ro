"""
Start Light - Wireless Remote Controlled Race Start System
Raspberry Pi Pico 2 W (preferred) or Pico W - MicroPython

Boot sequence:
1. Self-test: cycle all light sets
2. Try WiFi connect
   - Success: green blink 5x
   - Connecting: yellow blink
   - Fail: red blink 2x, 3s delay, retry (or BLE for credentials)
3. If WiFi fails repeatedly: enable BLE, wait for credentials
4. Web server: settings + remote control

Flash board-matched UF2: RPI_PICO2_W or RPI_PICO_W. Do not flash Pico W
firmware onto a Pico 2 W (or the reverse). Application .py files are shared.
"""

import time
import machine
import network

try:
    from board import log_boot
    log_boot()
except Exception as e:
    print("[Board] id failed:", e)

# Set country before WLAN init (helps CYW43 WiFi on some firmware)
# Uses value from BLE (wifi_country.json) or config default
try:
    from wifi_config import get_wifi_country
    WIFI_COUNTRY = get_wifi_country()
    try:
        import rp2
        rp2.country(WIFI_COUNTRY)
    except Exception:
        pass
    try:
        network.country(WIFI_COUNTRY)
    except Exception:
        pass
    print("[WiFi] Country: %s" % WIFI_COUNTRY)
except Exception as e:
    print("[WiFi] Country init:", e)

from lights import LightController
from settings import load
from wifi_config import (
    load_credentials,
    has_credentials,
    get_pending_ip_via_ble,
    set_pending_ip_via_ble,
    get_networks_to_try,
    record_successful_connection,
)
from webserver import (
    run_server,
    is_start_requested,
    get_start_delay_value,
    get_start_plan,
    clear_start_requested,
)
from onboard_led import (
    status_not_connected,
    status_connecting_tick,
    status_ble_tick,
    status_connected,
    off as led_off,
)
from display import (
    show_boot,
    show_wifi_connecting,
    show_wifi_connected,
    show_wifi_failed,
    show_ip,
)

# WiFi config
WIFI_TIMEOUT_MS = 15000
WIFI_RETRY_BEFORE_BLE = 3
BOOT_BLINK_INTERVAL = 0.25


def connect_wifi(tick_callback=None):
    """Connect to WiFi. Tries last successful first if in range. Returns True on success."""
    print("[WiFi] Activating WLAN...")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    time.sleep(0.5)  # Let CYW43 chip initialize

    # Scan for available networks (can hang on some builds - set WIFI_SCAN_ENABLED=False in config)
    scan_results = None
    try:
        from config import WIFI_SCAN_ENABLED
    except Exception:
        WIFI_SCAN_ENABLED = False
    try:
        if WIFI_SCAN_ENABLED:
            print("[WiFi] Scanning...")
            scan_results = wlan.scan()
            print("[WiFi] Scan: %d networks found" % len(scan_results))
    except Exception as e:
        print("[WiFi] Scan failed:", e)

    networks = get_networks_to_try(scan_results)
    print("[WiFi] Networks to try: %d" % len(networks))
    if not networks:
        print("[WiFi] No credentials stored")
        return False

    for ssid, password in networks:
        if not ssid or not password:
            continue
        print("[WiFi] Connecting to '%s'..." % (ssid[:20] if ssid else ""))
        show_wifi_connecting(ssid[:20] if ssid else "")
        wlan.connect(ssid, password)

        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < WIFI_TIMEOUT_MS:
            elapsed = time.ticks_diff(time.ticks_ms(), start)
            if tick_callback:
                tick_callback(elapsed)
            status = wlan.status()
            if status == network.STAT_GOT_IP:
                print("[WiFi] Connected to '%s'!" % ssid[:20])
                record_successful_connection(ssid)
                show_wifi_connected(ssid[:20] if ssid else "")
                return True
            if status == network.STAT_CONNECT_FAIL or status == network.STAT_NO_AP_FOUND:
                print("[WiFi] '%s' failed" % ssid[:20])
                break
            time.sleep_ms(100)
        else:
            print("[WiFi] '%s' timeout" % ssid[:20])

    print("[WiFi] All networks failed")
    show_wifi_failed()
    return False


def boot_self_test(lights):
    """Run self-test: cycle through all configured light sets"""
    print("[Boot] Self-test: cycling lights...")
    show_boot()
    lights.run_self_test()
    print("[Boot] Self-test done")


def boot_wifi_success(lights):
    """External: green 5x. Onboard LED: on, blink 5x, leave off"""
    print("[Boot] WiFi OK - green blink")
    lights.blink_status("green", 5, BOOT_BLINK_INTERVAL)
    status_connected()


def boot_wifi_connecting(lights):
    """External: yellow once. Onboard LED: blink every second (during connect_wifi)"""
    lights.blink_status("yellow", 1, BOOT_BLINK_INTERVAL)


def boot_wifi_error(lights):
    """External: red 2x. Onboard LED: blink 3x, wait 3 sec"""
    print("[WiFi] Failed - red blink, retrying in 3 sec...")
    lights.blink_status("red", 2, BOOT_BLINK_INTERVAL)
    status_not_connected()


def run_ble_credential_mode(lights, settings):
    """WiFi failed after 3 tries - enable BLE, wait for credentials or BLE START command."""
    print("[BLE] WiFi failed 3x - enabling BLE for new credentials...")
    lights.blink_status("red", 2, 0.3)
    time.sleep(1)
    # Deactivate WiFi before BLE (one CYW43 radio — Pico W and Pico 2 W)
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(False)
        time.sleep(0.5)
    except Exception:
        pass

    print("[BLE] Advertising as 'StartLight-WiFi' - connect and send: SSID,password")
    # Display: PIN + prompts are handled inside wait_for_credentials (do not call show_ble_waiting here — it would overwrite the PIN screen)
    try:
        from ble_uart import wait_for_credentials
        lights.blink_status("yellow", 1, 0.5)  # Indicate BLE mode
        ssid, pwd = wait_for_credentials(
            timeout_sec=300,
            tick_callback=status_ble_tick,
            lights=lights,
            settings=settings,
        )
        if ssid:
            print("[BLE] Credentials saved! Rebooting...")
            lights.blink_status("green", 3, 0.2)  # Success
            time.sleep(1)
            machine.reset()
        else:
            print("[BLE] Timeout - retrying WiFi...")
    except Exception as e:
        print("[BLE] Error:", e)
        lights.blink_status("red", 5, 0.2)  # Error
    # Fall through - will retry WiFi on next loop


def _cleanup(lights=None):
    """Failsafe cleanup: lights off, LED off, WiFi off. Call on KeyboardInterrupt."""
    print("[Cleanup] Stopping...")
    try:
        if lights:
            lights.all_off()
            print("[Cleanup] Lights off")
    except Exception as e:
        print("[Cleanup] Lights off failed:", e)
    try:
        led_off()
        print("[Cleanup] Onboard LED off")
    except Exception as e:
        print("[Cleanup] LED off failed:", e)
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(False)
        print("[Cleanup] WiFi off")
    except Exception as e:
        print("[Cleanup] WiFi off failed:", e)


def main():
    print("[Boot] ========== Start Light boot ==========")
    print("[Boot] Loading settings...")
    settings = load()
    print("[Boot] Initializing lights...")
    lights = LightController()

    # 1. Self-test
    print("[Boot] Step 1: Self-test")
    boot_self_test(lights)
    time.sleep(0.5)

    # 2. WiFi connection with status indication
    print("[Boot] Step 2: WiFi connection")
    wifi_ok = False
    retry_count = 0

    try:
        while not wifi_ok:
            if has_credentials():
                print("[WiFi] Attempt %d/%d" % (retry_count + 1, WIFI_RETRY_BEFORE_BLE))
                boot_wifi_connecting(lights)
                wifi_ok = connect_wifi(tick_callback=status_connecting_tick)
                if wifi_ok:
                    boot_wifi_success(lights)
                    break

            retry_count += 1
            # After 3 failed tries with credentials, or no credentials: enable BLE
            if retry_count >= WIFI_RETRY_BEFORE_BLE and has_credentials():
                boot_wifi_error(lights)
            if not has_credentials() or retry_count >= WIFI_RETRY_BEFORE_BLE:
                print("[Boot] No credentials or 3 failures - entering BLE mode")
                run_ble_credential_mode(lights, settings)
                retry_count = 0
                time.sleep(2)
    except KeyboardInterrupt:
        _cleanup(lights)
        print("[Boot] Stopped (Ctrl+C). Ready for upload.")
        raise

    # 3. If credentials came via BLE: briefly send IP over BLE
    print("[Boot] Step 3: Post-connect setup")
    ip = "0.0.0.0"
    try:
        sta = network.WLAN(network.STA_IF)
        if sta.isconnected():
            ip = sta.ifconfig()[0]
    except Exception:
        pass

    if get_pending_ip_via_ble() and ip != "0.0.0.0":
        print("[BLE] Pending IP via BLE - disabling WiFi, sending IP...")
        try:
            wlan = network.WLAN(network.STA_IF)
            wlan.active(False)
            time.sleep(0.5)
            from ble_uart import send_ip_via_ble
            send_ip_via_ble(ip, timeout_sec=30)
            set_pending_ip_via_ble(False)
        except Exception as e:
            print("[BLE] IP send failed:", e)
        print("[BLE] Re-enabling WiFi...")
        try:
            ssid, pwd = load_credentials()
            if ssid and pwd:
                wlan = network.WLAN(network.STA_IF)
                wlan.active(True)
                wlan.connect(ssid, pwd)
                for _ in range(50):
                    if wlan.status() == network.STAT_GOT_IP:
                        ip = wlan.ifconfig()[0]
                        print("[WiFi] Reconnected")
                        break
                    time.sleep_ms(200)
        except Exception as e:
            print("[WiFi] Reconnect failed:", e)
    else:
        print("[Boot] No pending BLE IP (or not connected)")

    print("[Boot] ========== Ready ==========")
    print("[OK] Start Light ready at http://" + ip)
    show_ip(ip)
    lights.all_off()
    led_off()  # Ensure onboard LED off when running

    try:
        while True:
            if is_start_requested():
                print("[Start] Sequence triggered")
                plan = get_start_plan()
                clear_start_requested()
                try:
                    if plan:
                        lights.run_start_sequence(
                            start_delay=plan["delay"],
                            red_dur=plan["red_duration"],
                            rand_min=settings["random_wait_min"],
                            rand_max=settings["random_wait_max"],
                            yellow_interval=plan["yellow_interval"],
                            green_off_delay=plan["green_off_delay"],
                            rand_wait=plan["random_wait"],
                        )
                    else:
                        delay = get_start_delay_value()
                        lights.run_start_sequence(
                            start_delay=delay,
                            red_dur=settings["red_duration"],
                            rand_min=settings["random_wait_min"],
                            rand_max=settings["random_wait_max"],
                            yellow_interval=settings["yellow_interval"],
                            green_off_delay=settings["green_off_delay"],
                        )
                except Exception as e:
                    print("[Start] Sequence error:", e)
                finally:
                    # HTTP was blocked during the sequence; ensure lamps are dark
                    # before accepting the next browser request.
                    try:
                        lights.all_off()
                    except Exception:
                        pass

            run_server(settings, lights)
            time.sleep_ms(50)
    except KeyboardInterrupt:
        _cleanup(lights)
        print("Stopped (Ctrl+C). Ready for upload.")
        raise


if __name__ == "__main__":
    print("")
    print("=== Start Light - MicroPython ===")
    try:
        main()
    except KeyboardInterrupt:
        _cleanup(None)
        print("[Boot] Stopped (Ctrl+C). Ready for upload.")
        raise

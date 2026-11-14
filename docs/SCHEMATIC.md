# Start Light System - Wiring Schematic

## Overview

Target board: **Raspberry Pi Pico 2 W** (RP2350) or original **Pico W** (RP2040). User GPIO and power pins used here are the same on both.

Single set of 4 GPIO pins drives all lights. Wire multiple light sets in **parallel** per color—each color shares one SSR. All red lights connect to SSR1, all yellow1 to SSR2, etc.

---

## GPIO Pin Assignment (4 pins total)

| Color    | GPIO | SSR  | Connects to                    |
|----------|------|------|---------------------------------|
| Red      | GP2  | SSR1 | All red lights (parallel)       |
| Yellow 1 | GP3  | SSR2 | All first yellow lights        |
| Yellow 2 | GP4  | SSR3 | All second yellow lights       |
| Green    | GP5  | SSR4 | All green lights               |

**Note:** Active-LOW: GPIO LOW = Light ON, GPIO HIGH = Light OFF

---

## Circuit Diagram (Per Channel) - Active-LOW

```
    3.3V                    Pico W
       │                        │
   ┌───┴───┐                    │
   │ 220Ω  │                    │  GPIO (LOW = SSR ON)
   └───┬───┘                    │
       │                        │
       └────────── SSR Input ───┘
                  (optocoupler)
                       │
                  ┌────┴────┐
                  │  SSR    │
                  │ Output  │
                  └────┬────┘
                       │
              ┌────────┴────────┐
              │                 │
          [5-12V]           [LED Strip]
              │                 │
           GND ────────────────┘
```

---

## Full Wiring Table

| Pico / Pico 2 W pin | GPIO | Function | Connect To |
|------------|------|----------|------------|
| Pin 4      | GP2  | Red      | SSR 1 Input (via 220R) |
| Pin 5      | GP3  | Yellow 1 | SSR 2 Input (via 220R) |
| Pin 6      | GP4  | Yellow 2 | SSR 3 Input (via 220R) |
| Pin 7      | GP5  | Green    | SSR 4 Input (via 220R) |
| Pin 9      | GP6  | I2C SDA  | OLED Display SDA |
| Pin 10     | GP7  | I2C SCL  | OLED Display SCL |
| Pin 36     | 3V3  | 3.3V out | SSR control + Display VCC |
| Pin 38     | GND  | Ground   | Common GND (see below) |
| Pin 40     | VBUS | 5V in    | 5V DC power (USB or adapter) |

## Power and GND

**Pico / Pico 2 W power (5V):**
- Connect 5V DC to **VBUS (pin 40)** and GND to **GND (pin 38)**
- Use USB cable, or 5V adapter (2.5mm barrel, or screw terminal)

**Common GND:**
- Tie together: Pico GND (pin 38), 5V supply GND, and LED supply GND
- All grounds must share a common reference

---

## SSR Requirements

- **Type:** Logic-level Solid State Relay (3.3V compatible)
- **Input:** Optocoupler LED, typically 5-20mA
- **Output:** DC switching capable of 5-12V at your LED current
- **Example:** Fotek SSR-25DA, or similar DC output SSR modules

### Resistor Calculation
- For 3.3V GPIO and ~10mA LED current: R = (3.3 - 1.2) / 0.01 ≈ **220Ω**
- Use 220Ω - 330Ω for safety margin

---

## LED Power Supply

- **Voltage:** 5V to 12V DC (match your LED strips/lights)
- **Current:** Ensure supply can handle all lights on simultaneously
- **Connection:** Supply + → LED anode, Supply - → SSR output common

---

## Parallel Wiring (Multiple Light Sets)

Wire all lights of the same color in parallel to one SSR:

```
    Pico W                    SSR Output → All lights of that color
    GP2 ──[220Ω]── SSR1 ────── Red (LED1, LED2, ... in parallel)
    GP3 ──[220Ω]── SSR2 ────── Yellow1 (all)
    GP4 ──[220Ω]── SSR3 ────── Yellow2 (all)
    GP5 ──[220Ω]── SSR4 ────── Green (all)
    GND ───────────────────── Power supply GND
```

---

---

## Mini Display (Optional)

I2C OLED (e.g. SSD1306 128×64) shows status during boot and runtime:

- **BLE steps** – Credential mode, waiting for SSID/password
- **WiFi status** – Connecting, connected, failed
- **IP address** – Assigned IP when connected

| Display Pin | Connect To |
|-------------|------------|
| VCC         | Pico 3V3 (pin 36) |
| GND         | Common GND |
| SDA         | Pico GP6 (pin 9) – I2C1 SDA |
| SCL         | Pico GP7 (pin 10) – I2C1 SCL |

**Display type:** SSD1306 128×64 I2C OLED (0x3C or 0x3D address)

---

## Important Notes

1. **Polarity:** Verify your SSR - some are active LOW (inverted logic)
2. **Isolation:** SSRs provide galvanic isolation between Pico and LED power
3. **Heat:** Mount SSRs on heatsink if switching high currents
4. **Testing:** Test with one light before connecting multiple in parallel
5. **Current:** Ensure each SSR and power supply can handle total current of all lights on that color
6. **Display:** Optional; omit display wiring if not used

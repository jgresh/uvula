# uvula

A small UV light integrator for cyanotype and other alternative-process sun printing. Dial in a target UV dose, walk away, and let it tell you when your print is done — regardless of clouds, time of day, or season.

Inspired by [Wagner Lungov's excellent piece on UV-controlled sun printing](https://www.alternativephotography.com/uv-printing-using-sunlight-with-total-control/) on Alternative Photography.

---

## The idea

UV light is not consistent. A morning session might need three times longer than an afternoon one, and a partly cloudy day is just guesswork. Instead of timing your exposures, *uvula* measures accumulated UV dose, the actual photons hitting your paper, and signals when you've reached your target.

Every second, it reads raw UV counts from a sensor, adds them to a running total, and estimates how much time is left based on current light levels. When the total hits your target: three long beeps. Done. Then it logs the whole session to a CSV file on the device so you can correlate readings with your actual print results over time.

---

## Hardware

| Part | Notes |
|------|-------|
| [Raspberry Pi RP2040](https://www.adafruit.com/product/5525) (Pimoroni Pico recommended) | Any RP2040 board works; use Pico W for future WiFi logging |
| [Adafruit LTR390 UV/Ambient Light Sensor](https://www.adafruit.com/product/4831) | I2C breakout, address 0x53 |
| [SSD1306 128×64 OLED Display](https://www.adafruit.com/product/326) | I2C breakout, address 0x3C |
| [4×4 Matrix Keypad](https://www.adafruit.com/product/3844) | |
| Passive buzzer | Generic 5V passive buzzer |
| 5V USB battery pack | Anything with a USB-A port |

---

## Wiring

```
RP2040          LTR390 / SSD1306 (shared I2C bus)
──────          ──────────────────────────────────
GP8  (SDA) ─── SDA
GP9  (SCL) ─── SCL
3.3V       ─── VCC
GND        ─── GND

RP2040          4×4 Keypad
──────          ──────────
GP26 ─── Row 0      GP19 ─── Col 0
GP22 ─── Row 1      GP18 ─── Col 1
GP21 ─── Row 2      GP17 ─── Col 2
GP20 ─── Row 3      GP16 ─── Col 3

RP2040          Buzzer
──────          ──────
GP6  ─── (+)
GND  ─── (−)
```

Both the LTR390 and the SSD1306 share the same I2C bus on GP8/GP9. The LTR390 uses address 0x53 by default; the display uses 0x3C. They coexist without any extra configuration.

---

## Installation

### 1. Flash CircuitPython

Hold the BOOTSEL button while connecting USB — the board appears as a drive called **RPI-RP2**. Download the [latest CircuitPython UF2 for your board](https://circuitpython.org/downloads) and drag it onto that drive. The board reboots as **CIRCUITPY**.

### 2. Install libraries

Download the [Adafruit CircuitPython Bundle](https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases) that matches your CircuitPython version. Copy these items from the bundle's `lib/` folder into the `lib/` folder on your CIRCUITPY drive:

```
adafruit_ltr390.mpy
adafruit_displayio_ssd1306.mpy
adafruit_display_text/
adafruit_bitmap_font/
adafruit_bus_device/
adafruit_register/
adafruit_matrixkeypad.mpy
asyncio/
```

The `lib/` directory is not in this repo — you copy it locally from the Adafruit bundle and it lives only on your device.

### 3. Copy project files

Copy these files to the root of the CIRCUITPY drive:

```
boot.py
code.py
settings.toml
Helvetica-Bold-16.bdf
```

### 4. Edit settings.toml

Open `settings.toml` and adjust to taste:

```toml
UVULA_TARGET_DEFAULT = 1000   # starting target UV dose (tune via test strips)
UVULA_BUZZER_ENABLED = 1      # 1 = on, 0 = silent
UVULA_LOG_ENABLED    = 1      # 1 = log sessions to CSV, 0 = skip
```

---

## The boot.py tradeoff

`boot.py` remounts the filesystem as writable so the device can log sessions. **This means the CIRCUITPY drive will not appear as an editable USB drive while it's active.** You won't be able to drag files onto it.

This is the most common stumbling block in CircuitPython data logging projects. Here's how to manage it:

**To edit files on the device:**
1. Connect USB and open a serial console (Mu editor works well; or `screen /dev/tty.usbmodem* 115200` in Terminal)
2. In `boot.py`, comment out the `storage.remount(...)` line
3. Save the file via serial and reboot — the CIRCUITPY drive reappears as writable
4. Make your edits, then re-enable `boot.py` when done

**To retrieve the log file without disabling boot.py**, see [Retrieving log data](#retrieving-log-data) below.

The tradeoff is intentional and unavoidable — CircuitPython can either let the computer write to the drive over USB *or* let the device write to it internally, but not both at the same time.

---

## Using the device

### Keypad layout

```
1  2  3  A
4  5  6  B
7  8  9  C
*  0  #  D
```

| Key | Function |
|-----|----------|
| 0–9 | Enter target UV dose |
| `#` | Confirm target and start exposure |
| `*` | Backspace |
| `D` | Clear to zero |
| Any key | Cancel running exposure / advance from summary screen |

### What you'll see

**State 1 — entering target:**
```
[live UV]
[target]
```
Top-left shows the live UV reading so you can get a sense of current light levels while typing. Bottom-left shows the target you're building.

**State 2 — exposure running:**
```
[cumulative]   [estimate]
[elapsed s]
```
Top-left: accumulated UV dose so far. Bottom-left: elapsed seconds. Top-right: estimated seconds remaining (based on current light level — updates every second).

**State 3 — done:**
```
DONE
[final total]
```
Press any key to return to target entry.

---

## Retrieving log data

The log file lives at `/session_log.csv` on the device. Each row is one second of exposure:

```
session_id,timestamp_s,uvs_reading,cumulative_uvs,elapsed_s,estimate_remaining
```

A `SUMMARY` row is appended at the end of each session:

```
SUMMARY,<session_id>,<completed|aborted>,<peak_uvs>,<min_uvs>,<elapsed_s>,<cumulative_uvs>
```

**Easiest retrieval method:**
1. Power off the device
2. Temporarily comment out the `storage.remount()` line in `boot.py`
3. Reboot — CIRCUITPY drive appears
4. Copy `session_log.csv` to your computer
5. Re-enable `boot.py` logging

**Via serial/REPL** (without rebooting):
Connect to the serial console and use:
```python
f = open('/session_log.csv')
print(f.read())
f.close()
```
Then copy-paste from the terminal.

---

## About the UV readings

The LTR390's `.uvs` property returns a raw UV count, not a UV index. This is intentional. Raw counts are reproducible, sensor-specific, and directly proportional to the dose your paper is receiving. Your target value will be specific to your sensor, your process, and your paper — you'll arrive at it by running a few test strips and comparing the accumulated counts at correct exposure. After that, the numbers become meaningful fast.

---

## WiFi logging (future / RP2040W only)

`wifi_logger.py` is a stub for a planned feature: the device hosts a local web page showing live UV readings and a progress bar, viewable from your phone while printing. Not implemented yet. See the stub for implementation notes. Requires a Pico W or other RP2040 board with WiFi.

---

## Library dependencies

```
adafruit_ltr390
adafruit_displayio_ssd1306
adafruit_display_text
adafruit_bitmap_font
adafruit_bus_device
adafruit_register
adafruit_matrixkeypad
asyncio (CircuitPython bundle)
```

All from the standard [Adafruit CircuitPython Bundle](https://github.com/adafruit/Adafruit_CircuitPython_Bundle).

---

*Built to accompany an article for [alternativephotography.com](https://www.alternativephotography.com/). The original inspiration: Wagner Lungov's [UV-controlled sun printing with total control](https://www.alternativephotography.com/uv-printing-using-sunlight-with-total-control/).*

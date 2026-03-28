"""
uvula — UV light integrator for cyanotype and alt-process sun printing.

Reads raw UV counts from an Adafruit LTR390 sensor once per second,
accumulates them toward a user-set target dose, sounds a buzzer when done,
and optionally logs each session to /session_log.csv on the CIRCUITPY drive.

Hardware:
  - RP2040 (Pimoroni Pico or similar)
  - Adafruit LTR390 UV sensor     I2C: SDA=GP8, SCL=GP9
  - SSD1306 OLED 128x64           I2C: addr 0x3C
  - 4x4 matrix keypad
  - Passive buzzer                 GP6
"""

import board
import busio
import time
import rtc
import os
import json
import displayio
import digitalio
import adafruit_displayio_ssd1306
import keypad
import asyncio
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font

# ---------------------------------------------------------------------------
# Pin assignments
# ---------------------------------------------------------------------------
PIN_SDA     = board.GP8
PIN_SCL     = board.GP9
PIN_BUZZER  = board.GP6
PIN_KP_ROWS = (board.GP26, board.GP22, board.GP21, board.GP20)
PIN_KP_COLS = (board.GP19, board.GP18, board.GP17, board.GP16)

# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------
DISPLAY_ADDR = 0x3C
DISPLAY_W    = 128
DISPLAY_H    = 64

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
LOG_PATH    = "/session_log.csv"
CONFIG_PATH = "/session_config.json"

# ---------------------------------------------------------------------------
# User-configurable settings — override in settings.toml
# ---------------------------------------------------------------------------
TARGET_DEFAULT = int(os.getenv("UVULA_TARGET_DEFAULT", 1000))
BUZZER_ENABLED = bool(int(os.getenv("UVULA_BUZZER_ENABLED", 1)))
LOG_ENABLED    = bool(int(os.getenv("UVULA_LOG_ENABLED", 1)))
TZ_OFFSET      = int(os.getenv("UVULA_TZ_OFFSET", 0))

# ---------------------------------------------------------------------------
# Hardware init
# ---------------------------------------------------------------------------
BUZZER = digitalio.DigitalInOut(PIN_BUZZER)
BUZZER.direction = digitalio.Direction.OUTPUT


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
class SessionData:
    """Accumulates per-second UV readings for one exposure run."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.session_id     = 0
        self.cumulative_uvs = 0
        self.elapsed_s      = 0
        self.estimate       = 'Inf'  # seconds remaining, or 'Inf' when light=0
        self.peak_uvs       = 0
        self.min_uvs        = None
        self.completed      = False


class State:
    def __init__(self, sensor):
        self.sensor          = sensor
        self.state           = 1
        self.buffer          = ''
        self.targetExposure  = TARGET_DEFAULT
        self.session         = SessionData()
        self.next_session_id = load_session_id() + 1


# ---------------------------------------------------------------------------
# Session ID persistence
# ---------------------------------------------------------------------------
def load_session_id():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f).get("session_id", 0)
    except Exception:
        return 0


def save_session_id(sid):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump({"session_id": sid}, f)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# NTP time sync
# ---------------------------------------------------------------------------
def sync_ntp():
    """Connect to WiFi, sync RTC from NTP. WiFi stays on for Web Workflow.
    Falls back silently if credentials missing or network unavailable."""
    ssid     = os.getenv("CIRCUITPY_WIFI_SSID")
    password = os.getenv("CIRCUITPY_WIFI_PASSWORD")
    if not ssid:
        print("NTP: no WiFi credentials in settings.toml — skipping")
        return
    try:
        import wifi
        import socketpool
        import adafruit_ntp
        print("NTP: connecting to", ssid)
        wifi.radio.connect(ssid, password)
        pool = socketpool.SocketPool(wifi.radio)
        ntp  = adafruit_ntp.NTP(pool, tz_offset=TZ_OFFSET, server="time.google.com")
        rtc.RTC().datetime = ntp.datetime
        t = time.localtime()
        print("NTP: synced — {:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec))
        print("NTP: WiFi staying on for Web Workflow —", str(wifi.radio.ipv4_address))
    except Exception as exc:
        print("NTP: sync failed —", exc)


def _timestamp():
    """Wall-clock timestamp if NTP synced, otherwise seconds since boot."""
    t = time.localtime()
    if t.tm_year >= 2021:
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
    return "{}s".format(int(time.monotonic()))


# ---------------------------------------------------------------------------
# CSV logging
# ---------------------------------------------------------------------------
_LOG_HEADER = "session_id,timestamp_s,uvs_reading,cumulative_uvs,elapsed_s,estimate_remaining\n"


def _ensure_log_header():
    try:
        os.stat(LOG_PATH)
    except OSError:
        try:
            with open(LOG_PATH, "w") as f:
                f.write(_LOG_HEADER)
        except Exception:
            pass


def log_row(session_id, uvs, session):
    """Append one per-second data row. Never raises — exposure must not crash."""
    if not LOG_ENABLED:
        return
    try:
        with open(LOG_PATH, "a") as f:
            f.write("{},{},{},{},{},{}\n".format(
                session_id,
                _timestamp(),
                uvs,
                session.cumulative_uvs,
                session.elapsed_s,
                session.estimate,
            ))
    except Exception:
        pass


def log_summary(session_id, session):
    """Append one summary row at exposure end."""
    if not LOG_ENABLED:
        return
    try:
        with open(LOG_PATH, "a") as f:
            status  = "completed" if session.completed else "aborted"
            min_uvs = session.min_uvs if session.min_uvs is not None else 0
            f.write("SUMMARY,{},{},{},{},{},{}\n".format(
                session_id,
                status,
                session.peak_uvs,
                min_uvs,
                session.elapsed_s,
                session.cumulative_uvs,
            ))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Buzzer
# ---------------------------------------------------------------------------
async def chirp(dur=0.15):
    if BUZZER_ENABLED:
        BUZZER.value = True
        await asyncio.sleep(dur)
        BUZZER.value = False
    else:
        await asyncio.sleep(dur)


async def playDone():
    for _ in range(3):
        await chirp(1.5)
        await asyncio.sleep(0.5)


# ---------------------------------------------------------------------------
# Keypad
# ---------------------------------------------------------------------------
async def setupKeypad(state):
    KEY_NAMES = [1, 2, 3, 'A', 4, 5, 6, 'B', 7, 8, 9, 'C', '*', 0, '#', 'D']
    km = keypad.KeyMatrix(PIN_KP_ROWS, PIN_KP_COLS)
    while True:
        event = km.events.get()
        if event:
            if event.pressed:
                await chirp(0.05)
            if event.released:
                state.buffer += str(KEY_NAMES[event.key_number])
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
def _read_uvs(state):
    """Return sensor UVS as a string; '--' if sensor missing or read fails."""
    if state.sensor is None:
        return '--'
    try:
        return str(state.sensor.uvs)
    except Exception:
        return '--'


async def displayHandler(i2c, state):
    displayio.release_displays()
    display_bus = displayio.I2CDisplay(i2c, device_address=DISPLAY_ADDR)
    display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=DISPLAY_W, height=DISPLAY_H)
    font = bitmap_font.load_font("/Helvetica-Bold-16.bdf")

    top_panel = displayio.Group()
    display.show(top_panel)

    text_area = [
        label.Label(font, text='', color=0xFFFFFF, x=0,  y=8),
        label.Label(font, text='', color=0xFFFFFF, x=0,  y=40),
        label.Label(font, text='', color=0xFFFFFF, x=64, y=8),
        label.Label(font, text='', color=0xFFFFFF, x=64, y=40),
    ]
    for ta in text_area:
        top_panel.append(ta)

    while True:
        text = ['', '', '', '']
        s = state.session

        if state.state == 1:
            # Collecting target: live UV reading and current target value
            text[0] = _read_uvs(state)
            text[1] = "{}".format(state.targetExposure)
            text[3] = "S{}".format(state.next_session_id)
        elif state.state == 2:
            # Running: cumulative UVS, elapsed seconds, estimated remaining, session
            text[0] = "{}".format(s.cumulative_uvs)
            text[1] = "{}s".format(s.elapsed_s)
            text[2] = "{}".format(s.estimate)
            text[3] = "S{}".format(s.session_id)
        elif state.state == 3:
            # Summary: done flag, final cumulative, session
            text[0] = "DONE"
            text[1] = "{}".format(s.cumulative_uvs)
            text[3] = "S{}".format(s.session_id)

        # Labels must be recreated and swapped — do not mutate existing ones
        old = list(text_area)
        text_area[0] = label.Label(font, text=text[0], color=0xFFFFFF, x=0,  y=8)
        text_area[1] = label.Label(font, text=text[1], color=0xFFFFFF, x=0,  y=40)
        text_area[2] = label.Label(font, text=text[2], color=0xFFFFFF, x=64, y=8)
        text_area[3] = label.Label(font, text=text[3], color=0xFFFFFF, x=64, y=40)

        for i in range(4):
            top_panel.append(text_area[i])
            top_panel.remove(old[i])

        await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# State machine phases
# ---------------------------------------------------------------------------
async def collectExposure(state):
    state.buffer = str(state.targetExposure)
    await asyncio.sleep(0.1)

    while True:
        if len(state.buffer) > 0:
            last = state.buffer[-1]

            if last == 'D':
                state.buffer = '0'
            elif last == '*':
                # Backspace: remove * and the character before it
                state.buffer = state.buffer[:-2] if len(state.buffer) > 1 else ''
            elif last == '#':
                # Confirm
                try:
                    if state.buffer[:-1]:
                        state.targetExposure = int(state.buffer[:-1])
                except ValueError:
                    pass
                state.buffer = ''
                break
            elif last in ('A', 'B', 'C'):
                # Letter keys have no function during target entry — strip them
                state.buffer = state.buffer[:-1]

            if len(state.buffer) > 0:
                try:
                    state.targetExposure = int(state.buffer)
                except ValueError:
                    state.buffer = state.buffer[:-1]

        await asyncio.sleep(0)


async def runExposure(state):
    session = state.session
    session.reset()

    session_id           = state.next_session_id
    session.session_id   = session_id
    state.next_session_id = session_id + 1
    save_session_id(session_id)
    _ensure_log_header()

    step = 1
    alarm_sounded = False

    while len(state.buffer) == 0:
        try:
            uvs = state.sensor.uvs if state.sensor else 0
        except Exception:
            uvs = 0

        session.peak_uvs = max(session.peak_uvs, uvs)
        session.min_uvs  = uvs if session.min_uvs is None else min(session.min_uvs, uvs)
        session.cumulative_uvs += uvs
        session.elapsed_s      += step

        remaining = state.targetExposure - session.cumulative_uvs
        session.estimate = max(0, int(remaining / uvs)) if uvs > 0 else 'Inf'

        log_row(session_id, uvs, session)

        await asyncio.sleep(step)

        if not alarm_sounded and session.cumulative_uvs >= state.targetExposure:
            asyncio.create_task(playDone())
            alarm_sounded = True

    session.completed = alarm_sounded
    log_summary(session_id, session)
    state.buffer = ''


async def showSummary(state):
    while len(state.buffer) == 0:
        await asyncio.sleep(0)
    state.buffer = ''


async def stateMachine(state):
    while True:
        if state.state == 1:
            await asyncio.gather(asyncio.create_task(collectExposure(state)))
            state.state = 2
        elif state.state == 2:
            await asyncio.gather(asyncio.create_task(runExposure(state)))
            state.state = 3
        elif state.state == 3:
            await asyncio.gather(asyncio.create_task(showSummary(state)))
            state.state = 1
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main():
    displayio.release_displays()
    sync_ntp()

    i2c = busio.I2C(PIN_SCL, PIN_SDA)
    if i2c.try_lock():
        print("i2c scan:", i2c.scan())
        i2c.unlock()

    sensor = None
    try:
        import adafruit_ltr390
        sensor = adafruit_ltr390.LTR390(i2c)
        print("LTR390 ready")
    except Exception as exc:
        print("LTR390 init failed:", exc)
        # Display will show '--' for UV readings; exposure will log zeros

    state = State(sensor)

    display_task = asyncio.create_task(displayHandler(i2c, state))
    keypad_task  = asyncio.create_task(setupKeypad(state))
    sm_task      = asyncio.create_task(stateMachine(state))

    await asyncio.gather(display_task, keypad_task, sm_task)


asyncio.run(main())

"""
wifi_logger.py — live UV logging over WiFi (RP2040W only)

TODO: Not yet implemented. Planned feature: the device hosts a small local
web page showing real-time UV readings and an exposure progress bar,
accessible from a phone or laptop on the same network while printing.

Implementation sketch:
  - Import wifi, socketpool, adafruit_httpserver from CircuitPython
  - Connect to network using CIRCUITPY_WIFI_SSID / _PASSWORD from settings.toml
  - Spin up an HTTP server on port 80
  - Serve a single-page app that polls /status for JSON data
  - /status returns: {session_id, uvs, cumulative_uvs, target, elapsed_s, estimate_s}
  - Progress bar and auto-refresh in the HTML

Constraints:
  - RP2040W only (standard Pico has no WiFi)
  - Must run as an asyncio task alongside the existing display/keypad/sensor tasks
  - Network outages must not affect exposure accuracy — wrap all WiFi calls in try/except
  - adafruit_httpserver library required (not in base bundle — install separately)

To scaffold:
  1. Uncomment CIRCUITPY_WIFI_SSID and CIRCUITPY_WIFI_PASSWORD in settings.toml
  2. Add adafruit_httpserver to lib/
  3. Implement start_wifi_logger(state) as an async task
  4. Add it to the asyncio.gather() call in main()
"""


async def start_wifi_logger(state):
    """Stub. Replace with WiFi server implementation for RP2040W."""
    # pylint: disable=unused-argument
    pass

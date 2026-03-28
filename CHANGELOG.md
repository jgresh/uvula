# Changelog

## v0.2 — Session Logging

- CSV session logging to `/session_log.csv` (one row/second + summary row per session)
- Session IDs persist across reboots via `/session_config.json`
- `boot.py` remounts filesystem as writable to enable logging
- Settings via `settings.toml`: target default, buzzer on/off, logging on/off
- `SessionData` class replaces fragile `cumulativeExposure` tuple
- Graceful sensor error handling — shows `--` on display if LTR390 not found
- Display now shows "DONE" + final cumulative UVS during summary phase
- Letter keys (A/B/C) silently ignored during target entry
- Sensor read errors during exposure log zero and continue (never crash)
- `wifi_logger.py` stub scaffolding for future RP2040W live logging
- `README.md`, `CHANGELOG.md`, `LICENSE`, `.gitignore` added

## v0.1 — Initial Working Prototype

- Three-state async loop: collect target → run exposure → show summary
- LTR390 UV sensor integration (raw `.uvs` counts, not UV index)
- 4x4 keypad for target dose entry (`#` to confirm, `*` to backspace, `D` to clear)
- SSD1306 128x64 OLED display with Helvetica Bold 16pt font
- Passive buzzer alarm (3 long beeps) when target dose reached
- Any key press cancels/advances to next state

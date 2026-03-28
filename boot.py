# boot.py — runs before code.py on every power-up
#
# Remounts the filesystem as writable so code.py can log sessions to CSV.
#
# TRADEOFF: while this line is active, the CIRCUITPY drive will NOT appear
# as a writable USB drive on your computer. You will not be able to drag
# files onto the drive or edit code.py directly.
#
# To re-enable USB editing:
#   1. Connect via USB serial (Mu editor, or: screen /dev/tty.usbmodem* 115200)
#   2. Comment out the storage.remount() line below
#   3. Save and reboot — CIRCUITPY drive reappears as writable
#
# To re-enable logging:
#   1. Uncomment the line
#   2. Reboot

import storage
storage.remount("/", readonly=False)

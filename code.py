import board
import busio
import time
import adafruit_ltr390
import os
import displayio
import digitalio
import adafruit_displayio_ssd1306
import terminalio
import keypad
import asyncio
from adafruit_display_text import label

BUZZER = digitalio.DigitalInOut(board.GP6)
BUZZER.direction = digitalio.Direction.OUTPUT

class State:
    def __init__(self, sensor, state = 1, buffer = '', targetExposure = 0):
        self.sensor = sensor
        self.state = state
        self.buffer = buffer
        self.targetExposure = targetExposure
        self.cumulativeExposure = (0, 0, 0)
        
async def setupKeypad(state):
    KEY_NAMES = [1, 2, 3, 'A', 4, 5, 6, 'B', 7, 8, 9, 'C', '*', 0, '#', 'D']
    
    km = keypad.KeyMatrix((board.GP26, board.GP22, board.GP21, board.GP20),
                          (board.GP19, board.GP18, board.GP17, board.GP16))
    while True:
        event = km.events.get()

        if event:
            if event.pressed:
                await chirp(0.05)
            if event.released:
                state.buffer += str(KEY_NAMES[event.key_number])
                print(state.buffer)
        
        await asyncio.sleep(0)

                
async def chirp(dur=0.15):
    BUZZER.value = True
    await asyncio.sleep(dur)
    BUZZER.value = False
    
async def playDone():
    for i in range(3):
        await chirp(1.5)
        await asyncio.sleep(0.5)
        
async def displayHandler(i2c, state):
    displayio.release_displays()
    display_bus = displayio.I2CDisplay(i2c, device_address=60)
    display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=128, height=64)

    # Make the display context
    top_panel = displayio.Group()
    display.show(top_panel)

    color_bitmap = displayio.Bitmap(128, 32, 1)
    color_palette = displayio.Palette(1)
    color_palette[0] = 0xFFFFFF  # White

    bg_sprite = displayio.TileGrid(color_bitmap, pixel_shader=color_palette, x=0, y=0)
    top_panel.append(bg_sprite)

    # Draw a smaller inner rectangle
    inner_bitmap = displayio.Bitmap(118, 24, 1)
    inner_palette = displayio.Palette(1)
    inner_palette[0] = 0x000000  # Black
    inner_sprite = displayio.TileGrid(inner_bitmap, pixel_shader=inner_palette, x=5, y=4)
    top_panel.append(inner_sprite)

    # Draw a label
    text = ""
    text_area = label.Label(terminalio.FONT, text=text, color=0xFFFF00, x=28, y=15)
    top_panel.append(text_area)

    while True:            
        old = text_area
        if state.state == 1:
            text = "%s\t%s" % (state.sensor.light, state.targetExposure)
        if state.state == 2:
            text = "%s\t%s\t%s" % (state.cumulativeExposure[0],
                                                state.cumulativeExposure[1], state.cumulativeExposure[2])
            
        text_area = label.Label(terminalio.FONT, text=text, color=0xFFFF00, x=8, y=15)
        top_panel.append(text_area)
        top_panel.remove(old)

        await asyncio.sleep(0.1)

async def stateMachine(state):
    while True:
        if state.state == 1:
            task = asyncio.create_task(collectExposure(state))
            await asyncio.gather(task)
            state.state = 2
        elif state.state == 2:
            task = asyncio.create_task(runExposure(state))
            await asyncio.gather(task)
            state.state = 3
        elif state.state == 3:
            task = asyncio.create_task(showSummary(state))
            await asyncio.gather(task)
            state.state = 1
        
        await asyncio.sleep(0)

async def collectExposure(state):
    state.buffer = str(state.targetExposure)
    await asyncio.sleep(0.1)

    while True:
        if len(state.buffer) > 0:
            # delete the whole buffer
            if state.buffer[-1] == 'D':
                state.buffer = '0'
            # delete one character including this
            elif state.buffer[-1] == '*':
                # delete only one if * is the only one
                if len(state.buffer) == 1:
                    state.buffer = state.buffer[0:-1]
                else:
                    state.buffer = state.buffer[0:-2]
                    
            # pound(#) is Enter
            elif state.buffer[-1] == '#':
                state.targetExposure = int(state.buffer[0:-1])
                state.buffer = ''
                break
            
            if len(state.buffer) > 0:
                state.targetExposure = int(state.buffer)
                
        await asyncio.sleep(0)

async def runExposure(state):
    state.cumulativeExposure = (0, 0, 0)
    step = 1
    alarm_sounded = False

    # count until a key is pressed
    while len(state.buffer) == 0:
        estimate = (state.targetExposure - state.cumulativeExposure[0]) / (state.sensor.light * step)
        state.cumulativeExposure = (state.cumulativeExposure[0] + state.sensor.light,
                                    state.cumulativeExposure[1] + step,
                                    estimate)

        await asyncio.sleep(step)
        
        if not alarm_sounded and state.cumulativeExposure[0] > state.targetExposure:
            sm_task = asyncio.create_task(playDone())
            alarm_sounded = True
            
    state.buffer = ''

async def showSummary(state):
    # just hold the screen now
    while len(state.buffer) == 0:
        await asyncio.sleep(0)

async def main():
    displayio.release_displays()

    SDA = board.GP8
    SCL = board.GP9
    i2c = busio.I2C(SCL, SDA)
    if(i2c.try_lock()):
        print("i2c.scan(): " + str(i2c.scan()))
        i2c.unlock()
    print("i2c ready")
    
    state = State(adafruit_ltr390.LTR390(i2c))
    
    display_task = asyncio.create_task(displayHandler(i2c, state))
    keypad_task = asyncio.create_task(setupKeypad(state))
    sm_task = asyncio.create_task(stateMachine(state))
    
    await asyncio.gather(display_task, keypad_task, sm_task)

asyncio.run(main())
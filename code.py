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
from adafruit_bitmap_font import bitmap_font

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
    font = bitmap_font.load_font("/Helvetica-Bold-16.bdf")

    # Make the display context
    top_panel = displayio.Group()
    display.show(top_panel)

    # Draw a label
    text = [''] * 4
    text_area = []
    
    text_area.append(label.Label(font, text=text[0], color=0xFFFFFF, x=0, y=8))
    text_area.append(label.Label(font, text=text[1], color=0xFFFFFF, x=0, y=40))
    text_area.append(label.Label(font, text=text[2], color=0xFFFFFF, x=64, y=8))
    text_area.append(label.Label(font, text=text[3], color=0xFFFFFF, x=64, y=40))
    
    top_panel.append(text_area[0])
    top_panel.append(text_area[1])
    top_panel.append(text_area[2])
    top_panel.append(text_area[3])

    while True:
        text = [''] * 4
        
        old = [ta for ta in text_area]

        if state.state == 1:
            text[0]= "%s" % (state.sensor.light)
            text[1] = "%s" % (state.targetExposure)
        if state.state == 2:
            text[0] = "%s" % (state.cumulativeExposure[0])
            text[1] = "%s" % (state.cumulativeExposure[1])
            text[2] = "%s" % (state.cumulativeExposure[2])
        
        # Old default font terminalio.FONT
        text_area[0] = label.Label(font, text=text[0], color=0xFFFFFF, x=0, y=8)
        text_area[1] = label.Label(font, text=text[1], color=0xFFFFFF, x=0, y=40)
        text_area[2] = label.Label(font, text=text[2], color=0xFFFFFF, x=64, y=8)
        text_area[3] = label.Label(font, text=text[3], color=0xFFFFFF, x=64, y=40)
        
        for i in range(4):
            top_panel.append(text_area[i])
            top_panel.remove(old[i])

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
import evdev
from evdev import InputDevice, categorize, ecodes
import time

# -----------------------------
# Motor control setup (example)
# -----------------------------
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)

LEFT_FORWARD = 17
LEFT_BACKWARD = 18
RIGHT_FORWARD = 22
RIGHT_BACKWARD = 23

GPIO.setup(LEFT_FORWARD, GPIO.OUT)
GPIO.setup(LEFT_BACKWARD, GPIO.OUT)
GPIO.setup(RIGHT_FORWARD, GPIO.OUT)
GPIO.setup(RIGHT_BACKWARD, GPIO.OUT)

def stop():
    GPIO.output(LEFT_FORWARD, 0)
    GPIO.output(LEFT_BACKWARD, 0)
    GPIO.output(RIGHT_FORWARD, 0)
    GPIO.output(RIGHT_BACKWARD, 0)

def forward():
    GPIO.output(LEFT_FORWARD, 1)
    GPIO.output(RIGHT_FORWARD, 1)

def backward():
    GPIO.output(LEFT_BACKWARD, 1)
    GPIO.output(RIGHT_BACKWARD, 1)

def left():
    GPIO.output(LEFT_BACKWARD, 1)
    GPIO.output(RIGHT_FORWARD, 1)

def right():
    GPIO.output(LEFT_FORWARD, 1)
    GPIO.output(RIGHT_BACKWARD, 1)

# -----------------------------
# Find the keyboard device
# -----------------------------
devices = [InputDevice(path) for path in evdev.list_devices()]
keyboard = None

for dev in devices:
    if "Keyboard" in dev.name or "keyboard" in dev.name:
        keyboard = InputDevice(dev.path)
        break

if keyboard is None:
    print("No keyboard found!")
    exit()

print("Ready. Use W/A/S/D to move, Q to quit.")

# -----------------------------
# Main loop
# -----------------------------
for event in keyboard.read_loop():
    if event.type == ecodes.EV_KEY:
        key = categorize(event)

        if key.keystate == key.key_down:

            if key.keycode == 'KEY_W':
                forward()

            elif key.keycode == 'KEY_S':
                backward()

            elif key.keycode == 'KEY_A':
                left()

            elif key.keycode == 'KEY_D':
                right()

            elif key.keycode == 'KEY_Q':
                stop()
                print("Exiting…")
                break

        elif key.keystate == key.key_up:
            stop()

GPIO.cleanup()

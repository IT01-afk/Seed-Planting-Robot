import evdev
from evdev import InputDevice, categorize, ecodes
import RPi.GPIO as GPIO
import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# -----------------------------
# GPIO Setup
# -----------------------------
GPIO.setmode(GPIO.BCM)

# L298N pins
IN1 = 17
IN2 = 18
IN3 = 22
IN4 = 23
ENA = 12
ENB = 13

GPIO.setup(IN1, GPIO.OUT)
GPIO.setup(IN2, GPIO.OUT)
GPIO.setup(IN3, GPIO.OUT)
GPIO.setup(IN4, GPIO.OUT)
GPIO.setup(ENA, GPIO.OUT)
GPIO.setup(ENB, GPIO.OUT)

pwm_left = GPIO.PWM(ENA, 1000)
pwm_right = GPIO.PWM(ENB, 1000)
pwm_left.start(70)
pwm_right.start(70)

# Servo pins
MOISTURE_SERVO = 5
SEED_SERVO = 6

GPIO.setup(MOISTURE_SERVO, GPIO.OUT)
GPIO.setup(SEED_SERVO, GPIO.OUT)

moisture_pwm = GPIO.PWM(MOISTURE_SERVO, 50)
seed_pwm = GPIO.PWM(SEED_SERVO, 50)

moisture_pwm.start(0)
seed_pwm.start(0)

def servo_angle(pwm, angle):
    duty = 2 + (angle / 18)
    pwm.ChangeDutyCycle(duty)
    time.sleep(0.4)
    pwm.ChangeDutyCycle(0)

# -----------------------------
# ADS1115 Setup
# -----------------------------
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)

# IMPORTANT: use raw channel number (0), not ADS.P0
chan = AnalogIn(ads, 0)

# -----------------------------
# Motor Control
# -----------------------------
def stop_all():
    GPIO.output(IN1, 0)
    GPIO.output(IN2, 0)
    GPIO.output(IN3, 0)
    GPIO.output(IN4, 0)

def motor1_forward():
    GPIO.output(IN1, 1)
    GPIO.output(IN2, 0)

def motor1_backward():
    GPIO.output(IN1, 0)
    GPIO.output(IN2, 1)

def motor2_forward():
    GPIO.output(IN3, 1)
    GPIO.output(IN4, 0)

def motor2_backward():
    GPIO.output(IN3, 0)
    GPIO.output(IN4, 1)

# -----------------------------
# Q Routine
# -----------------------------
q_running = False

def moisture_routine():
    global q_running
    q_running = True

    stop_all()

    # Move moisture servo to 180
    servo_angle(moisture_pwm, 180)

    # Read moisture
    value = chan.value
    print("Moisture:", value)

    # Decide seed servo
    if value < 15000:
        servo_angle(seed_pwm, 0)
    else:
        servo_angle(seed_pwm, 90)

    # Return moisture servo
    servo_angle(moisture_pwm, 0)

    q_running = False

# -----------------------------
# Keyboard Setup
# -----------------------------
TARGET_DEVICE = "/dev/input/event7"   # your real keyboard

try:
    keyboard = InputDevice(TARGET_DEVICE)
    keyboard.grab()  # exclusive control
    print(f"Using keyboard: {TARGET_DEVICE}")
except:
    print("Failed to open keyboard device. Check the event number.")
    exit()

# Track illegal combos
motor1_state = None
motor2_state = None

# -----------------------------
# Main Loop
# -----------------------------
for event in keyboard.read_loop():
    if event.type == ecodes.EV_KEY:
        key = categorize(event)

        if key.keystate == key.key_down:

            if key.keycode == 'KEY_ESC':
                stop_all()
                break

            if q_running:
                continue

            # Motor 1
            if key.keycode == 'KEY_A' and motor1_state != "back":
                motor1_forward()
                motor1_state = "forward"

            elif key.keycode == 'KEY_Z' and motor1_state != "forward":
                motor1_backward()
                motor1_state = "back"

            # Motor 2
            elif key.keycode == 'KEY_D' and motor2_state != "back":
                motor2_forward()
                motor2_state = "forward"

            elif key.keycode == 'KEY_C' and motor2_state != "forward":
                motor2_backward()
                motor2_state = "back"

            # Q routine
            elif key.keycode == 'KEY_Q' and not q_running:
                moisture_routine()

        elif key.keystate == key.key_up:
            if key.keycode in ['KEY_A', 'KEY_Z']:
                motor1_state = None
                stop_all()

            if key.keycode in ['KEY_D', 'KEY_C']:
                motor2_state = None
                stop_all()

stop_all()
moisture_pwm.stop()
seed_pwm.stop()
pwm_left.stop()
pwm_right.stop()
GPIO.cleanup()

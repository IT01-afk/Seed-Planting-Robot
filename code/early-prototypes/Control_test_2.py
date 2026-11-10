#!/usr/bin/env python3
"""
Controller -> Robot control (fixed mappings)
Pi 3B, controller on /dev/input/event8

Run with: sudo python3 controller_robot_fixed.py
"""

import sys
import time
import signal

import evdev
from evdev import InputDevice, ecodes

import RPi.GPIO as GPIO

# CircuitPython ADS1115
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# -----------------------------
# Configuration (change if needed)
# -----------------------------
TARGET_DEVICE = "/dev/input/event8"   # your controller device
ADS_CHANNEL = 0                       # ADS1115 channel for moisture sensor

# GPIO pins (Pi 3B)
# Servos
SERVO_A_PIN = 5    # Right trigger -> Servo A (moisture probe servo)
SERVO_B_PIN = 6    # Left trigger  -> Servo B (seed servo)
SERVO_C_PIN = 18   # Button X -> Servo C (held action)

# Motor driver 1 (L298N) - Motor A
M1_IN1 = 17
M1_IN2 = 27
# Motor driver 1 - Motor B
M2_IN3 = 22
M2_IN4 = 23
# Motor driver 1 - PWM enables
M1_EN = 12   # ENA -> Motor A PWM (hardware PWM)
M2_EN = 13   # ENB -> Motor B PWM (hardware PWM)

# Water pump driver (L298N-style)
PUMP_IN1 = 19
PUMP_IN2 = 26
PUMP_EN = 21   # PWM for pump (software PWM)

# PWM frequencies
MOTOR_PWM_FREQ = 1000   # Hz
SERVO_PWM_FREQ = 50     # Hz

# Servo helper
def angle_to_duty(angle):
    return 2.0 + (angle / 18.0)

# -----------------------------
# GPIO setup
# -----------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Motor direction pins
for p in (M1_IN1, M1_IN2, M2_IN3, M2_IN4):
    GPIO.setup(p, GPIO.OUT)
    GPIO.output(p, 0)

# Motor PWM pins
GPIO.setup(M1_EN, GPIO.OUT)
GPIO.setup(M2_EN, GPIO.OUT)
motor_pwm_a = GPIO.PWM(M1_EN, MOTOR_PWM_FREQ)
motor_pwm_b = GPIO.PWM(M2_EN, MOTOR_PWM_FREQ)
motor_pwm_a.start(0)
motor_pwm_b.start(0)

# Pump pins
GPIO.setup(PUMP_IN1, GPIO.OUT)
GPIO.setup(PUMP_IN2, GPIO.OUT)
GPIO.setup(PUMP_EN, GPIO.OUT)
pump_pwm = GPIO.PWM(PUMP_EN, MOTOR_PWM_FREQ)
pump_pwm.start(0)
pump_state = False

# Servo pins
for p in (SERVO_A_PIN, SERVO_B_PIN, SERVO_C_PIN):
    GPIO.setup(p, GPIO.OUT)

servo_a_pwm = GPIO.PWM(SERVO_A_PIN, SERVO_PWM_FREQ)
servo_b_pwm = GPIO.PWM(SERVO_B_PIN, SERVO_PWM_FREQ)
servo_c_pwm = GPIO.PWM(SERVO_C_PIN, SERVO_PWM_FREQ)

servo_a_pwm.start(0)
servo_b_pwm.start(0)
servo_c_pwm.start(0)

# -----------------------------
# ADS1115 setup
# -----------------------------
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
chan = AnalogIn(ads, ADS_CHANNEL)

# -----------------------------
# Motor helpers
# -----------------------------
def stop_all_motors():
    GPIO.output(M1_IN1, 0)
    GPIO.output(M1_IN2, 0)
    GPIO.output(M2_IN3, 0)
    GPIO.output(M2_IN4, 0)
    motor_pwm_a.ChangeDutyCycle(0)
    motor_pwm_b.ChangeDutyCycle(0)

def set_motor_a(speed):  # speed: -1.0 .. 1.0
    if speed > 0:
        GPIO.output(M1_IN1, 1)
        GPIO.output(M1_IN2, 0)
        motor_pwm_a.ChangeDutyCycle(min(abs(speed) * 100.0, 100.0))
    elif speed < 0:
        GPIO.output(M1_IN1, 0)
        GPIO.output(M1_IN2, 1)
        motor_pwm_a.ChangeDutyCycle(min(abs(speed) * 100.0, 100.0))
    else:
        GPIO.output(M1_IN1, 0)
        GPIO.output(M1_IN2, 0)
        motor_pwm_a.ChangeDutyCycle(0)

def set_motor_b(speed):  # speed: -1.0 .. 1.0
    if speed > 0:
        GPIO.output(M2_IN3, 1)
        GPIO.output(M2_IN4, 0)
        motor_pwm_b.ChangeDutyCycle(min(abs(speed) * 100.0, 100.0))
    elif speed < 0:
        GPIO.output(M2_IN3, 0)
        GPIO.output(M2_IN4, 1)
        motor_pwm_b.ChangeDutyCycle(min(abs(speed) * 100.0, 100.0))
    else:
        GPIO.output(M2_IN3, 0)
        GPIO.output(M2_IN4, 0)
        motor_pwm_b.ChangeDutyCycle(0)

# -----------------------------
# Pump helpers
# -----------------------------
def set_pump(on):
    global pump_state
    pump_state = bool(on)
    if pump_state:
        # forward direction
        GPIO.output(PUMP_IN1, 1)
        GPIO.output(PUMP_IN2, 0)
        pump_pwm.ChangeDutyCycle(100)
    else:
        GPIO.output(PUMP_IN1, 0)
        GPIO.output(PUMP_IN2, 0)
        pump_pwm.ChangeDutyCycle(0)

# -----------------------------
# Servo helpers
# -----------------------------
def set_servo_pwm(servo_pwm, angle):
    angle = max(0.0, min(180.0, angle))
    duty = angle_to_duty(angle)
    servo_pwm.ChangeDutyCycle(duty)
    time.sleep(0.02)
    servo_pwm.ChangeDutyCycle(0)

# -----------------------------
# Moisture routine (Button A)
# -----------------------------
q_running = False

def moisture_routine():
    global q_running
    if q_running:
        return
    q_running = True
    try:
        # stop motors
        set_motor_a(0)
        set_motor_b(0)
        # move moisture servo (Servo A) to probe position
        set_servo_pwm(servo_a_pwm, 180)
        time.sleep(0.4)
        # read ADC
        value = chan.value
        print("[MOISTURE] ADC raw value:", value)
        # decide seed servo (Servo B)
        if value < 15000:
            set_servo_pwm(servo_b_pwm, 0)
            print("[MOISTURE] Dry -> seed servo to 0°")
        else:
            set_servo_pwm(servo_b_pwm, 90)
            print("[MOISTURE] Wet -> seed servo to 90°")
        # return moisture servo
        set_servo_pwm(servo_a_pwm, 0)
        time.sleep(0.2)
    finally:
        q_running = False

# -----------------------------
# Axis normalization helpers
# -----------------------------
def normalize_axis(value, absinfo):
    try:
        amin = absinfo.min
        amax = absinfo.max
    except Exception:
        amin, amax = -32768, 32767
    center = (amax + amin) / 2.0
    half_range = (amax - amin) / 2.0
    if half_range == 0:
        return 0.0
    return (value - center) / half_range

def normalize_trigger(value, absinfo):
    try:
        amin = absinfo.min
        amax = absinfo.max
    except Exception:
        amin, amax = 0, 255
    if amax == amin:
        return 0.0
    # Some controllers: released=0, pressed=max
    return (value - amin) / float(amax - amin)

# -----------------------------
# Controller mapping detection (robust)
# -----------------------------
def build_abs_map(dev):
    caps = dev.capabilities()
    abs_entries = caps.get(evdev.ecodes.EV_ABS, [])
    available = set(code for code, info in abs_entries)

    # choose left_y
    abs_map = {}
    if evdev.ecodes.ABS_Y in available:
        abs_map['left_y'] = evdev.ecodes.ABS_Y

    # choose right_y: prefer ABS_RY, then ABS_RZ, then ABS_RX, avoid left_y
    for candidate in (evdev.ecodes.ABS_RY, evdev.ecodes.ABS_RZ, evdev.ecodes.ABS_RX, evdev.ecodes.ABS_Y):
        if candidate in available and candidate != abs_map.get('left_y'):
            abs_map['right_y'] = candidate
            break

    # triggers: prefer ABS_Z and ABS_RZ but avoid conflicts
    # left trigger
    for candidate in (evdev.ecodes.ABS_Z, evdev.ecodes.ABS_BRAKE, evdev.ecodes.ABS_THROTTLE):
        if candidate in available and candidate not in abs_map.values():
            abs_map['lt'] = candidate
            break
    # right trigger
    for candidate in (evdev.ecodes.ABS_RZ, evdev.ecodes.ABS_RY, evdev.ecodes.ABS_RX, evdev.ecodes.ABS_Z):
        if candidate in available and candidate not in abs_map.values():
            abs_map['rt'] = candidate
            break

    return abs_map

# -----------------------------
# Main loop
# -----------------------------
def main():
    # open controller device explicitly
    try:
        dev = InputDevice(TARGET_DEVICE)
    except Exception as e:
        print("Failed to open", TARGET_DEVICE, ":", e)
        print("Available devices:")
        for p in evdev.list_devices():
            d = InputDevice(p)
            print(" ", p, ":", d.name)
        cleanup_and_exit(1)

    print("Using controller:", TARGET_DEVICE, dev.name)
    try:
        dev.grab()
    except Exception as e:
        print("Warning: could not grab device exclusively:", e)

    # build mapping
    abs_map = build_abs_map(dev)
    print("ABS mapping chosen:", abs_map)

    # prefetch absinfo
    absinfo_cache = {}
    for name, code in abs_map.items():
        try:
            absinfo_cache[code] = dev.absinfo(code)
        except Exception:
            absinfo_cache[code] = type("A", (), {"min": -32768, "max": 32767})

    # axis state
    axis_state = {'left_y': 0.0, 'right_y': 0.0, 'lt': 0.0, 'rt': 0.0}

    # servo C state (Button X)
    servo_c_active = False

    print("Ready. Left stick up -> Motor A forward. Right stick up -> Motor B forward.")
    print("Right trigger -> Servo A. Left trigger -> Servo B.")
    print("Button A -> Moisture read. Button B -> Toggle pump. Button X -> Servo C while held.")
    print("Ctrl+C to exit.")

    try:
        for event in dev.read_loop():
            if event.type == evdev.ecodes.EV_ABS:
                code = event.code
                val = event.value

                # left stick vertical
                if 'left_y' in abs_map and code == abs_map['left_y']:
                    n = normalize_axis(val, absinfo_cache[code])
                    n = -n  # invert so pushing up -> positive
                    if abs(n) < 0.05:
                        n = 0.0
                    axis_state['left_y'] = max(-1.0, min(1.0, n))
                    set_motor_a(axis_state['left_y'])

                # right stick vertical
                elif 'right_y' in abs_map and code == abs_map['right_y']:
                    n = normalize_axis(val, absinfo_cache[code])
                    n = -n
                    if abs(n) < 0.05:
                        n = 0.0
                    axis_state['right_y'] = max(-1.0, min(1.0, n))
                    set_motor_b(axis_state['right_y'])

                # left trigger
                elif 'lt' in abs_map and code == abs_map['lt']:
                    t = normalize_trigger(val, absinfo_cache[code])
                    axis_state['lt'] = max(0.0, min(1.0, t))
                    angle = axis_state['lt'] * 180.0
                    set_servo_pwm(servo_b_pwm, angle)

                # right trigger
                elif 'rt' in abs_map and code == abs_map['rt']:
                    t = normalize_trigger(val, absinfo_cache[code])
                    axis_state['rt'] = max(0.0, min(1.0, t))
                    angle = axis_state['rt'] * 180.0
                    set_servo_pwm(servo_a_pwm, angle)

            elif event.type == evdev.ecodes.EV_KEY:
                keycode = event.code
                keystate = event.value  # 1=press,0=release,2=hold

                # Button A -> BTN_SOUTH -> moisture routine on press
                if keycode == evdev.ecodes.BTN_SOUTH and keystate == 1:
                    moisture_routine()

                # Button B -> BTN_EAST -> toggle pump on press
                elif keycode == evdev.ecodes.BTN_EAST and keystate == 1:
                    set_pump(not pump_state)
                    print("[PUMP] Toggled ->", "ON" if pump_state else "OFF")

                # Button X -> BTN_NORTH -> servo C while held
                elif keycode == evdev.ecodes.BTN_NORTH:
                    if keystate == 1:
                        servo_c_active = True
                        set_servo_pwm(servo_c_pwm, 90)
                    elif keystate == 0:
                        servo_c_active = False
                        set_servo_pwm(servo_c_pwm, 0)

                # Optional: Start/Select for stop/exit
                elif keycode == evdev.ecodes.BTN_START and keystate == 1:
                    print("Start pressed: stopping motors.")
                    set_motor_a(0)
                    set_motor_b(0)
                elif keycode == evdev.ecodes.BTN_SELECT and keystate == 1:
                    print("Select pressed: exiting.")
                    break

    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        try:
            dev.ungrab()
        except Exception:
            pass
        cleanup_and_exit(0)

# -----------------------------
# Cleanup
# -----------------------------
def cleanup_and_exit(code=0):
    try:
        stop_all_motors()
        set_pump(False)
        servo_a_pwm.stop()
        servo_b_pwm.stop()
        servo_c_pwm.stop()
        motor_pwm_a.stop()
        motor_pwm_b.stop()
        pump_pwm.stop()
        GPIO.cleanup()
    except Exception:
        pass
    sys.exit(code)

if __name__ == "__main__":
    main()

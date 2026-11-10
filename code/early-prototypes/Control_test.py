#!/usr/bin/env python3
"""
Xbox-style controller -> robot control
Raspberry Pi 3B compatible.

Requirements:
- python3-evdev
- RPi.GPIO
- adafruit-circuitpython-ads1x15
- board, busio (CircuitPython)
Run with sudo (evdev device access and GPIO).
"""

import sys
import time
import math
import signal

import evdev
from evdev import InputDevice, categorize, ecodes

import RPi.GPIO as GPIO

# CircuitPython ADS1115
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# -----------------------------
# GPIO pin assignments (Pi 3B)
# Adjust here if you want different pins
# -----------------------------
# Servos
SERVO_A_PIN = 5    # Right trigger -> Servo A (moisture servo in previous code)
SERVO_B_PIN = 6    # Left trigger -> Servo B (seed servo in previous code)
SERVO_C_PIN = 18   # Button A -> Servo C (new servo)

# Motor driver 1 (L298N) - Motor A
M1_IN1 = 17
M1_IN2 = 27
# Motor driver 1 - Motor B
M2_IN3 = 22
M2_IN4 = 23
# Motor driver 1 - PWM enables
M1_EN = 12   # ENA -> Motor A PWM
M2_EN = 13   # ENB -> Motor B PWM

# Water pump driver (not used by controller mapping here, but reserved)
PUMP_IN1 = 19
PUMP_IN2 = 26
PUMP_EN = 21

# PWM frequencies
MOTOR_PWM_FREQ = 1000   # Hz
SERVO_PWM_FREQ = 50     # Hz

# ADS1115 channel for moisture sensor
ADS_CHANNEL = 0

# Servo angle helper
def angle_to_duty(angle):
    # Standard servo: 0 -> ~2% , 180 -> ~12% (approx)
    return 2.0 + (angle / 18.0)

# -----------------------------
# GPIO setup
# -----------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Motor pins
for p in (M1_IN1, M1_IN2, M2_IN3, M2_IN4):
    GPIO.setup(p, GPIO.OUT)
    GPIO.output(p, 0)

GPIO.setup(M1_EN, GPIO.OUT)
GPIO.setup(M2_EN, GPIO.OUT)

motor_pwm_a = GPIO.PWM(M1_EN, MOTOR_PWM_FREQ)
motor_pwm_b = GPIO.PWM(M2_EN, MOTOR_PWM_FREQ)
motor_pwm_a.start(0)
motor_pwm_b.start(0)

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
# Motor control helpers
# -----------------------------
def stop_all_motors():
    GPIO.output(M1_IN1, 0)
    GPIO.output(M1_IN2, 0)
    GPIO.output(M2_IN3, 0)
    GPIO.output(M2_IN4, 0)
    motor_pwm_a.ChangeDutyCycle(0)
    motor_pwm_b.ChangeDutyCycle(0)

def set_motor_a(speed):  # speed: -1.0 .. 1.0
    # positive -> forward, negative -> backward
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
# Servo control helpers
# -----------------------------
def set_servo_pwm(servo_pwm, angle):
    angle = max(0.0, min(180.0, angle))
    duty = angle_to_duty(angle)
    servo_pwm.ChangeDutyCycle(duty)
    # small delay to let servo move; do not hold duty cycle to avoid jitter
    time.sleep(0.02)
    servo_pwm.ChangeDutyCycle(0)

# -----------------------------
# Moisture routine (Button B)
# -----------------------------
q_running = False

def moisture_routine():
    global q_running
    if q_running:
        return
    q_running = True
    try:
        # Stop motors while measuring
        set_motor_a(0)
        set_motor_b(0)

        # Move moisture servo (Servo A) to probe position (180)
        set_servo_pwm(servo_a_pwm, 180)
        time.sleep(0.4)

        # Read ADS1115
        value = chan.value
        print("[MOISTURE] ADC raw value:", value)

        # Decide seed servo (Servo B) based on threshold
        # Threshold chosen from earlier code: 15000
        if value < 15000:
            set_servo_pwm(servo_b_pwm, 0)
            print("[MOISTURE] Dry -> seed servo to 0°")
        else:
            set_servo_pwm(servo_b_pwm, 90)
            print("[MOISTURE] Wet -> seed servo to 90°")

        # Return moisture servo
        set_servo_pwm(servo_a_pwm, 0)
        time.sleep(0.2)
    finally:
        q_running = False

# -----------------------------
# Controller detection
# -----------------------------
def find_gamepad_device():
    """
    Find an input device that looks like a gamepad with:
    - ABS_Y (left vertical)
    - ABS_RY or ABS_Y2 (right vertical)
    - ABS_Z / ABS_RZ (triggers)
    - BTN_SOUTH (A) and BTN_EAST (B)
    """
    candidates = []
    for path in evdev.list_devices():
        dev = InputDevice(path)
        caps = dev.capabilities(verbose=True)
        # quick checks for common gamepad features
        names = dev.name.lower()
        has_axes = False
        has_buttons = False
        try:
            abs_codes = [c[0] for c in dev.capabilities().get(evdev.ecodes.EV_ABS, [])]
        except Exception:
            abs_codes = []
        try:
            key_codes = [c[0] for c in dev.capabilities().get(evdev.ecodes.EV_KEY, [])]
        except Exception:
            key_codes = []
        # check for typical axes and buttons
        if (evdev.ecodes.ABS_Y in abs_codes) and ( (evdev.ecodes.ABS_RY in abs_codes) or (evdev.ecodes.ABS_RX in abs_codes) or (evdev.ecodes.ABS_RZ in abs_codes) ):
            has_axes = True
        if (evdev.ecodes.BTN_SOUTH in key_codes) and (evdev.ecodes.BTN_EAST in key_codes):
            has_buttons = True
        if has_axes and has_buttons:
            candidates.append((path, dev.name))
    # prefer devices with "xbox" or "xinput" in name
    for path, name in candidates:
        if "xbox" in name.lower() or "x-input" in name.lower() or "xinput" in name.lower() or "xbox" in name.lower():
            return path
    if candidates:
        return candidates[0][0]
    # fallback: return None
    return None

# -----------------------------
# Axis normalization helpers
# -----------------------------
def normalize_axis(value, absinfo):
    """
    Normalize raw axis value to -1.0 .. 1.0 (center -> 0).
    absinfo is evdev.AbsInfo with .min and .max
    """
    try:
        amin = absinfo.min
        amax = absinfo.max
    except Exception:
        # fallback common ranges
        amin, amax = -32768, 32767
    center = (amax + amin) / 2.0
    half_range = (amax - amin) / 2.0
    if half_range == 0:
        return 0.0
    return (value - center) / half_range

def normalize_trigger(value, absinfo):
    """
    Normalize trigger raw value to 0.0 .. 1.0 (released -> 0).
    """
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
# Main event loop
# -----------------------------
def main():
    # find controller
    dev_path = find_gamepad_device()
    if not dev_path:
        print("No suitable gamepad device found. Available devices:")
        for p in evdev.list_devices():
            d = InputDevice(p)
            print(f"  {p} : {d.name}")
        print("If your controller is listed, set TARGET_DEVICE to its path and re-run.")
        cleanup_and_exit(1)

    print("Using controller device:", dev_path)
    dev = InputDevice(dev_path)
    try:
        dev.grab()
    except Exception as e:
        print("Warning: could not grab device exclusively:", e)

    # store latest axis values
    axis_state = {
        'left_y': 0.0,   # -1..1 (up positive)
        'right_y': 0.0,  # -1..1 (up positive)
        'lt': 0.0,       # 0..1
        'rt': 0.0        # 0..1
    }

    # map which ABS codes to use (detect available)
    abs_map = {}
    caps = dev.capabilities()
    abs_codes = [c for c in caps.get(evdev.ecodes.EV_ABS, [])]
    # Build a set of available ABS codes
    available_abs = set(code for code, info in abs_codes)
    # prefer standard codes
    if evdev.ecodes.ABS_Y in available_abs:
        abs_map['left_y'] = evdev.ecodes.ABS_Y
    if evdev.ecodes.ABS_RY in available_abs:
        abs_map['right_y'] = evdev.ecodes.ABS_RY
    elif evdev.ecodes.ABS_RZ in available_abs:
        abs_map['right_y'] = evdev.ecodes.ABS_RZ
    elif evdev.ecodes.ABS_RX in available_abs:
        abs_map['right_y'] = evdev.ecodes.ABS_RX

    # triggers
    if evdev.ecodes.ABS_Z in available_abs:
        abs_map['lt'] = evdev.ecodes.ABS_Z
    if evdev.ecodes.ABS_RZ in available_abs:
        abs_map['rt'] = evdev.ecodes.ABS_RZ
    # some controllers use ABS_BRAKE / ABS_THROTTLE
    if 'lt' not in abs_map and evdev.ecodes.ABS_BRAKE in available_abs:
        abs_map['lt'] = evdev.ecodes.ABS_BRAKE
    if 'rt' not in abs_map and evdev.ecodes.ABS_THROTTLE in available_abs:
        abs_map['rt'] = evdev.ecodes.ABS_THROTTLE

    # If right_y not found, try ABS_Y2 style (rare)
    if 'right_y' not in abs_map:
        # try ABS_RY fallback to ABS_Y (use right stick not available)
        if evdev.ecodes.ABS_Y in available_abs:
            abs_map['right_y'] = evdev.ecodes.ABS_Y

    print("ABS mapping:", abs_map)

    # Pre-fetch absinfo for normalization
    absinfo_cache = {}
    for name, code in abs_map.items():
        try:
            absinfo_cache[code] = dev.absinfo(code)
        except Exception:
            # fallback default
            absinfo_cache[code] = type("A", (), {"min": -32768, "max": 32767})

    print("Ready. Use left stick (up/down) for Motor A, right stick for Motor B.")
    print("Left trigger -> Servo B, Right trigger -> Servo A, A -> Servo C, B -> Moisture read.")
    print("Press Ctrl+C to exit.")

    # Button state for Servo C (A button)
    servo_c_active = False

    try:
        for event in dev.read_loop():
            if event.type == evdev.ecodes.EV_ABS:
                code = event.code
                val = event.value
                # left stick vertical
                if 'left_y' in abs_map and code == abs_map['left_y']:
                    # normalize so pushing up -> positive
                    n = normalize_axis(val, absinfo_cache[code])
                    # invert because many controllers: up -> negative raw
                    n = -n
                    # deadzone
                    if abs(n) < 0.05:
                        n = 0.0
                    axis_state['left_y'] = max(-1.0, min(1.0, n))
                    # apply to motor A
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
                    # map to servo B angle 0..180
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
                keystate = event.value  # 1 = down/press, 0 = up, 2 = hold
                # Button A -> BTN_SOUTH -> servo C while held
                if keycode == evdev.ecodes.BTN_SOUTH:
                    if keystate == 1:  # pressed
                        servo_c_active = True
                        set_servo_pwm(servo_c_pwm, 90)
                    elif keystate == 0:  # released
                        servo_c_active = False
                        set_servo_pwm(servo_c_pwm, 0)
                # Button B -> BTN_EAST -> moisture routine on press
                elif keycode == evdev.ecodes.BTN_EAST and keystate == 1:
                    # run moisture routine (non-blocking if you want; here we run synchronously)
                    moisture_routine()
                # Optional: handle start/back to stop motors or exit
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
        servo_a_pwm.stop()
        servo_b_pwm.stop()
        servo_c_pwm.stop()
        motor_pwm_a.stop()
        motor_pwm_b.stop()
        GPIO.cleanup()
    except Exception:
        pass
    sys.exit(code)

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    main()

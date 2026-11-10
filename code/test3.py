#!/usr/bin/env python3

import sys
import time
import evdev
from evdev import InputDevice, ecodes
import RPi.GPIO as GPIO

# ADS1115
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

ADS_CHANNEL = 0

# -----------------------------
# GPIO assignments (FINAL)
# -----------------------------

# Servos
SERVO_A_PIN = 5
SERVO_B_PIN = 6
SERVO_C_PIN = 18

# L298N1 (Pump + Motor A)
PUMP_IN1 = 19
PUMP_IN2 = 26
PUMP_EN  = 21       # Pump PWM

M1_IN1 = 22         # Motor A direction
M1_IN2 = 23
M1_EN  = 13         # Motor A PWM

# L298N2 (Motor B)
M2_IN1 = 17
M2_IN2 = 27
M2_EN  = 12         # Motor B PWM

MOTOR_PWM_FREQ = 1000
SERVO_PWM_FREQ = 50

# -----------------------------
# Controller auto-detection
# -----------------------------
def find_controller():
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        name = dev.name.lower()
        if "xbox" in name or "wireless" in name or "gamepad" in name:
            return path
    return None

# -----------------------------
# Helper functions
# -----------------------------
def angle_to_duty(angle):
    return 2.0 + (angle / 18.0)

def set_servo_pwm(servo_pwm, angle):
    angle = max(0, min(180, angle))
    duty = angle_to_duty(angle)
    servo_pwm.ChangeDutyCycle(duty)
    time.sleep(0.02)
    servo_pwm.ChangeDutyCycle(0)

# -----------------------------
# Motor control
# -----------------------------
def set_motor_a(speed):
    if speed > 0:
        GPIO.output(M1_IN1, 1)
        GPIO.output(M1_IN2, 0)
        motor_pwm_a.ChangeDutyCycle(speed * 100)
    elif speed < 0:
        GPIO.output(M1_IN1, 0)
        GPIO.output(M1_IN2, 1)
        motor_pwm_a.ChangeDutyCycle(abs(speed) * 100)
    else:
        GPIO.output(M1_IN1, 0)
        GPIO.output(M1_IN2, 0)
        motor_pwm_a.ChangeDutyCycle(0)

def set_motor_b(speed):
    if speed > 0:
        GPIO.output(M2_IN1, 1)
        GPIO.output(M2_IN2, 0)
        motor_pwm_b.ChangeDutyCycle(speed * 100)
    elif speed < 0:
        GPIO.output(M2_IN1, 0)
        GPIO.output(M2_IN2, 1)
        motor_pwm_b.ChangeDutyCycle(abs(speed) * 100)
    else:
        GPIO.output(M2_IN1, 0)
        GPIO.output(M2_IN2, 0)
        motor_pwm_b.ChangeDutyCycle(0)

def set_pump(on):
    if on:
        GPIO.output(PUMP_IN1, 1)
        GPIO.output(PUMP_IN2, 0)
        pump_pwm.ChangeDutyCycle(100)
    else:
        GPIO.output(PUMP_IN1, 0)
        GPIO.output(PUMP_IN2, 0)
        pump_pwm.ChangeDutyCycle(0)

# -----------------------------
# Moisture routine
# -----------------------------
q_running = False

def moisture_routine():
    global q_running
    if q_running:
        return
    q_running = True

    try:
        set_motor_a(0)
        set_motor_b(0)

        set_servo_pwm(servo_a_pwm, 180)
        time.sleep(0.4)

        value = chan.value
        print("Moisture:", value)

        if value < 15000:
            set_servo_pwm(servo_b_pwm, 0)
        else:
            set_servo_pwm(servo_b_pwm, 90)

        set_servo_pwm(servo_a_pwm, 0)
        time.sleep(0.2)

    finally:
        q_running = False

# -----------------------------
# Startup test sequence
# -----------------------------
def startup_test():
    print("Running startup test...")

    print("Motor A forward")
    set_motor_a(1)
    time.sleep(2)
    set_motor_a(0)

    print("Motor B forward")
    set_motor_b(1)
    time.sleep(2)
    set_motor_b(0)

    print("Pump ON")
    set_pump(True)
    time.sleep(1)
    set_pump(False)

    print("Servo A")
    set_servo_pwm(servo_a_pwm, 90)
    time.sleep(1)
    set_servo_pwm(servo_a_pwm, 0)

    print("Servo B")
    set_servo_pwm(servo_b_pwm, 90)
    time.sleep(1)
    set_servo_pwm(servo_b_pwm, 0)

    print("Servo C")
    set_servo_pwm(servo_c_pwm, 90)
    time.sleep(1)
    set_servo_pwm(servo_c_pwm, 0)

    print("Startup test complete.")

# -----------------------------
# Axis normalization
# -----------------------------
def normalize_axis(value, info):
    amin, amax = info.min, info.max
    center = (amin + amax) / 2
    half = (amax - amin) / 2
    if half == 0:
        return 0
    return (value - center) / half

def normalize_trigger(value, info):
    amin, amax = info.min, info.max
    if amax == amin:
        return 0
    return (value - amin) / (amax - amin)

# -----------------------------
# Controller mapping
# -----------------------------
def build_abs_map(dev):
    caps = dev.capabilities()
    abs_entries = caps.get(ecodes.EV_ABS, [])
    available = {code for code, info in abs_entries}

    abs_map = {}

    if ecodes.ABS_Y in available:
        abs_map['left_y'] = ecodes.ABS_Y

    for cand in (ecodes.ABS_RY, ecodes.ABS_RX, ecodes.ABS_RZ):
        if cand in available:
            abs_map['right_y'] = cand
            break

    for cand in (ecodes.ABS_Z, ecodes.ABS_BRAKE, ecodes.ABS_THROTTLE):
        if cand in available:
            abs_map['lt'] = cand
            break

    for cand in (ecodes.ABS_RZ, ecodes.ABS_RX, ecodes.ABS_RY):
        if cand in available and cand != abs_map.get('right_y'):
            abs_map['rt'] = cand
            break

    return abs_map

# -----------------------------
# Main loop
# -----------------------------
def main():
    # Find controller
    device_path = find_controller()
    if device_path is None:
        print("No controller found.")
        sys.exit(1)

    dev = InputDevice(device_path)
    dev.grab()
    print(f"Controller detected at {device_path}")

    # GPIO setup
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # L298N1
    for p in (PUMP_IN1, PUMP_IN2, M1_IN1, M1_IN2):
        GPIO.setup(p, GPIO.OUT)
        GPIO.output(p, 0)

    GPIO.setup(PUMP_EN, GPIO.OUT)
    GPIO.setup(M1_EN, GPIO.OUT)
    global pump_pwm, motor_pwm_a
    pump_pwm = GPIO.PWM(PUMP_EN, MOTOR_PWM_FREQ)
    motor_pwm_a = GPIO.PWM(M1_EN, MOTOR_PWM_FREQ)
    pump_pwm.start(0)
    motor_pwm_a.start(0)

    # L298N2
    for p in (M2_IN1, M2_IN2):
        GPIO.setup(p, GPIO.OUT)
        GPIO.output(p, 0)

    GPIO.setup(M2_EN, GPIO.OUT)
    global motor_pwm_b
    motor_pwm_b = GPIO.PWM(M2_EN, MOTOR_PWM_FREQ)
    motor_pwm_b.start(0)

    # Servos
    for p in (SERVO_A_PIN, SERVO_B_PIN, SERVO_C_PIN):
        GPIO.setup(p, GPIO.OUT)

    global servo_a_pwm, servo_b_pwm, servo_c_pwm
    servo_a_pwm = GPIO.PWM(SERVO_A_PIN, SERVO_PWM_FREQ)
    servo_b_pwm = GPIO.PWM(SERVO_B_PIN, SERVO_PWM_FREQ)
    servo_c_pwm = GPIO.PWM(SERVO_C_PIN, SERVO_PWM_FREQ)
    servo_a_pwm.start(0)
    servo_b_pwm.start(0)
    servo_c_pwm.start(0)

    # ADS1115
    i2c = busio.I2C(board.SCL, board.SDA)
    global chan
    ads = ADS.ADS1115(i2c)
    chan = AnalogIn(ads, ADS_CHANNEL)

    # Run startup test
    startup_test()

    # Controller mapping
    abs_map = build_abs_map(dev)
    absinfo = {code: dev.absinfo(code) for code in abs_map.values()}
    axis_state = {'left_y': 0, 'right_y': 0, 'lt': 0, 'rt': 0}

    print("Controller ready.")

    try:
        for event in dev.read_loop():

            if event.type == ecodes.EV_ABS:
                code = event.code
                val = event.value

                if code == abs_map.get('left_y'):
                    n = -normalize_axis(val, absinfo[code])
                    axis_state['left_y'] = 0 if abs(n) < 0.05 else n
                    set_motor_a(axis_state['left_y'])

                elif code == abs_map.get('right_y'):
                    n = -normalize_axis(val, absinfo[code])
                    axis_state['right_y'] = 0 if abs(n) < 0.05 else n
                    set_motor_b(axis_state['right_y'])

                elif code == abs_map.get('lt'):
                    t = normalize_trigger(val, absinfo[code])
                    set_servo_pwm(servo_b_pwm, t * 180)

                elif code == abs_map.get('rt'):
                    t = normalize_trigger(val, absinfo[code])
                    set_servo_pwm(servo_a_pwm, t * 180)

            elif event.type == ecodes.EV_KEY:
                key = event.code
                state = event.value

                if key == ecodes.BTN_SOUTH and state == 1:
                    moisture_routine()

                elif key == ecodes.BTN_EAST:
                    set_pump(state == 1)

                elif key == ecodes.BTN_NORTH:
                    if state == 1:
                        set_servo_pwm(servo_c_pwm, 90)
                    else:
                        set_servo_pwm(servo_c_pwm, 0)

    except KeyboardInterrupt:
        pass
    finally:
        dev.ungrab()
        GPIO.cleanup()

if __name__ == "__main__":
    main()

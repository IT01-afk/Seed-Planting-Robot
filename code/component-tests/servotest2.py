#!/usr/bin/env python3

import time
import pygame
import pigpio

# -----------------------------
# SERVO PINS
# -----------------------------
SERVO_A = 5
SERVO_B = 6
SERVO_C = 18

SERVO_MIN = 500
SERVO_MAX = 2500

# -----------------------------
# SETUP PIGPIO
# -----------------------------
pi = pigpio.pi()
if not pi.connected:
    print("❌ pigpio not running. Start with: sudo pigpiod")
    exit()

for pin in (SERVO_A, SERVO_B, SERVO_C):
    pi.set_mode(pin, pigpio.OUTPUT)
    pi.set_servo_pulsewidth(pin, 0)

# -----------------------------
# SETUP CONTROLLER
# -----------------------------
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("❌ No controller found")
    exit()

joy = pygame.joystick.Joystick(0)
joy.init()
print(f"🎮 Controller detected: {joy.get_name()}")

# -----------------------------
# MAIN LOOP
# -----------------------------
print("Move LT/RT to control servos. Press X to test Servo C.")

try:
    while True:
        pygame.event.pump()

        # Left Trigger (axis 2)
        lt = joy.get_axis(2)
        if lt < -0.1: lt = 0  # some controllers invert
        lt_val = int(SERVO_MIN + (lt * (SERVO_MAX - SERVO_MIN)))
        pi.set_servo_pulsewidth(SERVO_A, lt_val)
        print(f"Servo A (LT): {lt_val}us")

        # Right Trigger (axis 5)
        rt = joy.get_axis(5)
        if rt < -0.1: rt = 0
        rt_val = int(SERVO_MIN + (rt * (SERVO_MAX - SERVO_MIN)))
        pi.set_servo_pulsewidth(SERVO_B, rt_val)
        print(f"Servo B (RT): {rt_val}us")

        # X button → test Servo C
        if joy.get_button(2):
            print("Servo C test pulse")
            pi.set_servo_pulsewidth(SERVO_C, SERVO_MAX)
            time.sleep(0.3)
            pi.set_servo_pulsewidth(SERVO_C, SERVO_MIN)
            time.sleep(0.3)
            pi.set_servo_pulsewidth(SERVO_C, 0)

        time.sleep(0.05)

except KeyboardInterrupt:
    pass

finally:
    pi.set_servo_pulsewidth(SERVO_A, 0)
    pi.set_servo_pulsewidth(SERVO_B, 0)
    pi.set_servo_pulsewidth(SERVO_C, 0)
    pi.stop()
    pygame.quit()

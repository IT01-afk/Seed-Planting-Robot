#!/usr/bin/env python3

import time
import sys
import threading
import glob
from typing import Optional
import RPi.GPIO as GPIO
import pygame
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from evdev import InputDevice, categorize, ecodes

# ============================================================================
# GPIO PIN CONFIGURATION
# ============================================================================

# L298N Motor Driver #1 (Pump + Motor A)
PUMP_IN1 = 19
PUMP_IN2 = 26
PUMP_ENA = 21

MOTOR_A_IN3 = 22
MOTOR_A_IN4 = 23
MOTOR_A_ENB = 13

# L298N Motor Driver #2 (Motor B)
MOTOR_B_IN1 = 17
MOTOR_B_IN2 = 27
MOTOR_B_ENA = 12

# Servo pins
SERVO_A = 5   # Moisture probe
SERVO_B = 6   # Indicator (optional)
SERVO_C = 18  # Seed servo

# Servo PWM duty cycles
SERVO_MIN = 2.5
SERVO_MID = 7.5
SERVO_MAX = 12.5

# Moisture thresholds
MOISTURE_DRY = 20000
MOISTURE_WET = 10000

# ============================================================================
# ESC LISTENER USING EVDEV
# ============================================================================

class EscListener:
    def __init__(self):
        self.escape_pressed = False
        self.device = None

        for path in glob.glob('/dev/input/event*'):
            try:
                dev = InputDevice(path)
                if "kbd" in dev.name.lower() or "keyboard" in dev.name.lower():
                    self.device = InputDevice(path)
                    print(f"ESC listening on {path}")
                    break
            except:
                pass

        if self.device:
            thread = threading.Thread(target=self._listen, daemon=True)
            thread.start()

    def _listen(self):
        for event in self.device.read_loop():
            if event.type == ecodes.EV_KEY:
                key = categorize(event)
                if key.keycode == "KEY_ESC" and key.keystate == 1:
                    print("⏹ ESC pressed — stopping robot")
                    self.escape_pressed = True
                    break

# ============================================================================
# ROBOT CLASS
# ============================================================================

class SeedPlantingRobot:
    def __init__(self):
        self.running = False
        self.controller = None
        self.moisture_channel = None

    # --------------------------------------------------------------
    # SETUP
    # --------------------------------------------------------------

    def setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # DC motor pins
        for p in [
            PUMP_IN1, PUMP_IN2, PUMP_ENA,
            MOTOR_A_IN3, MOTOR_A_IN4, MOTOR_A_ENB,
            MOTOR_B_IN1, MOTOR_B_IN2, MOTOR_B_ENA
        ]:
            GPIO.setup(p, GPIO.OUT)
            GPIO.output(p, GPIO.LOW)

        # Servo pins
        GPIO.setup(SERVO_A, GPIO.OUT)
        GPIO.setup(SERVO_B, GPIO.OUT)
        GPIO.setup(SERVO_C, GPIO.OUT)

        # Motor PWM
        self.motor_a_pwm = GPIO.PWM(MOTOR_A_ENB, 1000)
        self.motor_b_pwm = GPIO.PWM(MOTOR_B_ENA, 1000)
        self.pump_pwm = GPIO.PWM(PUMP_ENA, 1000)

        self.motor_a_pwm.start(0)
        self.motor_b_pwm.start(0)
        self.pump_pwm.start(0)

        # Servo PWM objects (used only during movement)
        self.servo_a_pwm = GPIO.PWM(SERVO_A, 50)
        self.servo_b_pwm = GPIO.PWM(SERVO_B, 50)
        self.servo_c_pwm = GPIO.PWM(SERVO_C, 50)

    def setup_i2c(self):
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            ads = ADS.ADS1115(i2c)
            self.moisture_channel = AnalogIn(ads, ADS.P0)
        except:
            self.moisture_channel = None

    def detect_controller(self):
        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            print("❌ No controller detected!")
            return False

        self.controller = pygame.joystick.Joystick(0)
        self.controller.init()

        print("🎮 Controller:", self.controller.get_name())
        return True

    # --------------------------------------------------------------
    # JITTER‑FREE SERVO MOVEMENT
    # --------------------------------------------------------------

    def servo_move(self, pwm, pin, duty):
        pwm.start(duty)
        time.sleep(0.3)       # allow servo to reach angle
        pwm.ChangeDutyCycle(0)
        GPIO.output(pin, GPIO.LOW)   # remove PWM — prevents jitter

    # --------------------------------------------------------------
    # COMPONENT TEST
    # --------------------------------------------------------------

    def test_components(self):
        print("🧪 Testing components...")

        print("Motor A")
        GPIO.output(MOTOR_A_IN3, GPIO.HIGH)
        GPIO.output(MOTOR_A_IN4, GPIO.LOW)
        self.motor_a_pwm.ChangeDutyCycle(50)
        time.sleep(1)
        self.motor_a_pwm.ChangeDutyCycle(0)
        GPIO.output(MOTOR_A_IN3, GPIO.LOW)

        print("Motor B")
        GPIO.output(MOTOR_B_IN1, GPIO.HIGH)
        GPIO.output(MOTOR_B_IN2, GPIO.LOW)
        self.motor_b_pwm.ChangeDutyCycle(50)
        time.sleep(1)
        self.motor_b_pwm.ChangeDutyCycle(0)
        GPIO.output(MOTOR_B_IN1, GPIO.LOW)

        print("Pump")
        GPIO.output(PUMP_IN1, GPIO.HIGH)
        GPIO.output(PUMP_IN2, GPIO.LOW)
        self.pump_pwm.ChangeDutyCycle(100)
        time.sleep(1)
        self.pump_pwm.ChangeDutyCycle(0)
        GPIO.output(PUMP_IN1, GPIO.LOW)

        print("Servo A")
        self.servo_move(self.servo_a_pwm, SERVO_A, SERVO_MIN)
        self.servo_move(self.servo_a_pwm, SERVO_A, SERVO_MAX)

        print("Servo B")
        self.servo_move(self.servo_b_pwm, SERVO_B, SERVO_MIN)
        self.servo_move(self.servo_b_pwm, SERVO_B, SERVO_MAX)

        print("Servo C")
        self.servo_move(self.servo_c_pwm, SERVO_C, SERVO_MIN)
        self.servo_move(self.servo_c_pwm, SERVO_C, SERVO_MAX)

        print("Moisture test")
        if self.moisture_channel:
            print("Moisture:", self.moisture_channel.value)

    # --------------------------------------------------------------
    # ROUTINES
    # --------------------------------------------------------------

    def full_moisture_routine(self):
        print("🌱 Moisture routine...")
        self.servo_move(self.servo_a_pwm, SERVO_A, SERVO_MAX)

        if self.moisture_channel:
            print("Moisture:", self.moisture_channel.value)

        self.servo_move(self.servo_a_pwm, SERVO_A, SERVO_MIN)
        self.servo_move(self.servo_a_pwm, SERVO_A, SERVO_MID)

    def seed_cycle(self):
        print("🌾 Seed drop...")
        self.servo_move(self.servo_c_pwm, SERVO_C, SERVO_MAX)
        self.servo_move(self.servo_c_pwm, SERVO_C, SERVO_MIN)
        self.servo_move(self.servo_c_pwm, SERVO_C, SERVO_MID)

    def water_once(self):
        print("💧 Watering...")
        GPIO.output(PUMP_IN1, GPIO.HIGH)
        GPIO.output(PUMP_IN2, GPIO.LOW)
        self.pump_pwm.ChangeDutyCycle(100)
        time.sleep(1)
        self.pump_pwm.ChangeDutyCycle(0)
        GPIO.output(PUMP_IN1, GPIO.LOW)

    # --------------------------------------------------------------
    # MOTOR CONTROL
    # --------------------------------------------------------------

    def drive_left_motor(self, speed):
        if speed > 0:
            GPIO.output(MOTOR_A_IN3, GPIO.HIGH)
            GPIO.output(MOTOR_A_IN4, GPIO.LOW)
        elif speed < 0:
            GPIO.output(MOTOR_A_IN3, GPIO.LOW)
            GPIO.output(MOTOR_A_IN4, GPIO.HIGH)
        else:
            GPIO.output(MOTOR_A_IN3, GPIO.LOW)
            GPIO.output(MOTOR_A_IN4, GPIO.LOW)

        self.motor_a_pwm.ChangeDutyCycle(min(abs(speed), 100))

    def drive_right_motor(self, speed):
        if speed > 0:
            GPIO.output(MOTOR_B_IN1, GPIO.HIGH)
            GPIO.output(MOTOR_B_IN2, GPIO.LOW)
        elif speed < 0:
            GPIO.output(MOTOR_B_IN1, GPIO.LOW)
            GPIO.output(MOTOR_B_IN2, GPIO.HIGH)
        else:
            GPIO.output(MOTOR_B_IN1, GPIO.LOW)
            GPIO.output(MOTOR_B_IN2, GPIO.LOW)

        self.motor_b_pwm.ChangeDutyCycle(min(abs(speed), 100))

    # --------------------------------------------------------------
    # CONTROLLER INPUT
    # --------------------------------------------------------------

    def process_controller_input(self):
        pygame.event.pump()

        left_raw = self.controller.get_axis(1)
        right_raw = self.controller.get_axis(3)

        if abs(left_raw) < 0.2:
            left_raw = 0
        if abs(right_raw) < 0.2:
            right_raw = 0

        left_speed = int(-left_raw * 100)
        right_speed = int(-right_raw * 100)

        self.drive_left_motor(left_speed)
        self.drive_right_motor(right_speed)

        if self.controller.get_button(0):  # A
            self.full_moisture_routine()

        if self.controller.get_button(2):  # X
            self.seed_cycle()

        if self.controller.get_button(3):  # Y
            self.water_once()

    # --------------------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------------------

    def run(self):
        self.running = True
        esc = EscListener()
        clock = pygame.time.Clock()

        while self.running:
            if esc.escape_pressed:
                break

            self.process_controller_input()
            clock.tick(60)

        self.shutdown()

    # --------------------------------------------------------------
    # SHUTDOWN
    # --------------------------------------------------------------

    def shutdown(self):
        print("🔌 Shutting down...")
        self.motor_a_pwm.ChangeDutyCycle(0)
        self.motor_b_pwm.ChangeDutyCycle(0)
        self.pump_pwm.ChangeDutyCycle(0)

        GPIO.cleanup()
        pygame.quit()

# ============================================================================
# MAIN
# ============================================================================

def main():
    robot = SeedPlantingRobot()
    robot.setup_gpio()
    robot.setup_i2c()

    if not robot.detect_controller():
        GPIO.cleanup()
        sys.exit(1)

    robot.test_components()
    robot.run()

if __name__ == "__main__":
    main()

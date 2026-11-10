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
SERVO_B = 6   # Moisture indicator (optional)
SERVO_C = 18  # Seed servo

# PWM Frequencies
MOTOR_PWM_FREQ = 1000
SERVO_PWM_FREQ = 50

# Servo angles
SERVO_MIN = 2.5
SERVO_MID = 7.5
SERVO_MAX = 12.5

# Moisture thresholds
MOISTURE_DRY = 20000
MOISTURE_WET = 10000

# ============================================================================
# ESC KEY DETECTION (EVDEV)
# ============================================================================

class EscListener:
    def __init__(self):
        self.escape_pressed = False
        self.device = None

        # find keyboard event device
        for path in glob.glob('/dev/input/event*'):
            try:
                d = InputDevice(path)
                if ("kbd" in d.name.lower()) or ("keyboard" in d.name.lower()):
                    self.device = InputDevice(path)
                    print(f"ESC key listening on {path} ({d.name})")
                    break
            except:
                pass

        if self.device:
            t = threading.Thread(target=self._listen, daemon=True)
            t.start()
        else:
            print("⚠ No keyboard device found. ESC will NOT work.")

    def _listen(self):
        for event in self.device.read_loop():
            if event.type == ecodes.EV_KEY:
                key = categorize(event)
                if key.keycode == 'KEY_ESC' and key.keystate == 1:
                    print("⏹ ESC pressed — shutting down...")
                    self.escape_pressed = True
                    break

# ============================================================================
# MAIN ROBOT CLASS
# ============================================================================

class SeedPlantingRobot:
    def __init__(self):
        self.running = False
        self.controller = None
        self.ads = None
        self.moisture_channel = None

    # --------------------------------------------------------------
    # SETUP
    # --------------------------------------------------------------

    def setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        for p in [
            PUMP_IN1, PUMP_IN2, PUMP_ENA,
            MOTOR_A_IN3, MOTOR_A_IN4, MOTOR_A_ENB,
            MOTOR_B_IN1, MOTOR_B_IN2, MOTOR_B_ENA
        ]:
            GPIO.setup(p, GPIO.OUT)
            GPIO.output(p, GPIO.LOW)

        for p in [SERVO_A, SERVO_B, SERVO_C]:
            GPIO.setup(p, GPIO.OUT)

        self.pump_pwm = GPIO.PWM(PUMP_ENA, MOTOR_PWM_FREQ)
        self.motor_a_pwm = GPIO.PWM(MOTOR_A_ENB, MOTOR_PWM_FREQ)
        self.motor_b_pwm = GPIO.PWM(MOTOR_B_ENA, MOTOR_PWM_FREQ)

        self.servo_a_pwm = GPIO.PWM(SERVO_A, SERVO_PWM_FREQ)
        self.servo_b_pwm = GPIO.PWM(SERVO_B, SERVO_PWM_FREQ)
        self.servo_c_pwm = GPIO.PWM(SERVO_C, SERVO_PWM_FREQ)

        self.pump_pwm.start(0)
        self.motor_a_pwm.start(0)
        self.motor_b_pwm.start(0)

        self.servo_a_pwm.start(SERVO_MID)
        self.servo_b_pwm.start(SERVO_MID)
        self.servo_c_pwm.start(SERVO_MID)

    def setup_i2c(self):
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.ads = ADS.ADS1115(i2c, address=0x48)
            self.moisture_channel = AnalogIn(self.ads, ADS.P0)
            return True
        except:
            print("⚠ Could not initialize moisture sensor.")
            return False

    def detect_controller(self):
        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            print("No controller detected.")
            return False

        self.controller = pygame.joystick.Joystick(0)
        self.controller.init()
        print("Controller detected:", self.controller.get_name())
        return True

    # --------------------------------------------------------------
    # TEST COMPONENTS
    # --------------------------------------------------------------

    def test_components(self):
        print("🧪 Running component test...")

        print("Testing Motor A")
        GPIO.output(MOTOR_A_IN3, GPIO.HIGH)
        GPIO.output(MOTOR_A_IN4, GPIO.LOW)
        self.motor_a_pwm.ChangeDutyCycle(50)
        time.sleep(1)
        self.motor_a_pwm.ChangeDutyCycle(0)
        GPIO.output(MOTOR_A_IN3, GPIO.LOW)

        print("Testing Motor B")
        GPIO.output(MOTOR_B_IN1, GPIO.HIGH)
        GPIO.output(MOTOR_B_IN2, GPIO.LOW)
        self.motor_b_pwm.ChangeDutyCycle(50)
        time.sleep(1)
        self.motor_b_pwm.ChangeDutyCycle(0)
        GPIO.output(MOTOR_B_IN1, GPIO.LOW)

        print("Testing Pump")
        GPIO.output(PUMP_IN1, GPIO.HIGH)
        GPIO.output(PUMP_IN2, GPIO.LOW)
        self.pump_pwm.ChangeDutyCycle(100)
        time.sleep(1)
        self.pump_pwm.ChangeDutyCycle(0)
        GPIO.output(PUMP_IN1, GPIO.LOW)

        print("Testing Servo A")
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.4)
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.4)
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MID)

        print("Testing Servo B")
        self.servo_b_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.4)
        self.servo_b_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.4)
        self.servo_b_pwm.ChangeDutyCycle(SERVO_MID)

        print("Testing Servo C")
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.4)
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.4)
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MID)

        print("Testing Moisture Sensor")
        if self.moisture_channel:
            print("Moisture:", self.moisture_channel.value)

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
    # ACTION ROUTINES
    # --------------------------------------------------------------

    def full_moisture_routine(self):
        print("🌱 Moisture routine...")
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.5)

        if self.moisture_channel:
            print("Moisture:", self.moisture_channel.value)

        self.servo_a_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.5)
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MID)

    def seed_cycle(self):
        print("🌾 Seed drop...")
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.5)
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.5)
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MID)

    def water_once(self):
        print("💧 Watering 1 sec...")
        GPIO.output(PUMP_IN1, GPIO.HIGH)
        GPIO.output(PUMP_IN2, GPIO.LOW)
        self.pump_pwm.ChangeDutyCycle(100)
        time.sleep(1)
        self.pump_pwm.ChangeDutyCycle(0)
        GPIO.output(PUMP_IN1, GPIO.LOW)

    # --------------------------------------------------------------
    # CONTROLLER INPUT (GAMESIR NOVA LITE)
    # --------------------------------------------------------------

    def process_controller_input(self):
        pygame.event.pump()

        # Tank drive
        left_raw = self.controller.get_axis(1)   # left stick vertical
        right_raw = self.controller.get_axis(4)  # right stick vertical

        # Deadzone
        if abs(left_raw) < 0.2:
            left_raw = 0
        if abs(right_raw) < 0.2:
            right_raw = 0

        # Convert to motor speeds
        left_speed = int(-left_raw * 100)
        right_speed = int(-right_raw * 100)

        self.drive_left_motor(left_speed)
        self.drive_right_motor(right_speed)

        # Button Actions
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
                self.running = False
                break

            self.process_controller_input()
            clock.tick(60)

        self.shutdown()

    def shutdown(self):
        print("🔌 Shutdown...")
        self.drive_left_motor(0)
        self.drive_right_motor(0)
        self.pump_pwm.ChangeDutyCycle(0)

        self.servo_a_pwm.ChangeDutyCycle(SERVO_MID)
        self.servo_b_pwm.ChangeDutyCycle(SERVO_MID)
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MID)

        time.sleep(0.3)

        self.pump_pwm.stop()
        self.motor_a_pwm.stop()
        self.motor_b_pwm.stop()
        self.servo_a_pwm.stop()
        self.servo_b_pwm.stop()
        self.servo_c_pwm.stop()

        GPIO.cleanup()
        pygame.quit()

# ============================================================================
# MAIN ENTRY
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

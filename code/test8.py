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
import pigpio     # <--- NEW: hardware PWM for servos
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

# Servo pins (hardware PWM with pigpio)
SERVO_A = 5
SERVO_B = 6
SERVO_C = 18

# Moisture thresholds
MOISTURE_DRY = 20000
MOISTURE_WET = 10000

# Servo pulse widths (microseconds)
SERVO_MIN_US = 500
SERVO_MID_US = 1500
SERVO_MAX_US = 2400

# ============================================================================
# ESC KEY LISTENER USING EVDEV
# ============================================================================

class EscListener:
    def __init__(self):
        self.escape_pressed = False
        self.device = None

        for path in glob.glob('/dev/input/event*'):
            try:
                d = InputDevice(path)
                if "kbd" in d.name.lower() or "keyboard" in d.name.lower():
                    self.device = InputDevice(path)
                    print(f"ESC using {path} ({d.name})")
                    break
            except:
                pass

        if self.device:
            thread = threading.Thread(target=self._listen, daemon=True)
            thread.start()
        else:
            print("⚠ ESC not available — keyboard not found")

    def _listen(self):
        for event in self.device.read_loop():
            if event.type == ecodes.EV_KEY:
                key = categorize(event)
                if key.keycode == "KEY_ESC" and key.keystate == 1:
                    print("⏹ ESC pressed — exiting…")
                    self.escape_pressed = True
                    break

# ============================================================================
# ROBOT CLASS
# ============================================================================

class SeedPlantingRobot:
    def __init__(self):
        self.running = False
        self.controller = None
        self.ads = None
        self.moisture_channel = None
        self.pi = pigpio.pi()     # <--- pigpio instance

        if not self.pi.connected:
            print("❌ pigpio daemon not running!")
            sys.exit(1)

    # --------------------------------------------------------------
    # SETUP
    # --------------------------------------------------------------

    def setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # DC motors + pump pins
        for p in [
            PUMP_IN1, PUMP_IN2, PUMP_ENA,
            MOTOR_A_IN3, MOTOR_A_IN4, MOTOR_A_ENB,
            MOTOR_B_IN1, MOTOR_B_IN2, MOTOR_B_ENA
        ]:
            GPIO.setup(p, GPIO.OUT)
            GPIO.output(p, GPIO.LOW)

        # Motor PWM init
        self.pump_pwm = GPIO.PWM(PUMP_ENA, 1000)
        self.motor_a_pwm = GPIO.PWM(MOTOR_A_ENB, 1000)
        self.motor_b_pwm = GPIO.PWM(MOTOR_B_ENA, 1000)

        self.pump_pwm.start(0)
        self.motor_a_pwm.start(0)
        self.motor_b_pwm.start(0)

    def setup_i2c(self):
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.ads = ADS.ADS1115(i2c, address=0x48)
            self.moisture_channel = AnalogIn(self.ads, ADS.P0)
        except:
            print("⚠ Moisture sensor not detected")

    def detect_controller(self):
        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            print("❌ No controller detected")
            return False

        self.controller = pygame.joystick.Joystick(0)
        self.controller.init()
        print("🎮 Controller:", self.controller.get_name())
        return True

    # --------------------------------------------------------------
    # SERVO CONTROL (PIGPIO)
    # --------------------------------------------------------------

    def servo_set(self, pin, pulse):
        self.pi.set_servo_pulsewidth(pin, pulse)

    # --------------------------------------------------------------
    # COMPONENT TEST
    # --------------------------------------------------------------

    def test_components(self):
        print("🧪 Running hardware test…")

        # Motor A
        print("Testing Motor A")
        GPIO.output(MOTOR_A_IN3, GPIO.HIGH)
        GPIO.output(MOTOR_A_IN4, GPIO.LOW)
        self.motor_a_pwm.ChangeDutyCycle(50)
        time.sleep(1)
        GPIO.output(MOTOR_A_IN3, GPIO.LOW)

        # Motor B
        print("Testing Motor B")
        GPIO.output(MOTOR_B_IN1, GPIO.HIGH)
        GPIO.output(MOTOR_B_IN2, GPIO.LOW)
        self.motor_b_pwm.ChangeDutyCycle(50)
        time.sleep(1)
        GPIO.output(MOTOR_B_IN1, GPIO.LOW)

        # Pump
        print("Testing Pump")
        GPIO.output(PUMP_IN1, GPIO.HIGH)
        GPIO.output(PUMP_IN2, GPIO.LOW)
        self.pump_pwm.ChangeDutyCycle(100)
        time.sleep(1)
        GPIO.output(PUMP_IN1, GPIO.LOW)

        # Servo A
        print("Testing Servo A")
        self.servo_set(SERVO_A, SERVO_MIN_US)
        time.sleep(0.4)
        self.servo_set(SERVO_A, SERVO_MAX_US)
        time.sleep(0.4)
        self.servo_set(SERVO_A, SERVO_MID_US)

        # Servo B
        print("Testing Servo B")
        self.servo_set(SERVO_B, SERVO_MIN_US)
        time.sleep(0.4)
        self.servo_set(SERVO_B, SERVO_MAX_US)
        time.sleep(0.4)
        self.servo_set(SERVO_B, SERVO_MID_US)

        # Servo C
        print("Testing Servo C")
        self.servo_set(SERVO_C, SERVO_MIN_US)
        time.sleep(0.4)
        self.servo_set(SERVO_C, SERVO_MAX_US)
        time.sleep(0.4)
        self.servo_set(SERVO_C, SERVO_MID_US)

        # Moisture
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
    # ROUTINES
    # --------------------------------------------------------------

    def full_moisture_routine(self):
        print("🌱 Taking moisture reading...")
        self.servo_set(SERVO_A, SERVO_MAX_US)
        time.sleep(0.5)

        if self.moisture_channel:
            print("Moisture:", self.moisture_channel.value)

        self.servo_set(SERVO_A, SERVO_MIN_US)
        time.sleep(0.5)
        self.servo_set(SERVO_A, SERVO_MID_US)

    def seed_cycle(self):
        print("🌾 Dropping seed...")
        self.servo_set(SERVO_C, SERVO_MAX_US)
        time.sleep(0.5)
        self.servo_set(SERVO_C, SERVO_MIN_US)
        time.sleep(0.5)
        self.servo_set(SERVO_C, SERVO_MID_US)

    def water_once(self):
        print("💧 Watering...")
        GPIO.output(PUMP_IN1, GPIO.HIGH)
        GPIO.output(PUMP_IN2, GPIO.LOW)
        self.pump_pwm.ChangeDutyCycle(100)
        time.sleep(1)
        self.pump_pwm.ChangeDutyCycle(0)
        GPIO.output(PUMP_IN1, GPIO.LOW)

    # --------------------------------------------------------------
    # CONTROLLER INPUT (Gamesir Nova Lite)
    # --------------------------------------------------------------

    def process_controller_input(self):
        pygame.event.pump()

        left_raw = self.controller.get_axis(1)   # left stick
        right_raw = self.controller.get_axis(3)  # right stick (corrected)

        # Deadzone
        if abs(left_raw) < 0.2:
            left_raw = 0
        if abs(right_raw) < 0.2:
            right_raw = 0

        left_speed = int(-left_raw * 100)
        right_speed = int(-right_raw * 100)

        self.drive_left_motor(left_speed)
        self.drive_right_motor(right_speed)

        # Buttons
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

    # --------------------------------------------------------------
    # SHUTDOWN
    # --------------------------------------------------------------

    def shutdown(self):
        print("🔌 Shutting down...")

        self.drive_left_motor(0)
        self.drive_right_motor(0)
        self.pump_pwm.ChangeDutyCycle(0)

        self.servo_set(SERVO_A, 0)
        self.servo_set(SERVO_B, 0)
        self.servo_set(SERVO_C, 0)

        time.sleep(0.3)

        self.pump_pwm.stop()
        self.motor_a_pwm.stop()
        self.motor_b_pwm.stop()

        GPIO.cleanup()
        pygame.quit()
        self.pi.stop()     # <--- turn off pigpio

# ============================================================================
# MAIN ENTRY POINT
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

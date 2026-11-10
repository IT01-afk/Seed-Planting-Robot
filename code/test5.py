#!/usr/bin/env python3

import time
import sys
import threading
from typing import Optional
import RPi.GPIO as GPIO
import pygame
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from pynput import keyboard

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
SERVO_A = 5   # moisture probe
SERVO_B = 6   # moisture indicator (unused now?)
SERVO_C = 18  # seed servo

# PWM Frequencies
MOTOR_PWM_FREQ = 1000
SERVO_PWM_FREQ = 50

# Servo positions
SERVO_MIN = 2.5
SERVO_MID = 7.5
SERVO_MAX = 12.5

# Moisture thresholds
MOISTURE_DRY = 20000
MOISTURE_WET = 10000

# ============================================================================
# ESC KEY LISTENER USING PYNPUT
# ============================================================================

class EscListener:
    def __init__(self):
        self.escape_pressed = False
        self.listener = keyboard.Listener(on_press=self.on_press)
        self.listener.start()

    def on_press(self, key):
        if key == keyboard.Key.esc:
            print("⏹ ESC pressed — shutting down...")
            self.escape_pressed = True
            return False

# ============================================================================
# MAIN ROBOT CLASS
# ============================================================================

class SeedPlantingRobot:
    def __init__(self):
        self.running = False
        self.controller = None
        self.ads = None
        self.moisture_channel = None
        
        self.pump_pwm = None
        self.motor_a_pwm = None
        self.motor_b_pwm = None
        self.servo_a_pwm = None
        self.servo_b_pwm = None
        self.servo_c_pwm = None

    # ----------------------------------------------------------------------
    # SETUP
    # ----------------------------------------------------------------------

    def setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Motor pins
        motor_pins = [
            PUMP_IN1, PUMP_IN2, PUMP_ENA,
            MOTOR_A_IN3, MOTOR_A_IN4, MOTOR_A_ENB,
            MOTOR_B_IN1, MOTOR_B_IN2, MOTOR_B_ENA
        ]
        for p in motor_pins:
            GPIO.setup(p, GPIO.OUT)
            GPIO.output(p, GPIO.LOW)

        # Servo pins
        for p in [SERVO_A, SERVO_B, SERVO_C]:
            GPIO.setup(p, GPIO.OUT)

        # PWM init
        self.pump_pwm = GPIO.PWM(PUMP_ENA, MOTOR_PWM_FREQ)
        self.motor_a_pwm = GPIO.PWM(MOTOR_A_ENB, MOTOR_PWM_FREQ)
        self.motor_b_pwm = GPIO.PWM(MOTOR_B_ENA, MOTOR_PWM_FREQ)

        self.servo_a_pwm = GPIO.PWM(SERVO_A, SERVO_PWM_FREQ)
        self.servo_b_pwm = GPIO.PWM(SERVO_B, SERVO_PWM_FREQ)
        self.servo_c_pwm = GPIO.PWM(SERVO_C, SERVO_PWM_FREQ)

        # Start PWM
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

    # ----------------------------------------------------------------------
    # COMPONENT TEST
    # ----------------------------------------------------------------------

    def test_components(self):
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
        time.sleep(0.5)
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.5)
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MID)

        print("Testing Servo B")
        self.servo_b_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.5)
        self.servo_b_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.5)
        self.servo_b_pwm.ChangeDutyCycle(SERVO_MID)

        print("Testing Servo C")
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.5)
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.5)
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MID)

        print("Testing Moisture Sensor")
        if self.moisture_channel:
            print("Moisture reading:", self.moisture_channel.value)

    # ----------------------------------------------------------------------
    # MOVEMENT
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # SPECIAL ACTIONS
    # ----------------------------------------------------------------------

    def full_moisture_routine(self):
        print("Running moisture routine...")

        # 1. Insert probe
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.5)

        # 2. Read moisture
        if self.moisture_channel:
            val = self.moisture_channel.value
            print("Moisture:", val)

        # 3. Retract probe
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.5)

        # 4. Return to center
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MID)
        print("Moisture routine complete.")

    def seed_cycle(self):
        print("Dropping seed...")
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.5)
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.5)
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MID)

    def water_once(self):
        print("Watering...")
        GPIO.output(PUMP_IN1, GPIO.HIGH)
        GPIO.output(PUMP_IN2, GPIO.LOW)
        self.pump_pwm.ChangeDutyCycle(100)
        time.sleep(1)
        self.pump_pwm.ChangeDutyCycle(0)
        GPIO.output(PUMP_IN1, GPIO.LOW)

    # ----------------------------------------------------------------------
    # CONTROLLER HANDLING
    # ----------------------------------------------------------------------

    def process_controller_input(self):
        pygame.event.pump()

        # Tank drive
        left_axis = -self.controller.get_axis(1)   # left stick vertical
        right_axis = -self.controller.get_axis(4)  # right stick vertical

        left_speed = int(left_axis * 100)
        right_speed = int(right_axis * 100)

        self.drive_left_motor(left_speed)
        self.drive_right_motor(right_speed)

        # A button → full routine
        if self.controller.get_button(0):
            self.full_moisture_routine()

        # X button → seed cycle
        if self.controller.get_button(2):
            self.seed_cycle()

        # Y button → water for 1 sec
        if self.controller.get_button(3):
            self.water_once()

    # ----------------------------------------------------------------------
    # LOOP + SHUTDOWN
    # ----------------------------------------------------------------------

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
        print("Shutting down...")
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

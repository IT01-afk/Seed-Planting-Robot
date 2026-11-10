#!/usr/bin/env python3

import time
import sys
import threading
import glob
import RPi.GPIO as GPIO
import pygame
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from evdev import InputDevice, categorize, ecodes
import pigpio

# ============================================================================
# PIN CONFIGURATION
# ============================================================================

PUMP_IN1 = 19
PUMP_IN2 = 26
PUMP_ENA = 21

MOTOR_A_IN3 = 22
MOTOR_A_IN4 = 23
MOTOR_A_ENB = 13

MOTOR_B_IN1 = 17
MOTOR_B_IN2 = 27
MOTOR_B_ENA = 12

SERVO_A = 5
SERVO_B = 6
SERVO_C = 18

SERVO_MIN = 500
SERVO_MID = 1500
SERVO_MAX = 2500

# ============================================================================
# ESC LISTENER
# ============================================================================

class EscListener:
    def __init__(self):
        self.escape_pressed = False
        self.device = None

        for path in glob.glob('/dev/input/event*'):
            try:
                dev = InputDevice(path)
                if "kbd" in dev.name.lower():
                    self.device = InputDevice(path)
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
                    self.escape_pressed = True
                    break

# ============================================================================
# ROBOT CLASS
# ============================================================================

class SeedPlantingRobot:

    def __init__(self):
        self.running = False
        self.motor_a_pwm = None
        self.motor_b_pwm = None
        self.pump_pwm = None
        self.moisture_channel = None
        self.controller = None

        # Connect to pigpio daemon for servos
        self.pi = pigpio.pi()
        if not self.pi.connected:
            print("❌ Could not connect to pigpio daemon (is pigpiod running?)")
            sys.exit(1)

        # Ensure servo pins are set as outputs in pigpio
        self.pi.set_mode(SERVO_A, pigpio.OUTPUT)
        self.pi.set_mode(SERVO_B, pigpio.OUTPUT)
        self.pi.set_mode(SERVO_C, pigpio.OUTPUT)

        # Start with servos off
        self.pi.set_servo_pulsewidth(SERVO_A, 0)
        self.pi.set_servo_pulsewidth(SERVO_B, 0)
        self.pi.set_servo_pulsewidth(SERVO_C, 0)

    # ------------------------------------------------------------------
    # GPIO SETUP (motors + pump only)
    # ------------------------------------------------------------------

    def setup_gpio(self):

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Pump pins
        GPIO.setup(PUMP_IN1, GPIO.OUT)
        GPIO.setup(PUMP_IN2, GPIO.OUT)
        GPIO.setup(PUMP_ENA, GPIO.OUT)

        # Motor direction pins
        GPIO.setup(MOTOR_A_IN3, GPIO.OUT)
        GPIO.setup(MOTOR_A_IN4, GPIO.OUT)
        GPIO.setup(MOTOR_B_IN1, GPIO.OUT)
        GPIO.setup(MOTOR_B_IN2, GPIO.OUT)

        # Motor enable pins
        GPIO.setup(MOTOR_A_ENB, GPIO.OUT)
        GPIO.setup(MOTOR_B_ENA, GPIO.OUT)

        # Default LOW
        for pin in [
            PUMP_IN1, PUMP_IN2,
            MOTOR_A_IN3, MOTOR_A_IN4,
            MOTOR_B_IN1, MOTOR_B_IN2
        ]:
            GPIO.output(pin, GPIO.LOW)

        # PWM objects for motors and pump
        self.motor_a_pwm = GPIO.PWM(MOTOR_A_ENB, 1000)
        self.motor_b_pwm = GPIO.PWM(MOTOR_B_ENA, 1000)
        self.pump_pwm = GPIO.PWM(PUMP_ENA, 1000)

        self.motor_a_pwm.start(0)
        self.motor_b_pwm.start(0)
        self.pump_pwm.start(0)

    # ------------------------------------------------------------------
    # I2C SETUP
    # ------------------------------------------------------------------

    def setup_i2c(self):
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            ads = ADS.ADS1115(i2c)
            self.moisture_channel = AnalogIn(ads, ADS.P0)
        except:
            self.moisture_channel = None

    # ------------------------------------------------------------------
    # CONTROLLER
    # ------------------------------------------------------------------

    def detect_controller(self):
        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() == 0:
            print("❌ No controller found")
            return False

        self.controller = pygame.joystick.Joystick(0)
        self.controller.init()
        print(f"🎮 Controller detected: {self.controller.get_name()}")
        return True

    # ------------------------------------------------------------------
    # SERVO CONTROL (pigpio, no jitter)
    # ------------------------------------------------------------------

    def servo_move(self, pin, pulse, duration=0.35):
        # pulse in microseconds: 500–2500
        self.pi.set_servo_pulsewidth(pin, pulse)
        time.sleep(duration)
        # Stop sending pulses to avoid jitter
        self.pi.set_servo_pulsewidth(pin, 0)

    # ------------------------------------------------------------------
    # ACTION ROUTINES
    # ------------------------------------------------------------------

    def seed_cycle(self):
        self.servo_move(SERVO_C, SERVO_MAX)
        self.servo_move(SERVO_C, SERVO_MIN)
        self.servo_move(SERVO_C, SERVO_MID)

    def water_once(self):
        GPIO.output(PUMP_IN1, GPIO.HIGH)
        GPIO.output(PUMP_IN2, GPIO.LOW)
        self.pump_pwm.ChangeDutyCycle(100)
        time.sleep(1)
        self.pump_pwm.ChangeDutyCycle(0)
        GPIO.output(PUMP_IN1, GPIO.LOW)

    # ------------------------------------------------------------------
    # MOTOR CONTROL
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # CONTROLLER INPUT
    # ------------------------------------------------------------------

    def process_controller_input(self):

        pygame.event.pump()

        left = -self.controller.get_axis(1)
        right = -self.controller.get_axis(3)

        if abs(left) < 0.2:
            left = 0
        if abs(right) < 0.2:
            right = 0

        self.drive_left_motor(int(left * 100))
        self.drive_right_motor(int(right * 100))

        # Button 2 → seed cycle
        if self.controller.get_button(2):
            self.seed_cycle()

        # Button 3 → water once
        if self.controller.get_button(3):
            self.water_once()

    # ------------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------------

    def run(self):
        esc = EscListener()
        clock = pygame.time.Clock()

        while not esc.escape_pressed:
            self.process_controller_input()
            clock.tick(60)

        self.shutdown()

    def shutdown(self):
        self.drive_left_motor(0)
        self.drive_right_motor(0)
        self.pump_pwm.ChangeDutyCycle(0)

        self.motor_a_pwm.stop()
        self.motor_b_pwm.stop()
        self.pump_pwm.stop()

        # Turn off servos cleanly
        self.pi.set_servo_pulsewidth(SERVO_A, 0)
        self.pi.set_servo_pulsewidth(SERVO_B, 0)
        self.pi.set_servo_pulsewidth(SERVO_C, 0)
        self.pi.stop()

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
        robot.pi.stop()
        sys.exit(1)

    robot.run()

if __name__ == "__main__":
    main()

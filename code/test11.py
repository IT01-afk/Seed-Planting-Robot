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
# GPIO PIN CONFIGURATION
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

# Servo pulse widths (microseconds)
SERVO_MIN = 500
SERVO_MID = 1500
SERVO_MAX = 2500

MOISTURE_DRY = 20000
MOISTURE_WET = 10000

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
                    print(f"ESC listener active on {path}")
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

        # Connect to pigpio daemon
        self.pi = pigpio.pi()
        if not self.pi.connected:
            print("❌ Could not connect to pigpio daemon")
            sys.exit(1)

    # --------------------------------------------------------------
    # SETUP
    # --------------------------------------------------------------

    def setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        for p in [
            PUMP_IN1, PUMP_IN2, PUMP_ENA,
            MOTOR_A_IN3, MOTOR_A_IN4,
            MOTOR_B_IN1, MOTOR_B_IN2
        ]:
            GPIO.setup(p, GPIO.OUT)
            GPIO.output(p, GPIO.LOW)

        # Motor PWM (UNCHANGED)
        self.motor_a_pwm = GPIO.PWM(MOTOR_A_ENB, 1000)
        self.motor_b_pwm = GPIO.PWM(MOTOR_B_ENA, 1000)
        self.pump_pwm = GPIO.PWM(PUMP_ENA, 1000)

        self.motor_a_pwm.start(0)
        self.motor_b_pwm.start(0)
        self.pump_pwm.start(0)

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
            print("❌ No controller found")
            return False

        self.controller = pygame.joystick.Joystick(0)
        self.controller.init()
        print("🎮 Controller detected:", self.controller.get_name())
        return True

    # --------------------------------------------------------------
    # HARDWARE-TIMED SERVO MOVEMENT (NO JITTER)
    # --------------------------------------------------------------

    def servo_move(self, pin, pulse_width, move_time=0.35):
        self.pi.set_servo_pulsewidth(pin, pulse_width)
        time.sleep(move_time)

        # Stop signal completely (removes holding jitter)
        self.pi.set_servo_pulsewidth(pin, 0)

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
        self.servo_move(SERVO_A, SERVO_MIN)
        self.servo_move(SERVO_A, SERVO_MAX)

        print("Servo B")
        self.servo_move(SERVO_B, SERVO_MIN)
        self.servo_move(SERVO_B, SERVO_MAX)

        print("Servo C")
        self.servo_move(SERVO_C, SERVO_MIN)
        self.servo_move(SERVO_C, SERVO_MAX)

    # --------------------------------------------------------------
    # ACTION ROUTINES
    # --------------------------------------------------------------

    def full_moisture_routine(self):
        print("🌱 Taking moisture reading...")
        self.servo_move(SERVO_A, SERVO_MAX)

        if self.moisture_channel:
            print("Moisture:", self.moisture_channel.value)

        self.servo_move(SERVO_A, SERVO_MIN)
        self.servo_move(SERVO_A, SERVO_MID)

    def seed_cycle(self):
        print("🌾 Dropping seed...")
        self.servo_move(SERVO_C, SERVO_MAX)
        self.servo_move(SERVO_C, SERVO_MIN)
        self.servo_move(SERVO_C, SERVO_MID)

    def water_once(self):
        print("💧 Watering...")
        GPIO.output(PUMP_IN1, GPIO.HIGH)
        GPIO.output(PUMP_IN2, GPIO.LOW)
        self.pump_pwm.ChangeDutyCycle(100)
        time.sleep(1)
        self.pump_pwm.ChangeDutyCycle(0)
        GPIO.output(PUMP_IN1, GPIO.LOW)

    # --------------------------------------------------------------
    # MOTOR CONTROL (UNCHANGED)
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
    # CONTROLLER INPUT (UNCHANGED)
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

        if self.controller.get_button(0):
            self.full_moisture_routine()

        if self.controller.get_button(2):
            self.seed_cycle()

        if self.controller.get_button(3):
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
        print("🔌 Shutting down…")
        self.drive_left_motor(0)
        self.drive_right_motor(0)
        self.pump_pwm.ChangeDutyCycle(0)

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
        sys.exit(1)

    robot.test_components()
    robot.run()

if __name__ == "__main__":
    main()
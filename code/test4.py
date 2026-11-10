#!/usr/bin/env python3
"""
Seed Planting Robot Control System
Controls motors, pump, servos, and moisture sensor via USB controller
"""

import time
import sys
import threading
from typing import Optional, Tuple
import RPi.GPIO as GPIO
import pygame
import keyboard
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

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
SERVO_A = 5   # Moisture probe arm
SERVO_B = 6   # Moisture indicator
SERVO_C = 18  # Extra function

# ============================================================================
# SYSTEM CONFIGURATION
# ============================================================================

# PWM Frequencies
MOTOR_PWM_FREQ = 1000
SERVO_PWM_FREQ = 50

# Speed settings (0-100)
DEFAULT_MOTOR_SPEED = 50
MAX_MOTOR_SPEED = 100
PUMP_SPEED = 100

# Servo positions (duty cycles for 50Hz PWM)
SERVO_MIN = 2.5  # 0 degrees
SERVO_MID = 7.5  # 90 degrees
SERVO_MAX = 12.5 # 180 degrees

# Moisture sensor thresholds
MOISTURE_DRY = 20000    # Below this = dry
MOISTURE_WET = 10000    # Above this = wet

# ============================================================================
# ROBOT CONTROLLER CLASS
# ============================================================================

class SeedPlantingRobot:
    def __init__(self):
        """Initialize the robot control system"""
        self.running = False
        self.controller = None
        self.ads = None
        self.moisture_channel = None
        
        # PWM objects
        self.pump_pwm = None
        self.motor_a_pwm = None
        self.motor_b_pwm = None
        self.servo_a_pwm = None
        self.servo_b_pwm = None
        self.servo_c_pwm = None
        
        # Current states
        self.motor_speed = DEFAULT_MOTOR_SPEED
        self.servo_positions = {'A': SERVO_MID, 'B': SERVO_MID, 'C': SERVO_MID}
        self.pump_active = False
        
        print("🤖 Seed Planting Robot Initializing...")
        
    def setup_gpio(self):
        """Initialize GPIO pins and PWM"""
        print("📍 Setting up GPIO pins...")
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Setup motor pins
        motor_pins = [
            PUMP_IN1, PUMP_IN2, PUMP_ENA,
            MOTOR_A_IN3, MOTOR_A_IN4, MOTOR_A_ENB,
            MOTOR_B_IN1, MOTOR_B_IN2, MOTOR_B_ENA
        ]
        for pin in motor_pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
        
        # Setup servo pins
        servo_pins = [SERVO_A, SERVO_B, SERVO_C]
        for pin in servo_pins:
            GPIO.setup(pin, GPIO.OUT)
        
        # Initialize PWM for motors
        self.pump_pwm = GPIO.PWM(PUMP_ENA, MOTOR_PWM_FREQ)
        self.motor_a_pwm = GPIO.PWM(MOTOR_A_ENB, MOTOR_PWM_FREQ)
        self.motor_b_pwm = GPIO.PWM(MOTOR_B_ENA, MOTOR_PWM_FREQ)
        
        # Initialize PWM for servos
        self.servo_a_pwm = GPIO.PWM(SERVO_A, SERVO_PWM_FREQ)
        self.servo_b_pwm = GPIO.PWM(SERVO_B, SERVO_PWM_FREQ)
        self.servo_c_pwm = GPIO.PWM(SERVO_C, SERVO_PWM_FREQ)
        
        # Start PWM with 0 duty cycle
        self.pump_pwm.start(0)
        self.motor_a_pwm.start(0)
        self.motor_b_pwm.start(0)
        self.servo_a_pwm.start(SERVO_MID)
        self.servo_b_pwm.start(SERVO_MID)
        self.servo_c_pwm.start(SERVO_MID)
        
        print("✅ GPIO setup complete")
        
    def setup_i2c(self):
        """Initialize I2C and ADS1115 for moisture sensor"""
        try:
            print("🔌 Setting up I2C and moisture sensor...")
            i2c = busio.I2C(board.SCL, board.SDA)
            self.ads = ADS.ADS1115(i2c, address=0x48)
            self.moisture_channel = AnalogIn(self.ads, ADS.P0)
            print("✅ Moisture sensor ready")
            return True
        except Exception as e:
            print(f"⚠️ Failed to initialize moisture sensor: {e}")
            return False
    
    def detect_controller(self) -> bool:
        """Detect and initialize USB game controller"""
        print("🎮 Searching for USB controller...")
        pygame.init()
        pygame.joystick.init()
        
        if pygame.joystick.get_count() == 0:
            print("❌ No controller detected")
            return False
        
        self.controller = pygame.joystick.Joystick(0)
        self.controller.init()
        controller_name = self.controller.get_name()
        print(f"✅ Controller detected: {controller_name}")
        return True
    
    def test_components(self):
        """Test all components in sequence (1 second each)"""
        print("\n" + "="*50)
        print("🧪 COMPONENT TEST SEQUENCE STARTING")
        print("="*50)
        
        tests = [
            ("Motor A", self.test_motor_a),
            ("Motor B", self.test_motor_b),
            ("Water Pump", self.test_pump),
            ("Servo A (Probe Arm)", self.test_servo_a),
            ("Servo B (Indicator)", self.test_servo_b),
            ("Servo C (Extra)", self.test_servo_c),
            ("Moisture Sensor", self.test_moisture_sensor)
        ]
        
        for name, test_func in tests:
            print(f"\n📋 Testing {name}...")
            test_func()
            time.sleep(0.5)  # Brief pause between tests
        
        print("\n" + "="*50)
        print("✅ COMPONENT TEST COMPLETE")
        print("="*50 + "\n")
    
    def test_motor_a(self):
        """Test Motor A"""
        GPIO.output(MOTOR_A_IN3, GPIO.HIGH)
        GPIO.output(MOTOR_A_IN4, GPIO.LOW)
        self.motor_a_pwm.ChangeDutyCycle(50)
        time.sleep(1)
        self.motor_a_pwm.ChangeDutyCycle(0)
        GPIO.output(MOTOR_A_IN3, GPIO.LOW)
        print("   ✓ Motor A tested")
    
    def test_motor_b(self):
        """Test Motor B"""
        GPIO.output(MOTOR_B_IN1, GPIO.HIGH)
        GPIO.output(MOTOR_B_IN2, GPIO.LOW)
        self.motor_b_pwm.ChangeDutyCycle(50)
        time.sleep(1)
        self.motor_b_pwm.ChangeDutyCycle(0)
        GPIO.output(MOTOR_B_IN1, GPIO.LOW)
        print("   ✓ Motor B tested")
    
    def test_pump(self):
        """Test water pump"""
        GPIO.output(PUMP_IN1, GPIO.HIGH)
        GPIO.output(PUMP_IN2, GPIO.LOW)
        self.pump_pwm.ChangeDutyCycle(100)
        time.sleep(1)
        self.pump_pwm.ChangeDutyCycle(0)
        GPIO.output(PUMP_IN1, GPIO.LOW)
        print("   ✓ Pump tested")
    
    def test_servo_a(self):
        """Test Servo A"""
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.5)
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.5)
        self.servo_a_pwm.ChangeDutyCycle(SERVO_MID)
        print("   ✓ Servo A tested")
    
    def test_servo_b(self):
        """Test Servo B"""
        self.servo_b_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.5)
        self.servo_b_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.5)
        self.servo_b_pwm.ChangeDutyCycle(SERVO_MID)
        print("   ✓ Servo B tested")
    
    def test_servo_c(self):
        """Test Servo C"""
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MIN)
        time.sleep(0.5)
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MAX)
        time.sleep(0.5)
        self.servo_c_pwm.ChangeDutyCycle(SERVO_MID)
        print("   ✓ Servo C tested")
    
    def test_moisture_sensor(self):
        """Test moisture sensor reading"""
        if self.moisture_channel:
            moisture = self.read_moisture()
            status = self.get_moisture_status(moisture)
            print(f"   ✓ Moisture: {moisture} ({status})")
        else:
            print("   ⚠️ Moisture sensor not available")
    
    def read_moisture(self) -> int:
        """Read current moisture level"""
        if self.moisture_channel:
            return self.moisture_channel.value
        return 0
    
    def get_moisture_status(self, value: int) -> str:
        """Convert moisture reading to status"""
        if value > MOISTURE_DRY:
            return "DRY 🏜️"
        elif value < MOISTURE_WET:
            return "WET 💧"
        else:
            return "MOIST 🌱"
    
    def drive_motors(self, left_speed: int, right_speed: int):
        """Control both drive motors"""
        # Motor A (Left)
        if left_speed > 0:
            GPIO.output(MOTOR_A_IN3, GPIO.HIGH)
            GPIO.output(MOTOR_A_IN4, GPIO.LOW)
            self.motor_a_pwm.ChangeDutyCycle(min(abs(left_speed), 100))
        elif left_speed < 0:
            GPIO.output(MOTOR_A_IN3, GPIO.LOW)
            GPIO.output(MOTOR_A_IN4, GPIO.HIGH)
            self.motor_a_pwm.ChangeDutyCycle(min(abs(left_speed), 100))
        else:
            GPIO.output(MOTOR_A_IN3, GPIO.LOW)
            GPIO.output(MOTOR_A_IN4, GPIO.LOW)
            self.motor_a_pwm.ChangeDutyCycle(0)
        
        # Motor B (Right)
        if right_speed > 0:
            GPIO.output(MOTOR_B_IN1, GPIO.HIGH)
            GPIO.output(MOTOR_B_IN2, GPIO.LOW)
            self.motor_b_pwm.ChangeDutyCycle(min(abs(right_speed), 100))
        elif right_speed < 0:
            GPIO.output(MOTOR_B_IN1, GPIO.LOW)
            GPIO.output(MOTOR_B_IN2, GPIO.HIGH)
            self.motor_b_pwm.ChangeDutyCycle(min(abs(right_speed), 100))
        else:
            GPIO.output(MOTOR_B_IN1, GPIO.LOW)
            GPIO.output(MOTOR_B_IN2, GPIO.LOW)
            self.motor_b_pwm.ChangeDutyCycle(0)
    
    def control_pump(self, active: bool):
        """Control water pump"""
        if active:
            GPIO.output(PUMP_IN1, GPIO.HIGH)
            GPIO.output(PUMP_IN2, GPIO.LOW)
            self.pump_pwm.ChangeDutyCycle(PUMP_SPEED)
            self.pump_active = True
        else:
            GPIO.output(PUMP_IN1, GPIO.LOW)
            GPIO.output(PUMP_IN2, GPIO.LOW)
            self.pump_pwm.ChangeDutyCycle(0)
            self.pump_active = False
    
    def move_servo(self, servo: str, position: float):
        """Move specified servo to position"""
        position = max(SERVO_MIN, min(position, SERVO_MAX))
        
        if servo == 'A':
            self.servo_a_pwm.ChangeDutyCycle(position)
        elif servo == 'B':
            self.servo_b_pwm.ChangeDutyCycle(position)
        elif servo == 'C':
            self.servo_c_pwm.ChangeDutyCycle(position)
        
        self.servo_positions[servo] = position
    
    def process_controller_input(self):
        """Process controller input and control robot"""
        pygame.event.pump()
        
        # Get joystick axes (left stick for movement)
        if self.controller.get_numaxes() >= 2:
            x_axis = self.controller.get_axis(0)  # Left/Right
            y_axis = self.controller.get_axis(1)  # Forward/Back
            
            # Calculate motor speeds (tank drive)
            forward = -y_axis * self.motor_speed
            turn = x_axis * self.motor_speed * 0.5
            
            left_speed = int(forward + turn)
            right_speed = int(forward - turn)
            
            # Apply deadzone
            if abs(x_axis) < 0.1 and abs(y_axis) < 0.1:
                left_speed = 0
                right_speed = 0
            
            self.drive_motors(left_speed, right_speed)
        
        # Button controls
        # A button (0) - Water pump
        if self.controller.get_button(0):
            self.control_pump(True)
        else:
            self.control_pump(False)
        
        # B button (1) - Deploy moisture probe
        if self.controller.get_button(1):
            self.move_servo('A', SERVO_MAX)
        
        # X button (2) - Retract moisture probe
        if self.controller.get_button(2):
            self.move_servo('A', SERVO_MIN)
        
        # Y button (3) - Read moisture
        if self.controller.get_button(3):
            moisture = self.read_moisture()
            status = self.get_moisture_status(moisture)
            print(f"💧 Moisture: {moisture} ({status})")
            
            # Move indicator servo based on moisture
            if moisture > MOISTURE_DRY:
                self.move_servo('B', SERVO_MIN)  # Dry position
            elif moisture < MOISTURE_WET:
                self.move_servo('B', SERVO_MAX)  # Wet position
            else:
                self.move_servo('B', SERVO_MID)  # Moist position
        
        # Right trigger - Increase speed
        if self.controller.get_numaxes() > 5:
            right_trigger = self.controller.get_axis(5)
            if right_trigger > 0.5:
                self.motor_speed = min(self.motor_speed + 1, MAX_MOTOR_SPEED)
        
        # Left trigger - Decrease speed
        if self.controller.get_numaxes() > 2:
            left_trigger = self.controller.get_axis(2)
            if left_trigger > 0.5:
                self.motor_speed = max(self.motor_speed - 1, 10)
    
    def keyboard_monitor(self):
        """Monitor keyboard for ESC key"""
        while self.running:
            if keyboard.is_pressed('escape'):
                print("\n⏹️ ESC pressed - Shutting down...")
                self.running = False
                break
            time.sleep(0.1)
    
    def run(self):
        """Main control loop"""
        self.running = True
        
        # Start keyboard monitoring thread
        keyboard_thread = threading.Thread(target=self.keyboard_monitor, daemon=True)
        keyboard_thread.start()
        
        print("\n🎮 CONTROLLER ACTIVE - Robot Ready!")
        print("="*50)
        print("CONTROLS:")
        print("  Left Stick: Drive")
        print("  A: Water pump")
        print("  B: Deploy probe")
        print("  X: Retract probe")
        print("  Y: Read moisture")
        print("  Right Trigger: Speed up")
        print("  Left Trigger: Slow down")
        print("  ESC (keyboard): Exit")
        print("="*50 + "\n")
        
        clock = pygame.time.Clock()
        
        while self.running:
            try:
                self.process_controller_input()
                clock.tick(60)  # 60 FPS control loop
                
            except KeyboardInterrupt:
                print("\n⏹️ Keyboard interrupt - Shutting down...")
                break
            except Exception as e:
                print(f"❌ Error in control loop: {e}")
                break
        
        self.shutdown()
    
    def shutdown(self):
        """Clean shutdown of all systems"""
        print("\n🔧 Shutting down robot systems...")
        
        # Stop all motors
        self.drive_motors(0, 0)
        self.control_pump(False)
        
        # Center all servos
        self.move_servo('A', SERVO_MID)
        self.move_servo('B', SERVO_MID)
        self.move_servo('C', SERVO_MID)
        
        time.sleep(0.5)
        
        # Stop PWM
        if self.pump_pwm:
            self.pump_pwm.stop()
        if self.motor_a_pwm:
            self.motor_a_pwm.stop()
        if self.motor_b_pwm:
            self.motor_b_pwm.stop()
        if self.servo_a_pwm:
            self.servo_a_pwm.stop()
        if self.servo_b_pwm:
            self.servo_b_pwm.stop()
        if self.servo_c_pwm:
            self.servo_c_pwm.stop()
        
        # Cleanup GPIO
        GPIO.cleanup()
        
        # Quit pygame
        if self.controller:
            self.controller.quit()
        pygame.quit()
        
        print("✅ Shutdown complete. Goodbye! 👋")

# ============================================================================
# MAIN PROGRAM
# ============================================================================

def main():
    """Main program entry point"""
    print("="*50)
    print("🌱 SEED PLANTING ROBOT v1.0")
    print("="*50)
    
    robot = SeedPlantingRobot()
    
    try:
        # Setup hardware
        robot.setup_gpio()
        robot.setup_i2c()
        
        # Detect controller
        if not robot.detect_controller():
            print("\n❌ No controller detected. Please connect a USB controller.")
            print("Exiting...")
            GPIO.cleanup()
            sys.exit(1)
        
        # Run component tests
        robot.test_components()
        
        # Start main control loop
        robot.run()
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        robot.shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main()

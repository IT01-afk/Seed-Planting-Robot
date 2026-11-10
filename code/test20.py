import pigpio
import time
import smbus2
import sys

# ========================
# GPIO PIN MAPPING
# ========================

SERVO_1_PIN = 12       # Pan servo
SERVO_2_PIN = 13       # Tilt servo
PUMP_PIN    = 18       # Water pump relay/MOSFET

# ========================
# I2C SETUP (Soil Sensor)
# ========================

# ========================
# I2C SETUP (ADS1115 ADC)
# ========================

import smbus2
import struct

I2C_BUS = 1
ADC_ADDR = 0x48

bus = smbus2.SMBus(I2C_BUS)

CONFIG_REG = 0x01
CONVERSION_REG = 0x00


def read_ads1115():
    try:
        # Configure ADS1115:
        # Single-shot mode
        # A0 single-ended
        # ±4.096V range
        # 128 SPS
        config = 0xC183

        bus.write_i2c_block_data(
            ADC_ADDR,
            CONFIG_REG,
            [(config >> 8) & 0xFF, config & 0xFF]
        )

        time.sleep(0.1)

        data = bus.read_i2c_block_data(ADC_ADDR, CONVERSION_REG, 2)

        raw = struct.unpack('>h', bytes(data))[0]

        return raw

    except Exception as e:
        print("❌ ADC read error:", e)
        return None


def read_soil_moisture():
    value = read_ads1115()

    if value is None:
        print("❌ Soil moisture sensor not detected")
        return None

    voltage = value * 4.096 / 32768.0

    print("🌱 Moisture Reading:")
    print("Raw ADC:", value)
    print("Voltage:", round(voltage, 3), "V")

    return value
# ========================
# PIGPIO SETUP
# ========================

pi = pigpio.pi()

if not pi.connected:
    print("❌ pigpiod not running")
    sys.exit()

# Set GPIO modes
pi.set_mode(SERVO_1_PIN, pigpio.OUTPUT)
pi.set_mode(SERVO_2_PIN, pigpio.OUTPUT)
pi.set_mode(PUMP_PIN, pigpio.OUTPUT)

pi.write(PUMP_PIN, 0)

print("✅ GPIO Initialised")

# ========================
# SERVO FUNCTIONS
# ========================

def set_servo_angle(pin, angle):
    pulsewidth = 500 + (angle / 180.0) * 2000
    pi.set_servo_pulsewidth(pin, pulsewidth)

def stop_servos():
    pi.set_servo_pulsewidth(SERVO_1_PIN, 0)
    pi.set_servo_pulsewidth(SERVO_2_PIN, 0)

# ========================
# WATER PUMP FUNCTION
# ========================

def run_pump(duration=2):
    print("💧 Pump ON")
    pi.write(PUMP_PIN, 1)
    time.sleep(duration)
    pi.write(PUMP_PIN, 0)
    print("💧 Pump OFF")

# ========================
# SOIL MOISTURE FUNCTION
# ========================

def read_soil_moisture():
    try:
        # Read single byte from ADC
        value = bus.read_byte(SOIL_SENSOR_ADDR)
        print(f"🌱 Raw Soil Moisture Reading: {value}")
        return value
    except Exception as e:
        print("❌ Soil moisture sensor not detected")
        print("Error:", e)
        return None

# ========================
# MAIN LOOP
# ========================

print("🌿 System Ready")

try:
    while True:
        command = input("Enter command (left/right/up/down/water/moisture/exit): ").lower()

        if command == "left":
            set_servo_angle(SERVO_1_PIN, 45)

        elif command == "right":
            set_servo_angle(SERVO_1_PIN, 135)

        elif command == "up":
            set_servo_angle(SERVO_2_PIN, 45)

        elif command == "down":
            set_servo_angle(SERVO_2_PIN, 135)

        elif command == "water":
            run_pump(2)

        elif command == "moisture":
            moisture = read_soil_moisture()
            if moisture is not None:
                print(f"🌱 Moisture Level = {moisture}")

        elif command == "exit":
            break

        else:
            print("Unknown command")

except KeyboardInterrupt:
    pass

finally:
    stop_servos()
    pi.write(PUMP_PIN, 0)
    pi.stop()
    print("🛑 Shutdown complete")
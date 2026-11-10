import pigpio
import time
import smbus2
import sys
import struct

# ========================
# GPIO PIN MAPPING
# ========================

SERVO_1_PIN = 12
SERVO_2_PIN = 13
PUMP_PIN    = 18

# ========================
# I2C SETUP (ADS1115)
# ========================

I2C_BUS = 1
ADC_ADDR = 0x48

bus = smbus2.SMBus(I2C_BUS)

# ADS1115 Registers
CONFIG_REG = 0x01
CONVERSION_REG = 0x00

# ========================
# PIGPIO SETUP
# ========================

pi = pigpio.pi()

if not pi.connected:
    print("❌ pigpiod not running")
    sys.exit()

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
# SOIL MOISTURE (ADS1115)
# ========================

def read_ads1115(channel=0):
    try:
        # Config for single-ended A0
        config = 0xC183  # 0b1100000110000011
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
    value = read_ads1115(0)
    if value is None:
        print("❌ Soil sensor not detected")
        return None

    # Convert to voltage (±4.096V range)
    voltage = value * 4.096 / 32768.0

    print(f"🌱 Raw ADC: {value}")
    print(f"🌱 Voltage: {voltage:.3f} V")

    return value

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
                print(f"🌱 Moisture Reading = {moisture}")

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
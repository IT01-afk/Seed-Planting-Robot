import pigpio
import time

# ================= SERVO SETUP =================
SERVO_X = 17
SERVO_Y = 27

pi = pigpio.pi()

if not pi.connected:
    print("Pigpio daemon not running")
    exit()

pi.set_mode(SERVO_X, pigpio.OUTPUT)
pi.set_mode(SERVO_Y, pigpio.OUTPUT)

# Track last pulse to prevent unnecessary updates
last_x = 0
last_y = 0

def move_servo(pin, pulse, last_value):
    pulse = max(1000, min(2000, pulse))  # safety clamp
    
    if pulse != last_value:
        pi.set_servo_pulsewidth(pin, pulse)
        return pulse
    return last_value

def stop_servo(pin):
    pi.set_servo_pulsewidth(pin, 0)

# ================= MAIN LOOP =================

try:
    while True:
        # Replace this with your controller input logic
        x_pulse = 1500
        y_pulse = 1500

        last_x = move_servo(SERVO_X, x_pulse, last_x)
        last_y = move_servo(SERVO_Y, y_pulse, last_y)

        time.sleep(0.02)

except KeyboardInterrupt:
    stop_servo(SERVO_X)
    stop_servo(SERVO_Y)
    pi.stop()
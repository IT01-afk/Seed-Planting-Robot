import pigpio
import time

SERVO_PIN = 17   # change to your servo GPIO (BCM)

pi = pigpio.pi()

if not pi.connected:
    print("Pigpio not connected")
    exit()

# Set as output explicitly (fixes your previous error)
pi.set_mode(SERVO_PIN, pigpio.OUTPUT)

print("Moving to center")
pi.set_servo_pulsewidth(SERVO_PIN, 1500)
time.sleep(2)

print("Moving left")
pi.set_servo_pulsewidth(SERVO_PIN, 1000)
time.sleep(2)

print("Moving right")
pi.set_servo_pulsewidth(SERVO_PIN, 2000)
time.sleep(2)

print("Stopping")
pi.set_servo_pulsewidth(SERVO_PIN, 0)

pi.stop()
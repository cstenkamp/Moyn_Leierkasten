import mido
import time
import serial
import re
import threading
from queue import Queue
import rtmidi

for _ in range(10):
    try:
        print(mido.get_output_names())
    except rtmidi._rtmidi.SystemError:
        print("nop")
    else:
        print("got it")
        break

MIDI_FILE = "/home/chris/Documents/projects/wanderzirkus/leierkasten/alte-k.mid"

# Serial communication setup
ser = serial.Serial('/dev/ttyUSB0', 115200)  # Change port and baud rate as needed

# MIDI playback setup
mid = mido.MidiFile(MIDI_FILE)  # Replace with your MIDI file's path
output = mido.open_output(mido.get_output_names()[0])

# Initialize thread-safe queue
rpm_queue = Queue()

# Define a lock for thread synchronization
lock = threading.Lock()

# Variable to hold the last RPM update time
last_rpm_update_time = time.time()

# Function to read RPM from serial and put it in the queue
def read_rpm_thread():
    global last_rpm_update_time
    while True:
        serial_data = ser.readline().decode().strip()  # Read serial data
        rpm_match = re.search(r'Average RPM \(Last 5000 ms\): (\d+\.\d+)', serial_data)
        current_time = time.time()
        if rpm_match and current_time - last_rpm_update_time >= 0.5:
            rpm = float(rpm_match.group(1))  # Extract RPM value from serial data
            with lock:
                print(rpm)
                rpm_queue.put(rpm)  # Put RPM in the queue
                last_rpm_update_time = current_time
        time.sleep(0.05)  # Sleep for 50 ms to avoid busy waiting

# Function to adjust playback speed and handle MIDI playback
def playback_thread():
    current_rpm = 20.0  # Default RPM value
    while True:
        try:
            with lock:
                if not rpm_queue.empty():
                    current_rpm = rpm_queue.get()  # Get the most recent RPM value from the queue
            for msg in mid.play():
                if msg.type == 'note_on' or msg.type == 'note_off':
                    adjusted_time = adjust_playback_speed(msg.time, current_rpm)
                    time.sleep(adjusted_time)
                    output.send(msg)
        except KeyboardInterrupt:
            break

# Playback speed adjustment function
def adjust_playback_speed(event_time, rpm):
    rpm = max(rpm, 0.01)  # Set a minimum RPM value
    speed_factor = 20 / rpm  # Adjust speed based on 20 RPM as reference
    adjusted_time = event_time * speed_factor
    return min(adjusted_time, 0.2)  # Limit adjusted time to a maximum of 200 ms

# Create and start threads
read_thread = threading.Thread(target=read_rpm_thread)
playback_thread = threading.Thread(target=playback_thread)

read_thread.start()
playback_thread.start()

try:
    read_thread.join()
    playback_thread.join()
except KeyboardInterrupt:
    ser.close()
    output.close()

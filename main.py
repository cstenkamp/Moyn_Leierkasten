from time import sleep, time
import serial
import re
import threading
from queue import Queue

from anki.pylib.anki.sound import SoundOrVideoTag
from anki.qt import aqt
from anki.qt.aqt.sound import SimpleMplayerSlaveModePlayer
from anki.qt.aqt.taskman import TaskManager

def main():
    kasten = Leierkasten()
    song = SoundOrVideoTag('/home/chris/Documents/projects/wanderzirkus/leierkasten/musik/Britney Spears - Toxic.mp3')
    kasten.player.play(song)
    kasten.run()
    # sleep(2)
    # kasten.player.command("speed_set 0.5")


class Leierkasten():

    def __init__(self, rpm_for_1 = 20, serial_port = '/dev/ttyUSB1', baudrate = 115200, default_rpm = 20):
        self.rpm_for_1 = rpm_for_1
        self.ser = serial.Serial(serial_port, baudrate)
        self.rpm_queue = Queue()
        self.lock = threading.Lock()
        # self.last_rpm_update_time = time()
        self.player = setup_player()
        self.default_rpm = default_rpm

    def read_rpm_thread(self):
        last_rpm_update_time = time()
        while True:
            serial_data = self.ser.readline().decode().strip()  # Read serial data
            rpm_match = re.search(r'Average RPM \(Last 5000 ms\): (\d+\.\d+)', serial_data)
            current_time = time()
            if rpm_match and current_time - last_rpm_update_time >= 0.5:
                rpm = float(rpm_match.group(1))  # Extract RPM value from serial data
                with self.lock:
                    print("RPM:", rpm)
                    self.rpm_queue.put(rpm)  # Put RPM in the queue
                    last_rpm_update_time = current_time
            sleep(0.05)  # Sleep for 50 ms to avoid busy waiting

    def playback_thread(self):
        current_rpm = self.default_rpm
        while True:
            try:
                with self.lock:
                    if not self.rpm_queue.empty():
                        current_rpm = self.rpm_queue.get()
                self.player.command(f"speed_set {current_rpm / self.rpm_for_1}")
            except KeyboardInterrupt:
                break

    @staticmethod
    def adjust_playback_speed(event_time, rpm):
        rpm = max(rpm, 0.01)  # Set a minimum RPM value
        speed_factor = 20 / rpm  # Adjust speed based on 20 RPM as reference
        adjusted_time = event_time * speed_factor
        return min(adjusted_time, 0.2)  # Limit adjusted time to a maximum of 200 ms

    def run(self):
        read_thread = threading.Thread(target=self.read_rpm_thread)
        playback_thread = threading.Thread(target=self.playback_thread)
        read_thread.start()
        playback_thread.start()

        try:
            read_thread.join()
            playback_thread.join()
        except KeyboardInterrupt:
            self.ser.close()


def setup_player():
    taskman = TaskManager(None)
    aqt.sound.setup_audio(taskman, "/home/chris/Documents/projects/wanderzirkus/leierkasten/musik/",
                                   "/home/chris/Documents/projects/wanderzirkus/leierkasten/musik/" ) #self.pm.base, self.col.media.dir())
    return SimpleMplayerSlaveModePlayer(taskman, "/home/chris/Documents/projects/wanderzirkus/leierkasten/musik/")



if __name__ == '__main__':
    main()

import os
import sys
from time import sleep, time
import serial
import re
import threading
from queue import Queue

from mplayer_util import SimpleMplayerSlaveModePlayer
import json
from settings import BASE_DIR, SPEED_FACTOR
import subprocess


# TODO: long button-press switches between nomove = [pause, veeeryslow, 1xspeed]
# TODO: das mit dem moving average arduino-seitig besser machen (see jakobs messages)
# TODO: der arm braucht mehr drehwiederstand

def execute(cmd, **kwargs):
    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, **kwargs)
    for stdout_line in iter(popen.stdout.readline, ""):
        yield stdout_line.strip()
    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, cmd)
    
def crawl_songs(base_dir):
    return (" ".join(line for line in execute(["ls", "-m", base_dir])).split(", "))

class SoundOrVideoTag():
    def __init__(self, filename):
        self.filename = filename

def main():
    # with open("songs.json", "r") as rfile:
    #     songs = json.load(rfile)
    songs = crawl_songs(BASE_DIR)
    print(songs)
    kasten = Leierkasten(BASE_DIR, songs)
    kasten.play()
    kasten.run()

def done_callback():
    print("DONE!!!")

class NullContextManager(object):
    def __init__(self, dummy_resource=None):
        self.dummy_resource = dummy_resource
    def __enter__(self):
        return self.dummy_resource
    def __exit__(self, *args):
        pass

class Leierkasten():

    def __init__(self, base_dir, songs, rpm_for_1 = 20, serial_port = None, baudrate = 115200, default_rpm = 20, song_index = 0):
        self.song_index = song_index
        self.songs = songs
        if serial_port is None:
            serial_port = "/dev/"+[i for i in os.listdir("/dev") if "ttyUSB" in i][0]
        self.base_dir = base_dir
        self.rpm_for_1 = rpm_for_1
        self.ser = serial.Serial(serial_port, baudrate)
        self.rpm_queue = Queue()
        self.cmd_queue = Queue()
        self.kill_queue = Queue()
        self.mplayerout_queue = Queue()
        self.lock = threading.Lock()
        # self.last_rpm_update_time = time()
        self.player = setup_player(base_dir)
        self.default_rpm = default_rpm
        self.is_pausing = True

    def play(self, index=0):
        song = SoundOrVideoTag(self.songs[index])
        self.player.play(song, done_callback)
        self.is_pausing = False

    def next_song(self, must_pause=True, no_lock=False):
        """!! only puts something in the command-queue such that _nextsong_mainthread is called !!"""
        self.song_index = (self.song_index + 1) % len(self.songs)
        song = SoundOrVideoTag(self.songs[self.song_index])
        print(f"Next song: {song.filename}")
        with (self.lock if not no_lock else NullContextManager()):
            if must_pause:
                self.cmd_queue.put(("pause", f"play \"{os.path.join(self.base_dir, song.filename)}\"")) # self.player.toggle_pause(), # self.player.command(f"loadfile {song.filename}"), ...
            else:
                self.cmd_queue.put(f"play \"{os.path.join(self.base_dir, song.filename)}\"") # self.player.toggle_pause(), # self.player.command(f"loadfile {song.filename}"), ...

    def _nextsong_mainthread(self, cmd, must_pause=False):
        if must_pause:
            self.player.toggle_pause()
            self.is_pausing = not self.is_pausing
            # print(f"toggled pause - is now {self.is_pausing}")
            # self.play(self.song_index)
            newcommand = cmd.replace("play", "loadfile")+" 0"
            # print(f"now executing {newcommand}")
            self.player.command(newcommand)
            self.is_pausing = False
        else:
            self.play(self.song_index)

    def print_mplayer_thread(self):
        while self.kill_queue.empty():
            if self.player._process:
                line = self.player._process.stdout.readline()
                if len(line) == 0:
                    break
                line = line.decode("UTF-8")
                # print(line)
                if "End of file" in line:
                    self.mplayerout_queue.put("ended")
            sleep(0.05)
            # if not self.mplayerout_queue.empty():
            #     line = self.mplayerout_queue.get()
            #     print(line)
            #     sleep(0.01)



    def read_rpm_thread(self):
        last_rpm_update_time = time()
        while self.kill_queue.empty():
            try:
                line = self.ser.readline()
                if line:
                    try:
                        serial_data = line.decode("UTF-8").strip()  # Read serial data
                    except UnicodeDecodeError:
                        print("UnicodeDecodeError!", file=sys.stderr)
                        continue
                    rpm_match = re.search(r'Average RPM \(Last (\d+) ms\): (-?\d+\.\d+)', serial_data)
                    current_time = time()
                    if rpm_match and current_time - last_rpm_update_time >= 0.5:
                        with self.lock:
                            rpm = abs(float(rpm_match.group(2)))  # Extract RPM value from serial data
                            # TODO not abs, but treat negative as negative??
                            print(f"RPM ({rpm_match.group(1)} ms interval): {rpm}")
                            self.rpm_queue.put(rpm)  # Put RPM in the queue
                            last_rpm_update_time = current_time
                    elif re.search(r'button1_pressed', serial_data):
                        pass
                    elif re.search(r'button1_released', serial_data):
                        self.next_song()
                sleep(0.05)  # Sleep for 50 ms to avoid busy waiting
            except Exception as e:
                print("!! Exception !!")
                raise e

        print("read_rpm_thread ending!")

    def playback_thread(self):
        current_rpm = self.default_rpm
        while self.kill_queue.empty():
            try:
                with self.lock:
                    if not self.rpm_queue.empty():
                        current_rpm = self.rpm_queue.get()

                    if not self.cmd_queue.empty():
                        cmd = self.cmd_queue.get()
                        do_pause = False
                        print(f"Received command: {cmd}")
                        if isinstance(cmd, (list, tuple)) and cmd[0] == "pause":
                            do_pause = True
                            cmd = cmd[1]
                        if cmd.startswith("play"):
                            self._nextsong_mainthread(cmd, do_pause)
                    if not self.mplayerout_queue.empty():
                        while not self.mplayerout_queue.empty():
                            self.mplayerout_queue.get()
                        print("Song ended, next!")
                        self.next_song(must_pause=False, no_lock=True)

                if not self.is_pausing:
                    errored = False
                    for _ in range(5):
                        try:
                            rpm_factor = current_rpm / self.rpm_for_1
                            if rpm_factor == 0:
                                speed = 0
                            elif rpm_factor > 1:
                                speed = abs(1 - rpm_factor) * SPEED_FACTOR + 1
                            else:
                                speed = 1 - (abs(1 - rpm_factor) * SPEED_FACTOR)
                            # print(f"rpm_factor: {rpm_factor}, speed: {speed}")
                            self.player.command(f"speed_set {speed}")
                        except BrokenPipeError as e:
                            sleep(0.01)
                            errored = True
                        else:
                            if errored:
                                print("Escaped error")
                            break
                sleep(0.05)
            except KeyboardInterrupt:
                break
        print("playback_thread ended")

    @staticmethod
    def adjust_playback_speed(event_time, rpm):
        rpm = max(rpm, 0.01)  # Set a minimum RPM value
        speed_factor = 20 / rpm  # Adjust speed based on 20 RPM as reference
        adjusted_time = event_time * speed_factor
        return min(adjusted_time, 0.2)  # Limit adjusted time to a maximum of 200 ms

    def run(self):
        read_thread = threading.Thread(target=self.read_rpm_thread)
        playback_thread = threading.Thread(target=self.playback_thread)
        print_mplayer_thread = threading.Thread(target=self.print_mplayer_thread)
        read_thread.start()
        playback_thread.start()
        print_mplayer_thread.start()

        try:
            try:
                while True:
                    sleep(0.5)
            except KeyboardInterrupt:
                print("KILLING")
                self.kill_queue.put("kill")
            read_thread.join()
            playback_thread.join()
        except KeyboardInterrupt:
            print("KILLED - Closing Serial!")
            self.ser.close()
            self.kill_queue.put("kill")


def setup_player(base_dir):
    return SimpleMplayerSlaveModePlayer(None, base_dir)



if __name__ == '__main__':
    main()

# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import os
import sys
import subprocess
from abc import ABC, abstractmethod
from concurrent.futures import Future
from dataclasses import dataclass
import time
from pathlib import Path
from typing import Any, Collection, Callable, Union


is_win = is_mac = False

OnDoneCallback = Callable[[], None]



def startup_info():
    "Use subprocess.Popen(startupinfo=...) to avoid opening a console window."
    if sys.platform != "win32":
        return None
    si = subprocess.STARTUPINFO()  # pytype: disable=module-attr
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # pytype: disable=module-attr
    return si


class _MediaFileFilterFilter:
    """Allows manipulating the file path that media will be read from"""

    _hooks = []

    def append(self, callback):
        """(txt: str)"""
        self._hooks.append(callback)

    def remove(self, callback):
        if callback in self._hooks:
            self._hooks.remove(callback)

    def count(self):
        return len(self._hooks)

    def __call__(self, txt):
        for filter in self._hooks:
            try:
                txt = filter(txt)
            except:
                # if the hook fails, remove it
                self._hooks.remove(filter)
                raise
        return txt


media_file_filter = _MediaFileFilterFilter()

class Player(ABC):
    @abstractmethod
    def play(self, tag, on_done):
        """Play a file.

        When reimplementing, make sure to call
        gui_hooks.av_player_did_begin_playing(self, tag)
        on the main thread after playback begins.
        """

    def stop(self):
        """Optional.

        If implemented, the player must not call on_done() when the audio is stopped."""

    def seek_relative(self, secs: int):
        "Jump forward or back by secs. Optional."

    def toggle_pause(self):
        "Optional."

    def shutdown(self):
        "Do any cleanup required at program termination. Optional."


AUDIO_EXTENSIONS = {
    "3gp",
    "flac",
    "m4a",
    "mp3",
    "oga",
    "ogg",
    "opus",
    "spx",
    "wav",
}


def is_audio_file(fname):
    ext = fname.split(".")[-1].lower()
    return ext in AUDIO_EXTENSIONS


class SoundOrVideoPlayer(Player):  # pylint: disable=abstract-method
    default_rank = 0

    def rank_for_tag(self, tag):
        if hasattr(tag, "filename"):
            return self.default_rank
        else:
            return None


class SoundPlayer(Player):  # pylint: disable=abstract-method
    default_rank = 0

    def rank_for_tag(self, tag):
        if hasattr(tag, "filename") and is_audio_file(tag.filename):
            return self.default_rank
        else:
            return None


# Packaged commands
##########################################################################


# return modified command array that points to bundled command, and return
# required environment
def _packagedCmd(cmd):
    cmd = cmd[:]
    env = os.environ.copy()
    if "LD_LIBRARY_PATH" in env:
        del env["LD_LIBRARY_PATH"]

    if is_win:
        packaged_path = Path(sys.prefix) / (cmd[0] + ".exe")
    elif is_mac:
        packaged_path = Path(sys.prefix) / ".." / "Resources" / cmd[0]
    else:
        packaged_path = Path(sys.prefix) / cmd[0]
    if packaged_path.exists():
        cmd[0] = str(packaged_path)

    return cmd, env


# Platform hacks
##########################################################################

# legacy global for add-ons
si = startup_info()


# osx throws interrupted system call errors frequently
def retryWait(proc: subprocess.Popen):
    while 1:
        try:
            return proc.wait()
        except OSError:
            continue


# Simple player implementations
##########################################################################


class SimpleProcessPlayer(Player):  # pylint: disable=abstract-method
    "A player that invokes a new process for each tag to play."

    args = []
    env = None

    def __init__(self, taskman, media_folder = None):
        self._taskman = taskman
        self._media_folder = media_folder
        self._terminate_flag = False
        self._process = None
        self._warned_about_missing_player = False
        self.current_tag = None

    def play(self, tag, on_done: OnDoneCallback = None):
        if on_done is None:
            on_done = lambda: print("song ended.")
        self._terminate_flag = False
        self.current_tag = tag
        # self._taskman.run_in_background(
        #     lambda: self._play(tag), lambda res: self._on_done(res, on_done)
        # )
        self._play(tag)

    def stop(self):
        self._terminate_flag = True

    # note: mplayer implementation overrides this
    def _play(self, tag):
        assert hasattr(tag, "filename")
        self._process = subprocess.Popen(
            self.args + [tag.filename],
            env=self.env,
            cwd=self._media_folder,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self._wait_for_termination(tag)

    def _wait_for_termination(self, tag):
        # self._taskman.run_on_main(
        #     lambda: gui_hooks.av_player_did_begin_playing(self, tag)
        # )

        while True:
            # should we abort playing?
            if self._terminate_flag:
                self._process.terminate()
                self._process.wait(1)
                try:
                    if self._process.stdin:
                        self._process.stdin.close()
                except Exception as e:
                    print("unable to close stdin:", e)
                self._process = None
                return

            # wait for completion
            try:
                self._process.wait(0.1)
                if self._process.returncode != 0:
                    print(f"player got return code: {self._process.returncode}")
                try:
                    if self._process.stdin:
                        self._process.stdin.close()
                except Exception as e:
                    print("unable to close stdin:", e)
                self._process = None
                return
            except subprocess.TimeoutExpired:
                # process still running, repeat loop
                pass

    def _on_done(self, ret, cb):
        try:
            ret.result()
        except FileNotFoundError:
            if not self._warned_about_missing_player:
                # showWarning(tr.media_sound_and_video_on_cards_will())
                self._warned_about_missing_player = True
            # must call cb() here, as we don't currently have another way
            # to flag to av_player that we've stopped
        cb()


class SimpleMplayerPlayer(SimpleProcessPlayer, SoundOrVideoPlayer):
    # args, env = _packagedCmd(["mplayer", "-really-quiet", "-noautosub"])
    args, env = _packagedCmd(["mplayer", "-quiet", "-noautosub"])
    # print("args:", args) # "env:", env)
    env["TERM"] = "xterm-256color"
    if is_win:
        args += ["-ao", "win32"]

# Mplayer in slave mode
##########################################################################


class SimpleMplayerSlaveModePlayer(SimpleMplayerPlayer):
    def __init__(self, taskman, media_folder: str):
        self.media_folder = media_folder
        self.current_tag = None
        super().__init__(taskman, media_folder)
        self.args.append("-slave")


    def _poll_stdfile(self, stdfile, poll_for = 1):
        # text = ""
        # poll_stdfile = select.poll()
        # poll_stdfile.register(stdfile, select.POLLIN)
        #
        # start_time = time.time()
        # line = ""
        # while (time.time() < start_time + poll_for*1):
        #     poll_result = poll_stdfile.poll(0)
        #     if poll_result:
        #         line = stdfile.readline()
        #         if line:
        #             text += line.decode("UTF-8")
        # return text
        for stdout_line in iter(stdfile.readline, ""):
            if stdout_line:
                print(stdout_line.strip())
            else:
                break
        return ""



    def _play(self, tag):
        assert hasattr(tag, "filename")
        self.current_tag = tag

        filename = media_file_filter(tag.filename)

        self._process = subprocess.Popen(
            self.args + [filename],
            env=self.env,
            cwd=self.media_folder,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startup_info(),
        )
        # self._wait_for_termination(tag)

    def _command(self, *args: Any, poll_outerr = False):
        """Send a command over the slave interface.

        The trailing newline is automatically added."""
        str_args = [str(x) for x in args]
        if self._process:
            for trial in range(1000):
                try:
                    self._process.stdin.write(" ".join(str_args).encode("utf8") + b"\n")
                    self._process.stdin.flush()
                except BrokenPipeError as e:
                    if trial < 3:
                        print(f"BrokenPipeError #{trial}! Waiting..")
                        time.sleep(0.5)
                    else:
                        raise e
                else:
                    break

        return "", ""

    def command(self, *args: Any, poll_outerr = False, ignore_exc=False):
        """ignore_exc: I have the brokenpipeexception when trying to play a new song when there is no song playing.
        While in that case it's relevant, it's not relevant for the speed_set command, there it should just nothing happen"""
        try:
            self._command(*args, poll_outerr=poll_outerr)
        except BrokenPipeError as e:
            if ignore_exc:
                print("Ignoring the BrokenPipeErrors. (probably because its speed_set command")
                return
            # print(f"Many BrokenPipeErrors. re-playing current one and re-executing - for command: {args}")
            print(f"Many BrokenPie")
            try:
                self.play(self.current_tag)
            except AttributeError as e:
                print("No current song to play, ignoring exception.")
                # AttributeError: 'SimpleMplayerSlaveModePlayer' object has no attribute 'current_tag'
                # should be the case for speed_set
            else:
                self._command(*args, poll_outerr=poll_outerr)

    def seek_relative(self, secs: int):
        self.command("seek", secs, 0)

    def toggle_pause(self):
        self.command("pause")


# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import os
import sys
import subprocess
from abc import ABC, abstractmethod
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Collection, Callable, Union


is_win = is_mac = False

OnDoneCallback = Callable[[], None]



def startup_info() -> Any:
    "Use subprocess.Popen(startupinfo=...) to avoid opening a console window."
    if sys.platform != "win32":
        return None
    si = subprocess.STARTUPINFO()  # pytype: disable=module-attr
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # pytype: disable=module-attr
    return si

@dataclass
class TTSTag:
    """Records information about a text to speech tag.

    See tts.py for more information.
    """

    field_text: str
    lang: str
    voices: list[str]
    speed: float
    # each arg should be in the form 'foo=bar'
    other_args: list[str]


@dataclass
class SoundOrVideoTag:
    """Contains the filename inside a [sound:...] tag.

    Video files also use [sound:...].
    """

    filename: str


# note this does not include image tags, which are handled with HTML.
AVTag = Union[SoundOrVideoTag, TTSTag]


class _MediaFileFilterFilter:
    """Allows manipulating the file path that media will be read from"""

    _hooks: list[Callable[["str"], str]] = []

    def append(self, callback: Callable[["str"], str]) -> None:
        """(txt: str)"""
        self._hooks.append(callback)

    def remove(self, callback: Callable[["str"], str]) -> None:
        if callback in self._hooks:
            self._hooks.remove(callback)

    def count(self) -> int:
        return len(self._hooks)

    def __call__(self, txt: str) -> str:
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
    def play(self, tag: AVTag, on_done: OnDoneCallback) -> None:
        """Play a file.

        When reimplementing, make sure to call
        gui_hooks.av_player_did_begin_playing(self, tag)
        on the main thread after playback begins.
        """

    def stop(self) -> None:
        """Optional.

        If implemented, the player must not call on_done() when the audio is stopped."""

    def seek_relative(self, secs: int) -> None:
        "Jump forward or back by secs. Optional."

    def toggle_pause(self) -> None:
        "Optional."

    def shutdown(self) -> None:
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


def is_audio_file(fname: str) -> bool:
    ext = fname.split(".")[-1].lower()
    return ext in AUDIO_EXTENSIONS


class SoundOrVideoPlayer(Player):  # pylint: disable=abstract-method
    default_rank = 0

    def rank_for_tag(self, tag: AVTag) -> int | None:
        if isinstance(tag, SoundOrVideoTag):
            return self.default_rank
        else:
            return None


class SoundPlayer(Player):  # pylint: disable=abstract-method
    default_rank = 0

    def rank_for_tag(self, tag: AVTag) -> int | None:
        if isinstance(tag, SoundOrVideoTag) and is_audio_file(tag.filename):
            return self.default_rank
        else:
            return None


# Packaged commands
##########################################################################


# return modified command array that points to bundled command, and return
# required environment
def _packagedCmd(cmd: list[str]) -> tuple[Any, dict[str, str]]:
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
def retryWait(proc: subprocess.Popen) -> int:
    while 1:
        try:
            return proc.wait()
        except OSError:
            continue


# Simple player implementations
##########################################################################


class SimpleProcessPlayer(Player):  # pylint: disable=abstract-method
    "A player that invokes a new process for each tag to play."

    args: list[str] = []
    env: dict[str, str] | None = None

    def __init__(self, taskman, media_folder: str | None = None) -> None:
        self._taskman = taskman
        self._media_folder = media_folder
        self._terminate_flag = False
        self._process: subprocess.Popen | None = None
        self._warned_about_missing_player = False

    def play(self, tag: AVTag, on_done: OnDoneCallback = None) -> None:
        if on_done is None:
            on_done = lambda: print("song ended.")
        self._terminate_flag = False
        self._taskman.run_in_background(
            lambda: self._play(tag), lambda res: self._on_done(res, on_done)
        )

    def stop(self) -> None:
        self._terminate_flag = True

    # note: mplayer implementation overrides this
    def _play(self, tag: AVTag) -> None:
        assert isinstance(tag, SoundOrVideoTag)
        self._process = subprocess.Popen(
            self.args + [tag.filename],
            env=self.env,
            cwd=self._media_folder,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self._wait_for_termination(tag)

    def _wait_for_termination(self, tag: AVTag) -> None:
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

    def _on_done(self, ret: Future, cb: OnDoneCallback) -> None:
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
    def __init__(self, taskman, media_folder: str) -> None:
        self.media_folder = media_folder
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



    def _play(self, tag: AVTag) -> None:
        # assert isinstance(tag, SoundOrVideoTag)

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

    def command(self, *args: Any, poll_outerr = False) -> Collection[str]:
        """Send a command over the slave interface.

        The trailing newline is automatically added."""
        str_args = [str(x) for x in args]
        if self._process:
            self._process.stdin.write(" ".join(str_args).encode("utf8") + b"\n")
            self._process.stdin.flush()
            # if poll_outerr:
            #     if not self._process:
            #         print("hä")
            #         return "", ""
            #     print("polling self._process")
            #     res = self._poll_stdfile(self._process.stdout), self._poll_stdfile(self._process.stderr)
            #     print("polling self._process done")
            #     return res
        return "", ""

    def seek_relative(self, secs: int) -> None:
        self.command("seek", secs, 0)

    def toggle_pause(self) -> None:
        self.command("pause")


# MP3 transcoding
##########################################################################

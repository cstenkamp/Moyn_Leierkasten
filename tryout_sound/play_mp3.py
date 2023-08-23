import os
import subprocess
import sys
from typing import Any, Dict, List, Tuple

isMac = isWin = False

def main():
    song = '/home/chris/Documents/projects/wanderzirkus/leierkasten/musik/Britney Spears - Toxic.mp3'
    player = SimpleMplayerSlaveModePlayer()
    player._play(song)

# return modified command array that points to bundled command, and return
# required environment
def _packagedCmd(cmd: List[str]) -> Tuple[Any, Dict[str, str]]:
    cmd = cmd[:]
    env = os.environ.copy()
    if "LD_LIBRARY_PATH" in env:
        del env["LD_LIBRARY_PATH"]
    if isMac:
        dir = os.path.dirname(os.path.abspath(__file__))
        exeDir = os.path.abspath(dir + "/../../Resources/audio")
    else:
        exeDir = os.path.dirname(os.path.abspath(sys.argv[0]))
        if isWin and not cmd[0].endswith(".exe"):
            cmd[0] += ".exe"
    path = os.path.join(exeDir, cmd[0])
    if not os.path.exists(path):
        return cmd, env
    cmd[0] = path
    return cmd, env

class SimpleMplayerPlayer():
    args, env = _packagedCmd(["mplayer", "-really-quiet", "-noautosub"])
    if isWin:
        args += ["-ao", "win32"]

class SimpleMplayerSlaveModePlayer(SimpleMplayerPlayer):
    def __init__(self):
        super().__init__()
        self.args.append("-slave")

    def _play(self, filename) -> None:
        self._process = subprocess.Popen(
            self.args + [filename],
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # startupinfo=startup_info(),
        )
        self._wait_for_termination(tag)

    def command(self, *args: Any) -> None:
        """Send a command over the slave interface.
        The trailing newline is automatically added."""
        str_args = [str(x) for x in args]
        if self._process:
            self._process.stdin.write(" ".join(str_args).encode("utf8") + b"\n")
            self._process.stdin.flush()

    def seek_relative(self, secs: int) -> None:
        self.command("seek", secs, 0)

    def toggle_pause(self) -> None:
        self.command("pause")


    def _wait_for_termination(self, tag: AVTag) -> None:
        self._taskman.run_on_main(
            lambda: gui_hooks.av_player_did_begin_playing(self, tag)
        )

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
                showWarning(tr.media_sound_and_video_on_cards_will())
                self._warned_about_missing_player = True
            # must call cb() here, as we don't currently have another way
            # to flag to av_player that we've stopped
        cb()


if __name__ == '__main__':
    main()

from anki.pylib.anki.sound import SoundOrVideoTag
from anki.qt import aqt
from anki.qt.aqt.sound import SimpleMplayerSlaveModePlayer
from anki.qt.aqt.taskman import TaskManager

def setup_player(base_dir):
    taskman = TaskManager(None)
    aqt.sound.setup_audio(taskman, base_dir, base_dir)
    return SimpleMplayerSlaveModePlayer(taskman, base_dir)
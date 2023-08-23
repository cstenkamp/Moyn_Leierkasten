## Install

Keep in mind that midi-files don't contain audio: *MIDIs don't contain audio, but notes played by a specific instruments and timestamps when said instrument should play, you need something that has the instruments audio and something that converts the notes and instruments and timestamps into something audible.* (https://bbs.archlinux.org/viewtopic.php?id=260019), so let's install `fluidsynth`:

```
sudo apt install fluidsynth
systemctl --user start fluidsynth
```

### Meehhh, for mp3 is better.

We want to use mplayer, which can regularly update the playback speed: https://unix.stackexchange.com/a/578168/441563. For that, we just use the Anki sound-library that did it: https://raw.githubusercontent.com/ankitects/anki/484377b8091179504b21b29be1de6925c70af4bd/qt/aqt/sound.py. Sooo for that we need PortAudio: https://askubuntu.com/a/1090345

```
sudo apt-get install libasound-dev portaudio19-dev libportaudio2 libportaudiocpp0
sudo apt-get install ffmpeg libav-tools
sudo apt install mplayer
```

#### Fucking shit we just install anki.

https://github.com/ankitects/anki
https://github.com/ankitects/anki/blob/main/docs/linux.md
```
git clone git@github.com:ankitects/anki.git
sudo apt install bash grep findutils curl gcc g++ git rsync ninja-build
```
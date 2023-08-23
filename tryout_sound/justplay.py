import mido
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

def play(path: str):
    file = mido.MidiFile(path)
    with mido.open_output(mido.get_output_names()[0]) as port:
        for message in file.play():
            port.send(message)

def list_devices():
    print(mido.get_output_names())
    # ['IAC Driver Bus 1', 'IAC Driver Bus 1'] if on macOS.
    # ['Microsoft GS Wavetable Synth 0'] if on Windows.

if __name__ == '__main__':
    play(MIDI_FILE)
    # list_devices()

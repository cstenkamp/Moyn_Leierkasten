import os


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "musik"))
SONGS_JSON = os.path.join(os.path.basename(__file__), "songs.json")


SPEED_FACTOR = 0.25 # if 20 RPM is default speed, then with a SPEED_FACTOR=1 40 RPM would be 2x default. With SPEED_FACTOR=0.5, 40 RPM -> 1.5x default
# FROM DONE: die sensibilität einstellen können - dass der nen bisschen disktretisiert bzw ne abschwächende kurve über
#        die tatsächliche drehgeschwindigkeit liegt sodass nicht nur exakt 20RPM 1x speed sind und 30RPM schon 1.5x...
#        -> letztlich einfach nur: "doppelt so schnell drehen heißt NICHT doppelt so schnell abspielen, sondern nen faktor."
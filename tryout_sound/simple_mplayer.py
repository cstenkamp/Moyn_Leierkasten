import subprocess, time
# start mplayer
song = '/home/chris/Documents/projects/wanderzirkus/leierkasten/musik/Britney Spears - Toxic.mp3'
cmd = ['mplayer', '-slave', '-quiet', song]
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.PIPE)

# send a command every 3 seconds.
# Full command reference here: http://www.mplayerhq.hu/DOCS/tech/slave.txt
while True:
    print('sleep 3 seconds ...')
    time.sleep(3)
    cmd = 'get_meta_artist'
    print('send command: {}'.format(cmd))
    p.stdin.write(cmd)
    output = p.communicate()[0]
    print(output)
